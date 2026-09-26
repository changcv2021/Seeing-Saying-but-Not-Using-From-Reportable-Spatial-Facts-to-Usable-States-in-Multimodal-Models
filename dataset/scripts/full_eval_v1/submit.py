"""Submit the approved bounded Slurm chain; persist IDs after each submission."""
import argparse
import json
import subprocess
from pathlib import Path
from common import write

p=argparse.ArgumentParser()
p.add_argument('--run-root',type=Path,required=True)
p.add_argument('--run-id',required=True)
p.add_argument('--dry-run',action='store_true')
p.add_argument('--resume',action='store_true')
p.add_argument('--seed',type=int,default=20260904)
p.add_argument('--limit',type=int)
p.add_argument('--prepare-dependency',help='Explicit integration job ID that must complete first')
args=p.parse_args()
jobs_path=args.run_root/'submission.json'
jobs=json.loads(jobs_path.read_text()) if jobs_path.exists() else {}
if jobs and not args.resume: raise FileExistsError(jobs_path)
stages=[('prepare','general' if args.prepare_dependency else 'debug',1,'8G',0,'02:00:00' if args.prepare_dependency else '01:00:00',None,None),
        ('smoke','gpu',4,'64G',1,'01:00:00','afterok:prepare',None),
        ('infer','gpu',4,'64G',1,'04:00:00','afterok:smoke','0-7%2'),
        ('score','general',1,'8G',0,'00:30:00','afterany:infer',None),
        ('judge','gpu',4,'32G',1,'06:00:00','afterok:infer','0-7%2'),
        ('final','general',1,'8G',0,'00:30:00','afterany:judge:score',None)]
for name,partition,cpus,ram,gpus,time,dependency,array in stages:
    if name in jobs: continue
    command=['sbatch','--parsable','--job-name=sc_full_v1_'+name,'--partition='+partition,
             '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',f'--cpus-per-task={cpus}',
             '--mem='+ram,'--time='+time,
             '--output='+str(args.run_root/'slurm'/f'{name}_%A_%a.out'),
             '--error='+str(args.run_root/'slurm'/f'{name}_%A_%a.err')]
    if gpus: command.append(f'--gpus-per-node={gpus}')
    if array: command.append('--array='+array)
    if dependency:
        parts=dependency.split(':')
        command.append('--dependency='+':'.join([parts[0]]+[jobs[x]['job_id'] if x in jobs else x for x in parts[1:]]))
    if name=='prepare' and args.prepare_dependency:
        if not args.prepare_dependency.isdigit(): raise ValueError('INVALID_INTEGRATION_JOB_ID')
        command.append('--dependency=afterok:'+args.prepare_dependency)
    command += [str(args.run_root/'code/job.sh'),name,str(args.run_root)]
    print(json.dumps(dict(phase=name,command=command)),flush=True)
    if not args.dry_run:
        result=subprocess.run(command,capture_output=True,text=True,check=True)
        job_id=result.stdout.strip().split(';')[0]
        if not job_id.isdigit(): raise ValueError('UNEXPECTED_SBATCH_OUTPUT')
        jobs[name]=dict(job_id=job_id,command=command,run_id=args.run_id)
        write(jobs_path,jobs)
        print(f'SUBMITTED {name} {job_id}',flush=True)
