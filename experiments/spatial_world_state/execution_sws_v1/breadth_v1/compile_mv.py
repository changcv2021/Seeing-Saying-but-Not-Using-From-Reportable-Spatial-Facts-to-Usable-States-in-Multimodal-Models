"""E1 source-grounded transforms and explicitly secondary missing-marker controls.

Only the already frozen 40 VIEW_FRAME_IDENTITY discovery worlds are inspected.
Symbolic source-observability replay is NOT a pixel-complete fusion certificate.
"""
import copy
import sys
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import compile as br
from compile import *

BATCH='multiview_breadth_v1_20260910'
MODULES=('compile_mv.py','runner_mv.py','rescore_mv.py','analysis_mv.py','job_compile_mv.sh')

def replay(b,c):
    pair=b['source']['pair'];target=pair['supported_claim']['normalized']['context']
    ref=pair['graph_reference']['world_graph_hash'].removeprefix('sha256:')
    selected=[r for r in b['source_graphs'] if r['sha256']==ref]
    if len(selected)!=1:raise ValueError('EXACT_RELEASE_GRAPH_NOT_RESOLVED')
    verify(selected);graph=load(selected[0]['path'])
    ids=set(pair['source']['source_item_ids'])
    if len(ids)!=1:raise ValueError('SOURCE_LOCAL_IDENTITY_REQUIRED')
    facts=[f for f in graph['facts'] if f['context']==target and ids.intersection(f.get('provenance',{}).get('source_item_ids',[]))]
    from spaceconflict.generation.verification import independent_label
    from spaceconflict.unknown.pipeline import _witness_facts
    available=[f for f in graph['facts'] if not ids.intersection(f.get('provenance',{}).get('source_item_ids',[]))]
    auth=set(graph.get('authorized_rule_ids',[]));cert={}
    for side,label in [('supported_claim','SUPPORTED'),('contradictory_claim','CONTRADICTORY')]:
        claim=pair[side]
        def check(fs):return independent_label(candidate=claim,entity_graph=claim['normalized'],world_facts=fs,authorized_rule_ids=auth)
        full=check(graph['facts']);deleted=check(available)
        positive,negative=_witness_facts(claim['normalized']['atoms'][0],target)
        wp,wn=check([*available,positive]),check([*available,negative])
        if full['label']!=label or full['co_truth_possible']:raise ValueError('FULL_RELEASE_PROOF_REPLAY_FAILED')
        if deleted['label']!='UNKNOWN' or deleted['co_truth_possible'] or deleted['requires_unprovided_fact']:raise ValueError('ABLATION_REPLAY_FAILED')
        if wp['label']!='SUPPORTED' or wn['label']!='CONTRADICTORY':raise ValueError('WITNESS_REPLAY_FAILED')
        cert[side]=dict(full=full,ablated=deleted,positive_witness=positive,negative_witness=negative,
            positive_replay=wp,negative_replay=wn)
    return facts,dict(source_graph=selected[0],source_item_ids=sorted(ids),replay=cert,
        scope='SOURCE_LOCAL_REFERENCE_OBSERVABILITY_ONLY_NOT_PIXEL_COMPLETION',
        genuine_multiview_necessity=False,pixel_consistent_counterworlds_verified=False)

