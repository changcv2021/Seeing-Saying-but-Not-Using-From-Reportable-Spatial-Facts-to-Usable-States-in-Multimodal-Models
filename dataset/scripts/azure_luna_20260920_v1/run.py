"""Azure adapter for immutable SpaceConflict inputs; credentials never serialized."""
import argparse
import base64
import concurrent.futures
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

CODE = Path(__file__).resolve().parent
PROJECT = CODE.parent.parent
LEGACY = CODE.parent / 'full_multimodel_20260908_v1'
sys.path[:0] = [str(LEGACY), str(PROJECT / 'src')]
from common import load, unique, sha, write, metrics
from protocol import messages_for
from output_policy import parse_prediction, gate_usable

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'label': {'type': 'string', 'enum': ['SUPPORTED', 'CONTRADICTORY', 'UNKNOWN']},
        'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'reason': {'type': 'string'},
    }, 'required': ['label', 'confidence', 'reason'],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def freeze(cfg):
    root, source = Path(cfg['output_root']), Path(cfg['source_root'])
    if sha(source / 'requests.jsonl') != cfg['source_requests_sha256']:
        raise ValueError('SOURCE_REQUEST_HASH_CHANGED')
    if sha(source / 'private_gold.jsonl') != cfg['source_gold_sha256']:
        raise ValueError('SOURCE_GOLD_HASH_CHANGED')
    req, gold = unique(load(source / 'requests.jsonl')), unique(load(source / 'private_gold.jsonl'))
    if set(req) != set(gold) or len(req) != cfg['expected_inputs']:
        raise ValueError('SOURCE_COVERAGE_MISMATCH')
    root.mkdir(parents=True, exist_ok=True)
    for name in ('requests.jsonl', 'private_gold.jsonl'):
        target = root / name
        if not target.exists():
            shutil.copyfile(source / name, target)
        if sha(target) != sha(source / name):
            raise ValueError('EXISTING_COPY_CHANGED:' + name)
    files = [CODE / x for x in ('config.json', 'run.py', 'job.sh', 'launch.py')]
    files += [LEGACY / x for x in ('common.py', 'output_policy.py', 'protocol.py')]
    files += [PROJECT / 'src/spaceconflict/mllm_l4.py', root / 'requests.jsonl', root / 'private_gold.jsonl']
    lock = {'config': cfg, 'sha256': {str(p): sha(p) for p in files}, 'schema': SCHEMA,
            'code_commit': 'FILE_HASH_PROVENANCE_NO_GIT_COMMIT_ASSERTED'}
    lockpath = root / 'PROTOCOL_LOCK.json'
    if lockpath.exists() and json.loads(lockpath.read_text()) != lock:
        raise ValueError('FROZEN_PROTOCOL_CHANGED')
    if not lockpath.exists():
        write(lockpath, lock)
    smoke = []
    for level in ('L1', 'L2', 'L3', 'L4'):
        choices = [r for r in req.values() if r['level'] == level]
        choices.sort(key=lambda r: digest([cfg['seed'], 'interface_smoke', r['sample_id']]))
        smoke += choices[:cfg['smoke_per_level']]
    write(root / 'smoke_ids.json', [r['sample_id'] for r in smoke])
    # Audit every referenced path/hash on the compute node before external calls.
    media = {}
    for r in req.values():
        for m in r.get('media', []):
            if m.get('kind') != 'image':
                raise ValueError('UNEXPECTED_NON_IMAGE_MEDIA')
            if m['path'] in media and media[m['path']] != m['sha256']:
                raise ValueError('MEDIA_HASH_CONFLICT')
            media[m['path']] = m['sha256']
    bad = []
    for path, expected in media.items():
        if not Path(path).is_file():
            bad.append({'path': path, 'reason': 'MISSING'})
        elif sha(path) != expected.removeprefix('sha256:'):
            bad.append({'path': path, 'reason': 'HASH_MISMATCH'})
    report = dict(status='PASS' if not bad else 'BLOCKED_MEDIA', created_at=now(),
                  requests=len(req), levels=dict(Counter(r['level'] for r in req.values())),
                  media_occurrences=sum(len(r.get('media', [])) for r in req.values()),
                  unique_media=len(media), media_failures=bad, smoke_ids=[r['sample_id'] for r in smoke])
    write(root / 'PREFLIGHT.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('media_failures', 'smoke_ids')}), flush=True)
    if bad:
        raise ValueError('MEDIA_PREFLIGHT_FAILED_NO_SUBSTITUTION')


def verify_lock(root):
    lock = json.loads((root / 'PROTOCOL_LOCK.json').read_text())
    for path, expected in lock['sha256'].items():
        if sha(path) != expected:
            raise ValueError('PROTOCOL_FILE_CHANGED:' + path)
    return lock


def make_body(sample, cfg):
    from PIL import Image
    old = messages_for(sample, cfg['media_budget'])
    content, visual, media_i = [], [], 0
    for item in old[1]['content']:
        if item['type'] == 'text':
            content.append({'type': 'input_text', 'text': item['text']})
            continue
        if item['type'] != 'image':
            raise ValueError('NON_IMAGE_AFTER_FROZEN_FRAME_EXTRACTION')
        media = sample['media'][media_i]
        media_i += 1
        with Image.open(media['path']) as source:
            im = source.convert('RGB')
        try:
            cap = media.get('presentation_max_pixels', 401408)
            if im.width * im.height > cap:
                scale = math.sqrt(cap / (im.width * im.height))
                resized = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.Resampling.BICUBIC)
                im.close()
                im = resized
            buf = io.BytesIO()
            im.save(buf, format='PNG')
            data = buf.getvalue()
            visual.append(dict(path=media['path'], role=media.get('role'), size=list(im.size),
                               rgb_sha256=hashlib.sha256(im.tobytes()).hexdigest(),
                               submitted_png_sha256=hashlib.sha256(data).hexdigest()))
            content.append(dict(type='input_image', detail=cfg['image_detail'],
                                image_url='data:image/png;base64,' + base64.b64encode(data).decode()))
        finally:
            im.close()
    body = dict(model=cfg['model'], store=False, reasoning={'effort': cfg['reasoning_effort']},
                max_output_tokens=cfg['max_output_tokens'],
                input=[{'role': 'system', 'content': old[0]['content']}, {'role': 'user', 'content': content}],
                text={'format': {'type': 'json_schema', 'name': 'spaceconflict_verdict', 'strict': True, 'schema': SCHEMA}})
    # Persist only text, metadata and hashes, never the data URLs or credentials.
    trace = dict(system=old[0]['content'], ordered_text=[c['text'] for c in content if c['type'] == 'input_text'],
                 visual_inputs=visual, body_sha256=digest(body), detail=cfg['image_detail'])
    return body, trace


