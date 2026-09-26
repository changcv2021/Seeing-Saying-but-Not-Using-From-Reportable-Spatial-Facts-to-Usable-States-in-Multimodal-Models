"""CPU-only engineering validation; zero candidate or judge model calls."""
import argparse, ast, json, os, subprocess, sys, unittest
from orchestration import (EXTENSION, ORIGINAL, REPORTING, ROOT, RUN_ID, SEED, LOCK,
                           budget_for, validate_rows, array_command, cpu_command,
                           registry, verify, frozen, sha)

class SchedulingTests(unittest.TestCase):
    def test_single_card_independent_requests(self):
        plan=budget_for(dict(gpus=1,replicas=4),3,192)
        cmd=array_command('fixture','candidate',plan)
        self.assertIn('--gpus-per-node=1',cmd)
        self.assertIn('--nodes=1',cmd)
        self.assertFalse(any(x.startswith('--nodelist') or x=='--exclusive' for x in cmd))
        self.assertEqual(plan['candidate']['concurrency'],4)
    def test_large_model_two_cards_per_shard(self):
        plan=budget_for(dict(gpus=2,replicas=2),3,192)
        self.assertEqual(plan['candidate']['gpus'],2)
        self.assertEqual(plan['candidate']['concurrency'],2)
        self.assertIn('--gpus-per-node=2',array_command('fixture','candidate',plan))
        self.assertEqual(plan['judge']['gpus'],1)
    def test_budget_bounded(self):
        for seconds in [1,3,5]:
            plan=budget_for(dict(gpus=1,replicas=4),seconds,192)
            self.assertLessEqual(plan['maximum_reserved_gpu_hours'],192)
            for stage in ['candidate','judge']:
                self.assertLessEqual(plan[stage]['wall_hours'],6)
                self.assertLessEqual(plan[stage]['shards'],64)
        with self.assertRaises(ValueError):budget_for(dict(gpus=2,replicas=2),10000,960)
    def test_overbudget_examples_are_rejected(self):
        for gpus,replicas,seconds in [(1,4,10),(2,2,20),(1,4,40)]:
            with self.assertRaisesRegex(ValueError,'BUDGET_EXCEEDS|ESTIMATE_TOO_LONG'):
                budget_for(dict(gpus=gpus,replicas=replicas),seconds,960)
    def test_all_24196_inputs_once(self):
        requests=[dict(sample_id=str(i)) for i in range(24196)]
        for count in [2,4,8,16,32,64]:
            self.assertEqual(validate_rows(requests,[requests[i::count] for i in range(count)]),24196)
    def test_missing_duplicate_and_wrong_shard_rejected(self):
        requests=[dict(sample_id=str(i)) for i in range(7)]
        good=[requests[::2],requests[1::2]]
        with self.assertRaises(ValueError):validate_rows(requests,[good[0][:-1],good[1]])
        with self.assertRaises(ValueError):validate_rows(requests,[good[0]+[good[0][0]],good[1]])
        with self.assertRaises(ValueError):validate_rows(requests,[good[1],good[0]])
    def test_no_answer_based_selection(self):
        requests=[dict(sample_id='x')]
        # Missing label is a scored model output, not an engineering failure.
        self.assertEqual(validate_rows(requests,[[dict(sample_id='x',error=None,raw_response='')]]),1)
        with self.assertRaises(ValueError):
            validate_rows(requests,[[dict(sample_id='x',error='CUDA failure')]])
    def test_failure_reaches_cpu_acceptance(self):
        cmd=cpu_command('fixture','handoff','123')
        self.assertIn('--dependency=afterany:123',cmd)
        self.assertNotIn('--gpus-per-node=1',cmd)
        self.assertIn('--partition=general',cmd)
    def test_fixed_science_reused(self):
        text=(EXTENSION/'worker.py').read_text()
        self.assertIn("ORIGINAL/('infer.py'",text)
        self.assertNotIn('from_pretrained',text)
        self.assertNotIn('quantization_config',text)
        self.assertNotIn('model.generate',text)
        self.assertIn("'--num-shards'",text)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('PROTOCOL_MISMATCH')
    if a.dry_run:print('CPU parser/partition/budget tests and immutable code validation; no inference.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    verify()
    sys.path.insert(0,str(REPORTING))
    from report import verify_extension as verify_reporting
    verify_reporting()
    for path in EXTENSION.glob('*.py'):ast.parse(path.read_text())
    subprocess.run(['bash','-n',str(EXTENSION/'job.sh')],check=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SchedulingTests))
    if not result.wasSuccessful():raise SystemExit(1)
    # This extension is being installed before any new full inference exists.
    for key in registry():
        if list((ROOT/key/'full').glob('predictions_*.jsonl')) or (ROOT/key/'full_node_submission.json').exists():
            raise ValueError('FULL_ALREADY_STARTED_DO_NOT_CHANGE_PARTITIONING')
    files=[*sorted(EXTENSION.glob('*.py')),*sorted(EXTENSION.glob('*.sh'))]
    frozen(LOCK,dict(status='PASS',scientific_protocol_sha256=sha(ROOT/'protocol_lock.json'),
                     files={str(p):sha(p) for p in files},model_calls=0,tests=result.testsRun))
    frozen(ROOT/'split_engineering_tests.json',dict(status='PASS',tests=result.testsRun,
                     job=os.environ['SLURM_JOB_ID'],original_science_verified=True,
                     reporting_extension_verified=True,model_calls=0,
                     all_inputs_once=True,missing_labels_retained=True))
    print('SPLIT_SCHEDULING_EXTENSION_PASS',flush=True)

if __name__=='__main__':main()
