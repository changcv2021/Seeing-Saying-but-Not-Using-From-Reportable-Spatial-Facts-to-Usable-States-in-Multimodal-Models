"""Versioned post-hoc, gold-independent label scoring correction."""
import argparse
import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
SPACE = CODE.parent.parent
LEGACY = SPACE / 'dataset/scripts/full_multimodel_20260908_v1'
sys.path.insert(0, str(LEGACY))
from common import load, unique, sha, write, metrics

PSS = Path('artifacts/model_results/pss_20260922_v1/approved_v2')
ROOT = PSS / 'label_rescore_v2'
TEN = PSS / 'heldout_test_full_pss_v1/TEN_MODEL_SUMMARY.json'
BASE = PSS.parent.parent / 'full_multimodel_20260908_v1/qwen35_9b'
RUN_ID = 'phase8_label_rescore_v2_20260923'
SEED = 20260923
METHODS = ('answer_natural', 'answer_balanced', 'cot_partial', 'pss_l4', 'pss_full')
KEYS = ('base_qwen35_9b',) + tuple(f'{m}__seed_{s}' for m in METHODS for s in (20260922, 20260923))


def read(path):
    return json.loads(Path(path).read_text())


def parser(description):
    p = argparse.ArgumentParser(description)
    p.add_argument('stage', choices=('prepare', 'score', 'summary'))
    p.add_argument('--index', type=int)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=SEED)
    p.add_argument('--limit', type=int)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    return p


def verify():
    seal = read(ROOT / 'FREEZE.json')
    if sha(ROOT / 'MANIFEST.json') != seal['manifest_sha256']:
        raise ValueError('MANIFEST_CHANGED')
    manifest = read(ROOT / 'MANIFEST.json')
    for path, digest in manifest['code_hashes'].items():
        if sha(path) != digest:
            raise ValueError('FROZEN_SCORER_CHANGED:' + path)
    return manifest
