#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


TASKS = {"binary", "cardinality", "grounding2d", "grounding3d", "multichoice", "regression"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-validation", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    download = json.loads(args.download_validation.read_text(encoding="utf-8"))
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    failures = []
    if download.get("status") != "FULL_DOWNLOAD_VALID":
        failures.append({"gate": "DOWNLOAD_VALIDATION_STATUS", "actual": download.get("status")})
    if profile.get("status") != "PROFILED":
        failures.append({"gate": "PROFILE_STATUS", "actual": profile.get("status")})
    for key in ("download_verified_files", "download_verified_bytes"):
        expected_key = "expected_file_count" if key.endswith("files") else "expected_bytes"
        if profile.get(key) != download.get(expected_key):
            failures.append({"gate": "PROFILE_DOWNLOAD_COUNT", "field": key, "expected": download.get(expected_key), "actual": profile.get(key)})
    task_profiles = profile.get("task_profiles", {})
    if set(task_profiles) != TASKS:
        failures.append({"gate": "PROFILE_TASK_SET", "expected": sorted(TASKS), "actual": sorted(task_profiles)})
    for task, task_profile in task_profiles.items():
        if task_profile.get("num_examples_from_dataset_info", 0) <= 0:
            failures.append({"gate": "TASK_EXAMPLE_COUNT", "task": task, "actual": task_profile.get("num_examples_from_dataset_info")})
        if not task_profile.get("first_record_feature_summary"):
            failures.append({"gate": "TASK_FIRST_RECORD_SCHEMA", "task": task})
    if profile.get("train_examples_from_dataset_info") != sum(
        item.get("num_examples_from_dataset_info", 0) for item in task_profiles.values()
    ):
        failures.append({"gate": "TOTAL_EXAMPLE_COUNT"})
    expected_scope = "COMPLETE_ACQUISITION_INVENTORY_AND_DECLARED_COUNTS_PLUS_FIRST_RECORD_SCHEMA_PER_TASK"
    if profile.get("profile_scope") != expected_scope:
        failures.append({"gate": "PROFILE_SCOPE_DECLARATION", "expected": expected_scope, "actual": profile.get("profile_scope")})
    if "FULL_TFRECORD_QA_DISTRIBUTION" not in profile.get("not_claimed", []):
        failures.append({"gate": "PROFILE_LIMITATION_NOT_DECLARED"})
    if profile.get("val_archive_bytes") != 31650263144:
        failures.append({"gate": "VAL_ARCHIVE_BYTES", "actual": profile.get("val_archive_bytes")})
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "audit_version": "ca_vqa_full_profile_audit_v1",
        "status": "FULL_ACQUISITION_PROFILE_VALID" if not failures else "REJECTED",
        "download_verified_files": download.get("verified_file_count"),
        "download_verified_bytes": download.get("verified_bytes"),
        "train_task_count": len(task_profiles),
        "train_examples_from_dataset_info": profile.get("train_examples_from_dataset_info"),
        "failure_count": len(failures), "failures": failures,
        "next_gate": "PRODUCTION_SUBSET_STREAM_PROFILE_AND_ADAPT" if not failures else "ACQUISITION_OR_PROFILE_REPAIR_REQUIRED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
