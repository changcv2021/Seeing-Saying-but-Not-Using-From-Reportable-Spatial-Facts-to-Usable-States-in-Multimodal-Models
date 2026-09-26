"""Lightweight full-release plan audit, before image reads and model evaluation."""
import argparse
import collections
from pathlib import Path
from common import load, sha, write
from spar_media import locator, view_plan

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260905)
    p.add_argument('--limit',type=int)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args()
    if a.dry_run:
        print('PLANNED: source view and bbox metadata audit, no image reads')
        return
    inputs={}
    def read(path):
        inputs[str(path)]=sha(path)
        return load(path)
    index=a.project/'data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl'
    manifests={r['media_id']:r for r in read(index)}
    import json
    release=a.bundle/'benchmark/l1_l3/release'
    release_manifest=json.loads((release/'manifest.json').read_text())
    candidates={}
    for rel,expected in release_manifest['input_hashes'].items():
        if rel.startswith('candidates/unknown/'):
            path=a.project/rel
            rows=read(path)
            if inputs[str(path)]!=expected.removeprefix('sha256:'):
                raise ValueError('UNKNOWN_SOURCE_HASH_MISMATCH')
            candidates.update({r['unknown_id']:r for r in rows})
    counts=collections.Counter(); errors=[]; views=set(); changes=collections.Counter()
    for file,component in [('claims.jsonl','binary'),('unknown_challenge.jsonl','unknown')]:
        for row in read(release/file):
            refs=row['media'].get('source_references') or []
            if not refs or not str(locator(refs[0])).startswith('spar/'):
                continue
            try:
                planned=view_plan(row,component,manifests,candidates.get(row['sample_id']))
                for item in planned:
                    views.add(item['locator'])
                counts[(component,locator(refs[0]).split('/')[1])]+=1
                if len(planned)>len(refs): changes['binary_expanded_inputs']+=1
                if any(item['boxes'] for item in planned): changes['inputs_with_visible_source_boxes']+=1
            except (ValueError,KeyError,IndexError,TypeError) as e:
                errors.append(dict(sample_id=row['sample_id'],error=repr(e)))
    report=dict(status='PASS' if not errors else 'FAIL',run_id=a.run_id,seed=a.seed,
                counts={':'.join(k):v for k,v in counts.items()},changes=dict(changes),
                required_unique_views_by_dataset=dict(collections.Counter(x.split('/')[1] for x in views)),
                errors=errors,input_hashes=inputs,code_sha256=sha(__file__))
    write(a.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='input_hashes'}),flush=True)
    if errors: raise ValueError('FULL_RELEASE_SPAR_VIEW_PLAN_AUDIT_FAILED')

if __name__=='__main__': main()
