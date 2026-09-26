"""Freeze validated shared input files and three separate model run configs."""
import argparse
import collections
import json
import os
import shutil
from pathlib import Path
from common import sha, load, unique, write
from source_preflight import EXPECTED, model_presence

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--campaign',type=Path,required=True); p.add_argument('--run-id',required=True)
    p.add_argument('--seed',type=int,default=20260904); p.add_argument('--dry-run',action='store_true')
    p.add_argument('--resume',action='store_true'); p.add_argument('--limit',type=int)
    a=p.parse_args(); cfg=json.loads((a.campaign/'config.json').read_text())
    if a.dry_run: print(json.dumps(dict(status='PLANNED',inputs=24196,models=3))); return
    if a.limit is not None or cfg['run_id']!=a.run_id or cfg['seed']!=a.seed: raise ValueError('CONFIG_OR_SCOPE_MISMATCH')
    source=Path(cfg['baseline_run']); shared=a.campaign/'shared'; shared.mkdir(exist_ok=True)
    report=dict(run_id=a.run_id,seed=a.seed,job_id=os.getenv('SLURM_JOB_ID'),code_commit='NO_GIT_REPOSITORY_AVAILABLE',code_sha256=sha(__file__))
    try:
        for name, expected in EXPECTED.items():
            if sha(source/name)!=expected: raise ValueError(f'SOURCE_HASH_CHANGED:{name}')
            target=shared/name
            if not target.exists(): shutil.copyfile(source/name,target)
            if sha(target)!=expected: raise ValueError(f'SNAPSHOT_HASH_MISMATCH:{name}')
        requests=unique(load(shared/'requests.jsonl')); gold=unique(load(shared/'private_gold.jsonl'))
        smoke=unique(load(shared/'smoke.jsonl'))
        if len(requests)!=24196 or set(requests)!=set(gold) or len(smoke)!=96: raise ValueError('INPUT_COVERAGE_MISMATCH')
        if any(requests.get(k)!=v for k,v in smoke.items()): raise ValueError('SMOKE_NOT_EXACT_SUBSET')
        paths=set(); kinds=collections.Counter()
        for req in requests.values():
            if req['component']=='unknown' and gold[req['sample_id']].get('reference_proposition') is not None:
                raise ValueError('UNKNOWN_WITHHELD_REFERENCE_PRESENT')
            for m in req['media']:
                kinds[m['kind']]+=1
                paths.update(m['paths'] if m['kind']=='video_frames' else [m['path']])
        bundle=Path('artifacts').resolve()
        for raw in paths:
            path=Path(raw).resolve()
            if not path.is_relative_to(bundle) or not path.is_file() or not path.stat().st_size:
                raise ValueError(f'MEDIA_MISSING_OR_INVALID:{raw}')
        model_checks={}
        for model in cfg['models']:
            manifest=json.loads(Path(model['manifest_path']).read_text())
            if (manifest['model_id'],manifest['revision']) != (model['model_id'],model['revision']): raise ValueError('MODEL_REVISION_MISMATCH')
            model_checks[model['key']]=model_presence(Path(model['model_path']))
            dest=a.campaign/model['key']; dest.mkdir(exist_ok=True)
            for name in EXPECTED:
                path=dest/name
                if not path.exists(): path.symlink_to(shared/name)
                if sha(path)!=EXPECTED[name]: raise ValueError('MODEL_INPUT_LINK_MISMATCH')
            per_model=dict(cfg,candidate=model,run_id=cfg['run_id']+'_'+model['key'],input_hashes=EXPECTED)
            path=dest/'config.json'
            if path.exists() and json.loads(path.read_text())!=per_model: raise ValueError('FROZEN_MODEL_CONFIG_CHANGED')
            write(path,per_model)
            for folder in ('smoke','full','smoke_judge','full_judge'): (dest/folder).mkdir(exist_ok=True)
        report.update(status='PASS',eligible_per_model=24196,total_requested_predictions=72588,success_count=24196,
                      failure_count=0,unique_media_paths=len(paths),media_kinds=dict(kinds),model_checks=model_checks,
                      input_hashes=EXPECTED,source_revision='production_available_v10 plus l4_v3_3, validated media job 8158262',
                      config_snapshot=cfg,config_sha256=sha(a.campaign/'config.json'),
                      code_hashes={p.name:sha(p) for p in (a.campaign/'code').iterdir() if p.is_file()},
                      output_hashes={str(a.campaign/m['key']/'config.json'):sha(a.campaign/m['key']/'config.json') for m in cfg['models']})
        write(a.campaign/'preparation_report.json',report)
        print(json.dumps({k:report[k] for k in ('status','eligible_per_model','unique_media_paths','media_kinds')}),flush=True)
    except Exception as exc:
        write(a.campaign/'preparation_report.json',dict(report,status='FAIL',failure_count=1,error=f'{type(exc).__name__}: {exc}')); raise

if __name__=='__main__': main()
