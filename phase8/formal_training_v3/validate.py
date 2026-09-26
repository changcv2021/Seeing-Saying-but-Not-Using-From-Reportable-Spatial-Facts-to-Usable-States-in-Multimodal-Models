"""Actual fresh-process 9B continuation comparison, all-arm ingress, no test."""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from paths import *
from core import METHODS, Schedule, digest
from checkpoint import save_checkpoint, restore_checkpoint, StopAtBoundary
from determinism import configure
from trainer import make_optimizer, train_update, initial_progress, advance

VALIDATION = OUTPUT/'runtime_validation_v2'
SEED = 20260922
UPDATES = 4
TOKENS = 64


def subset(all_meta):
    chosen = set()
    for level in ('L1','L2','L3','L4'):
        answers = [k for k,r in all_meta.items() if r['pool']=='answer' and r['level']==level]
        k = min(answers, key=lambda x: digest(['formal_runtime_smoke',x]))
        chosen.add(k); chosen.add('cot:'+all_meta[k]['sample_id'])
        states = [k for k,r in all_meta.items() if r['pool']=='state' and r['level']==level]
        chosen.add(min(states, key=lambda x: digest(['formal_runtime_smoke',x])))
    for criterion in ('fallback','S2','max_media'):
        candidates = [k for k,r in all_meta.items() if
            ((criterion=='fallback' and r['pool']=='cot' and r.get('rationale_available') is False) or
             (criterion=='S2' and r['pool']=='state' and r['stage']=='S2') or
             (criterion=='max_media' and r['pool']=='answer'))]
        key = (max(candidates, key=lambda k:(all_meta[k]['media_count'],digest(k))) if criterion=='max_media'
               else min(candidates,key=lambda k:digest([criterion,k])))
        chosen.add(key)
        if all_meta[key]['pool']=='cot': chosen.add('answer:'+all_meta[key]['sample_id'])
        if all_meta[key]['pool']=='answer': chosen.add('cot:'+all_meta[key]['sample_id'])
    return {k: all_meta[k] for k in sorted(chosen)}


def worker(mode):
    compute()
    deterministic_receipt = configure()
    import torch
    import numpy as np
    import random
    from model_io_verified import load_engine
    frozen = read(VALIDATION/'FROZEN.json')
    for path, expected in frozen['code_hashes'].items():
        if sha(path) != expected: raise ValueError('VALIDATION_CODE_CHANGED')
    metadata = {r['key']:r for r in rows(VALIDATION/'catalog.jsonl')}
    records = load_records(metadata)
    random.seed(SEED); np.random.seed(SEED)
    model, processor, engine = load_engine(ROOT, SEED)
    optimizer, scheduler = make_optimizer(model, UPDATES)
    schedule = Schedule(metadata, 'pss_full', SEED); progress = initial_progress(schedule)
    dest = VALIDATION/mode; dest.mkdir()
    write(dest/'DETERMINISM.json', deterministic_receipt)
    fingerprint = frozen['fingerprint']
    if mode=='resumed':
        progress = restore_checkpoint(VALIDATION/'continuous/checkpoints/step_0000002',
            model, optimizer, scheduler, fingerprint)
        schedule = Schedule(metadata, 'pss_full', SEED, progress['sampler'])
    model.train(); stopper = StopAtBoundary().install(); trace = []
    if mode=='interfaces':
        zero = save_checkpoint(dest/'checkpoints', model, optimizer, scheduler, progress, fingerprint)
        for method in METHODS:
            restore_checkpoint(zero, model, optimizer, scheduler, fingerprint)
            method_schedule = Schedule(metadata, method, SEED)
            segments = method_schedule.segments(TOKENS)
            result = train_update(model, processor, optimizer, scheduler, records, metadata, segments)
            trace.append(dict(method=method, **result))
        # Exercise approved answer-only fallback and actual S2 target explicitly,
        # independent of which events fit the tiny generic scheduling panel.
        for name, keys in (
            ('cot_answer_only_fallback', [k for k,r in metadata.items() if r['pool']=='cot' and r.get('rationale_available') is False]),
            ('S2_state', [k for k,r in metadata.items() if r['pool']=='state' and r['stage']=='S2']),
            ('max_media_answer', [max((k for k,r in metadata.items() if r['pool']=='answer'),key=lambda k:metadata[k]['media_count'])])):
            restore_checkpoint(zero, model, optimizer, scheduler, fingerprint)
            k = sorted(keys)[0]; n = metadata[k]['target_tokens']
            result = train_update(model, processor, optimizer, scheduler, records, metadata,
                [dict(key=k, offset=0, count=n, target_tokens=n, begins_example=True)])
            trace.append(dict(method=name, **result))
        write(dest/'TRACE.json', trace); return
    target = 2 if mode=='interrupted' else UPDATES
    while progress['step'] < target:
        start = time.monotonic(); segments = schedule.segments(TOKENS)
        result = train_update(model, processor, optimizer, scheduler, records, metadata, segments)
        advance(progress, schedule, segments, result, time.monotonic()-start)
        trace.append(dict(step=progress['step'], **result))
        if progress['step']==2:
            if mode=='interrupted':
                os.kill(os.getpid(), signal.SIGUSR1)
                if not stopper.requested: raise ValueError('USR1_NOT_HANDLED')
            save_checkpoint(dest/'checkpoints', model, optimizer, scheduler, progress, fingerprint)
    if target!=2:
        save_checkpoint(dest/'checkpoints', model, optimizer, scheduler, progress, fingerprint)
    write(dest/'TRACE.json', trace)
    write(dest/'END.json', dict(step=progress['step'], signal_handled=stopper.requested,
        peak_allocated_bytes=torch.cuda.max_memory_allocated(), pending_target=progress['sampler']['pending']))


