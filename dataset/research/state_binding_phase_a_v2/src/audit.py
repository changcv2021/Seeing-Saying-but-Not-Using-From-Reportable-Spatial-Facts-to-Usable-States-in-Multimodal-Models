"""A0: read-only historical score replay and protected input inventory."""
import collections
import importlib.util
import subprocess
import sys
from base import *

def main():
    a = args(__doc__).parse_args(); cfg, root, project = setup(a)
    if a.dry_run:
        print(json.dumps(dict(status='PLANNED', action='audit', root=str(root)))); return
    hist = Path(cfg['historical']); campaign = Path(cfg['campaign'])
    tests = []
    for label, directory, command in [
        ('provided_reference_metrics', CODE/'reference/SpaceConflict_PhaseA_v2', [sys.executable,'-m','unittest','-v','test_reference_metrics.py']),
        ('reused_parser_and_pair_tests', CODE.parent/'spatial_conflict_diagnosis_v1', [sys.executable,'-m','unittest','discover','-s','tests','-v'])]:
        result = subprocess.run(command, cwd=directory, text=True, capture_output=True)
        tests.append(dict(name=label, status='PASS' if result.returncode == 0 else 'FAIL', command=command, stdout=result.stdout, stderr=result.stderr))
    write(root/'reports/scorer_tests.json', tests)
    if any(t['status'] != 'PASS' for t in tests): raise ValueError('SCORER_TEST_FAILED')
    gold = resolved_gold(hist, project)
    inputs = unique(rows(hist/'requests.jsonl'), 'sample_id')
    predictions = unique((r for f in sorted((hist/'full').glob('predictions_*.jsonl')) for r in rows(f)), 'sample_id')
    if set(inputs) != set(gold) or set(predictions)-set(gold): raise ValueError('GOLD_INPUT_PREDICTION_ID_MISMATCH')
    sys.path.insert(0, str(hist/'code'))
    import common as historical_common
    records = []
    for sid, g in gold.items():
        p = predictions.get(sid, {})
        parsed = historical_common.parse(p.get('raw_response', ''))
        predicted = parsed['label'] if not p.get('error') and parsed.get('schema_valid') else None
        request = inputs[sid]
        if request['split'] != g['split'] or request['pair_id'] != g['pair_id']: raise ValueError('METADATA_JOIN_MISMATCH')
        records.append(dict(sample_id=sid, pair_id=g['pair_id'], gold=g['gold'], pred=predicted or 'INVALID',
                            split=g['split'], level=g['level'], source=g['dataset'], operator=g.get('operator') or 'NOT_ANNOTATED',
                            cluster_id=cluster(g['global_world_id']), runtime_error=p.get('error'), missing=not bool(p)))
    confusion=[]; pair_tables=[]; results={}; mismatches=[]
    for split in ['all','train','dev','test']:
        rr = [r for r in records if split=='all' or r['split']==split]
        results[split] = pair_metrics(rr)
        for group_key in ['overall','level','source','operator']:
            groups = {'ALL':rr} if group_key=='overall' else {v:[r for r in rr if r[group_key]==v] for v in sorted({r[group_key] for r in rr},key=str)}
            for value, members in groups.items():
                counts=collections.Counter((r['gold'],r['pred']) for r in members)
                for gt in LABELS:
                    for pred in OUTCOMES:
                        confusion.append(dict(model='qwen25vl7b_historical_256',split=split,group=group_key,value=value,gold=gt,pred=pred,n=counts[gt,pred]))
        pairs=collections.defaultdict(dict)
        for r in rr:
            if r['gold'] in LABELS[:2]: pairs[r['pair_id']][r['gold']]=r['pred']
        counts=collections.Counter((p['SUPPORTED'],p['CONTRADICTORY']) for p in pairs.values())
        for ps in OUTCOMES:
            for pc in OUTCOMES: pair_tables.append(dict(model='qwen25vl7b_historical_256',split=split,pred_supported_member=ps,pred_contradictory_member=pc,n=counts[ps,pc]))
    prior=load(hist/'full_score.json')
    for split,key in [('all','overall'),('test','test_only')]:
        for metric in ['claim_accuracy','pair_accuracy']:
            if abs(results[split][metric]-prior[key][metric])>1e-12: mismatches.append([split,metric,results[split][metric],prior[key][metric]])
    csvwrite(root/'tables/confusion_matrices.csv',confusion)
    csvwrite(root/'tables/pair_response_matrices.csv',pair_tables)
    write(root/'scores/historical_recomputed.json',dict(results=results,score_mismatches=mismatches))
    write(root/'scores/historical_joined.jsonl',records,'jsonl')
    write(root/'reports/world_metadata_repair.json', dict(status='PASS',rule='EXACT_FROZEN_ID_JOIN',historical_files_modified=False,
        repaired_ids=[sid for sid,g in gold.items() if g.get('diagnostic_world_metadata_origin')=='EXACT_FROZEN_ID_JOIN']))
    paths=[project/'PROJECT_SPEC.md',project/'datasets.yaml',project/'release/production_available_v10/manifest.json',project/'release/production_available_v10/pairs.jsonl',
           project/'release/production_available_v10/claims.jsonl',project/'release/production_available_v10/unknown_challenge.jsonl',project/'l4/v3_3/release/manifest.json',
           project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl',project/'l4/v3_3/release/gold.l4_three_part_v3.jsonl',
           project/'l4/v3_3/release/unknown_challenge.l4_v3.jsonl',hist/'requests.jsonl',hist/'private_gold.jsonl',hist/'full_score.json',campaign/'config.json']
    paths+=sorted((hist/'full').glob('predictions_*.jsonl'))
    paths+=sorted((CODE/'src').glob('*.py'))
    assets=[evidence_entry(p) for p in paths]
    models=load(campaign/'config.json')['models']
    model_assets=[]
    for m in models:
        mm=load(m['manifest_path'])
        if (mm['model_id'],mm['revision'])!=(m['model'],m['revision']): raise ValueError('MODEL_MANIFEST_MISMATCH')
        model_assets.append(dict(**m, files=[evidence_entry(Path(m['model_path'])/n) for n in ['config.json','generation_config.json','tokenizer_config.json','preprocessor_config.json']]))
    write(root/'manifest/repository_inventory.json', dict(status='PASS' if not mismatches else 'FAIL',assets=assets,models=model_assets,
        current_campaign_config=load(campaign/'config.json'),v1_status='THREE_SOURCE_FILES_ONLY_NO_EXPERIMENTS_RUN',
        dataset_review=cfg['review'],commit='NO_GIT_COMMIT_CLAIMED',run_id=a.run_id,seed=a.seed))
    protected=[entry for entry in assets if not entry['path'].startswith(str(CODE))]
    frozen_write(root/'manifest/protected_assets.before.json',protected)
    write(root/'reports/protocol_diff.json',dict(historical=load(hist/'config.json'),current_scale=load(campaign/'config.json'),phase_a=cfg,
        result_reuse='HISTORICAL_AUDIT_ONLY; new prompts not interchangeable with old predictions'))
    write(root/'reports/test_exposure_log.md', '# Test exposure disclosure\n\nHistorical test aggregate scores have been seen by the researcher and assistant. A0 replays historical aggregates only. No new official-test or sealed-confirmation model request is authorized. Discovery sampling never uses model correctness.\n','text')
    ctest=[r for r in records if r['split']=='test' and r['gold']=='CONTRADICTORY']
    flows=collections.Counter(r['pred'] for r in ctest)
    text='# A0 历史评分复核\n\n'
    text+=f"历史 Qwen2.5-VL-7B（256 tokens）：{len(records)} 条输入；ID 与重复检查通过。\n\n"
    text+='| split | N | pairs | ClaimAcc | BinaryClaimAcc | PairAcc | Recall_C |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for split,v in results.items(): text+=f"| {split} | {v['n']} | {v['pairs']} | {v['claim_accuracy']:.6f} | {v['binary_claim_accuracy']:.6f} | {v['pair_accuracy']:.6f} | {v['recalls']['CONTRADICTORY']:.6f} |\n"
    text+=f"\n与历史 full_score.json 差异：{mismatches}。test 真实 C 的预测流向（N={len(ctest)}）：{dict(flows)}。\n\n"
    text+='这只是历史行为描述：PairAcc 与 C 召回共享失败，不能作为两个独立机制证据；全体含 UNKNOWN 的 ClaimAcc 不与二元 PairAcc 直接相减。新条件必须独立测量。\n'
    write(root/'reports/baseline_reaudit.md',text,'text')
    write(root/'reports/a0_acceptance.json',dict(status='PASS' if not mismatches else 'FAIL',score_agreement=not mismatches,duplicate_ids=0,missing_predictions=len(set(gold)-set(predictions)),runtime_errors=sum(bool(r['runtime_error']) for r in records),test_new_requests=0))
    print(json.dumps(dict(status='PASS' if not mismatches else 'FAIL',records=len(records),test_C_flow=dict(flows))))
    if mismatches: raise ValueError('HISTORICAL_METRIC_MISMATCH')

if __name__=='__main__': main()
