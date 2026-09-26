from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from ..hashing import sha256_file
from .common import output_hashes, read_jsonl, write_json, write_jsonl


def _balanced_test_slice(
    pairs: list[dict[str, Any]], *, target: int, seed: int,
) -> list[dict[str, Any]]:
    test = [row for row in pairs if row["split"] == "test"]
    native = [row for row in test if row["l4_origin"] == "SOURCE_NATIVE"]
    controlled = [row for row in test if row["l4_origin"] == "BENCHMARK_CONTROLLED"]
    native_target = min(len(native), round(target * 0.40))
    controlled_target = min(len(controlled), target - native_target)
    if native_target + controlled_target < target:
        native_target = min(len(native), target - controlled_target)
    key = lambda row: hashlib.sha256(f"{seed}:{row['pair_id']}".encode()).hexdigest()
    return sorted(native, key=key)[:native_target] + sorted(controlled, key=key)[:controlled_target]


def build_release(
    *, native_pairs_path: Path, native_inputs_path: Path, native_gold_path: Path,
    controlled_pairs_path: Path, controlled_inputs_path: Path, controlled_gold_path: Path,
    unknown_path: Path, unknown_inputs_path: Path, unknown_gold_path: Path,
    config_path: Path, output_dir: Path, seed: int, run_id: str,
    dry_run: bool, resume: bool,
) -> dict[str, Any]:
    outputs = {
        "pairs": output_dir / "pairs.l4_three_part_v3.jsonl",
        "model_inputs": output_dir / "model_inputs.l4_three_part_v3.jsonl",
        "gold": output_dir / "gold.l4_three_part_v3.jsonl",
        "unknown": output_dir / "unknown_challenge.l4_v3.jsonl",
        "unknown_inputs": output_dir / "model_inputs.l4_unknown_v3.jsonl",
        "unknown_gold": output_dir / "gold.l4_unknown_v3.jsonl",
        "test_slice": output_dir / "test_slices/l4_balanced_test_v3.jsonl",
        "native_test": output_dir / "test_slices/l4_native_test_v3.jsonl",
        "controlled_test": output_dir / "test_slices/l4_controlled_test_v3.jsonl",
        "manifest": output_dir / "manifest.json",
        "report": output_dir / "L4_THREE_PART_REPORT_CN.md",
    }
    if dry_run:
        return {"status": "PLANNED", "outputs": {key: str(value) for key, value in outputs.items()}}
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    native = read_jsonl(native_pairs_path)
    controlled = read_jsonl(controlled_pairs_path)
    pairs = native + controlled
    model_inputs = read_jsonl(native_inputs_path) + read_jsonl(controlled_inputs_path)
    gold = read_jsonl(native_gold_path) + read_jsonl(controlled_gold_path)
    unknown = read_jsonl(unknown_path)
    unknown_inputs = read_jsonl(unknown_inputs_path)
    unknown_gold = read_jsonl(unknown_gold_path)
    errors: list[str] = []
    pair_ids = [row["pair_id"] for row in pairs]
    if len(pair_ids) != len(set(pair_ids)):
        errors.append("REJECT_DUPLICATE_SEMANTIC_SAMPLE")
    world_splits: dict[str, set[str]] = defaultdict(set)
    for row in pairs + unknown:
        world_splits[str(row["global_world_id"])].add(str(row["split"]))
    if any(len(splits) != 1 for splits in world_splits.values()):
        errors.append("REJECT_SPLIT_LEAKAGE")
    if any(row.get("validation", {}).get("final_status") != "AUTO_ACCEPTED" for row in pairs + unknown):
        errors.append("NON_AUTO_ACCEPTED_RECORD")
    test_pairs = [row for row in pairs if row["split"] == "test"]
    test_world_counts = Counter(str(row["base_scene_id"]) for row in test_pairs)
    test_world_family_counts = Counter(
        (str(row["base_scene_id"]), str(row["transition_family"])) for row in test_pairs
    )
    if any(value > 2 for value in test_world_counts.values()):
        errors.append("TEST_WORLD_PAIR_DENSITY_EXCEEDED")
    if any(value > 1 for value in test_world_family_counts.values()):
        errors.append("TEST_WORLD_FAMILY_DENSITY_EXCEEDED")
    if len(model_inputs) != len(pairs) * 2 or len(gold) != len(pairs) * 2:
        errors.append("BINARY_MODEL_GOLD_COUNT_MISMATCH")
    if len(unknown_inputs) != len(unknown) or len(unknown_gold) != len(unknown):
        errors.append("UNKNOWN_MODEL_GOLD_COUNT_MISMATCH")
    calibration = sum(row["dependency_type"] == "CALIBRATION" for row in pairs)
    controlled_share = len(controlled) / len(pairs) if pairs else 0.0
    calibration_share = calibration / len(pairs) if pairs else 0.0
    binary_min, binary_max = map(int, config["acceptable_binary_range"])
    unknown_min, unknown_max = map(int, config["unknown_target"])
    if not binary_min <= len(pairs) <= binary_max:
        errors.append("BINARY_TARGET_RANGE_SHORTFALL")
    if not unknown_min <= len(unknown) <= unknown_max:
        errors.append("UNKNOWN_TARGET_RANGE_SHORTFALL")
    if calibration_share > float(config["calibration_max_fraction"]):
        errors.append("CALIBRATION_RATIO_EXCEEDED")
    if controlled_share > float(config["controlled_absolute_max_fraction"]):
        errors.append("CONTROLLED_RATIO_EXCEEDED")
    test_low, test_high = map(int, config["test_binary_target"])
    test_target = min(test_high, max(test_low, 300))
    balanced_test = _balanced_test_slice(pairs, target=test_target, seed=seed)
    native_test = [row for row in pairs if row["split"] == "test" and row["l4_origin"] == "SOURCE_NATIVE"]
    controlled_test = [row for row in pairs if row["split"] == "test" and row["l4_origin"] == "BENCHMARK_CONTROLLED"]
    balanced_test_soft_target_met = test_low <= len(balanced_test) <= test_high
    write_jsonl(outputs["pairs"], pairs, resume=resume)
    write_jsonl(outputs["model_inputs"], model_inputs, resume=resume)
    write_jsonl(outputs["gold"], gold, resume=resume)
    write_jsonl(outputs["unknown"], unknown, resume=resume)
    write_jsonl(outputs["unknown_inputs"], unknown_inputs, resume=resume)
    write_jsonl(outputs["unknown_gold"], unknown_gold, resume=resume)
    write_jsonl(outputs["test_slice"], balanced_test, resume=resume)
    write_jsonl(outputs["native_test"], native_test, resume=resume)
    write_jsonl(outputs["controlled_test"], controlled_test, resume=resume)
    origin_counts = Counter(
        ("Native-" + str(row.get("native_subtype", "")).title())
        if row["l4_origin"] == "SOURCE_NATIVE" else
        ("Controlled-" + str(row["dependency_type"]).title())
        for row in pairs
    )
    transition_counts = Counter(row["transition_family"] for row in pairs)
    grounding_counts = Counter(row["grounding_mode"] for row in pairs)
    input_paths = (
        native_pairs_path, native_inputs_path, native_gold_path,
        controlled_pairs_path, controlled_inputs_path, controlled_gold_path,
        unknown_path, unknown_inputs_path, unknown_gold_path, config_path,
    )
    manifest = {
        "schema_version": "spaceconflict_l4_three_part_release_v3",
        "status": "L4_THREE_PART_RELEASE_VALID" if not errors else "L4_THREE_PART_RELEASE_SHORTFALL_OR_GATE_FAIL",
        "run_id": run_id, "seed": seed,
        "binary_pair_count": len(pairs), "binary_claim_count": len(model_inputs),
        "unknown_claim_count": len(unknown), "world_count": len(world_splits),
        "origin_counts": dict(sorted(origin_counts.items())),
        "transition_family_counts": dict(sorted(transition_counts.items())),
        "grounding_counts": dict(sorted(grounding_counts.items())),
        "split_counts": dict(sorted(Counter(row["split"] for row in pairs).items())),
        "unknown_split_counts": dict(sorted(Counter(row["split"] for row in unknown).items())),
        "calibration_fraction": calibration_share,
        "controlled_fraction": controlled_share,
        "balanced_test_count": len(balanced_test),
        "balanced_test_soft_target": [test_low, test_high],
        "balanced_test_soft_target_met": balanced_test_soft_target_met,
        "full_test_pair_count": len(test_pairs),
        "max_test_pairs_per_world": max(test_world_counts.values(), default=0),
        "max_test_pairs_per_world_family": max(test_world_family_counts.values(), default=0),
        "balanced_test_origin_counts": dict(sorted(Counter(row["l4_origin"] for row in balanced_test).items())),
        "quality_gate_errors": errors,
        "media_redistributed": False,
        "upstream_acquisition_required": True,
        "config_snapshot": config,
        "input_hashes": {str(path): sha256_file(path) for path in input_paths},
    }
    write_json(outputs["manifest"], manifest, resume=resume)
    report_lines = [
        "# SpaceConflict L4 三组成构建报告",
        "",
        f"状态：`{manifest['status']}`",
        "",
        f"- L4 二分类 minimal pairs：{len(pairs)}",
        f"- Native：{len(native)}",
        f"- Controlled：{len(controlled)}（占 {controlled_share:.2%}）",
        f"- Calibration：{calibration}（占 {calibration_share:.2%}）",
        f"- L4-Unknown：{len(unknown)}",
        f"- World：{len(world_splits)}",
        f"- Balanced test：{len(balanced_test)}（软目标 {test_low}–{test_high}；{'达到' if balanced_test_soft_target_met else '未达到'}）",
        "",
        "## Origin",
        "",
        *[f"- {key}: {value}" for key, value in sorted(origin_counts.items())],
        "",
        "## Transition family",
        "",
        *[f"- {key}: {value}" for key, value in sorted(transition_counts.items())],
        "",
        "## Grounding",
        "",
        *[f"- {key}: {value}" for key, value in sorted(grounding_counts.items())],
        "",
        "## Quality gates",
        "",
        ("全部硬门通过。" if not errors else "未通过：" + ", ".join(errors)),
        (
            "Test 软目标未达到；已输出独立 Native/Controlled test slices，且未放宽 proof gate。"
            if not balanced_test_soft_target_met else "Test 软目标达到。"
        ),
        "",
        "发布只包含 source IDs、hash、派生 branch、claims 和 certificates；不再分发上游媒体。",
    ]
    from ..hypo3d_l4.common import write_versioned
    write_versioned(outputs["report"], ("\n".join(report_lines) + "\n").encode("utf-8"), resume=resume)
    return {**manifest, "outputs": {key: str(value) for key, value in outputs.items()}, "output_hashes": output_hashes(outputs.values())}
