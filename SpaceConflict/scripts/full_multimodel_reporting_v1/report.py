"""Add model identity and accurate report titles without editing frozen scoring."""
import argparse,ast,json,os,sys
from pathlib import Path
EXTENSION=Path(__file__).resolve().parent
ORIGINAL=EXTENSION.parent/'full_multimodel_20260908_v1'
sys.path.insert(0,str(ORIGINAL))
from campaign import ROOT,RUN_ID,SEED,registry,verify,frozen,sha

def verify_extension():
    obj=json.loads((ROOT/'reporting_extension_lock.json').read_text())
    if obj['original_protocol_sha256']!=sha(ROOT/'protocol_lock.json'):raise ValueError('ORIGINAL_PROTOCOL_CHANGED')
    for path,digest in obj['files'].items():
        if sha(path)!=digest:raise ValueError('REPORTING_EXTENSION_CHANGED:'+path)

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--model');p.add_argument('--validate-extension',action='store_true')
    p.add_argument('--run-id',default=RUN_ID);p.add_argument('--seed',type=int,default=SEED)
    p.add_argument('--resume',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--limit',type=int)
    a=p.parse_args()
    if a.run_id!=RUN_ID or a.seed!=SEED or a.limit is not None:raise ValueError('REPORT_PROTOCOL_MISMATCH')
    if a.dry_run:print('Immutable score identity/report overlay only; no new predictions.');return
    if not os.environ.get('SLURM_JOB_ID'):raise ValueError('SLURM_REQUIRED')
    verify()
    if a.validate_extension:
        evidence=[ROOT/'parser_tests_with_judge.json',ROOT/'processor_precheck_bounded_tiles.json',ROOT/'preflight.json']
        for path in evidence:
            if json.loads(path.read_text())['status']!='PASS':raise ValueError('ENGINEERING_EVIDENCE_NOT_PASS:'+str(path))
        for path in [*EXTENSION.glob('*.py'),*ORIGINAL.glob('*.py')]:ast.parse(path.read_text())
        frozen(ROOT/'reporting_extension_lock.json',dict(status='PASS',model_calls=0,original_protocol_sha256=sha(ROOT/'protocol_lock.json'),
            files={str(p):sha(p) for p in [*sorted(EXTENSION.glob('*.py')),*sorted(EXTENSION.glob('*.sh')),*evidence]},
            purpose='Correct per-model report identity without changing scientific code, input, predictions or metrics.'))
        print('FROZEN_PROTOCOL_AND_REPORT_EXTENSION_PASS',flush=True);return
    verify_extension();cfg=registry()[a.model];root=ROOT/a.model
    score=json.loads((root/'full_score.json').read_text())
    if score['run_id']!=cfg['run_id']:raise ValueError('REPORT_IDENTITY_MISMATCH')
    annotated=dict(score,model_id=cfg['model_id'],model_revision=cfg['revision'],
        active_generation=dict(do_sample=False,max_new_tokens=512,enable_thinking=cfg['enable_thinking']),
        legacy_config_fields_note='Industry generation and per-task max_new_tokens are retained provenance only; not used by this frozen SpaceConflict runner.',
        original_score_sha256=sha(root/'full_score.json'),config_sha256=sha(root/'config.json'),
        judge_model='Qwen/Qwen3.5-4B',judge_scope='Auxiliary explanation rubric only, no independent visual verification; same-family/self-judge bias.',
        reporting_extension_sha256=sha(ROOT/'reporting_extension_lock.json'))
    frozen(root/'full_score_with_identity.json',annotated)
    lines=['# SpaceConflict 完整评测：'+cfg['model_id'],'',f"状态：{score['status']}；run：{cfg['run_id']}。",'',
        '全 split 指标仅作诊断；test-only 单列。原始预测、无效输出、漏答及其分母均保留。','',
        '| 范围 | 输入数 | Claim Accuracy | Balanced Accuracy | Macro-F1 | Pair Accuracy | Unknown F1 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return 'N/A' if v is None else f'{100*v:.2f}%'
    for label,metric in [('All splits',score['overall']),('Test only',score['test_only']),*sorted(score['grouped']['level'].items())]:
        lines.append('| '+label+' | '+str(metric['n'])+' | '+' | '.join(fmt(metric.get(k)) for k in ['claim_accuracy','balanced_accuracy','macro_f1','pair_accuracy','unknown_f1'])+' |')
    lines+=['',f"解释 Rubric Score（辅助，0–100）：{score.get('explanation_rubric_score')}。",'',
        'Judge：Qwen3.5-4B；同家族与自评偏差需要披露。该分数不替代基于 gold 的准确率，不声称独立视觉验证。','',
        '本轮实际配置：greedy；总生成上限 512 token，包含 Thinking 的思考；截断后只评分已输出的最终字段。InternVL max_patches=2，其余媒体和预算见冻结协议。',
        'config.json 中从旧 Industry 模型注册表继承的 generation 和按 T1–T4 分组的 max_new_tokens 仅为来源字段，不是本轮实际 decode。不得按那些旧字段重跑本实验。','',
        '本报告与 full_score_with_identity.json 是带正确模型身份的交付。兼容评分器生成的 full_score.md 保留其旧版 7B 标题，不作为其他模型的论文汇报入口；数值未改写。','',
        '原始评分：[full_score.json](full_score.json)；完整带身份评分：[full_score_with_identity.json](full_score_with_identity.json)。','']
    dest=root/'full_report_cn.md';text='\n'.join(lines)
    if dest.exists() and dest.read_text()!=text:raise ValueError('EXISTING_REPORT_PRESERVED')
    if not dest.exists():dest.write_text(text)

if __name__=='__main__':main()
