"""Independent two-seed held-out inference and the unchanged label_rescore_v2."""
import argparse
import collections
import importlib.util
import os
import shutil
import sys
from plan import *

TEST_CODE = HERE.parent / 'heldout_test_v1'
LABEL_CODE = HERE.parent / 'label_rescore_v2'
REPO = HERE.parents[1] / 'SpaceConflict'
ORIGINAL = REPO / 'scripts/full_multimodel_20260908_v1'
EXTENSION = REPO / 'scripts/full_multimodel_split_v5'


def evaluation_root(seed):
    return OUTPUT / 'evaluation' / ('seed_' + str(seed))


def prepare(seed):
    dest = evaluation_root(seed)
    if (dest / 'FREEZE.json').exists():
        raise FileExistsError('ALREADY_PREPARED_TEST')
    key = f'{METHOD}__seed_{seed}'
    train = seed_output(seed)
    complete = read(train / 'runs' / key / 'TRAINING_COMPLETE.json')
    exposure = read(train / 'ACTUAL_EXPOSURE_CONFIRMED.json')
    p = read(train / 'PLAN.json')
    if exposure['status'] != 'PASS_EXACT_FROZEN_EXPOSURES_AND_PROCESSOR_TOKENS':
        raise ValueError('ACTUAL_EXPOSURE_NOT_VALIDATED')
    if complete['progress']['step'] != p['optimizer_updates']:
        raise ValueError('NOT_FIXED_FINAL_STEP')
    original = ROOT / 'heldout_test_v1' / f'pss_l4__seed_{seed}'
    cfg = read(original / 'config.json')
    adapter = Path(complete['final_adapter'])
    if adapter != train / 'runs' / key / 'checkpoints' / f'step_{p["optimizer_updates"]:07d}' / 'adapter':
        raise ValueError('UNEXPECTED_FINAL_ADAPTER')
    if read(adapter / 'adapter_config.json')['base_model_name_or_path'] != cfg['model_path']:
        raise ValueError('BASE_MISMATCH')
    provenance = dict(training_method=METHOD, training_seed=seed, step=p['optimizer_updates'],
        selection='FIXED_FINAL_STEP_NOT_TEST_SELECTED',
        files={str(path): sha(path) for path in [train / 'runs' / key / 'TRAINING_COMPLETE.json',
            train / 'ACTUAL_EXPOSURE_CONFIRMED.json', adapter / 'adapter_config.json', adapter / 'adapter_model.safetensors']})
    cfg.update(key=key, run_id=RUN_ID+'_'+key, model_id='Qwen/Qwen3.5-9B+'+key,
               adapter_path=str(adapter), adapter_provenance=provenance)
    model = dest / key
    model.mkdir(parents=True)
    for name in ('requests.jsonl','private_gold.jsonl','rubric.json'):
        source = (original / name).resolve()
        if name in cfg['input_hashes'] and sha(source) != cfg['input_hashes'][name]:
            raise ValueError('TEST_PAYLOAD_CHANGED')
        (model / name).symlink_to(source)
    write(model / 'config.json', cfg)
    plan = dict(configs={key: sha(model / 'config.json')}, code_hashes=read(OUTPUT/'FREEZE.json')['code_hashes'],
                split_worlds={'test':1124}, keys=[key], n_each=5608, shards_each=4,
                scoring_policy_sha256=sha(LABEL_CODE/'label_policy.py'), training_plan_sha256=sha(train/'PLAN.json'))
    write(dest / 'PLAN.json', plan)
    write(dest / 'FREEZE.json', dict(plan_sha256=sha(dest/'PLAN.json'),status='PASS_FIXED_FINAL_ADAPTER'))


