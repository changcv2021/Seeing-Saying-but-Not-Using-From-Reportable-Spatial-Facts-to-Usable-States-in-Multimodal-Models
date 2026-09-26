#!/usr/bin/env python3
"""Select deterministic scene-balanced SPAR-7M qualitative relation rows."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


TASKS = ("obj_spatial_relation_oc_mv", "obj_spatial_relation_oo", "obj_spatial_relation_oo_mv")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def scene_id(row_id: str) -> str:
    match = re.fullmatch(r"(.+)_([0-9]+)", row_id)
    if not match:
        raise ValueError(f"UNPARSEABLE_SPAR_ROW_ID:{row_id}")
    return match.group(1)


def source_family(images: list[str]) -> str:
    joined = "/".join(images).casefold()
    for family in ("scannetpp", "scannet", "structured3d", "rxr"):
        if re.search(rf"(?:^|[/_-]){family}(?:[/_-]|$)", joined):
            return family
    return "unresolved"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--per-scene-task", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root, parquet = args.root.resolve(), args.parquet.resolve()
    output, report_path = args.output.resolve(), args.report.resolve()
    output.relative_to(root)
    report_path.relative_to(root)
    if args.per_scene_task < 1 or args.limit < 0:
        parser.error("--per-scene-task must be >= 1 and --limit must be >= 0")
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "tasks": TASKS, "per_scene_task": args.per_scene_task,
            "source": str(parquet), "output": str(output), "limit": args.limit,
        }, sort_keys=True))
        return 0

    heaps: dict[tuple[str, str], list[tuple[int, str, int, dict[str, Any]]]] = defaultdict(list)
    seen_ids: set[tuple[str, str]] = set()
    duplicate_counts: Counter[str] = Counter()
    source_match_counts: Counter[str] = Counter()
    scanned_count = 0
    match_ordinal = 0
    columns = [
        "id", "qa_type", "qa_format", "question", "answer", "image", "split",
        "red_bbox", "green_bbox", "blue_bbox", "yellow_bbox", "bbox_img_idx",
    ]
    parquet_file = pq.ParquetFile(parquet)
    for batch in parquet_file.iter_batches(batch_size=65536, columns=columns):
        if args.limit:
            remaining = args.limit - scanned_count
            if remaining <= 0:
                break
            if batch.num_rows > remaining:
                batch = batch.slice(0, remaining)
        scanned_count += batch.num_rows
        mask = pc.is_in(batch.column("qa_type"), value_set=pa.array(TASKS))
        for row in batch.filter(mask).to_pylist():
            match_ordinal += 1
            task = str(row["qa_type"])
            source_match_counts[task] += 1
            row_id = str(row["id"])
            source_key = (task, row_id)
            if source_key in seen_ids:
                duplicate_counts[task] += 1
                continue
            seen_ids.add(source_key)
            scene = scene_id(row_id)
            rank = int(hashlib.sha256(f"{args.seed}\0{task}\0{row_id}".encode()).hexdigest(), 16)
            entry = (-rank, row_id, match_ordinal, row)
            heap = heaps[(scene, task)]
            if len(heap) < args.per_scene_task:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)

    selected: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    scenes: set[str] = set()
    for (scene, task), heap in sorted(heaps.items()):
        for negative_rank, row_id, source_ordinal, row in sorted(
            heap, key=lambda item: (-item[0], item[1], item[2])
        ):
            images = [str(value) for value in row.get("image") or []]
            family = source_family(images)
            family_counts[family] += 1
            task_counts[task] += 1
            scenes.add(scene)
            selected.append({
                **row, "id": row_id, "scene_id": scene, "base_dataset": family,
                "selection_rank": -negative_rank, "source_match_ordinal": source_ordinal,
                "selection_policy": "lowest_seeded_task_row_id_hash_per_scene_task",
                "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
            })
    selected.sort(key=lambda row: (row["scene_id"], row["qa_type"], row["selection_rank"], row["id"]))
    output_payload = b"".join(compact(row) + b"\n" for row in selected)
    report = {
        "schema_version": "1.0", "selection_version": "spar_7m_relation_subset_v1",
        "status": "SUBSET_SELECTED", "seed": args.seed, "run_id": args.run_id,
        "tasks": list(TASKS),
        "selection_policy": "lowest_seeded_task_row_id_hash_per_scene_task_without_question_answer_or_media_content_in_rank",
        "per_scene_task_cap": args.per_scene_task, "scanned_row_count": scanned_count,
        "source_match_counts": dict(sorted(source_match_counts.items())),
        "duplicate_source_id_counts": dict(sorted(duplicate_counts.items())),
        "unique_source_id_count": len(seen_ids),
        "selected_row_count": len(selected), "selected_scene_count": len(scenes),
        "selected_task_counts": dict(sorted(task_counts.items())),
        "selected_source_family_counts": dict(sorted(family_counts.items())),
        "unresolved_source_family_count": family_counts["unresolved"],
        "input_hashes": {str(parquet): sha256(parquet)},
        "output_hashes": {str(output.relative_to(root)): "sha256:" + hashlib.sha256(output_payload).hexdigest()},
        "success_count": len(selected), "failure_count": 0,
        "next_gate": "VERSIONED_QUALITATIVE_RELATION_SEMANTIC_PARSER_PREFLIGHT",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    for path, payload in ((output, output_payload), (report_path, report_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not args.resume:
                raise FileExistsError(f"OUTPUT_EXISTS:{path}")
            if path.read_bytes() != payload:
                raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
        else:
            path.write_bytes(payload)
    print(compact({
        "status": report["status"], "selected_rows": len(selected),
        "selected_scenes": len(scenes), "selected_task_counts": report["selected_task_counts"],
    }).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
