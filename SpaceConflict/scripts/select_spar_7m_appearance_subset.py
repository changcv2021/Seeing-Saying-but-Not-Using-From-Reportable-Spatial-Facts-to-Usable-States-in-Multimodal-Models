#!/usr/bin/env python3
"""Select a deterministic scene-balanced SPAR-7M appearance-order subset."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


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
    parser.add_argument("--per-scene", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int, default=0, help="0 scans all source rows")
    args = parser.parse_args()
    root = args.root.resolve()
    parquet = args.parquet.resolve()
    output = args.output.resolve()
    report_path = args.report.resolve()
    output.relative_to(root)
    report_path.relative_to(root)
    if args.per_scene < 1 or args.limit < 0:
        parser.error("--per-scene must be >= 1 and --limit must be >= 0")
    if args.dry_run:
        print(json.dumps({
            "status": "PLANNED", "task": "appearance_order", "per_scene": args.per_scene,
            "source": str(parquet), "output": str(output), "limit": args.limit,
        }, sort_keys=True))
        return 0

    heaps: dict[str, list[tuple[int, str, int, dict[str, Any]]]] = defaultdict(list)
    seen_source_ids: set[str] = set()
    duplicate_source_id_count = 0
    source_match_count = 0
    scanned_count = 0
    columns = ["id", "qa_type", "qa_format", "question", "answer", "image", "split"]
    parquet_file = pq.ParquetFile(parquet)
    for batch in parquet_file.iter_batches(batch_size=65536, columns=columns):
        if args.limit:
            remaining = args.limit - scanned_count
            if remaining <= 0:
                break
            if batch.num_rows > remaining:
                batch = batch.slice(0, remaining)
        scanned_count += batch.num_rows
        filtered = batch.filter(pc.equal(batch.column("qa_type"), "appearance_order"))
        for row in filtered.to_pylist():
            source_match_count += 1
            row_id = str(row["id"])
            if row_id in seen_source_ids:
                duplicate_source_id_count += 1
                continue
            seen_source_ids.add(row_id)
            scene = scene_id(row_id)
            rank = int(hashlib.sha256(f"{args.seed}\0{row_id}".encode()).hexdigest(), 16)
            # Official rows can repeat an id.  The monotonic source ordinal is a
            # stable final tie-breaker and prevents Python from comparing row
            # dictionaries when both the seeded rank and id are equal.
            entry = (-rank, row_id, source_match_count, row)
            heap = heaps[scene]
            if len(heap) < args.per_scene:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)

    selected = []
    family_counts: Counter[str] = Counter()
    for scene, heap in sorted(heaps.items()):
        for negative_rank, row_id, source_ordinal, row in sorted(
            heap, key=lambda item: (-item[0], item[1], item[2])
        ):
            images = [str(value) for value in row.get("image") or []]
            family = source_family(images)
            family_counts[family] += 1
            selected.append({
                **row,
                "id": row_id,
                "scene_id": scene,
                "base_dataset": family,
                "selection_rank": -negative_rank,
                "source_match_ordinal": source_ordinal,
                "selection_policy": "lowest_seeded_row_id_hash_per_scene",
                "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
            })
    selected.sort(key=lambda row: (row["scene_id"], row["selection_rank"], row["id"]))
    output_payload = b"".join(compact(row) + b"\n" for row in selected)
    report = {
        "schema_version": "1.0",
        "selection_version": "spar_7m_appearance_subset_v1",
        "status": "SUBSET_SELECTED",
        "seed": args.seed,
        "run_id": args.run_id,
        "task": "appearance_order",
        "selection_policy": "lowest_seeded_row_id_hash_per_scene_without_question_answer_or_media_content_access",
        "per_scene_cap": args.per_scene,
        "scanned_row_count": scanned_count,
        "source_match_count": source_match_count,
        "unique_source_id_count": len(seen_source_ids),
        "duplicate_source_id_count": duplicate_source_id_count,
        "selected_row_count": len(selected),
        "selected_scene_count": len(heaps),
        "selected_source_family_counts": dict(sorted(family_counts.items())),
        "unresolved_source_family_count": family_counts["unresolved"],
        "input_hashes": {str(parquet): sha256(parquet)},
        "output_hashes": {str(output.relative_to(root)): "sha256:" + hashlib.sha256(output_payload).hexdigest()},
        "success_count": len(selected),
        "failure_count": 0,
        "next_gate": "VERSIONED_APPEARANCE_ORDER_ADAPTER_AND_SOURCE_RECONSTRUCTION",
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    for path, payload in ((output, output_payload), (report_path, report_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not args.resume:
                raise FileExistsError(f"Output exists: {path}; use --resume")
            if path.read_bytes() != payload:
                raise ValueError(f"Non-deterministic output: {path}")
        else:
            path.write_bytes(payload)
    print(compact({
        "status": report["status"], "selected_rows": len(selected),
        "selected_scenes": len(heaps), "source_families": report["selected_source_family_counts"],
    }).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