def build(cc,b):
    pair=b['source']['pair'];at=atom(pair);media=b['original_requests'][0]['media']
    if len(media)!=3 or any(m['kind']!='image' for m in media):raise ValueError('THREE_IMAGE_BUNDLE_REQUIRED')
    marked=[m for m in media if any(x['color']=='red' for x in m.get('presentation',{}).get('boxes',[]))]
    if len(marked)!=1 or marked[0]['role']=='frame_0':raise ValueError('UNIQUE_NONPRIMARY_RED_TARGET_REQUIRED')
    if 'red_bbox_target' not in at.get('subject','') and 'red_bbox_target' not in at.get('object',''):raise ValueError('TARGET_NOT_RED_SOURCE_ANNOTATION')
    removed=marked[0];remain=[m for m in media if m['role']!=removed['role']]
    def rawhash(m):return m.get('presentation',{}).get('source_sha256',m['sha256'])
    if any(rawhash(m)==rawhash(removed) or m.get('source_locator')==removed.get('source_locator') for m in remain):raise ValueError('WITHHELD_VIEW_STILL_PRESENT')
    fs,cert=replay(b,cc.c);s,val,q=spec(at)
    # No guessing a second object's identity or a camera transform. Source-local
    # axes are retained separately and are NOT an unrelated protected-object fact.
    typed={}
    for f in fs:
        if f.get('derivation') is not None or f.get('polarity')!='positive' or f['subject']!=at['subject'] or f.get('object')!=at.get('object') or f['predicate'] not in INV:continue
        key=tuple(sorted([f['predicate'],INV[f['predicate']]]))
        if key in typed and typed[key]['predicate']!=f['predicate']:raise ValueError('CONTRADICTORY_LOCAL_AXES')
        typed[key]=f
    ff=sorted(typed.values(),key=lambda f:digest([cc.c['seed'],'MV_FACT',f['fact_id']]))[:3]
    extra='The queried target is defined by its colored bounding-box annotation, not by a guessed unmarked substitute. Stable source frame labels keep their meaning when image order changes.\n'
    ids={};localids=[]
    ids['FULL']=cc.emit(b,'FULL',s,dict(value=val),q,exp='E1',extra=extra)
    for name,mm in [('REVERSED',list(reversed(media))),('ROTATED',media[1:]+media[:1]),('REDUNDANT',media+[copy.deepcopy(media[0])])]:
        ids[name]=cc.emit(b,name,s,dict(value=val),q,exp='E1',media=mm,extra=extra)
    for f in ff:
        ss,vv,qq=spec(f)
        localids.append(cc.emit(b,'LOCAL_'+str(len(localids)+1),ss,dict(value=vv),qq,exp='E1',extra=extra))
    if len(ff)>=2:
        js=dict(kind='facts',domain='enum',values=sorted({v for f in ff for v in [f['predicate'],INV[f['predicate']]]}),nullable=True,
            query_ids=['q'+str(i+1) for i in range(len(ff))])
        jj=' '.join('q'+str(i+1)+': '+spec(f)[2] for i,f in enumerate(ff))
        ids['JOINT']=cc.emit(b,'JOINT',js,dict(facts={'q'+str(i+1):f['predicate'] for i,f in enumerate(ff)}),jj,exp='E1',extra=extra)
    else:cc.gap(b,'JOINT','FEWER_THAN_TWO_SOURCE_LOCAL_AXES')
    marker=dict(kind='value',domain='enum',values=[m['role'] for m in media],nullable=True)
    mq='Which stable source frame label contains the red annotated bounding-box outline in the supplied input? Return null if that annotation is absent.'
    ids['MARKER_FULL']=cc.emit(b,'MARKER_FULL',marker,dict(value=removed['role']),mq,exp='E1_LOCAL_CONTROL',extra=extra)
    ids['MARKER_REMOVED']=cc.emit(b,'MARKER_REMOVED',marker,dict(value=None),mq,exp='E1_LOCAL_CONTROL',media=remain,extra=extra)
    for m in media:
        ids['SINGLE_MARKER_'+m['role']]=cc.emit(b,'SINGLE_MARKER_'+m['role'],marker,dict(value=removed['role'] if m['role']==removed['role'] else None),mq,
            exp='E1_LOCAL_CONTROL',media=[m],extra=extra)
    # Secondary reference-loss, not a main pixel-level spatial UNKNOWN gold.
    ids['REFERENCE_REMOVED']=cc.emit(b,'REFERENCE_REMOVED',s,dict(value=None),q,exp='E1_REFERENCE_ABLATION_SECONDARY',media=remain,extra=extra)
    vs=dict(kind='verdict',domain='enum',values=['SUPPORTED','CONTRADICTORY','UNKNOWN'],nullable=True)
    for label in ('SUPPORTED','CONTRADICTORY'):
        ids['ABLATE_'+label]=cc.emit(b,'ABLATE_'+label,vs,dict(verdict='UNKNOWN'),'Judge this candidate: '+claim_text(pair,label),
            exp='E1_REFERENCE_ABLATION_SECONDARY',media=remain,extra=extra,role='CANDIDATE')
    cert.update(world_cluster_id=b['world_cluster_id'],removed_role=removed['role'],removed_source=removed,
        retained_media=remain,source_bundle=b['_ref'],primary_frame_present=any(m['role']=='frame_0' for m in remain),
        main_fusion_eligible=False,annotation_reference_absence=True,actual_processor_check='PENDING')
    certpath=cc.root/'batches'/BATCH/'private_gold/ablation_certificates'/(digest(b['world_cluster_id'])+'.json')
    save(certpath,cert)
    for rid in ids.values():
        cc.gold[rid]['ablation_certificate']=entry(certpath)
        cc.gold[rid]['reference_loss_not_spatial_pixel_coverage']=True
    cc.matched.append(dict(experiment='E1',world_cluster_id=b['world_cluster_id'],level='L3',local_fact_requests=localids,
        source_local_axis_count=len(ff),protected_unrelated_fact_available=False,**ids))
    cc.panels.append(dict(world_cluster_id=b['world_cluster_id'],source_level='L3',bundle=b['_ref'],
        source_local_axis_count=len(ff),certificate=entry(certpath),main_fusion_eligible=False))
    cc.gap(b,'MINIMAL_SUFFICIENT_AND_SPATIAL_SINGLE_VIEWS','NO_PIXEL_COMPLETE_SINGLE_VIEW_COVERAGE_AND_COUNTERWORLD_CERTIFICATE')
    cc.gap(b,'UNRELATED_PROTECTED_FACT','SAME_OBJECT_AXES_ARE_NOT_UNRELATED_OBJECT_PROTECTION')

