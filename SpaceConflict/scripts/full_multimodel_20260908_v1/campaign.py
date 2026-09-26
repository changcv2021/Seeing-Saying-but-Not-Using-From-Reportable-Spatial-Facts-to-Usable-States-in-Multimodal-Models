"""CPU preparation, immutable model registry, parser audits and bounded submission."""
import argparse, collections, csv, hashlib, json, math, os, shutil, socket, subprocess, sys, time
from pathlib import Path
from common import load, unique, sha, write, parse, RUBRIC, LABELS
from output_policy import parse_prediction, gate_usable

CODE=Path(__file__).resolve().parent
PROJECT=CODE.parent.parent
INDUSTRY=PROJECT.parent.parent/'industry'
ROOT=Path('artifacts/model_results/full_multimodel_20260908_v1')
SOURCE=ROOT.parent/'qwen2_5_vl_7b/full_release_qwen35judge_v2_scans_20260905'
RUN_ID=ROOT.name
SEED=20260904

def args():
    p=argparse.ArgumentParser(__doc__);p.add_argument('action',nargs='?',default='fixtures');p.add_argument('--model',default='qwen25vl_7b')
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--limit',type=int);p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED:raise ValueError('RUN_ID_SEED_MISMATCH')
    return a

def frozen(path,obj,jsonl=False):
    if Path(path).exists():
        existing=load(path) if jsonl else json.loads(Path(path).read_text())
        if existing!=obj:raise ValueError('PRESERVE_EXISTING:'+str(path))
    else:write(path,obj,jsonl=jsonl)

def registry():return json.loads((ROOT/'registry.json').read_text())

def verify():
    lock=json.loads((ROOT/'protocol_lock.json').read_text())
    for path,digest in lock['files'].items():
        if sha(path)!=digest:raise ValueError('FROZEN_INPUT_OR_CODE_CHANGED:'+path)

def model_check(m):
    p=Path(m['model_path']);index=p/'model.safetensors.index.json'
    names=sorted(set(json.loads(index.read_text())['weight_map'].values())) if index.exists() else ['model.safetensors']
    files=[p/name for name in names];missing=[str(f) for f in files if not f.is_file() or not f.stat().st_size]
    return dict(status='READY' if not missing else 'MISSING_WEIGHTS',missing=missing,
        weight_bytes=sum(f.stat().st_size for f in files if f.is_file()),shards=len(files),
        model_config_sha256=sha(p/'config.json') if (p/'config.json').exists() else None)

