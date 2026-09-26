"""Submit independent preparation/controller branches after tiny Batch bootstrap."""
import argparse
import getpass
import json
import os
import shlex
import subprocess
from batch import ROOT,CODE,RUN_ID,SEED,write

def main():
    p=argparse.ArgumentParser();p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED);p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.run_id==RUN_ID and a.seed==SEED and a.limit is None
    path=ROOT/'SUBMISSIONS.json';saved=json.loads(path.read_text()) if path.exists() else {}
    if saved and not a.resume and not a.dry_run:raise SystemExit('ALREADY_SUBMITTED')
    env=dict(os.environ)
    if not a.dry_run:
        (ROOT/'logs').mkdir(parents=True,exist_ok=True)
        secret=os.environ.get('SPACECONFLICT_AZURE_API_KEY') or getpass.getpass('Azure API key (hidden): ')
        if not secret.strip():raise SystemExit('MISSING_CREDENTIAL')
        env['SPACECONFLICT_AZURE_API_KEY']=secret.strip();secret=None
    def submit(stage,partition,cpus,ram,wall,dependency=None):
        if stage in saved:return saved[stage]['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',
            '--partition='+partition,'--cpus-per-task='+str(cpus),'--mem='+ram,'--time='+wall,
            '--job-name=sc_g54batch_'+stage,'--chdir='+str(CODE),
            '--output='+str(ROOT/'logs'/('%x_%j.out')),'--error='+str(ROOT/'logs'/('%x_%j.err'))]
        if dependency:cmd+=['--dependency=afterok:'+dependency]
        cmd += [str(CODE/'job.sh'),stage];print(shlex.join(cmd),flush=True)
        if a.dry_run:return '${BOOTSTRAP_ID}'
        result=subprocess.run(cmd,env=env,capture_output=True,text=True)
        if result.returncode:
            print(result.stderr,flush=True)
            raise SystemExit('SLURM_REJECTED_NO_JOB_CREATED')
        jid=result.stdout.strip().split(';')[0];assert jid.isdigit()
        saved[stage]={'job_id':jid,'command':cmd};write(path,saved);print(json.dumps(saved[stage]),flush=True)
        return jid
    boot=submit('bootstrap','general',4,'8G','00:30:00')
    submit('prepare','general',4,'8G','12:00:00',boot)
    submit('control','general',1,'4G','3-00:00:00',boot)
    env.pop('SPACECONFLICT_AZURE_API_KEY',None)

if __name__=='__main__':main()
