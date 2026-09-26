"""Engineering and contract tests; no model correctness threshold."""
import unittest
import tempfile
import subprocess
from v3common import *
from score_v3 import parse,score,adapter_selftest
from pipeline_v3 import fingerprint,generated_suffix
from contracts_v3 import VALUE_SCHEMA,ACTION_SCHEMA,SCALAR,joint_text


class ContractTests(unittest.TestCase):
    def test_original_adapter_and_scorer(self):
        self.assertEqual(adapter_selftest(),dict(status='PASS',legacy_tests=18,new_tests=29))

    def test_scalar_alias_same_value_wrong_value_stays_wrong(self):
        r=dict(raw_response='{"query_value":3}')
        g=dict(schema=VALUE_SCHEMA,expected=2)
        out=score(r,g)
        self.assertFalse(out['correct']); self.assertEqual(out['pred'],3)
        self.assertFalse(out['strict_contract_ok']); self.assertTrue(out['extractable_valid'])
        self.assertEqual(r,dict(raw_response='{"query_value":3}'))

    def test_nullable_not_a_gold_dependent_contract(self):
        for expected in [None,0,2]:
            out=score(dict(raw_response='{"value":null}'),dict(schema=VALUE_SCHEMA,expected=expected))
            self.assertEqual(out['status'],'NULL'); self.assertEqual(out['correct'],expected is None)

    def test_reject_wrong_types_extra_conflicting_duplicate_keys(self):
        for text in ['{"value":true}','{"value":"2"}','{"value":2.0}','{"value":-1}',
                     '{"value":2,"query_value":2}','{"query_value":2,"reason":"x"}',
                     '{"value":2,"value":2}','The value is 2']:
            self.assertEqual(parse(dict(raw_response=text),VALUE_SCHEMA)['status'],'INVALID',text)

    def test_truncated_fields_only(self):
        for text,valid in [('{"query_value":12',False),('{"query_value":12,',True),('{"value":12e',False)]:
            self.assertEqual(parse(dict(raw_response=text,truncated=True),VALUE_SCHEMA)['extractable_valid'],valid)

    def test_suffix_slicing(self):
        ids,discarded=generated_suffix([10,11,12,80,81],3,512)
        self.assertEqual((ids,discarded),([80,81],0))
        ids,discarded=generated_suffix([42]*20+list(range(600)),20,512)
        self.assertEqual(ids,list(range(512))); self.assertEqual(discarded,88)

    def test_actions_nullable_and_exact_category(self):
        out=parse(dict(raw_response='{"operation":"ADD","target":null,"amount":null}'),ACTION_SCHEMA)
        self.assertEqual(out['status'],'VALID_ACTION')
        g=dict(schema=ACTION_SCHEMA,expected=dict(operation='ADD',target='table',amount=1))
        out=score(dict(raw_response='{"operation":"ADD","target":"tables","amount":1}'),g)
        self.assertFalse(out['correct']); self.assertFalse(out['component_scores']['target'])
        self.assertEqual(out['entity_grounding'],'NOT_MEASURED')

    def test_infra_and_not_run_are_not_accuracy_false(self):
        g=dict(schema=VALUE_SCHEMA,expected=2)
        self.assertIsNone(score(None,g)['correct'])
        self.assertIsNone(score(dict(raw_response='',infrastructure_error='OOM'),g)['correct'])

    def test_joint_only_report_order_changes(self):
        a=joint_text(['PRE','POST']).replace('order: PRE, POST.','order: <ORDER>.')
        b=joint_text(['POST','PRE']).replace('order: POST, PRE.','order: <ORDER>.')
        self.assertEqual(a,b)
        sch=dict(kind='joint',domain='count',nullable=True,keys=['PRE','POST'])
        g=dict(schema=sch,expected={'PRE':1,'POST':2})
        self.assertTrue(score(dict(raw_response='{"POST":2,"PRE":1}'),g)['correct'])
        self.assertFalse(score(dict(raw_response='{"PRE":2,"POST":1}'),g)['correct'])

    def test_visual_hash_excludes_text_and_detects_pixel_changes(self):
        import torch
        base=dict(pixel_values=torch.tensor([[1.,2.]]),image_grid_thw=torch.tensor([[1,1,1]]),input_ids=torch.tensor([[1,2]]),attention_mask=torch.tensor([[1,1]]),mm_token_type_ids=torch.tensor([[0,1]]))
        changed=dict(base,mm_token_type_ids=torch.tensor([[0,0,1]]),input_ids=torch.tensor([[1,2,3]]))
        a=fingerprint(base); b=fingerprint(changed)
        self.assertEqual(a['presentation_hash'],b['presentation_hash']); self.assertNotEqual(a['text_auxiliary'],b['text_auxiliary'])
        changed['pixel_values']=torch.tensor([[1.,3.]])
        self.assertNotEqual(a['presentation_hash'],fingerprint(changed)['presentation_hash'])
        with self.assertRaises(ValueError): fingerprint(dict(base,mystery=torch.tensor([1])))

    def test_gold_guard_blocks_open_in_child(self):
        program='from pipeline_v3 import install_gold_guard; a=install_gold_guard(); open("/tmp/private_gold/forbidden.json")'
        r=subprocess.run([sys.executable,'-c',program],capture_output=True,text=True)
        self.assertNotEqual(r.returncode,0); self.assertIn('INFERENCE_PRIVATE_GOLD_READ_FORBIDDEN',r.stderr)


