"""Reuse the unexecuted v1 IO/parser utilities; no gold is loaded on import."""
import sys
from pathlib import Path
CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE.parent/'spatial_conflict_diagnosis_v1/src'))
from diaglib import *

def stable_rank(seed, value): return digest([seed, value])

def cluster(world):
    # Only explicit scene naming equivalences; never visual or category similarity.
    if world.startswith('hypo3d:'):
        scene = world.split(':', 1)[1]
        if scene.startswith('scene'): return 'scannet:' + scene
        if len(scene) == 36 and scene.count('-') == 4: return '3rscan:' + scene
    return world

def resolved_gold(hist, project):
    """Restore absent world metadata from exact frozen IDs, never from predictions."""
    pair_world = {}
    for p in rows(project/'release/production_available_v10/pairs.jsonl'):
        pair_world[p['pair_id']] = p['source']['global_world_id']
    for p in rows(project/'l4/v3_3/release/pairs.l4_three_part_v3.jsonl'):
        pair_world[p['pair_id']] = p['global_world_id']
    unknown_world = {u['sample_id']:u['global_world_id'] for u in rows(project/'l4/v3_3/release/unknown_challenge.l4_v3.jsonl')}
    gg = unique(rows(hist/'private_gold.jsonl'), 'sample_id')
    for sid, g in gg.items():
        world = pair_world.get(g.get('pair_id')) or unknown_world.get(sid)
        if g.get('global_world_id') and world and g['global_world_id'] != world: raise ValueError('FROZEN_WORLD_DISAGREEMENT:'+sid)
        if not g.get('global_world_id'):
            if not world: raise ValueError('WORLD_NOT_RESOLVABLE_FROM_FROZEN_IDS:'+sid)
            g = dict(g, global_world_id=world, diagnostic_world_metadata_origin='EXACT_FROZEN_ID_JOIN')
            gg[sid] = g
    return gg

def frozen_write(path, obj, kind='json'):
    path = Path(path)
    if path.exists():
        existing = list(rows(path)) if kind == 'jsonl' else path.read_text() if kind == 'text' else load(path)
        if existing != obj: raise ValueError('FROZEN_OUTPUT_DIFFERS:' + str(path))
        return
    write(path, obj, kind)

def evidence_entry(path):
    path = Path(path)
    return dict(path=str(path), available=path.is_file(), bytes=path.stat().st_size if path.is_file() else None,
                sha256=sha(path) if path.is_file() else None)
