"""Apply only the user-approved exclusion list; preserve every test request."""
from collections import Counter,defaultdict
from common import *

def main():
    a=cli(__doc__).parse_args();root=a.run_root
    if a.dry_run: print('Apply approved exclusions in new directory '+str(root));return
    compute()
    if (root/'SPLIT_AUDIT.json').exists():
        if a.resume: print((root/'SPLIT_AUDIT.json').read_text());return
        raise FileExistsError(root/'SPLIT_AUDIT.json')
    if a.limit: raise ValueError('FULL_SPLIT_REQUIRED')
    for ent in read(OLD/'audit/source_hashes.json'):
        if Path(ent['path']).name in ('requests.jsonl','private_gold.jsonl','pairs.jsonl','pairs.l4_three_part_v3.jsonl'):
            if sha(ent['path'])!=ent['sha256']: raise ValueError('SOURCE_CHANGED:'+ent['path'])
    exclusions=list(rows(OLD/'physical_world_impact_v1/EXCLUSION_PROPOSAL_NOT_APPLIED.jsonl'))
    excluded={r['sample_id'] for r in exclusions}
    if Counter(r['split'] for r in exclusions)!=Counter(train=1646,dev=199): raise ValueError('APPROVED_COUNTS_CHANGED')
    gold=list(rows(FROZEN/'private_gold.jsonl'));requests=list(rows(FROZEN/'requests.jsonl'))
    restore={r['sample_id']:r for r in rows(OLD/'alias_verification_v1/recovered_world_metadata.jsonl')}
    for r in gold:
        if not r.get('global_world_id'): r['global_world_id']=restore[r['sample_id']]['global_world_id']
    g={r['sample_id']:r for r in gold}
    physical={r['global_world_id']:r['physical_group'] for r in rows(OLD/'physical_world_impact_v1/WORLD_GROUPS.jsonl')}
    worlds=set(physical);parent={w:w for w in worlds}
    def find(w):
        while w!=parent[w]:parent[w]=parent[parent[w]];w=parent[w]
        return w
    def union(ww):
        ww=sorted(ww)
        if not ww:return
        first=find(ww[0])
        for w in ww[1:]:parent[find(w)]=first
    bygroup=defaultdict(set);byhash=defaultdict(set)
    for w,p in physical.items():bygroup[p].add(w)
    for ww in bygroup.values():union(ww)
    for r in requests:
        for m in r.get('media',[]):
            if m.get('sha256'):byhash[m['sha256'].removeprefix('sha256:')].add(g[r['sample_id']]['global_world_id'])
    for ww in byhash.values():union(ww)
    canonical={w:'pss_world_'+digest(sorted(x for x in worlds if find(x)==find(w)))[:24] for w in worlds}
    split_worlds=defaultdict(set);totals={};group_counts=[];files={}
    original_test=[r for r in requests if r['split']=='test']
    for split in ('train','dev','test'):
        public=[r for r in requests if r['split']==split and r['sample_id'] not in excluded]
        private=[dict(g[r['sample_id']],underlying_world_id=canonical[g[r['sample_id']]['global_world_id']]) for r in public]
        if split=='test' and public!=original_test:raise ValueError('TEST_CHANGED')
        split_worlds[split]={r['underlying_world_id'] for r in private}
        totals[split]=len(public)
        for level,n in sorted(Counter(r['level'] for r in public).items()):group_counts.append(dict(split=split,level=level,n=n))
        for name,data in [('requests',public),('private_gold',private)]:
            path=root/'data'/split/(name+'.jsonl');write(path,data,True);files[str(path.relative_to(root))]=sha(path)
    if totals!={'train':13476,'dev':3267,'test':5608}:raise ValueError('FROZEN_COUNTS_MISMATCH')
    for s,t in [('train','dev'),('train','test'),('dev','test')]:
        if split_worlds[s]&split_worlds[t]:raise ValueError('WORLD_OVERLAP:'+s+'/'+t)
    write(root/'data/exclusions.jsonl',exclusions,True)
    write(root/'data/world_groups.jsonl',[dict(global_world_id=w,underlying_world_id=c) for w,c in sorted(canonical.items())],True)
    write(root/'USER_APPROVAL.json',dict(user_message='我觉得没问题',scope='Apply proposed train 1646/dev 199 exclusions; keep all 5608 test inputs unchanged',
        source_proposal_sha256=sha(OLD/'physical_world_impact_v1/EXCLUSION_PROPOSAL_NOT_APPLIED.jsonl'),original_sources_modified=False))
    result=dict(status='PASS_FROZEN_SOURCE_ID_PHYSICAL_SPACE_AND_EXACT_MEDIA_RULES',samples=totals,by_level=group_counts,
        worlds={s:len(w) for s,w in split_worlds.items()},files=files,test_payload_equal_to_original=True,
        known_alias_policy='source catalog + ScanNet physical space ID + exact media connected components',
        limitations=['No claim to exhaustive physical identity for datasets without official scene IDs'],
        seeds=SEEDS,job_id=os.environ['SLURM_JOB_ID'],code_sha256=sha(__file__))
    write(root/'SPLIT_AUDIT.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