def compare(a, b, path='root'):
    import torch
    import numpy as np
    if isinstance(a, torch.Tensor):
        if a.shape!=b.shape or a.dtype!=b.dtype: raise ValueError('RESTORE_TENSOR_SHAPE:'+path)
        exact = torch.equal(a,b)
        if a.is_floating_point():
            if not torch.allclose(a,b,rtol=1e-5,atol=1e-6): raise ValueError('RESTORE_TENSOR_VALUE:'+path)
            delta = float((a-b).abs().max()) if a.numel() else 0.
        else:
            if not exact: raise ValueError('RESTORE_INTEGER_OR_RNG:'+path)
            delta = 0.
        return dict(tensors=1, exact_tensors=int(exact), max_abs_diff=delta)
    if isinstance(a, np.ndarray):
        if not np.array_equal(a,b): raise ValueError('RESTORE_NUMPY:'+path)
        return dict(tensors=0,exact_tensors=0,max_abs_diff=0.)
    if isinstance(a, dict):
        if set(a)!=set(b): raise ValueError('RESTORE_KEYS:'+path)
        children = [compare(a[k],b[k],path+'.'+str(k)) for k in a]
    elif isinstance(a, (tuple,list)):
        if len(a)!=len(b): raise ValueError('RESTORE_LENGTH:'+path)
        children = [compare(x,y,path+'.'+str(i)) for i,(x,y) in enumerate(zip(a,b))]
    else:
        if a!=b: raise ValueError('RESTORE_SCALAR:'+path)
        children = []
    return dict(tensors=sum(c['tensors'] for c in children),
        exact_tensors=sum(c['exact_tensors'] for c in children),
        max_abs_diff=max([c['max_abs_diff'] for c in children],default=0.))


