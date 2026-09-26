"""Score only emitted tokens. Never infer a label or finish a truncated reason."""
import json
import re
from common import parse, LABELS

TOKEN_LIMIT = 512
POLICY_VERSION = 'retained_prefix_512_v1'
NORMALIZATION_VERSION = 'outer_json_fence_v1'

def normalize_outer_fence(raw, truncated=False):
    """Remove one whole-response JSON fence, not embedded blocks or prose."""
    text=raw.strip()
    match=re.fullmatch(r'```(?:json)?[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n```[ \t]*',text,re.IGNORECASE)
    if match:
        return match.group('body').strip(), True
    # A hard token cutoff can remove the closing fence along with the JSON tail.
    opener=re.match(r'```(?:json)?[ \t]*\r?\n',text,re.IGNORECASE)
    if truncated and opener:
        body=text[opener.end():]
        # Discard an incomplete closing fence only after a complete JSON object.
        tail=re.fullmatch(r'([\s\S]*})\s*`{1,2}',body)
        if tail and parse(tail.group(1))['strict_json_valid']: body=tail.group(1)
        return body.strip(), True
    return raw, False

def generation_metadata(count, last_token, eos_ids, original_count=None):
    if not 0 <= count <= TOKEN_LIMIT:
        raise ValueError('RETAINED_OUTPUT_EXCEEDS_512')
    original_count = count if original_count is None else original_count
    ended = count > 0 and last_token in set(eos_ids)
    truncated = original_count > TOKEN_LIMIT or (count == TOKEN_LIMIT and not ended)
    return dict(generated_tokens=count, output_cap_hit=count == TOKEN_LIMIT,
                ended_with_eos=ended, finish_reason='length' if truncated else 'eos' if ended else 'stop',
                discarded_tokens=max(0, original_count-count), max_new_tokens=TOKEN_LIMIT,
                scoring_policy=POLICY_VERSION)

def _string(text, pos):
    """Read a JSON string; on EOF return only complete literal/escape characters."""
    if text[pos] != '"': raise ValueError('EXPECTED_STRING')
    pos += 1; out=[]
    escapes={'"':'"', '\\':'\\', '/':'/', 'b':'\b', 'f':'\f', 'n':'\n', 'r':'\r', 't':'\t'}
    while pos < len(text):
        c=text[pos]
        if c == '"': return ''.join(out), pos+1, True
        if ord(c) < 32: raise ValueError('INVALID_STRING_CONTROL')
        if c != '\\': out.append(c); pos+=1; continue
        pos+=1
        if pos == len(text): return ''.join(out), pos, False
        c=text[pos]
        if c in escapes: out.append(escapes[c]); pos+=1; continue
        if c != 'u': raise ValueError('INVALID_ESCAPE')
        digits=text[pos+1:pos+5]
        if any(d not in '0123456789abcdefABCDEF' for d in digits): raise ValueError('INVALID_UNICODE_ESCAPE')
        if len(digits) < 4: return ''.join(out), len(text), False
        out.append(chr(int(digits,16))); pos+=5
    return ''.join(out), pos, False

def _prefix_fields(text):
    """Parse top-level schema fields, without extracting labels inside reason text."""
    text=text.strip(); fields={}; complete=[]; partial_reason=False
    if not text.startswith('{'): raise ValueError('PREFIX_NOT_OBJECT')
    i=1
    def ws(p):
        while p<len(text) and text[p].isspace(): p+=1
        return p
    while True:
        i=ws(i)
        if i==len(text): break
        if text[i]=='}':
            if text[i+1:].strip(): raise ValueError('TRAILING_TEXT')
            break
        key,i,closed=_string(text,i)
        if not closed: break
        if key not in {'label','confidence','reason'}: raise ValueError('UNKNOWN_FIELD')
        if key in complete: raise ValueError('DUPLICATE_FIELD')
        i=ws(i)
        if i==len(text): break
        if text[i]!=':': raise ValueError('MISSING_COLON')
        i=ws(i+1)
        if i==len(text): break
        if text[i]=='"':
            value,i,closed=_string(text,i)
            if not closed:
                if key=='reason': fields[key]=value; partial_reason=True
                break
        else:
            # Numeric confidence is accepted only with an emitted delimiter.
            try: value,end=json.JSONDecoder().raw_decode(text,i)
            except ValueError: break
            if end==len(text): break
            if text[end] not in ',} \t\r\n':
                if re.fullmatch(r'-?(?:0|[1-9]\d*)(?:\.\d*)?(?:[eE][+-]?\d*)?',text[i:]): break
                raise ValueError('INVALID_VALUE_SUFFIX')
            i=end
        fields[key]=value; complete.append(key); i=ws(i)
        if i==len(text): break
        if text[i]=='}':
            if text[i+1:].strip(): raise ValueError('TRAILING_TEXT')
            break
        if text[i]!=',': raise ValueError('MISSING_COMMA')
        i+=1
    return fields, complete, partial_reason

def parse_prediction(row):
    original=row.get('raw_response','')
    raw,removed=normalize_outer_fence(original,row.get('finish_reason')=='length')
    result=parse(raw); normalized_valid=result['strict_json_valid']
    result.update(prefix_recovered=False, partial_reason=False, scoring_policy=POLICY_VERSION,
                  normalization_version=NORMALIZATION_VERSION,fence_removed=removed,
                  normalized_json_valid=normalized_valid,strict_json_valid=parse(original)['strict_json_valid'])
    if row.get('generated_tokens',0)>TOKEN_LIMIT: raise ValueError('UNBOUNDED_OUTPUT_IN_SCORE')
    if normalized_valid or row.get('finish_reason')!='length' or row.get('error'):
        return result
    try: fields,complete,partial=_prefix_fields(raw)
    except ValueError:
        result['prefix_reject_code']='MALFORMED_NOT_JUST_TRUNCATED'
        return result
    # Reuse field validation, NOT its schema-valid flag, on observed fields only.
    observed=parse(json.dumps(fields))
    result.update(label=observed['label'],confidence=observed['confidence'],reason=observed['reason'],
                  prefix_recovered=bool(complete or partial),partial_reason=partial,
                  observed_complete_fields=complete,prefix_reject_code=None)
    return result

def gate_usable(parsed, row):
    return bool(parsed['schema_valid'] or (row.get('finish_reason')=='length' and
                parsed['prefix_recovered'] and parsed['label'] in LABELS))