class Api:
    def __init__(self, cfg, root):
        self.cfg, self.root = cfg, root
        self.key = os.environ.get('SPACECONFLICT_AZURE_API_KEY', '')
        if not self.key:
            raise ValueError('AZURE_CREDENTIAL_MISSING')
        self.lock, self.write_lock = threading.Lock(), threading.Lock()
        self.next_start, self.cooldown = 0.0, 0.0
        self.stop = threading.Event()

    def wait_slot(self):
        with self.lock:
            start = max(time.monotonic(), self.next_start, self.cooldown)
            self.next_start = start + self.cfg['minimum_request_interval_seconds']
        if self.stop.wait(max(0, start - time.monotonic())):
            raise RuntimeError('CIRCUIT_STOP_BEFORE_REQUEST')

    def attempt_record(self, row):
        with self.write_lock:
            with (self.root / 'transport_attempts.jsonl').open('a') as f:
                f.write(json.dumps(row) + '\n')

    def call(self, sample):
        if self.stop.is_set():
            return None
        begin = time.monotonic()
        row = dict(sample_id=sample['sample_id'], pair_id=sample.get('pair_id'), component=sample['component'],
                   level=sample['level'], run_id=self.cfg['run_id'], model_id=self.cfg['model'],
                   protocol_lock_sha256=sha(self.root / 'PROTOCOL_LOCK.json'), raw_response='', error=None,
                   generated_tokens=0, finish_reason='error', created_at=now())
        try:
            body, trace = make_body(sample, self.cfg)
            row['input_trace'] = trace
            payload = json.dumps(body).encode()
            response = None
            for attempt in range(1, self.cfg['transport_attempt_limit'] + 1):
                self.wait_slot()
                req = urllib.request.Request(self.cfg['endpoint'], data=payload,
                      headers={'Content-Type': 'application/json', 'api-key': self.key,
                               'Authorization': 'Bearer ' + self.key})
                try:
                    with urllib.request.urlopen(req, timeout=self.cfg['request_timeout_seconds']) as http:
                        response = json.load(http)
                        row['api_request_id'] = http.headers.get('x-request-id') or http.headers.get('apim-request-id')
                        row['rate_limits'] = {k: v for k, v in http.headers.items() if 'ratelimit' in k.lower()}
                    break
                except urllib.error.HTTPError as exc:
                    message = exc.read().decode(errors='replace')[:2000].replace(self.key, '[REDACTED]')
                    self.attempt_record(dict(sample_id=sample['sample_id'], attempt=attempt, at=now(),
                                             http_status=exc.code, message=message))
                    if exc.code not in (408, 429, 500, 502, 503, 504):
                        raise RuntimeError('HTTP_' + str(exc.code)) from None
                    try:
                        delay = float(exc.headers.get('Retry-After', 2 ** attempt * 5))
                    except ValueError:
                        delay = 2 ** attempt * 5
                    with self.lock:
                        self.cooldown = max(self.cooldown, time.monotonic() + min(max(delay, 1), 300))
                except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
                    self.attempt_record(dict(sample_id=sample['sample_id'], attempt=attempt, at=now(),
                                             error_type=type(exc).__name__, ambiguous_billing_possible=True))
                    with self.lock:
                        self.cooldown = max(self.cooldown, time.monotonic() + 2 ** attempt * 5)
            if response is None:
                raise RuntimeError('TRANSPORT_RETRIES_EXHAUSTED')
            row['response'] = response
            row['returned_model'] = response.get('model')
            row['usage'] = response.get('usage') or {}
            row['raw_response'] = ''.join(c.get('text', '') for item in response.get('output', [])
                         if item.get('type') == 'message' and item.get('role') == 'assistant'
                         for c in item.get('content', []) if c.get('type') == 'output_text')
            row['generated_tokens'] = row['usage'].get('output_tokens', 0)
            row['finish_reason'] = 'length' if (response.get('incomplete_details') or {}).get('reason') == 'max_output_tokens' else 'stop'
            if row['generated_tokens'] > 512:
                raise RuntimeError('SERVER_EXCEEDED_FROZEN_OUTPUT_CAP')
            if response.get('status') not in ('completed', 'incomplete'):
                raise RuntimeError('UNEXPECTED_RESPONSE_STATUS')
            row['prediction'] = parse_prediction(row)
        except Exception as exc:
            row['error'] = type(exc).__name__ + ':' + str(exc).replace(self.key, '[REDACTED]')[:500]
            self.stop.set()
        row['seconds'] = round(time.monotonic() - begin, 4)
        return row


