"""Submit three independent bounded Qwen3.5 evaluation chains."""
import argparse
import json
import subprocess
from pathlib import Path
from common import write, sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260904);p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();root=a.run_root;cfg=json.loads((root/'config.json').read_text())
    if a.limit is not None:p.error('Full release submission; smoke is mandatory')
    if cfg['campaign_id']!=a.run_id or cfg['seed']!=a.seed:raise ValueError('CONFIG_MISMATCH')
    out=root/'submission.json'
    record=json.loads(out.read_text()) if out.exists() else dict(run_id=a.run_id,seed=a.seed,jobs={},status='SUBMITTING',config_sha256=sha(root/'config.json'),code_sha256=sha(__file__))
    if record['config_sha256']!=sha(root/'config.json'):raise ValueError('SUBMISSION_CONFIG_CHANGED')
    if record['jobs'] and not a.resume:raise FileExistsError(out)
    def submit(stage,key,partition,cpus,ram,gpus,wall,dependencies=(),dep_type='afterok',array=None):
        name=f'{key}.{stage}'
        if name in record['jobs']:return
        cmd=['sbatch','--parsable','--job-name=sc35_'+key+'_'+stage,'--account=YOUR_ACCOUNT','--qos=allocated',
             '--partition='+partition,'--nodes=1','--ntasks=1',f'--cpus-per-task={cpus}','--mem='+ram,'--time='+wall,
             '--output='+str(root/'slurm'/f'{key}_{stage}_%A_%a.out'),'--error='+str(root/'slurm'/f'{key}_{stage}_%A_%a.err')]
        if gpus:cmd.append(f'--gpus-per-node={gpus}')
        if array:cmd.append('--array='+array)
        dep_ids=[record['jobs'][d]['job_id'] for d in dependencies]
        if stage=='compare':
            external=cfg.get('comparison_external_dependencies', [])
            if not all(str(j).isdigit() for j in external):raise ValueError('INVALID_EXTERNAL_DEPENDENCY')
            dep_ids.extend(external)
        if dep_ids:cmd.append('--dependency='+dep_type+':'+':'.join(dep_ids))
        cmd += [str(root/'code/job.sh'),stage,str(root),key]
        print(json.dumps(dict(name=name,command=cmd)),flush=True)
        if a.dry_run:
            record['jobs'][name]=dict(job_id=f'<{name}>',command=cmd);return
        result=subprocess.run(cmd,text=True,capture_output=True)
        if result.returncode:
            record.update(status='SUBMISSION_FAILED',failed_stage=name,error=result.stderr);write(out,record)
            raise RuntimeError(result.stderr)
        job_id=result.stdout.strip().split(';')[0]
        if not job_id.isdigit():raise ValueError('INVALID_SBATCH_RESPONSE')
        record['jobs'][name]=dict(job_id=job_id,command=cmd);write(out,record)
        state=subprocess.run(['scontrol','show','job','-o',job_id],text=True,capture_output=True,check=True).stdout
        if 'Reason=JobHeldAdmin' in state:
            record.update(status='STOPPED_ADMIN_HOLD',failed_stage=name);write(out,record)
            raise RuntimeError('Administrator hold: stopped without workarounds')
        print('SUBMITTED '+name+' '+job_id,flush=True)
    submit('prepare','shared','debug',1,'8G',0,'00:30:00')
    finals=[]
    for m in cfg['models']:
        k=m['key']
        submit('smoke',k,'gpu',m['cpus'],m['ram'],m['gpus'],m['smoke_wall'],['shared.prepare'])
        submit('smoke_judge',k,'gpu',4,'32G',1,'01:00:00',[k+'.smoke'])
        submit('infer',k,'gpu',m['cpus'],m['ram'],m['gpus'],m['infer_wall'],[k+'.smoke_judge'],array='0-31%2')
        submit('score',k,'general',1,'8G',0,'00:30:00',[k+'.infer'],dep_type='afterany')
        submit('judge',k,'gpu',4,'32G',1,'06:00:00',[k+'.infer'],array='0-7%2')
        submit('final',k,'general',1,'8G',0,'00:30:00',[k+'.judge',k+'.score'],dep_type='afterany')
        finals.append(k+'.final')
    submit('compare','shared','general',1,'8G',0,'00:30:00',finals,dep_type='afterany')
    if not a.dry_run:
        record['status']='SUBMITTED';write(out,record)

if __name__=='__main__':main()
