#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from spaceconflict.adapters.ca_vqa import adapt
from spaceconflict.adapters.common import record_hash
from spaceconflict.hashing import sha256_bytes, sha256_file


OLD_VERSION = "ca_vqa_train_production_subset_v1"
NEW_VERSION = "ca_vqa_train_production_subset_v2"


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def payload(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(compact(row) + b"\n" for row in rows)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_versioned(path: Path, value: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_bytes() != value:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
    else:
        path.write_bytes(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--task", choices=["binary", "cardinality"], required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    old_report_path = root / "reports/ca_vqa" / f"train_production_subset.{args.task}.v1.json"
    new_report_path = root / "reports/ca_vqa" / f"train_production_subset.{args.task}.v2.json"
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "task": args.task, "run_id": args.run_id, "output": str(new_report_path)}))
        return 0
    old_report = json.loads(old_report_path.read_text(encoding="utf-8"))
    if old_report.get("status") != "PRODUCTION_SUBSET_TASK_VALID":
        raise ValueError(f"OLD_REPORT_INVALID:{old_report_path}")
    old_source_path = root / old_report["outputs"]["source_rows"]
    old_candidate_path = root / old_report["outputs"]["fact_candidates"]
    old_reject_path = root / old_report["outputs"]["reject_examples"]
    for path in (old_source_path, old_candidate_path, old_reject_path):
        if sha256_file(path) != old_report["output_hashes"][str(path.relative_to(root))]:
            raise ValueError(f"OLD_OUTPUT_HASH_MISMATCH:{path}")
    old_rows = load_jsonl(old_source_path)
    old_candidates = load_jsonl(old_candidate_path)
    if args.limit is not None:
        old_rows = old_rows[:args.limit]
    if len(old_rows) != len(old_candidates) and args.limit is None:
        raise ValueError("OLD_SOURCE_CANDIDATE_COUNT_MISMATCH")
    new_rows, new_candidates = [], []
    for row in old_rows:
        locator = row["source_locator"]
        shard_name = Path(locator["tfrecord"]).name
        migrated = dict(row)
        migrated["id"] = f"train:{args.task}:{shard_name}:{locator['record_index']}:{locator['qa_index']}"
        migrated.pop("source_record_hash", None)
        migrated["source_record_hash"] = record_hash(migrated)
        candidate = adapt(migrated, locator["qa_index"]).to_dict()
        if candidate["status"] != "WAITING_MEDIA" or not candidate["reconstruction_pass"]:
            raise ValueError(f"MIGRATED_CANDIDATE_INVALID:{migrated['id']}")
        candidate["status"] = "MEDIA_REFERENCE_VALID"
        new_rows.append(migrated)
        new_candidates.append(candidate)
    new_rows.sort(key=lambda row: (row["global_world_id"], row["id"]))
    new_candidates.sort(key=lambda row: (row["global_world_id"], row["source_item_id"]))
    if len({row["source_item_id"] for row in new_candidates}) != len(new_candidates):
        raise ValueError("MIGRATED_SOURCE_ITEM_ID_NOT_UNIQUE")

    output_root = root / "data/staging/ca_vqa_train" / args.source_revision / NEW_VERSION / args.task
    paths = {
        "source_rows": output_root / "source_rows.jsonl",
        "fact_candidates": output_root / "fact_candidates.jsonl",
        "reject_examples": root / "rejected/metadata/ca_vqa_train" / args.source_revision / NEW_VERSION / f"{args.task}.examples.jsonl",
    }
    values = {
        "source_rows": payload(new_rows), "fact_candidates": payload(new_candidates),
        "reject_examples": old_reject_path.read_bytes(),
    }
    for name, path in paths.items():
        write_versioned(path, values[name], args.resume)
    report = {
        **old_report,
        "output_version": NEW_VERSION,
        "id_policy": "task_plus_full_tfrecord_filename_plus_record_index_plus_qa_index",
        "migration_version": "ca_vqa_subset_id_migration_v1",
        "migration_reason": "Path.stem removed the tfrecord shard suffix and caused cross-shard ID collisions",
        "migration_source_report": str(old_report_path.relative_to(root)),
        "migrated_source_item_count": len(new_candidates),
        "input_hashes": {
            **old_report["input_hashes"],
            str(old_report_path.relative_to(root)): sha256_file(old_report_path),
            str(old_source_path.relative_to(root)): sha256_file(old_source_path),
            str(old_candidate_path.relative_to(root)): sha256_file(old_candidate_path),
            str(old_reject_path.relative_to(root)): sha256_file(old_reject_path),
        },
        "outputs": {name: str(path.relative_to(root)) for name, path in paths.items()},
        "output_hashes": {str(paths[name].relative_to(root)): sha256_bytes(value) for name, value in values.items()},
    }
    write_versioned(new_report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({
        "status": report["status"], "task": args.task, "output_version": NEW_VERSION,
        "migrated_source_item_count": len(new_candidates), "source_item_ids_unique": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