def infer(cfg, resume):
    root = Path(cfg['output_root'])
    verify_lock(root)
    # From here the inference process cannot open gold or scores.
    def guard(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name
            if name in {'private_gold.jsonl', 'scores.jsonl', 'report.json', 'rubric.json'}:
                raise PermissionError('INFERENCE_GOLD_ACCESS_FORBIDDEN')
    sys.addaudithook(guard)
    requests = unique(load(root / 'requests.jsonl'))
    out = root / 'predictions.jsonl'
    prior = unique(load(out)) if out.exists() else {}
    if prior and not resume:
        raise ValueError('RESUME_REQUIRED')
    if set(prior) - set(requests):
        raise ValueError('UNEXPECTED_PREDICTION_ID')
    if any(r['protocol_lock_sha256'] != sha(root / 'PROTOCOL_LOCK.json') for r in prior.values()):
        raise ValueError('PRIOR_PROTOCOL_CHANGED')
    if any(r.get('error') for r in prior.values()):
        raise ValueError('PRIOR_ERRORS_REQUIRE_EXPLICIT_RECOVERY_NO_SILENT_RETRY')
    api = Api(cfg, root)
    completed = dict(prior)
    def save_row(row):
        if row is None:
            return
        with out.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        completed[row['sample_id']] = row
        state = dict(at=now(), returned=len(completed), expected=len(requests),
                     errors=sum(bool(r.get('error')) for r in completed.values()),
                     last_id=row['sample_id'], job_id=os.environ.get('SLURM_JOB_ID'))
        write(root / 'PROGRESS.json', state)
        print(json.dumps(state), flush=True)
    smoke_ids = json.loads((root / 'smoke_ids.json').read_text())
    for sid in smoke_ids:
        if sid not in completed:
            save_row(api.call(requests[sid]))
        if api.stop.is_set():
            raise RuntimeError('SMOKE_TRANSPORT_BLOCKED')
    smoke_rows = [completed[sid] for sid in smoke_ids]
    usable = sum(gate_usable(parse_prediction(r), r) for r in smoke_rows)
    # Gate never reads gold or accuracy; observed nulls/invalids are retained.
    smoke_ok = usable == len(smoke_rows) and all(r.get('returned_model') == cfg['model'] for r in smoke_rows)
    write(root / 'SMOKE_ACCEPTANCE.json', dict(status='PASS' if smoke_ok else 'BLOCKED_INTERFACE',
           n=len(smoke_rows), usable=usable, selection='HASH_RANK_PER_LEVEL_NO_GOLD', accuracy_used=False,
           output_tokens=sum(r['usage'].get('output_tokens', 0) for r in smoke_rows),
           seconds=sum(r['seconds'] for r in smoke_rows),
           reused_in_full=True, completed_at=now()))
    if not smoke_ok:
        raise RuntimeError('SMOKE_INTERFACE_FAILED_NO_PROMPT_TUNING')
    todo = iter(r for sid, r in requests.items() if sid not in completed)
    with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['workers']) as pool:
        pending = set()
        for _ in range(cfg['workers']):
            sample = next(todo, None)
            if sample is not None:
                pending.add(pool.submit(api.call, sample))
        while pending:
            done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                save_row(future.result())
                if not api.stop.is_set():
                    sample = next(todo, None)
                    if sample is not None:
                        pending.add(pool.submit(api.call, sample))
    if api.stop.is_set() or len(completed) != len(requests):
        raise RuntimeError('INCOMPLETE_SEE_PRESERVED_RESPONSES')


