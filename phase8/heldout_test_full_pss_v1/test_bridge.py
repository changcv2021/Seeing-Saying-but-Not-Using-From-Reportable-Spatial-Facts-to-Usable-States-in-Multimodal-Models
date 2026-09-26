import importlib
import unittest
import full_common as bridge


class TestBridge(unittest.TestCase):
    def tearDown(self):
        importlib.reload(bridge.previous)

    def test_seed_isolation(self):
        paths = []
        for seed in bridge.SEEDS:
            settings = bridge.configure_seed(seed)
            self.assertEqual(settings.KEYS, (f'pss_full__seed_{seed}',))
            self.assertEqual(settings.METHODS, ('pss_full',))
            self.assertEqual(settings.SHARDS, 4)
            self.assertEqual(settings.N_TEST, 5608)
            self.assertEqual(settings.DECODE_SEED, 20260904)
            self.assertNotEqual(settings.ROOT, bridge.EIGHT_ROOT)
            paths.append(settings.ROOT)
        self.assertNotEqual(*paths)

    def test_read_only_code_reuse(self):
        settings = bridge.configure_seed(20260922)
        self.assertEqual(settings.CODE, bridge.PREVIOUS_CODE)
        self.assertEqual(settings.verify_plan.__globals__['ROOT'], settings.ROOT)
        self.assertEqual(settings.verify_model.__globals__['ROOT'], settings.ROOT)

    def test_unknown_seed_rejected(self):
        with self.assertRaises(ValueError):
            bridge.key(42)


if __name__ == '__main__':
    unittest.main()
