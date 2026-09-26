#!/usr/bin/env python3
"""Select SPAR rows whose target grounding requires a non-primary view."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_bytes, sha256_file


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def flatten_ints(value: Any) -> list[int]:
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in flatten_ints(child)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--media-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    root = args.root.resolve()
    candidates_path, media_path = args.candidates.resolve(), args.media_index.resolve()
    output, report_path = args.output.resolve(), args.report.resolve()
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "candidates": str(candidates_path), "limit": args.limit}))
        return 0
    media = {row["media_id"]: row for row in load_jsonl(media_path)}
    selected = []
    task_counts: Counter[str] = Counter()
    reject_counts: Counter[str] = Counter()
    checked = 0
    with candidates_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if args.limit is not None and checked >= args.limit:
                break
            row = json.loads(line)
            checked += 1
            locator = row["media_locator"]
            media_row = media.get(locator["media_id"])
            if media_row is None:
                reject_counts["MEDIA_INDEX_MISSING"] += 1
                continue
            if media_row["frame_count"] <= 1:
                reject_counts["SINGLE_IMAGE"] += 1
                continue
            indices = sorted(set(flatten_ints(media_row["bbox_grounding"].get("bbox_img_idx"))))
            support_indices = [index for index in indices if index > 0]
            if not support_indices:
                reject_counts["ALL_REQUIRED_BBOX_GROUNDINGS_IN_PRIMARY_VIEW"] += 1
                continue
            if any(index >= media_row["frame_count"] for index in indices):
                reject_counts["BBOX_IMAGE_INDEX_OUT_OF_RANGE"] += 1
                continue
            task = row["source_task"]
            task_counts[task] += 1
            selected.append({
                "source_item_id": row["source_item_id"],
                "global_world_id": row["global_world_id"], "source_task": task,
                "media_id": locator["media_id"], "frame_count": media_row["frame_count"],
                "required_bbox_frame_indices": indices,
                "required_support_frame_indices": support_indices,
                "selection_reason": "AT_LEAST_ONE_SOURCE_BBOX_TARGET_IS_GROUNDED_OUTSIDE_PRIMARY_VIEW_0",
                "l3_primary_track": "XFORM-PROJ",
            })
    selected.sort(key=lambda row: row["source_item_id"])
    payload = b"".join(compact(row) + b"\n" for row in selected)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if not args.resume or output.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OR_EXISTING_OUTPUT:{output}")
    else:
        output.write_bytes(payload)
    report = {
        "schema_version": "1.0", "selection_version": "spar_7m_strict_multiview_v1",
        "status": "STRICT_MULTIVIEW_SELECTED" if selected else "REJECTED",
        "checked_candidate_count": checked, "selected_count": len(selected),
        "selected_world_count": len({row["global_world_id"] for row in selected}),
        "selected_task_counts": dict(sorted(task_counts.items())),
        "reject_code_counts": dict(sorted(reject_counts.items())),
        "primary_view_index": 0,
        "selection_rule": "AT_LEAST_ONE_REQUIRED_SOURCE_BBOX_GROUNDING_HAS_IMAGE_INDEX_GREATER_THAN_ZERO",
        "identity_policy": "SOURCE_ITEM_LOCAL_NO_CROSS_QA_INSTANCE_MERGE",
        "input_hashes": {
            str(candidates_path.relative_to(root)): sha256_file(candidates_path),
            str(media_path.relative_to(root)): sha256_file(media_path),
        },
        "output_hashes": {str(output.relative_to(root)): sha256_bytes(payload)},
        "next_gate": "L3_XFORM_PROJ_CLAIMS_AND_REQUIRED_SUPPORT_VIEW_ABLATION",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        if not args.resume or report_path.read_bytes() != report_payload:
            raise ValueError(f"NONDETERMINISTIC_OR_EXISTING_OUTPUT:{report_path}")
    else:
        report_path.write_bytes(report_payload)
    print(json.dumps({key: report[key] for key in (
        "status", "checked_candidate_count", "selected_count", "selected_world_count",
        "selected_task_counts", "next_gate",
    )}, sort_keys=True))
    return 0 if selected else 2


if __name__ == "__main__":
    raise SystemExit(main())

