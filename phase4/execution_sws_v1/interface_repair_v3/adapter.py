"""Gold-blind v3: preserve values while repairing two serialization ambiguities."""
import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from contracts import parse as strict_parse
from research_utils import strict_json_loads

spec = importlib.util.spec_from_file_location('sws_adapter_v2_baseline', HERE.parent / 'interface_repair_v2/adapter.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
VERSION = 'sws_interface_normalization_v3_20260910'
RULES = baseline.RULES[:-1] + [
    'Wrap an entire bare JSON null as {"value":null} only for a nullable single-value schema.',
    'Convert canonical nonnegative decimal strings to identical integers only in count value slots.',
    'Never alter negative counts, bools, floats, enum labels, verdicts, query IDs, extra keys or missing values.',
    'Never use gold, model identity, correctness or multiple-answer selection.',
]


def normalize(text, schema):
    result = baseline.normalize(text, schema)
    result['version'] = VERSION
    if result['strict']['status'] == 'VALID':
        return result
    candidate = result['canonical_text']
    try:
        obj = strict_json_loads(candidate)
    except (ValueError, TypeError):
        return result
    ops = list(result['operations'])
    if obj is None and schema['kind'] == 'value' and schema.get('nullable', True):
        obj = {'value': None}
        ops.append(dict(rule='WRAP_WHOLE_BARE_NULL_SINGLE_VALUE'))
    if isinstance(obj, dict) and schema.get('domain') == 'count':
        obj = copy.deepcopy(obj)
        paths = []

        def convert(container, key, path):
            if (isinstance(container, dict) and isinstance(container.get(key), str)
                    and re.fullmatch(r'0|[1-9][0-9]*', container[key])):
                container[key] = int(container[key])
                paths.append(path)

        if schema['kind'] in ('value', 'joint'):
            convert(obj, 'value', '$.value')
            if schema['kind'] == 'value' and set(obj) == {'query_value'}:
                convert(obj, 'query_value', '$.query_value')
        elif schema['kind'] == 'facts' and isinstance(obj.get('facts'), list):
            for i, item in enumerate(obj['facts']):
                convert(item, 'value', f'$.facts[{i}].value')
        if paths:
            ops.append(dict(rule='CANONICAL_DECIMAL_STRING_IN_COUNT_SLOT', paths=paths))
    if len(ops) != len(result['operations']):
        candidate = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    result.update(canonical_text=candidate, normalized=strict_parse(candidate, schema),
                  operations=ops, changed=bool(ops))
    return result


def remaining_failure(result, schema):
    """Diagnostic only; never changes scoring or repairs substantive errors."""
    parsed = result['normalized']
    if parsed['status'] == 'VALID':
        return 'NONE'
    obj = parsed.get('parsed')
    slots = []
    if isinstance(obj, dict):
        slots = [obj.get('value')] if schema['kind'] in ('value', 'joint') else []
        if schema['kind'] == 'facts' and isinstance(obj.get('facts'), list):
            slots = [r.get('value') for r in obj['facts'] if isinstance(r, dict)]
    if schema.get('domain') == 'count' and any(type(v) is int and v < 0 for v in slots):
        return 'CONTENT_DOMAIN_ERROR_NEGATIVE_COUNT'
    return 'UNRESOLVED_INTERFACE_OR_DOMAIN_ERROR'
