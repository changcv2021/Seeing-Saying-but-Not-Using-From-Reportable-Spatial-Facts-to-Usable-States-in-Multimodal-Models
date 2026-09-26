"""Print exact live-validated resources, then independent append-safe submissions."""
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
    c=load(HERE.parent/'config_auto_v2.json');root=Path(c['root'])
    assoc=subprocess.run(['sacctmgr','-nP','show','assoc','where','user=anonymous','account=YOUR_ACCOUNT','format=User,Account,Partition,QOS'],capture_output=True,text=True,check=True).stdout
    site=subprocess.run(['sinfo','-h','-p','general,gpu','-o','%P %a %l %G'],capture_output=True,text=True,check=True).stdout
    if 'anonymous|YOUR_ACCOUNT||allocated' not in assoc or any(not any(l.startswith(k) and ' up ' in l for l in site.splitlines()) for k in ('general','gpu')):raise ValueError('LIVE_SITE_UNVERIFIED')
    ledger=root/'scheduler/coverage_supplement_v1';logs=root/'logs/coverage_supplement_v1'
    if a.submit:logs.mkdir(parents=True,exist_ok=True)
    reports=load(root/'preparation/coverage_supplement_v1_20260910/ACCEPTANCE.json')['batches']
    plan=[];smoke={}
    def submit(key,stage,args,cpus=2,mem='12G',wall='01:00:00',gpus=0,array=None,dep=None):
        f=ledger/(key+'.json')
        if f.exists():return load(f)['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--partition='+('gpu' if gpus else 'general'),
             '--nodes=1','--ntasks=1','--cpus-per-task='+str(cpus),'--mem='+mem,'--time='+wall,
             '--job-name=sws_supp_'+key,'--output='+str(logs/(key+'_%A_%a.out')),'--error='+str(logs/(key+'_%A_%a.err'))]
        if gpus:cmd+=['--gpus-per-node='+str(gpus),'--exclude='+','.join(c['resources']['exclusions'])]
        if array:cmd+=['--array='+array]
        if dep:cmd+=['--dependency='+dep,'--kill-on-invalid-dep=yes']
        cmd+=[str(HERE/'job.sh'),stage,*args]
        plan.append(dict(key=key,command=cmd));print(json.dumps(plan[-1]),flush=True)
        if not a.submit:return 'DRY_'+key
        jid=subprocess.run(cmd,capture_output=True,text=True,check=True).stdout.strip().split(';')[0]
        if not jid.isdigit():raise ValueError('UNPARSEABLE_JOB_ID')
        save(f,dict(job_id=jid,command=cmd,created_at=now(),status='SUBMITTED_NOT_COMPLETED',live_assoc=assoc,live_site=site,
                    submitter=entry(__file__),standing_user_authorization=True));return jid
    for r in reports:
        b=r['batch'];tag=r['kind'].lower()
        frozen=submit(tag+'_scorelock','runner',['--stage','freeze_score','--batch',b])
        for model in c['models']:
            m=model.split('_')[-1];g=2 if m=='27b' else 1
            proc=submit(tag+'_'+m+'_proc','runner',['--stage','processor','--batch',b,'--model',model],4,'32G','02:00:00')
            deps='afterok:'+proc+(':'+smoke[model] if tag!='setup' else '')
            inf=submit(tag+'_'+m+'_infer','runner',['--stage','infer','--batch',b,'--model',model],4*g,'128G' if g==2 else '64G',
                '00:30:00' if tag=='setup' else '04:00:00' if g==2 else '03:00:00',g,
                '0-'+str(len(r['shards'])-1)+'%2',deps)
            if tag=='setup':smoke[model]=inf
            submit(tag+'_'+m+'_score','rescore',['--batch',b,'--model',model],dep='afterok:'+frozen+',afterany:'+inf)
    if a.submit:
        save(ledger/'RESOURCE_AND_COMMAND_PLAN.json',dict(created_at=now(),commands=plan,
            source_manifest=entry(root/'preparation/coverage_supplement_v1_20260910/ACCEPTANCE.json'),
            no_project_total_gpu_hour_cap=True,scientific_caps_unchanged=True,max_independent_wave_gpus=24,
            qualification='ONE_FIXED_SETUP_ROUND_INTERFACE_ONLY_NO_SEMANTIC_SCORE_GATE',
            independent_models_batches=True,only_genuine_dependencies=True,
            worker_walltime_policy='RESUMABLE_PROFILE_SIZED_3H_4H_NOT_A_NEW_USAGE_LIMIT',
            model_profile='REUSED_SUCCESSFUL_SWS_BFLOAT16_SDPA_1GPU_4B_9B_2GPU_27B_NO_OFFLOAD'))


if __name__=='__main__':main()
