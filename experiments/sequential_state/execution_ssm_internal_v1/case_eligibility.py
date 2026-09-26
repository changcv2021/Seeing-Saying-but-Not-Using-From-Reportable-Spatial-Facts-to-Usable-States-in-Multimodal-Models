"""Frozen LOCALIZE-only behavioral eligibility and preselected success controls; no patch."""
from internal_common import *
def main():
    p=cli(__doc__);p.add_argument('--model',required=True);a=p.parse_args();c,out=setup(a)
    if a.dry_run:print('LOCALIZE-only I1 eligibility; no locked-eval outcome analysis.');return
    assert a.model in MODELS;verify_lock();dest=out/'case_eligibility_v1'/a.model
    structures=list(rows(out/'preparation/I1_BASE_PROTECTED_STRUCTURES.jsonl'))
    local=[r for r in structures if r['split']=='LOCALIZE'];controls=sorted(local,key=lambda r:digest([20260911,'PRESELECTED_SUCCESS_CONTROL',r['world_cluster_id'],r['sequence']]))[:32]
    save(dest/'CASE_RULE_LOCK.json',dict(status='FROZEN_BEFORE_THIS_CASE_ANALYSIS',code=entry(__file__),source=entry(out/'preparation/I1_BASE_PROTECTED_STRUCTURES.jsonl'),
        cases='B01 VALID wrong definite integer and B06 correct under SAME gold; LOCALIZE only; first 32 by structural hash if over cap',
        preselected_success_control_ids=[r['recipient'] for r in controls],replacements_if_control_wrong=False,
        select_outcomes_used=False,locked_eval_outcomes_used=False))
    # Accept one actual complete score snapshot, not a Slurm exit code alone.
    complete=[]
    for path in (ROOT/'batches/B1/scores'/a.model).glob('snapshot_*/SCORE_ACCEPTANCE.json'):
        ac=load(path)
        if ac['status']=='COMPLETE_WITH_EXPLICIT_NA':complete.append((path,ac))
    if len(complete)!=1:
        save(dest/'BLOCKED.json',dict(reason='REQUIRES_UNAMBIGUOUS_COMPLETE_B1_SCORING',complete_snapshots=len(complete)));return
    path,ac=complete[0];check(ac['scores']);sc={}
    with Path(ac['scores']['path']).open() as f:
        for r in csv.DictReader(f):
            if r['split']!='LOCALIZE':continue
            if r['request_id'] not in sc:sc[r['request_id']]=r
    result=[];eligible=[]
    for r in local:
        before=sc[r['recipient']];after=sc[r['oracle_donor']]
        pred=json.loads(before['prediction']) if before['prediction'] else {};gold=json.loads(before['expected']);oracle_gold=json.loads(after['expected'])
        assert gold==oracle_gold
        definite=type(pred.get('value')) is int and before['normalized_status']=='VALID'
        qualify=definite and before['content_correct']=='False' and after['content_correct']=='True'
        row=dict(**r,baseline_prediction=pred,oracle_prediction=json.loads(after['prediction']) if after['prediction'] else {},gold=gold,
            baseline_correct=before['content_correct']=='True',oracle_correct=after['content_correct']=='True',behavior_case_eligible=qualify,
            preselected_success_control=r['recipient'] in {x['recipient'] for x in controls},
            success_control_actually_correct=(r['recipient'] in {x['recipient'] for x in controls} and before['content_correct']=='True'),
            final_patch_eligibility='PENDING_PAIR_SPECIFIC_TECHNICAL_ACCEPTANCE',raw_baseline=json.loads(before['raw']) if before['raw'] else None,
            raw_oracle=json.loads(after['raw']) if after['raw'] else None)
        result.append(row)
        if qualify:eligible.append(row)
    selected=sorted(eligible,key=lambda r:digest([20260911,'I1_LOCALIZE_CASE',r['world_cluster_id'],r['sequence']]))[:32]
    save(dest/'ALL_LOCALIZE_CASES.jsonl',result,'jsonl');save(dest/'CAPPED_I1_CANDIDATES.jsonl',selected,'jsonl')
    save(dest/'ACCEPTANCE.json',dict(status='BEHAVIOR_CASES_PREPARED_NOT_PATCHED',model=a.model,localize_sequences=len(local),
        localize_worlds=len({r['world_cluster_id'] for r in local}),eligible_sequences=len(eligible),selected_sequences=len(selected),
        selected_worlds=len({r['world_cluster_id'] for r in selected}),preselected_controls=len(controls),
        preselected_controls_correct=sum(r['success_control_actually_correct'] for r in result),score_acceptance=entry(path),
        case_lock=entry(dest/'CASE_RULE_LOCK.json'),cases=entry(dest/'ALL_LOCALIZE_CASES.jsonl'),selected=entry(dest/'CAPPED_I1_CANDIDATES.jsonl'),
        patch_trials=0,never_claim_population_incidence=True,locked_eval_outcomes_analyzed=False))
    print(json.dumps(load(dest/'ACCEPTANCE.json')),flush=True)
if __name__=='__main__':main()
