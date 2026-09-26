from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from typing import Any


TASKS = ("binary", "cardinality", "grounding2d", "grounding3d", "multichoice", "regression")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def first_tfrecord(path: Path) -> bytes:
    with path.open("rb") as handle:
        length_bytes = handle.read(8)
        if len(length_bytes) != 8:
            raise ValueError(f"TFRECORD_EMPTY:{path}")
        length = struct.unpack("<Q", length_bytes)[0]
        if len(handle.read(4)) != 4:
            raise ValueError(f"TFRECORD_TRUNCATED_LENGTH_CRC:{path}")
        payload = handle.read(length)
        if len(payload) != length or len(handle.read(4)) != 4:
            raise ValueError(f"TFRECORD_TRUNCATED_PAYLOAD:{path}")
        return payload


def feature_summary(example: Any) -> dict[str, Any]:
    result = {}
    for key, feature in sorted(example.features.feature.items()):
        kind = feature.WhichOneof("kind")
        values = list(getattr(feature, kind).value) if kind else []
        row: dict[str, Any] = {"kind": kind, "value_count": len(values)}
        if kind == "bytes_list":
            row["byte_lengths"] = [len(value) for value in values[:8]]
            previews = []
            for value in values[:8]:
                try:
                    text = value.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if len(text) <= 500:
                    previews.append(text)
            if previews:
                row["utf8_previews"] = previews
        else:
            row["value_preview"] = values[:16]
        result[key] = row
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--download-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    summary_path = args.download_run / "summary.txt"
    summary = dict(line.split("=", 1) for line in summary_path.read_text().splitlines() if "=" in line) if summary_path.exists() else {}
    if not args.allow_incomplete and (summary.get("success_count") != "6157" or summary.get("failure_count") != "0"):
        raise RuntimeError(f"DOWNLOAD_NOT_COMPLETE:{summary}")
    from tensorflow.train import Example

    task_profiles = {}
    question_previews = []
    total_examples = 0
    input_hashes = {str(args.download_run / "results.tsv"): sha256(args.download_run / "results.tsv")}
    if summary_path.exists():
        input_hashes[str(summary_path)] = sha256(summary_path)
    for task in TASKS:
        task_dir = args.data_root / "train" / f"cavqa_{task}" / "1.0.0"
        info_path = task_dir / "dataset_info.json"
        features_path = task_dir / "features.json"
        shard = task_dir / f"cavqa_{task}-train.tfrecord-00000-of-01024"
        if not shard.exists():
            if args.allow_incomplete:
                continue
            raise FileNotFoundError(shard)
        if not args.allow_incomplete:
            for path in (info_path, features_path):
                if not path.exists():
                    raise FileNotFoundError(path)
        info = json.loads(info_path.read_text()) if info_path.exists() else {}
        features = json.loads(features_path.read_text()) if features_path.exists() else {}
        example = Example.FromString(first_tfrecord(shard))
        summary_features = feature_summary(example)
        split_count = sum(
            int(value.get("numExamples") or sum(int(item) for item in value.get("shardLengths", [])))
            for value in info.get("splits", [])
        )
        total_examples += split_count
        for key, value in summary_features.items():
            if "question" in key.casefold() or "answer" in key.casefold():
                question_previews.append({"task": task, "feature": key, "preview": value.get("utf8_previews", [])})
        task_profiles[task] = {
            "num_examples_from_dataset_info": split_count,
            "dataset_info": info,
            "features_schema": features,
            "first_record_feature_summary": summary_features,
            "first_shard": str(shard),
            "first_shard_bytes": shard.stat().st_size,
        }
        if info_path.exists():
            input_hashes[str(info_path)] = sha256(info_path)
        if features_path.exists():
            input_hashes[str(features_path)] = sha256(features_path)
    val_tar = args.data_root / "val" / "cavqa_val.tar.gz"
    if not val_tar.exists() and not args.allow_incomplete:
        raise FileNotFoundError(val_tar)
    report = {
        "schema_version": "1.0", "dataset": "ca_vqa", "profile_version": "ca_vqa_profile_v1",
        "status": "PILOT_PROFILED" if args.allow_incomplete else "PROFILED", "source_revision": "080812355c21a40f437ed03d4ae558d35bfa2929",
        "download_verified_files": None if args.allow_incomplete else 6157, "download_verified_bytes": None if args.allow_incomplete else 11575534117935,
        "train_task_count": len(task_profiles), "train_examples_from_dataset_info": total_examples,
        "val_archive": str(val_tar), "val_archive_bytes": val_tar.stat().st_size if val_tar.exists() else None,
        "task_profiles": task_profiles, "question_answer_feature_previews": question_previews,
        "profile_scope": "COMPLETE_ACQUISITION_INVENTORY_AND_DECLARED_COUNTS_PLUS_FIRST_RECORD_SCHEMA_PER_TASK",
        "not_claimed": ["FULL_TFRECORD_QA_DISTRIBUTION", "FULL_MEDIA_DECODE"],
        "task_policy": {
            "production_allow": ["binary", "cardinality", "multichoice"],
            "exclude_final_task": ["grounding2d", "grounding3d", "regression"],
            "note": "Final adapter remains subject to exact question-family and source-GT reconstruction checks.",
        },
        "input_hashes": input_hashes,
        "next_gate": "FULL_DOWNLOAD_PENDING" if args.allow_incomplete else "CA_VQA_ADAPTER_PILOT_PENDING",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output.exists() and args.output.read_text() != payload:
        raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{args.output}")
    args.output.write_text(payload)
    print(json.dumps({key: report[key] for key in ("status", "train_task_count", "train_examples_from_dataset_info", "val_archive_bytes", "next_gate")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
