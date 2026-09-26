"""Only genuine producer/consumer dependencies. No GPU waits for files."""
import subprocess,math,fcntl
from common_i2 import *
def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['technical','core'],required=True);a=p.parse_args();c,out=setup_i2(a)
    if a.dry_run:print('Three technical jobs in parallel; 9B core only after its actual PASS; CPU afterany summary');return
    verify();scheduler=out/'scheduler';scheduler.mkdir(exist_ok=True);(out/'logs').mkdir(exist_ok=True)
    fd=(scheduler/('submit_'+a.stage+'.lock')).open('a');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def run(cmd):return subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=45).stdout
    live=run(['sinfo','-h','-p','gpu','-o','%P|%a|%l|%G']);assoc=run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS'])
    assert 'gpu|up|2-00:00:00|gpu:4' in live and 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    def submit(key,opts,args):
        path=scheduler/(key+'.json')
        if path.exists():return load(path)['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--job-name=ssm_i2_'+key,
            '--output='+str(out/'logs'/(key+'_%A_%a.out')),'--error='+str(out/'logs'/(key+'_%A_%a.err')),*opts,str(CODE_I2/'job.sh'),*args]
        jid=run(cmd).strip().split(';')[0];assert jid.isdigit()
        save(path,dict(job_id=jid,command=cmd,submitted_at=now()));print(json.dumps(load(path)),flush=True);return jid
    exclude=','.join(sorted(set(c['resources']['exclusions'])|set('nid0642,nid0653,nid0661,nid0674,nid0685,nid0688,nid0694,nid0698'.split(','))))
    if a.stage=='technical':
        plan=dict(user_authorization='USER_EXPLICIT_20260911_IMPLEMENT_AND_RUN_I2',total_gpu_hour_cap=None,scientific_scope='FROZEN_LOCALIZE_I2_ONLY',
            preparation='debug 1CPU 8GiB 10min',technical='4B/9B 1GPU 4CPU 64GiB 1h each; 27B 2GPU 8CPU 128GiB 1h',
            main='9B 8 shards, max4 concurrent; 1GPU 4CPU 64GiB each; walltime at least12h, up to live48h from independent setup timing',
            core_logical_trials=load(out/'manifest/PROTOCOL.json')['trials'],main_generation_cap512=True,estimated_scoring_forwards_per_trial_upper=20,
            main_forwards_conservative_upper_per_trial=1100,storage_estimate_gb=5,lock=entry(out/'manifest/LOCK.json'),sinfo=live,association=assoc,
            new_models=False,backbone_training=False,comparison_model_interventions='TECHNICAL_ONLY_NO_FUNCTIONAL_CLAIM')
        save(scheduler/'RESOURCE_PLAN.json',plan)
        for model in MODELS:
            ng=2 if model=='qwen35_27b' else 1
            jid=submit('tech_'+model,['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={4*ng}',f'--mem={64*ng}G','--time=01:00:00','--exclude='+exclude],['worker','--model',model,'--stage','technical'])
            if model=='qwen35_9b':
                submit('core_dispatch',['--partition=debug','--cpus-per-task=1','--mem=8G','--time=00:10:00','--dependency=afterok:'+jid],['launch','--stage','core'])
    else:
        gate=load(out/'technical/qwen35_9b/ACCEPTANCE.json');assert gate['status']=='PASS';check(gate['tolerance'])
        tech=[load(r['path']) for r in gate['cases']];seconds=max(r['patched']['generation_seconds'] for r in tech)
        planned=list(rows(out/'public_inputs/trials.jsonl'));maxshard=max(sum(r['shard']==s for r in planned) for s in range(8))
        hours=max(12,min(48,math.ceil(maxshard*max(10,seconds)*8/3600+2)))
        save(scheduler/'MEASURED_CORE_RESOURCES.json',dict(technical_acceptance=entry(out/'technical/qwen35_9b/ACCEPTANCE.json'),max_setup_generation_seconds=seconds,
            largest_shard=maxshard,wall_hours=hours,policy='RUNTIME_ONLY_NO_OUTCOME_TUNING',gpus_per_worker=1,concurrency=4))
        jid=submit('core_9b',['--partition=gpu','--array=0-7%4','--gpus-per-node=1','--cpus-per-task=4','--mem=64G',f'--time={hours}:00:00','--exclude='+exclude],['worker','--model','qwen35_9b','--stage','core'])
        submit('summary',['--partition=general','--cpus-per-task=2','--mem=16G','--time=01:00:00','--dependency=afterany:'+jid],['summarize'])
if __name__=='__main__':main()

