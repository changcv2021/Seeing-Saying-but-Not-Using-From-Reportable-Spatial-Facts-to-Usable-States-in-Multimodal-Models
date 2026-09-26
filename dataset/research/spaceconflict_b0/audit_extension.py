"""Check whether the provisional native exclusion hides usable count worlds; no predictions."""
from collections import Counter,defaultdict
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Audit excluded dev/discovery native source truth only'); return
    compute(); project=Path(c['project'])
    excluded={r['pair_id'] for r in csvrows(root/'tables/source_eligibility_rejections.csv') if r['reason'].startswith('NEW_NATIVE_')}
    pairs={r['pair_id']:r for r in rows(project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl') if r['pair_id'] in excluded}
    prepath=project/'transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7/prestates.count_v2.jsonl'
    branches={r['branch_id'] for r in pairs.values() if r['supported_claim']['graph']['predicate']=='COUNT'}
    preindex={}
    for state in rows(prepath):
        if state['branch_id'] not in branches: continue
        for fact in state['pre_state_subgraph']['facts']:
            if fact['predicate']=='COUNT': preindex[state['branch_id'],fact['subject']]=(state,prepath)
    members=defaultdict(list)
    for r in rows(Path(c['historical'])/'requests.jsonl'):
        if r.get('pair_id') in pairs and r.get('split')=='dev': members[r['pair_id']].append(r)
    sys.path.insert(0,str(project/'src')); sys.path.insert(0,str(project/'research/state_binding_phase_a_v2/src'))
    from mine import group_from_l4
    audit=[]; potential=[]
    for pid,p in pairs.items():
        group,reason=group_from_l4(p,members,preindex,c)
        rec=dict(pair_id=pid,world=cluster(p['global_world_id']),predicate=p['supported_claim']['graph']['predicate'],
                 transition_family=p.get('transition_family'),reason=reason or 'REQUIRES_EXPLICIT_ACTION_AMOUNT_REVIEW')
        if group:
            key=p['branch_id'],p['supported_claim']['graph']['subject']; state=preindex[key][0]
            rec.update(values=group['private']['values'],accessible_transition=state['accessible_transition'],
                       original_intervention=group['intervention'])
            potential.append(rec)
        audit.append(rec)
    union_csv(root/'tables/native_extension_source_audit.csv',audit)
    result=dict(status='PASS_NO_ADDITIONAL_NATIVE_COUNT_GROUPS' if not potential else 'HOLD_BEFORE_SMOKE_NATIVE_COUNT_REVIEW_REQUIRED',
        excluded_native_pairs=len(pairs),reasons=dict(Counter(r['reason'] for r in audit)),potential=potential,
        model_predictions_read=False,source=entry(prepath),selection_scope='existing dev/discovery excluded pairs only')
    save(root/'reports/native_extension_source_audit.json',result); print(json.dumps(result),flush=True)
    if potential: raise SystemExit(2)


if __name__=='__main__': main()
