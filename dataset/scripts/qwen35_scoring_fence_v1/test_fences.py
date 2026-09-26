import json
import unittest
from copy import deepcopy
from output_policy import parse_prediction, gate_usable
from test_output_policy import PrefixTests

class FenceTests(unittest.TestCase):
    answer='{"label":"SUPPORTED","confidence":0.8,"reason":"The cup is left of the plate."}'
    def row(self,text,finish='eos'):
        return dict(raw_response=text,finish_reason=finish,generated_tokens=512 if finish=='length' else 80,error=None)
    def test_json_fence(self):
        row=self.row('```json\n'+self.answer+'\n```');before=deepcopy(row)
        p=parse_prediction(row)
        self.assertTrue(p['schema_valid']);self.assertTrue(p['fence_removed'])
        self.assertFalse(p['strict_json_valid']);self.assertTrue(p['normalized_json_valid'])
        self.assertEqual(p['label'],'SUPPORTED');self.assertEqual(row,before)
    def test_plain_fence(self):
        self.assertTrue(parse_prediction(self.row('```\n'+self.answer+'\n```'))['schema_valid'])
    def test_case_whitespace(self):
        self.assertTrue(parse_prediction(self.row(' \n```JSON \r\n'+self.answer+'\r\n``` \n'))['schema_valid'])
    def test_bare_unchanged(self):
        p=parse_prediction(self.row(self.answer))
        self.assertTrue(p['strict_json_valid']);self.assertFalse(p['fence_removed'])
    def test_external_prose_rejected(self):
        for text in ['Answer:\n```json\n'+self.answer+'\n```','```json\n'+self.answer+'\n```\nMore prose']:
            self.assertIsNone(parse_prediction(self.row(text))['label'])
    def test_multiple_blocks_rejected(self):
        p=parse_prediction(self.row('```json\n'+self.answer+'\n```\n```json\n'+self.answer+'\n```'))
        self.assertIsNone(p['label'])
    def test_duplicates_still_rejected(self):
        p=parse_prediction(self.row('```json\n{"label":"SUPPORTED","label":"UNKNOWN"}\n```'))
        self.assertIsNone(p['label'])
    def test_wrong_language_not_accepted(self):
        self.assertIsNone(parse_prediction(self.row('```python\n'+self.answer+'\n```'))['label'])
    def test_length_prefix_in_fence(self):
        row=self.row('```json\n{"label":"SUPPORTED","confidence":0.8,"reason":"The cup is left','length')
        p=parse_prediction(row)
        self.assertEqual(p['label'],'SUPPORTED');self.assertEqual(p['reason'],'The cup is left')
        self.assertTrue(gate_usable(p,row))
    def test_missing_close_without_length_not_accepted(self):
        self.assertIsNone(parse_prediction(self.row('```json\n'+self.answer))['label'])
    def test_partial_closing_fence_at_length(self):
        p=parse_prediction(self.row('```json\n'+self.answer+'\n``','length'))
        self.assertTrue(p['schema_valid'])

if __name__=='__main__':unittest.main()
