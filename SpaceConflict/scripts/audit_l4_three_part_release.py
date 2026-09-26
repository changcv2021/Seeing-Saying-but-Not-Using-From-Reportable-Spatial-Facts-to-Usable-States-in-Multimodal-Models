from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.release_root
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    pairs = read_jsonl(root / "pairs.l4_three_part_v3.jsonl")
    inputs = read_jsonl(root / "model_inputs.l4_three_part_v3.jsonl")
    gold = read_jsonl(root / "gold.l4_three_part_v3.jsonl")
    unknown = read_jsonl(root / "unknown_challenge.l4_v3.jsonl")
    unknown_inputs = read_jsonl(root / "model_inputs.l4_unknown_v3.jsonl")
    unknown_gold = read_jsonl(root / "gold.l4_unknown_v3.jsonl")
    balanced = read_jsonl(root / "test_slices/l4_balanced_test_v3.jsonl")
    native_test = read_jsonl(root / "test_slices/l4_native_test_v3.jsonl")
    controlled_test = read_jsonl(root / "test_slices/l4_controlled_test_v3.jsonl")

    errors: list[str] = []
    pair_ids = [str(row["pair_id"]) for row in pairs]
    sample_ids = [str(row["sample_id"]) for row in unknown]
    if len(pair_ids) != len(set(pair_ids)):
        errors.append("DUPLICATE_PAIR_ID")
    if len(sample_ids) != len(set(sample_ids)):
        errors.append("DUPLICATE_UNKNOWN_ID")
    if len(inputs) != 2 * len(pairs) or len(gold) != 2 * len(pairs):
        errors.append("BINARY_CARDINALITY_MISMATCH")
    if len(unknown_inputs) != len(unknown) or len(unknown_gold) != len(unknown):
        errors.append("UNKNOWN_CARDINALITY_MISMATCH")

    labels_by_pair: dict[str, list[str]] = defaultdict(list)
    for row in gold:
        labels_by_pair[str(row["pair_id"])].append(str(row["label"]))
    if any(sorted(values) != ["CONTRADICTORY", "SUPPORTED"] for values in labels_by_pair.values()):
        errors.append("PAIR_LABEL_SYMMETRY_FAIL")
    if set(labels_by_pair) != set(pair_ids):
        errors.append("PAIR_GOLD_COVERAGE_FAIL")
    if any("label" in row or "gold" in row for row in inputs + unknown_inputs):
        errors.append("MODEL_INPUT_LABEL_LEAK")
    if any(row.get("label") != "UNKNOWN" for row in unknown_gold):
        errors.append("UNKNOWN_GOLD_LABEL_FAIL")

    world_splits: dict[str, set[str]] = defaultdict(set)
    for row in pairs + unknown:
        world_splits[str(row["global_world_id"])].add(str(row["split"]))
    if any(len(values) != 1 for values in world_splits.values()):
        errors.append("WORLD_SPLIT_LEAKAGE")
    controlled_by_id = {
        str(row["pair_id"]): row for row in pairs if row["l4_origin"] == "BENCHMARK_CONTROLLED"
    }
    if any(
        str(row["base_determinate_sample_id"]) not in controlled_by_id
        or controlled_by_id[str(row["base_determinate_sample_id"])]["split"] != row["split"]
        for row in unknown
    ):
        errors.append("UNKNOWN_BASE_SPLIT_FAIL")

    test = [row for row in pairs if row["split"] == "test"]
    test_world_counts = Counter(str(row["base_scene_id"]) for row in test)
    test_family_counts = Counter((str(row["base_scene_id"]), str(row["transition_family"])) for row in test)
    if max(test_world_counts.values(), default=0) > 2:
        errors.append("TEST_WORLD_DENSITY_FAIL")
    if max(test_family_counts.values(), default=0) > 1:
        errors.append("TEST_FAMILY_DENSITY_FAIL")
    unknown_test_counts = Counter(str(row["base_scene_id"]) for row in unknown if row["split"] == "test")
    if max(unknown_test_counts.values(), default=0) > 1:
        errors.append("UNKNOWN_TEST_WORLD_DENSITY_FAIL")

    if any(row.get("validation", {}).get("final_status") != "AUTO_ACCEPTED" for row in pairs + unknown):
        errors.append("NON_AUTO_ACCEPTED_RECORD")
    if any(len(row.get("edit", {}).get("changed_slots", [])) != 1 for row in pairs):
        errors.append("MINIMAL_PAIR_CHANGED_SLOT_FAIL")
    controlled = list(controlled_by_id.values())
    project_root = Path(__file__).resolve().parents[1]
    pair_validator = Draft202012Validator(json.loads((project_root / "schemas/l4_pair_v3.schema.json").read_text(encoding="utf-8")))
    unknown_validator = Draft202012Validator(json.loads((project_root / "schemas/l4_unknown_v3.schema.json").read_text(encoding="utf-8")))
    action_validator = Draft202012Validator(json.loads((project_root / "schemas/l4_controlled_action_v3.schema.json").read_text(encoding="utf-8")))
    pair_schema_errors = sum(1 for row in pairs for _ in pair_validator.iter_errors(row))
    unknown_schema_errors = sum(1 for row in unknown for _ in unknown_validator.iter_errors(row))
    action_schema_errors = sum(1 for row in controlled for _ in action_validator.iter_errors(row["intervention"]))
    if pair_schema_errors:
        errors.append(f"PAIR_SCHEMA_FAIL:{pair_schema_errors}")
    if unknown_schema_errors:
        errors.append(f"UNKNOWN_SCHEMA_FAIL:{unknown_schema_errors}")
    if action_schema_errors:
        errors.append(f"CONTROLLED_ACTION_SCHEMA_FAIL:{action_schema_errors}")
    if any(
        row.get("validation", {}).get("transition_a_b_exact_match") is not True
        or row.get("validation", {}).get("transition_engine_a") != "PASS"
        or row.get("validation", {}).get("transition_checker_b") != "PASS"
        for row in controlled
    ):
        errors.append("CONTROLLED_DUAL_ENGINE_FAIL")
    if any(
        row.get("positive_witness_completion", {}).get("claim_holds") is not True
        or row.get("negative_witness_completion", {}).get("claim_holds") is not False
        or row.get("validation", {}).get("independent_witness_verifier") != "PASS"
        for row in unknown
    ):
        errors.append("UNKNOWN_DUAL_WITNESS_FAIL")

    reason_counts = Counter(str(row["unknown_axis"]) for row in unknown)
    source_counts = Counter(str(row["source_group"]) for row in unknown)
    if unknown and max(reason_counts.values()) / len(unknown) > 0.25:
        errors.append("UNKNOWN_REASON_QUOTA_FAIL")
    if unknown and max(source_counts.values()) / len(unknown) > 0.40:
        errors.append("UNKNOWN_SOURCE_QUOTA_FAIL")
    ablation = sum(row["unknown_origin"] == "EVIDENCE_ABLATION" for row in unknown)
    if not unknown or ablation / len(unknown) < 0.50:
        errors.append("UNKNOWN_ABLATION_QUOTA_FAIL")

    for path_text, expected in manifest.get("input_hashes", {}).items():
        path = Path(path_text)
        if not path.is_file() or sha256(path) != expected:
            errors.append(f"INPUT_HASH_FAIL:{path_text}")

    media_records: dict[str, str] = {}
    for row in pairs:
        for metadata in row.get("media", {}).values():
            media_records[str(metadata["path"])] = str(metadata["sha256"])
    media_missing = 0
    media_hash_fail = 0
    for relative, expected in sorted(media_records.items()):
        path = args.media_root / relative
        if not path.is_file():
            media_missing += 1
        elif sha256(path) != expected:
            media_hash_fail += 1
    if media_missing:
        errors.append(f"MEDIA_MISSING:{media_missing}")
    if media_hash_fail:
        errors.append(f"MEDIA_HASH_FAIL:{media_hash_fail}")

    artifact_paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json")
    report = {
        "schema_version": "l4_three_part_independent_audit_v3",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "release_status": manifest.get("status"),
        "counts": {
            "binary_pairs": len(pairs), "binary_claims": len(inputs),
            "native_pairs": len(pairs) - len(controlled), "controlled_pairs": len(controlled),
            "unknown_claims": len(unknown), "worlds": len(world_splits),
            "balanced_test": len(balanced), "native_test": len(native_test),
            "controlled_test": len(controlled_test), "unique_media_files": len(media_records),
        },
        "test_density": {
            "max_pairs_per_world": max(test_world_counts.values(), default=0),
            "max_pairs_per_world_family": max(test_family_counts.values(), default=0),
            "max_unknown_per_world": max(unknown_test_counts.values(), default=0),
        },
        "unknown_reason_counts": dict(sorted(reason_counts.items())),
        "unknown_source_counts": dict(sorted(source_counts.items())),
        "evidence_ablation_fraction": ablation / len(unknown) if unknown else 0.0,
        "media": {"missing": media_missing, "hash_fail": media_hash_fail},
        "schema_validation": {
            "pair_errors": pair_schema_errors,
            "unknown_errors": unknown_schema_errors,
            "controlled_action_errors": action_schema_errors,
        },
        "artifact_hashes": {str(path.relative_to(root)): sha256(path) for path in artifact_paths},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
