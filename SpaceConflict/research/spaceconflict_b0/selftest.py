"""CPU-only engineering checks independent of model results or world selection."""
import ast
import subprocess
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('AST and deterministic engineering tests; no model generation'); return
    compute()
    for path in CODE.glob('*.py'): ast.parse(path.read_text(),filename=str(path))
    r=subprocess.run([sys.executable,'-m','unittest','-v','test_b0'],capture_output=True,text=True)
    record=dict(status='PASS' if r.returncode==0 else 'FAIL',job_id=os.environ['SLURM_JOB_ID'],
                stdout=r.stdout,stderr=r.stderr,code=dependency_files(c),returncode=r.returncode,no_model_predictions_read=True)
    save(root/'reports'/f'engineering_precheck_{os.environ["SLURM_JOB_ID"]}.json',record)
    print(json.dumps(record),flush=True)
    if r.returncode: raise SystemExit(r.returncode)


if __name__=='__main__': main()
