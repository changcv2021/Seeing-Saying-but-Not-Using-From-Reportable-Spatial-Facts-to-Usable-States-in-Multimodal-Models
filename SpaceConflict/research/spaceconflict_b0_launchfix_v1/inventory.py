"""CPU source-only inventory/selection. No historical model prediction reads."""
from collections import Counter, defaultdict
import subprocess
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run:
        print('Source-only B0 inventory; no generation and no confirmation/test query construction'); return
    compute(); project=Path(c['project']); pa=Path(c['phase_a_root']); a1=Path(c['a1_root'])
    baseline=root/'manifest/history_before.jsonl'
    if not baseline.exists():
        protected={r['path']:r for r in rows(a1/'manifest/history_before.jsonl')}
        for p in sorted(a1.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts: protected[str(p)]=entry(p)
        save(baseline,list(protected.values()),'jsonl')
    records=list(rows(baseline))
    for offset in range(0,len(records),250):
        check_entries(records[offset:offset+250])
        print(json.dumps(dict(history_verified=min(offset+250,len(records)),history_total=len(records))),flush=True)
    # Only membership metadata is read for sealed partitions. Their gold/prompt assets are not opened.
    splits=load(pa/'manifest/cluster_split.json')
    permitted={w for w,v in splits['partition'].items() if v=='discovery'}
    excluded=set(splits['excluded_known_cross_split_clusters'])
    reviewed={r['group_id'] for r in csvrows(a1/'review/researcher_records.csv') if r['new_review_status']=='VERIFIED_FOR_A1'}
    old=[r for r in rows(a1/'review/candidate_panel.jsonl') if r['group_id'] in reviewed and r['level']=='L4']
    assert len(old)==7
    old_worlds={r['underlying_world_id'] for r in old}
    assert old_worlds<=permitted and not old_worlds&excluded
    source_path=project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'
    pairs={}; rejects=[]; eligible_pair_ids=set()
    for p in rows(source_path):
        w=cluster(p['global_world_id'])
        # Discard source contents outside dev/exploration before any proof/text processing.
        if p.get('split')!='dev' or w not in permitted or w in excluded or w in old_worlds: continue
        if p['l4_origin']!='BENCHMARK_CONTROLLED':
            rejects.append(dict(pair_id=p['pair_id'],world=w,reason='NEW_NATIVE_AMOUNT_ADAPTER_NOT_ENABLED_SOURCE_ONLY_EXTENSION')); continue
        if p['supported_claim']['graph']['predicate']!='COUNT':
            rejects.append(dict(pair_id=p['pair_id'],world=w,reason='NOT_L4_COUNT')); continue
        if p.get('intervention',{}).get('operator') not in [None,'ADD_AND_RECOUNT','REMOVE_AND_RECOUNT']:
            rejects.append(dict(pair_id=p['pair_id'],world=w,reason='NOT_SINGLE_ADD_REMOVE')); continue
        pairs[p['pair_id']]=p; eligible_pair_ids.add(p['pair_id'])
    request_by_pair=defaultdict(list)
    requestpath=Path(c['historical'])/'requests.jsonl'
    for r in rows(requestpath):
        if r.get('pair_id') in eligible_pair_ids and r.get('split')=='dev': request_by_pair[r['pair_id']].append(r)
    sys.path.insert(0,str(project/'src'))
    sys.path.insert(0,str(project/'research/state_binding_phase_a_v2/src'))
    from mine import group_from_l4
    pool=[]
    for pid,p in pairs.items():
        group,reason=group_from_l4(p,request_by_pair,{},c)
        if group is None:
            rejects.append(dict(pair_id=pid,world=cluster(p['global_world_id']),reason=reason)); continue
        act=p['intervention']; params=act.get('parameters',{}); op=group['operator']
        if op=='REMOVE_AND_RECOUNT' and params.get('target_id'): operation='REMOVE'; amount=1
        elif op=='ADD_AND_RECOUNT' and type(params.get('quantity')) is int: operation='ADD'; amount=params['quantity']
        else:
            rejects.append(dict(pair_id=pid,world=group['cluster_id'],reason='ACTION_AMOUNT_NOT_SOURCE_EXPLICIT')); continue
        graph=p['supported_claim']['graph']; category=graph.get('subject_label') or graph['subject']
        values={s['role']:group['private']['values'][s['alias']] for s in group['states']}
        if values['PRE']+(amount if operation=='ADD' else -amount)!=values['POST']:
            raise ValueError('SOURCE_COUNT_ACTION_DISAGREE')
        if not group['media'] or any(m['kind']!='image' or not Path(m['path']).is_file() for m in group['media']):
            rejects.append(dict(pair_id=pid,world=group['cluster_id'],reason='MEDIA_UNAVAILABLE')); continue
        pool.append(dict(group=group,source_pair=p,values=values,operation=operation,amount=amount,category=category,
                         selection_features=[operation,str(values['PRE'])+'->'+str(values['POST']),category,group['cluster_id'].split(':')[0]],
                         source_pair_sha256=digest(p),source_file=entry(source_path)))
    # Coverage score frozen before predictions: non-1->0 transitions, operation/count/category/source novelty.
    chosen=[]; used=set(old_worlds); features=set(); candidates=list(pool)
    while candidates and len(chosen)<c['extension_world_target']:
        candidates=[x for x in candidates if x['group']['cluster_id'] not in used]
        if not candidates: break
        def rank(x):
            v=x['values']; f=x['selection_features']
            coverage=sum(weight for key,weight in zip(enumerate(f),[4,5,2,1]) if key not in features)
            nontrivial=5 if (v['PRE'],v['POST'])!=(1,0) else 0
            return (-coverage-nontrivial,digest([c['seed'],x['group']['group_id']]))
        x=min(candidates,key=rank); chosen.append(x); used.add(x['group']['cluster_id']); features.update(enumerate(x['selection_features']))
    # Source proof retained privately, never passed as public model payload.
    save(root/'private_gold/extension_candidates.jsonl',pool,'jsonl')
    save(root/'private_gold/selected_extension.jsonl',chosen,'jsonl')
    save(root/'manifest/b0_a_source_cards.jsonl',old,'jsonl')
    union_csv(root/'tables/source_eligibility_rejections.csv',rejects)
    models=load(a1/'current_state_inventory.json')['models']; check_entries([m[k] for m in models for k in ['manifest','index','config']])
    for m in models:
        assert all(Path(s['path']).is_file() and Path(s['path']).stat().st_size==s['bytes'] for s in m['shard_sizes'])
    revision=subprocess.run(['git','-C',str(project),'rev-parse','HEAD'],capture_output=True,text=True)
    inventory=dict(status='SOURCE_PANEL_SELECTED_NOT_YET_PROCESSOR_VERIFIED',run_id=c['run_id'],created_at_utc=now(),
        old_worlds=len(old),extension_pool_pairs=len(pool),extension_pool_worlds=len({x['group']['cluster_id'] for x in pool}),
        selected_extension_worlds=len(chosen),extension_status='TARGET_MET' if len(chosen)>=12 else 'INSUFFICIENT_ELIGIBLE_WORLDS',
        selected=[dict(world=x['group']['cluster_id'],values=x['values'],operation=x['operation'],amount=x['amount'],category=x['category'],parent=x['group']['parent_ids']) for x in chosen],
        model_inventory=models,history_files=len(list(rows(baseline))),history_status='PASS',
        source_files=[entry(source_path),entry(requestpath),entry(pa/'manifest/cluster_split.json'),entry(c['guide']),entry(a1/'review/candidate_panel.jsonl')],
        git_revision=revision.stdout.strip() or 'NOT_A_GIT_REPOSITORY_USE_SOURCE_HASH_SNAPSHOT',
        git_check_stderr=revision.stderr,model_predictions_read_for_selection=False,
        confirmation_gold_semantically_read_for_experiment=False,
        historical_integrity_hashing_is_not_semantic_inspection=True,
        selection_scope='DEV plus existing DISCOVERY partition only; source-native new adapters not assumed')
    save(root/'manifest/source_inventory.json',inventory)
    save(root/'LIVE_STATUS.json',inventory,frozen=False)
    print(json.dumps({k:inventory[k] for k in ['status','old_worlds','extension_pool_worlds','selected_extension_worlds','selected','history_files']},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
