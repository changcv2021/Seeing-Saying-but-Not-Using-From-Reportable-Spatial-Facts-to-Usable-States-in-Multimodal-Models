"""Versioned, rejection-aware continuation; historical responses are immutable."""
import argparse
from collections import Counter, deque
import concurrent.futures as cf
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime

CODE = Path(__file__).resolve().parent
OLD_CODE = CODE.parent / 'azure_luna_20260920_v1'
spec = importlib.util.spec_from_file_location('luna_original', OLD_CODE / 'run.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
sha, load, unique, write = old.sha, old.load, old.unique, old.write
SOURCE = Path('artifacts/model_results/azure_luna_20260920_v1')
ROOT = SOURCE.parent / 'azure_luna_resume_20260920_v2'
RUN_ID = ROOT.name
SEED = 20260920
SOURCE_PRED_SHA = '8ba209895bac4de6f35bf8d32b1ad87252bdeb93d585512ef08bce7971415639'

def bundle(sample):
    return tuple(sorted(m['sha256'] for m in sample.get('media', [])))

def config():
    c = json.loads((OLD_CODE / 'config.json').read_text())
    c.update(run_id=RUN_ID, output_root=str(ROOT), workers=16,
        minimum_request_interval_seconds=.25, estimated_tokens_per_minute=600000,
        continuation_of=str(SOURCE), content_rejection_policy='RECORD_NO_RETRY_CONTINUE_OTHER_MEDIA',
        same_media_policy='Quarantine exact media multiset after explicit image content-policy rejection',
        notes='Same model, prompt, schema, media, 512 tokens and scorer. Transport-only recovery. No answer-based retry.')
    return c

def prepare():
    if (ROOT / 'PROTOCOL_LOCK.json').exists():
        old.verify_lock(ROOT)
        return
    old.verify_lock(SOURCE)
    assert sha(SOURCE / 'predictions.jsonl') == SOURCE_PRED_SHA
    assert json.loads((SOURCE / 'PREFLIGHT.json').read_text())['status'] == 'PASS'
    ROOT.mkdir(parents=True, exist_ok=True)
    for name in ('requests.jsonl', 'private_gold.jsonl', 'smoke_ids.json', 'SMOKE_ACCEPTANCE.json', 'PREFLIGHT.json'):
        target = ROOT / name
        if target.exists():
            assert sha(target) == sha(SOURCE / name)
        else:
            shutil.copyfile(SOURCE / name, target)
    rows = load(SOURCE / 'predictions.jsonl')
    keep, excluded = [], []
    for row in rows:
        if row.get('error') == 'RuntimeError:CIRCUIT_STOP_BEFORE_REQUEST':
            excluded.append(row['sample_id'])
        else:
            keep.append(row)
    assert len(keep) == 4486 and len(excluded) == 2
    assert sum(not r.get('error') for r in keep) == 4485
    out = ROOT / 'predictions.jsonl'
    if out.exists():
        assert load(out) == keep, 'PREPARATION_NOT_SAFE_TO_OVERWRITE'
    else:
        write(out, keep, jsonl=True)
    write(ROOT / 'config.json', config())
    write(ROOT / 'RECOVERY.json', dict(created_at=old.now(), source=str(SOURCE),
        source_predictions_sha256=SOURCE_PRED_SHA, inherited_success=4485,
        inherited_http400=1, unsent_circuit_stop_ids_rescheduled=excluded,
        retained_initial_count=len(keep), original_rows_kept_verbatim=True,
        original_predictions_never_written=True, no_policy_retries=True))
    paths = [CODE / p for p in ('resume.py', 'job.sh', 'launch.py')]
    paths += [OLD_CODE / 'run.py', OLD_CODE / 'config.json', ROOT / 'config.json',
              ROOT / 'requests.jsonl', ROOT / 'private_gold.jsonl', ROOT / 'RECOVERY.json', SOURCE / 'predictions.jsonl']
    paths += [Path(p) for p in json.loads((SOURCE/'PROTOCOL_LOCK.json').read_text())['sha256']]
    write(ROOT / 'PROTOCOL_LOCK.json', dict(config=config(), sha256={str(p):sha(p) for p in paths},
        schema=old.SCHEMA, source_lock_sha256=sha(SOURCE / 'PROTOCOL_LOCK.json'),
        code_commit='FILE_HASH_PROVENANCE_NO_GIT_COMMIT_ASSERTED'))
    print(json.dumps({'stage':'prepared','inherited_success':4485,'pending':24196-len(keep)}), flush=True)

class PolicyReject(Exception):
    pass

def error_kind(status, code):
    if status == 400 and code in ('content_policy_violation', 'content_filter'):
        return 'policy'
    if status in (401,403,404) or code in ('insufficient_quota','credit_balance_exhausted',
        'organization_spend_limit_exceeded','project_spend_limit_exceeded',
        'organization_usage_limit_exceeded'):
        return 'fatal'
    if status in (408,429,500,502,503,504):
        return 'transient'
    return 'fatal'

def retry_delay(headers, attempt):
    value = headers.get('Retry-After')
    if value:
        try:
            return max(0, float(value)) + .5
        except ValueError:
            try:
                return max(0, parsedate_to_datetime(value).timestamp()-time.time()) + .5
            except (ValueError, TypeError):
                pass
    return 5 * 2**attempt + random.random()

class Api(old.Api):
    def __init__(self, cfg, root, blocked):
        super().__init__(cfg, root)
        self.blocked = blocked
        self.window = deque()
        self.tpm = cfg['estimated_tokens_per_minute']
        self.started = time.monotonic()
        self.checked_media = set()
        self.media_lock = threading.Lock()

    def slot(self, tokens):
        while not self.stop.is_set():
            with self.lock:
                now = time.monotonic()
                while self.window and self.window[0][0] < now-60:
                    self.window.popleft()
                pause = max(0, self.cooldown-now, self.next_start-now)
                if sum(x[1] for x in self.window)+tokens > self.tpm and self.window:
                    pause = max(pause, self.window[0][0]+60-now+.1)
                if pause <= 0:
                    self.window.append((now,tokens))
                    self.next_start = now + (.5 if now-self.started < 120 else .25)
                    return
            if self.stop.wait(pause):
                break
        raise RuntimeError('CIRCUIT_STOP_BEFORE_REQUEST')

    def call(self, sample):
        if self.stop.is_set():
            return None
        begin=time.monotonic(); media_key=bundle(sample)
        row=dict(sample_id=sample['sample_id'],pair_id=sample.get('pair_id'),component=sample['component'],
            level=sample['level'],run_id=self.cfg['run_id'],model_id=self.cfg['model'],
            protocol_lock_sha256=sha(self.root/'PROTOCOL_LOCK.json'),raw_response='',error=None,
            generated_tokens=0,finish_reason='error',created_at=old.now(),http_attempts=0)
        try:
            with self.lock:
                blocked = bool(media_key and media_key in self.blocked)
            if blocked:
                raise PolicyReject('POLICY_QUARANTINE_SAME_MEDIA_NO_REQUEST')
            # Verify source hash before first use in this continuation, without changing images.
            with self.media_lock:
                for m in sample.get('media',[]):
                    item=(m['path'],m['sha256'])
                    if item not in self.checked_media:
                        assert sha(m['path']) == m['sha256'].removeprefix('sha256:'), 'MEDIA_CHANGED'
                        self.checked_media.add(item)
            body,trace=old.make_body(sample,self.cfg);row['input_trace']=trace
            payload=json.dumps(body).encode();response=None
            reserve=1024+len(sample.get('claim_text',''))+len(sample.get('intervention_text') or '')+1100*len(sample.get('media',[]))
            for attempt in range(1,self.cfg['transport_attempt_limit']+1):
                self.slot(reserve)
                with self.lock:
                    if media_key and media_key in self.blocked:
                        raise PolicyReject('POLICY_QUARANTINE_SAME_MEDIA_NO_REQUEST')
                row['http_attempts']=attempt
                req=urllib.request.Request(self.cfg['endpoint'],data=payload,
                    headers={'Content-Type':'application/json','api-key':self.key,'Authorization':'Bearer '+self.key})
                try:
                    with urllib.request.urlopen(req,timeout=self.cfg['request_timeout_seconds']) as http:
                        response=json.load(http)
                        row['api_request_id']=http.headers.get('x-request-id') or http.headers.get('apim-request-id')
                        row['rate_limits']={k:v for k,v in http.headers.items() if 'ratelimit' in k.lower()}
                        with self.lock:
                            if http.headers.get('x-ratelimit-limit-tokens'):
                                self.tpm=min(self.tpm,max(1,int(http.headers['x-ratelimit-limit-tokens'])*.7))
                    break
                except urllib.error.HTTPError as exc:
                    message=exc.read().decode(errors='replace').replace(self.key,'[REDACTED]')
                    try:
                        detail=json.loads(message).get('error',{});code=detail.get('code','')
                    except (ValueError,AttributeError):
                        code=''
                    self.attempt_record(dict(sample_id=sample['sample_id'],attempt=attempt,at=old.now(),
                        http_status=exc.code,code=code,message=message[:2000]))
                    kind=error_kind(exc.code,code)
                    if kind=='policy':
                        with self.lock:
                            if media_key:self.blocked.add(media_key)
                        row['provider_error_code']=code
                        raise PolicyReject('PROVIDER_CONTENT_POLICY_REJECTION_NO_RETRY') from None
                    if kind=='fatal':
                        raise RuntimeError('FATAL_HTTP_'+str(exc.code)+':'+str(code)) from None
                    with self.lock:
                        self.cooldown=max(self.cooldown,time.monotonic()+retry_delay(exc.headers,attempt))
                except (urllib.error.URLError,TimeoutError,ConnectionError,json.JSONDecodeError) as exc:
                    self.attempt_record(dict(sample_id=sample['sample_id'],attempt=attempt,at=old.now(),
                        error_type=type(exc).__name__,ambiguous_billing_possible=True))
                    with self.lock:
                        self.cooldown=max(self.cooldown,time.monotonic()+5*2**attempt)
            if response is None:
                raise RuntimeError('TRANSPORT_RETRIES_EXHAUSTED')
            row.update(response=response,returned_model=response.get('model'),usage=response.get('usage') or {})
            row['raw_response']=''.join(c.get('text','') for item in response.get('output',[])
                if item.get('type')=='message' and item.get('role')=='assistant'
                for c in item.get('content',[]) if c.get('type')=='output_text')
            row['generated_tokens']=row['usage'].get('output_tokens',0)
            row['finish_reason']='length' if (response.get('incomplete_details') or {}).get('reason')=='max_output_tokens' else 'stop'
            if row['returned_model']!=self.cfg['model'] or row['generated_tokens']>512:
                raise RuntimeError('MODEL_OR_OUTPUT_CAP_CHANGED')
            if response.get('status') not in ('completed','incomplete'):
                raise RuntimeError('UNEXPECTED_RESPONSE_STATUS')
            row['prediction']=old.parse_prediction(row)
        except PolicyReject as exc:
            row.update(error=str(exc),finish_reason='content_filter',policy_rejected=True)
        except Exception as exc:
            row['error']=type(exc).__name__+':'+str(exc).replace(self.key,'[REDACTED]')[:500]
            self.stop.set()
        row['seconds']=round(time.monotonic()-begin,4)
        return row

def infer():
    old.verify_lock(ROOT);cfg=config()
    def guard(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            if Path(os.fsdecode(args[0])).name in {'private_gold.jsonl','scores.jsonl','report.json','rubric.json'}:
                raise PermissionError('INFERENCE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(guard)
    requests=unique(load(ROOT/'requests.jsonl'));out=ROOT/'predictions.jsonl'
    completed=unique(load(out));assert not set(completed)-set(requests)
    blocked=set()
    for r in load(SOURCE/'transport_attempts.jsonl'):
        if r.get('http_status')==400 and 'content_policy_violation' in r.get('message',''):
            blocked.add(bundle(requests[r['sample_id']]))
    for r in completed.values():
        if r.get('policy_rejected'):blocked.add(bundle(requests[r['sample_id']]))
    api=Api(cfg,ROOT,blocked)
    todo=iter(r for sid,r in requests.items() if sid not in completed)
    with cf.ThreadPoolExecutor(max_workers=cfg['workers']) as pool:
        pending=set()
        for _ in range(cfg['workers']):
            r=next(todo,None)
            if r is not None:pending.add(pool.submit(api.call,r))
        while pending:
            done,pending=cf.wait(pending,return_when=cf.FIRST_COMPLETED)
            for f in done:
                row=f.result()
                if row is not None:
                    assert row['sample_id'] not in completed
                    with out.open('a') as stream:
                        stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
                    completed[row['sample_id']]=row
                    state=dict(at=old.now(),recorded=len(completed),expected=len(requests),
                        success=sum(not r.get('error') for r in completed.values()),
                        errors=sum(bool(r.get('error')) for r in completed.values()),
                        inherited_success=4485,last_id=row['sample_id'],job_id=os.environ['SLURM_JOB_ID'])
                    write(ROOT/'PROGRESS.json',state);print(json.dumps(state),flush=True)
                if not api.stop.is_set():
                    r=next(todo,None)
                    if r is not None:pending.add(pool.submit(api.call,r))
    if api.stop.is_set() or len(completed)!=len(requests):
        raise RuntimeError('INCOMPLETE_SEE_PRESERVED_RESPONSES')

def score():
    old.score(config())
    report=json.loads((ROOT/'report.json').read_text());rows=load(ROOT/'predictions.jsonl')
    rejected=[r['sample_id'] for r in rows if r.get('policy_rejected') or r.get('error')=='RuntimeError:HTTP_400']
    t=Counter()
    for r in rows:
        u=r.get('usage',{});d=u.get('input_tokens_details',{})
        t.update(input=u.get('input_tokens',0),output=u.get('output_tokens',0),
            cached=d.get('cached_tokens',0),cache_write=d.get('cache_write_tokens',0))
    cost=((t['input']-t['cached']-t['cache_write'])*.2+t['cached']*.02+t['cache_write']*.25+t['output']*1.2)/1e6
    complete=report['diagnostics']['missing']==0
    other_errors=[r['sample_id'] for r in rows if r.get('error') and r['sample_id'] not in rejected]
    report.update(status=('COMPLETE_WITH_POLICY_REJECTIONS' if rejected else 'COMPLETE') if complete and not other_errors else 'INCOMPLETE_NOT_FINAL',
        policy_rejected_ids=rejected,other_runtime_errors=other_errors,usage_with_cache=dict(t),
        public_price_reference_usd=cost,actual_azure_bill='NOT_VERIFIED',
        price_reference='https://developers.openai.com/api/docs/models/gpt-5.6-luna',
        inherited_success=4485,source_predictions_sha256=SOURCE_PRED_SHA)
    write(ROOT/'report.json',report)
    text=(ROOT/'accuracy_report_cn.md').read_text()
    text=text.replace('状态：INCOMPLETE_NOT_FINAL', '状态：'+report['status'])
    text+='\n续跑复用旧轮 4,485 条成功响应；内容拒绝及同媒体隔离项保留在分母，不伪造模型答案。\n'
    text+=f'\n内容拒绝/隔离记录：{len(rejected)}；其他运行错误：{len(other_errors)}；尚缺：{report["diagnostics"]["missing"]}。\n'
    text+=f'\n合并用量按公开标准价格折算约 ${cost:.4f}（包含旧轮；不是 Azure 已核实账单）。\n'
    (ROOT/'accuracy_report_cn.md').write_text(text)
    print(json.dumps({'status':report['status'],'recorded':len(rows),'policy_rejected':len(rejected),'reference_usd':cost}),flush=True)

def tests():
    import io
    from unittest.mock import patch
    assert error_kind(400,'content_policy_violation')=='policy'
    assert error_kind(401,'')=='fatal'
    assert error_kind(429,'insufficient_quota')=='fatal'
    assert error_kind(429,'rate_limit_exceeded')=='transient'
    assert retry_delay({'Retry-After':'600'},1)>=600
    assert old.parse_prediction({'raw_response':'{"label":"SUPPORTED","confidence":1,"reason":"cut',
        'finish_reason':'length','generated_tokens':512})['label']=='SUPPORTED'
    sample=dict(sample_id='unit_test',component='binary',level='L1',media=[],claim_text='test')
    with patch.dict(os.environ,{'SPACECONFLICT_AZURE_API_KEY':'REDACTED_USE_ENVIRONMENT'}), \
         patch.object(old,'make_body',return_value=({},{})), patch(__name__+'.sha',return_value='testhash'):
        api=Api(config(),ROOT,set());api.attempt_record=lambda r:None
        err=urllib.error.HTTPError('https://unit.invalid',400,'bad',{},
            io.BytesIO(b'{"error":{"code":"content_policy_violation"}}'))
        with patch('urllib.request.urlopen',side_effect=err) as send:
            row=api.call(sample)
            assert row['policy_rejected'] and not api.stop.is_set() and send.call_count==1
        api2=Api(config(),ROOT,set());api2.attempt_record=lambda r:None
        err=urllib.error.HTTPError('https://unit.invalid',401,'unauthorized',{},io.BytesIO(b'{}'))
        with patch('urllib.request.urlopen',side_effect=err) as send:
            row=api2.call(sample)
            assert row['error'].startswith('RuntimeError:FATAL_HTTP_401') and api2.stop.is_set() and send.call_count==1
    print('PASS: mocked content rejection continues without retry, auth stops, quota classification, full Retry-After, retained-prefix scoring')

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['prepare','infer','score','tests'])
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args()
    assert a.run_id==RUN_ID and a.seed==SEED and a.limit is None
    if a.dry_run:print(json.dumps(config()));sys.exit()
    if a.stage!='tests':assert os.environ.get('SLURM_JOB_ID'), 'SLURM_REQUIRED'
    {'prepare':prepare,'infer':infer,'score':score,'tests':tests}[a.stage]()
