"""Small common paths and versioned data access; never import test data here."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_CODE = HERE.parent/'execution_pss_v2'
sys.path.insert(0, str(ENGINE_CODE))
from common import ROOT, REPO, MODEL, PYTHON, read, rows, sha, write, atomic, compute

OUTPUT = ROOT/'formal_training_v1'
PREPARED = OUTPUT/'prepared_v1'
RESOURCE_CODE = HERE.parent/'formal_resources_v1'


def sources():
    return [('answer', ROOT/'supervision_v3/train/answer.jsonl'),
            ('cot', ROOT/'partial_cot_approved_v1/train/cot.jsonl'),
            ('state', ROOT/'grounded_state_v4/train/state.jsonl'),
            ('state', ROOT/'trajectory_aux_v1/train/state.jsonl')]


def catalog():
    return {r['key']: r for r in rows(PREPARED/'catalog.jsonl')}


def load_records(meta, keys=None):
    """Validate frozen source hashes, then load requested records by source line."""
    manifest = read(PREPARED/'BUDGET_PLAN.json')
    selected = set(meta) if keys is None else set(keys)
    wanted = {}
    for key in selected:
        m = meta[key]; wanted.setdefault(m['source'], {})[m['line']] = key
    result = {}
    for path, indices in wanted.items():
        if sha(path) != manifest['source_hashes'][path]:
            raise ValueError('TRAIN_SOURCE_CHANGED:' + path)
        for index, row in enumerate(rows(path)):
            if index in indices:
                result[indices[index]] = row
    if set(result) != selected:
        raise ValueError('MISSING_TRAIN_RECORDS')
    return result