def main():
    compute()
    if VALIDATION.exists(): raise FileExistsError('PRESERVE_VALIDATION_HISTORY')
    VALIDATION.mkdir(parents=True)
    sys.path.insert(0,str(REPO/'scripts/full_multimodel_split_v5'))
    from gpu_health import check
    check(VALIDATION)
    meta = subset(catalog()); write(VALIDATION/'catalog.jsonl',list(meta.values()),True)
    hashes = {str(p):sha(p) for p in HERE.glob('*.py')}
    for name in ('model_io.py','model_io_verified.py','state_schema.py','state_interface_v2.py','common.py'):
        hashes[str(ENGINE_CODE/name)] = sha(ENGINE_CODE/name)
    frozen = dict(seed=SEED, optimizer_updates=UPDATES, target_tokens_per_update=TOKENS,
        method='pss_full', code_hashes=hashes, sample_ids=sorted(meta),
        tolerances=dict(atol=1e-6,rtol=1e-5), no_accuracy_gate=True, test_opened=False,
        budget_sha256=sha(PREPARED/'BUDGET_PLAN.json'), catalog_sha256=sha(VALIDATION/'catalog.jsonl'))
    frozen['fingerprint']=digest(frozen); write(VALIDATION/'FROZEN.json',frozen)
    for mode in ('continuous','interrupted','resumed','interfaces'):
        with (VALIDATION/(mode+'.out')).open('x') as log:
            subprocess.run([PYTHON,str(Path(__file__).resolve()),'--worker',mode],stdout=log,stderr=subprocess.STDOUT,check=True)
    import torch
    from safetensors.torch import load_file
    a = VALIDATION/'continuous/checkpoints/step_0000004'
    b = VALIDATION/'resumed/checkpoints/step_0000004'
    independent_prefix = compare(
        load_file(VALIDATION/'continuous/checkpoints/step_0000002/adapter/adapter_model.safetensors'),
        load_file(VALIDATION/'interrupted/checkpoints/step_0000002/adapter/adapter_model.safetensors'))
    weights = compare(load_file(a/'adapter/adapter_model.safetensors'),load_file(b/'adapter/adapter_model.safetensors'))
    sa = torch.load(a/'training_state.pt',map_location='cpu',weights_only=False)
    sb = torch.load(b/'training_state.pt',map_location='cpu',weights_only=False)
    sa['progress'].pop('measured_step_seconds_max');sb['progress'].pop('measured_step_seconds_max')
    training = compare(sa,sb)
    loss_a = read(VALIDATION/'continuous/TRACE.json')[2:]
    loss_b = read(VALIDATION/'resumed/TRACE.json')
    loss_delta = max(abs(a['loss']-b['loss']) for a,b in zip(loss_a,loss_b))
    if loss_delta > 1e-5: raise ValueError('RESUME_LOSS_MISMATCH')
    for a,b in zip(loss_a,loss_b):
        if a['receipts'] != b['receipts']: raise ValueError('RESUME_INPUTS_DIFFER')
    interfaces = read(VALIDATION/'interfaces/TRACE.json')
    if {x['method'] for x in interfaces} != set(METHODS)|{'cot_answer_only_fallback','S2_state','max_media_answer'}:
        raise ValueError('METHOD_INTERFACE_INCOMPLETE')
    result = dict(status='PASS_FULL_RESUME_AND_ALL_METHOD_INGRESS',job_id=os.environ['SLURM_JOB_ID'],
        weights=weights,independent_prefix_weights=independent_prefix,
        training_state=training,resumed_loss_max_abs_diff=loss_delta,
        fresh_process_restore=True,signal_usr1_verified=True,
        resume_source='Same step-2 checkpoint produced by continuous branch; separate interrupted branch verifies SIGUSR1.',
        deterministic_backend=read(VALIDATION/'continuous/DETERMINISM.json'),optimizer_scheduler_rng_sampler_verified=True,
        method_ingress=[x['method'] for x in interfaces],code_hashes=hashes,
        budget_sha256=frozen['budget_sha256'],formal_training_started=False,test_opened=False,
        equivalence_scope='Four 64-target-token engineering updates; same assigned GPU; not a full-corpus stability guarantee.')
    write(VALIDATION/'ACCEPTANCE.json',result);print(result,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--worker',choices=['continuous','interrupted','resumed','interfaces'])
    args=parser.parse_args()
    if args.worker: worker(args.worker)
    else: main()
