#!/usr/bin/env python3
"""Prepare blind L4 balanced-test requests without reading private gold files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from spaceconflict.mllm_l4 import SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_KEYS = {
    "label", "gold", "certificate", "proof", "proof_nodes", "proof_edges",
    "unknown_axis", "positive_witness_completion", "negative_witness_completion",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Non-object JSONL row at {path}:{line_number}")
            rows.append(value)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contains_forbidden_key(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_KEYS:
                found.add(key)
            found.update(contains_forbidden_key(child))
    elif isinstance(value, list):
        for child in value:
            found.update(contains_forbidden_key(child))
    return found


def resolve_media(media: dict[str, Any], media_root: Path) -> list[dict[str, str]]:
    resolved = []
    root = media_root.resolve()
    for role, reference in media.items():
        if not isinstance(reference, dict) or not reference.get("path"):
            raise ValueError(f"Invalid media reference for role {role!r}")
        path = (root / str(reference["path"])).resolve()
        if root not in path.parents:
            raise ValueError(f"Media path escapes root: {reference['path']}")
        resolved.append({
            "role": str(role),
            "path": str(path),
            "sha256": str(reference.get("sha256") or ""),
        })
    return resolved


def smoke_subset(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    native_pairs: list[str] = []
    controlled_pairs: list[str] = []
    for row in rows:
        if row["component"] != "binary":
            continue
        bucket = native_pairs if row.get("l4_origin") == "SOURCE_NATIVE" else controlled_pairs
        if row["pair_id"] not in bucket:
            bucket.append(row["pair_id"])
    selected_pair_ids = set(native_pairs[:2] + controlled_pairs[:2])
    selected = [row for row in rows if row["component"] == "binary" and row["pair_id"] in selected_pair_ids]
    unknown_with_media = [row for row in rows if row["component"] == "unknown" and row["media"]]
    unknown_without_media = [row for row in rows if row["component"] == "unknown" and not row["media"]]
    selected.extend(unknown_with_media[:4])
    selected.extend(unknown_without_media[:4])
    if len(selected) != 16:
        raise ValueError(f"Expected a 16-sample stratified smoke set, found {len(selected)}")
    return selected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary-inputs", type=Path, default=ROOT / "l4/v3_3/release/model_inputs.l4_three_part_v3.jsonl")
    parser.add_argument("--unknown-inputs", type=Path, default=ROOT / "l4/v3_3/release/model_inputs.l4_unknown_v3.jsonl")
    parser.add_argument("--balanced-slice", type=Path, default=ROOT / "l4/v3_3/release/test_slices/l4_balanced_test_v3.jsonl")
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-media-hashes", action="store_true")
    args = parser.parse_args()

    pair_ids = [str(row["pair_id"]) for row in read_jsonl(args.balanced_slice)]
    if len(pair_ids) != 225 or len(set(pair_ids)) != 225:
        raise ValueError("Balanced L4 slice must contain exactly 225 unique pair IDs")
    pair_id_set = set(pair_ids)
    binary_source = read_jsonl(args.binary_inputs)
    binary_by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in binary_source:
        if str(row.get("pair_id")) in pair_id_set:
            binary_by_pair.setdefault(str(row["pair_id"]), []).append(row)
    if set(binary_by_pair) != pair_id_set or any(len(rows) != 2 for rows in binary_by_pair.values()):
        raise ValueError("Binary model inputs do not provide exactly two examples for every balanced-test pair")

    requests: list[dict[str, Any]] = []
    for pair_id in pair_ids:
        for row in binary_by_pair[pair_id]:
            requests.append({
                "sample_id": str(row["example_id"]),
                "pair_id": pair_id,
                "component": "binary",
                "split": str(row["split"]),
                "level": "L4",
                "l4_origin": str(row["l4_origin"]),
                "base_scene_id": str(row["base_scene_id"]),
                "branch_id": str(row["branch_id"]),
                "claim_text": str(row["claim_text"]),
                "intervention_text": str(row["intervention_text"]),
                "media": resolve_media(row.get("media") or {}, args.media_root),
            })

    unknown_rows = [row for row in read_jsonl(args.unknown_inputs) if row.get("split") == "test"]
    if len(unknown_rows) != 66:
        raise ValueError(f"Expected 66 test Unknown inputs, found {len(unknown_rows)}")
    for row in unknown_rows:
        requests.append({
            "sample_id": str(row["sample_id"]),
            "pair_id": None,
            "component": "unknown",
            "split": "test",
            "level": "L4",
            "l4_origin": "UNKNOWN_CHALLENGE",
            "base_scene_id": str(row["base_scene_id"]),
            "branch_id": str(row["branch_id"]),
            "claim_text": str(row["claim_text"]),
            "intervention_text": str(row["intervention_text"]),
            "media": resolve_media(row.get("media") or {}, args.media_root),
        })

    if len(requests) != 516 or len({row["sample_id"] for row in requests}) != 516:
        raise ValueError("Expected exactly 516 unique blind requests")
    forbidden = set().union(*(contains_forbidden_key(row) for row in requests))
    if forbidden:
        raise ValueError(f"Gold leakage keys in blind requests: {sorted(forbidden)}")

    missing = []
    mismatched = []
    checked_hashes: dict[str, str] = {}
    for request in requests:
        for media in request["media"]:
            path = Path(media["path"])
            if not path.is_file():
                missing.append(str(path))
                continue
            if args.verify_media_hashes:
                actual = checked_hashes.setdefault(str(path), sha256_file(path))
                expected = media["sha256"].removeprefix("sha256:")
                if expected and actual != expected:
                    mismatched.append(str(path))
    if missing or mismatched:
        raise ValueError(f"Media validation failed: missing={len(missing)}, hash_mismatch={len(mismatched)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    requested_path = args.output_dir / "requested_samples.jsonl"
    smoke_path = args.output_dir / "requested_samples.smoke.jsonl"
    write_jsonl(requested_path, requests)
    write_jsonl(smoke_path, smoke_subset(requests))
    (args.output_dir / "prompt.txt").write_text(SYSTEM_PROMPT + "\n", encoding="utf-8")
    prompt_hash = hashlib.sha256((SYSTEM_PROMPT + "\n").encode()).hexdigest()
    (args.output_dir / "prompt.sha256").write_text(prompt_hash + "  prompt.txt\n", encoding="utf-8")
    report = {
        "status": "PASS",
        "gold_leakage_keys": [],
        "requests": len(requests),
        "binary_examples": sum(row["component"] == "binary" for row in requests),
        "binary_pairs": len(pair_id_set),
        "unknown_examples": sum(row["component"] == "unknown" for row in requests),
        "examples_with_media": sum(bool(row["media"]) for row in requests),
        "examples_without_media": sum(not row["media"] for row in requests),
        "unique_media_files": len({media["path"] for row in requests for media in row["media"]}),
        "missing_media": len(missing),
        "hash_mismatch": len(mismatched),
        "hash_verification": "FULL" if args.verify_media_hashes else "NOT_RUN_RELEASE_AUDIT_RELIED_UPON",
        "requested_samples_sha256": sha256_file(requested_path),
        "smoke_samples": 16,
        "prompt_sha256": prompt_hash,
    }
    (args.output_dir / "media_resolution_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

