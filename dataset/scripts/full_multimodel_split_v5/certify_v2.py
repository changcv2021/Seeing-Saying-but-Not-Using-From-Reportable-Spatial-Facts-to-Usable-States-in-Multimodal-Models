"""Versioned scorer-only certification; historical blocked gate is immutable."""
import json,os
from orchestration import ROOT,verify_extension,frozen,load,sha
from common import unique
from output_policy import parse_prediction
from judge_v2 import _valid_raw,JUDGE_PROMPT_VERSION
from judge_interface import INTERFACE_SHA256,MAX_NEW_TOKENS
verify_extension()
p=ROOT/'qwen25vl_7b'
gate=json.loads((p/'interface_gate.json').read_text())
judges=load(p/'smoke_judge_v2/judgments_000.jsonl')
preds=unique(load(p/'smoke/predictions_000.jsonl'))
if gate['status']!='PASS' or len(judges)!=96 or {r['sample_id'] for r in judges}!=set(preds):
    raise ValueError('SCORING_CHECK_INCOMPLETE')
invalid=0;attempted=0
for row in judges:
    if row['judge_prompt_version']!=JUDGE_PROMPT_VERSION:raise ValueError('JUDGE_PROMPT_CHANGED')
    if row['judge_interface_sha256']!=INTERFACE_SHA256 or row['judge_max_new_tokens']!=MAX_NEW_TOKENS:raise ValueError('JUDGE_INTERFACE_CHANGED')
    reason=parse_prediction(preds[row['sample_id']]).get('reason') or ''
    for cid,raws in row['attempts'].items():
        if raws:attempted+=1;invalid+=not any(_valid_raw(raw,cid,reason) for raw in raws)
record=dict(status='PASS' if attempted>0 and invalid/attempted<=.05 else 'BLOCKED_JUDGE_INTERFACE',
    candidate_gate=gate,judged_inputs=96,attempted_criteria=attempted,malformed_criteria=invalid,
    no_accuracy_threshold=True,judge_prompt_version=JUDGE_PROMPT_VERSION,
    unchanged_semantic_criteria=True,evidence_max_nonwhitespace_chars=1000,judge_max_new_tokens=MAX_NEW_TOKENS,judge_interface_sha256=INTERFACE_SHA256,old_gate_sha256=sha(ROOT/'SCORING_GATE.json'),
    judgments_sha256=sha(p/'smoke_judge_v2/judgments_000.jsonl'),
    not_proof_all_future_outputs_valid=True,job=os.environ['SLURM_JOB_ID'])
frozen(ROOT/'SCORING_GATE_V2.json',record)
print(json.dumps(record),flush=True)
if record['status']!='PASS':raise ValueError('JUDGE_INTERFACE_BLOCKED_V2_NO_AUTOMATIC_PROMPT_SEARCH')
