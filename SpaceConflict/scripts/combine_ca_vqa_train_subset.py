#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_bytes, sha256_file


TASKS = ("binary", "cardinality", "multichoice")
COMBINE_VERSION = "ca_vqa_train_production_subset_combined_v1"


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
    parser.add_argument("--input-version", default="ca_vqa_train_production_subset_v2")
    parser.add_argument("--task-report-version", default="v2")
    parser.add_argument("--combine-version", default=COMBINE_VERSION)
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--report-name", default="train_production_subset.combined.v1.json")
    parser.add_argument("--world-cap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    tasks = tuple(item.strip() for item in args.tasks.split(",") if item.strip())
    if not tasks or set(tasks) - set(TASKS):
        raise ValueError(f"INVALID_TASK_SET:{tasks}")
    if args.limit is not None:
        args.world_cap = min(args.world_cap, args.limit)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "run_id": args.run_id, "world_cap": args.world_cap}))
        return 0
    task_reports, all_rows, all_candidates, reject_examples = {}, [], [], []
    input_hashes = {}
    for task in tasks:
        report_path = root / "reports/ca_vqa" / f"train_production_subset.{task}.{args.task_report_version}.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "PRODUCTION_SUBSET_TASK_VALID":
            raise ValueError(f"TASK_REPORT_NOT_VALID:{task}:{report.get('status')}")
        task_reports[task] = report
        input_hashes[str(report_path.relative_to(root))] = sha256_file(report_path)
        source_path = root / report["outputs"]["source_rows"]
        candidate_path = root / report["outputs"]["fact_candidates"]
        reject_path = root / report["outputs"]["reject_examples"]
        for path in (source_path, candidate_path, reject_path):
            expected = report["output_hashes"][str(path.relative_to(root))]
            if sha256_file(path) != expected:
                raise ValueError(f"TASK_OUTPUT_HASH_MISMATCH:{path}")
            input_hashes[str(path.relative_to(root))] = expected
        all_rows.extend(load_jsonl(source_path))
        all_candidates.extend(load_jsonl(candidate_path))
        reject_examples.extend(load_jsonl(reject_path))

    world_ids = sorted(
        {row["global_world_id"] for row in all_candidates},
        key=lambda world_id: hashlib.sha256(f"{args.seed}\0{world_id}".encode()).hexdigest(),
    )
    selected_worlds = set(world_ids[:args.world_cap])
    source_by_item = {f"ca_vqa:{row['task']}:{row['id']}": row for row in all_rows}
    candidates = sorted(
        (row for row in all_candidates if row["global_world_id"] in selected_worlds),
        key=lambda row: (row["global_world_id"], row["source_item_id"]),
    )
    source_rows = [source_by_item[row["source_item_id"]] for row in candidates]
    if len({row["source_item_id"] for row in candidates}) != len(candidates):
        raise ValueError("DUPLICATE_SELECTED_SOURCE_ITEM")
    if len(source_rows) != len(candidates):
        raise ValueError("SELECTED_SOURCE_ROW_MISSING")
    reject_examples.sort(key=lambda row: hashlib.sha256(compact(row)).hexdigest())
    reject_examples = reject_examples[:512]

    output_root = root / "data/staging/ca_vqa_train" / args.source_revision / args.combine_version
    paths = {
        "source_rows": output_root / "source_rows.jsonl",
        "fact_candidates": output_root / "fact_candidates.jsonl",
        "reject_examples": root / "rejected/metadata/ca_vqa_train" / args.source_revision / f"{args.combine_version}.examples.jsonl",
    }
    values = {
        "source_rows": payload(source_rows), "fact_candidates": payload(candidates),
        "reject_examples": payload(reject_examples),
    }
    for name, path in paths.items():
        write_versioned(path, values[name], args.resume)
    candidates_by_task = Counter(row["source_task"] for row in candidates)
    worlds_by_task = {
        task: len({row["global_world_id"] for row in candidates if row["source_task"] == task})
        for task in tasks
    }
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "extract_version": args.combine_version,
        "adapter_version": "ca_vqa_train_tfrecord_v1", "status": "TRAIN_PRODUCTION_SUBSET_COMBINED",
        "source_revision": args.source_revision, "seed": args.seed,
        "source_task_reports": {task: f"reports/ca_vqa/train_production_subset.{task}.{args.task_report_version}.json" for task in tasks},
        "available_world_count_before_cap": len(world_ids), "world_cap": args.world_cap,
        "world_count": len(selected_worlds), "source_qa_count": len(source_rows),
        "adapter_candidate_count": len(candidates), "selected_candidate_count_by_task": dict(sorted(candidates_by_task.items())),
        "selected_world_count_by_task": worlds_by_task,
        "world_selection_policy": "lowest_seeded_content_world_hash_independent_of_question_answer_and_label",
        "candidate_cap_per_world_per_task": 8, "source_reconstruction_rate": 1.0,
        "media_redistributed": False, "input_hashes": dict(sorted(input_hashes.items())),
        "outputs": {name: str(path.relative_to(root)) for name, path in paths.items()},
        "output_hashes": {str(paths[name].relative_to(root)): sha256_bytes(value) for name, value in values.items()},
        "next_gate": "PRODUCTION_SUBSET_MEDIA_LOCATOR_CANONICAL_AND_GRAPH_VALIDATION",
    }
    report_path = root / "reports/ca_vqa" / args.report_name
    write_versioned(report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n", args.resume)
    print(json.dumps({key: report[key] for key in (
        "status", "available_world_count_before_cap", "world_count", "adapter_candidate_count",
        "selected_candidate_count_by_task", "next_gate",
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
