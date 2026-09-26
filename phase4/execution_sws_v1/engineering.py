"""Run package + adapter unit tests and freeze symbolic controls on a CPU allocation."""
import subprocess
import sys
from common import *

def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('CPU package tests, SWS parser/range/control compiler tests'); return
    results=[]
    for cwd,cmd in [(Path(c['package']),[sys.executable,'-B','-m','unittest','discover','-s','tests','-v']),
                    (CODE,[sys.executable,'-B','-m','unittest','test_contracts','-v']),
                    (CODE,[sys.executable,'-B','compile_symbolic.py','--run-id',c['run_id'],'--seed',str(c['seed']),'--resume'])]:
        r=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True)
        results.append(dict(command=cmd,cwd=str(cwd),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
        if r.returncode: break
    result=dict(status='PASS' if len(results)==3 and all(r['returncode']==0 for r in results) else 'FAIL',job_id=os.environ['SLURM_JOB_ID'],results=results,new_model_calls=0)
    save(root/'reports/engineering_tests.json',result); print(json.dumps(result,ensure_ascii=False),flush=True)
    if result['status']!='PASS': raise SystemExit(2)

if __name__=='__main__': main()
