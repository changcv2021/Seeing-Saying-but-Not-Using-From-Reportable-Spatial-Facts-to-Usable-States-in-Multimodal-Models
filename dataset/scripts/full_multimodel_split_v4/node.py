"""One model per allocation; independent replica workers, no cross-model locks."""
import json, os, signal, subprocess, sys, time
from pathlib import Path
EXTENSION=Path(__file__).resolve().parent
from campaign import ROOT,CODE,SEED,RUN_ID,registry,verify,write

def main():
    action,key=sys.argv[1:3];
    from orchestration import verify_extension
    verify_extension();verify();cfg=registry()[key];root=ROOT/key;stage_started=time.monotonic()
    judge=action.endswith('judge');smoke=action.startswith('smoke');scope='smoke' if smoke else 'full'
    if judge and key!='qwen25vl_7b':
        if json.loads((ROOT/'SCORING_GATE.json').read_text())['status']!='PASS':raise ValueError('7B_SCORING_GATE_REQUIRED')
    count=1 if smoke else (4 if judge else cfg['replicas']);per_worker=1 if judge else cfg['gpus']
    devices=os.environ['CUDA_VISIBLE_DEVICES'].split(',')
    if len(devices)!=count*per_worker:raise ValueError('ALLOCATION_GPU_COUNT_MISMATCH')
    processes=[];progress=[0]*count;last=[time.monotonic()]*count;loaded=[False]*count
    stage=root/('smoke_judge' if judge and smoke else 'full_judge' if judge else scope);stage.mkdir(parents=True,exist_ok=True)
    def stop():
        for proc in processes:
            if proc.poll() is None:
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        deadline=time.monotonic()+20
        while any(p.poll() is None for p in processes) and time.monotonic()<deadline:time.sleep(1)
        for proc in processes:
            if proc.poll() is None:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
    def received(signum,frame):raise RuntimeError('BATCH_SIGNAL_'+str(signum))
    signal.signal(signal.SIGTERM,received);signal.signal(signal.SIGINT,received)
    def health():
        from gpu_health import check
        return check(stage)
    try:
        text=health();(stage/('device_health_'+os.environ['SLURM_JOB_ID']+'.txt')).write_text(text)
        for index in range(count):
            env=os.environ.copy();env['CUDA_VISIBLE_DEVICES']=','.join(devices[index*per_worker:(index+1)*per_worker]);env['OMP_NUM_THREADS']=str(4*per_worker)
            command=[sys.executable,str(CODE/('judge.py' if judge else 'infer.py')),'--run-root',str(root),'--run-id',cfg['run_id'],
                '--scope',scope,'--num-shards',str(count),'--shard-index',str(index),'--seed',str(SEED),'--resume']
            log=(stage/f'worker_{index:03d}_{os.environ["SLURM_JOB_ID"]}.log').open('a')
            processes.append(subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True));log.close()
        next_health=time.monotonic()+60
        while any(p.poll() is None for p in processes):
            now=time.monotonic()
            if now>=next_health:health();next_health=now+60
            for i,proc in enumerate(processes):
                if proc.poll() is not None:
                    if proc.returncode:raise RuntimeError(f'WORKER_{i}_FAILED_{proc.returncode}')
                    continue
                progress_file=stage/(f'judgments_{i:03d}.jsonl' if judge else f'progress_{i:03d}.json')
                if progress_file.exists():
                    size=progress_file.stat().st_size if judge else json.loads(progress_file.read_text())['completed']
                    if size>progress[i]:progress[i]=size;last[i]=now;loaded[i]=True
                envfile=root/f'environment_{scope}_{i:03d}.json'
                if not judge and not loaded[i] and envfile.exists():loaded[i]=True;last[i]=now
                if now-last[i]>(300 if loaded[i] else 1200):raise RuntimeError(f'WORKER_{i}_NO_PROGRESS_TIMEOUT')
            write(stage/'supervisor.json',dict(status='RUNNING',job=os.environ['SLURM_JOB_ID'],worker_progress=progress,
                note='judge progress is bytes, inference progress is responses',seconds_without_progress=[now-v for v in last]))
            time.sleep(10)
        if any(p.returncode for p in processes):raise RuntimeError('WORKER_FAILED')
        write(stage/'supervisor.json',dict(status='COMPLETE',job=os.environ['SLURM_JOB_ID'],workers=count,elapsed_seconds=time.monotonic()-stage_started))
        if action=='smoke' and key=='qwen25vl_7b':
            # Reuse the already allocated GPU after the candidate process exits;
            # this avoids extra queued jobs, not scheduler accounting or limits.
            subprocess.run([sys.executable,str(CODE/'campaign.py'),'audit7b','--model',key],check=True)
            subprocess.run([sys.executable,str(EXTENSION/'node.py'),'smoke_judge',key],check=True)
            subprocess.run([sys.executable,str(CODE/'campaign.py'),'certify','--model',key],check=True)
    except BaseException as exc:
        stop();write(stage/('failure_'+os.environ['SLURM_JOB_ID']+'.json'),dict(error=type(exc).__name__+': '+str(exc),
            status='STOPPED_OUTPUTS_PRESERVED_NO_RETRY'));raise

if __name__=='__main__':main()
