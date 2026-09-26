#!/usr/bin/env python3
"""Select a larger deterministic single-image SPAR relation subset for L2."""

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


TASK = "obj_spatial_relation_oo"


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


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
    parser.add_argument("--parquet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--per-scene", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    parquet, output, report_path = args.parquet.resolve(), args.output.resolve(), args.report.resolve()
    if args.per_scene < 1:
        parser.error("--per-scene must be >= 1")
    heaps: dict[str, list[tuple[int, str, int, dict[str, Any]]]] = defaultdict(list)
    seen_ids: set[str] = set()
    duplicate_count = scanned = matched = 0
    columns = [
        "id", "qa_type", "qa_format", "question", "answer", "image", "split",
        "red_bbox", "green_bbox", "blue_bbox", "yellow_bbox", "bbox_img_idx",
    ]
    parquet_file = pq.ParquetFile(parquet)
    for batch in parquet_file.iter_batches(batch_size=65536, columns=columns):
        scanned += batch.num_rows
        mask = pc.equal(batch.column("qa_type"), pa.scalar(TASK))
        for row in batch.filter(mask).to_pylist():
            matched += 1
            row_id = str(row["id"])
            if row_id in seen_ids:
                duplicate_count += 1
                continue
            seen_ids.add(row_id)
            scene = scene_id(row_id)
            rank = int(hashlib.sha256(f"{args.seed}\0{TASK}\0{row_id}".encode()).hexdigest(), 16)
            entry = (-rank, row_id, matched, row)
            heap = heaps[scene]
            if len(heap) < args.per_scene:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)
    selected: list[dict[str, Any]] = []
    family_counts: Counter[str] = Counter()
    for scene, heap in sorted(heaps.items()):
        for negative_rank, row_id, source_ordinal, row in sorted(heap, key=lambda item: (-item[0], item[1], item[2])):
            images = [str(value) for value in row.get("image") or []]
            family = source_family(images)
            family_counts[family] += 1
            selected.append({
                **row, "id": row_id, "scene_id": scene, "base_dataset": family,
                "selection_rank": -negative_rank, "source_match_ordinal": source_ordinal,
                "selection_policy": "lowest_seeded_task_row_id_hash_per_scene",
                "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
            })
    selected.sort(key=lambda row: (row["scene_id"], row["selection_rank"], row["id"]))
    payload = b"".join(compact(row) + b"\n" for row in selected)
    report = {
        "schema_version": "1.0", "selection_version": "spar_7m_l2_expansion_selection_v2",
        "status": "SUBSET_SELECTED", "seed": args.seed, "run_id": args.run_id, "task": TASK,
        "selection_policy": "lowest_seeded_task_row_id_hash_per_scene_without_question_answer_or_media_content_in_rank",
        "per_scene_cap": args.per_scene, "scanned_row_count": scanned, "source_match_count": matched,
        "duplicate_source_id_count": duplicate_count, "unique_source_id_count": len(seen_ids),
        "selected_row_count": len(selected), "selected_scene_count": len(heaps),
        "selected_source_family_counts": dict(sorted(family_counts.items())),
        "unresolved_source_family_count": family_counts["unresolved"],
        "input_hashes": {str(parquet): sha256(parquet)},
        "output_path": str(output), "output_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "next_gate": "BBOX_IDENTITY_GRAPH_AND_STRICT_L2_CHAIN_BUILD",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    for path, value in ((output, payload), (report_path, report_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not args.resume:
                raise FileExistsError(path)
            if path.read_bytes() != value:
                raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{path}")
        else:
            path.write_bytes(value)
    print(json.dumps({k: report[k] for k in ("status", "selected_row_count", "selected_scene_count", "output_path")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
