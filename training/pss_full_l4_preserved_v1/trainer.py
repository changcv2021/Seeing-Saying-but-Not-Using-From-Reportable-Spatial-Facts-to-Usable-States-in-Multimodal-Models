"""Reuse the unchanged v4 DDP trainer with an explicit additive dataset."""
import importlib.util
import sys
from plan import *

# Import our data class before old checkpoint.py adds the v3 directory to sys.path.
import data
sys.path.insert(1, str(V4))
spec = importlib.util.spec_from_file_location('preserved_legacy_trainer', V4 / 'trainer.py')
legacy_trainer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy_trainer)


def check_plan(output):
    p = legacy_trainer_check(output)
    for name, expected in p['additive_artifacts'].items():
        if sha(Path(output) / name) != expected:
            raise ValueError('FROZEN_ADDITIVE_DATA_CHANGED:' + name)
    return p


legacy_trainer_check = legacy_trainer.check_plan
legacy_trainer.check_plan = check_plan


if __name__ == '__main__':
    raise SystemExit(legacy_trainer.main())
