import copy
import json
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

from state_schema import RELATION_VARIABLES, serialize_state, parse_state
from state_interface_v2 import (LEGACY_SUFFIXES, OUTPUT_INSTRUCTION,
    parse_state_response, score_state_response, state_prompt_v2, encode_state_v2)


class TestStateInterfaceV2(unittest.TestCase):
    def setUp(self):
        self.gold = dict(entities=['chairs'], variable='count', frame='camera', value=5)

    def test_legacy_unchanged(self):
        text = serialize_state(self.gold)
        self.assertEqual(parse_state(text), self.gold)
        result = parse_state_response(text)
        self.assertEqual(result['state'], self.gold)
        self.assertTrue(result['legacy_strict_valid'])
        self.assertEqual(result['transformations'], [])

    def test_json_representations(self):
        text = json.dumps(self.gold)
        for raw in [text, '<STATE>\n'+text+'\n</STATE>', '```json\n'+text+'\n```']:
            with self.subTest(raw=raw):
                self.assertEqual(parse_state_response(raw)['state'], self.gold)

    def test_unary_scalar_exact_string_preserved(self):
        for variable, value in [('count', 5), ('existence', True), ('visibility', False)]:
            obj = dict(entities='chair with blue cushion', variable=variable, value=value)
            r = parse_state_response(json.dumps(obj))
            self.assertEqual(r['state']['entities'], ['chair with blue cushion'])
            self.assertEqual(r['state']['value'], value)
            self.assertEqual(r['transformations'], ['unary_entity_string_to_singleton_list'])

    def test_no_false_correct_from_reformatting(self):
        for predicted in (0, 3, 6):
            obj = dict(self.gold, entities='chairs', value=predicted)
            r = score_state_response('<STATE>\n'+json.dumps(obj)+'\n</STATE>', self.gold)
            self.assertTrue(r['parse_valid'])
            self.assertFalse(r['exact_match'])
            self.assertEqual(r['parsed']['value'], predicted)

    def test_correct_normalized_value_can_score(self):
        r = score_state_response(json.dumps(dict(self.gold, entities='chairs')), self.gold)
        self.assertTrue(r['exact_match'])

    def test_binary_scalar_rejected(self):
        for variable, value in [('horizontal_relation', 'LEFT_OF'), ('identity', True)]:
            with self.assertRaises(ValueError):
                parse_state_response(json.dumps(dict(entities='A and B', variable=variable, value=value)))

    def test_all_relation_families(self):
        for value, variable in RELATION_VARIABLES.items():
            gold = dict(entities=['A', 'B'], variable=variable, value=value)
            self.assertTrue(score_state_response(json.dumps(gold), gold)['exact_match'])

    def test_entity_order_identity_and_frame_not_repaired(self):
        for changed in [dict(entities=['other chair']), dict(frame='other camera')]:
            r = score_state_response(json.dumps(dict(self.gold, **changed)), self.gold)
            self.assertTrue(r['parse_valid'])
            self.assertFalse(r['exact_match'])
        gold = dict(entities=['A', 'B'], variable='horizontal_relation', value='LEFT_OF')
        self.assertFalse(score_state_response(json.dumps(dict(gold, entities=['B', 'A'])), gold)['exact_match'])

    def test_missing_frame_not_imputed(self):
        obj = dict(self.gold); del obj['frame']
        result = score_state_response(json.dumps(obj), self.gold)
        self.assertTrue(result['parse_valid'])
        self.assertNotIn('frame', result['parsed'])
        self.assertFalse(result['exact_match'])

    def test_invalid_value_types_no_coercion(self):
        for value in [-1, True, 1.0, '5', None, [], {}, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                parse_state_response(json.dumps(dict(self.gold, value=value)))
        for variable in ('existence', 'visibility', 'identity'):
            for value in (1, 0, 'true', 'false'):
                with self.assertRaises(ValueError):
                    parse_state_response(json.dumps(dict(self.gold, variable=variable, value=value)))

    def test_duplicate_fields_in_both_formats(self):
        bad_json = json.dumps(self.gold)[:-1] + ', "value": 0}'
        bad_fields = serialize_state(self.gold).replace('</STATE>', 'value: 0\n</STATE>')
        for raw in (bad_json, bad_fields):
            with self.assertRaisesRegex(ValueError, 'DUPLICATE_FIELD'):
                parse_state_response(raw)

    def test_ambiguous_or_incomplete_not_salvaged(self):
        text = json.dumps(self.gold)
        for raw in (None, '', 'null', 'Answer: '+text, text+'\n'+text,
                    '<STATE>'+text, '<STATE>'+text+'</STATE> extra',
                    '<STATE>'+text+'</STATE><STATE>'+text+'</STATE>',
                    '```python\n'+text+'\n```', text[:-1], '[ '+text+' ]'):
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                parse_state_response(raw)

    def test_unknown_fields_and_empty_entities(self):
        for change in (dict(unexpected=1), dict(entities=[]), dict(entities=' '),
                       dict(entities=[' ']), dict(variable=[]), dict(frame=1)):
            with self.assertRaises((ValueError, TypeError)):
                parse_state_response(json.dumps(dict(self.gold, **change)))

    def test_case_and_relation_value_not_repaired(self):
        for value in ('left_of', 'RIGHT_OF', '5'):
            gold = dict(entities=['A','B'], variable='horizontal_relation', value='LEFT_OF')
            self.assertFalse(score_state_response(json.dumps(dict(gold, value=value)), gold)['exact_match'])

    def test_prompt_context_and_actions_preserved(self):
        prefix = 'Public media context\nA1: rotate frame.\nA2: remove object.\n'
        for suffix in LEGACY_SUFFIXES:
            new = state_prompt_v2(prefix+suffix)
            self.assertEqual(new, prefix+OUTPUT_INSTRUCTION)
            self.assertEqual(state_prompt_v2(new), new)
            self.assertIn('at most 512 output tokens', new)

    def test_unknown_prompt_fail_closed(self):
        with self.assertRaises(ValueError):
            state_prompt_v2('A new unreviewed task')

    def test_gold_cannot_affect_parsing(self):
        raw = json.dumps(dict(self.gold, entities='chairs', value=2))
        a = score_state_response(raw, self.gold)
        b = score_state_response(raw, dict(self.gold, value=2))
        self.assertEqual(a['parsed'], b['parsed'])
        self.assertFalse(a['exact_match']); self.assertTrue(b['exact_match'])

    def test_no_mutation(self):
        before = copy.deepcopy(self.gold)
        score_state_response(json.dumps(self.gold), self.gold)
        self.assertEqual(self.gold, before)

    def test_shared_encoder_preserves_target_and_context(self):
        calls = []
        def fake(processor, request, **kwargs):
            calls.append(kwargs)
            return object(), dict(actual_task_prompt=kwargs['task_prompt'])
        request = dict(media_context='public context')
        prompt = 'public context\n' + LEGACY_SUFFIXES[0]
        target = serialize_state(self.gold)
        with patch.dict(sys.modules, {'model_io_verified': SimpleNamespace(encode=fake)}):
            _, receipt = encode_state_v2(None, request, task_prompt=prompt, target=target, end_turn=True)
            encode_state_v2(None, request, task_prompt=prompt)
        self.assertEqual(calls[0]['target'], target)
        self.assertTrue(calls[0]['end_turn'])
        self.assertIsNone(calls[1]['target'])
        self.assertEqual(calls[0]['task_prompt'], calls[1]['task_prompt'])
        self.assertTrue(receipt['actual_task_prompt'].startswith('public context\n'))
        self.assertEqual(receipt['state_interface_version'], 'state_interface_v2')

    def test_encoder_never_silently_rewrites_supervision(self):
        with patch.dict(sys.modules, {'model_io_verified': SimpleNamespace(encode=None)}):
            with self.assertRaises(ValueError):
                encode_state_v2(None, {}, task_prompt=LEGACY_SUFFIXES[0], target=json.dumps(self.gold))


if __name__ == '__main__':
    unittest.main()
