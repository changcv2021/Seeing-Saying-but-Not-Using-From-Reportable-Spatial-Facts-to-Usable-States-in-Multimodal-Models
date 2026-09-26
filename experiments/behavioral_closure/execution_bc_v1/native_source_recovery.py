"""Recover omitted E8 PRE source witnesses from dataset construction artifacts."""
from collections import defaultdict,Counter
from bc_common import *
from data_continuation_v1.prepare import source_guard

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Replay original prestate/transition witnesses for every frozen missing-PRE anchor.');return
    guard=source_guard();project=Path(c['project']);sys.path.insert(0,str(project/'src'))
    from spaceconflict.hypo3d_l4.verification import verify_count_pair_accessibly
    dest=out/'preparation/native_source_recovery_v1';path=sws/'batches/native_e8_breadth_v1_20260910/reports/NOT_DIAGNOSABLE.jsonl'
    gaps=[r for r in rows(path) if r['reason']=='STRUCTURED_PRE_VALUE_NOT_IN_RELEASE_BUNDLE']
    index=sws/'preparation/native_e8_c1_v1_20260910/native_bundle_index.jsonl'
    bundles={r['pair_id']:r for r in rows(index)}
    sources=sorted((project/'transition_micrographs').glob('hypo3d_l4_v2_official*/prestates.count_v2.jsonl'))
    refs=[entry(p) for p in sources];save(dest/'RECOVERY_LOCK.json',dict(seed=c['seed'],selection='ALL_FROZEN_E8_MISSING_PRE_ANCHORS_NO_OUTPUTS',
        targets=gaps,source_inputs=refs,gaps=entry(path),bundle_index=entry(index),code=entry(__file__),
        verifier=entry(project/'src/spaceconflict/hypo3d_l4/verification.py'),frozen_before_new_measurements=True))
    records=defaultdict(list)
    for path in sources:
        for line,r in enumerate(rows(path),1):
            key=tuple(str(r.get(k,'')) for k in ('scene_id','change_id','question_id'))
            records[key].append(dict(row=r,source_file=str(path),source_line=line,row_sha256=digest(r)))
    result=[];recovered=[]
    for gap in gaps:
        ref=bundles[gap['pair_id']]['bundle'];b=load(check(ref));pair=b['source']['pair'];sc=pair.get('source',{})
        key=tuple(str(sc.get(k,'')) for k in ('scene_id','change_id','question_id'))
        matches=records.get(key,[]);valid=[];failures=[]
        for rec in matches:
            r=rec['row'];pre=r.get('pre_state_subgraph',{});tr=r.get('accessible_transition',{})
            if tr.get('uses_post_oracle_as_premise') is not False:
                failures.append(dict(source_file=rec['source_file'],reason='POST_ORACLE_PREMISE_NOT_EXCLUDED'));continue
            pos=pair.get('supported_claim',{}).get('graph');neg=pair.get('contradictory_claim',{}).get('graph')
            if not pos or not neg:
                failures.append(dict(source_file=rec['source_file'],reason='NATIVE_PAIR_GRAPH_NOT_DIRECT'));continue
            audit=verify_count_pair_accessibly(pre_state_subgraph=pre,accessible_transition=tr,
                supported_claim=pos,contradictory_claim=neg,necessary_pre_fact_ids=r['necessary_pre_fact_ids'])
            ff=[f for f in pre.get('facts',[]) if f.get('predicate')=='COUNT' and f.get('subject')==pos['subject']]
            if audit['status']!='PASS' or len(ff)!=1 or type(ff[0].get('value')) is not int:
                failures.append(dict(source_file=rec['source_file'],reason='REPLAY_OR_UNIQUE_PRE_FAILED',audit=audit));continue
            # Exact joins and explicit source annotation; never derive PRE by reversing POST.
            if ff[0].get('origin_type')!='SOURCE_OBJECT_ANNOTATION_COUNT':
                failures.append(dict(source_file=rec['source_file'],reason='UNSUPPORTED_PRE_ORIGIN'));continue
            valid.append(dict(**rec,replay=audit,pre_value=ff[0]['value'],post_value=pos['value'],pre_fact=ff[0]))
        signatures={digest([v['pre_fact'],v['row']['accessible_transition']]) for v in valid}
        status='RECOVERED_STRUCTURED_PRE_AND_TRANSITION' if len(signatures)==1 else 'UNRESOLVED_CONFLICTING_SOURCE_VERSIONS' if signatures else 'NOT_RECOVERED'
        rr=dict(world_cluster_id=gap['world_cluster_id'],level='L4',pair_id=gap['pair_id'],status=status,
            source_key=key,matched_records=len(matches),passing_records=len(valid),source_bundle=ref,failures=failures)
        if len(signatures)==1:
            # Deterministic path ordering; all agreeing provenance retained, not best-performing selection.
            rr.update(pre_value=valid[0]['pre_value'],post_value=valid[0]['post_value'],pre_fact=valid[0]['pre_fact'],
                transition=valid[0]['row']['accessible_transition'],witnesses=valid,
                remaining='FREEZE_DERIVED_QUERY_AND_ACTUAL_PROCESSOR_REVIEW_BEFORE_NEW_MEASUREMENT',
                model_outputs_read=False,not_new_human_verification=True)
            recovered.append(rr)
        result.append(rr)
    save(dest/'recovered_evidence.jsonl',recovered,'jsonl');save(dest/'all_target_results.jsonl',result,'jsonl')
    csvsave(dest/'recovery_summary.csv',[{k:v for k,v in r.items() if k not in ('witnesses','failures')} for r in result])
    save(dest/'ACCEPTANCE.json',dict(status='SOURCE_REPLAY_COMPLETE_NOT_INFERENCE',targets=len(result),recovered=len(recovered),
        recovery_status=dict(Counter(r['status'] for r in result)),guard=guard,job_id=os.environ['SLURM_JOB_ID'],code=entry(__file__),
        old_release_modified=False,model_gold_guesses=False,grade='AUTO_ONLY_PROVISIONAL'))
    print(json.dumps(dict(targets=len(result),recovered=len(recovered))),flush=True)

if __name__=='__main__':main()
