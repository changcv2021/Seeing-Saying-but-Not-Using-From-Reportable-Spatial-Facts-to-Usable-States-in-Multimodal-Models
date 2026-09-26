"""CPU-only engineering validation; zero candidate or judge model calls."""
import argparse, ast, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from orchestration import (EXTENSION, ORIGINAL, REPORTING, ROOT, RUN_ID, SEED, LOCK,
                           budget_for, validate_rows, array_command, cpu_command,
                           registry, verify, frozen, sha, time_resume_allowed,
                           preserve_complete_prefix, read_cluster_limits)

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
    def test_only_site_per_job_limit(self):
        for seconds in [1,3,5,40,300,3000]:
            plan=budget_for(dict(gpus=1,replicas=4),seconds,192)
            self.assertIsNone(plan['cumulative_gpu_hour_cap'])
            self.assertIsNone(plan['artificial_shard_cap'])
            for stage in ['candidate','judge']:
                self.assertEqual(plan[stage]['wall_hours'],48)
                self.assertLessEqual(plan[stage]['shards'],1000)
    def test_previous_overbudget_examples_now_accepted(self):
        for gpus,replicas,seconds in [(1,4,10),(2,2,20),(1,4,40)]:
            plan=budget_for(dict(gpus=gpus,replicas=replicas),seconds,960)
            self.assertGreater(plan['maximum_reserved_gpu_hours'],192)
    def test_very_slow_measurement_never_refused_for_time(self):
        plan=budget_for(dict(gpus=2,replicas=2),10000,960)
        self.assertGreater(plan['candidate']['shards'],64)
        self.assertTrue(plan['candidate']['estimated_continuation_needed'])
    def test_all_24196_inputs_once(self):
        requests=[dict(sample_id=str(i)) for i in range(24196)]
        for count in [2,4,8,16,32,64,128,1000]:
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
        text=(EXTENSION/'checkpoint_worker.py').read_text()
        self.assertIn("ORIGINAL/('infer.py'",text)
        self.assertNotIn('from_pretrained',text)
        self.assertNotIn('quantization_config',text)
        self.assertNotIn('model.generate',text)
        self.assertIn("'--num-shards'",text)
    def test_only_time_related_continuation(self):
        self.assertTrue(time_resume_allowed('TIMEOUT',{},'123'))
        checkpoint=dict(status='CHECKPOINTED',array_job_id='123')
        self.assertTrue(time_resume_allowed('COMPLETED',checkpoint,'123'))
        for state in ['FAILED','OUT_OF_MEMORY','CANCELLED','NODE_FAIL']:
            self.assertFalse(time_resume_allowed(state,checkpoint,'123'))
        self.assertFalse(time_resume_allowed('COMPLETED',checkpoint,'456'))
    def test_truncated_tail_preserved_not_guessed(self):
        with tempfile.TemporaryDirectory(prefix='spaceconflict_checkpoint_test_') as temp:
            path=Path(temp)/'predictions_000.jsonl'
            original=b'{"sample_id":"x","error":null}\n{"sample_'
            path.write_bytes(original)
            self.assertEqual(preserve_complete_prefix(path,['x','y'],'123'),1)
            self.assertEqual(json.loads(path.read_bytes())['sample_id'],'x')
            self.assertEqual((Path(temp)/'timeout_archives/123/predictions_000.jsonl').read_bytes(),original)
    def test_committed_rows_not_repaired_or_reordered(self):
        with tempfile.TemporaryDirectory(prefix='spaceconflict_checkpoint_test_') as temp:
            path=Path(temp)/'predictions_000.jsonl';original=b'{"sample_id":"x","error":null}\n'
            path.write_bytes(original)
            self.assertEqual(preserve_complete_prefix(path,['x','y'],'123'),1)
            self.assertEqual(path.read_bytes(),original)
            self.assertFalse((Path(temp)/'timeout_archives').exists())
            with self.assertRaises(ValueError):preserve_complete_prefix(path,['y','x'],'123')
    def test_checkpoint_signal_after_durable_response_cpu_fixture(self):
        with tempfile.TemporaryDirectory(prefix='spaceconflict_signal_fixture_') as temp:
            folder=Path(temp);(folder/'fixture/full').mkdir(parents=True)
            output=folder/'fixture/full/predictions_000.jsonl'
            fake=folder/'infer.py'
            fake.write_text('import os,signal,json\n'
                'os.kill(os.getpid(),signal.SIGUSR1)\n'
                f'with open({str(output)!r},"w") as stream:\n'
                '    stream.write(json.dumps({"sample_id":"fixture","error":None})+"\\n")\n'
                '    stream.flush();os.fsync(stream.fileno())\n'
                'print(json.dumps({"model":"fixture","completed":1}),flush=True)\n'
                'raise RuntimeError("must checkpoint before next request")\n')
            script=('import sys;from pathlib import Path;import checkpoint_worker as c;'
                f'c.ORIGINAL=Path({str(folder)!r});c.ROOT=c.ORIGINAL;'
                'c.registry=lambda:{"fixture":{"run_id":"fixture"}};'
                'sys.argv=["fixture","candidate","--model","fixture","--num-shards","1","--shard-index","0"];c.main()')
            result=subprocess.run([sys.executable,'-c',script],env=dict(os.environ,SLURM_JOB_ID='fixture'),
                                  cwd=EXTENSION,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,77,result.stderr)
            self.assertEqual(json.loads(output.read_text())['sample_id'],'fixture')
            self.assertTrue((folder/'fixture/full/checkpoint_fixture_000.json').is_file())
    def test_slurm_signal_and_no_internal_elapsed_kill(self):
        plan=budget_for(dict(gpus=1,replicas=4),3,192)
        self.assertIn('--signal=B:USR1@600',array_command('fixture','candidate',plan))
        self.assertIn('--time=48:00:00',array_command('fixture','candidate',plan))
        self.assertNotIn("raise RuntimeError('NO_PROGRESS_TIMEOUT')",(EXTENSION/'worker.py').read_text())

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
    frozen(ROOT/'split_v2_engineering_tests.json',dict(status='PASS',tests=result.testsRun,
                     job=os.environ['SLURM_JOB_ID'],original_science_verified=True,
                     reporting_extension_verified=True,model_calls=0,
                     all_inputs_once=True,missing_labels_retained=True,
                     live_cluster_limits=read_cluster_limits(),cumulative_gpu_hour_cap=None,
                     safe_checkpoint_tested=True,completed_responses_not_regenerated=True))
    print('SPLIT_V2_SITE_LIMIT_ONLY_AND_CHECKPOINT_PASS',flush=True)

if __name__=='__main__':main()
