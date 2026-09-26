"""Claude Foundry adapter; immutable SpaceConflict inputs and retained-prefix scorer."""
import argparse
from collections import Counter, deque
import concurrent.futures as cf
import copy
import fcntl
import getpass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

CODE=Path(__file__).resolve().parent
SOURCE=Path('artifacts/model_results/azure_luna_20260920_v1')
ROOT=SOURCE.parent/'azure_claude_opus47_20260920_v1'
RUN_ID=ROOT.name
SEED=20260920
spec=importlib.util.spec_from_file_location('luna_original',CODE.parent/'azure_luna_20260920_v1/run.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha,load,unique,write=old.sha,old.load,old.unique,old.write

def config():
    c=json.loads((CODE.parent/'azure_luna_20260920_v1/config.json').read_text())
    c.update(run_id=RUN_ID,model='claude-opus-4-7',output_root=str(ROOT),
        endpoint='https://YOUR_ENDPOINT.invalid',
        api_mode='AZURE_ANTHROPIC_MESSAGES_ONLINE',workers=16,minimum_request_interval_seconds=.25,
        estimated_tokens_per_minute=600000,request_timeout_seconds=180,thinking={'type':'disabled'},
        temperature='PROVIDER_DEFAULT_NOT_GREEDY_ASSERTED',inherited_predictions=0,
        output_interface='ANTHROPIC_JSON_SCHEMA_LABEL_CONFIDENCE_REASON',
        schema_adapter='confidence numeric bounds expressed in description; original validator retained',
        notes='No prompt changes, no answer retries, no paid judge; ambiguous transport stops, no automatic resend.')
    return c

def schema():
    s=copy.deepcopy(old.SCHEMA)
    s['properties']['confidence']={'type':'number','description':'Confidence must be at least 0 and at most 1.'}
    return s

def convert(body):
    content=[]
    for item in body['input'][1]['content']:
        if item['type']=='input_text':content.append({'type':'text','text':item['text']})
        elif item['type']=='input_image':
            prefix,data=item['image_url'].split(',',1)
            assert prefix=='data:image/png;base64'
            content.append({'type':'image','source':{'type':'base64','media_type':'image/png','data':data}})
        else:raise ValueError('UNSUPPORTED_INPUT_KIND')
    return dict(model=config()['model'],max_tokens=512,thinking={'type':'disabled'},
        system=body['input'][0]['content'],messages=[{'role':'user','content':content}],
        output_config={'format':{'type':'json_schema','schema':schema()}})

def make_body(row):
    body,trace=old.make_body(row,config());converted=convert(body)
    trace['source_adapter_body_sha256']=trace.pop('body_sha256')
    trace['body_sha256']=old.digest(converted)
    trace['provider_media_detail']='Anthropic has no OpenAI detail field; identical pre-encoded PNG bytes'
    return converted,trace

def normalized(response):
    u=response.get('usage') or {};out=u.get('output_tokens',0)
    total_in=sum(u.get(k,0) or 0 for k in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens'))
    row=dict(raw_response=''.join(x.get('text','') for x in response.get('content',[]) if x.get('type')=='text'),
        response=response,returned_model=response.get('model'),provider_usage=u,
        usage={'input_tokens':total_in,'output_tokens':out,'total_tokens':total_in+out,
               'input_tokens_details':{'cached_tokens':u.get('cache_read_input_tokens',0),
                 'cache_write_tokens':u.get('cache_creation_input_tokens',0)}},
        generated_tokens=out,finish_reason='length' if response.get('stop_reason')=='max_tokens' else 'stop',error=None)
    if response.get('model')!='claude-opus-4-7':row['error']='RETURNED_MODEL_MISMATCH'
    if response.get('type')!='message' or response.get('stop_reason') not in ('end_turn','max_tokens','refusal'):
        row['error']='UNEXPECTED_RESPONSE_TYPE_OR_STOP'
    if any(x.get('type') in ('thinking','redacted_thinking') for x in response.get('content',[])):
        row['error']='THINKING_UNEXPECTED'
    if (u.get('output_tokens_details') or {}).get('thinking_tokens',0):row['error']='THINKING_TOKENS_UNEXPECTED'
    if out>512:
        row.update(error='PROVIDER_EXCEEDED_OUTPUT_CAP',provider_generated_tokens=out,generated_tokens=0)
    if response.get('stop_reason')=='refusal':row.update(error='PROVIDER_REFUSAL',policy_rejected=True)
    row['prediction']=old.parse_prediction(row)
    return row

def key():
    return os.environ.get('SPACECONFLICT_CLAUDE_API_KEY') or getpass.getpass('Claude Foundry API key (hidden): ')

def http(body,secret):
    request=urllib.request.Request(config()['endpoint'],data=json.dumps(body).encode(),headers={
        'Content-Type':'application/json','x-api-key':secret,'api-key':secret,'anthropic-version':'2023-06-01'})
    with urllib.request.urlopen(request,timeout=config()['request_timeout_seconds']) as r:
        return json.load(r),{k:v for k,v in r.headers.items() if 'ratelimit' in k.lower() or 'request-id' in k.lower()}

def probe():
    ROOT.mkdir(parents=True,exist_ok=True)
    path=ROOT/'SETUP_PROBE_sdk_auth.json'
    if path.exists():
        report=json.loads(path.read_text());print(json.dumps(report));assert report['status']=='PASS';return
    secret=key();body=dict(model=config()['model'],max_tokens=512,thinking={'type':'disabled'},
        system='Return the requested JSON object.',messages=[{'role':'user','content':
        'This is an API interface check, not benchmark data. Return label SUPPORTED, confidence 1, reason interface check.'}],
        output_config={'format':{'type':'json_schema','schema':schema()}})
    try:
        response,headers=http(body,secret);row=normalized(response)
        ok=not row['error'] and old.gate_usable(row['prediction'],row)
        report=dict(status='PASS' if ok else 'BLOCKED',at=old.now(),request=body,headers=headers,**row)
    except urllib.error.HTTPError as e:
        report=dict(status='BLOCKED',at=old.now(),http_status=e.code,message=e.read().decode(errors='replace').replace(secret,'[REDACTED]'))
    except Exception as e:report=dict(status='BLOCKED',at=old.now(),error=type(e).__name__+':'+str(e).replace(secret,'[REDACTED]'))
    write(path,report);print(json.dumps(report,ensure_ascii=False));assert report['status']=='PASS','SETUP_BLOCKED'

def freeze():
    if (ROOT/'PROTOCOL_LOCK.json').exists():old.verify_lock(ROOT);return
    old.verify_lock(SOURCE)
    assert json.loads((ROOT/'SETUP_PROBE_sdk_auth.json').read_text())['status']=='PASS'
    for name in ('requests.jsonl','private_gold.jsonl','smoke_ids.json','PREFLIGHT.json'):
        dest=ROOT/name
        if dest.exists():assert sha(dest)==sha(SOURCE/name)
        else:shutil.copyfile(SOURCE/name,dest)
    req=unique(load(ROOT/'requests.jsonl'));assert len(req)==24196
    assert set(req)==set(unique(load(ROOT/'private_gold.jsonl')))
    c=config();assert sha(ROOT/'requests.jsonl')==c['source_requests_sha256']
    assert sha(ROOT/'private_gold.jsonl')==c['source_gold_sha256']
    write(ROOT/'config.json',c)
    paths=[CODE/p for p in ('run.py','job.sh','launch.py')]
    paths += [ROOT/p for p in ('config.json','requests.jsonl','private_gold.jsonl','smoke_ids.json','SETUP_PROBE_sdk_auth.json')]
    paths += [Path(p) for p in json.loads((SOURCE/'PROTOCOL_LOCK.json').read_text())['sha256']]
    write(ROOT/'PROTOCOL_LOCK.json',dict(config=c,sha256={str(p):sha(p) for p in paths},schema=old.SCHEMA,
        provider_schema=schema(),seed=SEED,code_commit='FILE_HASH_PROVENANCE_NO_GIT_COMMIT_ASSERTED'))

def bundle(row):return tuple(sorted(m['sha256'] for m in row.get('media',[])))

class Api:
    def __init__(self):
        self.secret=os.environ['SPACECONFLICT_CLAUDE_API_KEY'];self.lock=threading.Lock()
        self.media_lock=threading.Lock();self.stop=threading.Event();self.checked=set();self.blocked=set()
        self.next_start=0.;self.cooldown=0.;self.window=deque();self.tpm=config()['estimated_tokens_per_minute']
    def slot(self,tokens):
        while not self.stop.is_set():
            with self.lock:
                now=time.monotonic()
                while self.window and self.window[0][0]<now-60:self.window.popleft()
                delay=max(0,self.cooldown-now,self.next_start-now)
                if self.window and sum(t for _,t in self.window)+tokens>self.tpm:delay=max(delay,self.window[0][0]+60-now+.1)
                if delay<=0:self.next_start=now+config()['minimum_request_interval_seconds'];self.window.append((now,tokens));return
            self.stop.wait(delay)
        raise RuntimeError('CIRCUIT_STOP_BEFORE_REQUEST')
    def call(self,sample):
        if self.stop.is_set():return None
        started=time.monotonic();media=bundle(sample)
        row=dict(sample_id=sample['sample_id'],pair_id=sample.get('pair_id'),component=sample['component'],level=sample['level'],
            run_id=RUN_ID,model_id=config()['model'],raw_response='',generated_tokens=0,finish_reason='error',error=None,
            created_at=old.now(),protocol_lock_sha256=sha(ROOT/'PROTOCOL_LOCK.json'),http_attempts=0)
        try:
            with self.lock:blocked=bool(media and media in self.blocked)
            if blocked:row.update(error='POLICY_QUARANTINE_IDENTICAL_MEDIA',policy_rejected=True);return row
            with self.media_lock:
                for m in sample.get('media',[]):
                    item=(m['path'],m['sha256'])
                    if item not in self.checked:
                        assert sha(m['path'])==m['sha256'].removeprefix('sha256:'),'MEDIA_HASH_CHANGED'
                        self.checked.add(item)
            body,trace=make_body(sample);row['input_trace']=trace
            reserve=2048+1500*len(sample.get('media',[]))
            for attempt in range(1,5):
                self.slot(reserve);row['http_attempts']=attempt
                with self.lock:blocked=bool(media and media in self.blocked)
                if blocked:row.update(error='POLICY_QUARANTINE_IDENTICAL_MEDIA',policy_rejected=True);return row
                try:
                    response,headers=http(body,self.secret);row.update(normalized(response));row['api_headers']=headers
                    if row['error'] and not row.get('policy_rejected'):self.stop.set()
                    return row
                except urllib.error.HTTPError as e:
                    msg=e.read().decode(errors='replace').replace(self.secret,'[REDACTED]')
                    with self.lock:
                        with (ROOT/'transport_attempts.jsonl').open('a') as f:
                            f.write(json.dumps(dict(sample_id=sample['sample_id'],attempt=attempt,at=old.now(),http_status=e.code,message=msg[:3000]))+'\n')
                    if e.code==400 and any(x in msg.lower() for x in ('content_policy_violation','content_filter')):
                        with self.lock:self.blocked.add(media)
                        row.update(error='PROVIDER_CONTENT_POLICY_REJECTION',policy_rejected=True);return row
                    if e.code not in (429,529,503):raise RuntimeError('FATAL_HTTP_'+str(e.code)+':'+msg[:500]) from None
                    delay=e.headers.get('Retry-After','60')
                    try:delay=float(delay)
                    except ValueError:delay=max(0,parsedate_to_datetime(delay).timestamp()-time.time())
                    with self.lock:self.cooldown=max(self.cooldown,time.monotonic()+max(5,delay)+1)
            raise RuntimeError('RATE_LIMIT_RETRIES_EXHAUSTED')
        except Exception as e:
            row['error']=type(e).__name__+':'+str(e).replace(self.secret,'[REDACTED]')[:600]
            self.stop.set();return row
        finally:row['seconds']=round(time.monotonic()-started,4)

def counts(rows):
    t=Counter()
    for r in rows:
        u=r.get('provider_usage') or {}
        t.update(recorded=1,success=int(not r.get('error')),errors=int(bool(r.get('error'))),
            input_tokens=u.get('input_tokens',0),output_tokens=u.get('output_tokens',0),
            cache_read_input_tokens=u.get('cache_read_input_tokens',0),cache_creation_input_tokens=u.get('cache_creation_input_tokens',0))
    return t

def infer():
    old.verify_lock(ROOT)
    def guard(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            if Path(os.fsdecode(args[0])).name in ('private_gold.jsonl','report.json','scores.jsonl','rubric.json'):
                raise PermissionError('CANDIDATE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(guard)
    req=unique(load(ROOT/'requests.jsonl'));path=ROOT/'predictions.jsonl'
    done=unique(load(path)) if path.exists() else {};assert not set(done)-set(req)
    api=Api();t=counts(done.values());ids=json.loads((ROOT/'smoke_ids.json').read_text())
    api.blocked={bundle(req[s]) for s,r in done.items() if r.get('policy_rejected') and 'CONTENT_POLICY' in r.get('error','')}
    def record(row):
        if row is None:return
        sid=row['sample_id'];assert sid not in done
        with path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        done[sid]=row;t.update(counts([row]))
        progress=dict(at=old.now(),expected=24196,job_id=os.environ['SLURM_JOB_ID'],**dict(t))
        write(ROOT/'PROGRESS.json',progress)
        if t['recorded']%20==0 or row.get('error'):print(json.dumps(progress),flush=True)
    for sid in ids:
        if sid not in done:record(api.call(req[sid]))
        if api.stop.is_set():raise RuntimeError('SMOKE_TRANSPORT_BLOCKED')
    usable=sum(old.gate_usable(old.parse_prediction(done[s]),done[s]) and not done[s].get('error') for s in ids)
    smoke=dict(status='PASS' if usable==12 else 'BLOCKED',n=12,usable=usable,accuracy_gate=False,reused_in_full=True)
    write(ROOT/'SMOKE_ACCEPTANCE.json',smoke);print(json.dumps(smoke),flush=True)
    assert smoke['status']=='PASS','SMOKE_INTERFACE_BLOCKED_NO_PROMPT_TUNING'
    todo=iter(r for sid,r in req.items() if sid not in done)
    with cf.ThreadPoolExecutor(max_workers=config()['workers']) as pool:
        pending=set()
        for _ in range(config()['workers']):
            r=next(todo,None)
            if r is not None:pending.add(pool.submit(api.call,r))
        while pending:
            finished,pending=cf.wait(pending,return_when=cf.FIRST_COMPLETED)
            for f in finished:
                record(f.result())
                if not api.stop.is_set():
                    r=next(todo,None)
                    if r is not None:pending.add(pool.submit(api.call,r))
    if api.stop.is_set() or len(done)!=24196:raise RuntimeError('INCOMPLETE_SEE_PRESERVED_RESPONSES')

def score():
    old.score(config());report=json.loads((ROOT/'report.json').read_text())
    rows=load(ROOT/'predictions.jsonl') if (ROOT/'predictions.jsonl').exists() else []
    usage=counts(rows);setup=json.loads((ROOT/'SETUP_PROBE_sdk_auth.json').read_text())
    report.update(provider_usage=dict(usage),setup_usage=setup.get('provider_usage'),actual_azure_bill='NOT_VERIFIED',
        raw_response_index='predictions.jsonl: response + sample_id + input_trace + api_headers')
    if len(rows)==24196 and all(not r.get('error') or r.get('policy_rejected') for r in rows):
        report['status']='COMPLETE_WITH_POLICY_REJECTIONS' if any(r.get('policy_rejected') for r in rows) else 'COMPLETE'
    write(ROOT/'report.json',report)
    path=ROOT/'accuracy_report_cn.md';text=path.read_text().replace('GPT-5.6 Luna','Claude Opus 4.7')
    text=text.replace('状态：INCOMPLETE_NOT_FINAL','状态：'+report['status'])
    text+='\nClaude Messages 非 Batch；thinking disabled；原始 tokenizer 与 GPT 不同。原始提供商用量见 report.json。\n'
    path.write_text(text)

def tests():
    body={'input':[{'content':'system'},{'content':[{'type':'input_text','text':'claim'},
        {'type':'input_image','image_url':'data:image/png;base64,YWJj'}]}]}
    b=convert(body);assert b['messages'][0]['content'][1]['source']['data']=='YWJj'
    assert b['system']=='system' and b['messages'][0]['content'][0]['text']=='claim'
    assert b['max_tokens']==512 and b['thinking']=={'type':'disabled'} and 'gold' not in b
    response=dict(type='message',model='claude-opus-4-7',stop_reason='max_tokens',
        usage={'input_tokens':10,'cache_read_input_tokens':2,'cache_creation_input_tokens':3,'output_tokens':512},
        content=[{'type':'text','text':'{"label":"SUPPORTED","confidence":1,"reason":"cut'}])
    r=normalized(response);assert r['prediction']['label']=='SUPPORTED' and r['usage']['input_tokens']==15
    assert old.gate_usable(r['prediction'],r)
    response['stop_reason']='refusal';assert normalized(response)['policy_rejected']
    print('PASS: exact text/media translation, 512-token prefix scoring, thinking disabled, cache normalization, refusal preservation')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['probe','freeze','infer','score','tests'])
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    p.add_argument('--seed',type=int,default=SEED);p.add_argument('--run-id',default=RUN_ID);p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.seed==SEED and a.run_id==RUN_ID and a.limit is None
    if a.dry_run:print(json.dumps(config()));sys.exit()
    if a.stage in ('freeze','infer','score'):assert os.environ.get('SLURM_JOB_ID'),'SLURM_REQUIRED'
    if a.stage=='infer':
        handle=(ROOT/'INFERENCE.lock').open('a');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    globals()[a.stage]()
