"""Persistent Azure Batch evaluation; immutable per-file requests and exact-ID merge."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import requests

CODE=Path(__file__).resolve().parent
SOURCE=Path('artifacts/model_results/azure_luna_20260920_v1')
ROOT=SOURCE.parent/'azure_gpt54_batch_20260920_v1'
RUN_ID=ROOT.name
SEED=20260920
OLD_CODE=CODE.parent/'azure_luna_20260920_v1'
spec=importlib.util.spec_from_file_location('luna_original',OLD_CODE/'run.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
load,unique,write,sha=old.load,old.unique,old.write,old.sha
TERMINAL={'completed','failed','cancelled','canceled','expired'}
FILE_LIMIT=100_000_000

def config():
    c=json.loads((OLD_CODE/'config.json').read_text())
    c.update(model='gpt-5.4',run_id=RUN_ID,output_root=str(ROOT),api_mode='AZURE_GLOBAL_BATCH_RESPONSES',
        allowed_returned_models=['gpt-5.4','gpt-5.4-2026-03-05'],completion_window='24h',
        batch_create_endpoint='/chat/completions',request_url='/v1/responses',
        batch_file_max_bytes=FILE_LIMIT,batch_file_max_requests=128,
        batch_file_expiry_seconds=1209600,no_answer_based_retries=True,
        notes='Azure Batch infers Responses operation from each JSONL url; no online inference. No paid judge.')
    return c

def bundle(r):return tuple(sorted(m['sha256'] for m in r.get('media',[])))

def init():
    if (ROOT/'PROTOCOL_LOCK.json').exists():old.verify_lock(ROOT);return
    old.verify_lock(SOURCE)
    for d in ('inputs','traces','manifests','cloud','raw','normalized','logs'): (ROOT/d).mkdir(parents=True,exist_ok=True)
    for name in ('requests.jsonl','private_gold.jsonl','smoke_ids.json','PREFLIGHT.json'):
        dest=ROOT/name
        if dest.exists():assert sha(dest)==sha(SOURCE/name)
        else:shutil.copyfile(SOURCE/name,dest)
    req=unique(load(ROOT/'requests.jsonl'));assert len(req)==24196
    assert set(req)==set(unique(load(ROOT/'private_gold.jsonl')))
    c=config();assert sha(ROOT/'requests.jsonl')==c['source_requests_sha256']
    assert sha(ROOT/'private_gold.jsonl')==c['source_gold_sha256']
    blocked=set()
    for r in load(SOURCE/'transport_attempts.jsonl'):
        if r.get('http_status')==400 and 'content_policy_violation' in r.get('message',''):
            blocked.add(bundle(req[r['sample_id']]))
    quarantined=[]
    for sid,r in req.items():
        if bundle(r) and bundle(r) in blocked:
            quarantined.append(dict(sample_id=sid,pair_id=r.get('pair_id'),component=r['component'],level=r['level'],
                run_id=RUN_ID,model_id=c['model'],raw_response='',generated_tokens=0,finish_reason='content_filter',
                error='POLICY_QUARANTINE_SAME_AZURE_MEDIA_NO_REQUEST',policy_rejected=True,http_attempts=0,
                evidence=str(SOURCE/'transport_attempts.jsonl')))
    write(ROOT/'quarantine.jsonl',quarantined,jsonl=True)
    write(ROOT/'config.json',c)
    files=[CODE/n for n in ('batch.py','job.sh','launch.py')]
    files += [ROOT/n for n in ('config.json','requests.jsonl','private_gold.jsonl','smoke_ids.json','quarantine.jsonl')]
    files += [Path(p) for p in json.loads((SOURCE/'PROTOCOL_LOCK.json').read_text())['sha256']]
    write(ROOT/'PROTOCOL_LOCK.json',dict(config=c,sha256={str(p):sha(p) for p in files},schema=old.SCHEMA,
        inherited_predictions=0,code_commit='FILE_HASH_PROVENANCE_NO_GIT_COMMIT_ASSERTED'))

def guard():
    def deny(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            if Path(os.fsdecode(args[0])).name in {'private_gold.jsonl','scores.jsonl','report.json','rubric.json'}:
                raise PermissionError('CANDIDATE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(deny)

def encode(row):
    # Same exact processor/prompt as Luna; source bytes checked before conversion.
    for m in row.get('media',[]):
        assert sha(m['path'])==m['sha256'].removeprefix('sha256:'),'MEDIA_HASH_CHANGED'
    body,trace=old.make_body(row,config())
    request=dict(custom_id=row['sample_id'],method='POST',url='/v1/responses',body=body)
    wire=(json.dumps(request,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if len(wire)>FILE_LIMIT:raise ValueError('SINGLE_REQUEST_EXCEEDS_FILE_LIMIT_NO_MEDIA_DROPPED')
    trace.update(sample_id=row['sample_id'],pair_id=row.get('pair_id'),component=row['component'],level=row['level'])
    return wire,trace

def emit(part,items,kind):
    assert items and sum(len(w) for w,_ in items)<=FILE_LIMIT,'BATCH_FILE_BOUND_EXCEEDED'
    name=f'part_{part:05d}';manifest=ROOT/'manifests'/(name+'.json')
    ids=[trace['sample_id'] for _,trace in items]
    if manifest.exists():
        m=json.loads(manifest.read_text());assert m['ids']==ids and sha(m['path'])==m['sha256'];return
    path=ROOT/'inputs'/(name+'.jsonl');temp=path.with_suffix('.jsonl.part')
    with temp.open('wb') as f:
        for wire,_ in items:f.write(wire)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    trace_path=ROOT/'traces'/(name+'.jsonl');write(trace_path,[t for _,t in items],jsonl=True)
    m=dict(part=part,name=name,kind=kind,n=len(ids),ids=ids,path=str(path),sha256=sha(path),
        bytes=path.stat().st_size,trace_path=str(trace_path),trace_sha256=sha(trace_path))
    write(manifest,m)
    print(json.dumps({'stage':'PREPARED_PART','name':name,'n':len(ids),'bytes':m['bytes']}),flush=True)

class ApiFault(Exception):
    def __init__(self,status,text):super().__init__(f'HTTP_{status}:{text}');self.status=status;self.text=text

class Client:
    def __init__(self):
        self.key=os.environ.get('SPACECONFLICT_AZURE_API_KEY','')
        if not self.key:raise ValueError('CREDENTIAL_MISSING')
        self.base=config()['endpoint'].removesuffix('/responses')
        self.session=requests.Session();self.session.headers.update({'api-key':self.key,'Authorization':'Bearer '+self.key})
    def call(self,method,path,**kwargs):
        # Never replay an ambiguous POST. Persist intent before mutations.
        attempts=4 if method=='GET' else 1
        for attempt in range(attempts):
            try:r=self.session.request(method,self.base+path,timeout=(30,300),**kwargs)
            except requests.RequestException as e:
                if method=='GET' and attempt+1<attempts:time.sleep(5*(attempt+1));continue
                raise RuntimeError('TRANSPORT_AMBIGUOUS_'+method+':'+type(e).__name__) from None
            if r.status_code>=400:
                text=r.text[:2000].replace(self.key,'[REDACTED]')
                if method=='GET' and r.status_code in (408,429,500,502,503,504) and attempt+1<attempts:
                    try:delay=float(r.headers.get('Retry-After',5*(attempt+1)))
                    except ValueError:delay=10
                    time.sleep(max(1,delay));continue
                raise ApiFault(r.status_code,text)
            return r
    def submit(self,m):
        record=ROOT/'cloud'/(m['name']+'.json')
        state=json.loads(record.read_text()) if record.exists() else {'manifest_sha256':sha(ROOT/'manifests'/(m['name']+'.json'))}
        assert state['manifest_sha256']==sha(ROOT/'manifests'/(m['name']+'.json')),'CLOUD_MANIFEST_CHANGED'
        if state.get('batch'):return state
        if state.get('ambiguous'):raise RuntimeError('AMBIGUOUS_POST_REQUIRES_RECONCILIATION:'+m['name'])
        if state.get('not_before',0)>time.time():return state
        if not state.get('file'):
            assert sha(m['path'])==m['sha256']
            state['ambiguous']='FILE_UPLOAD_INTENT';write(record,state)
            with open(m['path'],'rb') as f:
                response=self.call('POST','/files',data={'purpose':'batch','expires_after.seconds':'1209600','expires_after.anchor':'created_at'},
                    files={'file':(m['name']+'.jsonl',f,'application/json')}).json()
            state.update(file=response,ambiguous=None);write(record,state)
        file_info=self.call('GET','/files/'+state['file']['id']).json()
        if file_info.get('status') not in ('processed',None):
            if file_info.get('status')=='error':raise RuntimeError('FILE_PROCESSING_FAILED')
            return state
        state['ambiguous']='BATCH_CREATE_INTENT';write(record,state)
        try:
            batch=self.call('POST','/batches',json=dict(input_file_id=state['file']['id'],endpoint='/chat/completions',
                completion_window='24h',metadata={'run_id':RUN_ID,'part':m['name'],'input_sha256':m['sha256']},
                output_expires_after={'anchor':'created_at','seconds':1209600})).json()
        except ApiFault as e:
            state.update(ambiguous=None,last_error=str(e),not_before=time.time()+180);write(record,state)
            if 'token_limit_exceeded' in e.text or e.status==429:return state
            raise
        state.update(batch=batch,ambiguous=None,submitted_at=old.now());write(record,state)
        print(json.dumps({'stage':'AZURE_BATCH_SUBMITTED','part':m['name'],'id':batch['id'],'n':m['n']}),flush=True)
        return state
    def retrieve(self,m,state):
        batch=self.call('GET','/batches/'+state['batch']['id']).json()
        state.update(batch=batch,checked_at=old.now());write(ROOT/'cloud'/(m['name']+'.json'),state)
        if batch['status'] not in TERMINAL:return
        raw=[]
        for field in ('output_file_id','error_file_id'):
            if not batch.get(field):continue
            path=ROOT/'raw'/(m['name']+'_'+field+'.jsonl')
            if not path.exists():
                response=self.call('GET','/files/'+batch[field]+'/content')
                temp=path.with_suffix('.part');temp.write_bytes(response.content);os.replace(temp,path)
            raw.extend(load(path))
        predictions=normalize(m,raw,batch)
        write(ROOT/'normalized'/(m['name']+'.jsonl'),predictions,jsonl=True)
        state.update(harvested=True,output_count=len(predictions),normalized_sha256=sha(ROOT/'normalized'/(m['name']+'.jsonl')))
        write(ROOT/'cloud'/(m['name']+'.json'),state)

def normalize(m,raw,batch):
    assert sha(m['trace_path'])==m['trace_sha256'],'TRACE_HASH_CHANGED'
    traces=unique(load(m['trace_path']));assert set(traces)==set(m['ids'])
    found={}
    for r in raw:
        sid=r.get('custom_id');assert sid in traces and sid not in found,'BATCH_ID_MISMATCH_OR_DUPLICATE'
        trace=traces[sid];http=r.get('response') or {};body=http.get('body') or {}
        row=dict(sample_id=sid,pair_id=trace.get('pair_id'),component=trace['component'],level=trace['level'],
            run_id=RUN_ID,model_id='gpt-5.4',returned_model=body.get('model'),raw_response='',generated_tokens=0,
            finish_reason='error',error=None,batch_id=batch['id'],input_trace=trace,
            raw_batch_result=r,usage=body.get('usage') or {},response=body,
            protocol_lock_sha256=sha(ROOT/'PROTOCOL_LOCK.json'))
        if http.get('status_code')==200 and body.get('status') in ('completed','incomplete'):
            row['raw_response']=''.join(c.get('text','') for item in body.get('output',[]) if item.get('type')=='message'
                and item.get('role')=='assistant' for c in item.get('content',[]) if c.get('type')=='output_text')
            row['generated_tokens']=row['usage'].get('output_tokens',0)
            row['finish_reason']='length' if (body.get('incomplete_details') or {}).get('reason')=='max_output_tokens' else 'stop'
            if row['returned_model'] not in config()['allowed_returned_models']:row['error']='RETURNED_MODEL_MISMATCH'
            if row['generated_tokens']>512:raise ValueError('SERVER_EXCEEDED_512_RAW_PRESERVED')
            row['prediction']=old.parse_prediction(row)
        else:
            error=r.get('error') or body.get('error') or {'status':http.get('status_code')}
            row['error']='BATCH_REQUEST_ERROR:'+json.dumps(error,ensure_ascii=False)
            row['policy_rejected']=any(s in row['error'].lower() for s in ('content_policy','content_filter'))
        found[sid]=row
    # Explicit terminal records for omitted rows; never treat a missing answer as successful.
    for sid in set(m['ids'])-set(found):
        t=traces[sid]
        found[sid]=dict(sample_id=sid,pair_id=t.get('pair_id'),component=t['component'],level=t['level'],
            run_id=RUN_ID,model_id='gpt-5.4',raw_response='',generated_tokens=0,finish_reason='error',
            error='BATCH_TERMINAL_WITHOUT_RESPONSE:'+batch['status'],batch_id=batch['id'],batch_errors=batch.get('errors'))
    return [found[s] for s in m['ids']]

def bootstrap():
    init();guard();req=unique(load(ROOT/'requests.jsonl'));ids=json.loads((ROOT/'smoke_ids.json').read_text())
    assert len(ids)==12
    emit(0,[encode(req[s]) for s in ids],'smoke')
    Client().submit(json.loads((ROOT/'manifests/part_00000.json').read_text()))

def prepare():
    old.verify_lock(ROOT);guard()
    if (ROOT/'PREPARATION_COMPLETE.json').exists():return
    excluded=set(json.loads((ROOT/'smoke_ids.json').read_text()))|set(unique(load(ROOT/'quarantine.jsonl')))
    rows=[r for r in load(ROOT/'requests.jsonl') if r['sample_id'] not in excluded]
    part=1;items=[];size=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        # Bound in-flight encoded media memory; map only 16 rows at once.
        for start in range(0,len(rows),16):
            for wire,trace in pool.map(encode,rows[start:start+16]):
                if items and (size+len(wire)>FILE_LIMIT or len(items)>=128):
                    emit(part,items,'full');part+=1;items=[];size=0
                items.append((wire,trace));size+=len(wire)
    if items:emit(part,items,'full')
    manifests=[json.loads(p.read_text()) for p in sorted((ROOT/'manifests').glob('part_*.json'))]
    ids=[sid for m in manifests for sid in m['ids']]
    assert len(set(ids))==len(ids) and len(ids)+len(load(ROOT/'quarantine.jsonl'))==24196
    write(ROOT/'PREPARATION_COMPLETE.json',dict(at=old.now(),parts=len(manifests),requests=len(ids),
        quarantined=len(load(ROOT/'quarantine.jsonl')),bytes=sum(m['bytes'] for m in manifests)))

def control():
    old.verify_lock(ROOT);client=Client();smoke_pass=False
    # No gold is opened while controlling inference. Scoring runs in a separate process.
    guard()
    while True:
        manifests=[json.loads(p.read_text()) for p in sorted((ROOT/'manifests').glob('part_*.json'))]
        states=[]
        for m in manifests:
            record=ROOT/'cloud'/(m['name']+'.json')
            state=json.loads(record.read_text()) if record.exists() else {}
            if m['kind']!='smoke' and not smoke_pass:
                continue
            if not state.get('batch'):
                state=client.submit(m)
                if not state.get('batch'):
                    if state.get('last_error'):break
                    continue
            if not state.get('harvested'):
                client.retrieve(m,state)
                state=json.loads(record.read_text())
            states.append(state)
            if m['kind']=='smoke' and state.get('harvested'):
                rows=load(ROOT/'normalized'/(m['name']+'.jsonl'))
                smoke_pass=len(rows)==12 and all(not r.get('error') for r in rows)
                write(ROOT/'SMOKE_ACCEPTANCE.json',dict(status='PASS' if smoke_pass else 'BLOCKED',n=len(rows),
                    schema_valid=sum(old.parse_prediction(r)['schema_valid'] for r in rows),
                    accuracy_gate=False,reused_in_full=True,batch_id=state['batch']['id']))
                if not smoke_pass:raise RuntimeError('BATCH_SMOKE_FAILED_SEE_RAW_NO_PROMPT_TUNING')
        # Persist submitted-vs-finished counts separately.
        states=[json.loads(p.read_text()) for p in (ROOT/'cloud').glob('part_*.json')]
        state=dict(at=old.now(),prepared_parts=len(manifests),submitted_parts=sum(bool(s.get('batch')) for s in states),
            harvested_parts=sum(bool(s.get('harvested')) for s in states),
            cloud_completed_requests=sum((s.get('batch',{}).get('request_counts') or {}).get('completed',0) or 0 for s in states),
            preparation_complete=(ROOT/'PREPARATION_COMPLETE.json').exists(),smoke_pass=smoke_pass,
            job_id=os.environ['SLURM_JOB_ID'])
        write(ROOT/'PROGRESS.json',state);print(json.dumps(state),flush=True)
        if state['preparation_complete'] and state['harvested_parts']==len(manifests):return
        if (ROOT/'PREPARATION_FAILED.json').exists():raise RuntimeError('PREPARATION_FAILED')
        time.sleep(60)

def score():
    old.verify_lock(ROOT)
    rows=load(ROOT/'quarantine.jsonl')
    for p in sorted((ROOT/'normalized').glob('part_*.jsonl')):rows.extend(load(p))
    unique(rows);write(ROOT/'predictions.jsonl',rows,jsonl=True)
    old.score(config())
    report=json.loads((ROOT/'report.json').read_text())
    rejected=[r['sample_id'] for r in rows if r.get('policy_rejected')]
    other=[r['sample_id'] for r in rows if r.get('error') and not r.get('policy_rejected')]
    status=('COMPLETE_WITH_POLICY_REJECTIONS' if rejected else 'COMPLETE') if len(rows)==24196 and not other else 'INCOMPLETE_NOT_FINAL'
    tokens=Counter()
    for r in rows:
        u=r.get('usage',{});d=u.get('input_tokens_details',{})
        tokens.update(input=u.get('input_tokens',0),output=u.get('output_tokens',0),cached=d.get('cached_tokens',0),cache_write=d.get('cache_write_tokens',0))
    reference=((tokens['input']-tokens['cached'])*1.25+tokens['cached']*.125+tokens['output']*7.5)/1e6
    report.update(status=status,usage_with_cache=dict(tokens),policy_rejected_ids=rejected,other_errors=other,
        public_batch_price_reference_usd=reference,actual_azure_bill='NOT_VERIFIED',
        raw_response_index=[str(p) for p in sorted((ROOT/'raw').glob('*.jsonl'))])
    write(ROOT/'report.json',report)
    text=(ROOT/'accuracy_report_cn.md').read_text().replace('GPT-5.6 Luna','GPT-5.4 Batch')
    text=text.replace('状态：INCOMPLETE_NOT_FINAL','状态：'+status)
    text+=f'\nAzure Batch；内容拒绝/隔离 {len(rejected)}，其他错误 {len(other)}。错误保留全量分母。\n'
    text+=f'\n公开 Batch 价格参考费用 ${reference:.4f}；Azure 实际账单未核实；不包含 Luna。\n'
    (ROOT/'accuracy_report_cn.md').write_text(text)

def tests():
    from unittest.mock import patch
    c=config();assert c['model']=='gpt-5.4' and c['request_url']=='/v1/responses'
    assert c['max_output_tokens']==512 and c['reasoning_effort']=='none' and FILE_LIMIT<200_000_000
    assert old.parse_prediction({'raw_response':'{"label":"SUPPORTED","confidence":1,"reason":"cut',
        'finish_reason':'length','generated_tokens':512})['label']=='SUPPORTED'
    traces=[dict(sample_id=s,component='pair',level='L1') for s in ('a','b','c')]
    manifest=dict(ids=['a','b','c'],trace_path='mock',trace_sha256='frozen')
    good=dict(custom_id='b',response=dict(status_code=200,body=dict(status='incomplete',
        model='gpt-5.4',usage={'output_tokens':512},incomplete_details={'reason':'max_output_tokens'},
        output=[dict(type='message',role='assistant',content=[dict(type='output_text',
            text='{"label":"SUPPORTED","confidence":1,"reason":"cut')])])) )
    rejected=dict(custom_id='a',response=dict(status_code=400,body=dict(error={'code':'content_policy_violation'})))
    with patch.dict(normalize.__globals__,load=lambda p:traces,sha=lambda p:'frozen'):
        result=normalize(manifest,[good,rejected],{'id':'batch-test','status':'completed'})
        assert [r['sample_id'] for r in result]==['a','b','c']
        assert result[0]['policy_rejected'] and result[1]['prediction']['label']=='SUPPORTED'
        assert result[1]['finish_reason']=='length' and result[2]['error'].startswith('BATCH_TERMINAL')
        try:normalize(manifest,[good,good],{'id':'batch-test','status':'completed'})
        except AssertionError:pass
        else:raise AssertionError('DUPLICATE_ACCEPTED')
    print('PASS: Batch protocol, file bound, retained-prefix scoring, unordered-ID merge, duplicate rejection, policy/missing records')

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['bootstrap','prepare','control','score','tests'])
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.run_id==RUN_ID and a.seed==SEED and a.limit is None
    if a.dry_run:print(json.dumps(config()));sys.exit()
    if a.stage!='tests':assert os.environ.get('SLURM_JOB_ID'),'SLURM_REQUIRED'
    try:{'bootstrap':bootstrap,'prepare':prepare,'control':control,'score':score,'tests':tests}[a.stage]()
    except Exception as exc:
        if a.stage=='prepare':write(ROOT/'PREPARATION_FAILED.json',dict(error=str(exc),at=old.now()))
        raise
