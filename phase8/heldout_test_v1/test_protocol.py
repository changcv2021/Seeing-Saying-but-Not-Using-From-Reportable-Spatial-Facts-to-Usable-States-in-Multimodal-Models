import unittest
from settings import *
from output_policy import parse_prediction, generation_metadata


class TestProtocol(unittest.TestCase):
    def test_eight_predeclared_adapters(self):
        self.assertEqual(len(KEYS), 8)
        self.assertFalse(any(k.startswith('pss_full') for k in KEYS))

    def test_partition_exhaustive(self):
        parts = [set(range(i, N_TEST, SHARDS)) for i in range(SHARDS)]
        self.assertTrue(all(len(part) == 1402 for part in parts))
        self.assertEqual(len(set.union(*parts)), N_TEST)
        self.assertEqual(sum(map(len, parts)), N_TEST)

    def test_complete_answer(self):
        row = {'raw_response': '{"label":"SUPPORTED","confidence":0.9,"reason":"Visible relation."}'}
        parsed = parse_prediction(row)
        self.assertEqual(parsed['label'], 'SUPPORTED')
        self.assertTrue(parsed['schema_valid'])

    def test_retained_prefix_is_scored(self):
        row = dict(raw_response='{"label":"CONTRADICTORY","confidence":0.9,"reason":"The spatial',
                   finish_reason='length', generated_tokens=512)
        self.assertEqual(parse_prediction(row)['label'], 'CONTRADICTORY')

    def test_do_not_guess_from_reason(self):
        row = dict(raw_response='The answer is SUPPORTED', finish_reason='length', generated_tokens=512)
        self.assertIsNone(parse_prediction(row)['label'])

    def test_pair_metric(self):
        rows = [dict(gold=g, label=g, component='binary', pair_id='pair')
                for g in ('SUPPORTED', 'CONTRADICTORY')]
        self.assertEqual(metrics(rows)['pair_accuracy'], 1.)
        rows[1]['label'] = None
        self.assertEqual(metrics(rows)['pair_accuracy'], 0.)
        self.assertEqual(metrics(rows)['claim_accuracy'], .5)

    def test_output_budget(self):
        self.assertEqual(generation_metadata(512, 12, [13])['finish_reason'], 'length')
        with self.assertRaises(ValueError):
            generation_metadata(513, 12, [13])


if __name__ == '__main__':
    unittest.main()
