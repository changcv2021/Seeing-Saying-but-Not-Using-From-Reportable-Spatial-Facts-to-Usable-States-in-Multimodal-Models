"""Precommit bounded M2 discovery controls; never manufacture a mechanism lock."""
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common_auto_v2 import *
from data_continuation_v1.prepare import source_guard
from real_design_v1 import BATCH as SOURCE_BATCH

NAME='M2_discovery_repair_v1_20260910'
POSITIONS=['observation_end','target_end','query_end','answer_start']

def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    if a.dry_run:print('Freeze M1 structural worlds, paired donor controls and full-sequence likelihood probes; no output-based selection.');return
    out=root/'whitebox'/NAME
    if (out/'manifest/M2_PROTOCOL_LOCK.json').exists():print('ALREADY_FROZEN');return
    guard=source_guard();src=root/'batches'/SOURCE_BATCH;m1=root/'whitebox/M1_structural_d01_v1'
    refs=[m1/'private_gold/neutral_candidate_sham_pairs.jsonl',src/'public_inputs/requests.jsonl',src/'private_gold/request_gold.jsonl',src/'private_gold/matched_structure.jsonl']
    pairs=list(rows(refs[0]));requests={r['request_id']:r for r in rows(refs[1])};gold={r['request_id']:r for r in rows(refs[2])};matches=list(rows(refs[3]))
    pairs.sort(key=lambda r:digest([c['seed'],'M2_STRUCTURAL_ORDER_V1',r['world_cluster_id']]))
    if len({r['world_cluster_id'] for r in pairs})!=len(pairs):raise ValueError('DUPLICATE_WORLD')
    if len(pairs)>96:raise ValueError('STRUCTURAL_CAP')
    plan=[];private=[];gaps=[];used=set()
    def samevalue(a,b):return type(a) is type(b) and a==b
    for idx,p in enumerate(pairs):
        w=p['world_cluster_id'];n,f,s=(p[k] for k in ('neutral','false','sham'));family=requests[n]['sample_family']
        for rid in (n,f,s):
            if requests[rid]['split']!='discovery':raise ValueError('DISCOVERY_ONLY')
        if not all(requests[rid]['payload']['media']==requests[n]['payload']['media'] and requests[rid]['target_state']==requests[n]['target_state'] for rid in (f,s)):
            raise ValueError('NOT_MATCHED_MEDIA_TARGET')
        if not all(gold[rid]['expected']==gold[n]['expected'] for rid in (f,s)):raise ValueError('MATCHED_GOLD_CHANGED')
        operations=[]
        def op(name,donor,recipient,*,source_position=None,endpoint='TARGET'):
            used.update([donor,recipient]);g=gold[recipient];v=g['expected']['value']
            values=[v,p['candidate_value']]
            # These strings are likelihood probes, never an instruction or answer hint.
            alternatives=sorted({json.dumps({'value':x},separators=(',',':')) for x in values})
            oid='m2_'+digest([w,name,donor,recipient])[:24]
            operations.append(dict(operation_id=oid,name=name,donor=donor,recipient=recipient,
                donor_position_override=source_position,endpoint=endpoint,evaluation_sequences=alternatives))
            private.append(dict(operation_id=oid,world_cluster_id=w,family=family,endpoint=endpoint,
                correct_sequence=json.dumps({'value':v},separators=(',',':')),
                candidate_sequence=json.dumps({'value':p['candidate_value']},separators=(',',':')),
                source_request_gold=g))
        op('SELF_REPLACEMENT',f,f)
        op('NEUTRAL_TO_FALSE_RESCUE',n,f)
        op('FALSE_TO_NEUTRAL_REVERSE',f,n)
        op('SHAM_TO_FALSE_SAME_VALUE_DIFFERENT_ROLE',s,f)
        op('IRRELEVANT_POSITION_SAME_SIZE',n,f,source_position='observation_end')
        for equal,name in ((True,'CROSS_WORLD_SAME_ANSWER'),(False,'CROSS_WORLD_DIFFERENT_ANSWER')):
            pool=[q for q in pairs if q['world_cluster_id']!=w and requests[q['neutral']]['sample_family']==family
                and samevalue(q['target_gold'],p['target_gold'])==equal]
            if pool:
                donor=min(pool,key=lambda q:digest([c['seed'],'M2_DONOR_V1',w,name,q['world_cluster_id']]))
                op(name,donor['neutral'],f)
            else:gaps.append(dict(world_cluster_id=w,condition=name,status='NO_SOURCE_MATCHED_DONOR'))
        protection=[q for q in matches if q['world_cluster_id']==w and q['experiment']=='E2_PROTECTION' and samevalue(q['candidate_value'],p['candidate_value'])]
        if protection:op('PROTECTED_FACT_DAMAGE',n,protection[0]['false'],endpoint='PROTECTED')
        else:gaps.append(dict(world_cluster_id=w,condition='PROTECTED_FACT_DAMAGE',status='NO_EXACT_OFFSET_MATCH'))
        branch=[q for q in matches if q['world_cluster_id']==w and q['experiment']=='E3']
        if branch:op('LEGAL_UPDATE_DAMAGE',n,branch[0]['branch_value'],endpoint='LEGAL_UPDATE')
        else:gaps.append(dict(world_cluster_id=w,condition='LEGAL_UPDATE_DAMAGE',status='NOT_APPLICABLE_NO_BRANCH'))
        plan.append(dict(shard=idx,world_cluster_id=w,family=family,split='discovery',operations=operations))
    pilot=[]
    for family in ('COUNT','NONCOUNT_RELATION'):
        pp=[p for p in plan if p['family']==family]
        if pp:pilot.append(pp[0]['shard'])
    for rid in sorted(used):
        if requests[rid]['schema']['kind']!='value':raise ValueError('ONLY_VALUE_ENDPOINTS')
    save(out/'public_inputs/requests.jsonl',[requests[rid] for rid in sorted(used)],'jsonl')
    save(out/'public_inputs/operations.jsonl',plan,'jsonl')
    save(out/'private_gold/operation_labels.jsonl',private,'jsonl')
    save(out/'manifest/condition_gaps.jsonl',gaps,'jsonl')
    pre=src/'review/qwen35_9b/PROCESSOR_ACCEPTANCE.json'
    if load(root/'whitebox/M0_v1/M0_ACCEPTANCE.json')['status']!='PASS':raise ValueError('M0_NOT_PASSED')
    lock=dict(created_at=now(),name=NAME,seed=c['seed'],config_snapshot=c,model='qwen35_9b',
        sources=[entry(p) for p in refs],public_inputs=[entry(out/'public_inputs'/n) for n in ('requests.jsonl','operations.jsonl')],
        private_inputs=[entry(out/'private_gold/operation_labels.jsonl')],code=[entry(HERE/n) for n in ('prepare.py','worker.py','job.sh')],
        m0=entry(root/'whitebox/M0_v1/M0_ACCEPTANCE.json'),source_processor=entry(pre),
        pilot_shards=pilot,worlds=len(plan),selection='ALL_FROZEN_M1_STRUCTURAL_WORLDS_NOT_FAILURE_CASES',
        positions=POSITIONS,coarse_layers='8_ROUNDED_LINSPACE_FIRST_TO_LAST_LANGUAGE_BLOCK',pilot_layers='FIRST_MIDDLE_LAST',
        pilot_positions=['query_end','answer_start'],patch_site='LANGUAGE_BLOCK_OUTPUT_ONE_EXACT_SEMANTIC_TOKEN',
        hook_noop_logprob_abs_tolerance=1e-5,self_replacement_logprob_abs_tolerance=1e-5,
        canonical_metric='SUM_ALL_TOKENS_OF_COMPLETE_CANONICAL_JSON_SEQUENCE',
        generation_metric='NOT_MEASURED_BY_COARSE_LIKELIHOOD_SCREEN; REQUIRED_AT_VALIDATION',
        input_gold_leak_policy='Evaluation alternatives are teacher-forced suffix probes only; never passed into the public prompt or greedy generation',
        pilot_success='ALL_ACTUAL_PROCESSOR_BRIDGES_AND_NOOP_SELF_CHECKS_PASS_WITH_NO_INFRASTRUCTURE_ERRORS_NOT_ANSWER_ACCURACY',
        coarse_submission='ONLY_AFTER_MEASURED_PILOT_TECHNICAL_PASS',
        validation_plan=dict(new_worlds_required=True,region_selection='TOP_3_POSITIVE_MEAN_RESCUE_MINUS_SHAM_LOGPROB_REGIONS_DISJOINT_RADIUS_1_TIE_BY_LAYER_THEN_POSITION',
            selection_split='discovery_only',required_controls='ALL_LISTED_CONTROLS_AND_PROTECTION_AND_LEGAL_UPDATE; gaps prevent complete specificity claim',
            maximum_final_module_positions=12,missing_selectivity='NOT_IDENTIFIABLE_NOT_FORCED_MECHANISM'),
        mechanism_lock=False,C2_inference=False,prediction_guard=guard)
    save(out/'manifest/M2_PROTOCOL_LOCK.json',lock)
    print(json.dumps(dict(status='M2_DISCOVERY_PROTOCOL_FROZEN_PILOT_PENDING',worlds=len(plan),pilot_shards=pilot,operations=len(private),gaps=len(gaps))),flush=True)

if __name__=='__main__':main()
