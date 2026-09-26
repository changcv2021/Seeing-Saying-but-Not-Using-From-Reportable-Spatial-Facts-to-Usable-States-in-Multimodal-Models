"""Deterministic sampling and exact supervised-token update boundaries (stdlib)."""
import copy
import hashlib
import json
import random

METHODS = ('answer_natural', 'answer_balanced', 'cot_partial', 'pss_l4', 'pss_full')
LEVELS = ('L1', 'L2', 'L3', 'L4')
SEEDS = (20260922, 20260923)
TOKENS_PER_UPDATE = 1024


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Schedule:
    """Same base-ID stream for all balanced arms; explicit additional state stream.

    Matching tokens means different prefix lengths/exposure counts, NOT identical
    numbers of examples. CoT replaces a target, never adds a second answer stream.
    All cursors, including a target spanning update boundaries, are checkpointed.
    """
    def __init__(self, catalog, method, seed, state=None):
        if method not in METHODS:
            raise ValueError('METHOD')
        self.catalog = catalog; self.method = method; self.seed = seed
        self.s = copy.deepcopy(state) if state is not None else dict(events=0, base=0, aux=0, pending=None)
        self.base = sorted(k for k, r in catalog.items() if r['pool'] == 'answer')
        self.base_levels = {level: [k for k in self.base if catalog[k]['level'] == level] for level in LEVELS}
        self.states = sorted(k for k, r in catalog.items() if r['pool'] == 'state' and
                             (method != 'pss_l4' or r['level'] == 'L4'))
        self.state_levels = {level: [k for k in self.states if catalog[k]['level'] == level] for level in LEVELS}
        self.cache = {}
        if not self.base or any(not v for v in self.base_levels.values()):
            raise ValueError('EMPTY_OR_MISSING_ANSWER_LEVEL')
        if method.startswith('pss') and not self.states:
            raise ValueError('EMPTY_STATE_POOL')

    def _cycle(self, values, index, label):
        if not values:
            raise ValueError('EMPTY_CYCLE:' + label)
        epoch, offset = divmod(index, len(values))
        key = (label, epoch)
        if key not in self.cache:
            order = list(values)
            random.Random(digest([self.seed, label, epoch])).shuffle(order)
            # Keep only the most recent cycle for each independent stream.
            self.cache = {k: v for k, v in self.cache.items() if k[0] != label}
            self.cache[key] = order
        return self.cache[key][offset]

    def _next(self):
        state_turn = self.method.startswith('pss') and self.s['events'] % 2 == 1
        if state_turn:
            index = self.s['aux']; self.s['aux'] += 1
            if self.method == 'pss_l4':
                key = self._cycle(self.states, index, 'state:L4')
            else:
                levels = [level for level in LEVELS if self.state_levels[level]]
                level = levels[index % len(levels)]
                key = self._cycle(self.state_levels[level], index // len(levels), 'state:' + level)
        else:
            index = self.s['base']; self.s['base'] += 1
            if self.method == 'answer_natural':
                key = self._cycle(self.base, index, 'natural')
            else:
                level = LEVELS[index % 4]
                key = self._cycle(self.base_levels[level], index // 4, 'balanced:' + level)
            if self.method == 'cot_partial':
                key = 'cot:' + self.catalog[key]['sample_id']
                if key not in self.catalog:
                    raise ValueError('COT_POOL_MISMATCH')
        self.s['events'] += 1
        return key

    def segments(self, tokens):
        if type(tokens) is not int or tokens < 1:
            raise ValueError('POSITIVE_TOKEN_BUDGET_REQUIRED')
        result = []
        while tokens:
            if self.s['pending'] is None:
                self.s['pending'] = dict(key=self._next(), offset=0)
            p = self.s['pending']; total = self.catalog[p['key']]['target_tokens']
            count = min(tokens, total - p['offset'])
            result.append(dict(key=p['key'], offset=p['offset'], count=count,
                               target_tokens=total, begins_example=p['offset'] == 0))
            p['offset'] += count; tokens -= count
            if p['offset'] == total:
                self.s['pending'] = None
        return result

    def state_dict(self):
        return copy.deepcopy(self.s)

    def coverage_tokens(self):
        """Minimal whole-event prefix covering every original sample and aux row."""
        wanted = set(self.base)
        if self.method == 'cot_partial':
            wanted = {'cot:' + self.catalog[k]['sample_id'] for k in self.base}
        if self.method.startswith('pss'):
            wanted.update(self.states)
        seen = set(); tokens = 0
        while not wanted <= seen:
            key = self._next(); tokens += self.catalog[key]['target_tokens']; seen.add(key)
        return tokens

