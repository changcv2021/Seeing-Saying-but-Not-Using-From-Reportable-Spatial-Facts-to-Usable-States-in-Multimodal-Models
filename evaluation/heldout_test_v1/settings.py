"""Eight fixed-final-step adapters; no test-dependent selection."""
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
SPACE = CODE.parent.parent
REPO = SPACE / 'dataset'
ORIGINAL = REPO / 'scripts/full_multimodel_20260908_v1'
EXTENSION = REPO / 'scripts/full_multimodel_split_v5'
BASE = Path('artifacts/model_results')
PSS = BASE / 'pss_20260922_v1/approved_v2'
TRAIN = PSS / 'formal_training_v4'
ROOT = PSS / 'heldout_test_v1'
OLD = BASE / 'full_multimodel_20260908_v1/qwen35_9b'
RUN_ID = 'phase8_heldout_test_v1_20260923'
DECODE_SEED = 20260904  # Same greedy inference protocol as the base model.
METHODS = ('answer_natural', 'answer_balanced', 'cot_partial', 'pss_l4')
TRAIN_SEEDS = (20260922, 20260923)
KEYS = tuple(f'{m}__seed_{s}' for m in METHODS for s in TRAIN_SEEDS)
SHARDS = 4
N_TEST = 5608
PYTHON = 'python'
EXCLUDE = 'nid0642,nid0653,nid0661,nid0674,nid0684,nid0685,nid0687,nid0688,nid0694,nid0698'
sys.path[:0] = [str(ORIGINAL), str(EXTENSION), str(REPO / 'src')]
from common import load, unique, sha, write, metrics
import json


def read(path):
    return json.loads(Path(path).read_text())


def arguments(description):
    import argparse
    p = argparse.ArgumentParser(description)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=DECODE_SEED)
    p.add_argument('--limit', type=int)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    return p


def validate(args):
    if (args.run_id, args.seed, args.limit) != (RUN_ID, DECODE_SEED, None):
        raise ValueError('FROZEN_FULL_TEST_ONLY')


def verify_plan():
    seal = read(ROOT / 'FREEZE.json')
    if sha(ROOT / 'PLAN.json') != seal['plan_sha256']:
        raise ValueError('PLAN_CHANGED')
    plan = read(ROOT / 'PLAN.json')
    for path, digest in plan['code_hashes'].items():
        if sha(path) != digest:
            raise ValueError('CODE_CHANGED:' + path)
    return plan


def verify_model(key, plan):
    cfg_path = ROOT / key / 'config.json'
    if sha(cfg_path) != plan['configs'][key]:
        raise ValueError('CONFIG_CHANGED')
    cfg = read(cfg_path)
    for path, digest in cfg['adapter_provenance']['files'].items():
        if sha(path) != digest:
            raise ValueError('FINAL_ADAPTER_CHANGED:' + path)
    if sha(Path(cfg['model_path']) / 'config.json') != cfg['base_config_sha256']:
        raise ValueError('BASE_CONFIG_CHANGED')
    return cfg
