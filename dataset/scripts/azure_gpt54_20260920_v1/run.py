"""Independent GPT-5.4 evaluation of the same complete frozen release."""
import argparse
import concurrent.futures as cf
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import sys
from transport import Api, allowed_model, old, sha, bundle
from resume import error_kind, retry_delay

CODE=Path(__file__).resolve().parent
ROOT=Path('artifacts/model_results/azure_gpt54_20260920_v1')
SOURCE=ROOT.parent/'azure_luna_20260920_v1'
RUN_ID=ROOT.name
SEED=20260920
load,unique,write=old.load,old.unique,old.write

def config():
    c=json.loads((CODE.parent/'azure_luna_20260920_v1/config.json').read_text())
    c.update(run_id=RUN_ID,output_root=str(ROOT),model='gpt-5.4',
        allowed_returned_models=['gpt-5.4','gpt-5.4-2026-03-05'],workers=16,
        minimum_request_interval_seconds=.25,estimated_tokens_per_minute=600000,
        notes='Independent GPT-5.4 outputs, same frozen protocol as Luna; no inherited answers. No paid judge. Online, not Batch.')
    return c

def prepare():
    if (ROOT/'PROTOCOL_LOCK.json').exists():
        old.verify_lock(ROOT);return
    old.verify_lock(SOURCE)
    c=config();ROOT.mkdir(parents=True,exist_ok=True)
    assert json.loads((SOURCE/'PREFLIGHT.json').read_text())['status']=='PASS'
    for name in ('requests.jsonl','private_gold.jsonl','smoke_ids.json','PREFLIGHT.json'):
        dest=ROOT/name
        if dest.exists():assert sha(dest)==sha(SOURCE/name)
        else:shutil.copyfile(SOURCE/name,dest)
    req=unique(load(ROOT/'requests.jsonl'))
    assert len(req)==24196 and sha(ROOT/'requests.jsonl')==c['source_requests_sha256']
    assert sha(ROOT/'private_gold.jsonl')==c['source_gold_sha256']
    assert set(req)==set(unique(load(ROOT/'private_gold.jsonl')))
    # Do not resend identical media already explicitly rejected by this Azure endpoint.
    rejected=[]
    for r in load(SOURCE/'transport_attempts.jsonl'):
        if r.get('http_status')==400 and 'content_policy_violation' in r.get('message',''):
            rejected.append(dict(source=str(SOURCE/'transport_attempts.jsonl'),sample_id=r['sample_id'],
                media_sha256=list(bundle(req[r['sample_id']])),reason='PRIOR_EXPLICIT_AZURE_IMAGE_POLICY_REJECTION'))
    write(ROOT/'policy_quarantine.json',rejected)
    write(ROOT/'config.json',c)
    paths=[CODE/n for n in ('run.py','transport.py','launch.py','job.sh')]
    paths += [CODE.parent/'azure_luna_resume_20260920_v2/resume.py',ROOT/'config.json',
        ROOT/'requests.jsonl',ROOT/'private_gold.jsonl',ROOT/'policy_quarantine.json',ROOT/'smoke_ids.json',ROOT/'CONNECTIVITY.json']
    paths += [Path(p) for p in json.loads((SOURCE/'PROTOCOL_LOCK.json').read_text())['sha256']]
    write(ROOT/'PROTOCOL_LOCK.json',dict(config=c,sha256={str(p):sha(p) for p in paths},schema=old.SCHEMA,
        inherited_predictions=0,source_protocol_sha256=sha(SOURCE/'PROTOCOL_LOCK.json'),
        code_commit='FILE_HASH_PROVENANCE_NO_GIT_COMMIT_ASSERTED'))
    print(json.dumps({'stage':'PREPARED','inputs':len(req),'model':c['model']}),flush=True)

