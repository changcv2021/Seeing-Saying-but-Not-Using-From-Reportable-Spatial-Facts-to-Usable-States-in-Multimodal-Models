#!/usr/bin/env python3
"""Create deterministic oracle-format predictions for evaluator integration testing.

This is a test fixture generator, not a benchmark baseline: it reads private gold
artifacts and must never be presented as a model result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from spaceconflict.evaluation import _build_gold
from spaceconflict.registry import ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gold, _ = _build_gold(args.release_dir.resolve(), ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for sample_id in sorted(gold):
            target = gold[sample_id]
            evidence = []
            for evidence_id in sorted(target["evidence_ids"]):
                item = {
                    "media_ref": evidence_id,
                    "entity_ref": "gold_fixture",
                    "observation": "oracle integration-test evidence",
                }
                if evidence_id.startswith("fact:"):
                    item["fact_id"] = evidence_id
                evidence.append(item)
            justification = []
            if target["label"] in {"SUPPORTED", "CONTRADICTORY"}:
                # A Supported sample cites its grounded facts directly. Only the
                # contradictory member replays the certificate's inference rules.
                rules = sorted(target["required_rules"]) if target["label"] == "CONTRADICTORY" else []
                justification.append({
                    "type": "certificate_replay",
                    "statement": "Replay private gold certificate for integration testing only.",
                    "premise_fact_ids": sorted(target["evidence_ids"]),
                    **({"rule_id": rules[0]} if rules else {}),
                    "conclusion": target["label"],
                })
                for rule in rules[1:]:
                    justification.append({
                        "type": "certificate_replay",
                        "statement": "Apply the next private gold rule.",
                        "premise_fact_ids": sorted(target["evidence_ids"]),
                        "rule_id": rule,
                        "conclusion": target["label"],
                    })
            correction = None
            if target["label"] == "CONTRADICTORY":
                supported = target["correction"]
                correction = {
                    "normalized": supported["normalized"],
                    "text": supported["natural_text"],
                    "changed_slots": sorted(target["conflict_slots"]),
                }
            prediction = {
                "sample_id": sample_id,
                "label": target["label"],
                "conflict_location": {
                    "slots": sorted(target["conflict_slots"]),
                    "claim_fragments": [],
                },
                "evidence": evidence,
                "justification_steps": justification,
                "correction": correction,
                "unknown_reason": target["unknown_reason"],
                "confidence": 1.0,
            }
            if target["label"] != "UNKNOWN":
                prediction["source_qa_correct"] = True
            handle.write(json.dumps(prediction, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
