"""Diagnose camera identity without changing benchmark records."""
import argparse
import io
import json
import pickle
import tarfile
import zipfile
from pathlib import Path
import numpy as np

p = argparse.ArgumentParser()
p.add_argument('--dry-run', action='store_true')
p.add_argument('--resume', action='store_true')
p.add_argument('--seed', type=int, default=20260905)
p.add_argument('--run-id', default='frame_identity_20260905')
p.add_argument('--limit', type=int, default=3)
a = p.parse_args()
if a.dry_run:
    print('Inspect local camera metadata, no writes.')
    raise SystemExit()
root = Path('artifacts/upstream_media/spar7m_raw')
with tarfile.open(root/'scannetpp/archives/00a231a370.tar.gz', 'r|gz') as t:
    for m in t:
        if m.name.endswith('.npz'):
            with np.load(io.BytesIO(t.extractfile(m).read()), allow_pickle=False) as data:
                for k in data.files:
                    print('NPZ', k, data[k].shape, data[k].dtype, str(data[k])[:1200], flush=True)
path = Path('external/upstream/data/full_media_incoming/hypo3d/official/embodiedscan_v1/annotations/embodiedscan_infos_train.pkl')
with path.open('rb') as f:
    data = pickle.load(f)
print('EMBODIED_KEYS', data.keys(), flush=True)
scenes = [d for d in data['data_list'] if d['sample_idx'] in ('scannet/scene0051_00', 'scannet/scene0051_02', 'scannet/scene0073_01')]
with zipfile.ZipFile(root/'scannet/archives/scannet-frames.zip') as z:
    for scene in scenes:
        print('SCENE', scene['sample_idx'], scene.keys(), flush=True)
        print('FIRST_IMAGE', scene['images'][0], flush=True)
        scene_id = scene['sample_idx'].split('/')[-1]
        members = sorted(n for n in z.namelist() if n.startswith(f'scannet-frames/{scene_id}/') and n.endswith('.txt'))
        refs = np.array([r['cam2global'] for r in scene['images']])
        for name in members[:a.limit]:
            matrix = np.loadtxt(io.BytesIO(z.read(name)))
            errors = np.max(np.abs(refs - matrix), axis=(1,2))
            idx = int(np.argmin(errors))
            print('POSE_MATCH', name, scene['images'][idx]['img_path'], float(errors[idx]), flush=True)
