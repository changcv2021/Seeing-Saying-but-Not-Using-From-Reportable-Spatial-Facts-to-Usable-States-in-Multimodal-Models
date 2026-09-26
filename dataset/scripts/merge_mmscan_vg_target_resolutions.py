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
    return str(row["scene_id"]), str(row["change_id"]), str(row.get("question_id") or row.get("source_question_id"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--base-resolutions", type=Path, required=True)
    parser.add_argument("--mmscan-candidates", type=Path, required=True)
    parser.add_argument("--mmscan-vg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    parsed = {key(row): row for row in read_jsonl(args.parsed)}
    merged = {key(row): row for row in read_jsonl(args.base_resolutions)}
    candidates = read_jsonl(args.mmscan_candidates)
    vg_hash = sha256_file(args.mmscan_vg)
    counts: Counter[str] = Counter()
    for candidate in sorted(candidates, key=lambda row: (*key(row), row["role"])):
        current_key = key(candidate)
        parsed_row = parsed.get(current_key)
        if parsed_row is None:
            counts["reject_parsed_row_missing"] += 1
            continue
        row = merged.get(current_key)
        if row is None:
            if candidate["role"] != "target":
                counts["anchor_without_target_resolution"] += 1
                continue
            intervention = parsed_row["intervention"]
            row = {
                "resolution_id": f"target_{current_key[0]}_{current_key[1]}_{current_key[2]}",
                "scene_id": current_key[0], "change_id": current_key[1],
                "question_id": current_key[2], "branch_id": parsed_row["branch_id"],
                "resolver_version": "hypo3d_target_resolver_v2_3_mmscan_vg",
                "new_entity_ids": list(intervention.get("new_entities") or []),
                "resolved_targets": [], "resolved_anchors": [],
                "catalog_source_type": "EMBODIEDSCAN_OFFICIAL_ANNOTATION",
                "status": "PASS", "resolution_tier": candidate["resolution_tier"],
                "evidence_ids": [],
            }
            merged[current_key] = row
        row["resolver_version"] = "hypo3d_target_resolver_v2_3_mmscan_vg"
        evidence_id = f"mmscan_vg:{vg_hash}:{candidate['resolved_entity_id']}"
        if candidate["role"] == "target":
            if row.get("resolved_targets"):
                counts["target_already_resolved"] += 1
                continue
            row["resolved_targets"] = [{
                "target_ref_text": candidate["ref_text"], "candidate_count": 1,
                "resolved_entity_id": candidate["resolved_entity_id"],
                "resolution_tier": candidate["resolution_tier"],
                "evidence_fact_ids": [evidence_id],
            }]
            row["status"] = "PASS"
            row["resolution_tier"] = candidate["resolution_tier"]
            counts["target_added"] += 1
        else:
            anchors = row.setdefault("resolved_anchors", [])
            if any(value.get("resolved_entity_id") == candidate["resolved_entity_id"] for value in anchors):
                counts["anchor_duplicate"] += 1
                continue
            anchors.append({
                "anchor_ref_text": candidate["ref_text"], "candidate_count": 1,
                "resolved_entity_id": candidate["resolved_entity_id"],
                "resolution_tier": candidate["resolution_tier"],
                "evidence_fact_ids": [evidence_id],
            })
            counts["anchor_added"] += 1
        row.setdefault("evidence_ids", []).append(evidence_id)

    output_rows = [merged[current_key] for current_key in sorted(merged)]
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_bytes(b"".join(canonical_json(row) + b"\n" for row in output_rows))
    report = {
        "schema_version": "hypo3d_target_resolution_v2_3_mmscan_vg",
        "status": "TARGET_RESOLUTION_VALID",
        "base_resolution_count": len(read_jsonl(args.base_resolutions)),
        "merged_resolution_count": len(output_rows),
        "counts": dict(sorted(counts.items())),
        "input_hashes": {str(path): sha256_file(path) for path in (
            args.parsed, args.base_resolutions, args.mmscan_candidates, args.mmscan_vg,
        )},
        "output_hash": sha256_file(args.output),
    }
    report_path = args.output.parent / "target_resolution_merge_report.v2_3_mmscan_vg.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