def prepare(a):
    import cv2
    from PIL import Image
    ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'logs').mkdir(exist_ok=True)
    reference=json.loads((PROJECT/'scripts/qwen35_scale_512_v1/config.json').read_text())
    for name,digest in reference['input_hashes'].items():
        if sha(SOURCE/name)!=digest:raise ValueError('SOURCE_INPUT_CHANGED:'+name)
    source=load(SOURCE/'requests.jsonl');unique(source)
    if len(source)!=24196:raise ValueError('FULL_DENOMINATOR_CHANGED')
    checked={};frames={};requests=[];media_log=[]
    def check(path,expected=None):
        path=str(path)
        if path not in checked:
            if not Path(path).is_file():raise ValueError('MISSING_MEDIA:'+path)
            checked[path]=sha(path)
        if expected and checked[path]!=expected.removeprefix('sha256:'):raise ValueError('MEDIA_HASH_MISMATCH:'+path)
        return checked[path]
    for number,sample in enumerate(source,1):
        output=dict(sample);output['media']=[]
        for media in sample['media']:
            kind=media.get('kind','image');role=media.get('role','media')
            if kind=='image':
                check(media['path'],media.get('sha256'));output['media'].append(dict(media,presentation_max_pixels=401408));continue
            if kind=='video_frames':
                paths=media['paths'];indices=list(range(len(paths)))
                if len(paths)>16:indices=[round(i*(len(paths)-1)/15) for i in range(16)]
                selected=[(paths[i],i,None) for i in indices]
            elif kind=='video':
                path=media['path'];digest=check(path,media.get('sha256'))
                if digest not in frames:
                    cap=cv2.VideoCapture(path);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=float(cap.get(cv2.CAP_PROP_FPS))
                    if not cap.isOpened() or total<1 or fps<=0:raise ValueError('VIDEO_METADATA_INVALID:'+path)
                    count=min(total,16);indices=[round(i*(total-1)/max(1,count-1)) for i in range(count)];selected=[]
                    directory=ROOT/'frames'/digest;directory.mkdir(parents=True,exist_ok=True)
                    for i in indices:
                        out=directory/f'{i:09d}.png'
                        if not out.exists():
                            cap.set(cv2.CAP_PROP_POS_FRAMES,i);ok,pixels=cap.read()
                            if not ok:raise ValueError('VIDEO_FRAME_DECODE_FAILED:'+path+':'+str(i))
                            Image.fromarray(cv2.cvtColor(pixels,cv2.COLOR_BGR2RGB)).save(out)
                        selected.append((str(out),i,i/fps))
                    cap.release();frames[digest]=selected
                selected=frames[digest]
            else:raise ValueError('UNSUPPORTED_MEDIA_KIND:'+kind)
            for position,(path,index,seconds) in enumerate(selected,1):
                desc=f'{role}; ordered video frame {position}/{len(selected)}; source index {index}'
                if seconds is not None:desc+=f'; time {seconds:.6f} seconds'
                output['media'].append(dict(kind='image',path=str(path),sha256='sha256:'+check(path),role=desc,
                    presentation_max_pixels=200704,source_media_kind=kind,source_frame_index=index))
        requests.append(output)
        if number%1000==0:print(json.dumps(dict(prepared=number,total=len(source),media_checked=len(checked))),flush=True)
    # Selection is deterministic, non-test, metadata-stratified; no model outcome or gold label access.
    groups=collections.defaultdict(list)
    for r in requests:
        if r['split']!='test':groups[(r['level'],r['dataset'],r['component'])].append(r)
    for values in groups.values():values.sort(key=lambda r:hashlib.sha256((str(SEED)+r['sample_id']).encode()).hexdigest())
    smoke=[]
    while len(smoke)<96:
        changed=False
        for key in sorted(groups):
            if groups[key] and len(smoke)<96:smoke.append(groups[key].pop(0));changed=True
        if not changed:break
    if len(smoke)!=96 or any(r['split']=='test' for r in smoke):raise ValueError('SMOKE_SELECTION_FAILED')
    frozen(ROOT/'requests.jsonl',requests,True);frozen(ROOT/'smoke.jsonl',smoke,True)
    frozen(ROOT/'media_manifest.jsonl',[dict(path=p,sha256=h) for p,h in sorted(checked.items())],True)
    for name in ['private_gold.jsonl','rubric.json','unavailable.jsonl']:
        dest=ROOT/name
        if not dest.exists():shutil.copy2(SOURCE/name,dest)
        if sha(dest)!=sha(SOURCE/name):raise ValueError('GOLD_OR_RUBRIC_CHANGED')
    models=[]
    for filename in ['qwen_family_eval_v1.json','diverse_family_eval_v1.json']:
        models+=json.loads((INDUSTRY/'protocol'/filename).read_text())['models']
    env=json.loads((INDUSTRY/'reports/qwen25vl7b_full_eval_20260902/environment.json').read_text())
    models.insert(0,dict(key='qwen25vl_7b',model_id=env['model_id'],model_path=env['model_path'],revision=env['model_revision'],gpus=1,mode='direct'))
    models.insert(1,dict(key='qwen25vl_32b',model_id='Qwen/Qwen2.5-VL-32B-Instruct',
        model_path='artifacts/model_cache/Qwen2.5-VL-32B-Instruct',gpus=2,mode='direct'))
    from huggingface_hub import HfApi, get_hf_file_metadata, hf_hub_url, get_token
    api=HfApi();access={}
    for m in models:
        if m.get('manifest_path') and Path(m['manifest_path']).exists():m['revision']=json.loads(Path(m['manifest_path']).read_text())['revision']
        if not m.get('revision'):
            try:m['revision']=api.model_info(m['model_id']).sha
            except Exception as exc:
                m['revision']=None;m['blocked_reason']='OFFICIAL_REVISION_UNVERIFIED:'+type(exc).__name__
        if m['key']=='llama4_scout':
            try:
                get_hf_file_metadata(hf_hub_url(m['model_id'],'config.json',revision=m['revision']),token=get_token())
                access[m['key']]='ACCESS_CONFIRMED_BUT_SINGLE_NODE_BF16_TOO_LARGE_QUANTIZATION_NOT_VALIDATED'
            except Exception as exc:access[m['key']]='ACCESS_BLOCKED:'+type(exc).__name__
            m['enabled']=False;m['blocked_reason']=access[m['key']]
        else:m['enabled']=m['revision'] is not None
        m['availability']=model_check(m);m['model']=m['model_id'];m['run_id']=RUN_ID+'_'+m['key'];m['seed']=SEED
        m['decode']=dict(do_sample=False,max_new_tokens=512);m['scoring_policy']='retained_prefix_512_v1'
        m['prompt_version']='ordered_frames_bare_json_512_v1';m['replicas']=4//m['gpus']
        m['media_budget']=dict(min_pixels=100352,max_pixels=401408,video_max_pixels=200704,video_frames=16)
        m['enable_thinking']=m['mode']=='thinking'
        m['input_hashes']={name:sha(ROOT/name) for name in ['requests.jsonl','smoke.jsonl','private_gold.jsonl','rubric.json','unavailable.jsonl']}
        directory=ROOT/m['key'];directory.mkdir(exist_ok=True)
        for name in m['input_hashes']:
            if not (directory/name).exists():os.symlink(ROOT/name,directory/name)
        frozen(directory/'config.json',m)
    frozen(ROOT/'registry.json',{m['key']:m for m in models})
    # Save the historical parser failure evidence without using it to select requests.
    history=[]
    for path in sorted((SOURCE/'full').glob('predictions_*.jsonl')):
        source_digest=sha(path)
        for r in load(path):
            original=r.get('raw_response','');old=parse(original);revised=parse_prediction(dict(r,generated_tokens=min(r.get('generated_tokens',0),512)))
            if old['label']!=revised['label']:history.append(dict(sample_id=r['sample_id'],raw_response=original,
                strict_label=old['label'],fence_prefix_label=revised['label'],source_file=str(path),source_sha256=source_digest))
    frozen(ROOT/'historical_format_differences.jsonl',history,True)
    files=list(CODE.glob('*.py'))+list(CODE.glob('*.sh'))+[PROJECT/'src/spaceconflict/mllm_l4.py']
    files +=[ROOT/name for name in ['requests.jsonl','smoke.jsonl','private_gold.jsonl','rubric.json','media_manifest.jsonl','registry.json']]
    files +=[ROOT/m['key']/'config.json' for m in models]
    frozen(ROOT/'protocol_lock.json',dict(run_id=RUN_ID,seed=SEED,files={str(p):sha(p) for p in files},source_hashes=reference['input_hashes'],
        expected_inputs=24196,smoke=96,smoke_test_inputs=0,gold_unchanged=True,prompt_tuning_on_test=False,
        registered_models=len(models),max_node_gpus=4,maximum_nodes=12,maximum_wall_hours_per_stage=48))
    frozen(ROOT/'preflight.json',dict(status='PASS',inputs=len(requests),smoke=len(smoke),media_files=len(checked),
        media_bytes=sum(Path(p).stat().st_size for p in checked),historical_format_differences=len(history),access=access,
        by_level=dict(collections.Counter(r['level'] for r in requests)),models={m['key']:m['availability'] for m in models}))

