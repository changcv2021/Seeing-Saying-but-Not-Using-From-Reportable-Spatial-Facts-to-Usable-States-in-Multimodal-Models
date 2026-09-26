"""Inference has no B0/other-model/scorer dependency; scoring is a separate lane."""
import argparse
import datetime
import json
import math
import os
import subprocess
import time
from orchestration import (ROOT, RUN_ID, SEED, dispatch, frozen, load, registry,
                           sha, verify_extension, maybe_submit_judge, renew_controller, write)
from campaign import model_check

TERMINAL = {'COMPLETED','FAILED','CANCELLED','TIMEOUT','OUT_OF_MEMORY',
            'NODE_FAIL','PREEMPTED','BOOT_FAIL'}


def smoke_readiness(key, cfg):
    """Metadata/runtime audit only. Never score gold or require another model."""
    root = ROOT/key
    path = root/'smoke/predictions_000.jsonl'
    manifest_path = path.with_suffix('.manifest.json')
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    if manifest['status'] != 'COMPLETE' or manifest['count'] != 96 or manifest['output_sha256'] != sha(path):
        raise ValueError('SMOKE_MANIFEST_INCOMPLETE_OR_CHANGED')
    rows = load(path)
    expected = [r['sample_id'] for r in load(ROOT/'smoke.jsonl')]
    if [r['sample_id'] for r in rows] != expected or len(rows) != 96:
        raise ValueError('SMOKE_MEMBERSHIP_OR_ORDER_MISMATCH')
    for row in rows:
        if row.get('error'):
            raise ValueError('SMOKE_RUNTIME_ERROR_PRESERVED')
        if (row['model_id'],row['model_revision'],row['run_id'],row['config_sha256'],row['requested_samples_sha256']) != (
                cfg['model_id'],cfg['revision'],cfg['run_id'],sha(root/'config.json'),cfg['input_hashes']['smoke.jsonl']):
            raise ValueError('SMOKE_MODEL_INPUT_PROVENANCE_MISMATCH')
        if row.get('gold_access_attempts',0) or row.get('max_new_tokens') != 512 or row.get('generated_tokens',0)>512:
            raise ValueError('SMOKE_GOLD_OR_TOKEN_PROTOCOL_VIOLATION')
        if not math.isfinite(row['inference_seconds']) or row['inference_seconds'] <= 0:
            raise ValueError('INVALID_INFERENCE_TIMING')
    return dict(status='PASS_ENGINEERING_ONLY',n=96,runtime_errors=0,
                candidate_mean_seconds=sum(r['inference_seconds'] for r in rows)/96,
                prediction_sha256=sha(path),manifest_sha256=sha(manifest_path),
                common_scoring_gate_required=False,accuracy_is_not_gate=True,
                final_label_compliance_is_not_gate=True,model_answers_not_used_for_selection=True)


