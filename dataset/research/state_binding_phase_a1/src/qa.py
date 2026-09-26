"""Pre-inference engineering checks, no real-world responses or new predictions."""
import ast
import subprocess
from common import *
from scorer import selftest,score

def main():
    a=arguments(__doc__).parse_args(); cfg,root=setup(a)
    if a.dry_run: print('PLANNED: syntax, scorer, setup gold, snapshots and model metadata checks'); return
    require_compute(); tests=selftest(); sourcechecks=[]
    for p in sorted((CODE/'src').glob('*.py')):
        ast.parse(p.read_text(),filename=str(p)); sourcechecks.append(entry(p))
    lock=load(root/'manifest/setup_v1_lock.json')
    for e in lock['code']:
        if sha(e['path'])!=e['sha256']: raise ValueError('FROZEN_SETUP_CODE_CHANGED')
    inp=list(rows(root/'inputs/setup_v1/requests.jsonl')); gold={r['request_id']:r for r in rows(root/'gold/setup_v1.jsonl')}
    if len(inp)!=len(gold): raise ValueError('SETUP_INPUT_GOLD_SIZE')
    for r in inp:
        g=gold[r['request_id']]; expected=g['expected']; kind=g['schema']['kind']
        obj={'value':expected} if kind=='value' else {'label':expected} if kind=='verdict' else expected
        if not score({'raw_response':json.dumps(obj)},g)['correct']: raise ValueError('ORACLE_SCORER_ROUNDTRIP')
        if r['payload']['media'] or r['level']!='SETUP_ONLY': raise ValueError('REAL_WORLD_IN_SETUP')
    mismatches=[]
    baseline=list(rows(root/'manifest/phase_a_files_before.jsonl'))
    for e in baseline:
        if not Path(e['path']).is_file() or sha(e['path'])!=e['sha256']: mismatches.append(e['path'])
    save(root/'phase_a_preservation_check.json',dict(status='PASS' if not mismatches else 'FAIL',baseline_files=len(baseline),
        compared_files=len(baseline),changed_files=mismatches,baseline_sha256=sha(root/'manifest/phase_a_files_before.jsonl'),
        phase_a_scorer_unchanged=True,phase_a_not_rescored=True,scope='ALL_PHASE_A_RUN_FILES_AND_NON_PYCACHE_CODE_PLUS_REQUESTED_CSV',
        checked_at_utc=__import__('time').strftime('%Y-%m-%dT%H:%M:%SZ',__import__('time').gmtime())))
    if mismatches: raise ValueError('PHASE_A_PRESERVATION_FAILED')
    models=[]
    for mc in load(Path(cfg['campaign'])/'config.json')['models']:
        if mc['key'] not in cfg['models']: continue
        modeldir=Path(mc['model_path']); manifest=load(mc['manifest_path'])
        if (manifest['model_id'],manifest['revision'])!=(mc['model'],mc['revision']): raise ValueError('MODEL_MANIFEST_MISMATCH')
        idx=load(modeldir/'model.safetensors.index.json')
        shards=sorted(set(idx['weight_map'].values()))
        if not all((modeldir/s).is_file() for s in shards): raise ValueError('MISSING_MODEL_SHARDS')
        models.append(dict(key=mc['key'],revision=mc['revision'],shards=len(shards),all_present=True,
            manifest_sha256=sha(mc['manifest_path']),weight_shards_rehashed=False,weight_integrity_scope='EXISTENCE_AND_PREVIOUSLY_FROZEN_REVISION_MANIFEST'))
    save(root/'reports/engineering_acceptance.json',dict(status='PASS',scorer_tests=tests,setup_oracle_roundtrip=len(inp),
        source_syntax_files=sourcechecks,models=models,preservation='PASS',
        actual_gpu_calibration_still_required=True,no_real_predictions_inspected=True),frozen=True)
    print(json.dumps(dict(status='PASS',scorer_tests=tests,setup_roundtrip=len(inp),preserved_files=len(baseline))))

if __name__=='__main__': main()
