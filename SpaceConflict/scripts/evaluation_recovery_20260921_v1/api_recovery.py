"""Versioned transport recovery; original prompts, raw successes and scorers preserved."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time
import urllib.error

CODE=Path(__file__).resolve().parent
BASE=Path('artifacts/model_results')
OPS=BASE/CODE.name

def module(folder,name):
    path=CODE.parent/folder/name
    spec=importlib.util.spec_from_file_location('recovery_'+folder,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def archive(m,root,label,names):
    dest=OPS/'archive'/label;dest.mkdir(parents=True,exist_ok=True)
    for name in names:
        src=root/name;dst=dest/name
        if src.exists() and not dst.exists():shutil.copy2(src,dst)
    return dest

def batch_module():return module('azure_gpt54_batch_20260920_v1','batch.py')

def batch_control():
    m=batch_module();m.old.verify_lock(m.ROOT)
    (OPS/'batch_events').mkdir(parents=True,exist_ok=True)
    archive(m,m.ROOT,'gpt54_initial',('PROGRESS.json','report.json','scores.jsonl','accuracy_report_cn.md'))
    lock=(m.ROOT/'RECOVERY_CONTROLLER.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    m.write(OPS/'BATCH_RECOVERY_LOCK.json',dict(source_lock_sha256=m.sha(m.ROOT/'PROTOCOL_LOCK.json'),
        code_sha256=m.sha(__file__),unchanged_inputs=True,unchanged_generation=True,job_id=os.environ['SLURM_JOB_ID']))
    original=m.Client
    class ReconciledClient(original):
        def __init__(self):
            super().__init__();self.list_cache=None;self.list_at=0
        def all_batches(self):
            if self.list_cache is not None and time.time()-self.list_at<60:return self.list_cache
            items=[];after=None;seen=set()
            while True:
                params={'limit':100}
                if after:params['after']=after
                page=self.call('GET','/batches',params=params).json()
                items.extend(page['data'])
                if not page.get('has_more'):break
                after=page.get('last_id') or page['data'][-1]['id']
                assert after not in seen,'PAGINATION_LOOP';seen.add(after)
            self.list_cache=items;self.list_at=time.time();return items
        def reconcile(self,manifest,state):
            file_id=state.get('file',{}).get('id')
            if not file_id:return None
            matches=[b for b in self.all_batches() if b.get('input_file_id')==file_id]
            if len(matches)>1:raise RuntimeError('DUPLICATE_REMOTE_BATCHES_REQUIRE_REVIEW:'+manifest['name'])
            if not matches:return None
            b=matches[0];meta=b.get('metadata') or {}
            assert meta.get('run_id')==m.RUN_ID and meta.get('part')==manifest['name'],'BATCH_METADATA_MISMATCH'
            assert meta.get('input_sha256')==manifest['sha256'],'BATCH_INPUT_HASH_MISMATCH'
            state.update(batch=b,ambiguous=None,reconciled_at=m.old.now())
            state.pop('last_error',None)
            m.write(m.ROOT/'cloud'/(manifest['name']+'.json'),state)
            print(json.dumps({'event':'RECOVERED_EXISTING_BATCH','part':manifest['name'],'batch':b['id']}),flush=True)
            return state
        def submit(self,manifest):
            path=m.ROOT/'cloud'/(manifest['name']+'.json')
            state=json.loads(path.read_text()) if path.exists() else {}
            if state.get('batch'):return state
            uncertain=state.get('ambiguous') or state.get('recovery_pending') or any(
                tag in state.get('last_error','') for tag in ('HTTP_500:','HTTP_502:','HTTP_503:','HTTP_504:','TRANSPORT_AMBIGUOUS'))
            if uncertain:
                found=self.reconcile(manifest,state)
                if found:return found
                # No blind POST replay: leave only this part pending while other parts advance.
                state['recovery_pending']=True
                state['recovery_checked_at']=m.old.now()
                if state.get('last_error'):state.setdefault('recovery_errors',[]).append(state.pop('last_error'))
                m.write(path,state)
                return state
            try:return super().submit(manifest)
            except (m.ApiFault,RuntimeError) as e:
                message=str(e)
                is_uncertain=(isinstance(e,m.ApiFault) and e.status>=500) or 'TRANSPORT_AMBIGUOUS' in message
                if not is_uncertain:raise
                state=json.loads(path.read_text());state['recovery_pending']=True
                state.setdefault('recovery_errors',[]).append(message)
                state.pop('last_error',None);m.write(path,state)
                m.write(OPS/'batch_events'/f'{manifest["name"]}_{time.time_ns()}.json',dict(part=manifest['name'],error=message))
                print(json.dumps({'event':'POST_UNCERTAIN_RECONCILE_NOT_REPLAY','part':manifest['name']}),flush=True)
                self.list_at=0
                return state
    m.Client=ReconciledClient
    m.control()

def claude_module():
    m=module('azure_claude_opus47_20260920_v1','run.py')
    source=m.ROOT;m.ROOT=BASE/'azure_claude_opus47_resume_20260921_v2';m.RUN_ID=m.ROOT.name
    return m,source

def claude_prepare():
    m,source=claude_module();m.old.verify_lock(source);m.ROOT.mkdir(parents=True,exist_ok=True)
    if (m.ROOT/'RECOVERY_READY.json').exists():m.old.verify_lock(m.ROOT);return
    # Fresh tiny text-only authentication check; never rerun benchmark answers as a gate.
    m.probe()
    for name in ('requests.jsonl','private_gold.jsonl','smoke_ids.json','PREFLIGHT.json'):
        dest=m.ROOT/name
        if not dest.exists():shutil.copy2(source/name,dest)
        assert m.sha(dest)==m.sha(source/name)
    kept=[];retry=[]
    with (source/'predictions.jsonl').open() as f:
        for line in f:
            row=json.loads(line);error=row.get('error') or ''
            if error and not row.get('policy_rejected'):
                assert error=='RuntimeError:CIRCUIT_STOP_BEFORE_REQUEST' or 'invalid_model_endpoint_authentication' in error,'UNREVIEWED_RETRY_TYPE'
                assert not row.get('raw_response') and not row.get('response'),'MODEL_RESPONSE_MUST_NOT_BE_RETRIED'
                retry.append(row)
            else:kept.append(line)
    predictions=m.ROOT/'predictions.jsonl'
    assert not predictions.exists(),'PARTIAL_PREPARE_REQUIRES_INSPECTION'
    with predictions.open('x') as f:f.writelines(kept)
    m.write(m.ROOT/'inherited_transport_errors.jsonl',retry,jsonl=True)
    cfg=m.config();cfg.update(inherited_predictions=len(kept),recovery_source=str(source),
        retry_policy='Only missing/no-answer transport failures; successful responses and refusals never retried')
    m.write(m.ROOT/'config.json',cfg)
    paths=[m.ROOT/n for n in ('config.json','requests.jsonl','private_gold.jsonl','smoke_ids.json','SETUP_PROBE_sdk_auth.json')]
    paths += [CODE/'api_recovery.py',CODE/'api_job.sh',source/'predictions.jsonl',source/'PROTOCOL_LOCK.json']
    hashes=json.loads((source/'PROTOCOL_LOCK.json').read_text())['sha256']
    hashes.update({str(p):m.sha(p) for p in paths})
    m.write(m.ROOT/'PROTOCOL_LOCK.json',dict(config=cfg,sha256=hashes,schema=m.old.SCHEMA,
        provider_schema=m.schema(),seed=m.SEED,source_success_rows_unchanged=True))
    m.write(m.ROOT/'RECOVERY_READY.json',dict(source=str(source),inherited=len(kept),
        retried_transport_errors=len(retry),pending=24196-len(kept),inherited_sha256=m.sha(predictions)))
    print(json.dumps({'inherited':len(kept),'pending':24196-len(kept)}),flush=True)

def claude_infer():
    m,source=claude_module()
    handle=(m.ROOT/'INFERENCE.lock').open('a');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    original=m.http
    def transient_backend_auth(body,secret):
        for attempt in range(4):
            try:return original(body,secret)
            except urllib.error.HTTPError as e:
                if e.code!=500:raise
                payload=e.read()
                import io
                e.fp=io.BytesIO(payload);e.read=e.fp.read
                if b'invalid_model_endpoint_authentication' not in payload or attempt==3:raise
                # Explicit backend pre-inference rejection; no successful answer exists.
                m.write(m.ROOT/f'backend_auth_retry_{time.time_ns()}.json',
                    dict(at=m.old.now(),attempt=attempt+1,http_status=500,code='invalid_model_endpoint_authentication'))
                time.sleep(60*(attempt+1))
    m.http=transient_backend_auth
    m.infer()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['batch-control','batch-score','claude-prepare','claude-infer','claude-score'])
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true')
    p.add_argument('--seed',type=int,default=20260920);p.add_argument('--run-id',default=CODE.name);p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.seed==20260920 and a.run_id==CODE.name and a.limit is None
    if a.dry_run:print(a.stage);return
    assert os.environ.get('SLURM_JOB_ID'),'SLURM_REQUIRED'
    if a.stage=='batch-control':batch_control()
    elif a.stage=='batch-score':batch_module().score()
    elif a.stage=='claude-prepare':claude_prepare()
    elif a.stage=='claude-infer':claude_infer()
    else:claude_module()[0].score()

if __name__=='__main__':main()
