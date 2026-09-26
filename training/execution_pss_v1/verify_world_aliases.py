"""Read-only follow-up: verify source aliases and quantify a proposed quarantine.

Does NOT rewrite train/dev/test or create training data. No model predictions used.
"""
import argparse
import collections
import json
import os
from pathlib import Path
from audit import BASE, FROZEN, REPO, rows, sha, write

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--run-id',default='pss_20260922_alias_audit_v1')
    p.add_argument('--seed',type=int,default=20260922)
    p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a = p.parse_args()
    out = a.run_root/'alias_verification_v1'
    if a.dry_run:
        print(json.dumps({'output':str(out),'no_split_mutation':True})); return
    if not os.environ.get('SLURM_JOB_ID'): raise SystemExit('SLURM_REQUIRED')
    if (out/'ACCEPTANCE.json').exists():
        if a.resume: print((out/'ACCEPTANCE.json').read_text()); return
        raise SystemExit('REFUSE_OVERWRITE')
    if not (a.run_root/'AUDIT_COMPLETE.json').exists(): raise SystemExit('AUDIT_NOT_COMPLETE')
    gold = list(rows(FROZEN/'private_gold.jsonl'))
    # Restore missing private-evaluation metadata from exact released sample IDs,
    # not from model answers, text guessing, or a new split assignment.
    unknown_source = REPO/'l4/v3_3/release/unknown_challenge.l4_v3.jsonl'
    source_unknown = {r['sample_id']:r for r in rows(unknown_source)}
    recovered = []
    for row in gold:
        if row.get('global_world_id'): continue
        source = source_unknown.get(row['sample_id'])
        if not source or source['split'] != row['split'] or source['label'] != row['gold']:
            raise ValueError('MISSING_WORLD_NOT_SOURCE_RECOVERABLE:'+row['sample_id'])
        row['global_world_id'] = source['global_world_id']
        recovered.append({'sample_id':row['sample_id'],'global_world_id':row['global_world_id'],
            'split':row['split'],'source_path':str(unknown_source),'source_sha256':sha(unknown_source) if not recovered else recovered[0]['source_sha256'],
            'method':'EXACT_SAMPLE_ID_JOIN_SAME_SPLIT_AND_GOLD_NO_GOLD_CHANGE'})
    indexed = {r['sample_id']:r for r in gold}
    catalog_path = REPO/'data/canonical/hypo3d_l4_v2_official_referit3d_fusion_v2_6/object_catalog.v2.json'
    catalog = json.loads(catalog_path.read_text())
    scene_aliases = {}
    evidence = []
    for scene_id,scene in catalog['scenes'].items():
        official = scene.get('source_scene_id')
        if official and '/' in official:
            namespace,original = official.split('/',1)
            canonical = namespace+':'+original
            scene_aliases['hypo3d:'+scene_id] = canonical
            evidence.append({'alias':'hypo3d:'+scene_id,'source_world':canonical,
                'evidence_path':str(catalog_path),'json_pointer':'/scenes/'+scene_id+'/source_scene_id','value':official})
    world_groups = collections.defaultdict(list)
    for row in gold:
        world_groups[scene_aliases.get(row['global_world_id'],row['global_world_id'])].append(row)
    verified = []
    for world,rr in sorted(world_groups.items()):
        if len({r['split'] for r in rr}) > 1:
            verified.append({'source_world':world,'splits':sorted({r['split'] for r in rr}),
                'global_world_ids':sorted({r['global_world_id'] for r in rr}),
                'samples':[{k:r.get(k) for k in ('sample_id','global_world_id','split','level','dataset')} for r in rr]})
    # Components join source-confirmed worlds and exact media hash overlaps only.
    # This is a conservative proposed exclusion calculation, NOT a new split.
    parent = {r['global_world_id']:r['global_world_id'] for r in gold}
    def root(w):
        while parent[w] != w:
            parent[w] = parent[parent[w]]; w = parent[w]
        return w
    def union(ww):
        ww = sorted(ww)
        if not ww: return
        first = root(ww[0])
        for w in ww[1:]: parent[root(w)] = first
    for rr in world_groups.values(): union({r['global_world_id'] for r in rr})
    for media in rows(a.run_root/'audit/cross_split_media_hashes.jsonl'):
        union({indexed[s]['global_world_id'] for s in media['sample_ids']})
    groups = collections.defaultdict(list)
    for r in gold: groups[root(r['global_world_id'])].append(r)
    quarantine = []
    for rr in groups.values():
        splits = {r['split'] for r in rr}
        if 'test' in splits:
            quarantine += [dict(sample_id=r['sample_id'],split=r['split'],level=r['level'],global_world_id=r['global_world_id'],
                                reason='CONNECTED_TO_EXISTING_TEST_WORLD_OR_EXACT_MEDIA') for r in rr if r['split'] != 'test']
        elif 'dev' in splits:
            quarantine += [dict(sample_id=r['sample_id'],split=r['split'],level=r['level'],global_world_id=r['global_world_id'],
                                reason='CONNECTED_TO_EXISTING_DEV_WORLD_OR_EXACT_MEDIA') for r in rr if r['split'] == 'train']
    counts = collections.Counter((r['split'],r['level']) for r in quarantine)
    qids = {r['sample_id'] for r in quarantine}
    retained = collections.Counter((r['split'],r['level']) for r in gold if r['sample_id'] not in qids)
    suspects = list(rows(a.run_root/'audit/candidate_alias_conflicts.jsonl'))
    room_suspects = [r for r in suspects if r['candidate_alias'].startswith('possible_scannet_room:')]
    summary = {'status':'BLOCKED' if verified or qids or room_suspects else 'PASS_LIMITED_SOURCE_ALIAS_CHECK',
        'missing_world_ids_recovered_from_release':len(recovered),
        'total_inputs':len(gold),'all_split_sample_counts':dict(collections.Counter(r['split'] for r in gold)),
        'all_split_level_counts':[{'split':s,'level':l,'n':n} for (s,l),n in sorted(collections.Counter((r['split'],r['level']) for r in gold).items())],
        'source_confirmed_cross_split_worlds':len(verified),
        'source_catalog_aliases':len(scene_aliases), 'proposed_quarantine_samples':len(quarantine),
        'proposed_quarantine_by_split_level':[{'split':s,'level':l,'n':n} for (s,l),n in sorted(counts.items())],
        'proposed_remaining_by_split_level':[{'split':s,'level':l,'n':n} for (s,l),n in sorted(retained.items())],
        'unresolved_same_room_rescan_candidates':len(room_suspects),
        'proposal_applied':False,'training_submitted':False,'test_changed':False,
        'important':'Proposal is a lower-bound exclusion; unresolved physical-room aliases may require additional quarantine. No split changed.',
        'catalog':{'path':str(catalog_path),'sha256':sha(catalog_path)},
        'job_id':os.environ['SLURM_JOB_ID'],'code_sha256':sha(__file__)}
    write(out/'source_alias_evidence.jsonl',evidence,True)
    write(out/'recovered_world_metadata.jsonl',recovered,True)
    write(out/'verified_cross_split_worlds.jsonl',verified,True)
    write(out/'proposed_quarantine_NOT_APPLIED.jsonl',quarantine,True)
    write(out/'SUMMARY.json',summary)
    lines = ['# Underlying-world 别名核实（只读源数据）','',f'状态：{summary["status"]}。',
        '',f'已通过原 release 的精确 sample ID 恢复 {len(recovered)} 条缺失 world 元数据；原 private_gold 文件未修改，标签和 split 未改变。',
        f'修正统计口径后的完整输入划分：{summary["all_split_sample_counts"]}，合计 {len(gold)}。首轮 DATA_AUDIT 表格只计入了已有 world ID 的行，因此不是全量 split 样本数。',
        '',f'用实际构建使用的官方 object catalog.source_scene_id 核实别名，发现 {len(verified)} 个跨 split 的源 world。',
        f'仍有 {len(room_suspects)} 个同一 ScanNet scene 编号、不同 scan suffix 的物理房间候选需要进一步处理；未伪造全部审核通过。',
        '', '## 不改变原 test 的处置建议（尚未执行）', '',
        f'仅对已确认源 ID + 相同媒体 hash 的连通分量计算：需要从训练/开发用途隔离至少 {len(quarantine)} 条非 test 输入。',
        'test 样本不删、不挪、不改标签；原 release 仍保留所有样本。这里只生成候选清单，不训练、不自动重新划分。',
        '', '| split | level | 建议隔离 | 原 test 不变时剩余 |','|---|---|---:|---:|']
    for s,l in sorted(set(counts)|set(retained)): lines.append(f'| {s} | {l} | {counts[s,l]} | {retained[s,l]} |')
    lines += ['', '证据：verified_cross_split_worlds.jsonl；source_alias_evidence.jsonl；proposed_quarantine_NOT_APPLIED.jsonl。',
              '', '这个下界方案尚未解决所有跨 scan/跨来源别名。指南要求 split 检查 hard fail，不能以先跑起来为理由放行正式训练。']
    (out/'WORLD_ALIAS_REPORT_CN.md').write_text('\n'.join(lines)+'\n')
    write(out/'ACCEPTANCE.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__ == '__main__': main()
