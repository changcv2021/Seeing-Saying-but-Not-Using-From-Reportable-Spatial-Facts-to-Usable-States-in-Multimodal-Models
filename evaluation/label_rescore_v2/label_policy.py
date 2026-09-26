"""No gold, model identity, world, or expected answer enters this parser."""
import hashlib
import json
import re
from config import LEGACY
from common import LABELS
from output_policy import parse_prediction as legacy_parse, normalize_outer_fence

VERSION = 'observed_first_label_v2'
POLICY = {
    'version': VERSION,
    'scope': 'Primary label metrics only; original JSON compliance is unchanged.',
    'registration': 'POST_HOC_USER_AUTHORIZED_CORRECTION_NOT_ORIGINAL_PREREGISTRATION',
    'preserve': 'Preserve every label already identified by the frozen parser.',
    'recovery': 'At response start after existing outer-fence normalization, require an object '
                'whose first field is literal label with a completely closed quoted uppercase '
                'SUPPORTED/CONTRADICTORY/UNKNOWN value, followed by whitespace, comma, brace, or EOF.',
    'ambiguity': 'Reject recovery if another quoted label key occurs, including Unicode-escaped key names; '
                 'reject an additional unquoted label key. Do not search reasoning text for answers.',
    'termination': 'Same recovery for eos, stop, and length. Only retained <=512 output tokens are considered.',
    'no_completion': 'Do not append braces, invent confidence/reason, or claim malformed raw JSON is valid.',
    'comparison': 'Apply identical policy to both seeds of all five methods and the same-test base model.',
    'denominator': 'All 5608 inputs and all original complete binary pairs remain in the denominator.',
    'no_tuning': 'Freeze once before revised scoring; no selection by corrected test accuracy.',
}
HEADER = re.compile(r'^\s*\{\s*"label"\s*:\s*"(?P<label>SUPPORTED|CONTRADICTORY|UNKNOWN)"(?=$|\s|[,}])')
QUOTED_KEY = re.compile(r'(?<!\\)"(?P<body>(?:\\.|[^"\\])*)"\s*:')
UNQUOTED_LABEL = re.compile(r'(?<![\w"\\])\blabel\s*:', re.IGNORECASE)


def parse_observed(row):
    # Explicit input projection: callers may carry gold metadata, but it is never
    # exposed to the parsing rule or used to select an answer.
    evidence = {k: row.get(k) for k in ('raw_response', 'finish_reason', 'error', 'generated_tokens') if k in row}
    evidence.setdefault('raw_response', '')
    result = legacy_parse(evidence)
    old_label = None if evidence.get('error') else result['label']
    result.update(legacy_label=old_label, label=old_label, label_recovered_v2=False,
                  label_policy_version=VERSION, label_source='LEGACY' if old_label else 'UNRESOLVED',
                  recovery_reject=None, label_evidence_span=None)
    if evidence.get('error'):
        result['recovery_reject'] = 'RUNTIME_ERROR'
        return result
    if old_label is not None:
        return result
    text, _ = normalize_outer_fence(evidence['raw_response'], evidence.get('finish_reason') == 'length')
    match = HEADER.match(text)
    if not match:
        result['recovery_reject'] = 'NO_COMPLETE_FIRST_LABEL_FIELD'
        return result
    keys = []
    for token in QUOTED_KEY.finditer(text):
        try:
            decoded = json.loads('"' + token['body'] + '"')
        except ValueError:
            continue
        if decoded == 'label':
            keys.append(token.start())
    if len(keys) != 1 or UNQUOTED_LABEL.search(text[match.end():]):
        result['recovery_reject'] = 'ADDITIONAL_LABEL_KEY_AMBIGUOUS'
        return result
    label = match['label']
    start, end = match.span('label')
    if text[start:end] != label or label not in LABELS:
        raise AssertionError('UNOBSERVED_LABEL')
    result.update(label=label, label_recovered_v2=True, label_source='EXPLICIT_FIRST_LABEL_FIELD',
                  label_evidence_span=dict(coordinates='EXISTING_FENCE_NORMALIZED_RESPONSE',
                                           start=start, end=end, observed=text[start:end],
                                           normalized_sha256=hashlib.sha256(text.encode()).hexdigest()))
    # schema_valid / strict_json_valid / reason / confidence remain the legacy
    # observations. In particular, recovering a label never marks JSON valid.
    return result
