"""Candidate-specific provenance around the unchanged exact metric implementation."""
import argparse
import json
from pathlib import Path
from common import load, sha, write
from output_policy import POLICY_VERSION, TOKEN_LIMIT, NORMALIZATION_VERSION
import base_score

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--scope',choices=['smoke','full'],default='full');p.add_argument('--gate',action='store_true')
    p.add_argument('--seed',type=int,default=20260904);p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true')
    a=p.parse_args();cfg=json.loads((a.run_root/'config.json').read_text());cfg_hash=sha(a.run_root/'config.json')
    if (a.run_id,a.seed)!=(cfg['run_id'],cfg['seed']):raise ValueError('SCORE_CONFIG_MISMATCH')
    if cfg['scoring_policy']!=POLICY_VERSION or cfg['decode']['max_new_tokens']!=TOKEN_LIMIT:
        raise ValueError('SCORE_OUTPUT_POLICY_MISMATCH')
    if a.limit is not None:raise ValueError('SCORING_MUST_NOT_DROP_INPUTS')
    if a.dry_run:print('PLANNED');return
    req='smoke.jsonl' if a.scope=='smoke' else 'requests.jsonl'
    for name in (req,'private_gold.jsonl','rubric.json'):
        if sha(a.run_root/name)!=cfg['input_hashes'][name]:raise ValueError('SCORING_INPUT_CHANGED')
    for path in (a.run_root/a.scope).glob('predictions_*.jsonl'):
        for row in load(path):
            if not row.get('error') and (row.get('scoring_policy')!=POLICY_VERSION or row.get('max_new_tokens')!=TOKEN_LIMIT):
                raise ValueError('PREDICTION_OUTPUT_POLICY_MISMATCH')
            if (row['model_id'],row['model_revision'],row['config_sha256'],row['requested_samples_sha256'],row['run_id']) != (
                    cfg['model'],cfg['revision'],cfg_hash,cfg['input_hashes'][req],a.run_id):
                raise ValueError('CROSS_MODEL_OR_INPUT_PREDICTION')
    try:
        base_score.score(a)
    finally:
        path=a.run_root/f'{a.scope}_score.json'
        if path.exists():
            report=json.loads(path.read_text())
            report.update(model=cfg['model'],model_revision=cfg['revision'],judge_bias_note=cfg['judge_bias_note'],
                          normalization_version=NORMALIZATION_VERSION,
                          prompt_version=cfg['prompt_version'],protocol_change_note=cfg['protocol_change_note'],
                          config_sha256=cfg_hash,score_code_sha256=sha(__file__),base_score_sha256=sha(Path(base_score.__file__)))
            write(path,report)
        md=a.run_root/f'{a.scope}_score.md'
        if md.exists():
            md.write_text(md.read_text().replace('# SpaceConflict × Qwen2.5-VL-7B','# SpaceConflict × '+cfg['model']))
            with md.open('a') as stream:
                stream.write('\n\nParser normalization: '+NORMALIZATION_VERSION+'. Whole-response JSON fences are removed for scoring only; raw model output is unchanged.\n')
                stream.write('\n\nProtocol: '+cfg['prompt_version']+'. '+cfg['protocol_change_note']+'\n')

if __name__=='__main__':main()
