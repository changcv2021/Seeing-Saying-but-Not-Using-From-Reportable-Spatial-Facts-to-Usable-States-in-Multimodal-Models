#!/usr/bin/env python3
"""Combine the formal L1-L3 available-media and L4 Qwen2.5-VL-7B scores."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


LABELS = ("SUPPORTED", "CONTRADICTORY", "UNKNOWN")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def div(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def merged_metrics(reports: list[dict[str, Any]]) -> dict[str, Any]:
    per_label: dict[str, dict[str, Any]] = {}
    for label in LABELS:
        rows = [report["overall_three_class"]["per_label"][label] for report in reports]
        tp = sum(int(row["tp"]) for row in rows)
        fp = sum(int(row["fp"]) for row in rows)
        fn = sum(int(row["fn"]) for row in rows)
        support = sum(int(row["support"]) for row in rows)
        precision = div(tp, tp + fp)
        recall = div(tp, tp + fn)
        per_label[label] = {
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": div(2 * precision * recall, precision + recall),
        }
    n = sum(row["support"] for row in per_label.values())
    return {
        "n": n,
        "accuracy": div(sum(row["tp"] for row in per_label.values()), n),
        "balanced_accuracy": sum(row["recall"] for row in per_label.values()) / len(LABELS),
        "macro_f1": sum(row["f1"] for row in per_label.values()) / len(LABELS),
        "per_label": per_label,
    }


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
    parser.add_argument("--l1-l3-score", type=Path, required=True)
    parser.add_argument("--l4-score", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    l1_l3 = json.loads(args.l1_l3_score.read_text(encoding="utf-8"))
    l4 = json.loads(args.l4_score.read_text(encoding="utf-8"))
    if l1_l3.get("status") != "PASS" or l4.get("status") != "PASS":
        raise ValueError("INPUT_SCORE_NOT_PASS")

    combined = merged_metrics([l1_l3, l4])
    complete_pairs = int(l1_l3["binary_complete_pair_count"]) + int(l4["binary_complete_pair_count"])
    pair_correct = round(float(l1_l3["pair_accuracy"]) * int(l1_l3["binary_complete_pair_count"]))
    pair_correct += round(float(l4["pair_accuracy"]) * int(l4["binary_complete_pair_count"]))
    evaluated = int(l1_l3["evaluated_count"]) + int(l4["evaluated_count"])
    strict_valid = int(l1_l3["strict_json_valid_count"]) + int(l4["strict_json_valid_count"])
    schema_valid = int(l1_l3["schema_valid_count"]) + int(l4["schema_valid_count"])
    runtime_errors = int(l1_l3["runtime_error_count"]) + int(l4["runtime_error_count"])

    report = rounded({
        "schema_version": "spaceconflict_qwen25vl7b_composite_evaluation_v1",
        "status": "PASS",
        "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
        "model_revision": "cc594898137f460bfe9f0759e9844b3ce807cfb5",
        "evaluation_scope": {
            "l1_l3": "all 14,713 locally available-media inputs from production_available_v10",
            "l1_l3_release_total": int(l1_l3["release_total_count"]),
            "l1_l3_unavailable_media": int(l1_l3["unavailable_media_count"]),
            "l4": "516 examples from the 225-pair balanced test slice of l4/v3_3",
            "composite_is_full_release": False,
        },
        "evaluated_count": evaluated,
        "runtime_error_count": runtime_errors,
        "strict_json_valid_count": strict_valid,
        "strict_json_valid_rate": div(strict_valid, evaluated),
        "schema_valid_count": schema_valid,
        "schema_valid_rate": div(schema_valid, evaluated),
        "overall_three_class": combined,
        "binary_complete_pair_count": complete_pairs,
        "pair_accuracy": div(pair_correct, complete_pairs),
        "l1_l3": l1_l3,
        "l4": l4,
        "input_hashes": {
            "l1_l3_score": sha256_file(args.l1_l3_score),
            "l4_score": sha256_file(args.l4_score),
        },
    })

    unknown = report["overall_three_class"]["per_label"]["UNKNOWN"]
    lines = [
        "# SpaceConflict × Qwen2.5-VL-7B 正式测评报告",
        "",
        f"状态：`{report['status']}`",
        "",
        "## 测评范围",
        "",
        "- L1–L3：`production_available_v10` 中本地媒体可用的 14,713/21,624 条。",
        "- L1–L3 未覆盖：6,911 条 SPAR-7M 输入，原因是上游原始图像尚未取得。",
        "- L4：`l4/v3_3` balanced test 的 225 个 pair，共 516 条输入。",
        "- 下列 Composite 指标是上述两个正式测试范围的汇总，不代表冻结 release 的 100% 媒体覆盖。",
        "",
        "## 总体成绩",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Evaluated examples | {report['evaluated_count']:,} |",
        f"| Three-class accuracy | {report['overall_three_class']['accuracy']:.4f} |",
        f"| Balanced accuracy | {report['overall_three_class']['balanced_accuracy']:.4f} |",
        f"| Macro-F1 | {report['overall_three_class']['macro_f1']:.4f} |",
        f"| Pair Accuracy | {report['pair_accuracy']:.4f} |",
        f"| Unknown precision | {unknown['precision']:.4f} |",
        f"| Unknown recall | {unknown['recall']:.4f} |",
        f"| Unknown F1 | {unknown['f1']:.4f} |",
        f"| Strict JSON valid | {report['strict_json_valid_rate']:.4f} |",
        f"| Output schema valid | {report['schema_valid_rate']:.4f} |",
        f"| Runtime failures | {report['runtime_error_count']} |",
        "",
        "## 分阶段成绩",
        "",
        "| Scope | Examples | Accuracy | Balanced accuracy | Macro-F1 | Pair Accuracy |",
        "|---|---:|---:|---:|---:|---:|",
        (
            f"| L1–L3 available-media | {l1_l3['evaluated_count']:,} | "
            f"{l1_l3['overall_three_class']['accuracy']:.4f} | "
            f"{l1_l3['overall_three_class']['balanced_accuracy']:.4f} | "
            f"{l1_l3['overall_three_class']['macro_f1']:.4f} | {l1_l3['pair_accuracy']:.4f} |"
        ),
        (
            f"| L4 balanced test | {l4['evaluated_count']:,} | "
            f"{l4['overall_three_class']['accuracy']:.4f} | "
            f"{l4['overall_three_class']['balanced_accuracy']:.4f} | "
            f"{l4['overall_three_class']['macro_f1']:.4f} | {l4['pair_accuracy']:.4f} |"
        ),
        "",
        "模型输出与 gold 在推理阶段保持物理分离；评分仅在推理完成后执行。",
        "",
    ]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "evaluated_count": evaluated,
        "accuracy": report["overall_three_class"]["accuracy"],
        "output_json": str(args.output_json),
        "output_md": str(args.output_md),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
