import json
import unittest
from label_policy import parse_observed


class LabelPolicyTests(unittest.TestCase):
    def check(self, text, expected, finish='eos', **kwargs):
        row = dict(raw_response=text, finish_reason=finish, generated_tokens=30, **kwargs)
        result = parse_observed(row)
        self.assertEqual(result['label'], expected, text)
        return result

    def test_all_labels_and_stops(self):
        for label in ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN'):
            for finish in ('eos', 'stop', 'length'):
                for prefix in ('{"label":', '  { "label" : '):
                    result = self.check(prefix + json.dumps(label), label, finish)
                    self.assertFalse(result['schema_valid'])
                    self.assertFalse(result['strict_json_valid'])

    def test_missing_commas_and_reason_ending(self):
        self.check('{"label":"CONTRADICTORY"\n"confidence":0.9\n"reason":"There are none.', 'CONTRADICTORY')
        self.check('{"label":"SUPPORTED"\n\nA visible relationship is described.', 'SUPPORTED')

    def test_valid_json_preserved(self):
        result = self.check('{"reason":"UNKNOWN is not the chosen label","label":"SUPPORTED","confidence":0.8}', 'SUPPORTED')
        self.assertTrue(result['schema_valid'])
        self.assertFalse(result['label_recovered_v2'])
        self.check('{"label":"UNKNOWN"}', 'UNKNOWN')

    def test_quoted_confidence_not_primary_answer(self):
        result = self.check('{"label":"UNKNOWN","confidence":"0.9","reason":"Missing view"}', 'UNKNOWN')
        self.assertFalse(result['schema_valid'])

    def test_reject_unobserved_or_unstructured(self):
        for text in ('', 'SUPPORTED', 'The answer is UNKNOWN', '{"label":"SUPPOR',
                     '{"label":"SUPPORTED', '{"label":"SUPPORTED|UNKNOWN"',
                     '{"reason":"SUPPORTED"', '[{"label":"SUPPORTED"}]',
                     'Example: {"label":"SUPPORTED"}', '{"label":true',
                     '{"label":"supported"', '{"label":"SUPPORTED"confidence":0.9'):
            self.check(text, None)

    def test_reject_duplicates_even_same_label(self):
        for tail in (',"label":"UNKNOWN"}', ',"label":"SUPPORTED"}',
                     '\n{"label":"UNKNOWN"}', ',"\\u006cabel":"UNKNOWN"}',
                     '\nlabel: UNKNOWN'):
            result = self.check('{"label":"SUPPORTED"' + tail, None)
            self.assertEqual(result['recovery_reject'], 'ADDITIONAL_LABEL_KEY_AMBIGUOUS')

    def test_existing_fence_normalization(self):
        self.check('```json\n{"label":"UNKNOWN"\n```', 'UNKNOWN')
        self.check('```json\n{"label":"UNKNOWN"', 'UNKNOWN', 'length')
        self.check('```json\n{"label":"UNKNOWN"', None, 'eos')

    def test_reason_labels_not_selected(self):
        self.check('{"reason":"label is SUPPORTED"', None)
        self.check('{"label":"UNKNOWN"\n"reason":"The word SUPPORTED appears in the prompt.', 'UNKNOWN')

    def test_runtime_error_fails_closed(self):
        self.check('{"label":"SUPPORTED"}', None, error='INFERENCE_ERROR')

    def test_over_budget_rejected(self):
        with self.assertRaises(ValueError):
            parse_observed(dict(raw_response='{"label":"SUPPORTED"}', generated_tokens=513))

    def test_gold_and_identity_invariance(self):
        raw = dict(raw_response='{"label":"UNKNOWN"', finish_reason='eos', generated_tokens=10)
        expected = parse_observed(raw)
        for label in ('SUPPORTED', 'CONTRADICTORY', 'UNKNOWN'):
            self.assertEqual(parse_observed(dict(raw, gold=label, model_id=label,
                                                 level=label, seed=label, reference_proposition=label)), expected)

    def test_no_fabricated_fields(self):
        result = self.check('{"label":"UNKNOWN"', 'UNKNOWN')
        self.assertIsNone(result['reason'])
        self.assertIsNone(result['confidence'])
        self.assertEqual(result['label_evidence_span']['observed'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
