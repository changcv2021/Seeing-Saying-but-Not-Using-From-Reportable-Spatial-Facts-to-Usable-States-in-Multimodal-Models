"""Hard discovery preflight, after answer-blind resource/panel freeze."""
import subprocess
from base import *
from build import construct
from mine import group_from_l4


def media_paths(media):
    """Mirror the already-used protocol's image/video/video_frames storage forms."""
    kind=media.get('kind','image')
    if kind in ['image','video']:
        path=media.get('path')
        if not isinstance(path,str) or not path: raise ValueError('INVALID_MEDIA_PATH')
        return [path]
    if kind=='video_frames':
        paths=media.get('paths')
        if not isinstance(paths,list) or not paths or not all(isinstance(p,str) and p for p in paths): raise ValueError('INVALID_FRAME_PATHS')
        return paths
    raise ValueError('UNSUPPORTED_MEDIA_KIND:'+kind)


def main():
    a=args(__doc__).parse_args(); cfg,root,project=setup(a)
    if a.dry_run: print(json.dumps(dict(status='PLANNED',action='preflight'))); return
    resource=load(root/'manifest/resource_plan.json'); auth=load(root/'manifest/gpu_authorization.json')
    plan=load(root/'manifest/discovery/request_plan.json'); partition=load(root/'manifest/cluster_split.json')['partition']
    req=list(rows(root/'inputs/discovery/requests.jsonl')); gold=list(rows(root/'gold/discovery/gold.jsonl'))
    checks=[]
    def check(name,ok,detail=None):
        checks.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=detail))
    check('resource_gate',resource['status']=='PASS' and resource['budget_authorized'] and auth['batch_authorized'])
    check('budget_and_hard_caps',resource['estimate']['total_gpu_hours_including_smoke']<=auth['total_gpu_hours'] and all(resource['estimate']['models'][m]['wall_seconds']<=auth['discovery_wall_caps_seconds'][m] for m in cfg['models']))
    check('immutable_input_hash',sha(root/'inputs/discovery/requests.jsonl')==plan['input_hash']==resource['discovery_input_hash'])
    check('immutable_gold_hash',sha(root/'gold/discovery/gold.jsonl')==plan['gold_hash'])
    check('unique_ids_exact_gold',set(unique(req,'request_id'))==set(unique(gold,'request_id')))
    check('discovery_worlds_only',all(partition[r['cluster_id']]=='discovery' and r.get('original_input',{}).get('split','dev')=='dev' for r in req))
    check('phase_A_boundary',cfg['stop_after_report'] and all(not cfg[k] for k in ['allow_whitebox','allow_training','allow_confirmation_inference','allow_official_test_new_inference']))
    replay,rg,private_groups=construct(cfg,root,'discovery',*resource['estimate']['caps'],persist=False)
    check('source_replay_matches_frozen_inputs_and_gold',req==replay and gold==rg)
    # Re-execute source transitions; do not merely trust the cached PASS string.
    prepath=project/'transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_7/prestates.count_v2.jsonl'
    preindex={}
    for r in rows(prepath):
        for f in r['pre_state_subgraph']['facts']:
            if f['predicate']=='COUNT': preindex[r['branch_id'],f['subject']]=(r,prepath)
    source_unchanged=all(e['available'] and sha(e['path'])==e['sha256'] for e in load(root/'reports/mining_report.json')['source_hashes'])
    check('mining_source_hashes_unchanged',source_unchanged)
    l4=unique(rows(project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'),'pair_id')
    proof_rows=[]; source_files={prepath}
    for g in private_groups:
        truth=g['private']; source_files.update(Path(p) for p in truth['extra_source_files'])
        if g['state_dimension']=='PRE_POST':
            pid=g['parent_ids'][0]
            regenerated,reason=group_from_l4(l4[pid],{pid:g['original_inputs']},preindex,cfg)
            good=regenerated is not None and regenerated['private']['values']==truth['values'] and regenerated['private']['claim_gold']==truth['claim_gold']
            proof_rows.append(dict(group_id=g['group_id'],status='PASS' if good else 'FAIL',reason=reason,replay=regenerated['private']['replay'] if regenerated else None))
        else:
            ev=load(truth['extra_source_files'][0])
            ff=[f for f in ev.get('facts',[]) if f.get('predicate')=='COUNT' and f.get('polarity','positive')=='positive' and type(f.get('value'))==int and str(f.get('subject','')).startswith('class:')]
            good=ff==truth['pre_facts'] and len(ff)==2 and all(f.get('provenance') for f in ff)
            proof_rows.append(dict(group_id=g['group_id'],status='PASS' if good else 'FAIL',reason=None if good else 'SOURCE_COUNT_FACTS_CHANGED',replay={'rule':'EXACT_SOURCE_FACT_RECORD_EQUALITY'}))
    check('independent_source_truth_reexecution',all(r['status']=='PASS' for r in proof_rows),dict(groups=len(proof_rows)))
    write(root/'reports/discovery_source_replay.json',dict(status='PASS' if all(r['status']=='PASS' for r in proof_rows) else 'FAIL',groups=proof_rows,
        source_files=[evidence_entry(p) for p in sorted(source_files)],gold_modified=False,model_guessed_gold=False))
    check('ordinary_gold_isolation',all(not {'gold','private','claim_gold','gold_by_state','reference_answer'}&set(r) for r in req))
    check('oracle_media_absent',all(not r['payload']['media'] for r in req if r['is_oracle']))
    media={path for r in req for m in r['payload']['media'] for path in media_paths(m)}
    bad=[p for p in sorted(media) if not Path(p).is_file() or Path(p).stat().st_size==0]
    check('all_required_media_exist_nonempty',not bad,dict(unique_files=len(media),missing_or_empty=bad,
        validation='File stat only here; actual pixel tensors hashed and cross-model checked during inference/finalization.'))
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-v','-s',str(CODE/'tests')],capture_output=True,text=True)
    write(root/'reports/discovery_scorer_tests.json',dict(status='PASS' if not tests.returncode else 'FAIL',stdout=tests.stdout,stderr=tests.stderr,returncode=tests.returncode))
    check('scorer_pairing_cache_tests',tests.returncode==0)
    # Freeze the actual small executable dependency set; never hashes model weights here.
    paths=[CODE/'src'/n for n in ['run.py','request_identity.py','base.py']]
    paths+=[CODE/'scripts/job.sh',a.config,CODE.parent/'spatial_conflict_diagnosis_v1/src/diaglib.py']
    paths+=[Path(cfg['campaign'])/'code'/n for n in ['protocol.py','vision_process_frozen.py']]
    result=dict(status='PASS' if all(c['status']=='PASS' for c in checks) else 'BLOCKED',checks=checks,
        request_plan=evidence_entry(root/'manifest/discovery/request_plan.json'),dependencies=[evidence_entry(p) for p in paths],
        original_review='USER_ATTESTED_PASS',derived_review='PROVISIONAL',sample_selection_used_model_accuracy=False)
    write(root/'reports/discovery_preflight.json',result)
    if result['status']=='PASS': frozen_write(root/'manifest/discovery_execution_freeze.json',result)
    print(json.dumps(dict(status=result['status'],checks=checks)))
    if result['status']!='PASS': raise SystemExit(2)


if __name__=='__main__': main()
