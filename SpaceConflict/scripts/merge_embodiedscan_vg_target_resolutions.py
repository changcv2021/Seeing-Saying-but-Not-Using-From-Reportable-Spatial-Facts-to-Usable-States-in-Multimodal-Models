from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["scene_id"]), str(row["change_id"]),
        str(row.get("question_id") or row.get("source_question_id")),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--base-resolutions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-artifact", dest="source_artifacts", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="embodiedscan_vg_merge_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output.exists() and not args.resume:
        raise FileExistsError(args.output)
    parsed = {key(row): row for row in read_jsonl(args.parsed)}
    base_rows = read_jsonl(args.base_resolutions)
    merged = {key(row): row for row in base_rows}
    candidates = read_jsonl(args.candidates)
    source_hashes = {str(path): sha256_file(path) for path in args.source_artifacts}
    evidence_namespace = sha256_file(args.candidates)
    counts: Counter[str] = Counter()
    for candidate in sorted(candidates[: args.limit], key=key):
        current_key = key(candidate)
        parsed_row = parsed.get(current_key)
        if parsed_row is None:
            counts["reject_parsed_row_missing"] += 1
            continue
        if candidate.get("role") != "target":
            counts["reject_unsupported_role"] += 1
            continue
        row = merged.get(current_key)
        if row is not None and row.get("resolved_targets"):
            counts["target_already_resolved"] += 1
            continue
        if row is None:
            intervention = parsed_row["intervention"]
            row = {
                "resolution_id": f"target_{current_key[0]}_{current_key[1]}_{current_key[2]}",
                "scene_id": current_key[0], "change_id": current_key[1],
                "question_id": current_key[2], "branch_id": parsed_row["branch_id"],
                "new_entity_ids": list(intervention.get("new_entities") or []),
                "resolved_targets": [], "resolved_anchors": [],
                "catalog_source_type": "EMBODIEDSCAN_OFFICIAL_ANNOTATION",
            }
            merged[current_key] = row
        evidence_id = f"embodiedscan_vg:{evidence_namespace}:{candidate['resolved_entity_id']}"
        row.update({
            "resolver_version": "hypo3d_target_resolver_v2_4_all_official_grounding",
            "status": "PASS",
            "resolution_tier": candidate["resolution_tier"],
        })
        row["resolved_targets"] = [{
            "target_ref_text": candidate["ref_text"], "candidate_count": 1,
            "resolved_entity_id": candidate["resolved_entity_id"],
            "resolution_tier": candidate["resolution_tier"],
            "evidence_fact_ids": [evidence_id],
        }]
        row.setdefault("evidence_ids", []).append(evidence_id)
        counts["target_added"] += 1

    output_rows = [merged[current_key] for current_key in sorted(merged)]
    report = {
        "schema_version": "hypo3d_target_resolution_v2_4_all_official_grounding",
        "status": "TARGET_RESOLUTION_VALID",
        "run_id": args.run_id,
        "seed": args.seed,
        "base_resolution_count": len(base_rows),
        "merged_resolution_count": len(output_rows),
        "counts": dict(sorted(counts.items())),
        "input_hashes": {
            str(args.parsed): sha256_file(args.parsed),
            str(args.base_resolutions): sha256_file(args.base_resolutions),
            str(args.candidates): sha256_file(args.candidates),
            **source_hashes,
        },
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    args.output.parent.mkdir(parents=True, exist_ok=args.resume)
    args.output.write_bytes(b"".join(canonical_json(row) + b"\n" for row in output_rows))
    report["output_hash"] = sha256_file(args.output)
    (args.output.parent / "target_resolution_merge_report.v2_4.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