def infer(seed, shard):
    # Override only run locations/model keys, then invoke the existing adapter
    # wrapper. Media loader, prompt, generation seed, 512-token policy unchanged.
    sys.path.insert(0, str(TEST_CODE))
    import settings
    settings.ROOT = evaluation_root(seed)
    settings.KEYS = (f'{METHOD}__seed_{seed}',)
    settings.RUN_ID = RUN_ID
    spec=importlib.util.spec_from_file_location('preserved_adapter_inference',TEST_CODE/'infer_adapter.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    sys.argv=[str(TEST_CODE/'infer_adapter.py'),'--model-index','0','--shard-index',str(shard),'--run-id',RUN_ID]
    mod.main()


def score(seed):
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    dest=evaluation_root(seed);key=f'{METHOD}__seed_{seed}';model=dest/key
    p=read(dest/'PLAN.json')
    if sha(dest/'PLAN.json')!=read(dest/'FREEZE.json')['plan_sha256']:
        raise ValueError('EVAL_PLAN_CHANGED')
    cfg=read(model/'config.json')
    if sha(model/'config.json')!=p['configs'][key]:raise ValueError('CONFIG_CHANGED')
    ids=set();raw_hashes={}
    for shard in range(4):
        path=model/'full'/f'predictions_{shard:03d}.jsonl'
        done=read(model/'full'/f'adapter_completion_{shard:03d}.json')
        if done['output_sha256']!=sha(path) or done['adapter_receipt_sha256']!=sha(model/f'adapter_receipt_{shard:03d}.json'):
            raise ValueError('RAW_COMPLETION_CHANGED')
        for row in rows(path):
            if row['sample_id'] in ids:raise ValueError('DUPLICATE_TEST_PREDICTION')
            if row['config_sha256']!=p['configs'][key] or row['requested_samples_sha256']!=cfg['input_hashes']['requests.jsonl']:
                raise ValueError('PREDICTION_INPUT_CHANGED')
            ids.add(row['sample_id'])
        raw_hashes[str(path)]=sha(path)
    gold=ROOT/'data/test/private_gold.jsonl';requests=ROOT/'data/test/requests.jsonl'
    if len(ids)!=5608 or ids!={r['sample_id'] for r in rows(gold)}:raise ValueError('FULL_TEST_COVERAGE')
    sys.path[:0]=[str(EXTENSION),str(ORIGINAL),str(REPO/'src')]
    from types import SimpleNamespace
    from base_score_v2 import score as strict_score
    strict_score(SimpleNamespace(run_root=model,scope='full',run_id=cfg['run_id'],gate=False))
    # Reuse the original v2 score function with a new sealed manifest.
    sys.path.insert(0,str(LABEL_CODE))
    import config
    output=dest/'label_rescore_v2'
    config.ROOT=output;config.KEYS=(key,);config.RUN_ID=RUN_ID
    manifest=dict(run_id=RUN_ID,worlds=1124,gold_path=str(gold),gold_sha256=sha(gold),
        requests_path=str(requests),requests_sha256=sha(requests),code_hashes=p['code_hashes'],
        sources={key:dict(raw_hashes=raw_hashes,original_report=str(model/'full_score.json'),
            original_report_sha256=sha(model/'full_score.json'),original_scored=str(model/'full_scored.jsonl'),
            original_scored_sha256=sha(model/'full_scored.jsonl'),config_sha256=sha(model/'config.json'))})
    write(output/'MANIFEST.json',manifest)
    write(output/'FREEZE.json',dict(manifest_sha256=sha(output/'MANIFEST.json')))
    spec=importlib.util.spec_from_file_location('preserved_same_v2_scorer',LABEL_CODE/'run.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    mod.score(0)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('stage',choices=('prepare','infer','score'))
    parser.add_argument('--seed',type=int,choices=SEEDS,required=True)
    parser.add_argument('--shard',type=int)
    args=parser.parse_args()
    if args.stage=='prepare':prepare(args.seed)
    elif args.stage=='infer':infer(args.seed,args.shard if args.shard is not None else int(os.environ['SLURM_ARRAY_TASK_ID']))
    else:score(args.seed)


if __name__=='__main__':main()
