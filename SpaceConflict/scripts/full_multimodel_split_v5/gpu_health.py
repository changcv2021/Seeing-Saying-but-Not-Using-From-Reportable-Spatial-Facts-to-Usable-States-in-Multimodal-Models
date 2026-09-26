"""Resolve CUDA-visible allocation to stable UUIDs before NVML health query."""
import datetime,functools,json,os,re,subprocess,time
from pathlib import Path
@functools.lru_cache(maxsize=1)
def allocated_uuids():
    import torch
    expected=len(os.environ.get('CUDA_VISIBLE_DEVICES','').split(','))
    count=torch.cuda.device_count()
    if not os.environ.get('SLURM_JOB_GPUS') or count!=expected or count<1:
        raise ValueError('CUDA_ALLOCATION_CARDINALITY_MISMATCH')
    result=[]
    for index in range(count):
        value=str(torch.cuda.get_device_properties(index).uuid)
        if not value.startswith('GPU-'):value='GPU-'+value
        if not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}',value):raise ValueError('UNSUPPORTED_CUDA_UUID:'+value)
        result.append(value)
    if len(set(result))!=count:raise ValueError('DUPLICATE_CUDA_UUID')
    return result
def check(stage):
    record={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'hostname':os.uname().nodename,'job_id':os.environ.get('SLURM_JOB_ID'),
       'array_job_id':os.environ.get('SLURM_ARRAY_JOB_ID'),
       'array_index':os.environ.get('SLURM_ARRAY_TASK_ID'),
       'SLURM_JOB_GPUS':os.environ.get('SLURM_JOB_GPUS'),
       'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),
       'mapping':'CUDA_VISIBLE_DEVICE_PROPERTIES_UUID_NOT_SLURM_GLOBAL_INDEX'}
    folder=Path(stage)/'health_retry_v5'/str(record['job_id']);folder.mkdir(parents=True,exist_ok=True)
    error=None
    try:
        uuids=allocated_uuids();record['allocated_gpu_uuids']=uuids
        record['command']=['nvidia-smi','-i',','.join(uuids),'-q']
        result=subprocess.run(record['command'],capture_output=True,text=True,timeout=12)
        record.update(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        if result.returncode or 'requires reset' in result.stdout.lower():raise RuntimeError('GPU_HEALTH_FAILED')
        for line in result.stdout.splitlines():
            if 'GPU Recovery Action' in line and line.split(':',1)[1].strip()!='None':
                raise RuntimeError('GPU_RECOVERY_REQUIRED')
        for value in uuids:
            if value not in result.stdout:raise ValueError('HEALTH_REPORT_MISSING_ALLOCATED_UUID')
    except BaseException as exc:
        error=exc;record['error']=type(exc).__name__+': '+str(exc)
    finally:
        with (folder/(str(time.time_ns())+'.json')).open('x') as stream:
            json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    if error is not None:raise error
    return result.stdout
