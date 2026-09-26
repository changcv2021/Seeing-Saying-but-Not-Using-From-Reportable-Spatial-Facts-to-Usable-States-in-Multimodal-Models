#!/usr/bin/env python3
"""Score blind SpaceConflict production_available_v10 model predictions."""

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


def write_versioned(path: Path, text: str, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"OUTPUT_EXISTS:{path}")
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"NONDETERMINISTIC_OUTPUT:{path}")
        return
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requested-samples", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, nargs="+", required=True)
    parser.add_argument("--media-report", type=Path, required=True)
    parser.add_argument("--claims", type=Path, default=ROOT / "release/production_available_v10/claims.jsonl")
    parser.add_argument("--unknown", type=Path, default=ROOT / "release/production_available_v10/unknown_challenge.jsonl")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--run-id", default="qwen25vl7b_v10_cross_source_smoke_20260903")
    parser.add_argument(
        "--evaluation-kind", choices=("smoke", "available_media_baseline"), default="smoke",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    requests = read_jsonl(args.requested_samples)
    predictions = [row for path in args.predictions for row in read_jsonl(path)]
    if args.limit is not None:
        requests = requests[:args.limit]
    request_ids = [row["sample_id"] for row in requests]
    prediction_by_id = {row["sample_id"]: row for row in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ValueError("DUPLICATE_PREDICTION_IDS")
    missing = sorted(set(request_ids) - set(prediction_by_id))
    extra = sorted(set(prediction_by_id) - set(request_ids))
    if missing or extra:
        raise ValueError(f"PREDICTION_COVERAGE_MISMATCH:missing={len(missing)}:extra={len(extra)}")
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "run_id": args.run_id, "evaluated": len(requests)}, sort_keys=True))
        return 0

    claims = {row["sample_id"]: row for row in read_jsonl(args.claims)}
    unknown = {row["sample_id"]: row for row in read_jsonl(args.unknown)}
    gold_by_id = {**claims, **unknown}
    media_report = json.loads(args.media_report.read_text(encoding="utf-8"))
    pair_meta = {row["pair_id"]: row for row in media_report["selection"] if row.get("pair_id")}
    unknown_meta = {row["sample_id"]: row for row in media_report["selection"] if row.get("sample_id")}
    scored = []
    for request in requests:
        sample_id = request["sample_id"]
        if sample_id not in gold_by_id:
            raise ValueError(f"GOLD_MISSING:{sample_id}")
        prediction = prediction_by_id[sample_id]
        predicted = (prediction.get("prediction") or {}).get("label")
        expected = gold_by_id[sample_id]["label"]
        meta = pair_meta.get(request.get("pair_id")) or unknown_meta.get(sample_id) or {}
        scored.append({
            "sample_id": sample_id, "pair_id": request.get("pair_id"), "component": request["component"],
            "gold": expected, "prediction": predicted, "correct": expected == predicted,
            "strict_json_valid": bool((prediction.get("prediction") or {}).get("strict_json_valid")),
            "schema_valid": bool((prediction.get("prediction") or {}).get("schema_valid")),
            "runtime_error": prediction.get("error"), "stratum": meta.get("stratum"),
            "dataset": meta.get("dataset"), "level": meta.get("level"), "track": meta.get("track"),
            "operator_id": meta.get("operator_id"), "media_type": meta.get("media_type"),
        })

    metrics = classification_metrics(
        [row["gold"] for row in scored], [row["prediction"] for row in scored], LABELS,
    )
    pairs: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in scored:
        if row["component"] == "binary":
            pairs[row["pair_id"]].append(row)
    complete_pairs = [rows for rows in pairs.values() if len(rows) == 2]
    pair_accuracy = (
        sum(all(row["correct"] for row in rows) for rows in complete_pairs) / len(complete_pairs)
        if complete_pairs else None
    )
    grouped: dict[str, dict[str, Any]] = {}
    for field in ("stratum", "dataset", "level", "track", "operator_id", "media_type", "component"):
        grouped[field] = {}
        for value in sorted({str(row[field]) for row in scored if row.get(field) is not None}):
            rows = [row for row in scored if str(row.get(field)) == value]
            grouped[field][value] = {"n": len(rows), "accuracy": sum(row["correct"] for row in rows) / len(rows)}

    release_counts = media_report.get("release_counts") or {}
    release_total = int(release_counts.get("claims", 0)) + int(release_counts.get("unknown", 0))
    is_baseline = args.evaluation_kind == "available_media_baseline"
    report = rounded({
        "schema_version": (
            "spaceconflict_v10_mllm_available_media_score_v1"
            if is_baseline else "spaceconflict_v10_mllm_smoke_score_v1"
        ),
        "status": "PASS", "evaluation_kind": args.evaluation_kind,
        "run_id": args.run_id, "seed": args.seed, "requested_count": len(requests),
        "evaluated_count": len(scored), "missing_prediction_count": 0,
        "release_total_count": release_total,
        "unavailable_media_count": int(media_report.get("reject_count", 0)),
        "evaluation_coverage_rate": (len(scored) / release_total if release_total else None),
        "runtime_error_count": sum(bool(row["runtime_error"]) for row in scored),
        "strict_json_valid_count": sum(row["strict_json_valid"] for row in scored),
        "strict_json_valid_rate": sum(row["strict_json_valid"] for row in scored) / len(scored),
        "schema_valid_count": sum(row["schema_valid"] for row in scored),
        "schema_valid_rate": sum(row["schema_valid"] for row in scored) / len(scored),
        "overall_three_class": metrics, "binary_complete_pair_count": len(complete_pairs),
        "pair_accuracy": pair_accuracy, "grouped_accuracy": grouped,
        "format_diagnostics": {
            "invalid_json_sample_ids": [row["sample_id"] for row in scored if not row["strict_json_valid"]],
            "invalid_schema_sample_ids": [row["sample_id"] for row in scored if not row["schema_valid"]],
            "runtime_error_sample_ids": [row["sample_id"] for row in scored if row["runtime_error"]],
        },
    })
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    title = (
        "# SpaceConflict L1-L3 Qwen2.5-VL-7B Available-Media Baseline"
        if is_baseline else "# SpaceConflict L1-L3 cross-source Qwen2.5-VL smoke"
    )
    lines = [
        title,
        "", f"Status: `{report['status']}`", "", "| Metric | Value |", "|---|---:|",
        f"| Evaluated examples | {report['evaluated_count']} |",
        f"| Full-release examples | {report['release_total_count']} |",
        f"| Evaluation coverage | {report['evaluation_coverage_rate']:.4f} |",
        f"| Unavailable-media examples | {report['unavailable_media_count']} |",
        f"| Strict JSON valid | {report['strict_json_valid_rate']:.4f} |",
        f"| Output schema valid | {report['schema_valid_rate']:.4f} |",
        f"| Three-class accuracy | {report['overall_three_class']['accuracy']:.4f} |",
        f"| Three-class macro-F1 | {report['overall_three_class']['macro_f1']:.4f} |",
        f"| Complete binary pairs | {report['binary_complete_pair_count']} |",
        f"| Pair Accuracy | {report['pair_accuracy']:.4f} |" if report["pair_accuracy"] is not None else "| Pair Accuracy | Not available |",
        f"| Runtime failures | {report['runtime_error_count']} |", "",
        (
            "This is the formal baseline for all 14,713 inputs whose upstream media are locally available. "
            "It is not a 21,624/21,624 full-release result because 6,911 SPAR-7M inputs lack upstream images."
            if is_baseline else
            "This is a format and integration smoke, not the full 21,624-example baseline."
        ), "",
    ]
    write_versioned(args.output_json, json_text, args.resume)
    write_versioned(args.output_md, "\n".join(lines), args.resume)
    print(json_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
