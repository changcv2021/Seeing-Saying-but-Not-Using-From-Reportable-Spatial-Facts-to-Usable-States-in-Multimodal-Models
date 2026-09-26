from __future__ import annotations
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from state_contracts import Action, Program, count, interchange, paired_change, anchor_can_see, check_partition
from validate_review import validate, unique_index

class StateTests(unittest.TestCase):
    def test_valid_zero(self): self.assertEqual(count(0), 0)
    def test_bool_rejected(self):
        with self.assertRaises(ValueError): count(True)
    def test_float_rejected(self):
        with self.assertRaises(ValueError): count(2.0)
    def test_negative_rejected(self):
        with self.assertRaises(ValueError): count(-1)
    def test_bad_action(self):
        with self.assertRaises(ValueError): Action("MAGIC", 1)
    def test_remove_illegal(self):
        with self.assertRaises(ValueError): Action("REMOVE", 2).apply(1)
    def test_set_control(self): self.assertEqual(Action("SET", 3).apply(8), 3)
    def test_noop(self): self.assertEqual(Action("NOOP", 0).apply(5), 5)
    def test_bad_noop(self):
        with self.assertRaises(ValueError): Action("NOOP", 1)
    def test_no_native_set(self):
        with self.assertRaises(ValueError):
            Program(2, Action("SET", 5), Action("ADD", 1), "SOURCE_SUPPORTED_COUNT")
    def test_program(self):
        p = Program(2, Action("ADD", 2), Action("REMOVE", 1))
        self.assertEqual((p.s1, p.s2), (4, 3))
    def test_commutative(self):
        self.assertTrue(Program(3, Action("ADD", 2), Action("REMOVE", 1)).commutes_on_this_state())
    def test_order_sensitive(self):
        self.assertFalse(Program(3, Action("SET", 2), Action("ADD", 1)).commutes_on_this_state())
    def test_reverse_invalid(self):
        self.assertIsNone(Program(0, Action("ADD", 2), Action("REMOVE", 1)).commutes_on_this_state())
    def test_interchange_uses_recipient_a2(self):
        r = Program(2, Action("ADD", 2), Action("REMOVE", 1))
        d = Program(2, Action("ADD", 3), Action("ADD", 2))
        out = interchange(r, d)
        self.assertEqual(out["expected_counterfactual"], 4)
        self.assertEqual(out["donor_final_gold"], 7)
        self.assertTrue(out["discriminative"])
    def test_interchange_unchanged_donor(self):
        p = Program(2, Action("ADD", 2), Action("REMOVE", 1))
        self.assertFalse(interchange(p, p)["discriminative"])
    def test_interchange_unpatched_collision(self):
        r = Program(2, Action("ADD", 2), Action("REMOVE", 1))
        d = Program(2, Action("ADD", 3), Action("ADD", 2))
        self.assertIn("UNPATCHED_PREDICTION", interchange(r, d, 4)["collisions"])
    def test_illegal_interchanged_state(self):
        r = Program(5, Action("ADD", 1), Action("REMOVE", 5))
        d = Program(0, Action("ADD", 1), Action("ADD", 1))
        with self.assertRaises(ValueError): interchange(r, d)
    def test_ambiguous_signature(self):
        p = Program(2, Action("ADD", 1), Action("REMOVE", 1))
        self.assertEqual(p.signatures(2), ["S0", "S2"])
    def test_null_signature(self):
        self.assertEqual(Program(1, Action("ADD", 1), Action("ADD", 1)).signatures(None), ["NULL"])
    def test_no_future_information(self): self.assertFalse(anchor_can_see(20, 30))
    def test_complete_information_visible(self): self.assertTrue(anchor_can_see(30, 30))
    def test_rescue(self): self.assertEqual(paired_change(False, True), "RESCUE")
    def test_harm(self): self.assertEqual(paired_change(True, False), "HARM")
    def test_missing_not_score(self):
        with self.assertRaises(ValueError): paired_change(None, False)
    def test_partition_ok(self): check_partition({"donor_split":"LOCALIZE", "recipient_split":"LOCALIZE"})
    def test_partition_leak(self):
        with self.assertRaises(ValueError): check_partition({"donor_split":"LOCALIZE", "recipient_split":"LOCKED_EVAL"})
    def test_index_duplicate(self):
        with self.assertRaises(ValueError): unique_index([{"id":"A"},{"id":"A"}], "id")

class ClosureTests(unittest.TestCase):
    def fixture(self, root, missing=False):
        with gzip.open(root / "05_ALL_BEHAVIORAL_RESPONSES.jsonl.gz", "wt", encoding="utf8") as f:
            for rid in ("D", "R"):
                f.write(json.dumps({"response_id":rid,"raw_response":"{\"value\":3}"})+"\n")
        row={"patch_trial_id":"P", "donor_response_id":"D", "recipient_response_id":"X" if missing else "R",
             "patched_output":"{\"value\":4}", "original_gold":3, "expected_counterfactual":4,
             "control_type":"STATE_INTERCHANGE", "model":"M", "split":"LOCALIZE",
             "layer":1, "anchor":"CHECKPOINT", "execution_status":"COMPLETE"}
        with gzip.open(root / "06_ALL_PATCH_TRIALS.jsonl.gz", "wt", encoding="utf8") as f:
            f.write(json.dumps(row)+"\n")
        (root / "02_CLAIM_EVIDENCE_MATRIX.json").write_text(json.dumps([
            {"claim_id":"C", "raw_response_ids":["D","R"], "patch_trial_ids":["P"]}]), encoding="utf8")
    def test_valid_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root)
            self.assertEqual(validate(root)["status"], "PASS")
    def test_missing_raw_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.fixture(root, True)
            with self.assertRaises(ValueError): validate(root)

if __name__ == "__main__": unittest.main()
