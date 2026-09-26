"""Idempotent independent model/batch launch from completed compiler manifests."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import load,save,entry,now

def main():
    p=argparse.ArgumentParser();p.add_argument('--submit',action='store_true');a=p.parse_args()
    c=load(HERE.parent/'config_auto_v2.json');root=Path(c['root']);ledger=root/'scheduler/breadth_v1';logs=root/'logs/breadth_v1'
    assoc=subprocess.run(['sacctmgr','-nP','show','assoc','where','user=anonymous','account=YOUR_ACCOUNT','format=User,Account,Partition,QOS'],capture_output=True,text=True,check=True).stdout
    site=subprocess.run(['sinfo','-h','-p','general,gpu','-o','%P %a %l %G'],capture_output=True,text=True,check=True).stdout
    if 'anonymous|YOUR_ACCOUNT||allocated' not in assoc or any(not any(l.startswith(k) and ' up ' in l for l in site.splitlines()) for k in ('general','gpu')):raise ValueError('SITE_OR_ASSOC_UNVERIFIED')
    reports=load(root/'preparation/breadth_v1_20260910/ACCEPTANCE.json')['batches']
    reports.sort(key=lambda r:(r['batch']!='breadth_setup_v1_20260910',r['batch']))
    plan=[];smoke={}
    def submit(key,stage,extra,cpus=2,mem='8G',wall='00:30:00',gpus=0,array=None,dep=None):
        file=ledger/(key+'.json')
        if file.exists():return load(file)['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--partition='+('gpu' if gpus else 'general'),'--nodes=1','--ntasks=1',
            '--cpus-per-task='+str(cpus),'--mem='+mem,'--time='+wall,'--job-name=sws_br_'+key,
            '--output='+str(logs/(key+'_%A_%a.out')),'--error='+str(logs/(key+'_%A_%a.err'))]
        if gpus:cmd+=['--gpus-per-node='+str(gpus),'--exclude='+','.join(c['resources']['exclusions'])]
        if array:cmd+=['--array='+array]
        if dep:cmd+=['--dependency='+dep,'--kill-on-invalid-dep=yes']
        cmd+=[str(HERE/'job.sh'),stage,*extra];plan.append(dict(key=key,command=cmd));print(json.dumps(plan[-1]),flush=True)
        if not a.submit:return 'DRY_'+key
        jid=subprocess.run(cmd,capture_output=True,text=True,check=True).stdout.strip().split(';')[0]
        if not jid.isdigit():raise ValueError('UNPARSEABLE_JOB_ID')
        save(file,dict(job_id=jid,command=cmd,created_at=now(),status='SUBMITTED_NOT_COMPLETED',submitter=entry(__file__),live_assoc=assoc,live_site=site));return jid
    for r in reports:
        b=r['batch'];tag='setup' if b.startswith('breadth_setup') else 'e8' if b.startswith('native') else 'nc'
        freeze=submit(tag+'_scorelock','runner',['--stage','freeze_score','--batch',b])
        for model in c['models']:
            m=model.split('_')[-1];g=2 if m=='27b' else 1
            proc=submit(tag+'_'+m+'_proc','runner',['--stage','processor','--batch',b,'--model',model],4,'32G','01:00:00')
            deps='afterok:'+proc+(':'+smoke[model] if tag!='setup' else '')
            inf=submit(tag+'_'+m+'_infer','runner',['--stage','infer','--batch',b,'--model',model],4*g,'128G' if g==2 else '64G',
                '00:30:00' if tag=='setup' else '03:00:00' if g==2 else '02:00:00',g,'0-'+str(len(r['shards'])-1)+('%2' if g==2 else '%4'),deps)
            if tag=='setup':smoke[model]=inf
            submit(tag+'_'+m+'_score','rescore',['--batch',b,'--model',model],dep='afterok:'+freeze+',afterany:'+inf)
    if a.submit:save(ledger/'RESOURCE_AND_COMMAND_PLAN.json',dict(created_at=now(),commands=plan,source_manifest=entry(root/'preparation/breadth_v1_20260910/ACCEPTANCE.json'),
        no_project_total_budget=True,scientific_request_caps_unchanged=True,ordinary_generations=8988,setup_generations=18,
        max_wave_gpus=24,calibration='ONE_FIXED_SETUP_ROUND_NO_SEMANTIC_SCORE_GATE',independent_models=True))

if __name__=='__main__':main()
