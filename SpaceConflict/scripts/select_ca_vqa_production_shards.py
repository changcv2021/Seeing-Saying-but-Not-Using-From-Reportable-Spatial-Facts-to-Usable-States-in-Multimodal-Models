#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


TASKS = ("binary", "cardinality", "multichoice")
PLAN_VERSION = "ca_vqa_production_subset_plan_v1"


def compact(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def write_versioned(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != payload:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--shards-per-task", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    source_manifest = args.source_manifest.resolve()
    candidates = {task: [] for task in TASKS}
    with source_manifest.open(newline="", encoding="utf-8") as handle:
        for url, size, etag in csv.reader(handle, delimiter="\t"):
            for task in TASKS:
                marker = f"/train/cavqa_{task}/1.0.0/cavqa_{task}-train.tfrecord-"
                if marker not in url:
                    continue
                relative_path = url.split("/datasets/cavqa/", 1)[1]
                selection_hash = hashlib.sha256(f"{args.seed}\0{relative_path}".encode()).hexdigest()
                candidates[task].append({
                    "dataset": "ca_vqa", "task": task, "source_revision": args.source_revision,
                    "source_url": url, "relative_path": relative_path, "expected_bytes": int(size),
                    "source_etag": etag, "selection_hash": "sha256:" + selection_hash,
                    "selection_policy": "lowest_seeded_path_hash_per_task",
                })
    rows = []
    for task in TASKS:
        if len(candidates[task]) != 1024:
            raise ValueError(f"TASK_SHARD_INVENTORY_INVALID:{task}:{len(candidates[task])}")
        rows.extend(sorted(candidates[task], key=lambda row: row["selection_hash"])[:args.shards_per_task])
    rows.sort(key=lambda row: (row["task"], row["selection_hash"]))
    if args.limit is not None:
        rows = rows[:args.limit]
    manifest_payload = b"".join(compact(row) + b"\n" for row in rows)
    manifest_path = root / "data/manifests/ca_vqa" / args.source_revision / "production_subset_shards_v1.jsonl"
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "run_id": args.run_id, "selected_shard_count": len(rows), "output": str(manifest_path)}))
        return 0
    write_versioned(manifest_path, manifest_payload, args.resume)
    bytes_by_task = Counter()
    for row in rows:
        bytes_by_task[row["task"]] += row["expected_bytes"]
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "plan_version": PLAN_VERSION,
        "status": "PRODUCTION_SUBSET_PLANNED_DOWNLOAD_COMPLETION_PENDING",
        "source_revision": args.source_revision, "seed": args.seed,
        "allowed_tasks": list(TASKS), "excluded_tasks": ["grounding2d", "grounding3d", "regression"],
        "shards_per_task": args.shards_per_task, "selected_shard_count": len(rows),
        "selected_bytes": sum(row["expected_bytes"] for row in rows),
        "selected_bytes_by_task": dict(sorted(bytes_by_task.items())),
        "selection_policy": "seeded_path_hash_without_question_or_answer_access",
        "selection_independent_of_labels": True,
        "pilot_evidence": {
            "report": "reports/ca_vqa/train_pilot_closure.v3.json",
            "world_count": 12, "graph_valid_world_count": 9,
            "graph_valid_world_rate": 0.75, "candidate_count": 659,
        },
        "capacity_rationale": "48 shards are expected to expose far more than the 625 valid worlds needed for the CA-VQA 2,500-pair target at four pairs per world; final quotas remain acceptance-rate gated.",
        "manifest": str(manifest_path.relative_to(root)),
        "input_hashes": {str(source_manifest.relative_to(root)): digest(source_manifest.read_bytes())},
        "output_hashes": {str(manifest_path.relative_to(root)): digest(manifest_payload)},
        "next_gate": "RESOLVE_SELECTED_SHA256_FROM_COMPLETED_DOWNLOAD_THEN_STREAM_PROFILE_AND_ADAPT",
    }
    report_path = root / "reports/ca_vqa/production_subset_plan.v1.json"
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({key: report[key] for key in (
        "status", "selected_shard_count", "selected_bytes", "selected_bytes_by_task", "next_gate",
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
