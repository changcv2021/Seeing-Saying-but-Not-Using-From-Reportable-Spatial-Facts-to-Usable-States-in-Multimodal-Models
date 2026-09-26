"""CPU-only audit and freeze; source artifacts remain read-only."""
import collections
import os
import shutil
from settings import *


def link(source, destination):
    if destination.exists() or destination.is_symlink():
        if destination.resolve() != source.resolve():
            raise ValueError('EXISTING_DIFFERENT_INPUT:' + str(destination))
    else:
        destination.symlink_to(source)


def main():
    args = arguments(__doc__).parse_args()
    validate(args)
    if args.dry_run:
        print(json.dumps(dict(keys=KEYS, n_each=N_TEST, shards_each=SHARDS)))
        return
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('SLURM_REQUIRED')
    if (ROOT / 'FREEZE.json').exists():
        if not args.resume:
            raise FileExistsError('ALREADY_FROZEN')
        verify_plan()
        return
    audit = read(PSS / 'SPLIT_AUDIT.json')
    if not audit['status'].startswith('PASS_'):
        raise ValueError('SOURCE_SPLIT_AUDIT_NOT_PASS')
    for relative, digest in audit['files'].items():
        if sha(PSS / relative) != digest:
            raise ValueError('FROZEN_SPLIT_CHANGED:' + relative)
    worlds, ids = {}, {}
    for split in ('train', 'dev', 'test'):
        rows = load(PSS / 'data' / split / 'private_gold.jsonl')
        unique(rows)
        if any(r['split'] != split or not r.get('underlying_world_id') for r in rows):
            raise ValueError('BAD_SPLIT_OR_WORLD')
        worlds[split] = {r['underlying_world_id'] for r in rows}
        ids[split] = {r['sample_id'] for r in rows}
    for a, b in (('train', 'dev'), ('train', 'test'), ('dev', 'test')):
        if worlds[a] & worlds[b] or ids[a] & ids[b]:
            raise ValueError('WORLD_OR_SAMPLE_LEAKAGE')
    requests = load(PSS / 'data/test/requests.jsonl')
    gold = unique(load(PSS / 'data/test/private_gold.jsonl'))
    if len(requests) != N_TEST or set(unique(requests)) != set(gold):
        raise ValueError('TEST_ID_MISMATCH')
    old_requests = unique(load(OLD / 'requests.jsonl'))
    kinds = collections.Counter()
    paths = set()
    for row in requests:
        if row != old_requests[row['sample_id']] or row['split'] != 'test':
            raise ValueError('PUBLIC_TEST_PAYLOAD_CHANGED')
        if set(row) & {'gold', 'reference_proposition', 'certificate', 'answer'}:
            raise ValueError('PRIVATE_FIELD_IN_REQUEST')
        for media in row.get('media', []):
            kinds[media.get('kind', 'image')] += 1
            paths.update(media.get('paths', [media.get('path')]))
    if any(not p or not Path(p).is_file() for p in paths):
        raise ValueError('MISSING_TEST_MEDIA_NO_BLANK_SUBSTITUTION')
    # Historical runner has a shared image/media cursor. Fail closed on mixed
    # native-video inputs instead of silently changing that tested protocol.
    if set(kinds) - {'image'}:
        raise ValueError('NATIVE_VIDEO_REQUIRES_A_SEPARATE_VALIDATED_ADAPTER')
    configs = {}
    base = read(OLD / 'config.json')
    for key in KEYS:
        run = TRAIN / 'runs' / key
        complete = read(run / 'TRAINING_COMPLETE.json')
        adapter = Path(complete['final_adapter'])
        if (complete['status'] != 'COMPLETE_FIXED_UPDATE_BUDGET'
                or complete['progress']['step'] != 2237
                or adapter != run / 'checkpoints/step_0002237/adapter'):
            raise ValueError('NOT_FIXED_FINAL_ADAPTER:' + key)
        adapter_cfg = read(adapter / 'adapter_config.json')
        if adapter_cfg['base_model_name_or_path'] != base['model_path']:
            raise ValueError('ADAPTER_BASE_MISMATCH')
        provenance = dict(training_method=key.rsplit('__seed_', 1)[0],
                          training_seed=int(key.rsplit('_', 1)[1]), step=2237,
                          selection='FIXED_FINAL_STEP_NOT_TEST_SELECTED',
                          files={str(p): sha(p) for p in [run / 'TRAINING_COMPLETE.json',
                              adapter / 'adapter_config.json', adapter / 'adapter_model.safetensors']})
        cfg = dict(base, key=key, run_id=RUN_ID + '_' + key, replicas=SHARDS,
                   model_id=base['model_id'] + '+' + key, adapter_path=str(adapter),
                   adapter_provenance=provenance,
                   base_config_sha256=sha(Path(base['model_path']) / 'config.json'),
                   input_hashes={'requests.jsonl': audit['files']['data/test/requests.jsonl'],
                                 'private_gold.jsonl': audit['files']['data/test/private_gold.jsonl']},
                   max_new_tokens=512)
        dest = ROOT / key
        dest.mkdir(parents=True, exist_ok=True)
        link(PSS / 'data/test/requests.jsonl', dest / 'requests.jsonl')
        link(PSS / 'data/test/private_gold.jsonl', dest / 'private_gold.jsonl')
        link(OLD / 'rubric.json', dest / 'rubric.json')
        write(dest / 'config.json', cfg)
        configs[key] = sha(dest / 'config.json')
    baseline = []
    for row in load(OLD / 'full_scored.jsonl'):
        sid = row['sample_id']
        if sid not in gold:
            continue
        if any(row[k] != gold[sid][k] for k in ('gold', 'level', 'component', 'pair_id')):
            raise ValueError('BASELINE_GOLD_MISMATCH')
        baseline.append(row)
    if set(unique(baseline)) != set(gold):
        raise ValueError('INCOMPLETE_BASELINE')
    write(ROOT / 'baseline_test_score.json', dict(
        source=str(OLD / 'full_scored.jsonl'), source_sha256=sha(OLD / 'full_scored.jsonl'),
        model_id=base['model_id'], revision=base['revision'], overall=metrics(baseline),
        by_level={level: metrics([r for r in baseline if r['level'] == level])
                  for level in ('L1', 'L2', 'L3', 'L4')}))
    code_paths = list(CODE.glob('*.py')) + list(CODE.glob('*.sbatch'))
    code_paths += [ORIGINAL / p for p in ('infer.py', 'protocol.py', 'common.py', 'output_policy.py')]
    code_paths += [EXTENSION / p for p in ('gpu_health.py', 'base_score_v2.py')]
    code_paths += [REPO / 'src/spaceconflict/mllm_l4.py', PSS / 'environment/ENVIRONMENT.json']
    code_hashes = {str(p): sha(p) for p in code_paths}
    snapshot = ROOT / 'source_snapshot'
    for path in code_paths:
        relative = path.relative_to(SPACE) if path.is_relative_to(SPACE) else Path('environment') / path.name
        dest = snapshot / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    plan = dict(run_id=RUN_ID, status='FROZEN_BEFORE_TEST', keys=KEYS, n_each=N_TEST,
                total_requests=N_TEST * len(KEYS), shards_each=SHARDS,
                shard_rule='request_position_modulo_4', configs=configs, code_hashes=code_hashes,
                source_revision=base['revision'], code_commit='FILE_HASH_PROVENANCE_NO_COMMIT_ASSERTED',
                decode_seed=DECODE_SEED, input_hashes=audit['files'],
                split_worlds={k: len(v) for k, v in worlds.items()},
                by_level=dict(collections.Counter(r['level'] for r in requests)),
                media_kinds=dict(kinds), unique_media_paths=len(paths),
                no_gold_in_inference=True, output_policy='retained_prefix_512_v1',
                no_accuracy_based_retry=True, test_used_for_selection=False,
                resources=dict(gpu_partition='gpu', cpu_partition='general', account='YOUR_ACCOUNT',
                               qos='allocated', gpus_per_shard=1, cpus=4, memory='64G',
                               time='2-00:00:00', artificial_concurrency_cap=None),
                auxiliary_judge='NOT_REQUESTED_IN_THIS_PRIMARY_TEST_LAUNCH',
                job_id=os.environ['SLURM_JOB_ID'])
    write(ROOT / 'PLAN.json', plan)
    write(ROOT / 'FREEZE.json', dict(plan_sha256=sha(ROOT / 'PLAN.json'), status='PASS',
          baseline_sha256=sha(ROOT / 'baseline_test_score.json')))
    print(json.dumps(plan), flush=True)


if __name__ == '__main__':
    main()
