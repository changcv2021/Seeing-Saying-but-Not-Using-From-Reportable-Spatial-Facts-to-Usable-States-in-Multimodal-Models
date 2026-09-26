import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import verify

HERE = Path(__file__).resolve().parent


class LaunchRepair(unittest.TestCase):
    def test_frozen_runtime_and_override(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(verify.verify()['status'], 'FROZEN_LAUNCH_ONLY_OVERRIDE')

    def test_receipt_is_idempotent_for_continuation(self):
        original_read = verify.read
        runtime = original_read(verify.OUTPUT/'TRAINING_RUNTIME.json')
        runtime_sha = verify.sha(verify.OUTPUT/'TRAINING_RUNTIME.json')
        original_sha = verify.sha
        def read(path):
            return runtime if Path(path).name == 'TRAINING_RUNTIME.json' else original_read(path)
        def sha(path):
            return runtime_sha if Path(path).name == 'TRAINING_RUNTIME.json' else original_sha(path)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(verify, 'OUTPUT', Path(tmp)), patch.object(verify, 'read', read), patch.object(verify, 'sha', sha):
                with patch.dict('os.environ', {'SLURM_JOB_ID':'unit_test_only','SLURM_ARRAY_TASK_ID':'0'}, clear=True):
                    verify.verify(); verify.verify()
            self.assertEqual(len(list(Path(tmp,'launch_receipts').glob('*.json'))), 1)

    def test_explicit_affinity_and_no_serialization(self):
        s=(HERE/'train_array.sbatch').read_text()
        self.assertIn('srun --cpu-bind=none',s)
        self.assertIn('#SBATCH --array=0-9\n',s)
        self.assertNotIn('#SBATCH --dependency',s)
        self.assertNotIn('--exclusive',s)
        self.assertIn('"$status" -eq 75',s)

    def test_continuation_keeps_correct_launcher_and_boundary_guards(self):
        p=HERE/'continuation.py';s=p.read_text();ast.parse(s)
        self.assertIn("str(LAUNCH/'train_array.sbatch')",s)
        self.assertIn("'--array='+str(args.index)",s)
        self.assertIn('NO_VALID_BOUNDARY_CHECKPOINT',s)
        self.assertIn('DO_NOT_RESUBMIT_COMPLETED_RUN',s)


if __name__ == '__main__': unittest.main()
