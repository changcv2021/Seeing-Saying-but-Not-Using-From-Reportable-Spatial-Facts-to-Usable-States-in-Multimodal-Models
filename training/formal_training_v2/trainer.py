"""Single-GPU resumable Qwen3.5-9B LoRA trainer. Never opens held-out test."""
import argparse
from collections import Counter
import datetime
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import time

from paths import *
from core import Schedule, digest
from checkpoint import save_checkpoint, latest_checkpoint, restore_checkpoint, StopAtBoundary


def make_optimizer(model, updates):
    import torch
    from model_io import HP
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
        lr=HP['learning_rate'], weight_decay=HP['weight_decay'])
    warmup = max(1, math.ceil(updates*.03))
    def scale(step):
        if step < warmup: return (step+1)/warmup
        return max(0., (updates-step)/max(1, updates-warmup))
    return optimizer, torch.optim.lr_scheduler.LambdaLR(optimizer, scale)


def encode_row(processor, row, pool):
    from model_io_verified import encode
    from state_interface_v2 import encode_state_v2
    if pool == 'state':
        return encode_state_v2(processor, row['request'], task_prompt=row['task_prompt'],
                               target=row['target'], end_turn=row['end_turn'])
    return encode(processor, row['request'], row['target'], task_prompt=row.get('task_prompt'), end_turn=row['end_turn'])


def segmented_loss(model, batch, receipt, segment):
    import torch
    start = segment['offset']; n = segment['count']; p = receipt['prompt_tokens']
    if segment['target_tokens'] != receipt['target_tokens'] or start < 0 or start+n > receipt['target_tokens']:
        raise ValueError('LOSS_MASK_TOKEN_COUNT_MISMATCH')
    idx = torch.arange(p+start-1, p+start+n-1, device=model.device)
    output = model(**batch.to(model.device), use_cache=False, logits_to_keep=idx)
    labels = batch['input_ids'][:, p+start:p+start+n].to(model.device)
    return torch.nn.functional.cross_entropy(output.logits.float().reshape(-1, output.logits.shape[-1]), labels.reshape(-1), reduction='sum')


def train_update(model, processor, optimizer, scheduler, records, metadata, segments):
    import torch
    from model_io import HP
    total = sum(s['count'] for s in segments)
    optimizer.zero_grad(set_to_none=True)
    loss_sum = 0.; prompt_tokens = 0; processed_tokens = 0; receipts = []
    for seg in segments:
        row = records[seg['key']]; pool = metadata[seg['key']]['pool']
        batch, receipt = encode_row(processor, row, pool)
        loss = segmented_loss(model, batch, receipt, seg)
        if not torch.isfinite(loss): raise ValueError('NONFINITE_LOSS')
        (loss/total).backward()
        loss_sum += float(loss.detach()); prompt_tokens += receipt['prompt_tokens']
        processed_tokens += receipt['prompt_tokens']+receipt['target_tokens']
        receipts.append(dict(segment=seg, prompt_tokens=receipt['prompt_tokens'],
            target_tokens=receipt['target_tokens'], input_hash=receipt['processed_tensor_hashes']['input_ids']['sha256']))
        del batch, loss
    norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], HP['max_grad_norm'])
    if not torch.isfinite(norm): raise ValueError('NONFINITE_GRADIENT')
    optimizer.step(); scheduler.step(); optimizer.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    return dict(loss=loss_sum/total, gradient_norm=float(norm), supervised_tokens=total,
        prompt_tokens=prompt_tokens, processed_tokens=processed_tokens, forward_fragments=len(segments), receipts=receipts)


def initial_progress(schedule):
    return dict(step=0, sampler=schedule.state_dict(), supervised_tokens=0, prompt_tokens=0,
        processed_tokens=0, forward_fragments=0, exposures={}, measured_step_seconds_max=0.)


def advance(progress, schedule, segments, result, seconds):
    progress['step'] += 1; progress['sampler'] = schedule.state_dict()
    for field in ('supervised_tokens','prompt_tokens','processed_tokens','forward_fragments'):
        progress[field] += result[field]
    for seg in segments:
        if seg['begins_example']:
            key = seg['key']; progress['exposures'][key] = progress['exposures'].get(key,0)+1
    progress['measured_step_seconds_max'] = max(progress['measured_step_seconds_max'], seconds)


def allocation_end():
    # Never invent a short experiment cap. This is only the granted allocation end.
    info = subprocess.run(['scontrol','show','job','-o',os.environ['SLURM_JOB_ID']], capture_output=True, text=True, check=True).stdout
    end = next(v.split('=',1)[1] for v in info.split() if v.startswith('EndTime='))
    if end in ('Unknown','None','N/A'): raise ValueError('ALLOCATION_END_UNKNOWN')
    return datetime.datetime.fromisoformat(end).timestamp()


