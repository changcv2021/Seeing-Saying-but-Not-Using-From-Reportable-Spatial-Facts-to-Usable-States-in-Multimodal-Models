"""Policy regression fixtures only, never scientific sample qualification."""
import copy
import unittest
from common import load
from review_policy_v2 import CONFIG, HUMAN_FLAGS, WAIVED, GRADE, execution_decision, validate_policy


class ReviewPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load(CONFIG)
        self.waiver = load(self.config['review_waiver_record'])
        self.checks = {name: 'PASS' for name in (
            'source_truth', 'media_processor', 'query_derivation',
            'world_split', 'gold_separation', 'request_hashes')}

    def decide(self, **kwargs):
        return execution_decision(self.config, self.waiver, self.checks, **kwargs)

    def test_no_primary_review(self):
        self.assertTrue(self.decide()['can_proceed'])

    def test_pending_secondary_review(self):
        self.assertTrue(self.decide(human_record={'secondary': 'PENDING'})['can_proceed'])

    def test_pending_key_case_review(self):
        self.assertTrue(self.decide(human_record={'key_case': 'NOT_REVIEWED'})['can_proceed'])

    def test_pending_confirmation_review(self):
        self.assertTrue(self.decide(human_record={'confirmation': 'PENDING'})['can_proceed'])

    def test_legacy_unbound_acknowledgement(self):
        self.assertTrue(self.decide(human_record={'status': 'SCOPE_PENDING'})['can_proceed'])

    def test_existing_review_not_needed(self):
        self.assertEqual(self.decide(), self.decide(human_record={'primary': 'VERIFIED'}))

    def test_not_fabricated_verified(self):
        result = self.decide()
        self.assertEqual(result['review_status'], WAIVED)
        self.assertEqual(result['scientific_review_grade'], GRADE)
        self.assertFalse(result['human_verified'])

    def test_missing_machine_checks_still_not_ready(self):
        self.checks = {}
        self.assertFalse(self.decide()['can_proceed'])

    def test_each_automatic_failure_still_blocks(self):
        for key in self.checks:
            with self.subTest(check=key):
                checks = dict(self.checks, **{key: 'FAIL'})
                result = execution_decision(self.config, self.waiver, checks)
                self.assertFalse(result['can_proceed'])

    def test_m0_and_mechanism_lock_dependencies_remain(self):
        for dependency in ('M0_EQUIVALENCE', 'MECHANISM_LOCK_FOR_C2'):
            with self.subTest(dependency=dependency):
                self.assertFalse(self.decide(technical_dependencies=[dependency])['can_proceed'])

    def test_cannot_reintroduce_human_gate(self):
        for flag in HUMAN_FLAGS:
            with self.subTest(flag=flag):
                config = copy.deepcopy(self.config)
                config['review'][flag] = True
                with self.assertRaisesRegex(ValueError, 'HUMAN_GATE_REINTRODUCED'):
                    validate_policy(config, self.waiver)

    def test_cannot_forge_verification(self):
        self.config['review']['automatic_pass_is_human_verified'] = True
        with self.assertRaisesRegex(ValueError, 'FALSE_HUMAN_CERTIFICATION'):
            validate_policy(self.config, self.waiver)

    def test_scope_mismatch(self):
        self.waiver['run_id'] = 'another_study'
        with self.assertRaisesRegex(ValueError, 'WAIVER_SCOPE_MISMATCH'):
            validate_policy(self.config, self.waiver)

    def test_new_default_entry_uses_auto_policy(self):
        from common_auto_v2 import arguments
        self.assertEqual(arguments('fixture').parse_args([]).config, CONFIG)

    def test_scientific_configuration_unchanged(self):
        old = load(CONFIG.with_name('config.json'))
        for key in ('models', 'seed', 'generation', 'statistics', 'primary_model'):
            self.assertEqual(self.config[key], old[key])
        changed = {'secondary_review_fraction', 'all_real_main_inputs_require_human_review', 'unresolved_identity'}
        for key in old['sampling'].keys() - changed:
            self.assertEqual(self.config['sampling'][key], old['sampling'][key])


if __name__ == '__main__':
    unittest.main()
