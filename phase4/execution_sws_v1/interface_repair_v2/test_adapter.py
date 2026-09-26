"""Setup-only regression coverage for every current SWS output schema."""
import copy
import json
import unittest
from adapter import normalize


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.count=dict(kind='value',domain='count',nullable=True)
        self.enum=dict(kind='value',domain='enum',values=['YES','NO'],nullable=True)
        self.facts=dict(self.count,kind='facts',query_ids=['q1','q2'])
        self.enumfacts=dict(self.enum,kind='facts',query_ids=['q1','q2'])
        self.joint=dict(self.count,kind='joint',order=['value','verdict'])
        self.verdict=dict(self.count,kind='verdict')

    def check(self,text,schema,valid=True):
        before=copy.deepcopy(schema);r=normalize(text,schema)
        self.assertEqual(schema,before);self.assertEqual(r['normalized']['status']=='VALID',valid)
        again=normalize(r['canonical_text'],schema)
        self.assertEqual(again['canonical_text'],r['canonical_text'])
        self.assertEqual(again['normalized']['component_values'],r['normalized']['component_values'])
        return r

    def test_valid_all_schemas_preserved(self):
        four=dict(self.facts,query_ids=['q0','qA','qB','qP'])
        for text,s in [('{"value":2}',self.count),('{"value":"YES"}',self.enum),('{"value":null}',self.enum),
            ('{"verdict":"UNKNOWN"}',self.verdict),('{"value":2,"verdict":"SUPPORTED"}',self.joint),
            ('{"facts":[{"query_id":"q1","value":2},{"query_id":"q2","value":null}]}',self.facts),
            ('{"facts":[{"query_id":"q1","value":"NO"},{"query_id":"q2","value":null}]}',self.enumfacts),
            (json.dumps({'facts':[{'query_id':q,'value':i} for i,q in enumerate(four['query_ids'])]}),four)]:
            with self.subTest(text=text):
                r=self.check(text,s);self.assertEqual(r['canonical_text'],text);self.assertFalse(r['changed'])

    def test_fences(self):
        for lang in ('json',''):
            r=self.check('```'+lang+'\n{"value":2}\n```',self.count)
            self.assertEqual(r['normalized']['component_values'],{'value':2})

    def test_one_closing_brace(self):
        r=self.check('{"facts":[{"query_id":"q1","value":3},{"query_id":"q2","value":1}]',self.facts)
        self.assertEqual(r['normalized']['component_values'],{'facts':{'q1':3,'q2':1}})

    def test_period(self):
        self.check('{"value":2}.',self.count)
        self.check('{"value":2}..',self.count,False)

    def test_null_scalar_and_enum(self):
        for s in (self.count,self.enum):
            r=self.check('{"value":"null"}',s);self.assertIsNone(r['normalized']['component_values']['value'])
        self.check('{"value":"null"}',dict(self.enum,nullable=False),False)

    def test_combined_and_nested_null(self):
        text='```json\n{"facts":[{"query_id":"q1","value":"NO"},{"query_id":"q2","value":"null"}]\n```'
        r=self.check(text,self.enumfacts);self.assertEqual(len(r['operations']),3)
        self.assertEqual(r['normalized']['component_values'],{'facts':{'q1':'NO','q2':None}})

    def test_order_not_rewritten(self):
        r=self.check('```json\n{"verdict":"SUPPORTED","value":2}\n```',self.joint)
        self.assertEqual(r['normalized']['actual_key_order'],['verdict','value']);self.assertFalse(r['normalized']['order_compliant'])

    def test_no_answer_selection(self):
        for t in ['{"value":2} {"value":3}','Answer: {"value":2}','```json\n{"value":2}\n```\nExplanation',
                  '```json\n{"value":2}\n```\n```json\n{"value":3}\n```']:
            with self.subTest(text=t):self.check(t,self.count,False)

    def test_duplicate_keys_and_queries_rejected(self):
        for t,s in [('{"value":2,"value":3}',self.count),('```json\n{"value":2,"value":3}\n```',self.count),
                    ('{"facts":[{"query_id":"q1","value":2},{"query_id":"q1","value":3}]',self.facts)]:
            with self.subTest(text=t):self.check(t,s,False)

    def test_numeric_bool_and_case_not_coerced(self):
        for literal in ('"2"','true','2.0','-1','NaN','Infinity'):
            with self.subTest(value=literal):self.check('{"value":'+literal+'}',self.count,False)
        for literal in ('"yes"','"NULL"','"Unknown"'):
            with self.subTest(value=literal):self.check('{"value":'+literal+'}',self.enum,False)

    def test_no_missing_field_or_value_completion(self):
        for t,s in [('{"value":',self.count),('{"value":2',self.count),('{"value":"YE',self.enum),
                    ('{"facts":[{"query_id":"q1","value":2}]',self.facts),
                    ('{"facts":[{"query_id":"q1","value":2},{"query_id":"q2","value":',self.facts),
                    ('{"verdict":"null"}',self.verdict),('{"value":2,"reason":"x"}',self.count)]:
            with self.subTest(text=t):self.check(t,s,False)

    def test_existing_alias_retained(self):
        r=self.check('{"query_value":2}',self.count);self.assertEqual(r['normalized']['component_values'],{'value':2})
        self.check('{"value":2,"query_value":2}',self.count,False)

    def test_complete_string_not_partial(self):
        self.check('{"value":"YES"',self.enum)
        self.check('{"value":"YES',self.enum,False)

    def test_gold_not_an_argument(self):
        import inspect
        self.assertEqual(list(inspect.signature(normalize).parameters),['text','schema'])


if __name__=='__main__':unittest.main(verbosity=2)
