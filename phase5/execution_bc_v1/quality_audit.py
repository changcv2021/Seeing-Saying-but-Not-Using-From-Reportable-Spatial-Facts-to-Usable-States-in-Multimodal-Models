"""Independent coverage/status accounting; never repair gold or old results."""
from collections import Counter,defaultdict
from bc_common import *

def status_counts(endpoints):
    def null(x):
        if x is None:return True
        if isinstance(x,dict):return any(null(v) for v in x.values())
        if isinstance(x,list):return any(null(v) for v in x)
        return False
    eps=list(endpoints);returned=[e for e in eps if e['status']=='RETURNED']
    return dict(logical_endpoints=len(eps),returned=len(returned),not_run=sum(e['status']=='NOT_RUN' for e in eps),
        invalid=sum(e['parser_status']=='INVALID' for e in returned),
        null=sum(null(e.get('prediction',{})) for e in returned),
        missing_raw_reference=sum(not(e.get('raw_path') and e.get('raw_sha256')) for e in returned),
        counting_unit='LOGICAL_ENDPOINT_REFERENCES; ALIASES_CAN_REPEAT_PHYSICAL_RESPONSES')

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Account for every frozen E8 anchor and all diagnostic endpoint statuses.');return
    dest=out/'quality_audit_v1';summary=[];refs=[]
    for mod in ('P1_E2','P2_E5','P3_E8'):
        path=out/mod/'matrix.csv';rr=csvrows(path);refs.append(entry(path));groups=defaultdict(list)
        for r in rr:groups[(r['model'],r.get('level','ALL'))].append(r)
        for (model,level),rs in groups.items():
            ep=[v for r in rs for v in json.loads(r['endpoints']).values()]
            summary.append(dict(module=mod,model=model,level=level,worlds=len({r['world_cluster_id'] for r in rs}),
                matrix_rows=len(rs),**status_counts(ep)))
    csvsave(dest/'endpoint_status_accounting.csv',summary)
    src=sws/'preparation/native_e8_c1_v1_20260910';lock=load(src/'NATIVE_ANCHOR_LOCK.json')
    p,req,matched=batch(sws,'E8');panels=list(rows(p/'private_gold/world_panel.jsonl'))
    present={(x['world_cluster_id'],x['source_level']) for x in panels};gaps=list(rows(p/'reports/NOT_DIAGNOSABLE.jsonl'))
    grouped=defaultdict(list)
    for r in req.values():grouped[(r['world_cluster_id'],r['source_level'] if 'source_level' in r else r.get('level'))].append(r)
    # Request level is resolved via the explicitly frozen anchor when unambiguous.
    rows_out=[];missing=[]
    for anchor in lock['targets']:
        key=(anchor['world_cluster_id'],anchor['level']);gg=[g for g in gaps if (g['world_cluster_id'],g['level'])==key]
        rows_out.append(dict(world_cluster_id=key[0],level=key[1],in_compiled_panel=key in present,
            status='PRESENT_IN_DIAGNOSTIC_MATRIX' if key in present else 'NOT_IN_COMPILED_PANEL_RETAINED_HERE',
            source_gaps=gg,original_sample_ids=anchor['sample_ids']))
        if key not in present:
            for model in c['models']:
                sc,ss=scores(sws,'E8',model);refs+=ss
                # Preserve partial compiler outputs if the failed anchor emitted any.
                ids={k:v for m in matched if (m['world_cluster_id'],m.get('level'))==key
                     for k,v in m.items() if isinstance(v,str) and v in req}
                ep={k:endpoint(sc,rid) for k,rid in ids.items()}
                missing.append(dict(model=model,world_cluster_id=key[0],level=key[1],endpoints=ep,source_gaps=gg,
                    status='NOT_DIAGNOSABLE_PANEL_COMPILATION_INCOMPLETE',no_model_error_selection=True))
    csvsave(dest/'e8_all_frozen_anchor_coverage.csv',rows_out)
    csvsave(dest/'e8_missing_panel_overlay.csv',missing)
    refs += [entry(src/'NATIVE_ANCHOR_LOCK.json'),entry(p/'reports/NOT_DIAGNOSABLE.jsonl'),entry(p/'private_gold/world_panel.jsonl')]
    save(dest/'ACCEPTANCE.json',dict(status='COVERAGE_AND_STATUS_AUDIT_COMPLETE',
        e8_frozen_anchors=len(rows_out),e8_frozen_worlds=len({r['world_cluster_id'] for r in rows_out}),
        e8_missing_panel_anchors=sum(not r['in_compiled_panel'] for r in rows_out),overlay_rows=len(missing),
        references=list({r['path']:r for r in refs}.values()),code=entry(__file__),job_id=os.environ['SLURM_JOB_ID'],
        note='Overlay does not invent missing gold; use with original P3 matrix. Invalid/null counts are nonexclusive.'))

if __name__=='__main__':main()
