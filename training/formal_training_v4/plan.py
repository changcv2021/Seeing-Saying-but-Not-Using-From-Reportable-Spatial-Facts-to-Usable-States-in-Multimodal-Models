"""Update-matched, two-GPU plan; no data processing or submission on import."""
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / 'execution_pss_v2'
LEGACY = HERE.parent / 'formal_training_v3'
ROOT = Path('artifacts/model_results/pss_20260922_v1/approved_v2')
OUTPUT = ROOT / 'formal_training_v4'
METHODS = ('answer_natural', 'answer_balanced', 'cot_partial', 'pss_l4', 'pss_full')
SEEDS = (20260922, 20260923)
DEFAULTS = dict(schema='update_matched_ddp_v4', optimizer_updates=2237,
                effective_batch_size=16, world_size=2, micro_batch_size=2,
                loader_workers=2, prefetch_factor=2, cache_bytes_per_worker=536870912,
                attention_backend='sdpa_auto', loss_normalization='mean_per_base_example',
                learning_rate=2e-5, weight_decay=0.01, warmup_fraction=0.03,
                max_grad_norm=1.0, lora_rank=16, lora_alpha=32, lora_dropout=0.05,
                gradient_checkpointing=True, checkpoint_seconds=900)


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate_plan(plan):
    for key in ('optimizer_updates', 'effective_batch_size', 'world_size', 'micro_batch_size',
                'loader_workers', 'prefetch_factor', 'cache_bytes_per_worker'):
        if type(plan[key]) is not int or plan[key] < 1:
            raise ValueError('POSITIVE_INTEGER:' + key)
    if plan['world_size'] != 2 or plan['effective_batch_size'] % 2:
        raise ValueError('TWO_RANKS_AND_DIVISIBLE_GLOBAL_BATCH_REQUIRED')
    if plan['attention_backend'] != 'sdpa_auto':
        raise ValueError('ATTENTION_BACKEND')
    if plan['schema'] != DEFAULTS['schema'] or plan['loss_normalization'] != 'mean_per_base_example':
        raise ValueError('BUDGET_SCHEMA')
    if not 0 <= plan['warmup_fraction'] < 1:
        raise ValueError('WARMUP')
    for key in ('learning_rate', 'weight_decay', 'max_grad_norm', 'lora_rank', 'lora_alpha', 'lora_dropout'):
        if plan[key] != DEFAULTS[key]:
            raise ValueError('FROZEN_SHARED_HYPERPARAMETER:' + key)
    if 'tokens_per_update' in plan or 'supervised_tokens' in plan:
        raise ValueError('OUTPUT_TOKEN_EQUALITY_IS_NOT_A_BUDGET')


class ExampleSchedule:
    """Random-access schedule independent of target length, method and worker order.

    Balanced arms use identical level -> world -> original sample streams.
    Natural retains the original sample-frequency control. Local Random instances
    never consume model/dropout RNG. Resume starts at step * global batch size.
    """
    def __init__(self, samples, seed, balanced=True):
        self.samples = samples
        self.ids = sorted(samples)
        self.seed = seed
        self.balanced = balanced
        self.levels = defaultdict(lambda: defaultdict(list))
        self.cache = {}
        for sid in self.ids:
            row = samples[sid]
            self.levels[row['level']][row['world']].append(sid)
        if not self.ids or set(self.levels) != {'L1', 'L2', 'L3', 'L4'}:
            raise ValueError('ALL_FOUR_TRAIN_LEVELS_REQUIRED')

    def shuffled(self, values, label, cycle):
        key = (label, cycle)
        if key not in self.cache:
            order = sorted(values)
            random.Random(digest([self.seed, label, cycle])).shuffle(order)
            self.cache = {k: v for k, v in self.cache.items() if k[0] != label}
            self.cache[key] = order
        return self.cache[key]

    def at(self, index):
        if index < 0:
            raise ValueError('NEGATIVE_INDEX')
        if not self.balanced:
            cycle, offset = divmod(index, len(self.ids))
            return self.shuffled(self.ids, 'natural', cycle)[offset]
        level = ('L1', 'L2', 'L3', 'L4')[index % 4]
        worlds = self.levels[level]
        cycle, offset = divmod(index // 4, len(worlds))
        world = self.shuffled(worlds, level, cycle)[offset]
        ids = worlds[world]
        sample_cycle, sample_offset = divmod(cycle, len(ids))
        return self.shuffled(ids, level + ':' + world, sample_cycle)[sample_offset]


def rank_indices(step, batch_size, rank, world_size=2):
    if batch_size % world_size or not 0 <= rank < world_size:
        raise ValueError('RANK_BATCH')
    return list(range(step * batch_size + rank, (step + 1) * batch_size, world_size))


def unit_records(samples, sid, method, seed, index):
    """One primary example; same-world auxiliary is NOT an extra batch unit."""
    sample = samples[sid]
    if method not in METHODS: raise ValueError('METHOD')
    if method == 'cot_partial': return [(sample['cot'], 1.0)]
    if not method.startswith('pss') or not sample[method]:
        return [(sample['answer'], 1.0)]
    auxiliary = sample[method]
    selected = int(digest([seed, sid, index, 'same_world_aux']), 16) % len(auxiliary)
    return [(sample['answer'], 0.5), (auxiliary[selected], 0.5)]


def code_hashes():
    paths = list(HERE.glob('*.py')) + list(HERE.glob('*.sbatch')) + list(ENGINE.glob('*.py'))
    paths += [LEGACY / 'checkpoint.py']
    # Include the frozen public input protocol imported by model_io.
    protocol = HERE.parents[1] / 'dataset/scripts/full_multimodel_20260908_v1'
    paths += list(protocol.glob('*.py'))
    return {str(p): sha(p) for p in sorted(set(paths))}
