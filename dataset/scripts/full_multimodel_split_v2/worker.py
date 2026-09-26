"""One frozen inference/judge shard per Slurm allocation, no distributed model."""
import argparse, json, os, signal, subprocess, sys, time
from orchestration import EXTENSION, ORIGINAL, ROOT, RUN_ID, SEED, registry, verify_extension, require_gate, write

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['candidate','judge'])
    p.add_argument('--model',required=True);p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('PROTOCOL_MISMATCH')
    verify_extension();require_gate()
    cfg=registry()[a.model];root=ROOT/a.model
    plan=json.loads((root/'full_split_budget.json').read_text())[a.stage]
    index=int(os.environ.get('SLURM_ARRAY_TASK_ID','-1'))
    if not 0<=index<plan['shards']:raise ValueError('INVALID_ARRAY_INDEX')
    devices=os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')
    if len(devices)!=plan['gpus'] or not devices[0]:raise ValueError('WRONG_GPU_ALLOCATION')
    command=[sys.executable,str(EXTENSION/'checkpoint_worker.py'),a.stage,'--model',a.model,
             '--run-id',RUN_ID,
             '--num-shards',str(plan['shards']),'--shard-index',str(index),'--seed',str(SEED),'--resume']
    if a.dry_run:print(json.dumps(command));return
    job=os.environ['SLURM_JOB_ID']; stage=root/('full' if a.stage=='candidate' else 'full_judge')
    stage.mkdir(exist_ok=True)
    status=stage/f'supervisor_shard_{index:03d}.json';proc=None;checkpoint_requested=False
    def interrupt(signum,frame):raise RuntimeError('BATCH_SIGNAL_'+str(signum))
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    def request_checkpoint(signum,frame):
        nonlocal checkpoint_requested
        checkpoint_requested=True
        if proc is not None and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGUSR1)
            except ProcessLookupError:pass
    signal.signal(signal.SIGUSR1,request_checkpoint)
    def health():
        ids=os.environ.get('SLURM_JOB_GPUS')
        if not ids:raise ValueError('MISSING_ALLOCATED_GPU_IDS')
        result=subprocess.run(['nvidia-smi','-i',ids,'-q'],capture_output=True,text=True,timeout=12)
        if result.returncode or 'requires reset' in result.stdout.lower():raise RuntimeError('GPU_HEALTH_FAILED')
        for line in result.stdout.splitlines():
            if 'GPU Recovery Action' in line and line.split(':',1)[1].strip()!='None':
                raise RuntimeError('GPU_RECOVERY_REQUIRED')
        return result.stdout
    started=time.monotonic();last=started;next_health=started+60;previous=0;loaded=False
    try:
        if a.stage=='judge':
            accepted=json.loads((root/'full_candidate_acceptance.json').read_text())
            if accepted['status']!='COMPLETE' or accepted['n']!=24196:raise ValueError('CANDIDATE_NOT_COMPLETE')
        health_text=health();(stage/f'device_health_{job}_{index:03d}.txt').write_text(health_text)
        with (stage/f'worker_{index:03d}_{job}.log').open('a') as log:
            proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        if checkpoint_requested:request_checkpoint(signal.SIGUSR1,None)
        while proc.poll() is None:
            now=time.monotonic()
            if now>=next_health:health();next_health=now+60
            progress=stage/(f'progress_{index:03d}.json' if a.stage=='candidate' else f'judgments_{index:03d}.jsonl')
            if progress.exists():
                value=json.loads(progress.read_text())['completed'] if a.stage=='candidate' else progress.stat().st_size
                if value>previous:previous=value;last=now;loaded=True
            envfile=root/f'environment_full_{index:03d}.json'
            if a.stage=='candidate' and not loaded and envfile.exists():loaded=True;last=now
            write(status,dict(status='RUNNING',job=job,index=index,shards=plan['shards'],progress=previous,
                              progress_unit='responses' if a.stage=='candidate' else 'bytes',node=os.uname().nodename,
                              array_job_id=os.environ['SLURM_ARRAY_JOB_ID'],seconds_without_progress=now-last))
            time.sleep(10)
        if proc.returncode==77:
            write(status,dict(status='CHECKPOINTED',job=job,index=index,shards=plan['shards'],
                              array_job_id=os.environ['SLURM_ARRAY_JOB_ID'],elapsed_seconds=time.monotonic()-started))
            return
        if proc.returncode:raise RuntimeError('WORKER_FAILED_'+str(proc.returncode))
        write(status,dict(status='COMPLETE',job=job,index=index,shards=plan['shards'],elapsed_seconds=time.monotonic()-started))
    except BaseException as exc:
        if proc is not None and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        write(stage/f'failure_{job}_{index:03d}.json',dict(status='STOPPED_OUTPUTS_PRESERVED',error=str(exc)))
        raise

if __name__=='__main__':main()