def main():
    a=arguments(__doc__).parse_args();c,root=setup(a)
    if a.dry_run:print('E1 fixed 40 discovery worlds, no outcome selection; source-reference ablations secondary.');return
    dest=root/'preparation/multiview_breadth_v1_20260910'
    if (dest/'ACCEPTANCE.json').exists():print('ALREADY_COMPILED');return
    guard=source_guard();panel=root/'batches'/EXPAND/'private_gold/world_panel.jsonl'
    selected=[r for r in rows(panel) if r['primary_stratum']=='VIEW_FRAME_IDENTITY']
    if len(selected)!=40:raise ValueError('FROZEN_VIEW_PANEL_NOT_40')
    sys.path.insert(0,str(Path(c['project'])/'src'))
    import spaceconflict.generation.verification as verifier
    import spaceconflict.unknown.pipeline as unknown
    oldruntime=br.runtime_files
    br.runtime_files=lambda cfg:oldruntime(cfg)+[entry(HERE/x) for x in MODULES]+[entry(verifier.__file__),entry(unknown.__file__)]
    save(dest/'SELECTION_LOCK.json',dict(created_at=now(),source_panel=entry(panel),worlds=selected,code=[entry(HERE/x) for x in MODULES],
        selection='EXACT_ALREADY_FROZEN_VIEW_40_NO_REPLACEMENT',single_view_marker_only=True,
        source_unknown_scope='SECONDARY_REFERENCE_LOSS_NOT_MAIN_FUSION',max_calls_per_world=18,
        no_test_experiments=True,no_prediction_access=True))
    cc=Compiler(c,root,BATCH)
    for rec in selected:
        verify([rec['bundle']]);b=load(rec['bundle']['path']);b['_ref']=rec['bundle']
        if b['split']!='discovery':raise ValueError('NON_DISCOVERY_WORLD')
        before=len(cc.aliases)
        try:build(cc,b)
        except ValueError as exc:cc.gap(b,'REMAINING',str(exc))
        if len(cc.aliases)-before>18:raise ValueError('E1_PER_WORLD_CALL_LIMIT')
    from contracts import parse
    for rid,r in cc.req.items():
        expected=copy.deepcopy(cc.gold[rid]['expected'])
        if 'facts' in expected:expected['facts']=[dict(query_id=k,value=v) for k,v in expected['facts'].items()]
        parsed=parse(json.dumps(expected),r['schema'])
        if parsed['status']!='VALID' or parsed['component_values']!=cc.gold[rid]['expected']:raise ValueError('GOLD_SCHEMA_ROUNDTRIP_FAILED:'+rid)
        if any(x in r['payload']['text'] for x in ('source_item:','fact:','world_graph','proof_nodes','expected')):raise ValueError('PRIVATE_INPUT_LEAK')
    report=cc.publish();report.update(real_requests_schema_roundtrip=len(cc.req),source_guard=dict(guard),
        frozen_panel_worlds=40,fully_certified_pixel_multiview_worlds=0,
        secondary_ablations=True,primary_scope='FULL_EVIDENCE_FACT_REPORT_AND_PRESERVING_TRANSFORMS')
    save(dest/'ACCEPTANCE.json',report);print(json.dumps(report),flush=True)

if __name__=='__main__':main()
