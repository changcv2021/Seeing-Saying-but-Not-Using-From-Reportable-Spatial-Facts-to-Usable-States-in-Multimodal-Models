"""Deterministic, gold-blind scoring views. Never edit or regenerate a model answer."""
import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from contracts import parse as strict_parse
from research_utils import strict_json_loads

VERSION='sws_interface_normalization_v2_20260910'
RULES=[
    'Unwrap exactly one whole-response ```json or ``` fenced block, without prose.',
    'Remove one final full stop only when the remaining text is one complete strict JSON object.',
    'Close one missing outer object brace only after an already completed container or quoted string.',
    'Convert the exact string null to JSON null only in schema-declared nullable value slots.',
    'Keep original field order and all numeric, categorical, verdict, query_id and extra-field content.',
    'Never choose between answers, fill missing fields, coerce numeric strings/bools, or use gold.',
]


def as_object(text):
    try:
        obj=strict_json_loads(text)
        return obj if isinstance(obj,dict) else None
    except (ValueError,TypeError):return None


def normalize(text,schema):
    """Only text and public schema enter; no expected-answer or model-dependent branch."""
    original=strict_parse(text,schema);candidate=text.strip();ops=[]
    # Already valid answers retain the exact original text and parser result.
    if original['status']=='VALID':
        return dict(version=VERSION,canonical_text=text,strict=original,normalized=copy.deepcopy(original),operations=[],changed=False)
    fence=re.fullmatch(r'```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```',candidate)
    if fence:
        candidate=fence.group(1).strip();ops.append(dict(rule='UNWRAP_WHOLE_JSON_FENCE'))
    obj=as_object(candidate)
    if obj is None and candidate.endswith('.'):
        trimmed=candidate[:-1].rstrip();parsed=as_object(trimmed)
        if parsed is not None:
            candidate=trimmed;obj=parsed;ops.append(dict(rule='REMOVE_SINGLE_TRAILING_PERIOD'))
    # A number cut at the boundary could be the prefix of a longer number: never close it.
    # The strict decoder must accept the entire result, including duplicate-key rejection.
    if obj is None and candidate.startswith('{') and candidate.endswith((']','}','"')):
        parsed=as_object(candidate+'}')
        if parsed is not None:
            candidate+='}';obj=parsed;ops.append(dict(rule='CLOSE_SINGLE_OUTER_OBJECT_BRACE'))
    if obj is not None and schema.get('nullable',True):
        normalized=copy.deepcopy(obj);null_paths=[]
        def null_slot(container,key,path):
            if isinstance(container,dict) and container.get(key)=='null':
                container[key]=None;null_paths.append(path)
        if schema['kind'] in ('value','joint'):
            null_slot(normalized,'value','$.value')
            if schema['kind']=='value' and set(normalized)=={'query_value'}:
                null_slot(normalized,'query_value','$.query_value')
        elif schema['kind']=='facts' and isinstance(normalized.get('facts'),list):
            for i,record in enumerate(normalized['facts']):
                null_slot(record,'value',f'$.facts[{i}].value')
        if null_paths:
            obj=normalized;candidate=json.dumps(obj,ensure_ascii=False,separators=(',',':'))
            ops.append(dict(rule='NULL_STRING_IN_NULLABLE_VALUE_SLOT',paths=null_paths))
    result=strict_parse(candidate,schema)
    return dict(version=VERSION,canonical_text=candidate,strict=original,normalized=result,operations=ops,changed=bool(ops))
