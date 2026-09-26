#!/usr/bin/env python3
"""Fail unless the private-gold evaluator smoke report has oracle invariants."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    metrics = report["metrics"]
    required_ones = {
        "claim_accuracy": metrics["claim_accuracy"],
        "balanced_accuracy": metrics["balanced_accuracy"],
        "macro_f1": metrics["macro_f1"],
        "pair_accuracy": metrics["pair_accuracy"],
        "conflict_slot_f1": metrics["conflict_slot"]["f1"],
        "evidence_grounding_f1": metrics["evidence_grounding"]["f1"],
        "correction_slot_f1": metrics["structured_correction_slot"]["f1"],
        "unknown_f1": metrics["unknown"]["f1"],
        "unknown_reason_f1": metrics["unknown_reason"]["macro_f1"],
        "conditional_contradiction": metrics["conditional_contradiction_detection"]["value"],
        "proof_carrying_pair_accuracy": metrics["proof_carrying_pair_accuracy"],
    }
    failures = {name: value for name, value in required_ones.items() if value != 1.0}
    unsupported = metrics["unsupported_premise"]
    if unsupported["rate"] != 0.0 or unsupported["unsupported_rule_rate"] != 0.0:
        failures["unsupported_premise_or_rule_rate"] = unsupported
    if metrics["calibration"]["ece"] != 0.0 or metrics["calibration"]["brier"] != 0.0:
        failures["calibration"] = metrics["calibration"]
    if metrics["paraphrase_consistency"]["status"] != "NOT_AVAILABLE":
        failures["paraphrase_availability"] = metrics["paraphrase_consistency"]
    result = {"status": "FAIL" if failures else "PASS", "failures": failures, "checked": required_ones}
    print(json.dumps(result, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
