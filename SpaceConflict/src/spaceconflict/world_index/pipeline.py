from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..canonical import CANONICAL_VERSION
from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT


WORLD_INDEX_VERSION = "world_index_v6"
SPLIT_VERSION = "world_split_v6"
SPLIT_RATIOS = {"train": 0.60, "dev": 0.15, "test": 0.25}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) + b"\n" for row in rows)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {path}")
    else:
        path.write_bytes(payload)


def _canonical_inputs(root: Path, datasets: list[str] | None = None) -> list[Path]:
    if datasets is None:
        return sorted((root / "data/canonical").glob(f"*/*/{CANONICAL_VERSION}/records.jsonl"))
    return sorted(
        path
        for dataset in datasets
        for path in (root / "data/canonical" / dataset).glob(
            f"*/{CANONICAL_VERSION}/records.jsonl"
        )
    )


def build_world_index(
    *, dry_run: bool, resume: bool, limit: int | None, root: Path = ROOT,
    datasets: list[str] | None = None,
    world_index_version: str = WORLD_INDEX_VERSION,
) -> dict[str, Any]:
    output_path = root / "world_index" / f"{world_index_version}.jsonl"
    report_path = root / "reports" / f"{world_index_version}.json"
    inputs = _canonical_inputs(root, datasets)
    if dry_run:
        return {
            "status": "PLANNED", "canonical_inputs": [str(path.relative_to(root)) for path in inputs],
            "output": str(output_path.relative_to(root)), "limit": limit,
        }
    if not inputs:
        return {"status": "BLOCKED_SOURCE", "reason": "NO_CANONICAL_RECORDS"}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in inputs:
        for record in _load_jsonl(path):
            grouped[record["global_world_id"]].append(record)
    selected_world_ids = sorted(grouped)
    if limit is not None:
        selected_world_ids = selected_world_ids[:limit]
    entries: list[dict[str, Any]] = []
    for world_id in selected_world_ids:
        records = grouped[world_id]
        media_by_id = {
            media["media_id"]: media
            for record in records
            for media in record["media"]
        }
        fact_ids = sorted({fact["fact_id"] for record in records for fact in record["facts"]})
        source_datasets = sorted({record["source_dataset"] for record in records})
        entries.append({
            "schema_version": "1.0",
            "world_index_version": world_index_version,
            "global_world_id": world_id,
            "source_datasets": source_datasets,
            "record_ids": sorted(record["record_id"] for record in records),
            "source_item_ids": sorted({item for record in records for item in record["source_item_ids"]}),
            "media": [media_by_id[key] for key in sorted(media_by_id)],
            "fact_ids": fact_ids,
            "record_count": len(records),
            "fact_count": len(fact_ids),
        })
    payload = _jsonl_bytes(entries)
    _write_versioned(output_path, payload, resume)
    multi_source = [entry["global_world_id"] for entry in entries if len(entry["source_datasets"]) > 1]
    report = {
        "schema_version": "1.0",
        "world_index_version": world_index_version,
        "status": "WORLD_INDEX_VALID" if entries else "REJECTED",
        "canonical_input_count": len(inputs),
        "world_count": len(entries),
        "record_count": sum(entry["record_count"] for entry in entries),
        "fact_count": sum(entry["fact_count"] for entry in entries),
        "media_count": sum(len(entry["media"]) for entry in entries),
        "source_dataset_counts": dict(sorted(Counter(
            dataset for entry in entries for dataset in entry["source_datasets"]
        ).items())),
        "exact_global_id_cross_dataset_merges": len(multi_source),
        "exact_global_id_cross_dataset_worlds": multi_source,
        "deduplication_policy": [
            "normalized_global_world_id", "source_media_id", "source_record_id",
        ],
        "deferred_deduplication_signals": [
            "representative_frame_phash", "video_fingerprint",
        ],
        "input_hashes": {str(path.relative_to(root)): sha256_file(path) for path in inputs},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload)},
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _write_versioned(report_path, report_payload, resume)
    return report


def split_worlds(
    *, dry_run: bool, resume: bool, seed: int, limit: int | None, root: Path = ROOT,
    world_index_version: str = WORLD_INDEX_VERSION,
    split_version: str = SPLIT_VERSION,
) -> dict[str, Any]:
    index_path = root / "world_index" / f"{world_index_version}.jsonl"
    output_path = root / "splits" / f"{split_version}.seed_{seed}.jsonl"
    report_path = root / "reports" / f"{split_version}.seed_{seed}.json"
    if dry_run:
        return {
            "status": "PLANNED", "input": str(index_path.relative_to(root)),
            "output": str(output_path.relative_to(root)), "seed": seed, "limit": limit,
        }
    if not index_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "WORLD_INDEX_MISSING"}
    worlds = _load_jsonl(index_path)
    worlds.sort(key=lambda row: (
        hashlib.sha256(f"{seed}\0{row['global_world_id']}".encode("utf-8")).hexdigest(),
        row["global_world_id"],
    ))
    if limit is not None:
        worlds = worlds[:limit]
    count = len(worlds)
    train_end = round(count * SPLIT_RATIOS["train"])
    dev_end = train_end + round(count * SPLIT_RATIOS["dev"])
    assignments: list[dict[str, Any]] = []
    for index, world in enumerate(worlds):
        split = "train" if index < train_end else ("dev" if index < dev_end else "test")
        assignments.append({
            "schema_version": "1.0", "split_version": split_version, "seed": seed,
            "global_world_id": world["global_world_id"], "split": split,
            "source_datasets": world["source_datasets"],
        })
    assignments.sort(key=lambda row: row["global_world_id"])
    if len({row["global_world_id"] for row in assignments}) != len(assignments):
        raise ValueError("WORLD_SPLIT_LEAKAGE_DUPLICATE_WORLD_ID")
    payload = _jsonl_bytes(assignments)
    _write_versioned(output_path, payload, resume)
    split_counts = Counter(row["split"] for row in assignments)
    by_dataset: dict[str, Counter[str]] = defaultdict(Counter)
    for row in assignments:
        for dataset in row["source_datasets"]:
            by_dataset[dataset][row["split"]] += 1
    report = {
        "schema_version": "1.0", "split_version": split_version,
        "status": "WORLD_SPLIT_VALID" if assignments else "REJECTED",
        "seed": seed, "target_ratios": SPLIT_RATIOS, "world_count": count,
        "split_counts": dict(sorted(split_counts.items())),
        "source_dataset_split_counts": {
            dataset: dict(sorted(counts.items())) for dataset, counts in sorted(by_dataset.items())
        },
        "leakage_check": "PASS",
        "assignment_unit": "global_world_id",
        "input_hashes": {str(index_path.relative_to(root)): sha256_file(index_path)},
        "output_hashes": {str(output_path.relative_to(root)): sha256_bytes(payload)},
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _write_versioned(report_path, report_payload, resume)
    return report
