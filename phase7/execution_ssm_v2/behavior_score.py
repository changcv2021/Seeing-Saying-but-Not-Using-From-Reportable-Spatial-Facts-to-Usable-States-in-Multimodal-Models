"""Fixed normalization before gold access; preserve every raw / invalid / missing."""
from collections import defaultdict,Counter
from v2_common import *
from interface_repair_v3.adapter import normalize
def main():
    p=cli(__doc__);p.add_argument('--batch',required=True);p.add_argument('--model',required=True);a=p.parse_args();context(a)
    src=ROOT/'batches'/a.batch;out=src/'scores'/a.model/('snapshot_'+os.environ['SLURM_JOB_ID'])
    lock=load(src/'manifest/REQUEST_LOCK.json')
    for x in lock['code']+lock['public_inputs']:check(x)
    reqs=list(rows(src/'public_inputs/requests.jsonl'));locations={}
    for s in load(src/'manifest/shards.json'):
        for r in rows(s['request_file']['path']):locations[r['request_id']]=src/'raw'/a.model/f'shard_{s["shard"]:03}/records'/(r['request_id']+'.json')
    views={}
    for r in reqs:
        pth=locations[r['request_id']]
        if pth.exists():
            raw=load(pth);assert raw['request_hash']==r['model_independent_request_hash']
            views[r['request_id']]=dict(normalization=normalize(raw['raw_response'],r['schema']),raw_response=raw['raw_response'],raw=entry(pth),output_tokens=raw['output_tokens'],truncated=raw['truncated'])
    save(out/'normalizations.json',views)
    gold={g['request_id']:g for g in rows(src/'private_gold/request_gold.jsonl')};result=[]
    for r in reqs:
        g=gold[r['request_id']];v=views.get(r['request_id']);n=v['normalization']['normalized'] if v else {}
        pred=n.get('component_values');valid=n.get('status')=='VALID'
        proof=g.get('proof',{});cond=r['condition'];target=r['target_state']
        result.append(dict(model=a.model,request_id=r['request_id'],world_cluster_id=r['world_cluster_id'],
            condition=cond,target_state=target,program_family=proof.get('program_family',r['world_cluster_id']),
            status='RETURNED' if v else 'NOT_RUN',valid=valid if v else None,
            correct=valid and digest(pred)==digest(g['expected']) if v else None,expected=g['expected'],prediction=pred,
            terminal_state_value=proof.get('s2'),s0=proof.get('program',{}).get('s0'),s1=proof.get('s1'),s2=proof.get('s2'),
            **({k:v[k] for k in ['raw_response','raw','output_tokens','truncated']} if v else {})))
    csvsave(out/'DIAGNOSTIC_MATRIX.csv',result);groups=defaultdict(list)
    for r in result:groups[r['condition']].append(r)
    summary=[]
    for cond,rs in sorted(groups.items()):
        applicable=[dict(world_cluster_id=r['program_family'],value=int(r['correct'] is True)) for r in rs]
        summary.append(dict(model=a.model,condition=cond,programs=len(rs),returned=sum(r['status']=='RETURNED' for r in rs),invalid=sum(r['valid'] is False for r in rs),**cluster_ci(applicable)))
    csvsave(out/'GROUP_RESULTS.csv',summary)
    paired=[]
    if a.batch=='W1_TARGET':
        look={(r['world_cluster_id'],r['condition']):r for r in result}
        for target in ['S0','S1','S2']:
            for wording in ['T2','T3','T4']:
                rr=[]
                for r in result:
                    if r['condition']!='T1_'+target:continue
                    other=look[(r['world_cluster_id'],wording+'_'+target)]
                    if r['status']==other['status']=='RETURNED':rr.append(dict(world_cluster_id=r['program_family'],value=int(other['correct'])-int(r['correct'])))
                paired.append(dict(model=a.model,target=target,contrast=wording+' - T1',**cluster_ci(rr)))
        csvsave(out/'MATCHED_CONTROLS.csv',paired)
    counts=Counter(r['status'] for r in result)
    save(out/'ACCEPTANCE.json',dict(status='COMPLETE' if not counts['NOT_RUN'] else 'PARTIAL',planned=len(result),counts=dict(counts),
        raw_responses_immutable=True,normalizer=entry(SWS_CODE/'interface_repair_v3/adapter.py'),scoring='Exact typed equality; null/invalid retained; missing separate; truncated scored as retained',
        scores=entry(out/'DIAGNOSTIC_MATRIX.csv'),matched=paired))
    print(json.dumps(dict(batch=a.batch,model=a.model,counts=counts)),flush=True)
if __name__=='__main__':main()
