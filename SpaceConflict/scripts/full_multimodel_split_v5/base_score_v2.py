"""Exact primary scoring. Failed inference stays in the eligible denominator."""
import argparse
import collections
import json
from pathlib import Path
from common import load, unique, parse, metrics, write, sha, RUBRIC
from output_policy import parse_prediction, gate_usable, POLICY_VERSION, TOKEN_LIMIT, NORMALIZATION_VERSION

def score(args):
    root = args.run_root
    requests = unique(load(root/('smoke.jsonl' if args.scope=='smoke' else 'requests.jsonl')))
    gold = unique(load(root/'private_gold.jsonl'))
    files = sorted((root/args.scope).glob('predictions_*.jsonl'))
    predictions = unique([row for path in files for row in load(path)])
    if set(predictions) - set(requests):
        raise ValueError('EXTRA_PREDICTION_IDS')
    rows, missing = [], sorted(set(requests) - set(predictions))
    for sid, request in requests.items():
        prediction = predictions.get(sid, {})
        parsed = parse_prediction(prediction)
        parsed['scoring_usable'] = gate_usable(parsed, prediction)
        if prediction.get('error'):
            parsed['label'] = None
        rows.append(dict(gold[sid], **parsed, runtime_error=prediction.get('error'), missing_prediction=sid in missing))
    grouped = {}
    for field in ('level', 'dataset', 'track', 'split', 'origin', 'dependency_type'):
        groups = collections.defaultdict(list)
        for row in rows:
            groups[str(row.get(field) or 'NOT_ANNOTATED')].append(row)
        grouped[field] = {key: metrics(items) for key,items in groups.items()}
    report = dict(status='PASS' if not missing else 'INCOMPLETE', scope=args.scope, run_id=args.run_id,
                  overall=metrics(rows), test_only=metrics([r for r in rows if r['split']=='test']), grouped=grouped,
                  input_hashes={str(path):sha(path) for path in [root/'private_gold.jsonl', *files]},
                  rubric_sha256=sha(root/'rubric.json'))
    # Diagnostics are logs, not user-facing benchmark metrics.
    diagnostic = dict(missing=missing, runtime_errors=[r['sample_id'] for r in rows if r['runtime_error']],
                      malformed=[r['sample_id'] for r in rows if not r['schema_valid']],
                      strict_json_valid=sum(r['strict_json_valid'] for r in rows), complete_schema_valid=sum(r['schema_valid'] for r in rows))
    diagnostic.update(length_truncated=[sid for sid,p in predictions.items() if p.get('finish_reason')=='length'],
                      fence_removed=[r['sample_id'] for r in rows if r['fence_removed']],
                      normalized_json_valid=sum(r['normalized_json_valid'] for r in rows),
                      prefix_recovered=[r['sample_id'] for r in rows if r['prefix_recovered']],
                      scoring_usable=sum(r['scoring_usable'] for r in rows))
    report.update(scoring_policy=POLICY_VERSION,max_new_tokens=TOKEN_LIMIT,
                  normalization_version=NORMALIZATION_VERSION,
                  truncation_rule='Score retained output; truncation alone does not invalidate an answer.')
    judge_files = sorted((root/(args.scope+'_judge')).glob('judgments_*.jsonl'))
    if judge_files:
        judgments = unique([row for path in judge_files for row in load(path)])
        extra = set(judgments)-set(requests)
        if extra:
            raise ValueError('EXTRA_JUDGE_IDS')
        if set(judgments) == set(requests):
            from judge_interface import judgment_valid,VERSION,INTERFACE_SHA256
            points = {}
            for sid, row in judgments.items():
                if row.get('judge_prompt_version')!=VERSION or row.get('judge_interface_sha256')!=INTERFACE_SHA256:raise ValueError('JUDGE_INTERFACE_VERSION_MISMATCH')
                reason = parse_prediction(predictions.get(sid, {})).get('reason') or ''
                if row['prediction_sha256'] != __import__('hashlib').sha256(json.dumps(predictions[sid], sort_keys=True).encode()).hexdigest():
                    raise ValueError('JUDGE_PREDICTION_HASH_MISMATCH')
                criteria = row['criteria']
                if set(criteria) != set(RUBRIC['criteria']):
                    raise ValueError('JUDGE_CRITERIA_MISMATCH')
                points[sid] = 100*sum(bool(v['met']) and judgment_valid(v, cid, reason) for cid,v in criteria.items())/len(criteria)
            report['judge_interface_version']=VERSION
            report['judge_interface_sha256']=INTERFACE_SHA256
            report['judge_max_new_tokens']=512
            report['evidence_max_nonwhitespace_chars']=1000
            report['explanation_rubric_score'] = sum(points.values())/len(points)
            report['test_explanation_rubric_score'] = (sum(points[r['sample_id']] for r in rows if r['split']=='test')/sum(r['split']=='test' for r in rows)) if any(r['split']=='test' for r in rows) else None
            for field, groups in grouped.items():
                for key, item in groups.items():
                    selected = [r for r in rows if str(r.get(field) or 'NOT_ANNOTATED') == key]
                    item['explanation_rubric_score'] = sum(points[r['sample_id']] for r in selected)/len(selected)
            report['judge_status'] = 'COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF'
        else:
            report['judge_status'] = 'INCOMPLETE'
            report['explanation_rubric_score'] = None
    else:
        report['judge_status'] = 'NOT_YET_SCORED'
        report['explanation_rubric_score'] = None
    gate_failed = bool(missing or diagnostic['runtime_errors'] or not rows or diagnostic['scoring_usable']/len(rows) < .95)
    report['smoke_gate_status'] = ('FAIL' if gate_failed else 'PASS') if args.gate else 'NOT_REQUESTED'
    if args.gate and gate_failed:
        report['status'] = 'SMOKE_GATE_FAILED'
    write(root/f'{args.scope}_score.json', report)
    write(root/f'{args.scope}_diagnostics.json', diagnostic)
    write(root/f'{args.scope}_scored.jsonl', rows, jsonl=True)
    lines = ['# SpaceConflict × Qwen2.5-VL-7B', '', f"Scope: {args.scope}; status: {report['status']}.",
             '', 'All-split results are diagnostics, not a held-out test-only benchmark.', '',
             '| Scope | N | Claim Accuracy | Balanced Accuracy | Macro-F1 | Pair Accuracy | Unknown F1 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    def fmt(x):
        return 'N/A' if x is None else f'{100*x:.2f}%'
    for name,m in [('All eligible inputs',report['overall']),('Test only',report['test_only']),*[(k,v) for k,v in grouped['level'].items()]]:
        lines.append(f"| {name} | {m['n']} | " + ' | '.join(fmt(m.get(k)) for k in ('claim_accuracy','balanced_accuracy','macro_f1','pair_accuracy','unknown_f1'))+' |')
    lines += ['', f"Explanation Rubric Score (Qwen3.5-4B, auxiliary, 0–100): {report['explanation_rubric_score']}", '',
              'Missing/unverified source media are listed in unavailable.jsonl; they were not replaced with blank inputs. Runtime/format failures remain in the evaluated denominator.', '']
    (root/f'{args.scope}_score.md').write_text('\n'.join(lines))
    print(json.dumps({k:report[k] for k in ('status','overall','judge_status')}), flush=True)
    if args.gate:
        if gate_failed:
            raise ValueError('SMOKE_GATE_FAILED_SEE_DIAGNOSTICS')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--scope', choices=['smoke','full'], default='full')
    p.add_argument('--gate', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--seed',type=int,default=20260904)
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    if args.dry_run:
        print('PLANNED')
    else:
        score(args)
