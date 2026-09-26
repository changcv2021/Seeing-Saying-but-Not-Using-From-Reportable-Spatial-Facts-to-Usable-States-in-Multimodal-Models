"""CPU-only checks for the functional layout; no model/data generation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LayoutTests(unittest.TestCase):
    def test_functional_roots(self):
        for name in ('dataset', 'training', 'evaluation', 'experiments', 'docs', 'results'):
            self.assertTrue((ROOT/name).is_dir(), name)
        for name in ('SpaceConflict', 'phase4', 'phase5', 'phase6', 'phase7', 'phase8'):
            self.assertFalse((ROOT/name).exists(), name)

    def test_user_exclusions(self):
        for name in ('results/sft/predictions', 'results/sft/scored',
                     'artifacts/model_results/sequential_state_mechanism', 'auth'):
            self.assertFalse((ROOT/name).exists(), name)

    def test_import_routes(self):
        cases = {
            'evaluation/score.py': {'ROOT': '.'},
            'tools/score.py': {'ROOT': '.'},
            'evaluation/label_rescore_v2/config.py': {'SPACE': '.', 'LEGACY': 'dataset/scripts/full_multimodel_20260908_v1'},
            'evaluation/heldout_test_v1/settings.py': {'SPACE': '.', 'REPO': 'dataset'},
            'evaluation/heldout_test_full_pss_v1/full_common.py': {'PREVIOUS_CODE': 'evaluation/heldout_test_v1'},
            'training/formal_training_v4/plan.py': {'ENGINE': 'training/execution_pss_v2', 'LEGACY': 'training/formal_training_v3'},
            'training/pss_full_l4_preserved_v1/plan.py': {'V4': 'training/formal_training_v4'},
            'training/pss_full_l4_preserved_v1/evaluate.py': {'TEST_CODE': 'evaluation/heldout_test_v1', 'LABEL_CODE': 'evaluation/label_rescore_v2', 'REPO': 'dataset'},
            'experiments/behavioral_closure/execution_bc_v1/bc_common.py': {'SWS_CODE': 'experiments/spatial_world_state/execution_sws_v1'},
            'experiments/sequential_state/execution_ssm_v1/ssm_common.py': {'SWS_CODE': 'experiments/spatial_world_state/execution_sws_v1'},
            'experiments/sequential_state/execution_ssm_internal_v1/internal_common.py': {'SWS_CODE': 'experiments/spatial_world_state/execution_sws_v1'},
            'experiments/sequential_state/execution_ssm_i2_v1/common_i2.py': {'SWS_CODE': 'experiments/spatial_world_state/execution_sws_v1'},
            'experiments/state_interventions/execution_ssm_v2/v2_common.py': {'SPACE': '.', 'OLD_CODE': 'experiments/sequential_state/execution_ssm_v1'},
        }
        code = ('import json,runpy,sys; from pathlib import Path; '
                'p=Path(sys.argv[1]).resolve(); root=Path.cwd(); '
                'sys.path.insert(0,str(p.parent)); ns=runpy.run_path(str(p)); '
                'expected=json.loads(sys.argv[2]); '
                'assert all(Path(ns[k]).resolve()==(root/v).resolve() and Path(ns[k]).is_dir() for k,v in expected.items()), expected')
        for name, expected in cases.items():
            with self.subTest(module=name):
                result = subprocess.run([sys.executable, '-c', code, str(ROOT/name), json.dumps(expected)],
                    cwd=ROOT, text=True, capture_output=True, timeout=30,
                    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_configuration_routes(self):
        for name in ('config.json', 'config_auto_v2.json'):
            config=json.loads((ROOT/'experiments/spatial_world_state/execution_sws_v1'/name).read_text())
            self.assertEqual((ROOT/config['project']).resolve(), ROOT/'dataset')
            self.assertTrue((ROOT/config['package']).is_dir())

    def test_preserved_code_freeze_includes_evaluation(self):
        code = ('import sys; from pathlib import Path; '
                'sys.path.insert(0,"training/pss_full_l4_preserved_v1"); import plan; '
                'paths=plan.code_hashes(); '
                'assert any("/evaluation/heldout_test_v1/" in p for p in paths); '
                'assert any("/evaluation/label_rescore_v2/" in p for p in paths); '
                'assert all(Path(p).is_file() for p in paths)')
        p = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True, capture_output=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)

if __name__ == '__main__':
    unittest.main()
