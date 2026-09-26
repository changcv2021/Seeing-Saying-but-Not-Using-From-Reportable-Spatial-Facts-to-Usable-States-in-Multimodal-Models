"""Versioned state response interface; legacy targets and parser remain unchanged.

Only representation is normalized. No gold, query, or media is used for parsing.
"""
import json

from state_schema import canonicalize_state, parse_state as parse_state_v1

VERSION = 'state_interface_v2'
LEGACY_SUFFIXES = (
    'Return only <STATE> with fields entities, variable, frame, value, in that order using JSON values. At most 512 output tokens.',
    'Return only <STATE> with fields entities, variable, optional frame, value in that order, using JSON values. At most 512 output tokens.',
)
OUTPUT_INSTRUCTION = '''STATE OUTPUT FORMAT v2:
Return exactly one <STATE> block. Write one field per line, not a JSON object.
Use these field names in order: entities, variable, frame (only if specified), value.
Each field is followed by a colon and a JSON value. entities must always be a
JSON array of entity-name strings, even for a single entity. Preserve the queried
entity names and their order; do not merge, split, or invent entities.
variable and frame are JSON strings. value must be a nonnegative JSON integer
for count; a JSON boolean for existence, visibility, or identity; or the requested
relation string for a relation task. Do not quote integers or booleans.
The following is a format template, not an example answer; replace placeholders:
<STATE>
entities: ["<queried entity name>"]
variable: "<queried variable>"
frame: "<specified reference frame; omit this line if not specified>"
value: <computed JSON value>
</STATE>
No Markdown fences, explanation, second answer, or text outside the block.
Use at most 512 output tokens.'''


def state_prompt_v2(public_task_prompt):
    """Only sees the existing public query, never a private state/value."""
    if not isinstance(public_task_prompt, str):
        raise ValueError('STATE_PROMPT_TEXT')
    if public_task_prompt.endswith(OUTPUT_INSTRUCTION):
        return public_task_prompt
    for suffix in LEGACY_SUFFIXES:
        if public_task_prompt.endswith(suffix):
            return public_task_prompt[:-len(suffix)] + OUTPUT_INSTRUCTION
    raise ValueError('UNRECOGNIZED_STATE_OUTPUT_INSTRUCTION')


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('DUPLICATE_FIELD:' + key)
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError('NONFINITE_JSON:' + value)


def _json(text):
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def parse_state_response(text):
    """Accept one complete state; reject ambiguity rather than repair content.

    Returns the canonical state plus an explicit representation receipt. The
    original strict parser is still reported separately. A scalar entity string
    is wrapped only for unary count/existence/visibility, never for relations or
    identity. No numeric coercion, case folding, missing-field completion, or
    selection from multiple candidate answers is permitted.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError('STATE_TEXT')
    raw = text.strip()
    try:
        parse_state_v1(raw)
        legacy_valid = True
    except (ValueError, TypeError, KeyError):
        legacy_valid = False
    transformations = []
    if raw.startswith('```'):
        lines = raw.splitlines()
        if lines[0] not in ('```', '```json') or lines[-1] != '```':
            raise ValueError('STATE_FENCE')
        raw = '\n'.join(lines[1:-1]).strip()
        transformations.append('remove_single_markdown_fence')
    if raw.startswith('<STATE>') and raw.endswith('</STATE>'):
        body = raw[len('<STATE>'):-len('</STATE>')].strip()
        wrapped = True
    elif raw.startswith('{'):
        body = raw
        wrapped = False
    else:
        raise ValueError('STATE_BOUNDARY')
    if '<STATE>' in body or '</STATE>' in body or '```' in body:
        raise ValueError('MULTIPLE_OR_EMBEDDED_STATE_BLOCKS')
    if body.startswith('{'):
        obj = _json(body)
        source_format = 'wrapped_json_object' if wrapped else 'json_object'
    else:
        if not wrapped:
            raise ValueError('STATE_BOUNDARY')
        pairs = []
        for line in body.splitlines():
            if not line.strip():
                continue
            if ':' not in line:
                raise ValueError('STATE_FIELD_SYNTAX')
            key, value = line.split(':', 1)
            pairs.append((key.strip(), _json(value.strip())))
        obj = _unique_object(pairs)
        source_format = 'canonical_fields'
    if not isinstance(obj, dict):
        raise ValueError('STATE_OBJECT')
    variable = obj.get('variable')
    if not isinstance(variable, str):
        raise ValueError('STATE_VARIABLE')
    if isinstance(obj.get('entities'), str):
        if variable not in ('count', 'existence', 'visibility'):
            raise ValueError('AMBIGUOUS_SCALAR_ENTITIES')
        if not obj['entities'].strip():
            raise ValueError('STATE_ENTITIES')
        obj = dict(obj, entities=[obj['entities']])
        transformations.append('unary_entity_string_to_singleton_list')
    state = canonicalize_state(obj)
    if any(not entity.strip() for entity in state['entities']):
        raise ValueError('STATE_ENTITIES')
    return dict(state=state, source_format=source_format,
                legacy_strict_valid=legacy_valid, transformations=transformations,
                parser_version=VERSION)


def score_state_response(text, gold):
    """Gold affects comparison only, never parsing/normalization."""
    expected = canonicalize_state(gold)
    try:
        receipt = parse_state_response(text)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(parsed=None, parse_error=str(exc), parse_valid=False,
                    exact_match=False, parser_version=VERSION)
    return dict(parsed=receipt['state'], parse_error=None, parse_valid=True,
                exact_match=receipt['state'] == expected,
                **{k: v for k, v in receipt.items() if k != 'state'})


def encode_state_v2(processor, public_request, *, task_prompt, target=None,
                    end_turn=False):
    """Shared train/dev state entrypoint. Answer/CoT interfaces are untouched."""
    from model_io_verified import encode
    if target is not None:
        # Do not rewrite gold, targets, supervision, or target token lengths.
        parse_state_v1(target)
    batch, receipt = encode(processor, public_request, target=target,
                            task_prompt=state_prompt_v2(task_prompt),
                            end_turn=end_turn)
    receipt['state_interface_version'] = VERSION
    receipt['target_serialization'] = 'unchanged_canonical_fields_v1'
    return batch, receipt
