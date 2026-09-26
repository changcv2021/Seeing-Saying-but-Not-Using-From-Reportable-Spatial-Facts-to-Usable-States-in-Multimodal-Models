"""Small, read-only historical response audit and one frozen three-query rerun.

prepare: lightweight, three historical responses and 72 dev records; no model.
gpu: existing adapter, same three preselected dev IDs, one greedy generation each.
"""
import argparse
import datetime
import sys
import unittest

from common import ROOT, REPO, read, rows, sha, write, compute
from state_schema import parse_state
from state_interface_v2 import VERSION, state_prompt_v2, score_state_response
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_NAME = 'state_interface_repair_v2'


def prepare(root):
    old = root/'auxiliary_smoke_v3_independent'
    out = root/OUT_NAME
    if out.exists():
        raise FileExistsError('PRESERVE_EXISTING_REPAIR_RESULTS:' + str(out))
    suite = unittest.TestSuite()
    for module in ('test_state_schema', 'test_state_interface_v2'):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise ValueError('REGRESSION_TESTS_FAILED')
    source = root/'trajectory_aux_v1/dev/state.jsonl'
    dev = {r['sample_id']: r for r in rows(source)}
    predictions = []; requests = []; golds = []; hashes = {str(source): sha(source)}
    for stage in ('S0', 'S1', 'S2'):
        old_path = old/(stage+'_dev_raw.json')
        previous = read(old_path); row = dev[previous['sample_id']]
        if row['stage'] != stage or previous['gold'] != row['state']:
            raise ValueError('FROZEN_DEV_ID_OR_GOLD_CHANGED')
        hashes[str(old_path)] = sha(old_path)
        score = score_state_response(previous['raw_response'], previous['gold'])
        predictions.append(dict(sample_id=row['sample_id'], stage=stage,
            original_response_path=str(old_path), original_response_sha256=sha(old_path),
            raw_response=previous['raw_response'], gold=previous['gold'],
            old_parsed=previous['parsed'], old_parse_error=previous['parse_error'],
            old_exact_match=previous['exact_match_descriptive_only'], **score))
        # public request is frozen separately from private state/target.
        requests.append(dict(sample_id=row['sample_id'], stage=stage,
            public_request=row['request'], public_task_prompt=row['task_prompt'],
            actual_task_prompt=state_prompt_v2(row['task_prompt'])))
        golds.append(dict(sample_id=row['sample_id'], state=row['state'], target=row['target']))
    for name in ('repair_state_interface_v2.py', 'state_interface_v2.py', 'common.py',
                 'gpu_state_interface_v2_job.sh',
                 'state_schema.py', 'model_io.py', 'model_io_verified.py',
                 'test_state_schema.py', 'test_state_interface_v2.py'):
        hashes[str(HERE/name)] = sha(HERE/name)
    adapter = old/'engineering_adapter'
    for name in ('adapter_config.json', 'adapter_model.safetensors'):
        hashes[str(adapter/name)] = sha(adapter/name)
    manifest_path = root/'prepared_data_v2/MANIFEST.json'
    hashes[str(manifest_path)] = sha(manifest_path)
    summary = dict(status='PASS_LOCAL_INTERFACE_REGRESSION', parser_version=VERSION,
        regression_tests=result.testsRun, historical_responses=len(predictions),
        old_parse_valid=sum(p['old_parsed'] is not None for p in predictions),
        new_parse_valid=sum(p['parse_valid'] for p in predictions),
        old_exact_match=sum(p['old_exact_match'] for p in predictions),
        new_exact_match=sum(p['exact_match'] for p in predictions),
        no_model_calls=True, original_files_unchanged=True, test_opened=False,
        scope='THREE_FIXED_DEV_ENGINEERING_RESPONSES_NOT_METHOD_RESULTS')
    write(out/'historical_rescore.jsonl', predictions, True)
    write(out/'frozen_public_requests.jsonl', requests, True)
    write(out/'private_gold.jsonl', golds, True)
    for name in ('historical_rescore.jsonl', 'frozen_public_requests.jsonl', 'private_gold.jsonl'):
        hashes[str(out/name)] = sha(out/name)
    write(out/'LOCAL_ACCEPTANCE.json', summary)
    freeze = dict(version=VERSION, frozen_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        adapter=str(adapter), input_hashes=hashes,
        samples=[dict(sample_id=r['sample_id'], stage=r['stage']) for r in requests],
        policy='SAME_ENTIRE_THREE_QUERY_DEV_SMOKE_PANEL; SINGLE_PASS_NO_RESULT_BASED_RETRY',
        decode=dict(do_sample=False, enable_thinking=False, max_new_tokens=512),
        seed=20260922, training_updates=0, formal_test_opened=False,
        prompt_only_representation_clarification=True,
        targets_and_gold_unchanged=True,
        gpu_output_dir=str(out/'gpu_validation'))
    write(out/'FROZEN_VALIDATION.json', freeze)
    print(summary, flush=True)


