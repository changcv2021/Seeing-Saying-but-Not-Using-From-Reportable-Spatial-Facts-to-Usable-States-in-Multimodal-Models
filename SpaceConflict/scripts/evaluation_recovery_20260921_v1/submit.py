"""Explicit missing-work recovery; no successful-answer regeneration."""
import argparse
import getpass
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

CODE=Path(__file__).resolve().parent
BASE=Path('artifacts/model_results')
ROOT=BASE/CODE.name
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('target',choices=['qwen','api'])
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--seed',type=int,default=20260920);p.add_argument('--run-id',default=CODE.name);p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.seed==20260920 and a.run_id==CODE.name and a.limit is None
    record=ROOT/'SUBMISSIONS.json';saved=json.loads(record.read_text()) if record.exists() else {}
    if saved and not a.resume and not a.dry_run:raise FileExistsError(record)
    if not a.dry_run:(ROOT/'logs').mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    if a.target=='api' and not a.dry_run and any(k not in saved for k in ('gpt54','claude')):
        secret=getpass.getpass('Azure/Claude existing API key (hidden): ').strip()
        assert secret
        env['SPACECONFLICT_AZURE_API_KEY']=secret;env['SPACECONFLICT_CLAUDE_API_KEY']=secret
    def submit(key,args):
        if key in saved:return saved[key]['id']
        print(shlex.join(args),flush=True)
        if a.dry_run:return 'DRY_RUN'
        r=subprocess.run(args,env=env,check=True,capture_output=True,text=True)
        jid=r.stdout.strip().split(';')[0];assert jid.isdigit()
        saved[key]={'id':jid,'command':args};write(record,saved)
        print(json.dumps({'key':key,'id':jid}),flush=True);return jid
    common=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',
            '--chdir='+str(CODE),'--output='+str(ROOT/'logs/%x_%A_%a.out'),'--error='+str(ROOT/'logs/%x_%A_%a.err')]
    if a.target=='qwen':
        exclude='nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698'
        for model,indices,prior,score in [('qwen36_27b_direct','4','8303426','8303427'),('qwen38_27b_direct','10-12','8303428','8303429')]:
            if model not in saved:
                ix=[4] if model.startswith('qwen36') else [10,11,12]
                for i in ix:
                    assert not (BASE/'qwen36_38_nonthinking_20260920_v1'/model/'full'/f'predictions_{i:03d}.jsonl').exists()
            jid=submit(model,common+['--partition=gpu','--cpus-per-task=8','--mem=128G','--gpus-per-node=2','--time=2-00:00:00',
                '--exclude='+exclude,'--array='+indices,'--job-name=sc_'+model[:6]+'_repair3',
                str(CODE.parent/'qwen36_38_20260920_v1/job.sh'),'full','--model',model])
            cmd=['scontrol','update','JobId='+score,'Dependency=afterany:'+prior+':'+jid]
            print(shlex.join(cmd),flush=True)
            if not a.dry_run:
                subprocess.run(cmd,check=True);saved[model]['score_dependency_update']=cmd;write(record,saved)
    else:
        for target,cpu,mem,wall in [('gpt54',1,'4G','3-00:00:00'),('claude',4,'8G','2-00:00:00')]:
            submit(target,common+['--partition=general','--cpus-per-task='+str(cpu),'--mem='+mem,'--time='+wall,
                '--job-name=sc_'+target+'_recover21',str(CODE/'api_job.sh'),target])

if __name__=='__main__':main()
