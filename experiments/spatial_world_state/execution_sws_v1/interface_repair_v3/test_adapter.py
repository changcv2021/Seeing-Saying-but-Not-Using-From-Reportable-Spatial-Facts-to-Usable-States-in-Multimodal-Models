import importlib.util
import json
import unittest
from pathlib import Path
from adapter import normalize, remaining_failure

COUNT = dict(kind='value', domain='count', nullable=True)
FACTS = dict(kind='facts', domain='count', nullable=True, query_ids=['q0', 'qA'])
ENUM = dict(kind='value', domain='enum', nullable=True, values=['YES', 'NO'])


class V3(unittest.TestCase):
    def test_valid_unchanged(self):
        for text, schema in [(' {"value":2} ', COUNT), ('{"value":null}', COUNT), ('{"value":"YES"}', ENUM)]:
            out = normalize(text, schema)
            self.assertEqual(text, out['canonical_text'])
            self.assertFalse(out['changed'])

    def test_null_wrapper_scope(self):
        for schema in (COUNT, ENUM):
            self.assertEqual(normalize('null', schema)['normalized']['component_values'], {'value': None})
        for schema in (FACTS, dict(COUNT, kind='joint'), dict(COUNT, kind='verdict'), dict(COUNT, nullable=False)):
            self.assertEqual(normalize('null', schema)['normalized']['status'], 'INVALID')

    def test_exact_count_strings(self):
        for value in ['0', '1', '123456']:
            out = normalize(json.dumps({'value': value}), COUNT)
            self.assertEqual(out['normalized']['component_values'], {'value': int(value)})

    def test_facts_and_joint(self):
        out = normalize('{"facts":[{"query_id":"q0","value":"0"},{"query_id":"qA","value":"2"}]}', FACTS)
        self.assertEqual(out['normalized']['component_values']['facts'], {'q0': 0, 'qA': 2})
        out = normalize('{"verdict":"CONTRADICTORY","value":"2"}', dict(COUNT, kind='joint'))
        self.assertEqual(out['normalized']['actual_key_order'], ['verdict', 'value'])
        self.assertEqual(out['normalized']['component_values']['verdict'], 'CONTRADICTORY')

    def test_reject_noncanonical_and_semantic_values(self):
        for value in ['-1', '01', '1.0', '1e2', '+2', ' 2', 'two', -1, True, 1.0]:
            self.assertEqual(normalize(json.dumps({'value': value}), COUNT)['normalized']['status'], 'INVALID')
        out = normalize('{"facts":[{"query_id":"q0","value":0},{"query_id":"qA","value":-1}]}', FACTS)
        self.assertEqual(remaining_failure(out, FACTS), 'CONTENT_DOMAIN_ERROR_NEGATIVE_COUNT')
        self.assertEqual(out['normalized']['parsed']['facts'][1]['value'], -1)

    def test_no_answers_extracted_or_filled(self):
        for text in ['null null', 'Answer: null', '{"value":2}{"value":3}', '{"value":2,"value":3}', '{"value":"2"', '{}', '{"value":"2","extra":1}']:
            # A complete quoted value followed by one missing outer brace is a retained v2 rule.
            if text == '{"value":"2"':
                continue
            self.assertEqual(normalize(text, COUNT)['normalized']['status'], 'INVALID')
        for text in ['{"value":"yes"}', '{"value":"2"}']:
            self.assertEqual(normalize(text, ENUM)['normalized']['status'], 'INVALID')

    def test_composed_rules_and_alias(self):
        self.assertEqual(normalize('```json\nnull\n```', COUNT)['normalized']['status'], 'VALID')
        self.assertEqual(normalize('{"query_value":"2"}', COUNT)['normalized']['component_values'], {'value': 2})
        self.assertEqual(normalize('{"value":"null"}', COUNT)['normalized']['component_values'], {'value': None})

    def test_query_id_never_repaired(self):
        text = '{"facts":[{"query_id":"wrong","value":"0"},{"query_id":"qA","value":"2"}]}'
        self.assertEqual(normalize(text, FACTS)['normalized']['status'], 'INVALID')


if __name__ == '__main__':
    unittest.main()
