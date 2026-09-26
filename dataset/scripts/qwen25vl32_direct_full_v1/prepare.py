"""Prepare an explicitly authorized direct full run; never fabricate smoke PASS."""
import argparse
import collections
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPLIT = HERE.parent / 'full_multimodel_split_v2'
sys.path.insert(0, str(SPLIT))
from orchestration import (ROOT, RUN_ID, SEED, array_command, cpu_command,
                           frozen, load, read_cluster_limits, registry, sha,
                           verify_extension, write)
from campaign import model_check

KEY = 'qwen25vl_32b'
MODEL_ROOT = ROOT / KEY
DECISION = MODEL_ROOT / 'direct_full_v1'
B0_JOB = '8173736'
GATE_JOB = '8174239'
OLD_SMOKE = '8174240'


def plan_for(limits):
    if limits['max_array_tasks'] < 8 or limits['gpu_wall_hours'] < 1:
        raise ValueError('UNSUPPORTED_SITE_LIMITS')
    wall = limits['gpu_wall_hours']
    def stage(shards, gpus, memory, concurrency):
        return dict(shards=shards, gpus=gpus, cpus=4*gpus,
                    memory_gib=memory, concurrency=concurrency, wall_hours=wall,
                    estimated_hours=None, timed_continuation_supported=True,
                    estimated_continuation_needed=None)
    return dict(candidate=stage(8, 2, 128, 2), judge=stage(4, 1, 32, 4),
                candidate_mean_seconds=None, judge_smoke_seconds=None,
                timing_measurement_status='NOT_MEASURED_32B_SMOKE_WAIVED_BY_USER',
                shard_count_basis='FIXED_INDEX_PARTITION_BEFORE_ANY_MODEL_OUTPUT',
                input_count=24196, partition='gpu', account='YOUR_ACCOUNT', qos='allocated',
                shard_rule='request_index modulo num_shards', independent_nodes=True,
                max_concurrent_gpus_per_model=4, answer_based_retries=0,
                cumulative_gpu_hour_cap=None, artificial_shard_cap=None,
                maximum_reserved_gpu_hours=(8*2+4)*wall, cluster_limits=limits,
                time_limit_continuation='Only unfinished requests; completed outputs immutable.')


def candidate_command(plan):
    command = array_command(KEY, 'candidate', plan)
    command.insert(-3, '--dependency=afterany:'+B0_JOB+',afterok:'+GATE_JOB)
    return command


def engineering_checks(plan, command):
    parts = [list(range(i, 24196, 8)) for i in range(8)]
    assert sorted(v for part in parts for v in part) == list(range(24196))
    assert collections.Counter(map(len, parts)) == {3025: 4, 3024: 4}
    assert '--array=0-7%2' in command and '--gpus-per-node=2' in command
    assert '--nodes=1' in command and not any(c.startswith('--nodelist=') for c in command)
    assert '--dependency=afterany:8173736,afterok:8174239' in command
    assert command[-3:] == [str(SPLIT/'job.sh'), 'candidate', KEY]
    assert not any('8174240' in c for c in command)
    assert plan['candidate_mean_seconds'] is None and plan['cumulative_gpu_hour_cap'] is None
    assert '--signal=B:USR1@600' in command and '--no-requeue' in command
    # A skipped per-model smoke must not be represented as a passed interface test.
    assert not (MODEL_ROOT/'interface_gate.json').exists()
    return dict(status='PASS', checks=10, model_calls=0, scientific_code_modified=False)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--limit', type=int)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    a = p.parse_args()
    if a.run_id != RUN_ID or a.seed != SEED or a.limit is not None:
        raise ValueError('PROTOCOL_MISMATCH')
    if a.dry_run:
        print('CPU integrity checks only, then prepare 8 full-data shards; no model smoke or submission.')
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    verify_extension()
    models = registry()
    model = models[KEY]
    assert model['gpus'] == 2 and model['replicas'] == 2
    available = model_check(model)
    download = json.loads((MODEL_ROOT/'download_manifest.json').read_text())
    if available['status'] != 'READY' or any(available[k] != download[k] for k in available):
        raise ValueError('MODEL_DOWNLOAD_MANIFEST_MISMATCH')
    if (download['model_id'], download['revision']) != (model['model_id'], model['revision']):
        raise ValueError('MODEL_REVISION_MISMATCH')
    requests = load(ROOT/'requests.jsonl')
    if len(requests) != 24196 or len({r['sample_id'] for r in requests}) != 24196:
        raise ValueError('INCOMPLETE_OR_DUPLICATED_INPUTS')
    preflight = json.loads((ROOT/'preflight.json').read_text())
    if preflight['status'] != 'PASS' or preflight['inputs'] != len(requests):
        raise ValueError('PREPARATION_NOT_PASSED')
    if any((MODEL_ROOT/'full').glob('predictions_*.jsonl')):
        raise ValueError('PRESERVE_EXISTING_PREDICTIONS_RECONCILE_BEFORE_DIRECT_SUBMISSION')
    state = subprocess.run(['sacct', '-n', '-X', '-j', OLD_SMOKE, '--format=State', '-P'],
                           check=True, capture_output=True, text=True, timeout=30).stdout.strip()
    if not state.startswith('CANCELLED'):
        raise ValueError('OLD_SMOKE_NOT_CANCELLED')
    plan = plan_for(read_cluster_limits())
    command = candidate_command(plan)
    tests = engineering_checks(plan, command)
    frozen(MODEL_ROOT/'full_split_budget.json', plan)
    frozen(DECISION/'smoke_waiver.json', dict(
        status='WAIVED_BY_USER_NOT_TESTED', cancelled_smoke_job=OLD_SMOKE,
        authorization='2026-09-08 user explicitly cancelled 32B smoke and requested full evaluation.',
        administrator_contact='USER_REPORT_ADMINISTRATOR_WILL_HELP; NOT_INDEPENDENTLY_CONFIRMED',
        no_hold_release_or_priority_changes=True, no_resubmit_on_administrative_hold=True,
        common_7b_gate_preserved=True, b0_priority_preserved=True,
        gpu_fit_and_32b_runtime_not_yet_tested=True,
        model_id=model['model_id'], revision=model['revision'],
        input_count=24196, input_hashes=model['input_hashes'],
        max_new_tokens=512, scoring_policy=model['scoring_policy'],
        original_code_and_gold_read_only=True))
    frozen(DECISION/'prepared_submission.json', dict(candidate_command=command,
        handoff_command_template=cpu_command(KEY, 'handoff', 'CANDIDATE_ARRAY_ID'),
        plan=plan, availability=available, tests=tests,
        preparation_job=os.environ['SLURM_JOB_ID'], seed=SEED,
        source_revision_kind='SHA256_LOCK_NOT_GIT_COMMIT',
        files={str(f):sha(f) for f in [HERE/'prepare.py', HERE/'job.sh']},
        scientific_protocol_sha256=sha(ROOT/'protocol_lock.json'),
        split_scheduling_sha256=sha(ROOT/'split_scheduling_v2_lock.json')))
    print(json.dumps(dict(status='READY_FOR_DIRECT_FULL_SUBMISSION', tests=tests,
                          command=shlex.join(command), inputs=len(requests)), ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        if os.environ.get('SLURM_JOB_ID'):
            write(DECISION/('prepare_failure_'+os.environ['SLURM_JOB_ID']+'.json'),
                  dict(status='BLOCKED_NOT_SUBMITTED', error=type(exc).__name__+': '+str(exc)))
        raise
