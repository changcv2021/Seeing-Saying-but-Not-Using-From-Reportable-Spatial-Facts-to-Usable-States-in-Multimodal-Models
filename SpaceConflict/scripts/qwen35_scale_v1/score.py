"""Reuse exact frozen metrics; add candidate identity without changing scoring."""
import argparse
import json
from pathlib import Path
from common import load, sha, write
import base_score

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-root',type=Path,required=True); p.add_argument('--run-id',required=True)
    p.add_argument('--scope',choices=['smoke','full'],default='full'); p.add_argument('--gate',action='store_true')
    p.add_argument('--dry-run',action='store_true'); p.add_argument('--resume',action='store_true')
    p.add_argument('--seed',type=int,default=20260904); p.add_argument('--limit',type=int)
    a=p.parse_args(); cfg=json.loads((a.run_root/'config.json').read_text())
    if a.dry_run: print('PLANNED'); return
    if a.limit is not None: raise ValueError('SCORING_MUST_NOT_DROP_INPUTS')
    request_name='smoke.jsonl' if a.scope=='smoke' else 'requests.jsonl'
    for name in (request_name,'private_gold.jsonl','rubric.json'):
        if sha(a.run_root/name)!=cfg['input_hashes'][name]: raise ValueError('SCORING_INPUT_HASH_MISMATCH')
    for path in (a.run_root/a.scope).glob('predictions_*.jsonl'):
        for row in load(path):
            if (row['model_id'],row['model_revision'],row['run_id'],row['requested_samples_sha256']) != (
                    cfg['candidate']['model_id'],cfg['candidate']['revision'],a.run_id,cfg['input_hashes'][request_name]):
                raise ValueError('CROSS_MODEL_OR_INPUT_PREDICTION')
    base_score.score(a)
    report_path=a.run_root/f'{a.scope}_score.json'
    report=json.loads(report_path.read_text()); report.update(model_id=cfg['candidate']['model_id'],
        model_revision=cfg['candidate']['revision'],judge_model=cfg['judge'],decode=cfg['decode'],
        same_family_judge_caution='Auxiliary only; 4B self-judge and same-family/style bias possible',
        config_sha256=sha(a.run_root/'config.json'))
    write(report_path,report)
    md=a.run_root/f'{a.scope}_score.md'
    md.write_text(md.read_text().replace('# SpaceConflict × Qwen2.5-VL-7B','# SpaceConflict × '+cfg['candidate']['model_id'])+
        '\nQwen3.5 direct / non-thinking, greedy, 256 output tokens. Same-family 4B judge is auxiliary, not ground truth.\n')

if __name__=='__main__': main()
