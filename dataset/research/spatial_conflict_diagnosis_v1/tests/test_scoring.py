import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from diaglib import LABELS, parse_label, pair_metrics, unique, all_premises

class Scoring(unittest.TestCase):
    def test_pairs(self):
        for s, c, expected in [('SUPPORTED','CONTRADICTORY',1),('SUPPORTED','UNKNOWN',0),('UNKNOWN','UNKNOWN',0),('INVALID','CONTRADICTORY',0)]:
            rr = [dict(sample_id='s', pair_id='p', gold='SUPPORTED', pred=s),dict(sample_id='c', pair_id='p', gold='CONTRADICTORY', pred=c)]
            self.assertEqual(pair_metrics(rr)['pair_accuracy'], expected)
    def test_explanation_does_not_score_label(self):
        self.assertEqual(parse_label('{"label":"SUPPORTED","explanation":"wrong"}'), 'SUPPORTED')
        self.assertEqual(parse_label('{"explanation":"SUPPORTED"}'), 'INVALID')
    def test_duplicate_label(self):
        self.assertEqual(parse_label('{"label":"SUPPORTED","label":"UNKNOWN"}'), 'INVALID')
        self.assertEqual(parse_label('{"label":"SUPPORTED","label":"UNKNOWN","reason":"', True), 'INVALID')
    def test_truncation(self):
        self.assertEqual(parse_label('{"label":"SUPPORTED","explanation":"unfinished', True), 'SUPPORTED')
        self.assertEqual(parse_label('{"label":"SUPPOR', True), 'INVALID')
        self.assertEqual(parse_label('{"explanation":"label: SUPPORTED', True), 'INVALID')
    def test_fences(self):
        self.assertEqual(parse_label('```json\n{"label":"UNKNOWN"}\n```'), 'UNKNOWN')
        self.assertEqual(parse_label('prose {"label":"UNKNOWN"}'), 'INVALID')
    def test_duplicates_hard_failure(self):
        with self.assertRaises(ValueError): unique([{'id':1},{'id':1}], 'id')
    def test_mapping(self):
        for order in itertools.permutations(LABELS):
            mapping = dict(zip('ABC', order))
            for code in 'ABC': self.assertEqual(parse_label('{"code":"'+code+'"}', mapping=mapping, field='code'), mapping[code])
    def test_empty_facts(self):
        self.assertIsNone(all_premises([]))
        self.assertFalse(all_premises([True,False]))
    def test_no_unknown_on_failure(self):
        self.assertEqual(parse_label(''), 'INVALID')

if __name__ == '__main__': unittest.main()
