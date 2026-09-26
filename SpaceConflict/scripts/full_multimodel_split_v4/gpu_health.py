"""Capture allocation identity and raw failures; never bypass health checks."""
import datetime,json,os,subprocess,time
from pathlib import Path

def check(stage):
    ids=os.environ.get('SLURM_JOB_GPUS','')
    record={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'hostname':os.uname().nodename,'job_id':os.environ.get('SLURM_JOB_ID'),
            'array_job_id':os.environ.get('SLURM_ARRAY_JOB_ID'),
            'array_index':os.environ.get('SLURM_ARRAY_TASK_ID'),
            'SLURM_JOB_GPUS':ids,'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),
            'command':['nvidia-smi','-i',ids,'-q']}
    folder=Path(stage)/'health_retry_v4'/str(record['job_id'])
    folder.mkdir(parents=True,exist_ok=True)
    error=None
    try:
        if not ids:raise ValueError('MISSING_ALLOCATED_GPU_IDS')
        result=subprocess.run(record['command'],capture_output=True,text=True,timeout=12)
        record.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        if result.returncode or 'requires reset' in result.stdout.lower():
            raise RuntimeError('GPU_HEALTH_FAILED')
        for line in result.stdout.splitlines():
            if 'GPU Recovery Action' in line and line.split(':',1)[1].strip()!='None':
                raise RuntimeError('GPU_RECOVERY_REQUIRED')
    except BaseException as exc:
        error=exc;record['error']=type(exc).__name__+': '+str(exc)
    finally:
        # Saved even if nvidia-smi fails; no identities are inferred from other GPUs.
        with (folder/(str(time.time_ns())+'.json')).open('x') as stream:
            json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    if error is not None:raise error
    return result.stdout