def direct32_readiness(cfg):
    root = ROOT/'qwen25vl_32b'
    waiver_path = root/'direct_full_v1/smoke_waiver.json'
    waiver = json.loads(waiver_path.read_text())
    if waiver['status'] != 'WAIVED_BY_USER_NOT_TESTED':
        raise ValueError('USER_32B_SMOKE_WAIVER_MISSING')
    available = model_check(cfg)
    download = json.loads((root/'download_manifest.json').read_text())
    if available['status'] != 'READY' or any(available[k] != download[k] for k in available):
        raise ValueError('32B_MODEL_NOT_READY')
    return dict(status='WAIVED_BY_USER_NOT_TESTED',model_key='qwen25vl_32b',
                waiver_sha256=sha(waiver_path),candidate_mean_seconds=None,
                common_scoring_gate_required=False,b0_dependency_required=False,
                historical_waiver_scheduling_fields_superseded_by_current_user_request=True)


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:
        raise ValueError('PROTOCOL_MISMATCH')
    if a.dry_run:
        print('Independently dispatch ready candidates; judges wait only for own predictions and scorer certification.')
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    verify_extension()
    models=registry();sub=json.loads((ROOT/'retry_v4_initial_submissions.json').read_text())
    start=time.monotonic()
    while time.monotonic()-start<23*3600:
        result=subprocess.run(['sacct','-n','-P','-X','-j',','.join(sub['smoke'].values()),
                               '--format=JobIDRaw,State,ExitCode'],capture_output=True,text=True,timeout=30)
        if result.returncode:
            write(ROOT/'controller_status_v4.json',dict(status='SLURM_UNREACHABLE_NO_SUBMISSION'))
            time.sleep(60);continue
        states={line.split('|')[0]:line.split('|')[1].split()[0] for line in result.stdout.splitlines() if '|' in line}
        gatepath=ROOT/'SCORING_GATE.json'
        gate=json.loads(gatepath.read_text()) if gatepath.exists() else {}
        pilot_state=states.get(sub['smoke']['qwen25vl_7b'],'UNKNOWN')
        scorer_failed=pilot_state in TERMINAL and pilot_state!='COMPLETED' and gate.get('status')!='PASS'
        judge_clock=ROOT/'qwen25vl_7b/smoke_judge/supervisor.json'
        timing=json.loads(judge_clock.read_text()) if judge_clock.exists() else {}
        judge_seconds=timing.get('elapsed_seconds') if timing.get('status')=='COMPLETE' else None
        statuses={}
        for key,cfg in models.items():
            root=ROOT/key
            if not cfg['enabled']:
                statuses[key]=dict(status='BLOCKED_MODEL_DISABLED',reason=cfg.get('blocked_reason'));continue
            blocker=root/'full_blocker_v4.json'
            if blocker.exists():
                statuses[key]=json.loads(blocker.read_text());continue
            try:
                submitted_path=root/'full_shard_submission_v4.json'
                if not submitted_path.exists():
                    ready=(direct32_readiness(cfg) if key=='qwen25vl_32b' else smoke_readiness(key,cfg))
                    if ready is None:
                        state=states.get(sub['smoke'][key],'UNKNOWN')
                        statuses[key]=dict(status='SMOKE_FAILED' if state in TERMINAL else 'OWN_SMOKE_WAIT',
                                           job=sub['smoke'][key],slurm_state=state)
                        continue
                    frozen(root/'inference_readiness_v4.json',ready)
                    submitted=dispatch(key,ready['candidate_mean_seconds'],judge_seconds)
                    frozen(submitted_path,submitted)
                    write(root/'active_full_submission.json',dict(version='split_v4',record=str(submitted_path),**submitted))
                    print(json.dumps(dict(model=key,submission=submitted)),flush=True)
                else:
                    submitted=json.loads(submitted_path.read_text())
                # Readiness of this lane cannot stop another candidate/model.
                if scorer_failed:
                    judge_status=dict(status='SCORER_BOOTSTRAP_FAILED_CANDIDATE_UNAFFECTED',job=sub['smoke']['qwen25vl_7b'])
                else:
                    judge_status=maybe_submit_judge(key)
                statuses[key]=dict(status=judge_status['status'],candidate=submitted,scoring=judge_status)
            except Exception as exc:
                failure=dict(status='BLOCKED_REQUIRES_ENGINEERING_REVIEW',error=type(exc).__name__+': '+str(exc))
                frozen(blocker,failure);statuses[key]=failure
        write(ROOT/'controller_status_v4.json',dict(status='MONITORING',models=statuses,
              checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              inference_cross_model_dependencies=[],b0_dependency=False,
              scoring_gate_affects_inference=False,scorer_state=gate.get('status','NOT_COMPLETED'),
              answer_based_retries=0,time_based_continuations_allowed=True))
        done={'BLOCKED_MODEL_DISABLED','SMOKE_FAILED','BLOCKED_REQUIRES_ENGINEERING_REVIEW',
              'JUDGE_SUBMITTED','SCORER_BOOTSTRAP_FAILED_CANDIDATE_UNAFFECTED',
              'SCORING_BLOCKED_CANDIDATE_UNAFFECTED'}
        if all(item['status'] in done for item in statuses.values()):
            write(ROOT/'controller_completion_v4.json',dict(status='LANES_DISPATCHED_OR_EXPLICITLY_BLOCKED',
                  models=statuses,experiment_complete=False))
            return
        time.sleep(60)
    continuation=renew_controller()
    write(ROOT/'controller_status_v4.json',dict(status='CONTINUING_IN_NEXT_CPU_ALLOCATION',**continuation))


if __name__=='__main__':
    main()
