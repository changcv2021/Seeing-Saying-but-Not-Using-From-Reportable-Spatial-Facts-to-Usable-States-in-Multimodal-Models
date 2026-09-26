"""Versioned score-only views; original inference files remain unchanged."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from common import load, unique, sha, write, parse
from output_policy import parse_prediction, NORMALIZATION_VERSION

def link_readonly_input(dest, source):
    if dest.is_symlink():
        if dest.readlink()!=source: raise ValueError('EXISTING_LINK_MISMATCH')
    elif dest.exists(): raise FileExistsError(dest)
    else: dest.symlink_to(source, target_is_directory=source.name in ('smoke','full'))

def prepare(root,cfg):
    source=Path(cfg['source_campaign']);summary={};original_hashes={}
    source_prepare=json.loads((source/'prepare_report.json').read_text())
    if source_prepare['status']!='PASS' or source_prepare['success_count']!=24196:
        raise ValueError('SOURCE_PREPARATION_NOT_VALID')
    if sha(source/'config.json')!=cfg['source_config_sha256']:raise ValueError('SOURCE_CONFIG_CHANGED')
    for key in cfg['models']:
        src=source/key;dest=root/key;dest.mkdir(parents=True,exist_ok=True)
        model_cfg=json.loads((src/'config.json').read_text())
        for name,expected in model_cfg['input_hashes'].items():
            if sha(src/name)!=expected:raise ValueError('SOURCE_INPUT_HASH_MISMATCH')
        for name in [*model_cfg['input_hashes'],'config.json','smoke','full']:
            link_readonly_input(dest/name,src/name)
        prediction_path=src/'smoke/predictions_000.jsonl'
        original_hashes[key]=sha(prediction_path)
        rows=load(prediction_path)
        if len(rows)!=96 or set(unique(rows))!=set(unique(load(src/'smoke.jsonl'))):
            raise ValueError('SMOKE_INFERENCE_NOT_COMPLETE')
        # Existing 9B judge is reusable only if every actual judge input is unchanged.
        if key=='qwen35_9b':
            if any(parse(r['raw_response'])['reason']!=parse_prediction(r)['reason'] for r in rows):
                raise ValueError('NINE_B_JUDGE_PAYLOAD_CHANGED')
            old_judgments=src/'smoke_judge/judgments_000.jsonl'
            if not old_judgments.exists():raise ValueError('NINE_B_JUDGE_MISSING')
            judgments=load(old_judgments)
            for r in judgments:
                r.update(normalization_version=NORMALIZATION_VERSION,reused_from=str(old_judgments),
                         reused_file_sha256=sha(old_judgments))
            write(dest/'smoke_judge/judgments_000.jsonl',judgments,jsonl=True)
        command=[sys.executable,str(root/'code/score.py'),'--run-root',str(dest),'--run-id',model_cfg['run_id'],'--scope','smoke','--gate','--resume','--seed',str(cfg['seed'])]
        completed=subprocess.run(command,text=True,capture_output=True)
        diag=json.loads((dest/'smoke_diagnostics.json').read_text())
        report=json.loads((dest/'smoke_score.json').read_text())
        summary[key]=dict(status=report['smoke_gate_status'],scoring_usable=diag['scoring_usable'],
            total=report['overall']['n'],fence_removed=len(diag['fence_removed']),raw_strict_json_valid=diag['strict_json_valid'],
            missing=len(diag['missing']),runtime_errors=len(diag['runtime_errors']),remaining_malformed=diag['malformed'],
            length_truncated=len(diag['length_truncated']),exit_code=completed.returncode,
            stderr=completed.stderr,command=command,source_prediction_sha256=original_hashes[key])
        if sha(prediction_path)!=original_hashes[key]:raise ValueError('RAW_PREDICTION_CHANGED')
    passed=all(v['exit_code']==0 and v['status']=='PASS' for v in summary.values())
    write(root/'repair_gate_report.json',dict(status='PASS' if passed else 'FAIL',models=summary,
        run_id=cfg['run_id'],seed=cfg['seed'],source_revision=cfg['source_config_sha256'],code_commit='NO_GIT_REPOSITORY_AVAILABLE',
        normalization_version=NORMALIZATION_VERSION,config_snapshot=cfg,config_sha256=sha(root/'config.json'),
        code_hashes={p.name:sha(p) for p in (root/'code').glob('*.py')},
        success_count=sum(v['scoring_usable'] for v in summary.values()),failure_count=sum(v['total']-v['scoring_usable'] for v in summary.values()),
        output_hashes={key:sha(root/key/'smoke_score.json') for key in cfg['models']},raw_outputs_unchanged=True))
    print(json.dumps(summary),flush=True)
    if not passed:raise ValueError('REPAIRED_GATE_FAILED')

def compare(root,cfg):
    reports={};complete=True
    lines=['# SpaceConflict Qwen3.5 — unified 512-token / outer JSON fence normalization','',
           'Same raw inference and prompt; retained-prefix scoring with whole-response fence normalization. All-split and test-only results are separate.','',
           '| Model | Scope | N | ClaimAcc | BalancedAcc | MacroF1 | PairAcc | UnknownF1 | Rubric /100 |',
           '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for key in cfg['models']:
        path=root/key/'full_score.json'
        if not path.exists():reports[key]={'status':'MISSING'};complete=False;continue
        report=json.loads(path.read_text());reports[key]=report
        if report.get('normalization_version')!=NORMALIZATION_VERSION:raise ValueError('MIXED_PARSER_VERSIONS')
        if report['status']!='PASS' or report['judge_status']!='COMPLETE_AUTOMATIC_AUXILIARY_NOT_VISUAL_PROOF':complete=False
        for scope,rubric in [('overall','explanation_rubric_score'),('test_only','test_explanation_rubric_score')]:
            m=report[scope];values=['N/A' if m[k] is None else f'{100*m[k]:.2f}%' for k in ('claim_accuracy','balanced_accuracy','macro_f1','pair_accuracy','unknown_f1')]
            lines.append(f"| {key} | {scope} | {m['n']} | "+' | '.join(values)+f" | {report.get(rubric)} |")
    write(root/'comparison.json',dict(status='COMPLETE' if complete else 'INCOMPLETE',models=reports,
        run_id=cfg['run_id'],seed=cfg['seed'],normalization_version=NORMALIZATION_VERSION,config_sha256=sha(root/'config.json'),code_sha256=sha(__file__)))
    lines+=['', 'Qwen3.5-4B rubric is auxiliary: same-family/self-judge bias remains. This is the simplified label/confidence/reason evaluation, not all structured T1–T4 tasks.']
    (root/'comparison.md').write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['prepare','compare'])
    p.add_argument('--run-root',type=Path,required=True);p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260904);p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args();cfg=json.loads((a.run_root/'config.json').read_text())
    if a.run_id!=cfg['run_id'] or a.seed!=cfg['seed'] or a.limit is not None:raise ValueError('RUN_CONFIGURATION_MISMATCH')
    if a.dry_run:print('PLANNED '+a.phase);return
    marker=a.run_root/('repair_gate_report.json' if a.phase=='prepare' else 'comparison.json')
    if marker.exists() and not a.resume:raise FileExistsError(marker)
    try:(prepare if a.phase=='prepare' else compare)(a.run_root,cfg)
    except Exception as exc:
        write(a.run_root/(a.phase+'_error.json'),dict(status='FAIL',run_id=a.run_id,seed=a.seed,error=str(exc)));raise

if __name__=='__main__':main()
