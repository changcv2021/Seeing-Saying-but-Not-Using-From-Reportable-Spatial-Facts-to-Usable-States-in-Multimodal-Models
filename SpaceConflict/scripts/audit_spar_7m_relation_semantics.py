#!/usr/bin/env python3
"""Independent lexical sanity audit for projected SPAR qualitative relations."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_bytes, sha256_file


ALLOWED = {"LEFT_OF", "RIGHT_OF", "ABOVE", "BELOW", "FRONT_OF", "BEHIND"}


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root, source = args.root.resolve(), args.candidates.resolve()
    output, details = args.output.resolve(), args.details.resolve()
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "candidates": str(source), "limit": args.limit}))
        return 0
    failures: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    observations: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    checked = 0
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if args.limit is not None and checked >= args.limit:
                break
            row = json.loads(line)
            checked += 1
            task = row["source_task"]
            task_counts[task] += 1
            answer = str(row["source_answer"]).casefold()
            predicates = [fact["predicate"] for fact in row["facts"]]
            codes = []
            if not predicates or not set(predicates) <= ALLOWED:
                codes.append("NON_QUALITATIVE_PREDICATE")
            if len(predicates) != len(set(predicates)):
                codes.append("DUPLICATE_PREDICATE")
            if task != "obj_spatial_relation_oc_mv" and set(predicates) & {"FRONT_OF", "BEHIND"}:
                codes.append("OBJECT_OBSERVER_AXIS_LEAKED_INTO_OBJECT_OBJECT")
            if "RIGHT_OF" in predicates and re.search(r"\bright\s+(?:in\s+front|behind)\b", answer):
                codes.append("RIGHT_INTENSIFIER_FALSE_HORIZONTAL_RISK")
            if any(word in answer for word in ("closer", "farther", "distance", "meter")):
                observations["source_answers_with_excluded_metric_language"] += 1
            if row.get("reconstruction_pass") is not True:
                codes.append("SOURCE_RECONSTRUCTION_NOT_PASS")
            counts.update(codes)
            if codes:
                failures.append({
                    "source_item_id": row["source_item_id"],
                    "reject_codes": sorted(set(codes)), "predicates": predicates,
                    "source_answer": row["source_answer"],
                })
    details_payload = b"".join(compact(row) + b"\n" for row in failures)
    details.parent.mkdir(parents=True, exist_ok=True)
    if details.exists():
        if not args.resume or details.read_bytes() != details_payload:
            raise ValueError(f"NONDETERMINISTIC_OR_EXISTING_OUTPUT:{details}")
    else:
        details.write_bytes(details_payload)
    report = {
        "schema_version": "1.0", "audit_version": "spar_7m_relation_semantics_v1",
        "status": "PASS" if not failures and checked else "FAIL",
        "checked_candidate_count": checked, "task_counts": dict(sorted(task_counts.items())),
        "failure_count": len(failures), "failure_code_counts": dict(sorted(counts.items())),
        "observation_counts": dict(sorted(observations.items())),
        "metric_dimension_policy": "SOURCE_LANGUAGE_RETAINED_BUT_NO_METRIC_PREDICATE_EXPORTED",
        "input_hashes": {str(source.relative_to(root)): sha256_file(source)},
        "output_hashes": {str(details.relative_to(root)): sha256_bytes(details_payload)},
        "next_gate": "CORE_L1_CLAIM_GENERATION" if not failures else "VERSIONED_PARSER_FIX_REQUIRED",
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if not args.resume or output.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OR_EXISTING_OUTPUT:{output}")
    else:
        output.write_bytes(payload)
    print(json.dumps({key: report[key] for key in (
        "status", "checked_candidate_count", "failure_count", "failure_code_counts", "next_gate",
    )}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
