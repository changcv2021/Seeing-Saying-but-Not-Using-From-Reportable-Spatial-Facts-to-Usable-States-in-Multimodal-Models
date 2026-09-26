#!/usr/bin/env python3
"""Build a versioned track-annotation overlay for frozen L4 v3.3 pairs."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from spaceconflict.l4_tracks import ANNOTATION_VERSION, derive_missing_track_annotation


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "l4/v3_3/release/pairs.l4_three_part_v3.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "l4/v3_3/derived_annotations/track_annotations_v1"
EXPECTED_INPUT_SHA256 = "5219229fd6689c3b8ea3ea066e05756afc43e6dbd79da879272670332c01c246"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Non-object record at {path}:{line_number}")
            yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    value.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    value.add_argument("--allow-input-hash-mismatch", action="store_true")
    return value


def main() -> int:
    args = parser().parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    input_hash = sha256_file(input_path)
    if input_hash != EXPECTED_INPUT_SHA256 and not args.allow_input_hash_mismatch:
        raise SystemExit(
            f"Input hash mismatch: expected {EXPECTED_INPUT_SHA256}, found {input_hash}. "
            "Refusing to annotate a different release."
        )

    source_rows = list(read_jsonl(input_path))
    if len(source_rows) != 1136:
        raise SystemExit(f"Expected 1136 L4 pairs, found {len(source_rows)}")
    ids = [str(row.get("pair_id") or "") for row in source_rows]
    if "" in ids or len(set(ids)) != len(ids):
        raise SystemExit("Missing or duplicate pair_id in L4 input")

    annotations: list[dict[str, Any]] = []
    annotated_view: list[dict[str, Any]] = []
    released_count = 0
    for row in source_rows:
        task = row.get("task") or {}
        released_primary = task.get("primary_track")
        if released_primary:
            released_count += 1
            annotated_view.append(row)
            continue
        annotation = derive_missing_track_annotation(row)
        annotations.append(annotation)
        updated = dict(row)
        updated["task"] = {
            "level": "L4",
            "operator_id": annotation["operator_id"],
            "primary_track": annotation["primary_track"],
            "secondary_tracks": annotation["secondary_tracks"],
            "strength_slice": "L4_CALIBRATION" if row.get("dependency_type") == "CALIBRATION" else "L4_CORE",
        }
        updated["derived_track_annotation"] = {
            key: annotation[key]
            for key in ("annotation_version", "annotation_status", "rule_id", "confidence", "rationale")
        }
        annotated_view.append(updated)

    if released_count != 96 or len(annotations) != 1040:
        raise SystemExit(
            f"Expected 96 released and 1040 derived track annotations; "
            f"found {released_count} and {len(annotations)}"
        )

    primary_derived = collections.Counter(row["primary_track"] for row in annotations)
    primary_all = collections.Counter()
    secondary_derived = collections.Counter()
    rule_counts = collections.Counter()
    origin_primary = collections.Counter()
    for source, combined in zip(source_rows, annotated_view, strict=True):
        primary_all[combined["task"]["primary_track"]] += 1
        if not (source.get("task") or {}).get("primary_track"):
            annotation = next(row for row in annotations if row["pair_id"] == source["pair_id"])
            secondary_derived.update(annotation["secondary_tracks"])
            rule_counts[annotation["rule_id"]] += 1
            origin_primary[(source["l4_origin"], annotation["primary_track"])] += 1

    overlay_path = output_dir / "track_annotations.l4_v3_3.v1.jsonl"
    view_path = output_dir / "pairs.l4_three_part_v3.track_annotated_v1.jsonl"
    report_path = output_dir / "track_annotation_report.v1.json"
    markdown_path = output_dir / "TRACK_ANNOTATION_REPORT_CN.md"
    write_jsonl(overlay_path, annotations)
    write_jsonl(view_path, annotated_view)

    report = {
        "schema_version": ANNOTATION_VERSION,
        "status": "PASS",
        "frozen_release_modified": False,
        "input": str(input_path),
        "input_sha256": input_hash,
        "total_pairs": len(source_rows),
        "released_primary_track_pairs": released_count,
        "derived_primary_track_pairs": len(annotations),
        "unassigned_pairs": 0,
        "primary_track_counts_derived": dict(sorted(primary_derived.items())),
        "primary_track_counts_all": dict(sorted(primary_all.items())),
        "secondary_track_counts_derived": dict(sorted(secondary_derived.items())),
        "rule_counts": dict(sorted(rule_counts.items())),
        "origin_primary_track_counts": {
            f"{origin}|{track}": count
            for (origin, track), count in sorted(origin_primary.items())
        },
    }
    write_json(report_path, report)

    lines = [
        "# SpaceConflict L4 v3.3 Track 派生标注报告",
        "",
        "状态：`PASS`  ",
        f"标注版本：`{ANNOTATION_VERSION}`  ",
        "冻结 release 是否被修改：否",
        "",
        "## 结果",
        "",
        f"- L4 pair 总数：{len(source_rows):,}",
        f"- release 原有 primary track：{released_count:,}",
        f"- 本次派生标注：{len(annotations):,}",
        "- 未分配：0",
        "",
        "| Primary track | 全部 pairs | 本次派生 |",
        "|---|---:|---:|",
    ]
    for track in sorted(primary_all):
        lines.append(f"| `{track}` | {primary_all[track]:,} | {primary_derived.get(track, 0):,} |")
    lines.extend([
        "",
        "## 判定原则",
        "",
        "- Native movement 的 claim 直接改变互斥空间关系，且 release 未声明参考系：`GEO-TOPO`；`DYNAMIC` 为 secondary。",
        "- Controlled movement/swap 明确声明 `source_world_axes` 和 axis：`XFORM-PROJ`；`DYNAMIC`、`GEO-TOPO` 为 secondary。",
        "- 增加、移除、替换后的 count：`DYNAMIC`；`GEO-TOPO` 为 secondary，replacement 另加 `IDENTITY`。",
        "- replacement same-instance 冲突：`IDENTITY`；`DYNAMIC` 为 secondary。",
        "- attribute change 下的 instance persistence：`IDENTITY`；`DYNAMIC` 为 secondary。",
        "- 不产生 `EMBODIED-OBS`，因为这些 pair 没有显式 reachability、action-success 或 visibility-boundary oracle。",
        "",
        "## 使用方式",
        "",
        "`track_annotations.l4_v3_3.v1.jsonl` 是按 `pair_id` join 的 1,040 条 overlay。",
        "`pairs.l4_three_part_v3.track_annotated_v1.jsonl` 是方便分析使用的完整只读派生视图；它不是新的 release。",
        "",
    ])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    artifact_hashes = {
        path.name: sha256_file(path)
        for path in (overlay_path, view_path, report_path, markdown_path)
    }
    write_json(output_dir / "manifest.json", {
        "schema_version": ANNOTATION_VERSION,
        "status": "PASS",
        "source_release_file": str(input_path),
        "source_release_sha256": input_hash,
        "artifact_sha256": artifact_hashes,
    })
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

