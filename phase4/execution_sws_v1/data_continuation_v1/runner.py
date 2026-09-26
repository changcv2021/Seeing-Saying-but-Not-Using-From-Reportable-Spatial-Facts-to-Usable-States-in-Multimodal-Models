"""Bind the existing processor/inference/scorers to a NEW locked batch only."""
import importlib
import re
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *


def main():
    p = arguments(__doc__)
    p.add_argument('--stage', required=True, choices=['processor', 'infer', 'freeze_score', 'canonicalize', 'score'])
    p.add_argument('--batch', required=True); p.add_argument('--model'); p.add_argument('--shard', type=int)
    a = p.parse_args(); c, root = setup(a)
    if not re.fullmatch(r'ca_source_d(?:0[2-9]|[1-9][0-9])_20260910', a.batch): raise ValueError('NEW_BATCH_ONLY')
    lock = load(root / 'batches' / a.batch / 'manifest/REQUEST_LOCK.json')
    from real_processor_v1 import verify
    verify(lock['code'] + lock['public_inputs'])
    if a.dry_run: print(json.dumps(dict(batch=a.batch, stage=a.stage, model=a.model))); return
    import real_design_v1
    real_design_v1.BATCH = a.batch
    if a.stage in ('processor', 'infer'):
        module = importlib.import_module('real_processor_v1' if a.stage == 'processor' else 'real_worker_v1')
        module.BATCH = a.batch
        sys.argv = [module.__name__, '--config', str(a.config), '--run-id', a.run_id, '--seed', str(a.seed), '--resume', '--model', a.model]
        if a.stage == 'infer' and a.shard is not None: sys.argv += ['--shard', str(a.shard)]
        module.main(); return
    sys.path.insert(0, str(HERE.parent / 'interface_repair_v2'))
    import rescore
    rescore.CASES = {a.batch: dict(batch=a.batch, scorer='real_score_v1', table='all_physical_request_scores.csv',
        statistics='primary_statistics.csv', correct='content_correct')}
    rescore.base = lambda r: r / 'rescoring' / 'data_continuation_interface_v2' / a.batch
    import real_score_v1
    real_score_v1.BATCH = a.batch
    if a.stage == 'freeze_score': rescore.freeze(c, root)
    elif a.stage == 'canonicalize': rescore.canonicalize(c, root, a)
    else: rescore.score(c, root, a)


if __name__ == '__main__': main()
