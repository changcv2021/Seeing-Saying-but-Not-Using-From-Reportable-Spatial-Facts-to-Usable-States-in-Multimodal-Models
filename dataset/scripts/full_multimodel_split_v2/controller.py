"""Renewable CPU scheduler: site limits only, no answer-based candidate retries."""
import argparse, datetime, json, math, os, subprocess, time
from pathlib import Path
from types import SimpleNamespace
from orchestration import verify_extension, dispatch as dispatch_split, renew_controller
from campaign import ROOT,CODE,RUN_ID,SEED,registry,verify,frozen,score,write,load

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('CONTROLLER_PROTOCOL_MISMATCH')
    if a.dry_run:print('Monitor frozen smoke gates; independently submit disjoint per-GPU shard arrays.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    start=time.monotonic();models=registry();sub=json.loads((ROOT/'initial_submissions.json').read_text());verify_extension()
    terminal={'COMPLETED','FAILED','CANCELLED','TIMEOUT','OUT_OF_MEMORY','NODE_FAIL','PREEMPTED','BOOT_FAIL'}
    while time.monotonic()-start<23*3600:
        ids=list(sub['smoke'].values())+[sub['download32']]
        query=['sacct','-n','-P','-X','-j',','.join(ids),'--format=JobIDRaw,State,ExitCode']
        r=subprocess.run(query,capture_output=True,text=True,timeout=30)
        if r.returncode:
            write(ROOT/'controller_status.json',dict(status='SLURM_UNREACHABLE_NO_SUBMISSION',checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat()));time.sleep(60);continue
        states={line.split('|')[0]:line.split('|')[1].split()[0] for line in r.stdout.splitlines() if '|' in line}
        gate_path=ROOT/'SCORING_GATE.json';gate=json.loads(gate_path.read_text()) if gate_path.exists() else {}
        pilot_state=states.get(sub['smoke']['qwen25vl_7b'],'UNKNOWN')
        if pilot_state in terminal and pilot_state!='COMPLETED' and gate.get('status')!='PASS':
            write(ROOT/'controller_completion.json',dict(status='STOPPED_7B_SMOKE_FAILED',slurm_state=pilot_state,experiment_complete=False));return
        statuses={}
        for key,m in models.items():
            if not m['enabled']:
                statuses[key]=dict(status='BLOCKED',reason=m.get('blocked_reason'));continue
            root=ROOT/key;full_submission=root/'full_shard_submission.json'
            if full_submission.exists():
                statuses[key]=dict(status='FULL_SHARD_ARRAY_SUBMITTED',**json.loads(full_submission.read_text()));continue
            sid=sub['smoke'][key];state=states.get(sid,'UNKNOWN')
            if state!='COMPLETED':
                statuses[key]=dict(status='SMOKE_FAILED' if state in terminal else 'SMOKE_WAIT',job=sid,slurm_state=state);continue
            if gate.get('status')!='PASS':
                statuses[key]=dict(status='WAITING_FOR_7B_SCORING_GATE',gate=gate.get('status','NOT_COMPLETED'));continue
            if (root/'full_blocker.json').exists():statuses[key]=json.loads((root/'full_blocker.json').read_text());continue
            try:
                verify()
                if key!='qwen25vl_7b' and not (root/'interface_gate.json').exists():
                    # The common parser was calibrated on 7B, not selected on
                    # another model's accuracy or final-answer compliance rate.
                    score(SimpleNamespace(model=key),'smoke',False)
                    observed=load(root/'smoke/predictions_000.jsonl')
                    expected={r['sample_id'] for r in load(ROOT/'smoke.jsonl')}
                    if len(observed)!=96 or {r['sample_id'] for r in observed}!=expected or any(r.get('error') for r in observed):
                        raise ValueError('MODEL_SMOKE_RUNTIME_OR_COMPLETENESS_FAILURE')
                    from output_policy import parse_prediction
                    missing_labels=sum(parse_prediction(r)['label'] is None for r in observed)
                    frozen(root/'interface_gate.json',dict(status='PASS',basis='ENGINEERING_ONLY_AFTER_COMMON_7B_PARSER_CERTIFICATION',
                        n=96,runtime_errors=0,missing_final_labels=missing_labels,accuracy_is_not_gate=True,
                        compliance_rate_is_not_gate=True,policy='Score emitted final fields under 512; missing labels stay in denominator; no answer-based retry.'))
                ig=json.loads((root/'interface_gate.json').read_text())
                if ig['status']!='PASS':raise ValueError('MODEL_INTERFACE_NOT_PASSED')
                rows=load(root/'smoke/predictions_000.jsonl');mean=sum(r['inference_seconds'] for r in rows)/len(rows)
                judge_time=json.loads((ROOT/'qwen25vl_7b/smoke_judge/supervisor.json').read_text())['elapsed_seconds']
                submitted=dispatch_split(key,mean,judge_time)
                frozen(full_submission,submitted)
                statuses[key]=dict(status='FULL_SHARD_ARRAY_SUBMITTED',**submitted)
                print(json.dumps(dict(model=key,submission=submitted)),flush=True)
            except Exception as exc:
                blocker=dict(status='BLOCKED_REQUIRES_ENGINEERING_REVIEW',error=type(exc).__name__+': '+str(exc))
                frozen(root/'full_blocker.json',blocker);statuses[key]=blocker
        write(ROOT/'controller_status.json',dict(status='MONITORING',models=statuses,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            no_cross_model_waits_except_7b_scoring_gate=True,answer_based_retries=0,time_based_continuations_allowed=True))
        if all(s['status'] in ['FULL_SHARD_ARRAY_SUBMITTED','SMOKE_FAILED','BLOCKED','BLOCKED_REQUIRES_ENGINEERING_REVIEW'] for s in statuses.values()):
            write(ROOT/'controller_completion.json',dict(status='ALL_MODELS_DISPATCHED_OR_EXPLICITLY_BLOCKED',models=statuses,
                experiment_complete=False));return
        if gate.get('status','').startswith('BLOCKED'):
            write(ROOT/'controller_completion.json',dict(status='STOPPED_7B_GATE_FAILED',models=statuses,experiment_complete=False));return
        time.sleep(60)
    continuation=renew_controller()
    write(ROOT/'controller_status.json',dict(status='CONTINUING_IN_NEXT_CPU_ALLOCATION',**continuation))

if __name__=='__main__':main()
