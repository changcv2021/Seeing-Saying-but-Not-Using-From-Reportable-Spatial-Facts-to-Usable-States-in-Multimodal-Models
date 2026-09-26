"""Uniform posthoc v3 scoring; immutable v2 engine/scorers and raw-parent exposures."""
import importlib.util
import io
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify
from adapter import VERSION, RULES, normalize, baseline, remaining_failure

spec = importlib.util.spec_from_file_location('sws_v2_rescore_engine', HERE.parent / 'interface_repair_v2/rescore.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
engine.REPAIR = HERE
engine.VERSION, engine.RULES, engine.normalize = VERSION, RULES, normalize
engine.base = lambda root: root / 'rescoring/interface_v3_20260910'
real_spec = lambda batch: dict(batch=batch, scorer='real_score_v1', table='all_physical_request_scores.csv', statistics='primary_statistics.csv', correct='content_correct')
engine.CASES.update({f'D{i:02}': real_spec(f'ca_source_d{i:02}_20260910') for i in range(2, 5)})
engine.CASES.update(E8=real_spec('native_e8_breadth_v1_20260910'),
                    NONCOUNT=real_spec('noncount_breadth_v1_20260910'),
                    MULTIVIEW=real_spec('multiview_breadth_v2_20260910'))


def freeze(c, root):
    import test_adapter
    buf = io.StringIO()
    result = unittest.TextTestRunner(stream=buf, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_adapter))
    save(engine.base(root) / 'tests' / ('tests_' + os.environ['SLURM_JOB_ID'] + '.txt'), buf.getvalue(), 'text')
    if not result.wasSuccessful():
        raise RuntimeError(buf.getvalue())
    code, protected = engine.lock_sources(c, root)
    for name in ('adapter.py', 'rescore.py', 'test_adapter.py', 'job.sh'):
        code.append(entry(HERE.parent / 'interface_repair_v2' / name))
    save(engine.base(root) / 'NORMALIZATION_LOCK.json', dict(
        version=VERSION, created_at=now(), job_id=os.environ['SLURM_JOB_ID'], rules=RULES,
        models=c['models'], cases=list(engine.CASES), code=code, protected_prior_files=protected,
        tests=result.testsRun, status='PASS', raw_mutation=False, gold_mutation=False, prompt_mutation=False,
        model_reruns=0, identical_policy_all_models_all_conditions=True, output_token_cap_unchanged=512,
        canonicalization_inputs=['raw_response_text', 'public_schema'],
        method_status='POSTHOC_INTERFACE_CORRECTION_V3_NOT_ORIGINAL_PREREGISTERED_SCORE',
        scientific_status='AUTO_ONLY_PROVISIONAL', parent_policy='ACTUAL_RAW_PARENTS_UNCHANGED'))
    print(json.dumps(dict(status='V3_FROZEN', tests=result.testsRun, cases=list(engine.CASES))), flush=True)


def compare_v2(c, root, a):
    dest = engine.snapshot(root, a.batch, a.model)
    views = list(rows(dest / 'canonical_views.jsonl'))
    delta = []; failures = Counter()
    for v in views:
        if v['status'] != 'RETURNED':
            continue
        before = baseline.normalize(v['raw_response'], v['schema'])
        after = v['normalization']
        category = remaining_failure(after, v['schema'])
        failures[category] += 1
        delta.append(dict(request_id=v['request_id'], world_cluster_id=v['world_cluster_id'],
            v2_status=before['normalized']['status'], v3_status=after['normalized']['status'],
            v2_component_values=before['normalized']['component_values'], v3_component_values=after['normalized']['component_values'],
            remaining_failure=category, operations=after['operations'], original_raw=v['original_raw']))
    csvsave(dest / 'v2_to_v3_interface_audit.csv', delta)
    save(dest / 'V2_TO_V3_ACCEPTANCE.json', dict(case=a.batch, model=a.model, returned=len(delta),
        v2_invalid=sum(r['v2_status'] == 'INVALID' for r in delta),
        v3_invalid=sum(r['v3_status'] == 'INVALID' for r in delta),
        remaining_failure_counts=dict(failures), raw_parents_unchanged=True,
        substantive_errors_never_repaired=True, audit=entry(dest / 'v2_to_v3_interface_audit.csv')))


def main():
    p = arguments(__doc__)
    p.add_argument('--stage', choices=['freeze', 'canonicalize', 'score', 'summary'], required=True)
    p.add_argument('--batch', choices=list(engine.CASES)); p.add_argument('--model')
    p.add_argument('--cases', nargs='+', default=list(engine.CASES))
    a = p.parse_args(); c, root = setup(a)
    if a.stage == 'freeze':
        freeze(c, root); return
    if a.stage == 'summary':
        records = []
        for case in a.cases:
            for model in c['models']:
                candidates = sorted((engine.base(root) / case / model).glob('snapshot_*/V2_TO_V3_ACCEPTANCE.json'))
                records.append(load(candidates[-1]) if candidates else dict(case=case, model=model, status='NOT_COMPLETED'))
        save(engine.base(root) / ('SUMMARY_' + os.environ['SLURM_JOB_ID'] + '.json'), records)
        print(json.dumps(records), flush=True); return
    if a.model not in c['models']:
        raise ValueError('UNAUTHORIZED_MODEL')
    import importlib
    scoring = importlib.import_module(engine.CASES[a.batch]['scorer'])
    if a.batch != 'E9':
        scoring.BATCH = engine.CASES[a.batch]['batch']
    if a.stage == 'canonicalize':
        engine.canonicalize(c, root, a)
    else:
        engine.score(c, root, a)
        compare_v2(c, root, a)


if __name__ == '__main__':
    main()