def validate_design(root):
    import re
    records=list(rows(root/'review/draft_requests.jsonl')); truth={g['request_id']:g for g in rows(root/'private_gold/core_draft.jsonl')}
    assert len(records)==len(truth)==319
    grouped={}
    for r in records:
        grouped.setdefault(r['group_id'],[]).append(r)
        assert set(r['payload'])=={'system','text','media'}
        if r['schema']['kind']=='value': assert r['schema']['nullable'] and r['payload']['text'].endswith(SCALAR)
        if r['payload']['media']:
            assert ': query_count = ' not in r['payload']['text'] and 'Initial facts:' not in r['payload']['text']
        assert 'expected' not in r and 'values' not in r and 'claim_type' not in r
    target_pairs=0; sham_pairs=0
    for gid,rr in grouped.items():
        level=rr[0]['level']; assert len(rr)==(37 if level=='L4' else 12)
        for cond in ['SELECT_MEDIA','SELECT_MEDIA_OBJECT','ORACLE_MULTI']:
            pair=[r for r in rr if r['condition']==cond]
            if not pair: continue
            assert len(pair)==2
            clean=[re.sub(r'TARGET_(STATE|OBJECT): \S+',r'TARGET_\1: <TARGET>',r['payload']['text']) for r in pair]
            assert clean[0]==clean[1] and pair[0]['payload']['media']==pair[1]['payload']['media']
            assert truth[pair[0]['request_id']]['expected']!=truth[pair[1]['request_id']]['expected']
            target_pairs+=1
        for r in [r for r in rr if r['condition']=='ORACLE_MULTI']:
            s=next(s for s in rr if s['condition']=='ORACLE_SHAM' and s['target']==r['target'])
            # Only the non-target row's variable name changes, not the explanatory header.
            lines=s['payload']['text'].splitlines()
            lines=[line.replace(': unrelated_register =',': query_count =') if ': unrelated_register =' in line else line for line in lines]
            assert '\n'.join(lines)==r['payload']['text']; sham_pairs+=1
        for r in [r for r in rr if r['condition']=='CLAIM_ORACLE_MISSING']:
            g=truth[r['request_id']]; assert g['expected']=='UNKNOWN'
            assert {w['claim_true'] for w in g['witnesses']}=={True,False}
        if level=='L4':
            assert len([r for r in rr if r['condition']=='SELECT_MEDIA'])==2
            assert len([r for r in rr if r['condition']=='CLAIM_MEDIA'])==6
            assert len([r for r in rr if r['condition']=='CLAIM_ORACLE'])==6
    return dict(status='PASS',requests=319,worlds=len(grouped),target_only_pairs=target_pairs,matched_sham_pairs=sham_pairs,
                nullable_fixed=True,media_oracle_separated=True,unknown_witnesses_checked=True)


if __name__=='__main__': unittest.main()
