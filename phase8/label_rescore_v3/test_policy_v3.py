import unittest
from policy_v3 import parse_observed, v2_policy


class PolicyV3Tests(unittest.TestCase):
    def parse(self, text, finish='eos', **kw):
        return parse_observed(dict(raw_response=text, finish_reason=finish, generated_tokens=50, **kw))

    def test_missing_delimiter_all_labels_and_terminations(self):
        for label in ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN'):
            for finish in ('eos', 'stop', 'length'):
                for tail in ('confidence:0.9"reason":"example"}', '## Reasoning\nExample.',
                             '"confidence":0.9}', 'reason:"example"}', '', '\n', ','):
                    with self.subTest(label=label, finish=finish, tail=tail):
                        text = '{"label":"' + label + '"' + tail
                        got = self.parse(text, finish)
                        self.assertEqual(got['label'], label)
                        old = v2_policy.parse_observed(dict(raw_response=text, finish_reason=finish, generated_tokens=50))
                        for field in ('schema_valid', 'strict_json_valid', 'normalized_json_valid', 'reason', 'confidence'):
                            self.assertEqual(got[field], old[field])

    def test_no_invention(self):
        for text in ('', 'SUPPORTED', 'The answer is UNKNOWN', '{"label":"SUPPOR',
                     '{"label":"SUPPORTED', '{"label":"SUPPORTED|UNKNOWN"confidence:1',
                     '{"reason":"SUPPORTED"', '[{"label":"SUPPORTED"}]',
                     'Example: {"label":"SUPPORTED"}', '{"label":true',
                     '{"label":"supported"', '{"label":"SUPPORTEDNESS"confidence:1'):
            with self.subTest(text=text):
                self.assertIsNone(self.parse(text)['label'])

    def test_duplicate_keys_still_rejected(self):
        for tail in ('"label":"UNKNOWN"}', '"label":"SUPPORTED"}',
                     '\n{"label":"UNKNOWN"}', ',"\\u006cabel":"UNKNOWN"}',
                     '\nlabel: UNKNOWN'):
            with self.subTest(tail=tail):
                got = self.parse('{"label":"SUPPORTED"confidence:0.9' + tail)
                self.assertIsNone(got['label'])
                self.assertEqual(got['recovery_reject'], 'ADDITIONAL_LABEL_KEY_AMBIGUOUS')

    def test_valid_json_and_v2_labels_preserved(self):
        for text in ('{"reason":"UNKNOWN is not chosen","label":"SUPPORTED","confidence":0.8}',
                     '{"label":"UNKNOWN"}', '{"label":"CONTRADICTORY"\n"reason":"incomplete'):
            row = dict(raw_response=text, finish_reason='eos', generated_tokens=50)
            old = v2_policy.parse_observed(row)
            new = parse_observed(row)
            self.assertEqual(new['label'], old['label'])
            self.assertFalse(new['label_recovered_v3'])

    def test_fence_policy_unchanged(self):
        self.assertEqual(self.parse('```json\n{"label":"UNKNOWN"confidence:0.2\n```')['label'], 'UNKNOWN')
        self.assertIsNone(self.parse('```json\n{"label":"UNKNOWN"confidence:0.2')['label'])
        self.assertEqual(self.parse('```json\n{"label":"UNKNOWN"confidence:0.2', 'length')['label'], 'UNKNOWN')

    def test_gold_and_identity_invariance(self):
        row = dict(raw_response='{"label":"UNKNOWN"confidence:0.2', finish_reason='eos', generated_tokens=12)
        expected = parse_observed(row)
        for label in ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN'):
            for model in ('base', 'pss_l4', 'pss_full_l4_preserved'):
                self.assertEqual(parse_observed(dict(row, gold=label, model=model, sample_id='x', level='L4')), expected)

    def test_runtime_errors_and_token_cap(self):
        self.assertIsNone(self.parse('{"label":"SUPPORTED"confidence:0.2', error='RUNTIME_ERROR')['label'])
        with self.assertRaises(ValueError):
            parse_observed(dict(raw_response='{"label":"SUPPORTED"}', generated_tokens=513))

    def test_reason_mentions_are_not_answers(self):
        self.assertIsNone(self.parse('{"reason":"SUPPORTED",')['label'])
        self.assertEqual(self.parse('{"label":"UNKNOWN"confidence:0.2"reason":"SUPPORTED is mentioned"}')['label'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
