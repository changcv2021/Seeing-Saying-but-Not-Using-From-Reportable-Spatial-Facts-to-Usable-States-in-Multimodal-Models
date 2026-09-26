"""Quantify, but do not apply, physical-world exclusion with fixed test membership."""
import argparse
import collections
import json
import os
from pathlib import Path
import re
from audit import FROZEN, rows, sha, write

SCANNET_SOURCE = 'https://github.com/ScanNet/ScanNet/blob/master/README.md#data-organization'

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--run-id',default='pss_20260922_physical_impact_v1')
    p.add_argument('--seed',type=int,default=20260922)
    p.add_argument('--limit',type=int)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true')
    a=p.parse_args(); out=a.run_root/'physical_world_impact_v1'
    if a.dry_run: print(str(out)); return
    if not os.environ.get('SLURM_JOB_ID'): raise SystemExit('SLURM_REQUIRED')
    if (out/'SUMMARY.json').exists():
        if a.resume: print((out/'SUMMARY.json').read_text()); return
        raise SystemExit('REFUSE_OVERWRITE')
    if a.limit: raise SystemExit('IMPACT_REQUIRES_FULL_INPUTS')
    prev=a.run_root/'alias_verification_v1'
    aliases={r['alias']:r['source_world'] for r in rows(prev/'source_alias_evidence.jsonl')}
    recover={r['sample_id']:r for r in rows(prev/'recovered_world_metadata.jsonl')}
    gold=list(rows(FROZEN/'private_gold.jsonl'))
    for r in gold:
        if not r.get('global_world_id'): r['global_world_id']=recover[r['sample_id']]['global_world_id']
    indexed={r['sample_id']:r for r in gold}
    group=collections.defaultdict(list); mappings=[]
    for w in sorted({r['global_world_id'] for r in gold}):
        source=aliases.get(w,w)
        m=re.fullmatch(r'scannet:(scene\d{4})_\d{2}',source)
        physical='scannet_space:'+m[1] if m else source
        mappings.append({'global_world_id':w,'source_world':source,'physical_group':physical,
                         'scannet_rule_source':SCANNET_SOURCE if m else None})
        group[physical].append(w)
    parent={r['global_world_id']:r['global_world_id'] for r in gold}
    def root(w):
        while parent[w]!=w: parent[w]=parent[parent[w]]; w=parent[w]
        return w
    def union(ww):
        ww=sorted(ww)
        if not ww: return
        first=root(ww[0])
        for w in ww[1:]: parent[root(w)]=first
    for ww in group.values(): union(ww)
    physical_rows=collections.defaultdict(list)
    for r in gold: physical_rows[root(r['global_world_id'])].append(r)
    physical_conflicts=[{'physical_component':w,'worlds':sorted({r['global_world_id'] for r in rr}),
                         'splits':sorted({r['split'] for r in rr}),'sample_ids':[r['sample_id'] for r in rr]}
                        for w,rr in physical_rows.items() if len({r['split'] for r in rr})>1]
    # Normalize textual hash prefix; digest equality is recorded, not blindly
    # interpreted as room identity. Conservative exclusion may over-remove shared backgrounds.
    digests=collections.defaultdict(set); digest_paths=collections.defaultdict(set)
    for r in rows(FROZEN/'requests.jsonl'):
        for media in r.get('media',[]):
            h=media.get('sha256')
            if h:
                h=h.removeprefix('sha256:')
                digests[h].add(indexed[r['sample_id']]['global_world_id'])
                if media.get('path'): digest_paths[h].add(media['path'])
    hashed_conflicts=[]
    world_splits=collections.defaultdict(set)
    for r in gold: world_splits[r['global_world_id']].add(r['split'])
    for h,ww in digests.items():
        splits=set().union(*(world_splits[w] for w in ww))
        if len(splits)>1:
            paths=sorted(digest_paths[h])
            actual=[{'path':x,'sha256':sha(x),'matches':sha(x)==h} for x in paths]
            if not all(r['matches'] for r in actual): raise ValueError('CROSS_SPLIT_MEDIA_HASH_CHANGED:'+h)
            hashed_conflicts.append({'digest':h,'worlds':sorted(ww),'splits':sorted(splits),'verified_files':actual})
        union(ww)
    components=collections.defaultdict(list)
    for r in gold: components[root(r['global_world_id'])].append(r)
    proposed=[]
    for key,rr in components.items():
        splits={r['split'] for r in rr}
        for r in rr:
            reject=('test' in splits and r['split']!='test') or ('test' not in splits and 'dev' in splits and r['split']=='train')
            if reject: proposed.append({'sample_id':r['sample_id'],'split':r['split'],'level':r['level'],'global_world_id':r['global_world_id'],
                                         'component':key,'reason':'CONSERVATIVE_PHYSICAL_WORLD_OR_SHARED_MEDIA_EXCLUSION','applied':False})
    ids={r['sample_id'] for r in proposed}
    removed=collections.Counter(r['split'] for r in proposed)
    kept=collections.Counter(r['split'] for r in gold if r['sample_id'] not in ids)
    bylevel=collections.Counter((r['split'],r['level']) for r in gold if r['sample_id'] not in ids)
    summary={'status':'BLOCKED_REQUIRES_TRAINING_POOL_DECISION','proposal_applied':False,'test_changed':False,
        'official_scannet_id_rule_source':SCANNET_SOURCE,
        'source_or_physical_cross_split_components_before_media':len(physical_conflicts),
        'verified_normalized_cross_split_media_hashes':len(hashed_conflicts),
        'proposed_exclusions':dict(removed),'proposed_remaining':dict(kept),
        'proposed_remaining_by_level':[{'split':s,'level':l,'n':n} for (s,l),n in sorted(bylevel.items())],
        'limitations':['Other dataset physical aliases not claimed exhaustively solved',
                      'Shared images are conservative exclusion edges, not proof that all their worlds have identical geometry',
                      'No existing diagnostic panel has original test worlds; separate eligible held-out diagnostics needed'],
        'job_id':os.environ['SLURM_JOB_ID'],'code_sha256':sha(__file__)}
    write(out/'WORLD_GROUPS.jsonl',mappings,True)
    write(out/'SOURCE_PHYSICAL_CONFLICTS.jsonl',physical_conflicts,True)
    write(out/'VERIFIED_CROSS_SPLIT_MEDIA.jsonl',hashed_conflicts,True)
    write(out/'EXCLUSION_PROPOSAL_NOT_APPLIED.jsonl',proposed,True)
    write(out/'SUMMARY.json',summary)
    lines=['# Phase8 训练前置结果与待决策项','',
        '本轮完成实际 CPU 审计；尚未训练、没有训练后分数。原始数据、gold、预测未改动。',
        '', '## 已完成','',
        '- 24,196 条 requests/gold 精确对齐，21,228 个唯一媒体文件路径全部存在。',
        '- 根据原 release 精确 sample ID 恢复 300 条 L4 UNKNOWN 的 world 元数据，未改标签或 split。',
        '- 全部原始 split：train 15,122；dev 3,466；test 5,608。',
        '- 五种方案按用户最新定义记录，CoT 为 rationale + answer target replacement。',
        '', '## 训练阻塞：不是缺数据，而是 world 隔离不足','',
        '构建目录源 catalog 证实 Hypo3D 与 SPAR 等会共享 ScanNet 原始场景，但其 global_world_id 前缀不同。',
        f'ScanNet 的 spaceId 是物理地点，scanId 是该地点的扫描编号；不能把不同扫描自动当成独立 world。[官方命名定义]({SCANNET_SOURCE})。',
        f'按源 ID 与 physical-space 规则发现 {len(physical_conflicts)} 个跨 split 组件；实际复算确认 {len(hashed_conflicts)} 个跨 split 媒体摘要。',
        '', '## 建议（未执行，需要确定训练池政策）','',
        f'保持原 test 全部 5,608 条不变。只为 Phase8 建立非破坏性排除清单：train 隔离 {removed["train"]} 条，dev 隔离 {removed["dev"]} 条；',
        f'对应剩余 train {kept["train"]}、dev {kept["dev"]}、test {kept["test"]}。所有训练方案使用同一处理后的样本池。',
        '上述数字是当前已核实 source-ID / ScanNet space / exact-media 规则下的方案，不声称其他来源的所有物理别名已排查完。',
        '没有重新分配 split，没有删除源样本。完整逐样本候选见 EXCLUSION_PROPOSAL_NOT_APPLIED.jsonl。',
        '', '## 历史诊断与后续评测','',
        'B1 的 80 worlds：68 train + 12 dev；non-count 的 47 worlds：43 train + 4 dev。均无原 test world。',
        '不能把历史全 panel 重跑称为训练后的 held-out 诊断。需要从合格 held-out worlds 的源事实和冻结程序准备独立诊断，或将原 dev 子集明确标成开发诊断。',
        '', '## 未完成','',
        '训练池冲突处置、state/CoT 监督全覆盖与重放、PEFT 训练环境、资源 smoke、token 匹配、十次正式训练、dev checkpoint 选择、最终 test 与 CI。',
        '指南明确 split 审计 hard fail；当前不提交会泄漏的训练。处理训练池政策后再继续，而不是把作业提交当作完成。']
    (out/'EXECUTION_REPORT_CN.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
