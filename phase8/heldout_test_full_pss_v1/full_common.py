"""Read-only reuse of the frozen eight-model evaluation implementation."""
import argparse
import json
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
PREVIOUS_CODE = CODE.parent / 'heldout_test_v1'
sys.path.insert(0, str(PREVIOUS_CODE))
import settings as previous

PSS = previous.PSS
ROOT = PSS / 'heldout_test_full_pss_v1'
EIGHT_ROOT = previous.ROOT
RUN_ID = 'phase8_full_pss_test_v1_20260923'
SEEDS = (20260922, 20260923)
TRAINING_JOBS = {20260922: '8313002_8', 20260923: '8313002_9'}
read, write, sha = previous.read, previous.write, previous.sha


def parser(description):
    p = argparse.ArgumentParser(description)
    p.add_argument('--run-id', default=RUN_ID)
    p.add_argument('--seed', type=int, default=previous.DECODE_SEED)
    p.add_argument('--limit', type=int)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    return p


def validate(args):
    if (args.run_id, args.seed, args.limit) != (RUN_ID, 20260904, None):
        raise ValueError('UNCHANGED_COMPLETE_HELDOUT_TEST_REQUIRED')


def key(seed):
    if seed not in SEEDS:
        raise ValueError('UNDECLARED_TRAINING_SEED')
    return f'pss_full__seed_{seed}'


def configure_seed(seed):
    """Only in-process run identity/paths change. No old files are edited."""
    previous.ROOT = ROOT / f'seed_{seed}'
    previous.RUN_ID = RUN_ID + f'_seed_{seed}'
    previous.METHODS = ('pss_full',)
    previous.TRAIN_SEEDS = (seed,)
    previous.KEYS = (key(seed),)
    return previous


def verify_extension():
    seal = read(ROOT / 'EXTENSION_FREEZE.json')
    for path, digest in seal['files'].items():
        if sha(path) != digest:
            raise ValueError('EXTENSION_OR_PREVIOUS_PROTOCOL_CHANGED:' + path)
    return seal