def infer():
    old.verify_lock(ROOT);c=config()
    def guard(event,args):
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            if Path(os.fsdecode(args[0])).name in {'private_gold.jsonl','scores.jsonl','report.json','rubric.json'}:
                raise PermissionError('INFERENCE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(guard)
    req=unique(load(ROOT/'requests.jsonl'));out=ROOT/'predictions.jsonl'
    completed=unique(load(out)) if out.exists() else {}
    assert not set(completed)-set(req)
    digest=sha(ROOT/'PROTOCOL_LOCK.json')
    for r in completed.values():
        assert r['protocol_lock_sha256']==digest and r['model_id']==c['model']
        if r.get('error') and not r.get('policy_rejected'):
            raise ValueError('EXPLICIT_RECOVERY_REQUIRED_FOR_PRIOR_RUNTIME_ERROR')
    blocked={tuple(r['media_sha256']) for r in json.loads((ROOT/'policy_quarantine.json').read_text())}
    blocked.update(bundle(req[r['sample_id']]) for r in completed.values() if r.get('policy_rejected'))
    api=Api(c,ROOT,blocked)
    def save(row):
        if row is None:return
        assert row['sample_id'] not in completed
        with out.open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        completed[row['sample_id']]=row
        state=dict(at=old.now(),recorded=len(completed),expected=len(req),
            success=sum(not r.get('error') for r in completed.values()),
            policy_rejections=sum(bool(r.get('policy_rejected')) for r in completed.values()),
            errors=sum(bool(r.get('error')) for r in completed.values()),
            last_id=row['sample_id'],job_id=os.environ['SLURM_JOB_ID'])
        write(ROOT/'PROGRESS.json',state);print(json.dumps(state),flush=True)
    ids=json.loads((ROOT/'smoke_ids.json').read_text())
    for sid in ids:
        if sid not in completed:save(api.call(req[sid]))
        if api.stop.is_set():raise RuntimeError('SMOKE_RUNTIME_FAILED')
    smoke=[completed[s] for s in ids]
    parsed=[old.parse_prediction(r) for r in smoke]
    # No correctness gate or prompt tuning; malformed outputs remain measurable.
    passed=all(not r.get('error') and allowed_model(r.get('returned_model'),c) for r in smoke)
    write(ROOT/'SMOKE_ACCEPTANCE.json',dict(status='PASS' if passed else 'BLOCKED_INTERFACE',n=len(smoke),
        schema_valid=sum(r['schema_valid'] for r in parsed),accuracy_gate=False,
        reused_in_full=True,completed_at=old.now(),usage_input=sum(r.get('usage',{}).get('input_tokens',0) for r in smoke)))
    if not passed:raise RuntimeError('SMOKE_OPERATIONAL_FAILED')
    todo=iter(r for sid,r in req.items() if sid not in completed)
    with cf.ThreadPoolExecutor(max_workers=c['workers']) as pool:
        pending=set()
        for _ in range(c['workers']):
            r=next(todo,None)
            if r is not None:pending.add(pool.submit(api.call,r))
        while pending:
            done,pending=cf.wait(pending,return_when=cf.FIRST_COMPLETED)
            for future in done:
                save(future.result())
                if not api.stop.is_set():
                    r=next(todo,None)
                    if r is not None:pending.add(pool.submit(api.call,r))
    if api.stop.is_set() or len(completed)!=len(req):raise RuntimeError('INCOMPLETE_SEE_PRESERVED_RESPONSES')

def score():
    old.score(config())
    report=json.loads((ROOT/'report.json').read_text());rows=load(ROOT/'predictions.jsonl') if (ROOT/'predictions.jsonl').exists() else []
    rejected=[r['sample_id'] for r in rows if r.get('policy_rejected')]
    other=[r['sample_id'] for r in rows if r.get('error') and not r.get('policy_rejected')]
    status=('COMPLETE_WITH_POLICY_REJECTIONS' if rejected else 'COMPLETE') if len(rows)==24196 and not other else 'INCOMPLETE_NOT_FINAL'
    totals=Counter()
    for r in rows+[json.loads((ROOT/'CONNECTIVITY.json').read_text())]:
        u=r.get('usage',{});d=u.get('input_tokens_details',{})
        totals.update(input=u.get('input_tokens',0),output=u.get('output_tokens',0),
            cached=d.get('cached_tokens',0),cache_write=d.get('cache_write_tokens',0))
    # GPT-5.4 ordinary/cached input rates; no unverified separate Azure write premium.
    reference=((totals['input']-totals['cached'])*2.5+totals['cached']*.25+totals['output']*15)/1e6
    report.update(status=status,policy_rejected_ids=rejected,other_errors=other,
        usage_including_connectivity=dict(totals),public_price_reference_usd=reference,
        pricing_reference='https://developers.openai.com/api/docs/models/gpt-5.4',
        azure_actual_bill='NOT_VERIFIED',inherited_predictions=0)
    write(ROOT/'report.json',report)
    text=(ROOT/'accuracy_report_cn.md').read_text().replace('GPT-5.6 Luna','GPT-5.4')
    text=text.replace('状态：INCOMPLETE_NOT_FINAL','状态：'+status)
    text+=f'\n内容拒绝/同媒体隔离：{len(rejected)}；其他错误：{len(other)}。拒绝项仍在分母，不伪造模型答案。\n'
    text+=f'\n本轮独立用量按公开价格折算 ${reference:.4f}，含连接测试、不含 Luna；Azure 实际账单未核实。\n'
    (ROOT/'accuracy_report_cn.md').write_text(text)
    print(json.dumps({'status':status,'recorded':len(rows),'model':'gpt-5.4','reference_usd':reference}),flush=True)

def tests():
    c=config();assert c['model']=='gpt-5.4' and c['max_output_tokens']==512 and c['reasoning_effort']=='none'
    assert allowed_model('gpt-5.4-2026-03-05',c) and not allowed_model('gpt-5.6-luna',c)
    assert error_kind(400,'content_policy_violation')=='policy' and error_kind(401,'')=='fatal'
    assert retry_delay({'Retry-After':'600'},1)>=600
    assert old.parse_prediction({'raw_response':'{"label":"SUPPORTED","confidence":1,"reason":"cut',
        'finish_reason':'length','generated_tokens':512})['label']=='SUPPORTED'
    print('PASS: GPT-5.4 model allowlist, frozen 512/none, rejection handling, full Retry-After, prefix scoring')

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('stage',choices=['prepare','infer','score','tests'])
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();assert a.run_id==RUN_ID and a.seed==SEED and a.limit is None
    if a.dry_run:print(json.dumps(config()));sys.exit()
    if a.stage!='tests':assert os.environ.get('SLURM_JOB_ID'), 'SLURM_REQUIRED'
    {'prepare':prepare,'infer':infer,'score':score,'tests':tests}[a.stage]()
