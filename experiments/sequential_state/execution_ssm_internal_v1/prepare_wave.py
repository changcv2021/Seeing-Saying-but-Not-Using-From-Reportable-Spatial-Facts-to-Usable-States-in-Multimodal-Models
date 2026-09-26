"""Source-only fixed R1 inputs and I1/I2/protection structural manifests."""
from collections import Counter,defaultdict
from internal_common import *
from state_contracts import Program,Action,interchange
from data_continuation_v1.prepare import source_guard
def program(row):
    d=row['program'];return Program(d['s0'],Action(**d['a1']),Action(**d['a2']),d['source_type'])
def main():
    a=cli(__doc__).parse_args();c,out=setup(a)
    if a.dry_run:print('Source-only R1 plus structural I1/I2/BASE/PROTECTED; no outcome selection.');return
    if (out/'manifest/INDEPENDENT_WAVE_LOCK.json').exists():verify_lock();print('EXACT_FROZEN_WAVE_REUSED');return
    for path in WAVE_CODE.glob('*.py'):compile(path.read_text(),str(path),'exec')
    guard=source_guard();refs=[];req=[];labels=[];struct=[];pairs=[];panels={};logical={}
    for b in ('B1','B2'):
        src=ROOT/'batches'/b;lock=load(src/'manifest/REQUEST_LOCK.json')
        for ref in lock['public_inputs']+lock['private_inputs']:check(ref)
        refs += [entry(src/'manifest/REQUEST_LOCK.json')]+lock['public_inputs']+lock['private_inputs']
        allreq={r['request_id']:r for r in rows(src/'public_inputs/requests.jsonl')}
        panels[b]=list(rows(src/'private_gold/world_panel.jsonl'));logical[b]=list(rows(src/'public_inputs/logical_manifest.jsonl'))
        panelmap={(p['world_cluster_id'],p.get('sequence','PROGRAM')):p for p in panels[b]}
        conditions={'B01','B06'} if b=='B1' else {'FINAL'}
        selected=[l for l in logical[b] if l['condition'] in conditions]
        for l in selected:
            r=allreq[l['request_id']];p=panelmap[(l['world_cluster_id'],l['sequence'])];pr=program(p)
            req.append(dict(r,batch=b,r1_condition=l['condition'],sequence=l['sequence']))
            entity=None
            if b=='B1':
                graph=load(p['source_graphs'][0]['path']);entity=next(f['subject'] for f in graph['facts'] if f['fact_id']==p['source_facts'][0])
            labels.append(dict(request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],split=l['split'],batch=b,condition=l['condition'],
                cluster_id=p.get('program_family',r['world_cluster_id']),targets=dict(S0=pr.s0,S1=pr.s1,S2=pr.s2,A1_AMOUNT=pr.a1.amount,A2_AMOUNT=pr.a2.amount,
                A1_TYPE=pr.a1.kind,A2_TYPE=pr.a2.kind,Z='S2',ENTITY=entity,PROTECTED=p.get('protected')),explicit_s1_in_prompt=l['condition']=='B06'))
        if b=='B1':
            by=defaultdict(dict)
            for l in logical[b]:by[(l['world_cluster_id'],l['sequence'])][l['condition']]=l
            for p in panels[b]:
                ids=by[(p['world_cluster_id'],p['sequence'])];w=p['world_cluster_id']
                struct.append(dict(world_cluster_id=w,sequence=p['sequence'],split=p['split'],recipient=ids['B01']['request_id'],oracle_donor=ids['B06']['request_id'],
                    sham=ids['B07']['request_id'],base=ids['B15']['request_id'],protected=ids['B16']['request_id'],
                    protected_pre=by[(w,'SHARED')]['PROTECTED_PRE_SUPPLEMENT']['request_id'],
                    initial=ids['B02']['request_id'],intermediate=ids['B03']['request_id'],action_scope=ids['B04']['request_id'],
                    qualification='STRUCTURE_ONLY_PENDING_BEHAVIOR_AND_PAIR_SPECIFIC_T0',case_rule='B01 normalized valid wrong integer AND B06 correct; sham and success controls retained',
                    eligible_for_case_selection=p['split']!='LOCKED_EVAL'))
    assert len(req)==416 and len({r['request_id'] for r in req})==416
    # These are source-structural I2 candidates, not post-hoc effect-selected intervention pairs.
    for b in ('B1','B2'):
        ps=panels[b]
        for r in ps:
            candidates=[]
            for d in ps:
                if r['split']!=d['split']:continue
                if b=='B1' and r['world_cluster_id']!=d['world_cluster_id']:continue
                if b=='B2' and r['program_family']!=d['program_family']:continue
                try:info=interchange(program(r),program(d))
                except ValueError:continue
                tag='SELF_OR_SAME_S1' if info['recipient_s1']==info['donor_s1'] else 'DISCRIMINATIVE' if info['discriminative'] else 'DEGENERATE_OR_AMBIGUOUS'
                pair=dict(batch=b,recipient_world=r['world_cluster_id'],recipient_sequence=r.get('sequence','PROGRAM'),donor_world=d['world_cluster_id'],
                    donor_sequence=d.get('sequence','PROGRAM'),split=r['split'],same_world=r['world_cluster_id']==d['world_cluster_id'],
                    cluster_id=r.get('program_family',r['world_cluster_id']),control_type=tag,recipient_program=r['program'],donor_program=d['program'],
                    **info,status='SOURCE_STRUCTURE_ONLY_NOT_PATCHED',unpatched_collision_status='NOT_CHECKED_NO_PREDICTION_ACCESS')
                candidates.append(pair)
            # Bounded, structure/hash only, retain each control category independently.
            for tag in sorted({p['control_type'] for p in candidates}):
                for pair in sorted([p for p in candidates if p['control_type']==tag],key=lambda p:digest([20260911,p]))[:4]:
                    pair['pair_id']='ssmi2_'+digest(pair)[:24];pairs.append(pair)
    save(out/'public_inputs/r1_requests.jsonl',req,'jsonl');save(out/'private_gold/r1_labels.jsonl',labels,'jsonl')
    save(out/'preparation/I1_BASE_PROTECTED_STRUCTURES.jsonl',struct,'jsonl');save(out/'preparation/I2_STRUCTURAL_PAIRS.jsonl',pairs,'jsonl')
    save(out/'manifest/R1_PROTOCOL.json',dict(models=MODELS,contexts=416,groups={'B1_CANONICAL':160,'B1_ORACLE_S1':160,'B2_SYMBOLIC_FINAL':96},
        context_selection='SOURCE_CONDITION_ONLY_NO_MODEL_OUTCOME',layer_count=8,anchors=['P_PRE','P_A1','P_CHECKPOINT','P_A2','P_QUERY'],
        output='BLOCK_RESIDUAL_OUTPUT_BEFORE_GENERATION',oracle_as_explicit_positive_control_only=True,
        no_all_token_dump=True,split_policy='EXISTING_FROZEN_WORLD_OR_SYMBOLIC_FAMILY_SPLIT',
        probes={'variables':['S0','S1','S2','A1_AMOUNT','A2_AMOUNT','A1_TYPE','A2_TYPE','Z','ENTITY','PROTECTED'],'anchors':['P_CHECKPOINT','P_QUERY'],'ridge_alphas':[1.0,10.0,100.0],
            'class_min_train':2,'min_train_clusters':8,'min_select_clusters':3,'min_eval_clusters':3,
            'baselines':['MAJORITY','WORD_NUMBER_BAG_PLUS_LENGTH'],'selection':'SELECT_ONLY_PER_LAYER_ANCHOR_VARIABLE; NO_LAYER_SELECTION_FROM_LOCKED_EVAL'},
        intervention_authorization='NONE_BY_THIS_WAVE; STRUCTURAL_MANIFESTS_ARE_NOT_PATCH_TRIALS'))
    save(out/'manifest/T0_PROTOCOL.json',dict(scope='READ_ONLY_RESIDUAL_EXTRACTION_AND_EXTENDED_TECHNICAL_CHECK',
        technique='FULL_PREFILL_WITH_FRESH_CACHE_NONE; NO_SUFFIX_CACHE_REUSE',technical_cases=4,
        canonical_answers=['{"value":0}','{"value":12}','{"value":null}'],
        hooks='CLONE_SELF_AND_READONLY_CAPTURE',tolerance_policy='CALIBRATE_FROM_INDEPENDENT_TECH_INPUTS_ONLY_BEFORE_R1',
        max_allowed_technical_token_logprob_difference=0.5,max_allowed_prefix_relative_rms=0.01,
        extracted_argmax_must_match=True,mechanism_pair_specific_gate_still_required=True))
    for m in MODELS:refs += [entry(ROOT/'technical'/m/'ARCHITECTURE_MANIFEST.json'),entry(ROOT/'technical'/m/'BEHAVIOR_PREFLIGHT.json')]
    code=[entry(p) for p in sorted(WAVE_CODE.glob('*.py'))]+[entry(WAVE_CODE/'job.sh'),entry(HERE/'ssm_common.py'),entry(PACKAGE/'tools/state_contracts.py')]
    inputs=refs+[entry(out/n) for n in ('public_inputs/r1_requests.jsonl','private_gold/r1_labels.jsonl','manifest/R1_PROTOCOL.json','manifest/T0_PROTOCOL.json')]
    save(out/'manifest/INDEPENDENT_WAVE_LOCK.json',dict(created_at=now(),status='FROZEN_BEFORE_R1',code=code,inputs=inputs,
        source_guard=guard,seed=20260911,resource_authority='USER_20260911_SUBMIT_INDEPENDENT_STEPS_5_TO_10',
        no_training_backbone=True,no_test=True,no_patch_experiment_submitted=True))
    save(out/'preparation/PREPARE_ACCEPTANCE.json',dict(status='PASS',contexts=416,models=MODELS,source_guard=guard,structures=len(struct),
        pair_counts=dict(Counter((p['batch']+'_'+p['control_type']) for p in pairs)),
        pending_branches={'I1':'NEEDS_RETURNED_BEHAVIOR_AND_PAIR_SPECIFIC_T0','I2':'NEEDS_DISCRIMINATIVE_PAIRS_AND_INTERVENTION_RUNNER_T0',
            'I3':'NEEDS_I1_I2_LOCALIZE_EFFECT','PROTECTION_PATCH':'NEEDS_DEFINED_INTERVENTION','LOCKED_INTERVENTION_EVAL':'NEEDS_MECHANISM_LOCK'}))
    print(json.dumps(load(out/'preparation/PREPARE_ACCEPTANCE.json')),flush=True)
if __name__=='__main__':main()
