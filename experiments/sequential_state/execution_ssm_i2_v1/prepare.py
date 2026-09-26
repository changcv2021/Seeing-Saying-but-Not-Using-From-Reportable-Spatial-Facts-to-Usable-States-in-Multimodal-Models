"""Freeze source-only LOCALIZE pairs, controls, and independent technical requests."""
from collections import Counter,defaultdict
from common_i2 import *
from prepare_wave import program
from state_contracts import interchange
from data_continuation_v1.prepare import source_guard
def main():
    a=cli(__doc__).parse_args();c,out=setup_i2(a)
    if a.dry_run:print('16 source-hash main pairs; matched controls; LOCALIZE only; no outcome selection');return
    if (out/'manifest/LOCK.json').exists():verify();return
    for path in CODE_I2.glob('*.py'):compile(path.read_text(),str(path),'exec')
    guard=source_guard();verify_lock()
    panel=list(rows(ROOT/'batches/B2/private_gold/world_panel.jsonl'))
    ps={r['world_cluster_id']:r for r in panel if r['split']=='LOCALIZE'}
    source=list(rows(OUT/'preparation/I2_STRUCTURAL_PAIRS.jsonl'))
    candidates=[r for r in source if r['batch']=='B2' and r['split']=='LOCALIZE' and r['control_type']=='DISCRIMINATIVE']
    # Cover families first, then hash round-robin. No predicted values are read.
    families=defaultdict(list)
    for p in candidates:families[p['cluster_id']].append(p)
    for key in families:families[key].sort(key=lambda p:digest([20260911,'I2_PRIMARY',p['pair_id']]))
    primary=[]
    while len(primary)<16 and any(families.values()):
        for key in sorted(families,key=lambda k:digest([20260911,k])):
            if families[key] and len(primary)<16:primary.append(families[key].pop(0))
    requests={r['world_cluster_id']:r for r in rows(ROOT/'batches/B2/public_inputs/requests.jsonl') if r['condition']=='FINAL' and r['split']=='LOCALIZE'}
    trial=[];gold=[];coverage=[];need=set()
    def add(base,donor,kind,anchors):
        r=ps[base['recipient_world']];d=ps[donor];info=interchange(program(r),program(d))
        rid=requests[r['world_cluster_id']]['request_id'];did=requests[donor]['request_id'];need.update([rid,did])
        vals={program(r).s0,program(r).s1,program(r).s2,program(d).s0,program(d).s1,program(d).s2,program(r).a1.amount,program(r).a2.amount,info['expected_counterfactual']}
        answers=[json.dumps({'value':v},separators=(',',':')) for v in sorted(vals)]+['{"value":null}']
        for anchor in anchors:
            for depth in range(8):
                tid='i2_'+digest([base['pair_id'],donor,kind,anchor,depth])[:24]
                trial.append(dict(trial_id=tid,base_pair_id=base['pair_id'],recipient=rid,donor=did,control=kind,anchor=anchor,depth=depth,
                    split='LOCALIZE',cluster_id=r['program_family'],shard=int(digest(base['pair_id'])[:8],16)%8,
                    score_only_candidate_strings=answers))
                gold.append(dict(trial_id=tid,base_pair_id=base['pair_id'],recipient_world=r['world_cluster_id'],donor_world=donor,
                    recipient_program=r['program'],donor_program=d['program'],primary_counterfactual=base['expected_counterfactual'],**info))
    for base in primary:
        r=ps[base['recipient_world']];d=ps[base['donor_world']];rp=program(r);dp=program(d)
        add(base,base['donor_world'],'PRIMARY',['P_CHECKPOINT','P_A2','P_QUERY'])
        add(base,base['donor_world'],'UNRELATED_POSITION',['P_PRE'])
        add(base,base['recipient_world'],'SELF',['P_CHECKPOINT'])
        pool=[p for p in ps.values() if p['program_family']==r['program_family'] and p['world_cluster_id'] not in (r['world_cluster_id'],d['world_cluster_id'])]
        types={
            'SAME_S1_DIFFERENT_HISTORY':[p for p in pool if program(p).s1==dp.s1 and (program(p).s0,program(p).a1)!=(dp.s0,dp.a1)],
            'SAME_DONOR_FINAL_DIFFERENT_S1':[p for p in pool if program(p).s2==dp.s2 and program(p).s1!=dp.s1],
            'MATCHED_RANDOM_DONOR':pool}
        for kind,eligible in types.items():
            legal=[]
            for p in eligible:
                try:interchange(rp,program(p));legal.append(p)
                except ValueError:pass
            chosen=min(legal,key=lambda p:digest([20260911,base['pair_id'],kind,p['world_cluster_id']])) if legal else None
            coverage.append(dict(base_pair_id=base['pair_id'],control=kind,status='PREPARED' if chosen else 'NOT_AVAILABLE_IN_FROZEN_FAMILY',eligible=len(legal)))
            if chosen:add(base,chosen['world_cluster_id'],kind,['P_CHECKPOINT'])
        # Same donor and a different recipient A2, matched within one frozen program family.
        alternatives=[]
        for rr in pool:
            if program(rr).a2==rp.a2:continue
            try:inf=interchange(program(rr),dp)
            except ValueError:continue
            if inf['discriminative'] and inf['expected_counterfactual']!=base['expected_counterfactual']:alternatives.append((rr,inf))
        chosen=min(alternatives,key=lambda q:digest([20260911,base['pair_id'],'A2_MATCH',q[0]['world_cluster_id']])) if alternatives else None
        coverage.append(dict(base_pair_id=base['pair_id'],control='SAME_DONOR_DIFFERENT_A2',status='PREPARED' if chosen else 'NOT_AVAILABLE_IN_FROZEN_FAMILY'))
        if chosen:
            rr,inf=chosen;matched=dict(base,recipient_world=rr['world_cluster_id'],**{k:v for k,v in inf.items() if k not in base})
            matched.update(inf);add(matched,base['donor_world'],'SAME_DONOR_DIFFERENT_A2',['P_CHECKPOINT'])
        coverage.append(dict(base_pair_id=base['pair_id'],control='UNRELATED_REGISTER_SAME_VALUE',status='NOT_AVAILABLE_SINGLE_REGISTER_FROZEN_B2_NO_NEW_PROMPTS'))
    assert len({r['trial_id'] for r in trial})==len(trial) and len(trial)<3000
    public=[r for r in requests.values() if r['request_id'] in need]
    save(out/'public_inputs/requests.jsonl',public,'jsonl');save(out/'public_inputs/trials.jsonl',trial,'jsonl')
    save(out/'private_gold/trials.jsonl',gold,'jsonl');save(out/'preparation/ALL_STRUCTURAL_CANDIDATES.jsonl',source,'jsonl')
    save(out/'preparation/PRIMARY_PAIRS.jsonl',primary,'jsonl');save(out/'preparation/CONTROL_COVERAGE.jsonl',coverage,'jsonl')
    # Setup inputs do not depend on model failures or selected mechanism outcomes.
    allr=list(rows(OUT/'public_inputs/r1_requests.jsonl'));media=max((r['payload']['media'] for r in allr),key=len)
    tech=[]
    for i,(v,mm) in enumerate([(3,[]),(12,[]),(None,media[:1]),(4,media[:2])]):
        for variant,value in [('recipient',v),('donor',7)]:
            body=f'SETUP ONLY. Register R initially equals 2.\nACTION_1: add exactly 2 units.\nSTATE_NOTE: The unrelated answer register Q is {json.dumps(value)}.\nACTION_2: add exactly 1 unit to R.\nTARGET: Q. Copy the explicitly specified unrelated register Q; do not count the images.\nOUTPUT CONTRACT: Return JSON with one key value and an integer or null, within 512 output tokens.'
            tech.append(dict(request_id=f'I2_TECH_{i}_{variant}',case=i,variant=variant,payload=dict(system=public[0]['payload']['system'],text=body,media=mm),schema=public[0]['schema']))
    save(out/'public_inputs/technical.jsonl',tech,'jsonl')
    protocol=dict(primary_model='qwen35_9b',technical_models=MODELS,primary_pairs=len(primary),trials=len(trial),shards=8,
        scope='B2_SYMBOLIC_LOCALIZE_ONLY_NOT_SPATIAL_MECHANISM_CONFIRMATION',selection='SOURCE_FAMILY_ROUND_ROBIN_AND_HASH_NO_MODEL_OUTCOMES',
        anchors='EXACT_R1_TOKEN_ANCHORS; B2 CHECKPOINT ALIASES A1 END',layers='8 EQUALLY SPACED ACTUAL BLOCK OUTPUTS',
        patch='ONE TOKEN BLOCK RESIDUAL OUTPUT; STRENGTH 1; EVERY DECODE RECOMPUTES FULL PREFIX WITH SAME PATCH; NO CACHE',
        cap=512,do_sample=False,enable_thinking=False,strict_self_token_equivalence=True,
        technical_lp_safety_ceiling=.5,prefix_relative_rms_safety_ceiling=.01,
        controls=coverage,score='EXISTING GOLD-BLIND NORMALIZER; EXACT INTEGER; NULL/INVALID/NOT_RUN RETAINED',
        scoring_candidates='FULL JSON INCLUDING CLOSING BRACE; TEACHER FORCING ONLY AFTER FREE GENERATION; NEVER IN FREE PROMPT',
        baseline_collision='ALL RETAINED; EXCLUDE ONLY FROM CHANGED_CAUSAL_EFFECT METRIC; IIA FULL DENOMINATOR',
        statistical_clusters='PROGRAM_FAMILY_CONTAINS_BOTH_RECIPIENT_AND_DONOR',bootstrap_repetitions=5000,
        heldout='NO SELECT OR LOCKED_EVAL; NO NEW MECHANISM LOCK AUTOMATICALLY',comparison_models='TECHNICAL_ONLY_UNTIL_FUNCTIONAL_PREDICTION_LOCK',
        source_guard=guard)
    save(out/'manifest/PROTOCOL.json',protocol)
    refs=[entry(out/p) for p in ['public_inputs/requests.jsonl','public_inputs/trials.jsonl','public_inputs/technical.jsonl','manifest/PROTOCOL.json']]
    runtime=Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3/pipeline_v3.py'
    source=Path('external/scratch/industbench_qwen_family/venv/lib/python3.12/site-packages/transformers/models/qwen3_5/modeling_qwen3_5.py')
    code=[entry(p) for p in sorted(CODE_I2.glob('*')) if p.is_file()]+[entry(WAVE_CODE/'representations.py'),entry(PACKAGE/'tools/state_contracts.py'),entry(HERE/'ssm_common.py'),entry(runtime),entry(source)]
    code += [entry(SWS_CODE/p) for p in ['interface_repair_v3/adapter.py','interface_repair_v2/adapter.py','contracts.py']]
    code += [entry(SWS_CODE.parent/'SpaceConflict_SWS_v1_Codex_Package/tools/research_utils.py')]
    save(out/'manifest/LOCK.json',dict(created_at=now(),code=code,public_inputs=refs,private_inputs=[entry(out/'private_gold/trials.jsonl')],source=entry(OUT/'manifest/INDEPENDENT_WAVE_LOCK.json'),
        user_authorization='USER_20260911_IMPLEMENT_AND_RUN_I2',source_guard=guard))
    save(out/'preparation/ACCEPTANCE.json',dict(status='FROZEN_NOT_EXECUTED',primary_pairs=len(primary),primary_families=len({p['cluster_id'] for p in primary}),
        original_b2_discriminative=275,localize_candidates=len(candidates),requests=len(public),trials=len(trial),by_control=dict(Counter(r['control'] for r in trial)),
        source_guard=guard,not_run_control='UNRELATED_REGISTER_SAME_VALUE'))
    print(json.dumps(load(out/'preparation/ACCEPTANCE.json')),flush=True)
if __name__=='__main__':main()
