"""Expand exact accessible source requirements; never use withheld evidence."""
import argparse
import collections
import json
import shutil
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
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if a.dry_run:
        print('PLANNED: exact visible-media inventory, local manifests only')
        return
    a.output.mkdir(parents=True,exist_ok=True)
    inputs={}
    def read(path):
        inputs[str(path)]=sha(path)
        return load(path)
    index=a.project/'data/media_index/spar/0fe664cbada1e7c1173fd743e0f781882eebf777/qualitative_relation_media.v2.jsonl'
    manifests={r['media_id']:r for r in read(index)}
    by_locator=collections.defaultdict(set)
    for name,component in [('claims.jsonl','binary'),('unknown_challenge.jsonl','unknown')]:
        for row in read(a.bundle/'benchmark/l1_l3/release'/name):
            refs=row['media'].get('source_references') or []
            if refs and str(locator(refs[0])).startswith('spar/'):
                for item in view_plan(row,component,manifests):
                    by_locator[item['locator']].add(row['sample_id'])
    records=[dict(locator=key,base_dataset=key.split('/')[1],scene_id=key.split('/')[3],
                  sample_ids=sorted(value),withheld_evidence=False) for key,value in sorted(by_locator.items())]
    if a.limit: records=records[:a.limit]
    write(a.output/'required_accessible.jsonl',records,jsonl=True)
    # Extraction accepts a separate withheld manifest; no withheld-only media is requested.
    write(a.output/'withheld_not_requested.jsonl',[],jsonl=True)
    acq=a.bundle/'upstream_media/spar7m_acquisition'
    old=acq/'alternative_sources/validation/structured3d/full_extract_report.json'
    inputs[str(old)]=sha(old)
    if not (a.output/'structured3d_report.json').exists():
        shutil.copyfile(old,a.output/'structured3d_report.json')
    completed=json.loads(old.read_text())['completed']
    existing={r['locator'] for r in completed if not r['withheld']}
    missing=[r for r in records if r['base_dataset']=='structured3d' and r['locator'] not in existing]
    report=dict(run_id=a.run_id,seed=a.seed,status='PLAN_READY',
                requested_unique_by_base=dict(collections.Counter(r['base_dataset'] for r in records)),
                structured3d_not_in_old_accessible_map=len(missing),
                structured3d_affected_inputs=len({s for r in missing for s in r['sample_ids']}),
                input_hashes=inputs,code_sha256=sha(__file__),
                output_hashes={str(a.output/n):sha(a.output/n) for n in ['required_accessible.jsonl','withheld_not_requested.jsonl']})
    write(a.output/'plan.json',report)
    print(json.dumps(report),flush=True)

if __name__=='__main__': main()
