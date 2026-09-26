"""Gold-blind value-key alias adapter; legacy scorer and all source outputs stay read-only."""
import json
from scorer import score as strict_score, observed, selftest as legacy_selftest

VERSION = 'a1_value_alias_v2'


def canonicalize(raw, schema):
    """Return a derived scoring view, not a new model response. No gold input."""
    if raw is None:
        return None, {'normalization': 'NOT_RUN', 'original_json_valid': None}
    obj, json_valid = observed(raw.get('raw_response', ''), raw.get('truncated', False))
    audit = dict(normalization='NONE', original_json_valid=json_valid,
                 original_object=obj, adapter_version=VERSION)
    result = dict(raw)
    if schema['kind'] == 'value':
        keys = set(obj)
        if 'value' in keys and 'query_value' in keys:
            audit['normalization'] = 'REJECT_AMBIGUOUS_VALUE_KEYS'
        elif keys == {'query_value'}:
            audit['normalization'] = 'ALIAS_QUERY_VALUE_TO_VALUE'
            result['raw_response'] = json.dumps({'value': obj['query_value']}, ensure_ascii=False)
            audit['canonical_object'] = {'value': obj['query_value']}
        elif 'query_value' in keys:
            audit['normalization'] = 'REJECT_ALIAS_WITH_EXTRA_FIELDS'
    return result, audit


def score_v2(raw, gold):
    # Extraction is completed without expected-answer access.
    canonical, audit = canonicalize(raw, gold['schema'])
    strict = strict_score(raw, gold)
    semantic = strict_score(canonical, gold)
    return dict(strict=strict, semantic=semantic, audit=audit)


def selftest():
    legacy = legacy_selftest()
    g = dict(schema=dict(kind='value', domain='count', nullable=False), expected=12)
    tests = [
        ('{"query_value":12}', False, True),
        ('{"value":12}', False, True),
        ('{"query_value":11}', False, False),
        ('{"query_value":"12"}', False, False),
        ('{"query_value":true}', False, False),
        ('{"query_value":12.0}', False, False),
        ('{"query_value":-1}', False, False),
        ('{"query_value":null}', False, False),
        ('{"value":12,"query_value":12}', False, False),
        ('{"value":11,"query_value":12}', False, False),
        ('{"query_value":12,"reason":"x"}', False, False),
        ('{"query_value":12,"query_value":12}', False, False),
        ('{"query_value":12} {}', False, False),
        ('The answer is 12.', False, False),
        ('{"query_value":12', True, False),
        ('{"query_value":12,', True, True),
        ('{"query_value":12}', True, True),
        ('{"query_value":12e', True, False),
        ('{"value":', True, False),
    ]
    for text, truncated, wanted in tests:
        raw = dict(raw_response=text, truncated=truncated)
        before = json.dumps(raw, sort_keys=True)
        got = score_v2(raw, g)
        assert got['semantic']['correct'] == wanted, (text, got)
        assert json.dumps(raw, sort_keys=True) == before, 'RAW_MUTATED'
    nullable = dict(schema=dict(g['schema'], nullable=True), expected=None)
    assert score_v2({'raw_response':'{"query_value":null}'}, nullable)['semantic']['correct']
    relational = dict(schema=dict(kind='value',domain=['LEFT_OF','RIGHT_OF'],nullable=False),expected='LEFT_OF')
    assert score_v2({'raw_response':'{"query_value":"LEFT_OF"}'}, relational)['semantic']['correct']
    assert not score_v2({'raw_response':'{"query_value":"left_of"}'}, relational)['semantic']['correct']
    r = {'raw_response':'{"query_value":12}'}
    bad = dict(g, expected=11)
    assert canonicalize(r,g['schema']) == canonicalize(r,bad['schema'])
    assert not score_v2(dict(r,infrastructure_error='OOM'),g)['semantic']['correct']
    verdict = dict(schema=dict(kind='verdict'), expected='SUPPORTED')
    assert score_v2({'raw_response':'{"label":"SUPPORTED"}'}, verdict)['semantic']['correct']
    assert not score_v2({'raw_response':'{"query_value":"SUPPORTED"}'}, verdict)['semantic']['correct']
    joint = dict(schema=dict(kind='joint',domain='count',nullable=False,keys=['PRE','POST']), expected={'PRE':1,'POST':2})
    assert score_v2({'raw_response':'{"POST":2,"PRE":1}'},joint)['semantic']['correct']
    assert not score_v2({'raw_response':'{"PRE":2,"POST":1}'},joint)['semantic']['correct']
    assert score_v2(None,g)['semantic']['status'] == 'NOT_RUN'
    return dict(status='PASS',legacy_tests=legacy['tests'],new_tests=len(tests)+10)
