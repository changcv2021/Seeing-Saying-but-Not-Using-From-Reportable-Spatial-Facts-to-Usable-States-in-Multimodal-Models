"""CPU source build, fixed parser tests and actual three-model processor manifests."""
import subprocess
from collections import defaultdict
from b0common import *
from pipeline_v3 import Pipeline


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Build and validate frozen B0 draft prompts/actual processor; no model generation'); return
    compute()
    save(root/'manifest/model_inventory.json',load(root/'manifest/source_inventory.json')['model_inventory'])
    cmd=[sys.executable,str(CODE/'build.py'),'--config',str(a.config),'--run-id',a.run_id,'--seed',str(a.seed),'--resume']
    subprocess.run(cmd,check=True)
    test=subprocess.run([sys.executable,'-m','unittest','-v','test_b0'],capture_output=True,text=True)
    save(root/'reports'/f'engineering_tests_{os.environ["SLURM_JOB_ID"]}.json',dict(returncode=test.returncode,stdout=test.stdout,stderr=test.stderr))
    if test.returncode: raise ValueError('B0_ENGINEERING_TEST_FAILED')
    panels=list(rows(root/'02_B0_PANEL_MANIFEST.jsonl')); panel={r['group_id']:r for r in panels}
    required={r['group_id']:r['presentation_hash'] for r in csvrows(Path(c['a1_root'])/'review/researcher_records.csv') if r['new_review_status']=='VERIFIED_FOR_A1'}
    requests=list(rows(root/'inputs/smoke/requests.jsonl'))+list(rows(root/'inputs/core/requests.jsonl'))
    pure=defaultdict(set); index=[]; checks=[]
    for key in c['models']:
        pipe=Pipeline(c,key); records=[]; seen=set()
        for n,r in enumerate(requests,1):
            batch,pres,images=pipe.process(r)
            records.append(pres)
            if r['payload']['media'] and r['stage']=='core':
                gid=r['group_id']; pure[gid].add(pres['presentation_hash'])
                if gid in required and required[gid]!=pres['presentation_hash']: raise ValueError('A1_B0_PURE_MEDIA_DIFFERS')
                if gid not in seen:
                    checks.append(dict(model=key,world_id=r['underlying_world_id'],group_id=gid,presentation_hash=pres['presentation_hash'],
                        source_media_count=len(pres['media']),processed_sizes=pres['image_sizes'],input_tokens=pres['input_tokens'],
                        status='ACTUAL_PROCESSOR_RENDERED_SOURCE_HASH_VERIFIED',human_review_performed=False,
                        scope='DIGITAL_INPUT_INTEGRITY_NOT_PROOF_OF_VISUAL_COUNT_OBSERVABILITY'))
                    if key==c['primary_model']:
                        from PIL import Image,ImageDraw
                        board=Image.new('RGB',(320*len(images),290),'white'); draw=ImageDraw.Draw(board)
                        for i,im in enumerate(images):
                            view=im.copy(); view.thumbnail((320,240)); board.paste(view,(i*320,35))
                        draw.text((4,4),r['underlying_world_id']+' | '+panel[gid]['category'],fill='black')
                        path=root/'review'/f'{gid}.jpg'; path.parent.mkdir(parents=True,exist_ok=True)
                        if not path.exists(): board.save(path,quality=88)
                    seen.add(gid)
            if n%100==0: print(json.dumps(dict(model=key,processor_done=n,total=len(requests))),flush=True)
            del batch
        path=root/'preflight'/f'{key}.jsonl'; save(path,records,'jsonl'); index.append(entry(path))
        del pipe
    if any(len(v)!=1 for v in pure.values()) or len(pure)!=len(panels): raise ValueError('CONDITION_OR_MODEL_VISUAL_HASH_MISMATCH')
    union_csv(root/'review/processor_checks.csv',checks)
    save(root/'manifest/preflight_index.json',dict(status='PASS',files=index,requests_per_model=len(requests),worlds=len(panels),
        source_review_policy=c['review_policy'],visual_conditions_identical=True,model_panels_identical=True))
    # Frozen setup-only lock; final core lock will additionally include the analysis code/rules.
    save(root/'manifest/smoke_lock.json',dict(status='FROZEN_ENGINEERING_SMOKE',inputs_sha256=sha(root/'inputs/smoke/requests.jsonl'),
        config_sha256=sha(a.config),code=dependency_files(c),requests_per_model=8,preflight=entry(root/'manifest/preflight_index.json')))
    save(root/'LIVE_STATUS.json',dict(status='PROCESSOR_PASS_READY_FOR_FIXED_SMOKE',core_responses=0,worlds=len(panels),
                                    build=load(root/'manifest/build_summary.json')),frozen=False)
    print('B0_PREPARE_PASS',flush=True)


if __name__=='__main__': main()
