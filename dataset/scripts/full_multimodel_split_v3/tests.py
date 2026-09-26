"""CPU-only engineering validation; zero candidate or judge model calls."""
import argparse, ast, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import orchestration
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

    def test_inference_and_handoff_ignore_missing_scoring_gate(self):
        with patch.object(orchestration,'require_gate',side_effect=ValueError('NO_GATE')) as gate:
            for stage in ['candidate','candidate_continue_0001','handoff','handoff_continue_0001']:
                orchestration.require_stage_gate(stage)
            gate.assert_not_called()
            for stage in ['judge','judge_continue_0001','finish','finish_continue_0001']:
                with self.assertRaises(ValueError):orchestration.require_stage_gate(stage)
    def test_full_inference_budget_without_judge_measurement(self):
        plan=budget_for(dict(gpus=2,replicas=2),6,None)
        self.assertIsNone(plan['judge_smoke_seconds'])
        self.assertIsNone(plan['judge']['estimated_hours'])
        self.assertEqual(plan['judge']['shards'],4)
        self.assertFalse(any(v.startswith('--dependency') for v in array_command('fixture','candidate',plan)))
    def test_scorer_wait_does_not_submit_or_fail_inference(self):
        with tempfile.TemporaryDirectory(prefix='scf_scorer_wait_') as temp:
            root=Path(temp);(root/'fixture').mkdir()
            (root/'fixture/full_candidate_acceptance.json').write_text(json.dumps(dict(status='COMPLETE',n=24196)))
            with patch.object(orchestration,'ROOT',root),patch.object(orchestration,'submit') as submit:
                result=orchestration.maybe_submit_judge('fixture')
                self.assertEqual(result['status'],'WAITING_FOR_SCORER_ONLY_CANDIDATE_UNAFFECTED')
                submit.assert_not_called()
    def test_scorer_block_preserves_other_inference(self):
        with tempfile.TemporaryDirectory(prefix='scf_scorer_block_') as temp:
            root=Path(temp);(root/'fixture').mkdir()
            (root/'fixture/full_candidate_acceptance.json').write_text(json.dumps(dict(status='COMPLETE',n=24196)))
            (root/'SCORING_GATE.json').write_text(json.dumps(dict(status='BLOCKED_JUDGE_INTERFACE')))
            with patch.object(orchestration,'ROOT',root),patch.object(orchestration,'submit') as submit:
                self.assertEqual(orchestration.maybe_submit_judge('fixture')['status'],'SCORING_BLOCKED_CANDIDATE_UNAFFECTED')
                submit.assert_not_called()
    def test_judge_requires_own_predictions(self):
        with tempfile.TemporaryDirectory(prefix='scf_judge_producer_') as temp:
            root=Path(temp);(root/'fixture').mkdir()
            (root/'SCORING_GATE.json').write_text(json.dumps(dict(status='PASS')))
            with patch.object(orchestration,'ROOT',root),patch.object(orchestration,'submit') as submit:
                self.assertEqual(orchestration.maybe_submit_judge('fixture')['status'],'WAITING_FOR_OWN_PREDICTIONS')
                submit.assert_not_called()
    def test_ready_judge_submitted_only_once(self):
        with tempfile.TemporaryDirectory(prefix='scf_judge_once_') as temp:
            root=Path(temp);(root/'fixture').mkdir()
            (root/'fixture/full_candidate_acceptance.json').write_text(json.dumps(dict(status='COMPLETE',n=24196)))
            (root/'fixture/full_split_budget.json').write_text(json.dumps(budget_for(dict(gpus=1,replicas=4),3,None)))
            (root/'SCORING_GATE.json').write_text(json.dumps(dict(status='PASS')))
            with patch.object(orchestration,'ROOT',root),patch.object(orchestration,'submit',side_effect=[dict(job_id='101'),dict(job_id='102')]) as submit:
                self.assertEqual(orchestration.maybe_submit_judge('fixture')['judge_array'],'101')
                self.assertEqual(orchestration.maybe_submit_judge('fixture')['judge_array'],'101')
                self.assertEqual(submit.call_count,2)
    def test_controller_has_no_global_stop_on_7b_failure(self):
        text=(EXTENSION/'controller.py').read_text()
        self.assertNotIn('STOPPED_7B',text)
        self.assertNotIn('WAITING_FOR_7B_SCORING_GATE',text)
        self.assertNotIn('score(SimpleNamespace',text)
        self.assertIn('smoke_readiness',text)

    def test_candidate_dispatch_runs_without_common_gate(self):
        with tempfile.TemporaryDirectory(prefix='scf_independent_candidate_') as temp:
            root=Path(temp);(root/'fixture/split_jobs_v3').mkdir(parents=True)
            (root/'fixture/inference_readiness_v3.json').write_text(json.dumps(dict(status='PASS_ENGINEERING_ONLY')))
            limits=dict(gpu_wall_hours=48,max_array_tasks=1000,source='FIXTURE')
            with patch.object(orchestration,'ROOT',root),patch.object(orchestration,'verify_extension'),patch.object(orchestration,'registry',return_value={'fixture':dict(gpus=1,replicas=4)}),patch.object(orchestration,'read_cluster_limits',return_value=limits),patch.object(orchestration,'require_gate',side_effect=ValueError('NO_GATE')) as gate,patch.object(orchestration,'submit',side_effect=[dict(job_id='201'),dict(job_id='202')]):
                result=orchestration.dispatch('fixture',3,None)
                self.assertEqual(result['candidate_array'],'201')
                self.assertEqual(result['cross_model_dependencies'],[])
                gate.assert_not_called()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run-id',default=RUN_ID)
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('PROTOCOL_MISMATCH')
    if a.dry_run:print('CPU parser/partition/budget tests and immutable code validation; no inference.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    verify()
    old_lock=json.loads((ROOT/'split_scheduling_v2_lock.json').read_text())
    for filename,digest in old_lock['files'].items():
        if sha(filename)!=digest:raise ValueError('HISTORICAL_V2_CHANGED')
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
    frozen(ROOT/'split_v3_engineering_tests.json',dict(status='PASS',tests=result.testsRun,
                     job=os.environ['SLURM_JOB_ID'],original_science_verified=True,
                     reporting_extension_verified=True,model_calls=0,
                     all_inputs_once=True,missing_labels_retained=True,
                     live_cluster_limits=read_cluster_limits(),cumulative_gpu_hour_cap=None,
                     safe_checkpoint_tested=True,completed_responses_not_regenerated=True))
    print('SPLIT_V3_DECOUPLED_INFERENCE_AND_SCORING_PASS',flush=True)

if __name__=='__main__':main()
