"""CPU-only scoring regression and current report; never runs model inference."""
import subprocess
from base import *
from design_audit import audit


def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='analysis_qa_and_current_report'))); return
    records=[]
    suites=[('phase_a',CODE/'tests','test*.py'),
        ('user_reference',CODE/'reference/SpaceConflict_PhaseA_v2','test_reference_metrics.py'),
        ('reused_parser',CODE.parent/'spatial_conflict_diagnosis_v1/tests','test_scoring.py')]
    for name,directory,pattern in suites:
        completed=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(directory),'-p',pattern],capture_output=True,text=True)
        records.append(dict(suite=name,status='PASS' if completed.returncode==0 else 'FAIL',stdout=completed.stdout,stderr=completed.stderr,returncode=completed.returncode))
    dependency_failures=[d['path'] for d in load(root/'manifest/discovery_execution_freeze.json')['dependencies'] if not Path(d['path']).is_file() or sha(d['path'])!=d['sha256']]
    checks=dict(status='PASS' if not dependency_failures and all(r['status']=='PASS' for r in records) else 'FAIL',
        tests=records,inference_dependency_changes=dependency_failures,read_model_answers_for_selection=False,
        scope='SCORER_AND_REPORT_QA_NOT_DISCOVERY_EXPERIMENT_COMPLETION')
    write(root/'reports/analysis_qa.json',checks)
    audit(cfg,root)
    import report
    report.main()
    print(json.dumps(dict(status=checks['status'],phase_a_completed=False,evidence=str(root/'reports/analysis_qa.json'))))
    if checks['status']!='PASS': raise SystemExit(1)


if __name__=='__main__': main()
