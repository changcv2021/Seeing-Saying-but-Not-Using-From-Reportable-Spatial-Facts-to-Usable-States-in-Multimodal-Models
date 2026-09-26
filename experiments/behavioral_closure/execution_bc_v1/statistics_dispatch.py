"""Append independent per-model CPU analysis to already submitted measured batches."""
import subprocess
from bc_common import *

def main():
    p=cli(__doc__);p.add_argument('--batch',choices=['e5_measurement_v1','c1_count_v1'],required=True)
    a=p.parse_args();c,sws,out=context(a)
    if a.dry_run:print('Submit per-model statistics only after its diagnostic join.');return
    dest=out/'scheduler'/a.batch;source=dest/'SUBMISSION.json'
    if not source.exists():
        save(dest/'STATISTICS_NOT_SUBMITTED.json',dict(reason='NO_QUALIFIED_SUBMITTED_BATCH'));return
    for row in load(source)['jobs']:
        name=a.batch+'_'+row['model']+'_stats';record=dest/(name+'.json')
        if record.exists():continue
        command=['sbatch','--parsable','--partition=general','--account=YOUR_ACCOUNT','--qos=allocated',
            '--cpus-per-task=2','--mem=16G','--time=01:00:00','--dependency=afterok:'+row['join'],
            '--job-name=bc_'+name,'--output='+str(out/'logs'/(name+'_%j.out')),'--error='+str(out/'logs'/(name+'_%j.err')),
            str(HERE/'job_cpu.sh'),'measured_statistics','--batch',a.batch,'--model',row['model']]
        result=subprocess.run(command,check=True,capture_output=True,text=True,timeout=60)
        job=result.stdout.strip().split(';')[0]
        if not job.isdigit():raise ValueError('BAD_JOB_ID')
        save(record,dict(job_id=job,command=command,source=entry(source),code=entry(__file__),
            analysis_code=entry(HERE/'measured_statistics.py'),status_code=entry(HERE/'quality_audit.py')))
        print(json.dumps(dict(model=row['model'],statistics_job=job)),flush=True)

if __name__=='__main__':main()
