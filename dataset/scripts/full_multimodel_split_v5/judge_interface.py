"""Explicit user-approved auxiliary judge output contract; not candidate parsing."""
import json
from pathlib import Path
from common import sha
INTERFACE_PATH=Path(__file__).with_name('judge_interface.json')
INTERFACE=json.loads(INTERFACE_PATH.read_text())
VERSION=INTERFACE['version']
INTERFACE_SHA256=sha(INTERFACE_PATH)
MAX_NEW_TOKENS=INTERFACE['max_new_tokens']
def judgment_valid(obj,criterion,reason):
    if not isinstance(obj,dict) or set(obj)!={'criterion_id','met','evidence'}:return False
    if obj['criterion_id']!=criterion or type(obj['met']) is not bool or not isinstance(obj['evidence'],str):return False
    evidence=obj['evidence']
    return (evidence in reason and INTERFACE['evidence_min_nonwhitespace_chars'] <= len(''.join(evidence.split())) <= INTERFACE['evidence_max_nonwhitespace_chars']) if obj['met'] else evidence==''
