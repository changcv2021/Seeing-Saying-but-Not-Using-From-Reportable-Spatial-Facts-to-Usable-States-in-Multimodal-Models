"""Additive exposure experiment; frozen v4 engineering is reused, never edited."""
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4 = HERE.parent / 'formal_training_v4'
spec = importlib.util.spec_from_file_location('preserved_legacy_plan', V4 / 'plan.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
ROOT, ENGINE, LEGACY = old.ROOT, old.ENGINE, old.LEGACY
OLD_OUTPUT = ROOT / 'formal_training_v4'
OUTPUT = ROOT / 'pss_full_l4_preserved_v1'
METHOD = 'pss_full_l4_preserved'
METHODS, SEEDS = (METHOD,), old.SEEDS
DEFAULTS = dict(old.DEFAULTS)
read, sha, digest = old.read, old.sha, old.digest
validate_plan, rank_indices = old.validate_plan, old.rank_indices
ExampleSchedule = old.ExampleSchedule
PYTHON = 'python'
EXCLUDE = 'nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698'
RUN_ID = 'pss_full_l4_preserved_v1_20260923'


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write('\n')


def rows(path):
    with Path(path).open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def seed_output(seed):
    if seed not in SEEDS:
        raise ValueError('FROZEN_SEED')
    return OUTPUT / ('seed_' + str(seed))


def interleave(base_units, additions, batch=16):
    """Keep every old unit/weight and every old batch; insert complete new batches.

    Pad ONLY the extra stream with its own earliest frozen units, never remove
    or add an L4 unit to complete a batch. No test/model outcomes are consulted.
    """
    if not base_units or len(base_units) % batch or not additions:
        raise ValueError('BASE_BATCH_OR_EMPTY_ALIGNMENT')
    extra = [dict(unit) for unit in additions]
    padding = (-len(extra)) % batch
    for i in range(padding):
        extra.append(dict(additions[i % len(additions)], batch_padding_duplicate=True))
    b, a = len(base_units) // batch, len(extra) // batch
    result = []
    for i in range(b):
        result.extend(base_units[i * batch:(i + 1) * batch])
        start, end = i * a // b, (i + 1) * a // b
        result.extend(extra[start * batch:end * batch])
    if [u for u in result if u['stream'] == 'preserved_l4'] != base_units:
        raise ValueError('BASE_SUBSEQUENCE_NOT_EXACT')
    return result, padding


def code_hashes():
    paths = set(HERE.glob('*.py')) | set(HERE.glob('*.sbatch'))
    paths |= {Path(p) for p in old.code_hashes()}
    paths |= set((HERE.parent / 'heldout_test_v1').glob('*.py'))
    paths |= set((HERE.parent / 'label_rescore_v2').glob('*.py'))
    repo = HERE.parents[1] / 'SpaceConflict'
    paths |= {repo / 'scripts/full_multimodel_split_v5/gpu_health.py'}
    return {str(p): sha(p) for p in sorted(paths)}
