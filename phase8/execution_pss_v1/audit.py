"""Phase8 read-only source audit. Run on a Slurm compute node, before training."""
import argparse
import collections
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import socket

SPACE = Path('.')
REPO = SPACE / 'SpaceConflict'
BASE = Path('artifacts/model_results')
FROZEN = BASE / 'full_multimodel_20260908_v1'

def rows(path):
    with Path(path).open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def write(path, obj, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        if jsonl:
            for row in obj:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        else:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write('\n')

def aliases(world):
    # These are conservative candidate aliases, NOT automatically accepted remaps.
    found = re.search(r'(scene\d{4}_\d{2})', world)
    if found:
        return ['same_scannet_capture:' + found[1], 'possible_scannet_room:' + found[1].split('_')[0]]
    ident = world.split(':')[-1]
    if re.fullmatch(r'[a-f0-9]{8}-[a-f0-9-]{27}', ident):
        return ['same_scene_uuid:' + ident]
    return []

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--run-id', default='pss_20260922_v1')
    p.add_argument('--seed', type=int, default=20260922)
    p.add_argument('--limit', type=int)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.dry_run:
        print(json.dumps({'run_root': str(a.run_root), 'read_only_sources': str(FROZEN)})); return
    if not os.environ.get('SLURM_JOB_ID'):
        raise SystemExit('COMPUTE_ALLOCATION_REQUIRED')
    out = a.run_root
    if (out / 'AUDIT_COMPLETE.json').exists():
        if a.resume:
            print((out / 'AUDIT_COMPLETE.json').read_text()); return
        raise SystemExit('REFUSE_OVERWRITE')
    gold_list = list(rows(FROZEN / 'private_gold.jsonl'))
    requests_list = list(rows(FROZEN / 'requests.jsonl'))
    gold = {r['sample_id']: r for r in gold_list}
    requests = {r['sample_id']: r for r in requests_list}
    fatal = []
    if len(gold) != len(gold_list) or len(requests) != len(requests_list): fatal.append('DUPLICATE_SAMPLE_IDS')
    if gold.keys() != requests.keys(): fatal.append('REQUEST_GOLD_ID_MISMATCH')
    if a.limit: fatal.append('PARTIAL_AUDIT_NOT_TRAINING_ACCEPTANCE')
    split_worlds = collections.defaultdict(set)
    split_samples = collections.Counter()
    groups = collections.Counter()
    world_rows = collections.defaultdict(list)
    alias_rows = collections.defaultdict(list)
    for r in gold_list:
        world = r.get('global_world_id')
        if not world:
            fatal.append('MISSING_WORLD_ID'); continue
        world_rows[world].append(r)
        split_worlds[r['split']].add(world)
        split_samples[r['split']] += 1
        groups[(r['split'], r['level'])] += 1
        for candidate in aliases(world): alias_rows[candidate].append(r)
    direct_conflicts = [{'global_world_id': w, 'splits': sorted({r['split'] for r in rr}),
                         'samples': [{k: r.get(k) for k in ('sample_id', 'split', 'level', 'dataset')} for r in rr]}
                        for w, rr in sorted(world_rows.items()) if len({r['split'] for r in rr}) > 1]
    alias_conflicts = [{'candidate_alias': w, 'global_world_ids': sorted({r['global_world_id'] for r in rr}),
                        'splits': sorted({r['split'] for r in rr}), 'samples': [r['sample_id'] for r in rr],
                        'status': 'REQUIRES_SOURCE_IDENTITY_VERIFICATION_NO_REMAP_APPLIED'}
                       for w, rr in sorted(alias_rows.items())
                       if len({r['split'] for r in rr}) > 1 and len({r['global_world_id'] for r in rr}) > 1]
    if direct_conflicts: fatal.append('EXACT_WORLD_SPLIT_CONFLICT')
    if alias_conflicts: fatal.append('CROSS_SOURCE_OR_CAPTURE_ALIAS_REVIEW_REQUIRED')
    media_files = {}
    media_digest_splits = collections.defaultdict(set)
    media_digest_samples = collections.defaultdict(set)
    mismatch = []
    for r in requests_list[:a.limit]:
        g = gold.get(r['sample_id'], {})
        for key in ('split', 'level', 'component', 'pair_id'):
            if r.get(key) != g.get(key): mismatch.append({'sample_id':r['sample_id'], 'field':key, 'request':r.get(key), 'gold':g.get(key)})
        for m in r.get('media', []):
            for path in m.get('paths', []) if m.get('kind') == 'video_frames' else [m.get('path')]:
                if path:
                    media_files.setdefault(path, {'path':path, 'exists':Path(path).is_file()})
            digest = m.get('sha256')
            if digest:
                media_digest_splits[digest].add(g.get('split'))
                media_digest_samples[digest].add(r['sample_id'])
    missing_media = [m for m in media_files.values() if not m['exists']]
    media_collisions = [{'sha256':h, 'splits':sorted(s), 'sample_ids':sorted(media_digest_samples[h])}
                        for h,s in sorted(media_digest_splits.items()) if len(s) > 1]
    if missing_media: fatal.append('MEDIA_MISSING')
    if mismatch: fatal.append('REQUEST_GOLD_METADATA_MISMATCH')
    if media_collisions: fatal.append('EXACT_MEDIA_DIGEST_CROSS_SPLIT_REVIEW_REQUIRED')
    pairs_path = REPO / 'release/production_available_v10/pairs.jsonl'
    l4_path = REPO / 'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'
    source_inventory = []
    state_types = collections.Counter()
    for source in (pairs_path, l4_path):
        for row in rows(source):
            claim = row.get('supported_claim', {})
            graph = claim.get('normalized', {})
            atoms = graph.get('atoms', []) or ([claim['graph']] if claim.get('graph') else [])
            for atom in atoms: state_types[atom['predicate']] += 1
            source_inventory.append({'pair_id': row['pair_id'], 'source_path': str(source),
                'source_world_id':row.get('global_world_id') or row.get('source',{}).get('global_world_id'),
                'level':row.get('level') or row.get('task',{}).get('level'),
                'certificate_embedded':bool(row.get('certificate')), 'certificate_id':row.get('certificate_id'),
                'graph_reference':row.get('graph_reference'), 'state_atom_count':len(atoms),
                'has_pre_state': bool(row.get('pre_state')), 'has_post_state':bool(row.get('post_state')),
                'pre_state_reference':row.get('pre_state_reference'), 'post_state_reference':row.get('post_state_reference'),
                'transition_program':row.get('transition_program'), 'intervention':row.get('intervention'),
                'acceptance':row.get('validation',{}).get('final_status')})
    panels = {}
    panel_paths = {
        'B1': BASE/'sequential_state_mechanism/ssm_b1b2_20260911_v1/batches/B1/private_gold/world_panel.jsonl',
        'NONCOUNT': BASE/'sequential_state_mechanism/ssm_nextstage_v2_20260911/batches/NONCOUNT/private_gold/request_gold.jsonl'}
    for key,path in panel_paths.items():
        data = list(rows(path))
        worlds = {r['world_cluster_id'] for r in data}
        panels[key] = {'path':str(path), 'sha256':sha(path), 'records':len(data), 'worlds':len(worlds),
            'original_split_overlap':{s: len(worlds & ww) for s,ww in split_worlds.items()},
            'worlds_not_in_full_benchmark':sorted(worlds - set(world_rows)),
            'history_use':'Previously used diagnostics; not newly untouched test',
            'eligibility':'NOT_FROZEN_PENDING_WORLD_SPLIT_AUDIT'}
    env = {}
    for package in ('torch','transformers','peft','accelerate','trl','datasets','bitsandbytes'):
        try: env[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: env[package] = None
    model_cfg = FROZEN/'qwen35_9b/config.json'
    cfg = json.loads(model_cfg.read_text())
    model_path = Path(cfg['model_path'])
    model_files = {'path':str(model_path), 'exists':model_path.is_dir(), 'revision':cfg['revision'],
                   'files':[{ 'name':f.name,'bytes':f.stat().st_size} for f in sorted(model_path.glob('*')) if f.is_file()]}
    required = [FROZEN/'requests.jsonl', FROZEN/'private_gold.jsonl', FROZEN/'rubric.json', model_cfg,
                pairs_path,l4_path, SPACE/'phase8/sft.md',SPACE/'phase8/CoT_SFT_Addendum_CN.md',Path(__file__)]
    hashes = [{'path':str(f),'sha256':sha(f),'bytes':f.stat().st_size} for f in required]
    split_audit = {'status':'FAIL' if fatal else 'PASS', 'fatal':sorted(set(fatal)),
        'samples':dict(split_samples), 'worlds':{s:len(w) for s,w in split_worlds.items()},
        'groups':[{'split':s,'level':l,'samples':n} for (s,l),n in sorted(groups.items())],
        'exact_world_conflicts':len(direct_conflicts), 'candidate_alias_conflicts':len(alias_conflicts),
        'cross_split_media_hashes':len(media_collisions), 'missing_media':len(missing_media),
        'request_gold_mismatches':len(mismatch), 'no_original_splits_modified':True,
        'partial':bool(a.limit), 'all_worlds':len(world_rows)}
    write(out/'SPLIT_AUDIT.json',split_audit)
    for filename,data in [('exact_world_conflicts',direct_conflicts),('candidate_alias_conflicts',alias_conflicts),
                          ('cross_split_media_hashes',media_collisions),('missing_media',missing_media),
                          ('request_gold_mismatches',mismatch),('source_inventory',source_inventory)]:
        write(out/'audit'/f'{filename}.jsonl', data, jsonl=True)
    write(out/'audit/panel_inventory.json',panels)
    write(out/'audit/source_hashes.json',hashes)
    write(out/'audit/environment.json',{'packages':env,'model':model_files,'host':socket.gethostname(),
                                      'job_id':os.environ.get('SLURM_JOB_ID')})
    write(out/'audit/state_types.json',dict(state_types))
    lines = ['# Phase8 数据与训练前置审计', '', f'状态：{split_audit["status"]}。作业 {os.environ.get("SLURM_JOB_ID")}。',
        '', '本报告在编写训练代码之前生成。所有 release、gold、旧预测只读；未开始训练或最终 test。',
        '', '## A–C：原始划分与 underlying world', '',
        '| split | inputs | declared worlds |','|---|---:|---:|']
    lines += [f'| {s} | {n} | {len(split_worlds[s])} |' for s,n in sorted(split_samples.items())]
    lines += ['',f'完全相同 world ID 跨 split：{len(direct_conflicts)}；别名/同场景候选：{len(alias_conflicts)}；跨 split 相同媒体摘要：{len(media_collisions)}。',
              '媒体摘要相同需检查，不自动等价于同一个物理 world；相同 scene/capture ID 候选也不自动重划 split。',
              '',f'阻塞项：{", ".join(sorted(set(fatal))) or "无"}。',
              '逐样本证据：audit/exact_world_conflicts.jsonl、candidate_alias_conflicts.jsonl、cross_split_media_hashes.jsonl。',
              '', '## D–E：问题、媒体、gold 与监督证据', '',
              f'public requests/private gold：{len(requests_list)}/{len(gold_list)}；唯一媒体文件路径 {len(media_files)}；缺文件 {len(missing_media)}。',
              f'源 pair 记录 {len(source_inventory)}。见 audit/source_inventory.jsonl；实际 predicate 分布见 audit/state_types.json。',
              'L1–L3 有 normalized atoms、graph_reference、certificate_id；引用不等于已完成证书重放。',
              'L4 有 certificate、pre/post references、intervention；引用不等于每条已具备 S0/S1/S2 两步链。',
              '监督生成尚未批准：须先解析源图与证书、验证可见证据与状态及 deterministic replay。禁止从最终标签或模型答案反推状态。',
              '', '## F–H：工程与评分器', '',
              f'9B checkpoint：{model_path}；revision：{cfg["revision"]}。本地目录存在：{model_path.is_dir()}。',
              f'包元数据：{json.dumps(env,ensure_ascii=False)}。尚未做训练/forward/backward 验证。',
              '现有原始 protocol.py、output_policy.py、common.metrics 可复用；无已验收的本项目 Phase8 SFT pipeline/LoRA config。',
              '评测保持 non-thinking / greedy / 512 output tokens / 原始媒体预算；每级 ClaimAcc 与 PairAcc。',
              'confidence 不是 gold 概率；answer-stream loss masking 与 rationale 来源需统一冻结后再训练。',
              '', '## I：历史诊断 panel', '']
    for key,v in panels.items(): lines.append(f'- {key}：{v["records"]} 记录 / {v["worlds"]} worlds；原 split 重叠 {v["original_split_overlap"]}。源 {v["path"]}。')
    lines += ['', '这些 panel 已用于历史机制开发，不能标成新未曝光 test。必须剔除训练泄漏后才可作独立诊断；原 panel 不改动。',
              '', '## 配置决策与启动门槛', '',
              '计划五种方案 × seeds [20260922, 20260923]，主模型 Qwen3.5-9B；仅工程 smoke 可用小子集。',
              '拟定 Answer-SFT 原始级别比例；MultiTask-Answer-SFT 均衡 L1–L4；CoT/PSS 与后者共享原始答案池。尚待用户偏好及审计完成后冻结。',
              '硬门：world split PASS → 可靠监督构造 → state schema/训练/保存加载/评分 smoke → dev-only 选参 → 冻结 → 十次训练与完整 test。',
              '若 split 失败，不提交正式训练；不私自重划 test、不假报已开始。先核实别名证据并提供无 test 改动的处置建议。',
              'LoRA/optimizer/token budget/GPU 显存尚未实测，不填虚假“已冻结”参数。']
    (out/'DATA_AUDIT.md').write_text('\n'.join(lines)+'\n')
    status = {'status':'AUDIT_COMPLETED', 'training_gate':split_audit['status'], 'fatal':sorted(set(fatal)),
              'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'run_id':a.run_id,'seed':a.seed,
              'job_id':os.environ.get('SLURM_JOB_ID'),'data_audit_sha256':sha(out/'DATA_AUDIT.md')}
    write(out/'AUDIT_COMPLETE.json', status)
    print(json.dumps(status,sort_keys=True),flush=True)

if __name__ == '__main__': main()
