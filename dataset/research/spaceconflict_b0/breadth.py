"""Read-only release breadth and existing prediction availability, never inference."""
from collections import defaultdict,Counter
from b0common import *


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('Metadata/availability inventory only; no historical rescoring, no model generation'); return
    compute(); project=Path(c['project']); hist=Path(c['historical']); campaign=Path(c['campaign'])
    # Run after source-only selection to make outcome-independent selection auditable.
    if not (root/'manifest/source_inventory.json').exists(): raise ValueError('SOURCE_SELECTION_MUST_PRECEDE_BREADTH_PREDICTION_METADATA')
    sys.path.insert(0,str(project/'research/state_binding_phase_a_v2/src'))
    from base import resolved_gold
    metadata=resolved_gold(hist,project)
    annotation_path=project/'l4/v3_3/derived_annotations/track_annotations_v1/track_annotations.l4_v3_3.v1.jsonl'
    annotations={r['pair_id']:r for r in rows(annotation_path)} if annotation_path.exists() else {}
    cells=defaultdict(list)
    for sid,g in metadata.items():
        label=g['gold'].get('label') if isinstance(g['gold'],dict) else g['gold']
        track=g.get('track'); origin='EXISTING_EVALUATION_METADATA'
        if not track or track in ['Not annotated in released pair','Not annotated','UNKNOWN_TRACK']:
            ann=annotations.get(g.get('pair_id'))
            if ann: track=ann['primary_track']; origin='EXISTING_DERIVED_TRACK_ANNOTATION_V1'
            else: track='Not annotated in released pair'; origin='MISSING_NO_GUESS'
        key=(g['level'],track,g['split'],label,origin)
        cells[key].append(dict(sample_id=sid,pair_id=g.get('pair_id'),world=cluster(g['global_world_id']),component=g['component']))
    specifications=[(k,campaign/k) for k in c['models']]+[('qwen25vl_7b_historical',hist)]
    records=[]; filesnapshot=[]; rejects=[]
    for model,directory in specifications:
        files=sorted(set(p for pattern in ['predictions*.jsonl','full/predictions*.jsonl','shards/predictions*.jsonl','predictions/*.jsonl','inference/predictions*.jsonl'] for p in directory.glob(pattern)))
        present=set(); errors=set(); labels=set(); duplicates=Counter()
        for path in files:
            size=path.stat().st_size; seenbytes=0; digest_obj=hashlib.sha256()
            with path.open('rb') as f:
                for lineno,line in enumerate(f,1):
                    if seenbytes+len(line)>size: break
                    seenbytes+=len(line); digest_obj.update(line)
                    if not line.strip(): continue
                    try: pred=json.loads(line)
                    except ValueError:
                        rejects.append(dict(path=str(path),line=lineno,reason='MALFORMED_OR_PARTIAL_JSON_AT_SNAPSHOT')); continue
                    sid=pred.get('sample_id')
                    if sid not in metadata:
                        rejects.append(dict(path=str(path),line=lineno,reason='UNKNOWN_SAMPLE_ID')); continue
                    duplicates[sid]+=1; present.add(sid)
                    if pred.get('error') or pred.get('infrastructure_error'): errors.add(sid)
                    value=pred.get('prediction')
                    if isinstance(value,dict) and value.get('label') in ['SUPPORTED','CONTRADICTORY','UNKNOWN']: labels.add(sid)
            filesnapshot.append(dict(model=model,path=str(path),snapshot_bytes=size,bytes_read=seenbytes,sha256_read_prefix=digest_obj.hexdigest(),
                                     appended_later_bytes_not_included=True,read_at_utc=now()))
        metrics=sorted(set(str(p) for pattern in ['metrics*.json','reports/*metrics*.json','final/*metrics*.json','evaluation/*.json'] for p in directory.glob(pattern)))
        for key,rs in cells.items():
            ids={r['sample_id'] for r in rs}; count=len(ids&present)
            missing=[]
            if count<len(ids): missing.append('PREDICTIONS_PARTIAL' if count else 'NO_MATCHED_PREDICTIONS_FOUND')
            missing.append('LEVEL_TRACK_MODEL_LABEL_METRICS_NOT_VERIFIED_NO_RESCORING_IN_B0')
            records.append(dict(model=model,level=key[0],track=key[1],split=key[2],label_type=key[3],track_origin=key[4],
                world_count=len({r['world'] for r in rs}),pair_count=len({r['pair_id'] for r in rs if r['pair_id']}),
                claim_count=len(ids),unknown_count=len(ids) if key[3]=='UNKNOWN' else 0,
                existing_prediction_count=count,existing_parsed_label_count=len(ids&labels),existing_error_count=len(ids&errors),
                duplicate_prediction_ids=sum(duplicates[sid]>1 for sid in ids),missing_prediction_count=len(ids-present),
                prediction_availability='COMPLETE' if count==len(ids) else 'PARTIAL' if count else 'NOT_FOUND_IN_SCANNED_LAYOUT',
                existing_metrics_artifact_paths=metrics,existing_cell_metrics_status='NOT_VERIFIED',missing_evaluation_cells=missing,
                snapshot_scope='EXISTING_FULL_RELEASE_METADATA_ONLY_NOT_B0_BEHAVIORAL_COHORT'))
    union_csv(root/'benchmark_breadth_inventory.csv',records)
    union_csv(root/'reports/breadth_read_rejections.csv',rejects)
    save(root/'manifest/breadth_snapshot.json',dict(status='READ_ONLY_SNAPSHOT_NO_INFERENCE',generated_at_utc=now(),
        source_gold=entry(hist/'private_gold.jsonl'),track_annotation=entry(annotation_path) if annotation_path.exists() else None,
        source_claims=len(metadata),unique_worlds=len({cluster(g['global_world_id']) for g in metadata.values()}),
        files=filesnapshot,model_outcomes_used_for_b0_selection=False,historical_scores_modified=False,
        caution='Currently running campaigns can append after this snapshot; NOT_FOUND does not establish absence in unscanned historical layouts.'))
    plan='''# Benchmark breadth 分析准备（非 B0 机制统计）

统计框架：Level × Track × Model × Label Type，分别报告 train/dev/test 元数据单元；本轮不新增 test 或全量推理，也不重评分历史结果。

主表 benchmark_breadth_inventory.csv 的 pair_count 是每个标签单元中的唯一 pair ID 数；不能跨 SUPPORTED/CONTRADICTORY 行直接相加。UNKNOWN count 是标签 UNKNOWN 的 claim 数，不是 pair 数。world 使用与 Phase A 相同的明确场景别名合并规则。Track 优先沿用当前评测元数据；缺失时只引用既有 derived annotation v1，不按 operator 新猜。

建议下一次获准的 breadth 分析：Claim Accuracy、Binary Claim Accuracy、Pair Accuracy、CONTRADICTORY Recall、UNKNOWN Recall、world-macro；同一完成且可匹配的样本上分析 persistent-error across scales、repaired-by-scale、model-specific error。分母同时给出覆盖率，INVALID 纳入对应已执行准确率分母；缺预测不当作回答错误。世界聚类置信区间，跨模型用配对同 world。

本轮只核查现有预测 sample ID、已解析 label 的可用性和错误字段，不计算准确率。existing_cell_metrics_status=NOT_VERIFIED 不等于历史没有任何指标，只表示没有在本轮证明已有文件精确覆盖该交叉单元。read snapshot 的字节数和 hash 见 manifest/breadth_snapshot.json；其他既有作业仍可能继续写入。找不到匹配布局时保留 NOT_FOUND_IN_SCANNED_LAYOUT，不伪造零覆盖的全局结论。

禁止将 B0 的有限 L4 count dev/exploration 样本外推为整个 SpaceConflict；不为补齐本表自动启动新模型、完整 release 推理或 test 实验。
'''
    save(root/'benchmark_breadth_analysis_plan.md',plan,'text')
    print(json.dumps(dict(status='BREADTH_METADATA_SNAPSHOT_COMPLETE',cells=len(records),claims=len(metadata),files=len(filesnapshot),new_model_calls=0)))


if __name__=='__main__': main()
