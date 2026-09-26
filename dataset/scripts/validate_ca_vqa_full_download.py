#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TASKS = ("binary", "cardinality", "grounding2d", "grounding3d", "multichoice", "regression")
URL_PREFIX = "https://ml-site.cdn-apple.com/datasets/cavqa/"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_summary(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-run", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = args.download_run.resolve()
    data_root = args.data_root.resolve()
    manifest_path = run / "manifest_selected.tsv"
    results_path = run / "results.tsv"
    summary_path = run / "summary.txt"
    failures: list[dict[str, Any]] = []

    manifest: dict[str, dict[str, Any]] = {}
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for url, size, etag in csv.reader(handle, delimiter="\t"):
            if url in manifest:
                failures.append({"gate": "DUPLICATE_MANIFEST_URL", "url": url})
            manifest[url] = {"bytes": int(size), "etag": etag}
    results: dict[str, dict[str, Any]] = {}
    with results_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            url = row["url"]
            if url in results:
                failures.append({"gate": "DUPLICATE_RESULT_URL", "url": url})
            results[url] = row
    missing_urls = sorted(set(manifest) - set(results))
    extra_urls = sorted(set(results) - set(manifest))
    if missing_urls:
        failures.append({"gate": "RESULT_URL_MISSING", "count": len(missing_urls), "examples": missing_urls[:10]})
    if extra_urls:
        failures.append({"gate": "RESULT_URL_EXTRA", "count": len(extra_urls), "examples": extra_urls[:10]})

    status_counts: Counter[str] = Counter()
    task_shard_counts: Counter[str] = Counter()
    task_metadata_counts: Counter[str] = Counter()
    verified_bytes = 0
    readonly_file_count = 0
    for url, expected in manifest.items():
        row = results.get(url)
        if row is None:
            continue
        status_counts[row["status"]] += 1
        if row["status"] not in {"DOWNLOADED_AND_VERIFIED", "ALREADY_VALID"}:
            failures.append({"gate": "NON_SUCCESS_STATUS", "url": url, "status": row["status"]})
            continue
        if int(row["bytes"]) != expected["bytes"]:
            failures.append({"gate": "RESULT_SIZE_MISMATCH", "url": url, "expected": expected["bytes"], "actual": row["bytes"]})
        if not SHA256_PATTERN.fullmatch(row["sha256"]):
            failures.append({"gate": "RESULT_SHA256_INVALID", "url": url})
        if not url.startswith(URL_PREFIX):
            failures.append({"gate": "URL_PREFIX_INVALID", "url": url})
            continue
        relative = url.removeprefix(URL_PREFIX)
        expected_path = (data_root / relative).resolve()
        try:
            expected_path.relative_to(data_root)
        except ValueError:
            failures.append({"gate": "PATH_ESCAPE", "url": url, "path": str(expected_path)})
            continue
        result_path = Path(row["local_path"]).resolve()
        if result_path != expected_path:
            failures.append({"gate": "RESULT_PATH_MISMATCH", "url": url, "expected": str(expected_path), "actual": str(result_path)})
            continue
        if not expected_path.is_file() or expected_path.is_symlink():
            failures.append({"gate": "FILE_MISSING_OR_SYMLINK", "url": url, "path": str(expected_path)})
            continue
        actual_size = expected_path.stat().st_size
        if actual_size != expected["bytes"]:
            failures.append({"gate": "ON_DISK_SIZE_MISMATCH", "url": url, "expected": expected["bytes"], "actual": actual_size})
        if expected_path.stat().st_mode & 0o222 == 0:
            readonly_file_count += 1
        verified_bytes += actual_size
        parts = Path(relative).parts
        if len(parts) >= 4 and parts[0] == "train" and parts[1].startswith("cavqa_"):
            task = parts[1].removeprefix("cavqa_")
            name = parts[-1]
            if ".tfrecord-" in name:
                task_shard_counts[task] += 1
            elif name in {"dataset_info.json", "features.json"}:
                task_metadata_counts[task] += 1
    partial_files = [str(path) for path in data_root.rglob("*.part")]
    if partial_files:
        failures.append({"gate": "PARTIAL_FILES_REMAIN", "count": len(partial_files), "examples": partial_files[:10]})
    for task in TASKS:
        if task_shard_counts[task] != 1024:
            failures.append({"gate": "TASK_SHARD_COUNT", "task": task, "expected": 1024, "actual": task_shard_counts[task]})
        if task_metadata_counts[task] != 2:
            failures.append({"gate": "TASK_METADATA_COUNT", "task": task, "expected": 2, "actual": task_metadata_counts[task]})
    summary = read_summary(summary_path)
    expected_files = len(manifest)
    expected_bytes = sum(row["bytes"] for row in manifest.values())
    summary_expectations = {
        "selected_files": str(expected_files), "selected_bytes": str(expected_bytes),
        "success_count": str(expected_files), "failure_count": "0", "xargs_status": "0",
    }
    for key, expected in summary_expectations.items():
        if summary.get(key) != expected:
            failures.append({"gate": "SUMMARY_MISMATCH", "field": key, "expected": expected, "actual": summary.get(key)})
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "validation_version": "ca_vqa_full_download_v1",
        "status": "FULL_DOWNLOAD_VALID" if not failures else "REJECTED",
        "expected_file_count": expected_files, "result_file_count": len(results),
        "verified_file_count": sum(status_counts[value] for value in ("DOWNLOADED_AND_VERIFIED", "ALREADY_VALID")),
        "expected_bytes": expected_bytes, "verified_bytes": verified_bytes,
        "readonly_file_count": readonly_file_count,
        "status_counts": dict(sorted(status_counts.items())),
        "task_shard_counts": {task: task_shard_counts[task] for task in TASKS},
        "task_metadata_counts": {task: task_metadata_counts[task] for task in TASKS},
        "partial_file_count": len(partial_files), "failure_count": len(failures), "failures": failures,
        "hash_policy": "PER_FILE_SHA256_COMPUTED_AND_RECORDED_DURING_DOWNLOAD; POST_DOWNLOAD_GATE_VALIDATES_RECORD_FORMAT_SIZE_PATH_AND_COMPLETE_INVENTORY_WITHOUT_READING_11.5TB_AGAIN",
        "input_hashes": {
            str(manifest_path): sha256(manifest_path), str(results_path): sha256(results_path), str(summary_path): sha256(summary_path),
        },
        "next_gate": "FULL_PROFILE_AUDIT_PENDING" if not failures else "DOWNLOAD_REPAIR_REQUIRED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "verified_file_count", "verified_bytes", "failure_count", "next_gate")}, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
