"""Idempotent, live-checked Slurm submission. No GPU wait loops or artificial total cap."""
import subprocess,fcntl,shlex
from v2_common import *
def submit(key,options,args):
    root=ROOT/'scheduler';root.mkdir(parents=True,exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    p=root/(key+'.json')
    if p.exists():return load(p)['job_id']
    cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--job-name=ssmv2_'+key,
         '--output='+str(ROOT/'logs'/(key+'_%A_%a.out')),'--error='+str(ROOT/'logs'/(key+'_%A_%a.err')),*options,str(HERE/'job.sh'),*args]
    print(shlex.join(cmd),flush=True)
    job=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=45).stdout.strip().split(';')[0];assert job.isdigit()
    save(p,dict(task=key,job_id=job,command=cmd,submitted_at=now(),status='SUBMITTED_NOT_COMPLETED'));print('SUBMITTED '+key+' '+job,flush=True);return job
def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['prepare','behavior'],required=True);p.add_argument('--batch',default='W1_TARGET');a=p.parse_args()
    # This entry only inspects small metadata and submits jobs; safe on a login node.
    assert a.run_id==RUN and a.seed==SEED
    (ROOT/'scheduler').mkdir(parents=True,exist_ok=True)
    own=(ROOT/'scheduler/launcher.lock').open('a');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def run(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=45).stdout
    live=run(['sinfo','-h','-p','debug,general,gpu','-o','%P|%a|%l|%G'])
    assoc=run(['sacctmgr','-nP','show','assoc','where','user=anonymous','format=User,Account,Partition,QOS'])
    assert 'gpu|up|2-00:00:00|gpu:4' in live and 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    if not (ROOT/'scheduler/resource_authorization.json').exists():
        save(ROOT/'scheduler/resource_authorization.json',dict(approved=True,models=MODELS,
            authority='USER: 根据上述实验要求进行相关实验; prior explicit autonomous submission permission',
            no_global_gpu_hour_cap=True,site_limits_apply=True,no_unrelated_cancellations=True,live=live,assoc=assoc,
            behavior_profile='4B/9B 1 GPU 4CPU 64G; 27B 2GPU 8CPU128G; 12h allocation upper limit (not per-shard 6h restriction)',
            rationale='Historical 280 request shards took 5–18 minutes. New 288 request shards reuse the same loader/512-token engine; upper walltime leaves substantial contingency.',
            output=str(ROOT/'logs'),guide=entry(GUIDE)))
    if a.stage=='prepare':
        for key,task,extra in [('W0','close_history',['--stage','w0']),('W2','close_history',['--stage','w2']),('W1_build','build_w1',[])]:
            submit(key,['--partition=debug','--cpus-per-task=1','--mem=8G','--time=00:30:00'],[task,*extra])
        return
    out=ROOT/'batches'/a.batch;lock=load(out/'manifest/REQUEST_LOCK.json')
    for ref in lock['code']+lock['public_inputs']:check(ref)
    n=len(load(out/'manifest/shards.json'))
    for m in MODELS:
        ng=2 if m=='qwen35_27b' else 1;key=a.batch+'_'+m
        proc=submit(key+'_processor',['--partition=general','--cpus-per-task=4','--mem=32G','--time=02:00:00'],['runtime','--stage','processor','--batch',a.batch,'--model',m])
        infer=submit(key+'_infer',['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={4*ng}',f'--mem={64*ng}G','--time=12:00:00',
            f'--array=0-{n-1}%2','--exclude='+EXCLUSIONS,'--dependency=afterok:'+proc],['runtime','--stage','infer','--batch',a.batch,'--model',m])
        submit(key+'_score',['--partition=general','--cpus-per-task=1','--mem=8G','--time=00:30:00','--dependency=afterany:'+infer],['behavior_score','--batch',a.batch,'--model',m])
if __name__=='__main__':main()
