"""Rebuild diagnostic views and audit v2-to-v3 changes without new inference."""
import importlib.util
from collections import defaultdict
from common_auto_v2 import *
from e0_snapshot import interval
from real_processor_v1 import verify


def table(path):
    with Path(path).open() as f:return list(csv.DictReader(f))


def main():
    a=arguments(__doc__).parse_args();c,root=setup(a);base=root/'rescoring/interface_v3_20260910'
    lock=load(base/'NORMALIZATION_LOCK.json');verify(lock['code']+lock['protected_prior_files'])
    reports=[];index=[];remaining=[]
    for case in lock['cases']:
        for model in c['models']:
            pp=list((base/case/model).glob('snapshot_*/RESCORE_ACCEPTANCE.json'))
            if len(pp)!=1:raise ValueError('AMBIGUOUS_OR_MISSING_V3_SNAPSHOT')
            path=pp[0];report=load(path);dest=path.parent
            if report['status']!='COMPLETE':raise ValueError('RESCORE_INCOMPLETE')
            iface=load(dest/'V2_TO_V3_ACCEPTANCE.json')
            if case in ('D01','E7','E9'):oldbase=root/'rescoring/interface_v2_20260910'/case/model
            else:
                batch=(f'ca_source_d{int(case[1:]):02}_20260910' if case.startswith('D') else
                       {'E8':'native_e8_breadth_v1_20260910','NONCOUNT':'noncount_breadth_v1_20260910','MULTIVIEW':'multiview_breadth_v2_20260910'}[case])
                oldbase=root/'rescoring'/('data_continuation_interface_v2' if case.startswith('D') else 'breadth_interface_v2')/batch/batch/model
            prior=sorted(oldbase.glob('snapshot_*/RESCORE_ACCEPTANCE.json'),key=lambda p:int(p.parent.name.split('_')[-1]))[-1]
            name='per_request_diagnostics.csv' if case=='E7' else 'all_request_scores.csv' if case=='E9' else 'all_physical_request_scores.csv'
            col='correct' if case in ('E7','E9') else 'content_correct'
            old={r['request_id']:r for r in table(prior.parent/'normalized'/name)}
            new={r['request_id']:r for r in table(dest/'normalized'/name)}
            assert set(old)==set(new)
            ww=defaultdict(list);deltas=[]
            for rid,r in new.items():
                before=old[rid][col]=='True';after=r[col]=='True';w=r['world_cluster_id']
                ww[w].append(int(after)-int(before))
                if before and not after:raise ValueError('V3_DESTROYED_PREVIOUSLY_CORRECT_CONTENT')
                deltas.append(dict(request_id=rid,world_cluster_id=w,v2_correct=before,v3_correct=after,
                                   v2_schema=old[rid]['schema_status'],v3_schema=r['schema_status']))
            clustered=[(w,sum(v)/len(v),1) for w,v in ww.items()];lo,hi=interval(clustered,c['seed'],5000)
            row=dict(case=case,model=model,returned=report['returned'],worlds=report['worlds'],v2_invalid=iface['v2_invalid'],v3_invalid=iface['v3_invalid'],
                     v2_correct=sum(r[col]=='True' for r in old.values()),v3_correct=sum(r[col]=='True' for r in new.values()),
                     world_macro_accuracy_delta=sum(v[1] for v in clustered)/len(clustered),delta_ci95=[lo,hi],
                     score_ref=entry(path),v2_score_ref=entry(prior),gold_blind_audit=report['normalizer_gold_access_audit'])
            reports.append(row);csvsave(dest/'v2_to_v3_content_changes.csv',deltas)
            for v in rows(dest/'canonical_views.jsonl'):
                if v['status']=='RETURNED' and v['normalization']['normalized']['status']=='INVALID':
                    obj=v['normalization']['normalized'].get('parsed') or {};facts=obj.get('facts',[]) if isinstance(obj,dict) else []
                    negative=any(type(f.get('value')) is int and f['value']<0 or isinstance(f.get('value'),str) and __import__('re').fullmatch(r'-[1-9][0-9]*',f['value']) for f in facts if isinstance(f,dict))
                    remaining.append(dict(case=case,model=model,request_id=v['request_id'],world_cluster_id=v['world_cluster_id'],
                        raw_response=v['raw_response'],original_raw=v['original_raw'],
                        diagnosis='NEGATIVE_COUNT_CONTENT_ERROR_INCLUDING_STRING_SERIALIZATION' if negative else 'UNRESOLVED',
                        altered_answer=False))
            if case in ('E8','MULTIVIEW'):
                filename='analysis.py' if case=='E8' else 'analysis_mv.py'
                spec=importlib.util.spec_from_file_location('sws_v3_diag_'+case,CODE/'breadth_v1'/filename)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                module.analyze(c,root,batch,model,dest)
            index.append(dict(case=case,model=model,normalized=str(dest/'normalized'),strict=str(dest/'strict_replay'),
                              canonical=entry(dest/'canonical_views.jsonl'),acceptance=entry(path)))
    csvsave(base/'V2_TO_V3_RESULTS.csv',reports);csvsave(base/'REMAINING_CONTENT_ERRORS.csv',remaining)
    save(base/'ACTIVE_SCORING_INDEX.json',dict(version=lock['version'],status='COMPLETE',cases=index,
        original_predictions_preserved=True,original_E7_parent_exposures_preserved=True,
        normalized_is_posthoc_content_measure=True,raw_strict_compliance_separate=True))
    verify(lock['code']+lock['protected_prior_files'])
    text='# SWS 接口 v3：重评分结果与边界\n\n'
    text+=f'已完成 {len(reports)} 个批次×模型评分单元，共 {sum(r["returned"] for r in reports):,} 条原始响应重评分。v2 不合规 {sum(r["v2_invalid"] for r in reports)} 条 → v3 {sum(r["v3_invalid"] for r in reports)} 条。\n\n'
    text+='修复完全相同的 count 数字字符串以及单值 schema 的裸 null；保留所有值、顺序、gold、原始输出、旧分数和 E7 自生成父报告。它是事后测量修正，不是模型能力提升。\n\n'
    text+='| 批次 | 模型 | 响应/world | 不合规 v2→v3 | 正确数 v2→v3 | world-macro 准确率差及 95% CI |\n|---|---|---:|---:|---:|---|\n'
    for r in reports:
        if r['v2_invalid'] or r['v3_invalid'] or r['v2_correct']!=r['v3_correct']:
            text+=f'| {r["case"]} | {r["model"]} | {r["returned"]}/{r["worlds"]} | {r["v2_invalid"]}→{r["v3_invalid"]} | {r["v2_correct"]}→{r["v3_correct"]} | {r["world_macro_accuracy_delta"]:.4f}; {r["delta_ci95"]} |\n'
    text+='\n其余单元内容成绩未改变。CI 为固定 seed、5,000 次底层 world 配对 bootstrap；小样本 discovery、AUTO_ONLY_PROVISIONAL，不作为确认性结论。不同实验不得合并成一个 benchmark 准确率。\n\n'
    text+=f'剩余 {len(remaining)} 条全部按原样保留，详细文字与 SHA256 见 REMAINING_CONTENT_ERRORS.csv。负计数（包括字符串 "-1"）属于内容/合法状态域问题，不能改为 0 或 null，也不能据此直接判断唯一失败机制。\n\n'
    text+='E8 与多视图逐 world 诊断已基于 v3 重建。非计数 E2/E6 本次所有内容和分组成绩与 v2 相同，原非计数矩阵仍可作为等价诊断；新评分入口统一为 ACTIVE_SCORING_INDEX.json。\n\n'
    text+='证据文件：V2_TO_V3_RESULTS.csv、REMAINING_CONTENT_ERRORS.csv、各 snapshot 的 canonical_views.jsonl、strict_replay、normalized、v2_to_v3_content_changes.csv。\n'
    save(base/'interface_v3_report_cn.md',text,'text')
    print(json.dumps(dict(status='COMPLETE',units=len(reports),responses=sum(r['returned'] for r in reports),
                         previous_invalid=sum(r['v2_invalid'] for r in reports),remaining_invalid=len(remaining),report=str(base/'interface_v3_report_cn.md'))),flush=True)


if __name__=='__main__':main()
