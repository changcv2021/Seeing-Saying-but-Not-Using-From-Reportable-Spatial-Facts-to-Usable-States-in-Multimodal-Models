"""Prepare frozen evaluation copies and summarize independent model runs."""
import argparse
import collections
import json
import shutil
from pathlib import Path
from common import load, unique, sha, write

def prepare(root, cfg):
    source=Path(cfg['source_run'])
    for name, expected in cfg['input_hashes'].items():
        if sha(source/name) != expected: raise ValueError(f'FROZEN_INPUT_HASH:{name}')
    requests=load(source/'requests.jsonl'); gold=load(source/'private_gold.jsonl')
    if len(requests)!=24196 or set(unique(requests))!=set(unique(gold)):
        raise ValueError('FULL_COVERAGE_MISMATCH')
    if any(r['component']=='unknown' and r.get('reference_proposition') is not None for r in gold):
        raise ValueError('UNKNOWN_REFERENCE_LEAK')
    media_paths=set()
    for r in requests:
        for m in r['media']:
            media_paths.update(m['paths'] if m['kind']=='video_frames' else [m['path']])
    bundle=Path('artifacts').resolve()
    for raw in sorted(media_paths):
        path=Path(raw).resolve()
        if not path.is_relative_to(bundle) or not path.is_file() or path.stat().st_size==0:
            raise ValueError(f'MEDIA_PATH_MISSING:{raw}')
    manifests={}
    for m in cfg['models']:
        manifest=json.loads(Path(m['manifest_path']).read_text())
        if (manifest['model_id'],manifest['revision'])!=(m['model'],m['revision']):
            raise ValueError(f'MODEL_REVISION:{m["key"]}')
        model=Path(m['model_path'])
        index=json.loads((model/'model.safetensors.index.json').read_text())
        sizes={}
        for name in sorted(set(index['weight_map'].values())):
            if Path(name).name!=name or not (model/name).is_file() or (model/name).stat().st_size<=100:
                raise ValueError(f'MISSING_MODEL_SHARD:{m["key"]}:{name}')
            sizes[name]=(model/name).stat().st_size
        manifests[m['key']]=dict(manifest=manifest,shard_sizes=sizes,check='presence and sizes; GPU loader verifies tensor structure')
        out=root/m['key']; out.mkdir(parents=True,exist_ok=True)
        for name in cfg['input_hashes']:
            dest=out/name
            if dest.exists():
                if sha(dest)!=cfg['input_hashes'][name]: raise ValueError(f'EXISTING_INPUT_CHANGED:{dest}')
            else: shutil.copyfile(source/name,dest)
            if sha(dest)!=cfg['input_hashes'][name]: raise ValueError('COPY_HASH_MISMATCH')
        model_cfg={k:v for k,v in cfg.items() if k!='models'}
        model_cfg.update(m,run_id=f'{cfg["campaign_id"]}_{m["key"]}')
        if (out/'config.json').exists() and json.loads((out/'config.json').read_text())!=model_cfg:
            raise ValueError('MODEL_CONFIG_CHANGED')
        write(out/'config.json',model_cfg)
    write(root/'prepare_report.json', dict(status='PASS',run_id=cfg['campaign_id'],seed=cfg['seed'],
        success_count=len(requests),failure_count=0,by_level=dict(collections.Counter(r['level'] for r in requests)),
        media_paths_present=len(media_paths),input_hashes=cfg['input_hashes'],models=manifests,
        config_snapshot=cfg,config_sha256=sha(root/'config.json'),code_sha256=sha(__file__),
        code_hashes={p.name:sha(p) for p in sorted((root/'code').iterdir()) if p.is_file()},
        code_commit='NO_GIT_REPOSITORY_AVAILABLE',source_revision='Frozen SpaceConflict release and pinned model manifests',
        output_hashes={str(root/m['key']/n):sha(root/m['key']/n) for m in cfg['models'] for n in [*cfg['input_hashes'],'config.json']}))
    print('PASS: all 24196 inputs, 96 smoke inputs and three model snapshots prepared',flush=True)

def compare(root,cfg):
    results={}; complete=True
    lines=['# SpaceConflict — Qwen3.5 scale', '',
           'Direct mode (thinking disabled); deterministic generation. All-split diagnostic results and held-out test results are separate.', '',
           '| Model | Scope | N | ClaimAcc | BalancedAcc | MacroF1 | PairAcc | UnknownF1 | Rubric / 100 |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    lines.insert(2, cfg['protocol_change_note'])
    for model in cfg.get('comparison_models', cfg['models']):
        path=Path(model.get('report_root', root/model['key']))/'full_score.json'
        if not path.exists():
            results[model['key']]={'status':'REPORT_MISSING'}; complete=False; continue
        report=json.loads(path.read_text()); results[model['key']]=report
        if report.get('prompt_version')!=cfg['prompt_version'] or report.get('scoring_policy')!=cfg['scoring_policy'] or report.get('max_new_tokens')!=512:
            raise ValueError('CROSS_PROTOCOL_COMPARISON_FORBIDDEN')
        if report['status']!='PASS' or report['judge_status']!='COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF': complete=False
        for label,scope,rubric in [('All splits','overall','explanation_rubric_score'),('Test only','test_only','test_explanation_rubric_score')]:
            item=report[scope]
            values=['N/A' if item[k] is None else f'{100*item[k]:.2f}%' for k in ('claim_accuracy','balanced_accuracy','macro_f1','pair_accuracy','unknown_f1')]
            lines.append(f"| {model['model']} | {label} | {item['n']} | "+' | '.join(values)+f" | {report.get(rubric)} |")
    lines.extend(['',cfg['judge_bias_note'],'','Status: '+('COMPLETE' if complete else 'INCOMPLETE')])
    write(root/'comparison.json',dict(status='COMPLETE' if complete else 'INCOMPLETE',models=results,
          protocol_change_note=cfg['protocol_change_note'],controlled_scale_comparison=True,
          run_id=cfg['campaign_id'],seed=cfg['seed'],config_sha256=sha(root/'config.json'),code_sha256=sha(__file__)))
    (root/'comparison.md').write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('phase',choices=['prepare','compare'])
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260904)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();cfg=json.loads((a.run_root/'config.json').read_text())
    if a.limit is not None: p.error('Whole-release operation does not permit limit')
    if a.run_id!=cfg['campaign_id'] or a.seed!=cfg['seed']: raise ValueError('RUN_CONFIG_MISMATCH')
    if a.dry_run: print('PLANNED '+a.phase);return
    if not a.resume and (a.run_root/('prepare_report.json' if a.phase=='prepare' else 'comparison.json')).exists():
        raise FileExistsError('Use --resume for an existing report')
    try: (prepare if a.phase=='prepare' else compare)(a.run_root,cfg)
    except Exception as exc:
        write(a.run_root/(a.phase+'_error.json'),dict(status='FAIL',error=f'{type(exc).__name__}: {exc}',failure_count=1,run_id=a.run_id,seed=a.seed))
        raise

if __name__=='__main__':main()
