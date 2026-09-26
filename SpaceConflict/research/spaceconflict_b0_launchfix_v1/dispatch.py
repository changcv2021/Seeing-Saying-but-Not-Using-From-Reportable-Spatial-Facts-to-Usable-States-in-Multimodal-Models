"""Submit only the already-authorized frozen B0 core and terminal CPU analysis chain."""
import subprocess
import shlex
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run:
        print('After measured resource PASS only: same frozen 4B/9B/27B core, analyze, publish, then STOP.'); return
    compute(); lock=load(root/'manifest/core_lock.json'); check_entries(lock['code'])
    authorization=load(root/'resources/core_authorization.json')
    measurement=load(root/'reports/resource_measurement.json')
    if lock['status']!='B0_CORE_FROZEN' or measurement['status']!='PASS' or not authorization['approved']:
        raise ValueError('MEASURED_FROZEN_AUTHORIZED_CORE_REQUIRED')
    if c['models']!=['qwen35_4b','qwen35_9b','qwen35_27b'] or authorization['max_gpu_hours']!=24:
        raise ValueError('B0_FIXED_MODEL_RESOURCE_SCOPE_CHANGED')
    observations=[]
    for cmd in [['sinfo','-p','gpu','-h','-o','%P|%a|%l|%G|%c|%m'],
                ['sinfo','-p','debug','-h','-o','%P|%a|%l|%c|%m'],
                ['sacctmgr','-nP','show','assoc','where','user=anonymous','format=User,Account,Partition,QOS']]:
        result=subprocess.run(cmd,text=True,capture_output=True,timeout=45)
        observations.append(dict(command=cmd,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode: raise ValueError('LIVE_SLURM_CONFIGURATION_UNREACHABLE')
    if not any('gpu' in line and '|up|' in line and 'gpu:4' in line for line in observations[0]['stdout'].splitlines()):
        raise ValueError('DOCUMENTED_GPU_CONFIGURATION_NOT_PRESENT')
    if not any('debug' in line and '|up|' in line for line in observations[1]['stdout'].splitlines()):
        raise ValueError('DEBUG_CPU_PARTITION_NOT_UP')
    if 'anonymous|YOUR_ACCOUNT||allocated' not in observations[2]['stdout']:
        raise ValueError('KNOWN_ACCOUNT_QOS_ASSOCIATION_NOT_CONFIRMED')
    save(root/'resources'/f'dispatch_live_config_{os.environ["SLURM_JOB_ID"]}.json',observations)
    submitted=root/'resources/gpu_core_submissions.json'
    record=load(submitted) if submitted.exists() else dict(stage='core',status='SUBMITTING_NOT_EXPERIMENT_COMPLETE',
        dispatch_job_id=os.environ['SLURM_JOB_ID'],core_lock=entry(root/'manifest/core_lock.json'),
        authorization='core_authorization.json',commands={},normal_attempts=1,automatic_model_retries=0)
    def submit(name,action,cpus,ram,wall,partition,gpus=0,dependency=None,extra=None):
        cmd=['sbatch','--parsable','--job-name=scf_b0_'+name,'--partition='+partition,'--account=YOUR_ACCOUNT','--qos=allocated',
             '--nodes=1','--ntasks=1','--cpus-per-task='+str(cpus),'--mem='+str(ram)+'G','--time='+wall,'--no-requeue',
             '--output='+str(root/'logs'/(name+'_%j.out')),'--error='+str(root/'logs'/(name+'_%j.err'))]
        if gpus: cmd.append('--gpus-per-node='+str(gpus))
        else: cmd.append('--nodelist=nid0640')
        if dependency: cmd.append('--dependency='+dependency)
        cmd.extend([str(CODE/'job.sh'),action]+(extra or []))
        record['commands'][name]=shlex.join(cmd)
        save(submitted,record,frozen=False)
        print(shlex.join(cmd),flush=True)
        child_env={k:v for k,v in os.environ.items() if not k.startswith(('SLURM_CPU_BIND','SLURM_MEM_BIND','SRUN_CPU_BIND','SRUN_MEM_BIND')) and k!='SRUN_CPUS_PER_TASK'}
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=45,env=child_env)
        if result.returncode: raise ValueError('SBATCH_FAILED_NO_AUTO_RETRY:'+result.stderr)
        jid=result.stdout.strip().split(';')[0]
        if not jid.isdigit(): raise ValueError('UNRECOGNIZED_JOB_ID_REQUIRES_MANUAL_ACCOUNTING_CHECK')
        record[name.removeprefix('core_') if name.startswith('core_') else name]=jid
        save(submitted,record,frozen=False)
        print(json.dumps(dict(submitted=name,job_id=jid,experiment_completed=False)),flush=True)
        return jid
    for key in c['models']:
        if key in record: continue
        size=authorization['models_resources'][key]
        submit('core_'+key,'infer',size['cpus'],size['ram_gib'],size['walltime'],'gpu',size['gpus'],
               extra=['--stage','core','--model',key])
    if 'analyze' not in record:
        submit('analyze','analyze',4,16,'00:45:00','debug',dependency='afterany:'+':'.join(record[k] for k in c['models']))
    if 'publish' not in record:
        submit('publish','publish',2,8,'00:45:00','debug',dependency='afterok:'+record['analyze'])
    record['status']='SUBMITTED_B0_CHAIN_NOT_EXPERIMENT_COMPLETED'
    save(submitted,record,frozen=False)
    save(root/'LIVE_STATUS.json',dict(status=record['status'],planned_responses=lock['requests_total'],
        jobs={k:record[k] for k in c['models']+['analyze','publish']},stop_after_b0=True),frozen=False)
    print('B0_ONLY_CHAIN_SUBMITTED; NOT COMPLETE; NO POST-B0 ACTIONS',flush=True)


if __name__=='__main__': main()
