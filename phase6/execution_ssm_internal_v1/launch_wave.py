"""Parallel R1/technical preparation only; no fake dependent intervention submissions."""
import subprocess,fcntl
from internal_common import *
def main():
    a=cli(__doc__).parse_args();c,out=setup(a)
    if a.dry_run:print('Submit three independent R1 jobs and per-model probe consumers.');return
    verify_lock();(out/'scheduler').mkdir(parents=True,exist_ok=True);(out/'logs').mkdir(exist_ok=True)
    owner=(out/'scheduler/submit.lock').open('a');fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
    run=lambda cmd:subprocess.run(cmd,capture_output=True,text=True,timeout=45,check=True).stdout
    live=run(['sinfo','-h','-p','gpu','-o','%P|%a|%l|%G']);assoc=run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS'])
    assert 'gpu|up|2-00:00:00|gpu:4' in live and 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    jobs=[]
    def submit(key,options,args):
        rec=out/'scheduler'/(key+'.json')
        if rec.exists():r=load(rec);jobs.append(r);return r['job_id']
        cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--job-name=ssm_'+key,
            '--output='+str(out/'logs'/(key+'_%j.out')),'--error='+str(out/'logs'/(key+'_%j.err')),*options,str(WAVE_CODE/'job.sh'),*args]
        jid=run(cmd).strip().split(';')[0];assert jid.isdigit();r=dict(task=key,job_id=jid,command=cmd,time=now());save(rec,r);jobs.append(r);print(json.dumps(r),flush=True);return jid
    # This wave reserves <=4 GPUs; B1 currently <=8 and B2 generation has completed, so total <=12.
    b2jobs=run(['squeue','-h','-u','anonymous','-o','%j|%T'])
    if any('ssm_B2_' in l and ('infer' in l or 'preflight' in l) for l in b2jobs.splitlines()):raise ValueError('RECHECK_GLOBAL_CONCURRENCY_B2_STILL_ACTIVE')
    plan=out/'scheduler/RESOURCE_PLAN.json'
    if not plan.exists():save(plan,dict(scope='INDEPENDENT_STEPS5_AND_STRUCTURAL_PREPARATION6_7_9',models=MODELS,contexts_per_model=416,
        total_readonly_r1_forwards=1248,technical_cases_per_model=4,technical_candidate_strings=3,technical_forward_upper_per_model=256,
        new_behavior_generations=0,intervention_continuations=0,gpus_this_wave=4,concurrent_with_b1_gpu_cap=12,
        wave_scheduled_gpu_hours_upper=8,storage_gb_estimate=3,resources_restored_from=entry(ROOT/'scheduler/resource_authorization.json'),
        user_authorization='USER_REQUEST_INDEPENDENT_STEPS_5_THROUGH_10',sinfo=live,assoc=assoc))
    for m in MODELS:
        ng=2 if m=='qwen35_27b' else 1
        gpu=submit('r1_'+m,['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={ng*4}',f'--mem={ng*64}G','--time=02:00:00',
            '--exclude='+','.join(c['resources']['exclusions'])],['representations','--model',m])
        submit('probe_'+m,['--partition=general','--cpus-per-task=2','--mem=32G','--time=01:00:00','--dependency=afterok:'+gpu],['probe','--model',m])
    save(out/'scheduler/SUBMISSION.json',dict(status='SUBMITTED_NOT_COMPLETED',jobs=jobs,dependency='OWN_R1_TO_OWN_PROBE_ONLY',
        not_submitted={'I1':'CASE_ELIGIBILITY_AND_CHANGED_ACTIVATION_ENGINE_ACCEPTANCE','I2':'DISCRIMINATIVE_STRUCTURAL_QUALIFICATION_AND_PATCH_RUNNER',
            'I3':'NEEDS_COARSE_EFFECT','BASE_PROTECTED_PATCH':'NEEDS_INTERVENTION_RULE','LOCKED_INTERVENTION_EVAL':'NEEDS_MECHANISM_LOCK'}))
    text=['# 第 5–10 步独立任务提交记录','',f'结果目录：`{out}`','', '| 任务 | Job ID |','| --- | --- |']
    text += [f'| {r["task"]} | {r["job_id"]} |' for r in jobs]
    text += ['', '每模型 416 个 context，8 个固定层、5 个 pre-answer 锚点；只读表示提取，无激活替换。Oracle 组单列。',
        '第 6/7/9 步结构清单已冻结，但结构准备不是干预完成。第 8 步依赖粗定位；第 10 步干预验证依赖机制锁。',
        '完整干预工具仍需 changed-prefix 重算和机制 pair 的 free-generation 验收；本波只读技术 PASS 不冒充完整 T0。',
        '所有旧 B1/B2 raw/gold/代码/locks 均保持只读。']
    save(WAVE_CODE.parent/'SSM_STEPS5_10_SUBMISSION_STATUS.md','\n'.join(text)+'\n','text')
if __name__=='__main__':main()