def download(a):
    verify();m=registry()[a.model]
    if m['key']!='qwen25vl_32b':raise ValueError('ONLY_EXPLICIT_MISSING_32B_DOWNLOAD_ALLOWED')
    from huggingface_hub import snapshot_download
    snapshot_download(m['model_id'],revision=m['revision'],local_dir=m['model_path'],max_workers=4,
        allow_patterns=['*.json','*.safetensors','*.jinja','*.txt','*.model'])
    record=model_check(m);record.update(model_id=m['model_id'],revision=m['revision'])
    frozen(ROOT/a.model/'download_manifest.json',record)
    if record['status']!='READY':raise ValueError('DOWNLOAD_INCOMPLETE')

def score(a,scope='smoke',gate=False):
    verify();m=registry()[a.model]
    if a.model!='qwen25vl_7b' and not (ROOT/'SCORING_GATE.json').exists():raise ValueError('7B_SCORING_GATE_REQUIRED')
    request_name='smoke.jsonl' if scope=='smoke' else 'requests.jsonl'
    config_digest=sha(ROOT/a.model/'config.json')
    for file in (ROOT/a.model/scope).glob('predictions_*.jsonl'):
        for pred in load(file):
            if (pred['model_id'],pred['model_revision'],pred['run_id'],pred['config_sha256'],pred['requested_samples_sha256'])!=(
                m['model_id'],m['revision'],m['run_id'],config_digest,m['input_hashes'][request_name]):
                raise ValueError('PREDICTION_MODEL_INPUT_PROVENANCE_MISMATCH')
            if pred.get('gold_access_attempts',0) or pred.get('generated_tokens',0)>512:raise ValueError('GOLD_OR_TOKEN_PROTOCOL_VIOLATION')
            if not pred.get('error') and pred.get('max_new_tokens')!=512:raise ValueError('GENERATION_BUDGET_MISMATCH')
    import base_score
    from types import SimpleNamespace
    base_score.score(SimpleNamespace(run_root=ROOT/a.model,run_id=m['run_id'],scope=scope,gate=False))
    if not gate:return
    rows=load(ROOT/a.model/scope/'predictions_000.jsonl')
    req=load(ROOT/'smoke.jsonl');gold=unique(load(ROOT/'private_gold.jsonl'))
    if len(rows)!=96 or {r['sample_id'] for r in rows}!={r['sample_id'] for r in req}:raise ValueError('SMOKE_INCOMPLETE')
    diagnostic=[]
    for r in rows:
        p=parse_prediction(r);old=parse(r.get('raw_response',''));g=gold[r['sample_id']]['gold']
        diagnostic.append(dict(sample_id=r['sample_id'],gold=g,strict_label=old['label'],parsed_label=p['label'],
            strict_correct=old['label']==g,parsed_correct=p['label']==g,fence_removed=p['fence_removed'],prefix_recovered=p['prefix_recovered'],
            finish_reason=r.get('finish_reason'),channel_status=r.get('channel_status'),error=r.get('error'),
            raw_generated=r.get('raw_generated_special'),final_response=r.get('raw_response')))
    frozen(ROOT/a.model/'interface_audit.jsonl',diagnostic,True)
    usable=sum(gate_usable(parse_prediction(r),r) for r in rows);errors=sum(bool(r.get('error')) for r in rows)
    record=dict(status='PASS' if errors==0 and usable/96>=.95 else 'BLOCKED_INTERFACE_OR_RUNTIME',n=96,usable=usable,
        runtime_errors=errors,format_only_label_recoveries=sum(r['strict_label'] is None and r['parsed_label'] is not None for r in diagnostic),
        accuracy_is_not_gate=True,parser_tests=json.loads((ROOT/'parser_tests.json').read_text()),max_new_tokens=512)
    frozen(ROOT/a.model/'interface_gate.json',record)
    if record['status']!='PASS':raise ValueError('INTERFACE_GATE_BLOCKED_NO_FULL_RUN')