def score(cfg):
    root = Path(cfg['output_root'])
    verify_lock(root)
    gold = unique(load(root / 'private_gold.jsonl'))
    predictions = unique(load(root / 'predictions.jsonl')) if (root / 'predictions.jsonl').exists() else {}
    if set(predictions) - set(gold):
        raise ValueError('EXTRA_PREDICTIONS')
    scored = []
    for sid, g in gold.items():
        pred = predictions.get(sid, {})
        parsed = parse_prediction(pred)
        if pred.get('error'):
            parsed['label'] = None
        scored.append(dict(g, **parsed, missing_prediction=sid not in predictions, runtime_error=pred.get('error'),
                           correct=parsed['label'] == g['gold']))
    write(root / 'scores.jsonl', scored, jsonl=True)
    groups = defaultdict(list)
    for r in scored:
        groups[r['level']].append(r)
    complete = len(predictions) == len(gold) and not any(r.get('error') for r in predictions.values())
    totals = {key: sum(r.get('usage', {}).get(key, 0) for r in predictions.values())
              for key in ('input_tokens', 'output_tokens', 'total_tokens')}
    report = dict(status='COMPLETE' if complete else 'INCOMPLETE_NOT_FINAL', created_at=now(),
                  run_id=cfg['run_id'], model=cfg['model'], api_mode=cfg['api_mode'], expected=len(gold),
                  returned=len(predictions), overall=metrics(scored),
                  by_level={k: metrics(v) for k, v in sorted(groups.items())},
                  test_only=metrics([r for r in scored if r['split'] == 'test']),
                  diagnostics={'missing': len(gold)-len(predictions),
                     'runtime_errors': sum(bool(r.get('error')) for r in predictions.values()),
                     'schema_invalid_returned': sum(not parse_prediction(r)['schema_valid'] for r in predictions.values()),
                     'truncated': sum(r.get('finish_reason') == 'length' for r in predictions.values())},
                  usage=totals, scoring_policy=cfg['scoring_policy'], azure_cost='NOT_KNOWN_FROM_OPENAI_PUBLIC_PRICE',
                  files={p.name: sha(p) for p in (root / 'PROTOCOL_LOCK.json', root / 'scores.jsonl')},
                  all_split_is_descriptive_not_scene_disjoint_test=True, paid_judge=False)
    if (root / 'predictions.jsonl').exists():
        report['files']['predictions.jsonl'] = sha(root / 'predictions.jsonl')
    write(root / 'report.json', report)
    lines = ['# SpaceConflict × GPT-5.6 Luna（Azure）', '',
             f"状态：{report['status']}；已返回 {len(predictions):,}/{len(gold):,}。", '',
             '沿用冻结输入与原评分器；关闭额外推理，API 总输出上限 512，严格 JSON 传输。',
             '未完成时下表只表示固定全量分母下的阶段计数，不是最终准确率。', '',
             '| 范围 | 输入数 | 正确数 | Claim Accuracy | Pair Accuracy |', '|---|---:|---:|---:|---:|']
    for name, rs in [('ALL', scored)] + sorted(groups.items()):
        m = metrics(rs)
        pair = 'N/A' if m['pair_accuracy'] is None else f"{100*m['pair_accuracy']:.2f}%"
        lines.append(f"| {name} | {len(rs)} | {sum(r['correct'] for r in rs)} | {100*m['claim_accuracy']:.2f}% | {pair} |")
    lines += ['', 'UNKNOWN 纳入三分类准确率；S/C 两成员都正确才计 pair 正确。',
              '缺失、运行错误或未解析标签不从全量分母中删除；截断按实际输出前缀评分。',
              '本轮只做主指标，不另调用解释 judge。API 用量见 report.json，Azure 实际费用以实验室账单为准。',
              '原始响应与逐请求媒体 RGB/PNG hash：predictions.jsonl；逐样本评分：scores.jsonl。',
              '历史 release/gold/predictions 均未覆盖。全量 all-split 不是独立 held-out 泛化测试。', '']
    (root / 'accuracy_report_cn.md').write_text('\n'.join(lines))
    print(json.dumps(dict(status=report['status'], returned=len(predictions), usage=totals)), flush=True)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('stage', choices=['prepare', 'infer', 'score', 'selftest'])
    p.add_argument('--run-id', default='azure_luna_20260920_v1')
    p.add_argument('--seed', type=int, default=20260920)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--limit', type=int)
    args = p.parse_args()
    cfg = json.loads((CODE / 'config.json').read_text())
    if args.run_id != cfg['run_id'] or args.seed != cfg['seed'] or args.limit is not None:
        raise ValueError('FROZEN_CONFIG_MISMATCH_OR_UNAUTHORIZED_SUBSET')
    if args.dry_run:
        print(json.dumps(cfg))
        return
    if args.stage == 'selftest':
        assert parse_prediction({'raw_response': '{"label":"SUPPORTED","confidence":0.8,"reason":"ok"}'})['label'] == 'SUPPORTED'
        assert parse_prediction({'raw_response': '{"label":"SUPPORTED","confidence":0.8,"reason":"cut', 'finish_reason': 'length', 'generated_tokens': 512})['label'] == 'SUPPORTED'
        assert parse_prediction({'raw_response': 'SUPPORTED'})['label'] is None
        assert parse_prediction({'raw_response': '{"label":"SUPPORTED","label":"UNKNOWN"}'})['label'] is None
        print('PASS: strict JSON, retained prefix, no bare-label guessing, duplicate rejection')
        return
    if not os.environ.get('SLURM_JOB_ID') or socket.gethostname().startswith('login'):
        raise ValueError('COMPUTE_ALLOCATION_REQUIRED')
    if args.stage == 'prepare':
        freeze(cfg)
    elif args.stage == 'infer':
        infer(cfg, args.resume)
    else:
        score(cfg)


if __name__ == '__main__':
    main()
