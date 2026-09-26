#!/usr/bin/env python3
"""Validate a minimal SSM REVIEW directory's ID closure. Does not audit visual truth."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any, Iterable


def records(path: Path) -> Iterable[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path.name}:{line_no}: JSON object expected")
            yield record


def unique_index(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Missing {key}")
        if value in out:
            raise ValueError(f"Duplicate {key}: {value}")
        out[value] = row
    return out


def validate(root: Path) -> dict[str, Any]:
    responses = unique_index(records(root / "05_ALL_BEHAVIORAL_RESPONSES.jsonl.gz"),
                             "response_id")
    for rid, row in responses.items():
        if not isinstance(row.get("raw_response"), str):
            raise ValueError(f"{rid}: must include raw_response text, not only a server path")
    patches = unique_index(records(root / "06_ALL_PATCH_TRIALS.jsonl.gz"), "patch_trial_id")
    claims = json.loads((root / "02_CLAIM_EVIDENCE_MATRIX.json").read_text(encoding="utf-8"))
    if not isinstance(claims, list):
        raise ValueError("02_CLAIM_EVIDENCE_MATRIX.json must be a list")
    required_patch_fields = {"donor_response_id", "recipient_response_id", "patched_output",
                             "original_gold", "expected_counterfactual", "control_type",
                             "model", "split", "layer", "anchor", "execution_status"}
    for pid, row in patches.items():
        missing = required_patch_fields - row.keys()
        if missing:
            raise ValueError(f"{pid}: missing {sorted(missing)}")
        for key in ("donor_response_id", "recipient_response_id"):
            if row[key] not in responses:
                raise ValueError(f"{pid}: unresolved {key}: {row[key]}")
        if row["execution_status"] == "COMPLETE" and row["patched_output"] is None:
            raise ValueError(f"{pid}: COMPLETE cannot omit raw patched output")
    seen_claims = set()
    for row in claims:
        cid = row.get("claim_id")
        if not isinstance(cid, str) or not cid or cid in seen_claims:
            raise ValueError("Missing/duplicate claim_id")
        seen_claims.add(cid)
        for rid in row.get("raw_response_ids", []):
            if rid not in responses:
                raise ValueError(f"{cid}: unresolved response {rid}")
        for pid in row.get("patch_trial_ids", []):
            if pid not in patches:
                raise ValueError(f"{cid}: unresolved patch {pid}")
    return {"scope": "ID_REFERENCE_CLOSURE_ONLY", "status": "PASS",
            "behavioral_responses": len(responses), "patch_trials": len(patches),
            "claims": len(claims), "visual_audit": "NOT_PERFORMED",
            "scoring_replay": "NOT_PERFORMED", "mechanism_support": "NOT_DECIDED"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.review_directory), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
