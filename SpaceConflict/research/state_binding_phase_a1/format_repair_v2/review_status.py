"""Post-review status only; no claims of human verification or mechanism completion."""
import csv
import time
from collections import Counter
from common import arguments,load,rows,sha,save,require_compute
from pathlib import Path

def main():
    a=arguments(__doc__).parse_args(); cfg=load(a.config); root=Path(cfg['root'])
    assert (a.run_id,a.seed)==(cfg['run_id'],cfg['seed'])
    if a.limit is not None: raise ValueError('NO_POSTHOC_SUBSET')
    if a.dry_run: print('PLANNED: review status, no model inference'); return
    require_compute()
    if any((root/'raw/core').glob('*/*.json')): raise ValueError('CORE_RESULTS_REQUIRE_FULL_ANALYSIS')
    panel_path=root/'review/candidate_panel.jsonl'
    panel=list(rows(panel_path)) if panel_path.exists() else []
    p=root/'review/processor_acceptance.json'
    actual=load(p) if p.exists() else {'status':'NOT_RUN'}
    reviews=[]
    if (root/'derived_input_review.csv').exists():
        with (root/'derived_input_review.csv').open(newline='') as f: reviews=list(csv.DictReader(f))
    ready=actual['status']=='PASS'
    state='FORMAT_FIXED_REVIEW_PACKAGE_READY_MAIN_A1_PENDING_REVIEW' if ready else 'FORMAT_FIXED_REVIEW_PREPARATION_INCOMPLETE'
    before=list(rows(root/'manifest/source_a1_files_before.jsonl'))
    changes=[e['path'] for e in before if not Path(e['path']).is_file() or sha(e['path'])!=e['sha256']]
    if changes: raise ValueError('SOURCE_A1_CHANGED:'+repr(changes[:3]))
    save(root/'reports/post_review_preservation.json',dict(status='PASS',files=len(before),changed_files=[]))
    outcome=dict(status=state,format_gate=load(root/'reports/setup_calibration_acceptance.json')['status'],
        candidate_worlds=len(panel),strata=dict(Counter(x['stratum'] for x in panel)),
        review_states=dict(Counter(x['review_status'] for x in reviews)),actual_processor=actual,
        new_model_predictions=0,core_responses=0,human_review_completed=False,verified_worlds=0,
        core_inference_authorized=False,complete=False)
    save(root/'reports/review_status.json',outcome)
    save(root/'LIVE_STATUS.json',outcome)
    report=(root/'format_repair_report_cn.md').read_text()
    report+='\n## 派生输入复核进度\n\n'
    report+=f"状态：{state}。固定候选 {len(panel)} world；分层 {json_repr(outcome['strata'])}。\n\n"
    report+=f"实际 processor 复核：{actual['status']}；页面 [review package](review/review_package/index.html)。\n\n"
    report+='呈现 hash 仅包含图像/网格张量，mm_token_type_ids 等文本辅助张量单列，不把文字长度混作图像差异。'
    report+='未据此伪造人工 VERIFIED。真实机制推理仍为 0；后续须冻结实际复核面板和匹配该呈现规范的 runner。\n'
    save(root/'phase_a1_report_cn.md',report,'text')
    print(json_repr(outcome))
def json_repr(x):
    import json
    return json.dumps(x,ensure_ascii=False)
if __name__=='__main__': main()