def certify(a):
    verify();p=ROOT/'qwen25vl_7b';gate=json.loads((p/'interface_gate.json').read_text())
    judges=load(p/'smoke_judge/judgments_000.jsonl')
    if gate['status']!='PASS' or len(judges)!=96:raise ValueError('SCORING_CHECK_INCOMPLETE')
    # Missing reason legitimately earns zero; only malformed emitted judgments count as parser failures.
    from judge import _valid_raw
    preds=unique(load(p/'smoke/predictions_000.jsonl'));invalid=0;attempted=0
    for r in judges:
        reason=parse_prediction(preds[r['sample_id']]).get('reason') or ''
        for cid,raws in r['attempts'].items():
            if raws:attempted+=1;invalid+=not any(_valid_raw(raw,cid,reason) for raw in raws)
    record=dict(status='PASS' if attempted>0 and invalid/attempted<=.05 else 'BLOCKED_JUDGE_INTERFACE',
        candidate_gate=gate,judged_inputs=96,attempted_criteria=attempted,malformed_criteria=invalid,
        no_accuracy_threshold=True,not_proof_all_future_outputs_valid=True)
    frozen(ROOT/'SCORING_GATE.json',record)
    if record['status']!='PASS':raise ValueError('JUDGE_INTERFACE_BLOCKED')
    score(a,'smoke',False)

