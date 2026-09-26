"""Transport adapter derived from Luna v2; originals remain read-only."""
from collections import deque
from pathlib import Path
import json
import sys
import threading
import time
import urllib.error
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'azure_luna_resume_20260920_v2'))
from resume import old, sha, bundle, PolicyReject, error_kind, retry_delay

def allowed_model(value, cfg):
    return value in cfg['allowed_returned_models']

class Api(old.Api):
    def __init__(self, cfg, root, blocked):
        super().__init__(cfg, root)
        self.blocked = blocked
        self.window = deque()
        self.tpm = cfg['estimated_tokens_per_minute']
        self.interval = cfg['minimum_request_interval_seconds']
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
                    self.next_start = now + max(self.interval, .5 if now-self.started < 120 else .25)
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
                            if http.headers.get('x-ratelimit-limit-requests'):
                                self.interval=max(self.interval,60/(max(1,int(http.headers['x-ratelimit-limit-requests']))*.7))
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
            if not allowed_model(row['returned_model'], self.cfg) or row['generated_tokens']>512:
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


