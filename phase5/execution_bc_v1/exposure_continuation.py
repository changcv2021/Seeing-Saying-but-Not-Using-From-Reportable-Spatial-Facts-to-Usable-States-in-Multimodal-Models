"""Failure-only source audit continuation; never bypass holds or cancellation."""
import subprocess
from bc_common import *

def main():
    p=cli(__doc__);p.add_argument('--stage',choices=['dispatch','resume'],required=True);a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Continue only TIMEOUT/NODE_FAIL source audit; no model responses retried.');return
    dest=out/'P4_C1';accept=dest/'ACCEPTANCE.json'
    if accept.exists():
        if load(accept)['status']!='CANDIDATE_AUDIT_COMPLETE':raise ValueError('BAD_EXISTING_ACCEPTANCE')
        save(dest/('CONTINUATION_NOT_NEEDED_'+os.environ['SLURM_JOB_ID']+'.json'),dict(acceptance=entry(accept)));return
    state=subprocess.run(['sacct','-n','-P','-X','-j','8198605','--format=JobID,State'],capture_output=True,text=True,check=True,timeout=30).stdout
    records=[line.split('|') for line in state.strip().splitlines()]
    parent=next((r[1] for r in records if r[0]=='8198605'),None)
    if parent not in ('TIMEOUT','NODE_FAIL'):raise ValueError('NO_AUTOMATIC_CONTINUATION_FOR_STATE:'+str(parent))
    if a.stage=='resume':
        import exposure
        original_save=exposure.save
        def checked_save(path,value,*args,**kw):
            if Path(path)==dest/'EXPOSURE_AUDIT_LOCK.json' and Path(path).exists():
                old=load(path);new=dict(value);new['created_at']=old['created_at']
                if digest(old)!=digest(new):raise ValueError('RESUME_FROZEN_SOURCE_INPUTS_CHANGED')
                return
            return original_save(path,value,*args,**kw)
        exposure.save=checked_save
        save(dest/('RESUME_ATTEMPT_'+os.environ['SLURM_JOB_ID']+'.json'),dict(predecessor='8198605',state=parent,
            code=entry(__file__),frozen_exposure_code=entry(HERE/'exposure.py'),source_lock=entry(dest/'EXPOSURE_AUDIT_LOCK.json')))
        sys.argv=[sys.argv[0],'--resume'];exposure.main();return
    # A completed original audit leaves the existing compiler dependency untouched.
    # Only terminal infrastructure failure reaches this branch; a user cancellation or hold never does.
    config=subprocess.run(['sinfo','-h','-p','general','-o','%P|%a|%l'],capture_output=True,text=True,check=True,timeout=30).stdout
    association=subprocess.run(['sacctmgr','-n','-P','show','assoc','user=anonymous','format=User,Account,Partition,QOS'],capture_output=True,text=True,check=True,timeout=30).stdout
    if 'general|up|4-00:00:00' not in config.replace('general*','general') or 'anonymous|YOUR_ACCOUNT||allocated' not in association:raise ValueError('LIVE_RESOURCES_CHANGED')
    compiler=subprocess.run(['scontrol','show','job','8198628'],capture_output=True,text=True,check=True,timeout=30).stdout
    if 'JobState=PENDING' not in compiler or 'afterok:8198605' not in compiler:raise ValueError('COMPILER_DEPENDENCY_CHANGED')
    command=['sbatch','--parsable','--partition=general','--account=YOUR_ACCOUNT','--qos=allocated','--cpus-per-task=4','--mem=32G','--time=02:00:00',
        '--job-name=bc_P4_source_resume','--output='+str(out/'logs/P4_resume_%j.out'),'--error='+str(out/'logs/P4_resume_%j.err'),
        str(HERE/'job_cpu.sh'),'exposure_continuation','--stage','resume']
    record=dest/'CONTINUATION_SUBMISSION.json'
    if record.exists():job=load(record)['job_id']
    else:
        job=subprocess.run(command,capture_output=True,text=True,check=True,timeout=60).stdout.strip().split(';')[0]
        if not job.isdigit():raise ValueError('BAD_JOB_ID')
        save(record,dict(job_id=job,command=command,predecessor_state=parent,code=entry(__file__),reason='FAILURE_ONLY_SOURCE_AUDIT_RESUME'))
    subprocess.run(['scontrol','update','JobId=8198628','Dependency=afterok:'+job],check=True,timeout=30)
    save(dest/'CONTINUATION_DEPENDENCY_UPDATE.json',dict(compiler='8198628',dependency='afterok:'+job,request=entry(record)))

if __name__=='__main__':main()
