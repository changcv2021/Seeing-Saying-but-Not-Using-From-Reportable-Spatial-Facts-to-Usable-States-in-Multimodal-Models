"""Idempotent per-model producer-consumer jobs; no cross-model wait barrier."""
import fcntl
import subprocess
from bc_common import *

def main():
    p=cli(__doc__);p.add_argument('--batch',choices=['native_e8_measurement_v1'],required=True)
    p.add_argument('--existing-processors',default='');a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Submit frozen, qualified behavioral batch with only processor/infer/score dependencies.');return
    src=out/'batches'/a.batch;dest=out/'scheduler'/a.batch;dest.mkdir(parents=True,exist_ok=True)
    owner=(dest/'submit.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if not (src/'manifest/REQUEST_LOCK.json').exists():
        save(dest/'NOT_SUBMITTED.json',dict(reason='NO_QUALIFIED_FROZEN_BATCH',job_id=os.environ['SLURM_JOB_ID']));return
    if a.batch=='c1_count_v1':
        panel=load(out/'P4_C1/C1_PANEL_LOCK.json')
        if panel['status']!='FROZEN_BEFORE_CONFIRMATION_OUTPUTS':raise ValueError('C1_PANEL_NOT_FROZEN')
        check(panel['request_lock'])
    extra=load(src/'manifest/NATIVE_EXTENSION_LOCK.json')
    for ref in extra['code']+[extra['request_lock']]:check(ref)
    lock=load(src/'manifest/REQUEST_LOCK.json')
    for ref in lock['public_inputs']+lock['code']:check(ref)
    if not load(out/'scheduler/resource_authorization.json')['approved']:raise ValueError('NO_AUTHORITY')
    sinfo=subprocess.run(['sinfo','-h','-p','gpu','-o','%P|%a|%l|%G'],capture_output=True,text=True,timeout=30,check=True)
    assoc=subprocess.run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS'],capture_output=True,text=True,timeout=30,check=True)
    if 'gpu|up|2-00:00:00|gpu:4' not in sinfo.stdout or 'anonymous|YOUR_ACCOUNT||allocated' not in assoc.stdout:raise ValueError('LIVE_RESOURCE_CONFIGURATION_CHANGED')
    live=dest/('LIVE_RESOURCES_'+os.environ['SLURM_JOB_ID']+'.json')
    if not live.exists():save(live,dict(sinfo=sinfo.stdout,association=assoc.stdout,checked_at=now(),code=entry(__file__)))
    exclusions=','.join(c['resources']['exclusions']);existing=dict(zip(c['models'],a.existing_processors.split(','))) if a.existing_processors else {}
    if existing and (len(a.existing_processors.split(','))!=3 or any(not j.isdigit() for j in existing.values())):raise ValueError('EXISTING_PROCESSOR_MAP')
    def submit(key,options,script,args):
        record=dest/(key+'.json')
        if record.exists():return load(record)['job_id']
        command=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--job-name=bc_'+key,
            '--output='+str(out/'logs'/(key+'_%A_%a.out')),'--error='+str(out/'logs'/(key+'_%A_%a.err')),*options,str(HERE/script),*args]
        proc=subprocess.run(command,capture_output=True,text=True,timeout=60,check=True);job=proc.stdout.strip().split(';')[0]
        if not job.isdigit():raise ValueError('INVALID_SUBMISSION_REPLY:'+proc.stdout)
        save(record,dict(job_id=job,command=command,created_at=now(),batch_lock=entry(src/'manifest/REQUEST_LOCK.json')))
        print(json.dumps(dict(task=key,job_id=job,command=command)),flush=True);return job
    result=[]
    for model in c['models']:
        key=a.batch+'_'+model
        cpu=['--partition=general','--cpus-per-task=4','--mem=32G','--time=02:00:00']
        processor=existing.get(model) or submit(key+'_processor',cpu,'job_cpu.sh',['native_runtime','--stage','processor','--batch',a.batch,'--model',model])
        n=len(load(src/'manifest/shards.json'));ng=2 if model=='qwen35_27b' else 1
        gpu=['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={ng*4}',f'--mem={ng*64}G','--time=02:00:00',
            f'--array=0-{n-1}%2','--exclude='+exclusions,'--dependency=afterok:'+processor]
        infer=submit(key+'_infer',gpu,'job_cpu.sh',['native_runtime','--stage','infer','--batch',a.batch,'--model',model])
        score=submit(key+'_score',['--partition=general','--cpus-per-task=2','--mem=16G','--time=01:00:00','--dependency=afterany:'+infer],
            'job_native_score.sh',['--batch',a.batch,'--model',model])
        analyze=submit(key+'_join',['--partition=general','--cpus-per-task=2','--mem=16G','--time=01:00:00','--dependency=afterok:'+score],
            'job_cpu.sh',['native_join','--batch',a.batch,'--model',model])
        result.append(dict(model=model,processor=processor,infer=infer,score=score,join=analyze))
    save(dest/'SUBMISSION.json',dict(status='SUBMITTED_NOT_EXPERIMENT_COMPLETE',batch=a.batch,jobs=result,
        model_barriers=False,real_dependencies_only=True,no_whitebox_submission=True))

if __name__=='__main__':main()

