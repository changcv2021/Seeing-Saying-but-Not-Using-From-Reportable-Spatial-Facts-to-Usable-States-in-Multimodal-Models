#!/usr/bin/env python3
"""Score SpaceConflict L4 predictions against physically separate gold files."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from spaceconflict.mllm_l4 import LABELS, classification_metrics


ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {key: rounded(child) for key, child in value.items()}
    if isinstance(value, list):
        return [rounded(child) for child in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested-samples", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--binary-gold", type=Path, default=ROOT / "l4/v3_3/release/gold.l4_three_part_v3.jsonl")
    parser.add_argument("--unknown-gold", type=Path, default=ROOT / "l4/v3_3/release/gold.l4_unknown_v3.jsonl")
    parser.add_argument("--annotated-pairs", type=Path, default=ROOT / "l4/v3_3/derived_annotations/track_annotations_v1/pairs.l4_three_part_v3.track_annotated_v1.jsonl")
    parser.add_argument("--unknown-records", type=Path, default=ROOT / "l4/v3_3/release/unknown_challenge.l4_v3.jsonl")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--allow-subset", action="store_true")
    args = parser.parse_args()

    requested = read_jsonl(args.requested_samples)
    request_by_id = {row["sample_id"]: row for row in requested}
    if len(request_by_id) != len(requested):
        raise ValueError("Duplicate IDs in requested samples")
    predictions = [row for path in args.predictions for row in read_jsonl(path)]
    prediction_by_id = {row["sample_id"]: row for row in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ValueError("Duplicate prediction IDs across shards")
    extra = sorted(set(prediction_by_id) - set(request_by_id))
    missing = sorted(set(request_by_id) - set(prediction_by_id))
    if extra or (missing and not args.allow_subset):
        raise ValueError(f"Prediction coverage mismatch: missing={len(missing)}, extra={len(extra)}")

    evaluated_ids = [row["sample_id"] for row in requested if row["sample_id"] in prediction_by_id]
    binary_gold = {row["example_id"]: row for row in read_jsonl(args.binary_gold)}
    unknown_gold = {row["sample_id"]: row for row in read_jsonl(args.unknown_gold)}
    gold_by_id = {**binary_gold, **unknown_gold}
    absent_gold = [sample_id for sample_id in evaluated_ids if sample_id not in gold_by_id]
    if absent_gold:
        raise ValueError(f"Gold missing for {len(absent_gold)} evaluated IDs")

    pair_metadata = {row["pair_id"]: row for row in read_jsonl(args.annotated_pairs)}
    unknown_metadata = {row["sample_id"]: row for row in read_jsonl(args.unknown_records)}
    scored = []
    for sample_id in evaluated_ids:
        request = request_by_id[sample_id]
        prediction = prediction_by_id[sample_id]
        expected = gold_by_id[sample_id]["label"]
        predicted = (prediction.get("prediction") or {}).get("label")
        pair = pair_metadata.get(request.get("pair_id")) or {}
        unknown = unknown_metadata.get(sample_id) or {}
        scored.append({
            "sample_id": sample_id,
            "pair_id": request.get("pair_id"),
            "component": request["component"],
            "gold": expected,
            "prediction": predicted,
            "correct": expected == predicted,
            "strict_json_valid": bool((prediction.get("prediction") or {}).get("strict_json_valid")),
            "schema_valid": bool((prediction.get("prediction") or {}).get("schema_valid")),
            "runtime_error": prediction.get("error"),
            "has_media": bool(request.get("media")),
            "origin": request.get("l4_origin"),
            "primary_track": (pair.get("task") or {}).get("primary_track"),
            "operator_id": (pair.get("task") or {}).get("operator_id"),
            "transition_family": pair.get("transition_family"),
            "native_subtype": pair.get("native_subtype"),
            "dependency_type": pair.get("dependency_type"),
            "unknown_reason": unknown.get("unknown_axis"),
        })

    overall = classification_metrics(
        [row["gold"] for row in scored], [row["prediction"] for row in scored], LABELS,
    )
    binary = [row for row in scored if row["component"] == "binary"]
    unknown = [row for row in scored if row["component"] == "unknown"]
    binary_metrics = classification_metrics(
        [row["gold"] for row in binary], [row["prediction"] for row in binary], LABELS[:2],
    )

    pairs: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in binary:
        pairs[row["pair_id"]].append(row)
    complete_pairs = [rows for rows in pairs.values() if len(rows) == 2]
    pair_accuracy = (
        sum(all(row["correct"] for row in rows) for rows in complete_pairs) / len(complete_pairs)
        if complete_pairs else None
    )

    grouped: dict[str, dict[str, Any]] = {}
    for field in (
        "origin", "primary_track", "operator_id", "transition_family",
        "native_subtype", "dependency_type", "unknown_reason", "has_media",
    ):
        values = sorted({str(row[field]) for row in scored if row.get(field) is not None})
        grouped[field] = {}
        for value in values:
            rows = [row for row in scored if str(row.get(field)) == value]
            grouped[field][value] = {
                "n": len(rows),
                "accuracy": sum(row["correct"] for row in rows) / len(rows),
            }

    report = rounded({
        "schema_version": "spaceconflict_l4_mllm_score_v1",
        "status": "PASS",
        "requested_count": len(requested),
        "evaluated_count": len(scored),
        "missing_prediction_count": len(missing),
        "runtime_error_count": sum(bool(row["runtime_error"]) for row in scored),
        "strict_json_valid_count": sum(row["strict_json_valid"] for row in scored),
        "strict_json_valid_rate": sum(row["strict_json_valid"] for row in scored) / len(scored),
        "schema_valid_count": sum(row["schema_valid"] for row in scored),
        "schema_valid_rate": sum(row["schema_valid"] for row in scored) / len(scored),
        "overall_three_class": overall,
        "binary_claims": binary_metrics,
        "binary_complete_pair_count": len(complete_pairs),
        "pair_accuracy": pair_accuracy,
        "unknown_count": len(unknown),
        "unknown_precision": overall["per_label"]["UNKNOWN"]["precision"],
        "unknown_recall": overall["per_label"]["UNKNOWN"]["recall"],
        "unknown_f1": overall["per_label"]["UNKNOWN"]["f1"],
        "grouped_accuracy": grouped,
        "format_diagnostics": {
            "invalid_json_sample_ids": [row["sample_id"] for row in scored if not row["strict_json_valid"]],
            "invalid_schema_sample_ids": [row["sample_id"] for row in scored if not row["schema_valid"]],
            "runtime_error_sample_ids": [row["sample_id"] for row in scored if row["runtime_error"]],
        },
    })
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# SpaceConflict L4 Qwen2.5-VL Evaluation",
        "",
        f"Status: `{report['status']}`",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Evaluated examples | {report['evaluated_count']} |",
        f"| Strict JSON valid | {report['strict_json_valid_rate']:.4f} |",
        f"| Output schema valid | {report['schema_valid_rate']:.4f} |",
        f"| Three-class accuracy | {report['overall_three_class']['accuracy']:.4f} |",
        f"| Three-class balanced accuracy | {report['overall_three_class']['balanced_accuracy']:.4f} |",
        f"| Three-class macro-F1 | {report['overall_three_class']['macro_f1']:.4f} |",
        f"| Binary claim accuracy | {report['binary_claims']['accuracy']:.4f} |",
        f"| Complete binary pairs | {report['binary_complete_pair_count']} |",
        f"| Pair Accuracy | {report['pair_accuracy']:.4f} |" if report["pair_accuracy"] is not None else "| Pair Accuracy | Not available |",
        f"| Unknown precision | {report['unknown_precision']:.4f} |",
        f"| Unknown recall | {report['unknown_recall']:.4f} |",
        f"| Unknown F1 | {report['unknown_f1']:.4f} |",
        f"| Runtime failures | {report['runtime_error_count']} |",
        "",
        "This report scores only model outputs. Oracle smoke fixtures are not used as a baseline.",
        "",
    ]
    args.output_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
