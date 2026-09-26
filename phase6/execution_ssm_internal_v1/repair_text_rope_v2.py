"""Freeze technical-only correction, replace failed jobs without modifying historical code."""
import subprocess
from internal_common import *
def main():
    a=cli(__doc__).parse_args();c,out=setup(a)
    if a.dry_run:print('Repair only text position handling; same frozen panel and thresholds.');return
    verify_lock()
    code=[entry(WAVE_CODE/n) for n in ('representations.py','probe.py','representations_text_rope_v2.py','probe_text_rope_v2.py','repair_text_rope_v2.py')]
    for ref in code:compile(Path(ref['path']).read_text(),ref['path'],'exec')
    modeling=Path('external/scratch/industbench_qwen_family/venv/lib/python3.12/site-packages/transformers/models/qwen3_5/modeling_qwen3_5.py')
    save(out/'manifest/TEXT_ROPE_REPAIR_V2.json',dict(status='FROZEN_TECHNICAL_ADAPTER_REPAIR_NOT_PROMPT_CHANGE',code=code,modeling=entry(modeling),
        reason='Pure text compute_3d_position_ids returns None; let TextModel infer its native 4-axis positions. Preserve multimodal explicit delta.',
        old_namespace='representations',new_namespace='representations_v2',old_jobs=['8201864','8201866','8201868'],
        original_panel_unchanged=True,old_failures_preserved=True,thresholds_unchanged=True,mechanism_results_before_repair=0))
    run=lambda cmd:subprocess.run(cmd,capture_output=True,text=True,timeout=45,check=True).stdout
    live=run(['sinfo','-h','-p','gpu','-o','%P|%a|%l|%G']);assert 'gpu|up|2-00:00:00|gpu:4' in live
    assoc=run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS']);assert 'anonymous|YOUR_ACCOUNT||allocated' in assoc
    for jid in ('8201864','8201866','8201868','8201865','8201867','8201869'):
        state=run(['squeue','-h','-j',jid,'-o','%T']).strip()
        if state in ('RUNNING','PENDING','CONFIGURING'):run(['scancel',jid])
    result=[]
    for m in MODELS:
        ng=2 if m=='qwen35_27b' else 1
        def submit(key,options,script):
            path=out/'scheduler'/(key+'.json')
            if path.exists():rec=load(path);result.append(rec);return rec['job_id']
            cmd=['sbatch','--parsable','--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1','--job-name=ssm_'+key,
                '--output='+str(out/'logs'/(key+'_%j.out')),'--error='+str(out/'logs'/(key+'_%j.err')),*options,str(WAVE_CODE/'job.sh'),script,'--model',m]
            jid=run(cmd).strip().split(';')[0];assert jid.isdigit();rec=dict(task=key,job_id=jid,command=cmd,time=now());save(path,rec);result.append(rec);print(json.dumps(rec),flush=True);return jid
        gpu=submit('r1v2_'+m,['--partition=gpu',f'--gpus-per-node={ng}',f'--cpus-per-task={ng*4}',f'--mem={ng*64}G','--time=02:00:00','--exclude='+','.join(c['resources']['exclusions'])],'representations_text_rope_v2')
        submit('probev2_'+m,['--partition=general','--cpus-per-task=2','--mem=32G','--time=01:00:00','--dependency=afterok:'+gpu],'probe_text_rope_v2')
    save(out/'scheduler/SUBMISSION_TEXT_ROPE_V2.json',dict(status='REPAIR_SUBMITTED_NOT_COMPLETED',jobs=result,old_failed_dependency_jobs_cancelled=True,semantic_retries=0))
    text=['# 第 5 步技术修复后当前任务','', '首批在纯文本 RoPE=None 处失败，未产生 R1 正式结果；原代码与失败日志保留。以下为当前任务。','', '| 任务 | Job ID |','| --- | --- |']
    text += [f'| {r["task"]} | {r["job_id"]} |' for r in result]
    text += ['', 'R1 输入、提示、模型、分区、阈值不变；结果新存 representations_v2 和 probes_v2。未执行 I1/I2/组件定位或干预留出验证。']
    save(WAVE_CODE.parent/'SSM_STEPS5_10_REPAIR_V2_STATUS.md','\n'.join(text)+'\n','text')
if __name__=='__main__':main()
