"""Replace score jobs only; preserve all three existing inference job IDs."""
import argparse
import json
import subprocess
from pathlib import Path
from common import write,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-root',type=Path,required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260904);p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();root=a.run_root;cfg=json.loads((root/'config.json').read_text())
    if (a.run_id,a.seed)!=(cfg['run_id'],cfg['seed']) or a.limit is not None:raise ValueError('CONFIG_MISMATCH')
    out=root/'submission.json'
    record=json.loads(out.read_text()) if out.exists() else dict(run_id=a.run_id,seed=a.seed,jobs={},dependency_updates={},status='SUBMITTING',config_sha256=sha(root/'config.json'),code_sha256=sha(__file__))
    if record['config_sha256']!=sha(root/'config.json'):raise ValueError('CONFIG_CHANGED')
    if record['jobs'] and not a.resume:raise FileExistsError(out)
    def submit(key,phase,partition,cpus,ram,gpus,wall,dependency=None,array=None):
        name=key+'.'+phase
        if name in record['jobs']:return record['jobs'][name]['job_id']
        cmd=['sbatch','--parsable','--job-name=scf_'+key+'_'+phase,'--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',
             '--partition='+partition,'--cpus-per-task='+str(cpus),'--mem='+ram,'--time='+wall,
             '--output='+str(root/'slurm'/f'{key}_{phase}_%A_%a.out'),'--error='+str(root/'slurm'/f'{key}_{phase}_%A_%a.err')]
        if gpus:cmd.append('--gpus-per-node='+str(gpus))
        if array:cmd.append('--array='+array)
        if dependency:cmd.append('--dependency='+dependency)
        cmd.extend([str(root/'code/job.sh'),phase,str(root),key]);print(json.dumps(dict(stage=name,command=cmd)),flush=True)
        if a.dry_run:jid='<'+name+'>'
        else:
            result=subprocess.run(cmd,text=True,capture_output=True)
            if result.returncode:
                record.update(status='FAILED',failed_stage=name,error=result.stderr);write(out,record);raise RuntimeError(result.stderr)
            jid=result.stdout.strip().split(';')[0]
            if not jid.isdigit():raise ValueError('INVALID_JOB_ID')
        record['jobs'][name]=dict(job_id=jid,command=cmd)
        if not a.dry_run:
            write(out,record)
            state=subprocess.run(['scontrol','show','job','-o',jid],text=True,capture_output=True,check=True).stdout
            if 'Reason=JobHeldAdmin' in state:
                record.update(status='STOPPED_ADMIN_HOLD');write(out,record);raise RuntimeError('ADMIN_HOLD')
            print('SUBMITTED '+name+' '+jid,flush=True)
        return jid
    gate=submit('shared','prepare','debug',1,'8G',0,'00:30:00')
    final_ids=[];new_smoke={}
    for key in cfg['models']:
        inference=cfg['inference_jobs'][key]
        smoke=gate
        if key!='qwen35_9b':
            smoke=submit(key,'smoke_judge','gpu',4,'32G',1,'01:00:00','afterok:'+gate)
            new_smoke[key]=smoke
        score=submit(key,'score','general',1,'8G',0,'00:30:00',f'afterok:{gate},afterany:{inference}')
        judge=submit(key,'judge','gpu',4,'32G',1,'06:00:00',f'afterok:{inference}:{smoke}',array='0-7%2')
        final_ids.append(submit(key,'final','general',1,'8G',0,'00:30:00',f'afterany:{score}:{judge}'))
    submit('shared','compare','general',1,'8G',0,'00:30:00','afterany:'+':'.join(final_ids))
    # Only repair dependency links on the two blocked pending inference arrays.
    # Neither re-submit nor change priority/resources for any inference job.
    for key,smoke in new_smoke.items():
        if key in record['dependency_updates']:continue
        jid=cfg['inference_jobs'][key]
        cmd=['scontrol','update','JobId='+jid,'Dependency=afterok:'+smoke]
        print(json.dumps(dict(update=key,command=cmd)),flush=True)
        if not a.dry_run:
            state=subprocess.run(['scontrol','show','job','-o',jid],text=True,capture_output=True,check=True).stdout
            if 'JobState=PENDING' not in state or 'Reason=JobHeldAdmin' in state:
                raise ValueError('INFERENCE_NOT_SAFE_PENDING')
            result=subprocess.run(cmd,text=True,capture_output=True)
            if result.returncode:raise RuntimeError(result.stderr)
            record['dependency_updates'][key]=dict(command=cmd,status='UPDATED');write(out,record)
    if not a.dry_run:record['status']='SUBMITTED_AND_DEPENDENCIES_UPDATED';write(out,record)

if __name__=='__main__':main()
