"""Engineering fixtures only: never read model raw/core responses or write fake predictions."""
import json
import unittest
from copy import deepcopy
from v3common import CODE,load,rows,csvrows
from score_v3 import score
from cluster_stats import estimate
from analyze import (coverage,cohorts,controls,diagnostic_matrix,component_summaries,
                     condition_summary,conditional_summary,claim_summary,pair_pattern)


class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=load(CODE/'config.json'); root=__import__('pathlib').Path(cls.c['root'])
        cls.cards={r['group_id']:r for r in rows(root/'review/candidate_panel.jsonl')}
        cls.review={r['group_id']:r for r in csvrows(root/'review/researcher_records.csv')}
        cls.cohort=cohorts(cls.cards,cls.review)
        requests=list(rows(root/'review/draft_requests.jsonl'))
        gold={r['request_id']:r for r in rows(root/'private_gold/core_draft.jsonl')}
        selected=set(load(root/'manifest/reviewed_core_plan.json')['request_ids'])
        cls.matches=list(rows(root/'manifest/reviewed_matched_controls.jsonl')); cls.fixture=[]
        for model in cls.c['models']:
            for req in requests:
                g=deepcopy(gold[req['request_id']]); eligible=req['request_id'] in selected
                g['condition_eligible']=eligible; kind=req['schema']['kind']
                text={'value':g['expected']} if kind=='value' else {'label':g['expected']} if kind=='verdict' else g['expected']
                raw={'raw_response':json.dumps(text),'truncated':False,'ENGINEERING_FIXTURE_NOT_ACTUAL_MODEL':True} if eligible else None
                s=score(raw,g); card=cls.cards[req['group_id']]
                cls.fixture.append(dict(model=model,request_id=req['request_id'],group_id=req['group_id'],
                    underlying_world_id=req['underlying_world_id'],condition=req['condition'],target=req['target'],variant=req['variant'],
                    schema=req['schema'],level=card['level'],stratum=card['stratum'],source_values=card['values'],
                    condition_eligible=eligible,raw_record=raw,raw_path=None,execution_status='RESPONDED' if eligible else 'NOT_ELIGIBLE',
                    parse_status=s['status'] if eligible else 'NOT_ELIGIBLE',prediction=s['pred'],score=s,correct=s['correct'],
                    strict_contract_ok=s['strict_contract_ok'],normalization=s['normalization'],input_tokens=100,
                    presentation_hash='ENGINEERING_FIXTURE_NOT_REAL_PRESENTATION',media=req['payload']['media'],gold=g['expected'],
                    claim_type=g.get('claim_type'),claim_value=g.get('claim_value')))

    def test_cluster_repeated_items_not_independent_worlds(self):
        a=estimate([('w1',1,1),('w2',0,1)],['w1','w2'])
        b=estimate([('w1',1,1)]*10+[('w2',0,1)]*10,['w1','w2'])
        for k in ['estimate','ci95_low','ci95_high','world_macro']:
            self.assertEqual(a[k],b[k])
        self.assertEqual(a['cohort_worlds'],2)

    def test_empty_and_conditional_denominators(self):
        empty=estimate([],['w1','w2'])
        self.assertIsNone(empty['estimate']); self.assertEqual(empty['bootstrap_empty_denominator_fraction'],1)
        conditional=estimate([('w1',1,1)],['w1','w2'])
        self.assertGreater(conditional['bootstrap_empty_denominator_fraction'],0)
        self.assertIn('DEGENERATE',conditional['ci_limitation'])

    def test_full_fixture_coverage(self):
        for m in self.c['models']:
            n=coverage([r for r in self.fixture if r['model']==m])
            self.assertEqual((n['N_planned'],n['N_responses'],n['N_correct'],n['N_not_eligible']),(312,312,312,7))

    def test_unrun_not_zero_accuracy(self):
        rr=deepcopy(self.fixture[:1]); rr[0].update(execution_status='NOT_RUN',raw_record=None,correct=None,parse_status='NOT_RUN')
        n=coverage(rr)
        self.assertEqual(n['N_not_run'],1); self.assertIsNone(n['response_accuracy'])

    def test_control_fixture_no_harm_or_intrusion(self):
        pairs,summary=controls(self.fixture,self.matches,self.cards,self.cohort)
        self.assertEqual(len(pairs),576)
        self.assertTrue(all(r['net']==0 for r in pairs))
        self.assertTrue(all(r['intrusion_excess'] in [0,None] for r in pairs))
        self.assertTrue(all(r['tracking'] in [0,None] for r in pairs))

    def test_matrix_and_separate_l1_contract(self):
        matrix,pairs,conditional,transitions=diagnostic_matrix(self.fixture,self.cards,self.review,self.matches,self.cohort)
        self.assertEqual(len(matrix),48); self.assertEqual(len(pairs),72); self.assertEqual(len(transitions),21)
        active=[r for r in matrix if r['review_status']=='VERIFIED_FOR_A1']
        self.assertEqual(len(active),36)
        self.assertTrue(all(r['media_target_pair_correct'] and r['oracle_target_pair_correct'] for r in active))
        self.assertTrue(all(not r['failure_candidate_tags_json'] for r in active))
        self.assertTrue(all('pre_gold' not in r and 'action_request_id' not in r for r in active if r['level']=='L1'))
        self.assertTrue(all(r['consistent'] for r in transitions))
        summary=conditional_summary(conditional,self.cohort,self.c['models'])
        self.assertTrue(all(r['estimate'] in [0,None] for r in summary))
        self.assertTrue(component_summaries(self.fixture,matrix,self.cohort))

    def test_null_invalid_swap_are_distinct(self):
        a=dict(execution_status='RESPONDED',parse_status='VALUE',prediction=0)
        b=dict(execution_status='RESPONDED',parse_status='VALUE',prediction=1)
        self.assertEqual(pair_pattern(a,b,{'PRE':1,'POST':0},['PRE','POST']),('SWAPPED',False))
        b.update(parse_status='NULL',prediction=None)
        self.assertEqual(pair_pattern(a,b,{'PRE':1,'POST':0},['PRE','POST']),('NULL',False))
        b.update(parse_status='INVALID')
        self.assertEqual(pair_pattern(a,b,{'PRE':1,'POST':0},['PRE','POST']),('INVALID',False))
        b.update(execution_status='NOT_RUN')
        self.assertIsNone(pair_pattern(a,b,{'PRE':1,'POST':0},['PRE','POST'])[1])

    def test_summary_fixtures_no_model_raw_access(self):
        summary=condition_summary(self.fixture,self.cohort)
        self.assertTrue(all(r['estimate'] in [1,None] for r in summary))
        claims,confusion=claim_summary(self.fixture,self.cohort)
        self.assertTrue(all(r['estimate'] in [1,None] for r in claims if r['metric']=='accuracy'))
        self.assertTrue(all(r['gold']==r['prediction'] for r in confusion))


if __name__=='__main__': unittest.main()
