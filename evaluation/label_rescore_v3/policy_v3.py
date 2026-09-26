"""Gold-blind additive label recovery; all v2 decisions remain reproducible."""
import hashlib
import json
import re
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
V2_CODE = CODE.parent / 'label_rescore_v2'
sys.path.insert(0, str(V2_CODE))
import config as v2_config
import label_policy as v2_policy
from output_policy import normalize_outer_fence

VERSION = 'observed_first_label_v3'
HEADER = re.compile(r'^\s*\{\s*"label"\s*:\s*"(?P<label>SUPPORTED|CONTRADICTORY|UNKNOWN)"')
POLICY = dict(
    version=VERSION,
    registration='POST_HOC_USER_AUTHORIZED_DELIMITER_CORRECTION_NOT_PREREGISTERED',
    change='A completely closed first quoted label is not invalidated by missing subsequent delimiters.',
    preserve='Every label already identified by v2 remains unchanged.',
    recovery='Only a response-initial object with a literal first label key and a fully emitted, '
             'closed uppercase SUPPORTED/CONTRADICTORY/UNKNOWN string. No condition on the next character.',
    ambiguity='Retain v2 additional quoted/unquoted label-key rejection, including escaped keys; '
              'even repeated identical labels are not newly recovered.',
    scope='Primary label metrics only. JSON/schema validity, reason and confidence are unchanged.',
    termination='Same policy for eos/stop/length; only retained <=512 tokens. Never regenerate or complete text.',
    denominator='All original 5608 held-out test inputs and original complete pairs.',
    comparison='Base, both seeds of all five original methods, and both preserved-L4 Full PSS seeds.',
    no_tuning='One freeze before rescoring; no rule selection by accuracy, gold, model, seed or level.',
)


def parse_observed(row):
    # Project away all gold, sample identity, level and model information.
    evidence = {k: row[k] for k in ('raw_response', 'finish_reason', 'error', 'generated_tokens') if k in row}
    evidence.setdefault('raw_response', '')
    result = v2_policy.parse_observed(evidence)
    result.update(v2_label=result['label'], v2_recovery_reject=result['recovery_reject'],
                  label_recovered_v3=False, label_policy_version=VERSION)
    if result['label'] is not None or evidence.get('error'):
        return result
    text, _ = normalize_outer_fence(evidence['raw_response'], evidence.get('finish_reason') == 'length')
    match = HEADER.match(text)
    if not match:
        return result
    keys = []
    for token in v2_policy.QUOTED_KEY.finditer(text):
        try:
            key = json.loads('"' + token['body'] + '"')
        except ValueError:
            continue
        if key == 'label':
            keys.append(token.start())
    if len(keys) != 1 or v2_policy.UNQUOTED_LABEL.search(text[match.end():]):
        result['recovery_reject'] = 'ADDITIONAL_LABEL_KEY_AMBIGUOUS'
        return result
    start, end = match.span('label')
    result.update(label=match['label'], label_recovered_v3=True,
                  label_source='EXPLICIT_FIRST_CLOSED_LABEL_DELIMITER_INDEPENDENT',
                  recovery_reject=None,
                  label_evidence_span=dict(coordinates='EXISTING_FENCE_NORMALIZED_RESPONSE',
                      start=start, end=end, observed=text[start:end],
                      normalized_sha256=hashlib.sha256(text.encode()).hexdigest()))
    return result
