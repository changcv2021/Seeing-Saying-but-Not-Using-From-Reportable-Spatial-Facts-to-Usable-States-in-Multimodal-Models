"""Allocation-only UUID mapping and tiny CUDA kernel check, no model loading."""
import json,os,subprocess
from orchestration import ROOT,write,verify_extension
from gpu_health import check,allocated_uuids
verify_extension()
text=check(ROOT/'gpu_uuid_probe_v5')
import torch
x=torch.ones(8,device='cuda');assert float((x+x).sum())==16
record=dict(status='PASS',model_calls=0,job=os.environ['SLURM_JOB_ID'],
    SLURM_JOB_GPUS=os.environ['SLURM_JOB_GPUS'],CUDA_VISIBLE_DEVICES=os.environ['CUDA_VISIBLE_DEVICES'],
    gpu_uuids=allocated_uuids(),cuda_kernel='PASS',nvidia_smi_by_uuid='PASS')
old=subprocess.run(['nvidia-smi','-i',os.environ['SLURM_JOB_GPUS'],'-q'],capture_output=True,text=True,timeout=12)
record['old_global_index_query_returncode']=old.returncode
record['old_global_index_error']=old.stdout if old.returncode else None
write(ROOT/'gpu_uuid_probe_v5'/('result_'+os.environ['SLURM_JOB_ID']+'.json'),record)
print(json.dumps(record),flush=True)
