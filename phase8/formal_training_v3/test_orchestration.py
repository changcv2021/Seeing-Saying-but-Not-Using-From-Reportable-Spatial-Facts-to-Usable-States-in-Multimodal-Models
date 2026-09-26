import ast
import json
from pathlib import Path
import signal
import tempfile
import unittest

from paths import HERE, PREPARED, RESOURCE_CODE, read
from checkpoint import StopAtBoundary, latest_checkpoint, atomic_json, file_sha
from continuation import continuation_command
from core import METHODS, SEEDS


class Orchestration(unittest.TestCase):
    def test_python_syntax(self):
        for p in HERE.glob('*.py'): ast.parse(p.read_text(),filename=str(p))

    def test_continuation_is_only_one_element(self):
        for index in range(10):
            c=continuation_command(index)
            self.assertIn('--array='+str(index),c)
            self.assertFalse(any('dependency' in x or '%' in x for x in c))
        for bad in (-1,10,'0',True):
            with self.assertRaises(ValueError): continuation_command(bad)

    def test_signal_waits_for_boundary(self):
        flag=StopAtBoundary();self.assertFalse(flag.requested)
        flag.handle(signal.SIGUSR1,None)
        self.assertTrue(flag.requested);self.assertEqual(flag.signal,signal.SIGUSR1)

    def test_frozen_equal_budgets(self):
        budget=read(PREPARED/'BUDGET_PLAN.json')
        self.assertEqual(len(budget['runs']),10)
        self.assertEqual({r['optimizer_updates'] for r in budget['runs'].values()},{2237})
        self.assertEqual({r['supervised_tokens'] for r in budget['runs'].values()},{2290688})
        for r in budget['runs'].values():
            self.assertEqual(r['unique_original_samples'],13476)
            self.assertEqual(r['optimizer_updates']*r['tokens_per_update'],r['supervised_tokens'])

    def test_fixed_final_checkpoint_no_test_tuning(self):
        budget=read(PREPARED/'BUDGET_PLAN.json')
        self.assertIn('Fixed final budget',budget['final_checkpoint_policy'])
        self.assertFalse(budget['test_opened'])
        self.assertIn('total_processed_tokens',budget['not_matched'])

    def test_matching_config_and_budget(self):
        budget=read(PREPARED/'BUDGET_PLAN.json')
        for method in METHODS:
            for seed in SEEDS:
                name=f'{method}__seed_{seed}'
                c=read(RESOURCE_CODE/'configs'/(name+'.json'));b=budget['runs'][name]
                for k in ('optimizer_updates','supervised_tokens','method','seed'):self.assertEqual(c[k],b[k])

    def test_allocation_exit_not_general_retry(self):
        text=(RESOURCE_CODE/'train_array.sbatch').read_text()
        self.assertIn('"$status" -eq 75',text)
        self.assertIn('--signal=USR1@1800',text)
        self.assertIn('exit "$status"',text)
        self.assertNotIn('#SBATCH --dependency',text)

    def test_sigterm_does_not_authorize_autoretry(self):
        source=(HERE/'trainer.py').read_text()
        self.assertIn('stopper.signal == signal.SIGTERM',source)
        self.assertIn('return 143',source)
        self.assertIn('TERMINATED_NO_AUTORETRY',source)

    def commit_stub(self, root, step):
        p=root/f'step_{step:07d}';p.mkdir()
        atomic_json(p/'payload.json',dict(step=step))
        atomic_json(p/'COMMITTED.json',dict(step=step,fingerprint='fixed',hashes={'payload.json':file_sha(p/'payload.json')}))
        return p

    def test_orphan_committed_checkpoint_is_recovered(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);self.commit_stub(root,1);latest=self.commit_stub(root,2)
            atomic_json(root/'LATEST.json',dict(name='step_0000001',step=1,fingerprint='fixed'))
            (root/'step_0000003.incomplete.example').mkdir()
            self.assertEqual(latest_checkpoint(root,'fixed'),latest)

    def test_committed_checkpoint_without_pointer(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);latest=self.commit_stub(root,2)
            self.assertEqual(latest_checkpoint(root,'fixed'),latest)

    def test_corrupt_or_changed_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=self.commit_stub(root,2)
            with self.assertRaises(ValueError):latest_checkpoint(root,'other-config')
            atomic_json(p/'payload.json',dict(step=999))
            with self.assertRaises(ValueError):latest_checkpoint(root,'fixed')


if __name__=='__main__': unittest.main()