def gpu(root):
    compute()
    import os
    import time
    import torch
    from model_io_verified import load_engine, loss_for
    from state_interface_v2 import encode_state_v2
    out = root/OUT_NAME
    freeze = read(out/'FROZEN_VALIDATION.json')
    for path, expected in freeze['input_hashes'].items():
        if sha(path) != expected:
            raise ValueError('FROZEN_INPUT_CHANGED:' + path)
    dest = Path(freeze['gpu_output_dir'])
    if dest.exists():
        raise FileExistsError('NO_AUTOMATIC_REPEAT:' + str(dest))
    dest.mkdir()
    sys.path.insert(0, str(REPO/'scripts/full_multimodel_split_v5'))
    from gpu_health import check
    check(dest)
    # Check the new public-prompt transform and unchanged target against ALL
    # existing train/dev state rows, but never test. This scan runs in Slurm.
    manifest = read(root/'prepared_data_v2/MANIFEST.json')
    corpus_receipts = []
    for path_string, expected in manifest['input_hashes'].items():
        path = Path(path_string)
        if path.name != 'state.jsonl':
            continue
        if sha(path) != expected:
            raise ValueError('PREPARED_STATE_DATA_CHANGED:' + path_string)
        count = 0
        for row in rows(path):
            if parse_state(row['target']) != row['state']:
                raise ValueError('LEGACY_TARGET_ROUNDTRIP_FAILED')
            new_prompt = state_prompt_v2(row['task_prompt'])
            context = row['request'].get('media_context', '')
            if context and not new_prompt.startswith(context+'\n'):
                raise ValueError('PUBLIC_MEDIA_CONTEXT_DROPPED')
            count += 1
        corpus_receipts.append(dict(path=path_string, sha256=expected, rows=count))
    if len(corpus_receipts) != 4:
        raise ValueError('EXPECTED_FOUR_TRAIN_DEV_STATE_SOURCES')
    write(dest/'INPUT_COMPATIBILITY.json', dict(status='PASS', sources=corpus_receipts,
        rows=sum(r['rows'] for r in corpus_receipts), targets_changed=0,
        test_opened=False, actual_processor_probe_is_only_three_fixed_dev_rows=True))
    requests = list(rows(out/'frozen_public_requests.jsonl'))
    golds = {r['sample_id']: r for r in rows(out/'private_gold.jsonl')}
    model, processor, engine = load_engine(root, freeze['seed'], adapter=freeze['adapter'])
    model.eval(); model.gradient_checkpointing_disable(); model.requires_grad_(False)
    write(dest/'ENGINE.json', dict(engine, job_id=os.environ['SLURM_JOB_ID'],
        adapter=freeze['adapter'], seed=freeze['seed'], updates=0))
    predictions = []
    for public in requests:
        sample_id = public['sample_id']; start = time.monotonic()
        # No private state/gold is passed to this generation input builder.
        batch, receipt = encode_state_v2(processor, public['public_request'],
            task_prompt=public['public_task_prompt'])
        if receipt['actual_task_prompt'] != public['actual_task_prompt']:
            raise ValueError('PROMPT_CHANGED_AFTER_FREEZE')
        torch.cuda.reset_peak_memory_stats()
        with torch.inference_mode():
            output = model.generate(**batch.to(model.device), max_new_tokens=512,
                                    do_sample=False, use_cache=True)
        ids = output[0, receipt['prompt_tokens']:receipt['prompt_tokens']+512].tolist()
        raw = processor.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        gold = golds[sample_id]
        score = score_state_response(raw, gold['state'])
        pred = dict(sample_id=sample_id, stage=public['stage'], raw_response=raw,
            token_ids=ids, generated_tokens=len(ids), retained_prefix_scored=True,
            reached_token_budget=len(ids) == 512, **score,
            exact_match_scope='DEV_ENGINEERING_DESCRIPTIVE_ONLY',
            seconds=time.monotonic()-start, peak_allocated_bytes=torch.cuda.max_memory_allocated())
        write(dest/(public['stage']+'_raw.json'), pred)
        write(dest/(public['stage']+'_generation_receipt.json'), receipt)
        # Same shared wrapper for teacher forcing: prove gold is only appended
        # as supervision, and never changes the public generation prompt.
        teacher, teacher_receipt = encode_state_v2(processor, public['public_request'],
            task_prompt=public['public_task_prompt'], target=gold['target'], end_turn=True)
        if teacher_receipt['prompt_tokens'] != receipt['prompt_tokens'] or not torch.equal(
                teacher['input_ids'][:, :receipt['prompt_tokens']].cpu(), batch['input_ids'].cpu()):
            raise ValueError('TRAIN_DEV_PROMPT_PREFIX_MISMATCH')
        with torch.inference_mode():
            loss = loss_for(model, teacher, teacher_receipt)
        if not torch.isfinite(loss):
            raise ValueError('NONFINITE_TEACHER_FORCED_LOSS')
        write(dest/(public['stage']+'_teacher_receipt.json'), dict(teacher_receipt,
            teacher_forced_loss=float(loss), generation_prefix_equal=True, optimizer_updates=0))
        predictions.append(pred)
        print({k: pred[k] for k in ('stage', 'parse_valid', 'exact_match', 'generated_tokens')}, flush=True)
        del batch, output, teacher, loss
    # Protect old adapter/raw data as well as the new frozen request packet.
    for path, expected in freeze['input_hashes'].items():
        if sha(path) != expected:
            raise ValueError('SOURCE_CHANGED_DURING_VALIDATION:' + path)
    valid = sum(p['parse_valid'] for p in predictions)
    summary = dict(status='PASS_STATE_INTERFACE_DEV_SMOKE' if valid == len(predictions)
        else 'COMPLETED_WITH_INVALID_STATE_OUTPUTS', job_id=os.environ['SLURM_JOB_ID'],
        parser_version=VERSION, n=len(predictions), parse_valid=valid,
        legacy_strict_valid=sum(p.get('legacy_strict_valid', False) for p in predictions),
        exact_match_descriptive_only=sum(p['exact_match'] for p in predictions),
        old_files_unchanged=True, teacher_generation_prefix_equal=True,
        training_updates=0, formal_training_started=False, formal_test_started=False,
        all_raw_and_invalid_retained=True, fixed_single_pass=True,
        peak_allocated_bytes=max(p['peak_allocated_bytes'] for p in predictions))
    write(dest/'ACCEPTANCE.json', summary); print(summary, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode', choices=['prepare', 'gpu'])
    parser.add_argument('--run-root', type=Path, default=ROOT)
    args = parser.parse_args()
    (prepare if args.mode == 'prepare' else gpu)(args.run_root)
