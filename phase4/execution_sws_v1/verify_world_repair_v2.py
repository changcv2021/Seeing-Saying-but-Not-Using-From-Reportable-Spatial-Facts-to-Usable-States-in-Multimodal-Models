"""End-to-end acceptance for the isolated world-identity repair, not SWS completion."""
from collections import Counter, defaultdict
from common import *
from world_identity_v2 import checked_overlay, repair_root
from snapshot_store_v2 import frozen_predictions

def main():
    a = arguments(__doc__).parse_args(); c, original_root = setup(a)
    if a.dry_run:
        print('Verify recovered identities, protected history, snapshot metrics and regression fixtures'); return
    metadata, identity = checked_overlay(c, original_root)
    root = repair_root(original_root)
    inventory = load(root / 'inventory/reports/source_inventory.json')
    e0 = load(root / 'e0/reports/E0_snapshot_acceptance.json')
    protected = identity['immutable_inputs'] + identity['protected_historical_files'] + identity['code_files']
    mismatches = [r['path'] for r in protected if sha(r['path']) != r['sha256']]
    if mismatches: raise ValueError('PROTECTED_FILE_CHANGED:' + repr(mismatches))
    assert inventory['model_prediction_files_read'] == 0
    assert inventory['release_label_or_claim_fields_used'] == 0
    assert inventory['source_graphs_from_test_opened'] == 0
    assert inventory['source_graphs_from_old_confirmation_opened'] == 0
    assert e0['new_model_calls'] == 0
    scored = list(rows(root / 'e0/scores/E0_existing_snapshot.jsonl'))
    index = list(rows(root / 'e0/manifest/E0_raw_index.jsonl'))
    assert len(scored) == len(index)
    assert len({(r['model_id'], r['sample_id']) for r in scored}) == len(scored)
    raw_by_key = {}
    for ref in e0['snapshots']:
        assert sha(ref['snapshot_path']) == ref['snapshot_sha256']
        for r in rows(ref['snapshot_path']):
            key = (ref['model_id'], r['sample_id'])
            assert key not in raw_by_key
            raw_by_key[key] = digest(r)
    for r in index: assert raw_by_key[(r['model_id'], r['request_id'])] == r['raw_record_sha256']
    counts = Counter(); correct = Counter(); worlds = defaultdict(set); recovered = Counter()
    for r in scored:
        meta = metadata[r['sample_id']]
        assert r['world_cluster_id'] == meta['world_cluster_id']
        assert r['correct'] == (r['label'] == r['gold'])
        counts[r['model_id']] += 1; correct[r['model_id']] += r['correct']; worlds[r['model_id']].add(r['world_cluster_id'])
        recovered[r['model_id']] += meta['resolution'] == 'EXACT_RELEASE_SAMPLE_ID'
    with (root / 'e0/tables/E0_primary_statistics_snapshot.csv').open() as f: statistics = list(csv.DictReader(f))
    for r in statistics:
        if r['ci95_low']: assert 0 <= float(r['ci95_low']) <= float(r['ci95_high']) <= 1
        if r['dimension'] == 'OVERALL' and r['metric'] == 'ClaimAcc':
            assert int(float(r['denominator'])) == counts[r['model_id']]
            assert int(float(r['numerator'])) == correct[r['model_id']]
    with (root / 'inventory/tables/E0_release_breadth.csv').open() as f: breadth = list(csv.DictReader(f))
    assert sum(int(r['claims']) for r in breadth) == len(metadata)
    # Compile source without bytecode or touching any frozen file.
    for name in ('world_identity_v2.py', 'inventory_v2.py', 'e0_snapshot_v2.py', 'snapshot_store_v2.py'):
        compile((CODE / name).read_text(), str(CODE / name), 'exec')
    # Resume regression: an incomplete final line is retained separately; later source appends
    # must not change the finite set or the raw bytes used for E0 statistics.
    fixture = root / 'verification_fixture' / os.environ['SLURM_JOB_ID']
    path = fixture / 'source/model/full/predictions_0.jsonl'
    save(path, '{"sample_id":"fixture_1"}\n{"unfinished":', 'text')
    first = frozen_predictions(fixture / 'output', fixture / 'source', ['model'])
    with path.open('a') as f: f.write('true}\n')
    second = frozen_predictions(fixture / 'output', fixture / 'source', ['model'])
    assert first == second and first['files'][0]['incomplete_tail_bytes'] > 0
    assert len(list(rows(first['files'][0]['snapshot_path']))) == 1
    files = [entry(p) for d in ('inventory', 'e0') for p in sorted((root / d).rglob('*')) if p.is_file()]
    report = dict(status='PASS_WORLD_IDENTITY_REPAIR_NOT_FULL_SWS_COMPLETION', created_at=now(), job_id=os.environ['SLURM_JOB_ID'],
                  identity_job_id=identity['job_id'], inventory_job_id=inventory['job_id'], e0_job_id=e0['job_id'],
                  baseline_records=len(metadata), recovered_records=identity['recovered_records'],
                  recovered_world_clusters=identity['recovered_world_clusters'], unresolved_records=identity['unresolved_records'],
                  identity_regression_tests=identity['regression_tests_passed'], protected_files_verified=len(protected),
                  historical_mismatches=mismatches, raw_response_index_closure=len(index),
                  returned_by_model=dict(counts), recovered_rows_scored_by_model=dict(recovered),
                  planned_per_model=len(metadata), world_counts_by_model={k:len(v) for k,v in worlds.items()},
                  source_candidate_worlds=inventory['candidate_worlds'],
                  verified_real_SWS_worlds=inventory['real_worlds_verified_for_sws'],
                  new_GPU_calls=0, output_files=files, verification_code=entry(__file__),
                  no_input_gold_or_prompt_changes=True, snapshot_resume_and_incomplete_tail_test='PASS')
    save(root / 'REPAIR_ACCEPTANCE.json', report)
    text = f'''# SWS world ID 修复与验收

状态：PASS（本次两个 CPU 失败已修复，不代表完整 SWS 研究完成）。

根因：旧打包器 `SpaceConflict/scripts/full_eval_v1/prepare.py:278` 通过 pair_id 查 pair，再读取 pair.global_world_id。UNKNOWN 本来没有 pair_id，因此查到空字典，写出 null；`full_multimodel_20260908_v1/campaign.py:109` 按 hash 复制该历史元数据。原始 v3_3 release 的 UNKNOWN 记录按 sample_id 有完整 world ID。旧 cluster(None) 导致来源盘点和 E0 统计退出。不是源图像缺失，也没有修改 UNKNOWN 的真值。

- 全部输入：{len(metadata):,}；恢复：{identity['recovered_records']} 条、{identity['recovered_world_clusters']} 个底层 world；无法恢复：{identity['unresolved_records']}。
- 恢复依据：相同 sample_id，核对 scene / branch / split / level；源文件 SHA-256 与 datasets.yaml、release manifest 一致。没有猜测 ID，没有读取预测来筛选 world。
- 历史保护：{len(protected)} 个冻结文件核对无变化；原 release、gold、题面、旧快照和已完成 E9/M0 验收未覆盖。
- 作业：身份核查 {identity['job_id']}，来源盘点 {inventory['job_id']}，E0 重算 {e0['job_id']}，最终验收 {os.environ['SLURM_JOB_ID']}。

## E0 是已有预测的时间截点快照

返回数：{dict(counts)}（每模型计划 {len(metadata):,}）。恢复 ID 后纳入评分的 UNKNOWN 数：{dict(recovered)}。

只重算已有回答，没有重新调用 GPU。三模型快照按相同 sample_id 的交集作 scale 比较；尚未返回的回答不记错。沿用既定 512-token 前缀解析，按 world / source family 聚类、5000 次 bootstrap 的 CI；评分输出不足或不合规仍保留，不按分数重试。不是新 SWS 机制结果，也不是完整最终 benchmark 成绩。

## 输出位置

- `identity_acceptance.json`、`recovered_world_ids.jsonl`：逐条恢复依据和验收。
- `inventory/reports/source_inventory.json`、`inventory/manifest/world_candidate_inventory.jsonl`：来源盘点。
- `e0/tables/E0_primary_statistics_snapshot.csv`：准确率、分组结果和 CI。
- `e0/tables/E0_prediction_coverage_snapshot.csv`：实际返回覆盖率。
- `e0/manifest/E0_raw_index.jsonl`、`e0/raw/E0_existing_snapshot/SNAPSHOT_LOCK.json`：原始响应索引及固定快照。
- `REPAIR_ACCEPTANCE.json`：端到端检查、输出 hash 与作业记录。

下一步：来源资格盘点已恢复；新真实 E1–E8 输入仍须独立编译、媒体/派生问题审核及冻结。当前真实 SWS VERIFIED 数为 {inventory['real_worlds_verified_for_sws']}，不能用此次元数据修复冒充人工审核或新实验完成。
'''
    save(root / 'REPAIR_REPORT_CN.md', text, 'text')
    print(json.dumps({k:v for k,v in report.items() if k not in ('output_files', 'verification_code')}, ensure_ascii=False), flush=True)

if __name__ == '__main__': main()
