"""Read-only inspection of local source archives on a compute node."""
import argparse
import collections
import json
import tarfile
import zipfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--dry-run', action='store_true')
p.add_argument('--resume', action='store_true')
p.add_argument('--seed', type=int, default=20260905)
p.add_argument('--run-id', default='media_inspect_20260905')
p.add_argument('--limit', type=int, default=12)
a = p.parse_args()
if a.dry_run:
    print('Inspect SPAR metadata archives and mirror archive metadata; no writes.')
    raise SystemExit()
source = Path('external/upstream/data/full_media_incoming/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/SPAR-7M')
base = Path('artifacts/upstream_media')
for dataset in ('scannet', 'scannetpp'):
    counts = collections.Counter()
    examples = collections.defaultdict(list)
    with tarfile.open(source/f'{dataset}.tar.gz', 'r|gz') as archive:
        for member in archive:
            if not member.isfile():
                continue
            parts = member.name.split('/')
            category = '/'.join(parts[:2])
            counts[category] += 1
            if len(examples[category]) < 2:
                examples[category].append(dict(name=member.name, bytes=member.size,
                    text=archive.extractfile(member).read(1200).decode(errors='replace') if member.size < 20000 else 'large'))
    print(json.dumps(dict(dataset=dataset, counts=counts, examples=examples)), flush=True)
with zipfile.ZipFile(base/'spar7m_raw/scannet/archives/scannet-frames.zip') as z:
    names = z.namelist()
    special = [n for n in names if not n.endswith(('.jpg', '.png', '.txt', '/'))]
    print('SCANNET_SPECIAL', special[:a.limit], flush=True)
    for n in [n for n in names if n.endswith('.txt')][:3]:
        print(n, z.read(n)[:1200], flush=True)
with tarfile.open(base/'spar7m_raw/scannetpp/archives/00a231a370.tar.gz', 'r|gz') as t:
    for m in t:
        if m.isfile() and not m.name.endswith(('.png', '.jpg', '.jpeg')):
            print('SCANNETPP_METADATA', m.name, m.size, t.extractfile(m).read(2500), flush=True)
