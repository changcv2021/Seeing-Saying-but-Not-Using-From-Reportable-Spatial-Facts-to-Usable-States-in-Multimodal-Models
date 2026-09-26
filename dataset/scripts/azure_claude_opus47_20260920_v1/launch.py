import argparse
import getpass
import json
import os
import shlex
import subprocess
from run import ROOT,CODE,RUN_ID,SEED,write

p=argparse.ArgumentParser();p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
p.add_argument('--seed',type=int,default=SEED);p.add_argument('--run-id',default=RUN_ID);p.add_argument('--limit',type=int)
a=p.parse_args();assert a.seed==SEED and a.run_id==RUN_ID and a.limit is None
record=ROOT/'SUBMISSIONS.json'
if record.exists():raise SystemExit('ALREADY_SUBMITTED_SEE_SUBMISSIONS_JSON_NO_DUPLICATE')
cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--partition=general','--nodes=1','--ntasks=1',
    '--cpus-per-task=4','--mem=8G','--time=2-00:00:00','--job-name=sc_claude_opus47',
    '--chdir='+str(CODE),'--output='+str(ROOT/'logs/%x_%j.out'),'--error='+str(ROOT/'logs/%x_%j.err'),str(CODE/'job.sh')]
print(shlex.join(cmd),flush=True)
if not a.dry_run:
    assert json.loads((ROOT/'SETUP_PROBE_sdk_auth.json').read_text())['status']=='PASS'
    (ROOT/'logs').mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env.pop('SPACECONFLICT_AZURE_API_KEY',None)
    env['SPACECONFLICT_CLAUDE_API_KEY']=os.environ.get('SPACECONFLICT_CLAUDE_API_KEY') or getpass.getpass('Claude Foundry API key (hidden): ')
    result=subprocess.run(cmd,env=env,capture_output=True,text=True);env.pop('SPACECONFLICT_CLAUDE_API_KEY',None)
    if result.returncode:print(result.stderr);raise SystemExit('SLURM_REJECTED')
    jid=result.stdout.strip().split(';')[0];assert jid.isdigit()
    write(record,dict(job_id=jid,command=cmd));print('SUBMITTED '+jid)
