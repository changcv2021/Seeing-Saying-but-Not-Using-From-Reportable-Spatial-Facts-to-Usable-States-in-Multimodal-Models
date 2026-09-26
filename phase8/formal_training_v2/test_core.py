import unittest
from core import METHODS, Schedule, digest


def toy():
    rows = {}
    for level, n in [('L1', 5), ('L2', 2), ('L3', 3), ('L4', 2)]:
        for i in range(n):
            sid = level + '_' + str(i)
            for pool, tokens in [('answer', 3), ('cot', 11), ('state', 7)]:
                k = pool+':'+sid
                rows[k] = dict(key=k, pool=pool, sample_id=sid, level=level, target_tokens=tokens)
    return rows


class TestSchedule(unittest.TestCase):
    def test_exact_token_updates_and_resume(self):
        for method in METHODS:
            s = Schedule(toy(), method, 17)
            for _ in range(11):
                self.assertEqual(sum(x['count'] for x in s.segments(19)), 19)
            restored = Schedule(toy(), method, 17, s.state_dict())
            self.assertEqual(s.segments(1000), restored.segments(1000))

    def test_no_skipped_or_repeated_target_token_at_boundaries(self):
        s = Schedule(toy(), 'cot_partial', 18)
        stream = [x for _ in range(30) for x in s.segments(5)]
        expected = 0; key = None
        for r in stream:
            if expected == 0: key = r['key']
            self.assertEqual(key, r['key']); self.assertEqual(expected, r['offset'])
            expected += r['count']
            if expected == r['target_tokens']: expected = 0

    def test_shared_base_sequence(self):
        streams = {}
        for m in ('answer_balanced', 'cot_partial', 'pss_l4', 'pss_full'):
            s = Schedule(toy(), m, 9); ids = []
            while len(ids) < 40:
                k = s._next()
                if not k.startswith('state:'): ids.append(s.catalog[k]['sample_id'])
            streams[m] = ids
        self.assertTrue(all(x == streams['answer_balanced'] for x in streams.values()))

    def test_coverage(self):
        for m in METHODS:
            n = Schedule(toy(), m, 42).coverage_tokens()
            s = Schedule(toy(), m, 42)
            items = s.segments(n)
            actual = {s.catalog[x['key']]['sample_id'] for x in items if not x['key'].startswith('state:')}
            self.assertEqual(actual, {r['sample_id'] for r in toy().values() if r['pool']=='answer'})
            self.assertIsNone(s.s['pending'])

    def test_l4_aux_only(self):
        s = Schedule(toy(), 'pss_l4', 1)
        for x in s.segments(999):
            if x['key'].startswith('state:'): self.assertEqual(s.catalog[x['key']]['level'], 'L4')

    def test_different_seeds(self):
        a = Schedule(toy(), 'answer_balanced', 1).segments(900)
        b = Schedule(toy(), 'answer_balanced', 2).segments(900)
        self.assertNotEqual(digest(a), digest(b))

    def test_no_state_or_answer_added_to_cot(self):
        s = Schedule(toy(), 'cot_partial', 1)
        self.assertTrue(all(x['key'].startswith('cot:') for x in s.segments(100)))

    def test_state_dict_copy(self):
        s = Schedule(toy(), 'answer_natural', 1); s.segments(1)
        state = s.state_dict(); state['pending']['offset'] = 999
        self.assertEqual(s.s['pending']['offset'], 1)


if __name__ == '__main__': unittest.main()
