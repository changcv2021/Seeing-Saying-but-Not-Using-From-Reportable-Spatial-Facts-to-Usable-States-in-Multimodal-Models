"""Compile the first real batch from source facts, never from model predictions."""
from collections import defaultdict, Counter
import shutil
from common_auto_v2 import *
from real_design_v1 import *

REV='080812355c21a40f437ed03d4ae558d35bfa2929'
SOURCE_IMAGES=Path('external/upstream/data/full_media_incoming/ca_vqa')/REV/'val/cavqa_val_extracted'
BUNDLE=Path('artifacts')


def runtime_files(c):
    project=Path(c['project']); pipeline=project/'research/state_binding_phase_a1/core_execution_v3'
    names=['common.py','common_auto_v2.py','review_policy_v2.py','config_auto_v2.json','contracts.py',
           'real_design_v1.py','real_compile_v1.py','real_tests_v1.py','real_processor_v1.py',
           'real_worker_v1.py','real_score_v1.py','real_job_v1.sh','e0_snapshot.py']
    paths=[CODE/x for x in names]+[pipeline/x for x in ('pipeline_v3.py','v3common.py')]
    paths += [Path(c['campaign'])/'code'/x for x in ('protocol.py','vision_process_frozen.py')]
    paths += [Path(c['campaign'])/'config.json',Path(c['package'])/'tools/research_utils.py',
              project/'scripts/full_multimodel_split_v5/gpu_health.py',Path(c['review_waiver_record'])]
    return [entry(p) for p in paths]


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a); out=root/'batches'/BATCH
    if a.dry_run: print('24-world maximum real CA-VQA discovery batch; no model outputs read'); return
    if (out/'manifest/REQUEST_LOCK.json').exists():
        old=load(out/'manifest/REQUEST_LOCK.json')
        for ref in old['code']+old['public_inputs']+old['private_inputs']:
            if sha(ref['path'])!=ref['sha256']: raise ValueError('FROZEN_BATCH_CHANGED:'+ref['path'])
        print('REUSED_FROZEN_REAL_BATCH'); return
    import io, unittest
    from real_tests_v1 import DesignTests
    buf=io.StringIO(); tested=unittest.TextTestRunner(stream=buf,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DesignTests))
    save(out/'reports'/('design_tests_'+os.environ['SLURM_JOB_ID']+'.log'),buf.getvalue(),'text')
    if not tested.wasSuccessful(): raise RuntimeError(buf.getvalue())
    inventory=root/'repairs/world_identity_v2/inventory/manifest/world_candidate_inventory.jsonl'
    catalog=root/'repairs/world_identity_v2/inventory/private_gold/source_fact_catalog.jsonl'
    verified=load(root/'repairs/world_identity_v2/REPAIR_ACCEPTANCE.json')
    expected={x['path']:x['sha256'] for x in verified['output_files']}
    for p in (inventory,catalog):
        if sha(p)!=expected[str(p)]: raise ValueError('SOURCE_INVENTORY_CHANGED')
    allworlds={r['world_cluster_id']:r for r in rows(inventory)}
    worlds={w:r for w,r in allworlds.items() if w.startswith('arkitscenes:')
            and r['source_membership']['previously_exposed']
            and r['source_membership']['allowed_future_split']=='DISCOVERY_ONLY'
            and not r['source_membership']['reasons']}
    groups=defaultdict(dict); rejects=[]
    for row in rows(catalog):
        w=row['world_cluster_id']; f=row['fact']
        if w not in worlds or f['provenance']['source_dataset']!='CA-VQA' or not qualified_fact(f): continue
        roles=f.get('grounding',{}).get('frame_roles',{})
        if set(roles)!={'reference_frame','support_frame_1','support_frame_2','support_frame_3','support_frame_4'}: continue
        if any(not v.startswith('cavqa_val/images/') for v in roles.values()): continue
        typ='COUNT' if f['predicate']=='COUNT' else 'NONCOUNT_RELATION'
        key=(w,typ,digest(roles))
        # Duplicate semantic facts with disagreeing values are excluded, not majority-voted.
        fk=(f['subject'].split('@source_item:')[0],f['predicate'],str(f.get('object')).split('@source_item:')[0])
        if fk in groups[key] and fact_value(groups[key][fk]['fact'])!=fact_value(f):
            rejects.append(dict(world_cluster_id=w,code='CONFLICTING_SAME_FRAME_SOURCE_FACT',fact_key=fk))
            groups[key][fk]['conflicted']=True
        elif fk not in groups[key]: groups[key][fk]=row
    pairs=defaultdict(list)
    for (w,typ,framekey), ff in groups.items():
        ff=sorted([r for r in ff.values() if not r.get('conflicted')],key=lambda r:digest([c['seed'],'SOURCE_FACT',w,r['fact']['fact_id']]))
        for aa in ff:
            for bb in ff:
                if independent_facts(aa['fact'],bb['fact']):
                    pairs[(w,typ)].append((digest([c['seed'],'SOURCE_PAIR',w,aa['fact']['fact_id'],bb['fact']['fact_id']]),aa,bb))
    selected=[]; used=set(); source_cache={}; used_assets=set(); used_visual_hashes=set()
    source_refs={}; media_refs={}; media_provenance=[]
    quota=[('COUNT','ADD',3),('COUNT','REMOVE_POST_POSITIVE',3),('COUNT','REMOVE_POST_ZERO',3),('COUNT','PROTECTION_NOOP',3),('NONCOUNT_RELATION',None,12)]
    rank_order=[]
    for typ,sub,n in quota:
        eligible=sorted({w for w,t in pairs if t==typ},key=lambda w:digest([c['seed'],'REAL_D01_'+str(sub or typ),w]))
        accepted=0
        for w in eligible:
            if w in used: continue
            rank_order.append(dict(world_cluster_id=w,primary_stratum=typ,count_substratum=sub,
                                   rank=digest([c['seed'],'REAL_D01_'+str(sub or typ),w])))
            options=sorted(pairs[(w,typ)],key=lambda p:p[0])
            if sub=='REMOVE_POST_POSITIVE': options=[p for p in options if fact_value(p[1]['fact'])>=2]
            if sub=='REMOVE_POST_ZERO': options=[p for p in options if fact_value(p[1]['fact'])==1]
            if not options: continue
            _,ra,rb=options[0]; facts=[ra['fact'],rb['fact']]
            roles=facts[0]['grounding']['frame_roles']
            try:
                for rr in (ra,rb):
                    ref=rr['source_graph']; path=ref['path']
                    if path not in source_cache:
                        if sha(path)!=ref['sha256']: raise ValueError('SOURCE_GRAPH_HASH_MISMATCH')
                        source_cache[path]={f['fact_id']:f for f in load(path)['facts']}
                    if source_cache[path].get(rr['fact']['fact_id'])!=rr['fact']: raise ValueError('FACT_REPLAY_MISMATCH')
                    source_refs[path]=ref
                mm=[]
                from PIL import Image, ImageOps
                for role,member in sorted(roles.items(),key=lambda kv:(kv[0]!='reference_frame',kv[0])):
                    src=SOURCE_IMAGES/member
                    if not src.is_file(): raise ValueError('SOURCE_MEDIA_MISSING:'+str(src))
                    hh=sha(src)
                    with Image.open(src) as im:
                        im.verify()
                    with Image.open(src) as im:
                        tiny=ImageOps.grayscale(im).resize((16,16))
                        perceptual=bytes(int(x)//16 for x in tiny.getdata())
                    if role=='reference_frame' and (hh in used_assets or digest(list(perceptual)) in used_visual_hashes):
                        raise ValueError('EXACT_OR_QUANTIZED_REFERENCE_DUPLICATE')
                    cached=[BUNDLE/'media/l1_l3'/(hh[:24]+suffix) for suffix in ('.png','.jpg')]
                    dst=next((p for p in cached if p.is_file() and sha(p)==hh),None)
                    if dst is None:
                        dst=out/'media'/(hh+'.image'); dst.parent.mkdir(parents=True,exist_ok=True)
                        if dst.exists() and sha(dst)!=hh: raise ValueError('PERSISTENT_MEDIA_CONFLICT')
                        if not dst.exists(): shutil.copyfile(src,dst)
                    if sha(dst)!=hh: raise ValueError('COPIED_MEDIA_HASH_MISMATCH')
                    media_provenance.append(dict(world_cluster_id=w,role=role,source=entry(src),persistent=entry(dst)))
                    mm.append(dict(kind='image',path=str(dst),role=role,sha256='sha256:'+hh,presentation_max_pixels=401408))
                    media_refs[str(dst)]=entry(dst)
                    if role=='reference_frame': refhash=hh; phash=digest(list(perceptual))
                panel=dict(world_cluster_id=w,primary_stratum=typ,count_substratum=sub,split='discovery',
                           source_membership=worlds[w]['source_membership'],facts=facts,
                           source_graphs=[ra['source_graph'],rb['source_graph']],media=mm,
                           review_status=c['review']['default_review_status'],scientific_review_grade='AUTO_ONLY_PROVISIONAL',
                           genuine_multiview_necessity=False,reference_only_sufficiency='SOURCE_REFERENCE_FRAME_QA',
                           independent_fact_scope='DIFFERENT_CATEGORY_COUNTS_OR_DISJOINT_NAMED_ENTITY_CLASSES')
                selected.append(panel); used.add(w); used_assets.add(refhash); used_visual_hashes.add(phash); accepted+=1
            except (ValueError,FileNotFoundError,OSError) as exc:
                rejects.append(dict(world_cluster_id=w,primary_stratum=typ,code=str(exc))); continue
            if accepted==n: break
    if not selected: raise ValueError('NO_QUALIFIED_SOURCE_WORLDS')
    reqs=[]; gold=[]; matched=[]; aliases=[]
    for panel in selected:
        rr,gg,mm,aa=build_world(c,panel,panel['media']); reqs+=rr; gold+=gg; matched+=mm; aliases+=aa
    if len({r['request_id'] for r in reqs})!=len(reqs): raise ValueError('DUPLICATE_PHYSICAL_REQUEST_ID')
    if {r['request_id'] for r in reqs}!={g['request_id'] for g in gold}: raise ValueError('PUBLIC_PRIVATE_ID_MISMATCH')
    save(out/'private_gold/world_panel.jsonl',selected,'jsonl')
    save(out/'private_gold/request_gold.jsonl',gold,'jsonl')
    save(out/'private_gold/logical_aliases.jsonl',aliases,'jsonl')
    save(out/'private_gold/matched_structure.jsonl',matched,'jsonl')
    save(out/'manifest/world_allocation.jsonl',[{k:p[k] for k in ('world_cluster_id','primary_stratum','count_substratum','split','review_status','scientific_review_grade')} for p in selected],'jsonl')
    save(out/'manifest/source_selection_order.jsonl',rank_order,'jsonl')
    save(out/'manifest/rejects.jsonl',rejects,'jsonl')
    save(out/'manifest/media_provenance.jsonl',media_provenance,'jsonl')
    save(out/'public_inputs/requests.jsonl',reqs,'jsonl')
    # Four six-world shards: preserve whole matched bundles, no model-to-model barrier.
    ordered=sorted(selected,key=lambda p:digest([c['seed'],'REAL_D01_SHARD',p['world_cluster_id']]))
    shard_rows=[]
    for sid,start in enumerate(range(0,len(ordered),6)):
        ww={p['world_cluster_id'] for p in ordered[start:start+6]}; path=out/f'public_inputs/shard_{sid:03}.jsonl'
        ss=[r for r in reqs if r['world_cluster_id'] in ww]; save(path,ss,'jsonl')
        shard_rows.append(dict(shard=sid,worlds=len(ww),requests=len(ss),request_file=entry(path)))
    save(out/'manifest/shards.json',shard_rows)
    checks={name:'PASS' for name in ('source_truth','media_files','query_derivation','world_split','gold_separation','request_hashes')}
    decision=execution_decision(c,load(c['review_waiver_record']),checks)
    assert decision['can_proceed']
    report=dict(status='COMPILED_SOURCE_CHECKS_PASS_PROCESSOR_PENDING',created_at=now(),job_id=os.environ['SLURM_JOB_ID'],
                batch=BATCH,worlds=len(selected),requests_per_model=len(reqs),logical_requests=len(aliases),
                primary_strata=dict(Counter(p['primary_stratum'] for p in selected)),
                count_substrata=dict(Counter(p['count_substratum'] for p in selected if p['count_substratum'])),
                logical_module_requests=dict(Counter(a['experiment'] for a in aliases)),
                models=c['models'],shards=shard_rows,design_tests=tested.testsRun,review_policy=decision,
                gold_created_from_model=False,model_prediction_files_read=0,
                current_batch_scope='FIRST_REAL_DISCOVERY_BATCH_NOT_ALL_480_WORLDS_OR_FULL_STUDY',
                coverage_limits=['NATIVE_REFERENCE_IMAGE_SUFFICIENT_NOT_GENUINE_MULTIVIEW_FUSION',
                  'NONCOUNT_BOOLEAN_POLARITY_IS_SECONDARY_NOT_MULTIVALUE_INTRUSION_EVIDENCE',
                  'E7_E8_M1_M2_C1_C2_NOT_COMPILED_IN_THIS_BATCH',
                  'ONLY_PREVIOUSLY_EXPOSED_DISCOVERY_WORLDS_NO_NEW_HOLDOUT_CLAIM',
                  'NEW_OBSERVATION_CONTROL_NOT_AVAILABLE_NO_FABRICATED_NEW_MEDIA'])
    save(out/'reports/COMPILE_ACCEPTANCE.json',report)
    lock=dict(batch=BATCH,run_id=c['run_id'],status='FROZEN_REAL_REQUESTS_PENDING_PROCESSOR',created_at=now(),config_snapshot=c,
              selection_rule='SOURCE_ONLY_SEED_HASH_12_COUNT_12_RELATION_EXPOSED_DISCOVERY',
              quotas=quota,code=runtime_files(c),public_inputs=[entry(out/'public_inputs/requests.jsonl'),entry(out/'manifest/shards.json')]+[r['request_file'] for r in shard_rows],
              private_inputs=[entry(out/'private_gold'/n) for n in ('world_panel.jsonl','request_gold.jsonl','logical_aliases.jsonl','matched_structure.jsonl')],
              media=list(media_refs.values()),source_graphs=list(source_refs.values()),
              source_inventory=entry(inventory),source_fact_catalog=entry(catalog),
              E6_selection='ALL_24_WORLD_FIRST_BATCH_COUNTS_TOWARDS_144_CAP',
              global_quotas_unchanged=True,models=c['models'],human_gate=False,
              active_policy=entry(root/'scheduler/ACTIVE_EXECUTION_POLICY.json'))
    save(out/'manifest/REQUEST_LOCK.json',lock)
    print(json.dumps({k:report[k] for k in ('status','worlds','requests_per_model','primary_strata','count_substrata','logical_module_requests')},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
