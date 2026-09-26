"""Versioned E8 metadata correction; missing dimensions remain missing."""
from bc_common import *

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Use native E8 source_level/bundle, not nonexistent primary_stratum.');return
    p,req,matched=batch(sws,'E8');matrix=[];sources=[]
    panels=list(rows(p/'private_gold/world_panel.jsonl'));gaps=list(rows(p/'reports/NOT_DIAGNOSABLE.jsonl'))
    sources += [entry(p/'private_gold'/n) for n in ('world_panel.jsonl','matched_structure.jsonl')]+[entry(p/'reports/NOT_DIAGNOSABLE.jsonl')]
    required={'L1':['OBJECT','ARGUMENT','FACT_VALUE','SUPPORTED','CONTRADICTORY'],
        'L2':['PREMISE_1','PREMISE_2','JOINT_PREMISES','CONCLUSION','SUPPORTED','CONTRADICTORY'],
        'L3':['LOCAL_FACT','IDENTITY_ALIGNMENT','MARKER_VIEW','GLOBAL_FACT','SUPPORTED','CONTRADICTORY'],
        'L4':['PRE_VALUE','ACTION_PARSE','POST_VALUE','JOINT_STATE','TARGET_SELECT','SUPPORTED','CONTRADICTORY']}
    for model in c['models']:
        sc,refs=scores(sws,'E8',model);sources+=refs
        for panel in panels:
            w=panel['world_cluster_id'];level=panel['source_level']
            mm=[m for m in matched if m['world_cluster_id']==w and m['experiment']=='E8' and m.get('level')==level]
            ids={k:v for m in mm for k,v in m.items() if isinstance(v,str) and v in req}
            ep={k:endpoint(sc,rid) for k,rid in ids.items()}
            for k in required[level]:ep.setdefault(k,endpoint({},None))
            def cond(keys,target):
                vv=[ep.get(k,{}).get('correct') for k in keys];tv=ep.get(target,{}).get('correct')
                return not tv if all(v is True for v in vv) and tv is not None else None
            matrix.append(dict(model=model,world_cluster_id=w,level=level,
                source_family=sorted({req[rid]['sample_family'] for rid in ids.values()}),endpoints=ep,
                missing_conditions=[k for k in required[level] if ep[k]['status']=='NOT_RUN'],
                source_gaps=[g for g in gaps if g['world_cluster_id']==w and g['level']==level],
                status='NOT_DIAGNOSABLE' if any(ep[k]['status']=='NOT_RUN' for k in required[level]) else 'AVAILABLE',
                premise_correct_conclusion_wrong=cond(['PREMISE_1','PREMISE_2'],'CONCLUSION') if level=='L2' else None,
                pre_action_correct_post_wrong=cond(['PRE_VALUE','ACTION_PARSE'],'POST_VALUE') if level=='L4' else None,
                local_alignment_correct_global_wrong=cond(['LOCAL_FACT','IDENTITY_ALIGNMENT'],'GLOBAL_FACT') if level=='L3' else None,
                object_correct_relation_wrong=cond(['OBJECT'],'FACT_VALUE') if level=='L1' else None,
                source_bundle=panel['bundle'],split='discovery',interpretation='SAME_WORLD_FUNCTIONAL_BOUNDARIES_NOT_CAUSAL_MEDIATION'))
    sources.append(entry(__file__))
    publish(out,'P3_E8',matrix,sources,dict(metadata_fix='SOURCE_FAMILY_FROM_ACTUAL_REQUESTS_NOT_NONEXISTENT_PANEL_FIELD',failed_predecessor_job='8198601'))

if __name__=='__main__':main()