def main():
    compute()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--run-config', required=True, type=Path)
    parser.add_argument('--runtime-manifest', required=True, type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    config = read(args.run_config); runtime = read(args.runtime_manifest)
    if runtime['status'] != 'FROZEN_AND_VALIDATED': raise ValueError('UNVALIDATED_RUNTIME')
    for path, expected in runtime['code_hashes'].items():
        if sha(path) != expected: raise ValueError('FROZEN_CODE_CHANGED:' + path)
    if sha(args.run_config) != runtime['run_config_hashes'][str(args.run_config)]: raise ValueError('RUN_CONFIG_CHANGED')
    if sha(runtime['budget_plan']) != runtime['budget_plan_sha256']: raise ValueError('BUDGET_CHANGED')
    budget_plan = read(runtime['budget_plan']); budget = budget_plan['runs'][config['run_id']]
    if budget['method'] != config['method'] or budget['seed'] != config['seed']: raise ValueError('RUN_IDENTITY')
    meta = catalog()
    if sha(PREPARED/'catalog.jsonl') != budget_plan['catalog_sha256']: raise ValueError('CATALOG_CHANGED')
    fingerprint = digest([runtime, config, budget])
    output = Path(config['output_dir']); output.mkdir(parents=True, exist_ok=True)
    if (output/'TRAINING_COMPLETE.json').exists():
        done = read(output/'TRAINING_COMPLETE.json')
        if done['fingerprint'] != fingerprint: raise ValueError('COMPLETED_RUN_CONFIG_MISMATCH')
        print('ALREADY_COMPLETED', flush=True); return 0
    # Prevent accidental concurrent jobs writing one run. No cross-run locks.
    import fcntl
    lock = (output/'RUN.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    checkpoint_dir = Path(config['checkpoint_dir'])
    checkpoint = latest_checkpoint(checkpoint_dir, fingerprint)
    if checkpoint and not args.resume: raise ValueError('RESUME_REQUIRED')
    attempt = output/'attempts'/os.environ['SLURM_JOB_ID']
    if attempt.exists(): raise FileExistsError('ATTEMPT_ALREADY_EXISTS')
    attempt.mkdir(parents=True)
    import sys
    sys.path.insert(0, str(REPO/'scripts/full_multimodel_split_v5'))
    from gpu_health import check
    check(attempt)
    import torch
    import numpy as np
    from model_io_verified import load_engine
    random.seed(config['seed']); np.random.seed(config['seed'])
    model, processor, engine = load_engine(ROOT, config['seed'])
    optimizer, scheduler = make_optimizer(model, budget['optimizer_updates'])
    schedule = Schedule(meta, config['method'], config['seed'])
    progress = initial_progress(schedule)
    if checkpoint:
        progress = restore_checkpoint(checkpoint, model, optimizer, scheduler, fingerprint)
        schedule = Schedule(meta, config['method'], config['seed'], progress['sampler'])
    records = load_records(meta)
    model.train(); stopper = StopAtBoundary().install(); end_time = allocation_end()
    write(attempt/'START.json', dict(config=config, engine=engine, resumed_from=str(checkpoint) if checkpoint else None,
        start_step=progress['step'], allocation_end=end_time, fingerprint=fingerprint))
    last_save = time.monotonic(); last_saved_step = progress['step'] if checkpoint else -1
    with (attempt/'updates.jsonl').open('x') as log:
        while progress['step'] < budget['optimizer_updates']:
            reserve = max(1800., progress['measured_step_seconds_max']*2+600)
            if stopper.requested or end_time-time.time() < reserve:
                if last_saved_step != progress['step']:
                    checkpoint = save_checkpoint(checkpoint_dir, model, optimizer, scheduler, progress, fingerprint)
                if stopper.signal == signal.SIGTERM:
                    # Cancellation is not permission to resurrect a user's job.
                    write(attempt/'TERMINATED_NO_AUTORETRY.json', dict(checkpoint=str(checkpoint),
                        step=progress['step'], signal=stopper.signal, fingerprint=fingerprint))
                    return 143
                write(attempt/'CONTINUATION_REQUIRED.json', dict(checkpoint=str(checkpoint), step=progress['step'],
                    fingerprint=fingerprint, reason='SIGNAL_OR_ALLOCATION_END', signal=stopper.signal))
                return 75
            start = time.monotonic(); segments = schedule.segments(budget['tokens_per_update'])
            result = train_update(model, processor, optimizer, scheduler, records, meta, segments)
            seconds = time.monotonic()-start; advance(progress, schedule, segments, result, seconds)
            row = dict(step=progress['step'], seconds=seconds, lr=optimizer.param_groups[0]['lr'], **result)
            log.write(json.dumps(row)+'\n'); log.flush()
            atomic(output/'LIVE_STATUS.json', dict(step=progress['step'], total_updates=budget['optimizer_updates'],
                supervised_tokens=progress['supervised_tokens'], prompt_tokens=progress['prompt_tokens'],
                job_id=os.environ['SLURM_JOB_ID'], last_step_seconds=seconds, loss=result['loss']))
            print({k: row[k] for k in ('step','seconds','loss','supervised_tokens')}, flush=True)
            if time.monotonic()-last_save >= 900 or progress['step'] == budget['optimizer_updates']:
                checkpoint = save_checkpoint(checkpoint_dir, model, optimizer, scheduler, progress, fingerprint)
                last_saved_step = progress['step']; last_save = time.monotonic()
    if progress['supervised_tokens'] != budget['supervised_tokens'] or progress['sampler'] != budget['final_sampler_state']:
        raise ValueError('FINAL_BUDGET_OR_SAMPLER_MISMATCH')
    if digest(progress['exposures']) != budget['exposure_digest']: raise ValueError('FINAL_EXPOSURE_MISMATCH')
    write(output/'TRAINING_COMPLETE.json', dict(status='COMPLETE_FIXED_TRAINING_BUDGET', fingerprint=fingerprint,
        run_id=config['run_id'], final_checkpoint=str(checkpoint), final_adapter=str(checkpoint/'adapter'),
        progress=progress, held_out_test_run=False, primary_checkpoint_policy='FIXED_FINAL_BUDGET_NO_SEED_SELECTION'))
    return 0


if __name__ == '__main__': raise SystemExit(main())
