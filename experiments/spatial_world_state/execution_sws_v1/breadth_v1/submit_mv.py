"""Independent multiview model arrays with only actual producer dependencies."""
import argparse
import subprocess
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
BATCH='multiview_breadth_v2_20260910'

def main():
    p=argparse.ArgumentParser();p.add_argument('--submit',action='store_true');a=p.parse_args()
    c=load(HERE.parent/'config_auto_v2.json');root=Path(c['root']);ledger=root/'scheduler/breadth_v1';logs=root/'logs/breadth_v1'
    assoc=subprocess.run(['sacctmgr','-nP','show','assoc','where','user=anonymous','account=YOUR_ACCOUNT','format=User,Account,Partition,QOS'],capture_output=True,text=True,check=True).stdout
    site=subprocess.run(['sinfo','-h','-p','general,gpu','-o','%P %a %l %G'],capture_output=True,text=True,check=True).stdout
    if 'anonymous|YOUR_ACCOUNT||allocated' not in assoc or any(not any(l.startswith(k) and ' up ' in l for l in site.splitlines()) for k in ('general','gpu')):raise ValueError('SITE_OR_ASSOC_UNVERIFIED')
    reportpath=root/'preparation'/BATCH/'ACCEPTANCE.json';r=load(reportpath)
    plan=[]
    def submit(key,stage,args,cpus=2,mem='8G',wall='00:30:00',gpus=0,array=None,dep=None):
        f=ledger/(key+'.json')
        if f.exists():return load(f)['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--partition='+('gpu' if gpus else 'general'),
            '--nodes=1','--ntasks=1','--cpus-per-task='+str(cpus),'--mem='+mem,'--time='+wall,'--job-name=sws_br_'+key,
            '--output='+str(logs/(key+'_%A_%a.out')),'--error='+str(logs/(key+'_%A_%a.err'))]
        if gpus:cmd+=['--gpus-per-node='+str(gpus),'--exclude='+','.join(c['resources']['exclusions'])]
        if array:cmd+=['--array='+array]
        if dep:cmd+=['--dependency='+dep,'--kill-on-invalid-dep=yes']
        cmd+=[str(HERE/'job.sh'),stage,*args];plan.append(dict(key=key,command=cmd));print(json.dumps(plan[-1]),flush=True)
        if not a.submit:return 'DRY_'+key
        jid=subprocess.run(cmd,capture_output=True,text=True,check=True).stdout.strip().split(';')[0]
        if not jid.isdigit():raise ValueError('INVALID_SUBMISSION_ID')
        save(f,dict(job_id=jid,command=cmd,created_at=now(),status='SUBMITTED_NOT_COMPLETED',submitter=entry(__file__),live_assoc=assoc,live_site=site));return jid
    frozen=submit('mv_scorelock','runner_mv_v2',['--stage','freeze_score'])
    for model in c['models']:
        tag=model.split('_')[-1];g=2 if tag=='27b' else 1
        smoke=load(ledger/('setup_'+tag+'_infer.json'))['job_id']
        proc=submit('mv_'+tag+'_proc','runner_mv_v2',['--stage','processor','--model',model],4,'32G','01:00:00')
        inf=submit('mv_'+tag+'_infer','runner_mv_v2',['--stage','infer','--model',model],4*g,'128G' if g==2 else '64G',
            '03:00:00' if g==2 else '02:00:00',g,'0-'+str(len(r['shards'])-1)+('%2' if g==2 else '%4'),'afterok:'+proc+':'+smoke)
        submit('mv_'+tag+'_score','rescore_mv_v2',['--model',model],dep='afterok:'+frozen+',afterany:'+inf)
    if a.submit:save(ledger/'MV_RESOURCE_AND_COMMAND_PLAN.json',dict(created_at=now(),commands=plan,source_manifest=entry(reportpath),
        same_worlds_all_models=True,requests_per_model=r['requests_per_model'],no_project_total_budget=True,
        secondary_reference_ablation_not_main_fusion=True,independent_models=True))

if __name__=='__main__':main()