def sbatch(name,action,model='none',deps=(),gpu=0,wall='00:45:00',mem='16G',cpus=4,node=None,partition=None):
    subprocess.run(['sinfo','-p','gpu' if gpu else (partition or 'debug'),'-h'],check=True,capture_output=True,timeout=20)
    cmd=['sbatch','--parsable','--job-name='+name,'--partition='+('gpu' if gpu else (partition or 'debug')),
        '--account=YOUR_ACCOUNT','--qos=allocated','--nodes=1','--ntasks=1',f'--cpus-per-task={cpus}','--mem='+mem,'--time='+wall,
        '--no-requeue','--output='+str(ROOT/'logs'/(name+'_%j.out')),'--error='+str(ROOT/'logs'/(name+'_%j.err'))]
    if gpu:cmd+=['--gpus-per-node='+str(gpu),'--exclude=nid0688']
    if node:cmd+=['--nodelist='+node]
    elif not gpu and not partition:cmd+=['--nodelist=nid0640']
    if deps:cmd+=['--dependency=afterok:'+':'.join(str(x) for x in deps)]
    cmd +=[str(CODE/'job.sh'),action,model]
    result=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=30);jid=result.stdout.strip().split(';')[0]
    if not jid.isdigit():raise ValueError('INVALID_SBATCH_RESPONSE')
    frozen(ROOT/'submissions'/(jid+'.json'),dict(job_id=jid,command=cmd,action=action,model=model))
    print(json.dumps(dict(submitted=jid,command=cmd)),flush=True);return jid

def dispatch(a):
    verify();g=json.loads((ROOT/'SCORING_GATE.json').read_text())
    if g['status']!='PASS':raise ValueError('7B_GATE_NOT_PASS')
    score(a,'smoke',a.model!='qwen25vl_7b')
    m=registry()[a.model];p=ROOT/a.model;done=p/'full_submission.json'
    if done.exists():print(done.read_text());return
    r=load(p/'smoke/predictions_000.jsonl');seconds=[x['inference_seconds'] for x in r]
    estimated=math.ceil((sum(seconds)/len(seconds))*24196/m['replicas']*1.75+1800)
    hours=max(2,math.ceil(estimated/3600))
    budget=dict(estimated_seconds=estimated,requested_hours=min(48,hours),replicas=m['replicas'],gpus_per_replica=m['gpus'],
        node_gpus=4,cpus=16,mem='256G',mean_smoke_seconds=sum(seconds)/len(seconds),status='READY' if hours<=48 else 'BLOCKED_ESTIMATE_EXCEEDS_48H')
    frozen(p/'measured_budget.json',budget)
    if hours>48:raise ValueError('ESTIMATE_EXCEEDS_FROZEN_NODE_BUDGET')
    infer=sbatch('scfm_'+a.model,'full',a.model,gpu=4,wall=f'{hours:02d}:00:00',mem='256G',cpus=16)
    judge=sbatch('scfmj_'+a.model,'full_judge',a.model,deps=[infer],gpu=4,wall='48:00:00',mem='256G',cpus=16)
    final=sbatch('scfms_'+a.model,'final',a.model,deps=[judge])
    frozen(done,dict(inference=infer,judge=judge,final=final,cross_model_dependencies=[],shared_gate=str(ROOT/'SCORING_GATE.json')))

def main():
    a=args()
    if a.dry_run:print(json.dumps(dict(action=a.action,model=a.model,run_id=a.run_id)));return
    if not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login'):raise ValueError('COMPUTE_NODE_REQUIRED')
    if a.limit is not None:raise ValueError('NO_SILENT_SUBSETTING')
    if a.action=='prepare':prepare(a)
    elif a.action=='download':download(a)
    elif a.action=='audit7b':score(a,'smoke',True)
    elif a.action=='certify':certify(a)
    elif a.action=='dispatch':dispatch(a)
    elif a.action=='final':score(a,'full',False)
    else:raise ValueError('UNKNOWN_ACTION')

if __name__=='__main__':main()
