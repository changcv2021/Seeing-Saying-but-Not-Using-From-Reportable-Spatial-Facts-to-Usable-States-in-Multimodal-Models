"""Submit every authorized B1/B2 producer with actual dependencies only."""
import subprocess
import fcntl
from ssm_common import *
def main():
    a=cli(__doc__).parse_args();c,root=context(a)
    if a.dry_run:print('Three independent models, two independent batches, no internal intervention.');return
    scheduler=root/'scheduler';scheduler.mkdir(parents=True,exist_ok=True);(root/'logs').mkdir(exist_ok=True)
    owner=(scheduler/'launch.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    def run(cmd):return subprocess.run(cmd,capture_output=True,text=True,timeout=45,check=True).stdout
    live=run(['sinfo','-h','-p','gpu,general','-o','%P|%a|%l|%G'])
    assoc=run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS'])
    assert 'gpu|up|2-00:00:00|gpu:4' in live and 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    assert load(scheduler/'resource_authorization.json')['approved']
    panel=load(root/'manifest/PANEL_LOCK.json');assert panel['status']=='FROZEN_BEFORE_NEW_MODEL_OUTPUTS'
    for b in ('B1','B2'):
        lk=load(root/'batches'/b/'manifest/REQUEST_LOCK.json')
        for ref in lk['code']+lk['public_inputs']:check(ref)
    if not (scheduler/'LIVE_RESOURCES.json').exists():save(scheduler/'LIVE_RESOURCES.json',dict(sinfo=live,assoc=assoc,checked_at=now()))
    save(scheduler/'RESOURCE_PLAN.json',dict(scope='B1_B2_ONLY',restored_no_user_total_gpu_hour_cap=True,global_gpu_max=12,
        per_model_concurrency={'preflight':1,'B1':2,'B2':1},logical_bridge_cap=8640,symbolic_logical_cap=1152,
        supplement='PROTECTED_PRE: <=80 requests/model',physical_counts={r['batch']:r['physical_requests_per_model'] for r in panel['batches']},
        wall_allocation_gpu_hours_upper=52,estimate_basis='Historical 280-request shards: 9B 5-8 min, 27B 15-18 min; new preflight measures actual workload.',
        storage_estimate_gb=12,prefill_forward_estimate='one per generation',decode_forward_upper_bound='511 per generation; actual output lengths recorded',
        teacher_forced_score_forward=0,activation_dump=False,full_whitebox_T0_required_before_later_internal_interventions=True))
    records=[]
    def submit(key,options,args,script='job.sh'):
        path=scheduler/(key+'.json')
        if path.exists():old=load(path);records.append(old);return old['job_id']
        command=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--job-name=ssm_'+key,
            '--output='+str(root/'logs'/(key+'_%A_%a.out')),'--error='+str(root/'logs'/(key+'_%A_%a.err')),*options,str(HERE/script),*args]
        job=run(command).strip().split(';')[0];assert job.isdigit()
        r=dict(task=key,job_id=job,command=command,submitted_at=now());save(path,r);records.append(r);print(json.dumps(r),flush=True);return job
    profiles={}
    for m in MODELS:
        ng=2 if m=='qwen35_27b' else 1
        profiles[m]=submit('preflight_'+m,['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={ng*4}',f'--mem={ng*64}G','--time=01:00:00',
            '--exclude='+','.join(c['resources']['exclusions'])],['preflight','--model',m])
    for b in ('B1','B2'):
        for m in MODELS:
            ng=2 if m=='qwen35_27b' else 1;key=b+'_'+m
            proc=submit(key+'_processor',['--partition=general','--cpus-per-task=4','--mem=32G','--time=02:00:00'],['runtime','--stage','processor','--batch',b,'--model',m])
            n=len(load(root/'batches'/b/'manifest/shards.json'));concurrency=2 if b=='B1' else 1
            infer=submit(key+'_infer',['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={ng*4}',f'--mem={ng*64}G','--time=02:00:00',
                f'--array=0-{n-1}%{concurrency}','--exclude='+','.join(c['resources']['exclusions']),f'--dependency=afterok:{proc}:{profiles[m]}'],
                ['runtime','--stage','infer','--batch',b,'--model',m])
            submit(key+'_score',['--partition=general','--cpus-per-task=2','--mem=16G','--time=00:30:00','--dependency=afterany:'+infer],
                ['--batch',b,'--model',m],script='job_score.sh')
    # Per model: preflight <=1 worker; afterwards B1 <=2 + B2 <=1. Hence <=12 GPUs globally for this launch.
    save(scheduler/'SUBMISSION.json',dict(status='SUBMITTED_NOT_COMPLETED',jobs=records,model_barriers=False,no_internal_interventions=True))
    lines=['# SSM B1/B2 提交记录','', '本次只执行 B1/B2 与必要技术检查、确定性评分。提交不等于实验完成；旧结果只读。', '',
        f'结果根目录：`{root}`','', '| 任务 | Job ID |','| --- | --- |']
    lines += [f'| {r["task"]} | {r["job_id"]} |' for r in records]
    lines += ['', 'B1 每模型 4 个分片（并发 2）；B2 每模型 2 个分片（并发 1）。三模型无互等；只等待自己的 processor 和技术检查。',
        'B00 保留精确历史响应；B2 非法逆序记录 NOT_APPLICABLE，不运行负数量程序。所有 null/INVALID/错误保留，不按成绩重试。',
        '完整白盒 T0（含机制 pair / 因果前缀验收）属于后续内部干预准备，不将本轮行为 preflight 伪称完整 T0 PASS。']
    save(HERE.parent/'SSM_B1_B2_SUBMISSION_STATUS.md','\n'.join(lines)+'\n','text')
if __name__=='__main__':main()
