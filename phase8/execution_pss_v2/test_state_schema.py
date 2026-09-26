import unittest
from state_schema import *

class TestState(unittest.TestCase):
    def test_all_relation_families(self):
        for pred,var in RELATION_VARIABLES.items():
            s=dict(entities=['entity A','entity B'],variable=var,frame='source_declared',value=pred)
            self.assertEqual(parse_state(serialize_state(s)),s)
    def test_value_types(self):
        for variable,value in [('count',0),('count',12),('existence',True),('visibility',False),('identity',False)]:
            s=dict(entities=['chair'],variable=variable,value=value)
            self.assertEqual(parse_state(serialize_state(s)),s)
    def test_invalid(self):
        for value in [-1,True,1.1,'2']:
            with self.assertRaises(ValueError):serialize_state(dict(entities=['chair'],variable='count',value=value))
    def test_duplicates(self):
        with self.assertRaises(ValueError):parse_state('<STATE>\nentities: ["chair"]\nvariable: "count"\nvalue: 1\nvalue: 2\n</STATE>')
    def test_model_null_and_malformed(self):
        for text in ['', 'null', None, '<STATE>\nvalue: []\n</STATE>']:
            with self.assertRaises(ValueError):parse_state(text)
        for value in [None, [], {}]:
            with self.assertRaises(ValueError):serialize_state(dict(entities=['A','B'],variable='depth_relation',value=value))
if __name__=='__main__':unittest.main()
