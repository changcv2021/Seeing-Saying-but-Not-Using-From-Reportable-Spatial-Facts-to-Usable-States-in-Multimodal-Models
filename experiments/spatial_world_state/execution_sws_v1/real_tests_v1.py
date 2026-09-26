import unittest
from common import load, CODE
from real_design_v1 import *
from contracts import parse, legal_count_update


def fixture(predicate='COUNT', subject='class:chairs', value=3, obj=None, polarity='positive'):
    return dict(predicate=predicate,subject=subject,value=value,object=obj,polarity=polarity,
                fact_id=digest([subject,predicate,obj]),derivation=None,
                context={'scope':'reference_frame','state_id':'observed'},provenance={'origin_type':'QA_DIRECT'})


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.c=load(CODE/'config_auto_v2.json')
        self.a=fixture(); self.b=fixture(subject='class:tables',value=2)
        self.panel=dict(world_cluster_id='fixture:world',primary_stratum='COUNT',count_substratum='REMOVE_POST_POSITIVE',facts=[self.a,self.b])
        self.media=[dict(kind='image',path='/fixture/'+role,role=role,sha256='sha256:'+'0'*64) for role in
                    ('reference_frame','support_frame_1','support_frame_2','support_frame_3','support_frame_4')]

    def build(self): return build_world(self.c,self.panel,self.media)

    def test_all_count_substrata(self):
        for sub,n in [('ADD',3),('REMOVE_POST_POSITIVE',3),('REMOVE_POST_ZERO',1),('PROTECTION_NOOP',0)]:
            with self.subTest(sub=sub):
                self.a['value']=n; self.panel['count_substratum']=sub
                rr,gg,mm,aa=self.build()
                self.assertTrue(rr); self.assertEqual(len(rr),len(gg))

    def test_nonzero_remove(self):
        self.assertEqual(branch_spec(self.a,'REMOVE_POST_POSITIVE')['values'],{'S0':3,'SA':2,'SB':6})

    def test_invalid_remove(self):
        with self.assertRaises(ValueError): legal_count_update(0,1,'REMOVE')

    def test_post_not_pre(self):
        self.a['context']['state_id']='post_intervention'; self.assertFalse(qualified_fact(self.a))

    def test_source_only_not_model_gold(self):
        self.a['provenance']['origin_type']='MODEL_PREDICTED'; self.assertFalse(qualified_fact(self.a))

    def test_disjoint_protection(self):
        self.assertTrue(independent_facts(self.a,self.b))
        self.b['subject']='class:chair'; self.assertFalse(independent_facts(self.a,self.b))

    def test_no_gold_payload(self):
        for r in self.build()[0]:
            self.assertEqual(set(r['payload']),{'system','text','media'})
            for forbidden in ('is_false','target_gold','proof','source_record_hash','fact:'):
                self.assertNotIn(forbidden,str(r['payload']))

    def test_target_switch_only(self):
        rr,_,mm,_=self.build(); byid={r['request_id']:r for r in rr}
        pair=next(m for m in mm if m['experiment']=='E4')
        for state in ('SA','SB'):
            x=byid[pair[state]]['payload']; y=byid[pair['S0']]['payload']
            self.assertEqual(x['media'],y['media']); self.assertEqual(x['system'],y['system'])
            self.assertEqual(x['text'].replace('TARGET: '+state,'TARGET: S0').replace('in state '+state+'?','in state S0?'),y['text'])

    def test_evidence_ablation_null(self):
        _,_,_,aa=self.build()
        for a in aa:
            if a['view_variant']=='NO_MEDIA': self.assertEqual(a['logical_gold']['expected'],{'facts':{'q1':None,'q2':None}})

    def test_permutations_bind_reference_role(self):
        rr,_,_,_=self.build(); full=next(r for r in rr if r['view_variant']=='FULL')['payload']['media']
        for r in rr:
            if r['view_variant'].startswith('PERMUTE'):
                self.assertEqual({m['role']:m['path'] for m in r['payload']['media']},{m['role']:m['path'] for m in full})

    def test_order_and_duplicate_parser(self):
        self.assertEqual(parse('{"value":2,"value":3}',schema(self.a))['status'],'INVALID')
        s=schema(self.a,'joint',['verdict','value'])
        p=parse('{"value":2,"verdict":"SUPPORTED"}',s)
        self.assertEqual(p['status'],'VALID'); self.assertFalse(p['order_compliant'])

    def test_truth_refutation_not_absence(self):
        f=fixture('LEFT_OF','mention:chair',None,'mention:table','negative')
        self.assertEqual(fact_value(f),'NO'); self.assertTrue(qualified_fact(f))
        f['polarity']='missing'; self.assertFalse(qualified_fact(f))

    def test_binary_secondary(self):
        self.panel['primary_stratum']='NONCOUNT_RELATION'
        self.panel['facts']=[fixture('LEFT_OF','mention:chair',None,'mention:table'),fixture('BEHIND','mention:sink',None,'mention:door','negative')]
        rr,gg,mm,_=self.build()
        self.assertTrue(all(g['binary_nonidentifying'] for g in gg))
        self.assertFalse(any(r['experiment']=='E4' for r in rr))

    def test_three_e6_claim_types(self):
        m=[m for m in self.build()[2] if m['experiment']=='E6']
        self.assertEqual({r['claim_type'] for r in m},{'TARGET_MATCH','OTHER_STATE','NEITHER_STATE'})

    def test_sham_numeric_match(self):
        rr,_,mm,_=self.build(); d={r['request_id']:r for r in rr}
        for m in mm:
            if m['experiment']=='E2':
                f,s=d[m['false']],d[m['sham']]
                self.assertEqual(f['payload']['media'],s['payload']['media'])
                self.assertEqual(f['schema'],s['schema'])
                self.assertIn(str(m['candidate_value']),f['payload']['text']); self.assertIn(str(m['candidate_value']),s['payload']['text'])

    def test_repeated_build_identical(self):
        self.assertEqual(self.build(),self.build())


if __name__=='__main__': unittest.main()
