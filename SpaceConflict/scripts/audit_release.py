#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def media_signature(media: dict[str, Any]) -> str:
    return json.dumps(media, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", default="golden_verified_slice_v6")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--quota-version", default="quota_golden_v6")
    parser.add_argument("--unknown-version", default="unknown_v2")
    parser.add_argument("--split-version", default="world_split_v6")
    parser.add_argument("--unknown-path", action="append")
    parser.add_argument("--split-path", action="append")
    args = parser.parse_args()
    root = args.root.resolve()
    release = root / "release" / args.release
    failures: list[dict[str, Any]] = []

    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    pairs = load_jsonl(release / "pairs.jsonl")
    claims = load_jsonl(release / "claims.jsonl")
    unknown_claims = load_jsonl(release / "unknown_challenge.jsonl")
    pair_schema = json.loads((root / "schemas/benchmark_pair.schema.json").read_text())
    claim_schema = json.loads((root / "schemas/benchmark_claim.schema.json").read_text())
    cert_schema = json.loads((root / "schemas/proof_certificate.schema.json").read_text())
    unknown_cert_schema = json.loads((root / "schemas/unknown_certificate.schema.json").read_text())
    pair_validator = Draft202012Validator(pair_schema)
    claim_validator = Draft202012Validator(claim_schema)
    cert_validator = Draft202012Validator(cert_schema)
    unknown_cert_validator = Draft202012Validator(unknown_cert_schema)

    schema_error_counts: Counter[str] = Counter()
    for kind, rows, validator in (
        ("pair", pairs, pair_validator),
        ("claim", claims, claim_validator),
        ("unknown_claim", unknown_claims, claim_validator),
    ):
        for row in rows:
            errors = list(validator.iter_errors(row))
            if errors:
                schema_error_counts[kind] += len(errors)
                failures.append({"gate": "SCHEMA", "kind": kind, "id": row.get("pair_id"), "error": errors[0].message})

    count_expectations = {
        "pair_count": len(pairs), "claim_count": len(claims),
        "unknown_claim_count": len(unknown_claims),
    }
    for key, actual in count_expectations.items():
        if manifest.get(key) != actual:
            failures.append({"gate": "MANIFEST_COUNT", "field": key, "manifest": manifest.get(key), "actual": actual})
    hash_failures = []
    for relative, expected in manifest["output_hashes"].items():
        actual = sha256(root / relative)
        if actual != expected:
            hash_failures.append({"path": relative, "expected": expected, "actual": actual})
    failures.extend({"gate": "OUTPUT_HASH", **item} for item in hash_failures)

    pair_ids = [row["pair_id"] for row in pairs]
    sample_ids = [row["sample_id"] for row in claims + unknown_claims]
    if len(pair_ids) != len(set(pair_ids)):
        failures.append({"gate": "UNIQUE_PAIR_ID"})
    if len(sample_ids) != len(set(sample_ids)):
        failures.append({"gate": "UNIQUE_SAMPLE_ID"})
    pair_id_set = set(pair_ids)
    claim_pair_counts = Counter(row["pair_id"] for row in claims)
    if set(claim_pair_counts) != pair_id_set or set(claim_pair_counts.values()) != {2}:
        failures.append({"gate": "PAIR_CLAIM_CARDINALITY", "distribution": dict(Counter(claim_pair_counts.values()))})

    binary_texts = [row["claim"] for row in claims]
    unknown_texts = [row["claim"] for row in unknown_claims]
    composite_samples = [(row["claim"], media_signature(row["media"])) for row in claims + unknown_claims]
    text_checks = {
        "binary_text_unique": len(binary_texts) == len(set(binary_texts)),
        "unknown_text_unique": len(unknown_texts) == len(set(unknown_texts)),
        "claim_media_composite_unique": len(composite_samples) == len(set(composite_samples)),
    }
    if not text_checks["claim_media_composite_unique"]:
        failures.append({"gate": "CLAIM_MEDIA_COMPOSITE_UNIQUE"})
    bad_text_patterns = {
        "DOUBLE_ARTICLE": re.compile(r"\bthe\s+the\b", re.I),
        "RELATION_PREPOSITION_IN_SUBJECT": re.compile(r"\bto the\s+(?:is|lies|appears|comes|has|occurs|precedes)\b", re.I),
        "REDUNDANT_ACTUAL_OBSERVED": re.compile(r"\bactual observed\b", re.I),
        "INTERNAL_ID_LEAKAGE": re.compile(r"(?:source_item|spar_sample|@source|\bclass:|\bmention:|\bomni:)", re.I),
    }
    bad_text_counts: Counter[str] = Counter()
    for row in claims + unknown_claims:
        for code, pattern in bad_text_patterns.items():
            if pattern.search(row["claim"]):
                bad_text_counts[code] += 1
    if bad_text_counts:
        failures.append({"gate": "TEXT_QUALITY", "counts": dict(bad_text_counts)})

    forbidden_payload_keys = {"base64", "bytes", "blob", "binary_payload", "image_payload", "video_payload"}
    payload_key_hits: Counter[str] = Counter()
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in forbidden_payload_keys:
                    payload_key_hits[key.casefold()] += 1
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for row in pairs + claims + unknown_claims:
        walk(row.get("media"))
    if payload_key_hits:
        failures.append({"gate": "MEDIA_PAYLOAD", "keys": dict(payload_key_hits)})

    ca_role_failures = 0
    for pair in pairs:
        if pair["source"]["source_dataset"] != "ca_vqa":
            continue
        references = pair["media"]["source_references"]
        if len(references) != 1:
            ca_role_failures += 1
            continue
        reference = references[0]
        roles = reference.get("frame_roles", {})
        support_frames = reference.get("support_frames", [])
        expected_role_names = {"reference_frame", *(f"support_frame_{index}" for index in range(1, len(support_frames) + 1))}
        expected_support_frames = [roles.get(f"support_frame_{index}") for index in range(1, len(support_frames) + 1)]
        if (
            set(roles) != expected_role_names
            or reference.get("reference_frame") != roles.get("reference_frame")
            or support_frames != expected_support_frames
        ):
            ca_role_failures += 1
    if ca_role_failures:
        failures.append({"gate": "CA_MEDIA_ROLES", "count": ca_role_failures})

    sampled_path = root / "sampled" / f"pairs.{args.quota_version}.seed_{args.seed}.jsonl"
    sampled = load_jsonl(sampled_path)
    sampled_by_id = {row["pair_id"]: row for row in sampled}
    evidence_failures: Counter[str] = Counter()
    for pair in pairs:
        row = sampled_by_id.get(pair["pair_id"])
        if row is None:
            evidence_failures["SAMPLED_ROW_MISSING"] += 1
            continue
        evidence = json.loads((root / row["evidence_subgraph_path"]).read_text())
        certificate = json.loads((root / row["certificate_path"]).read_text())
        if list(cert_validator.iter_errors(certificate)):
            evidence_failures["CERTIFICATE_SCHEMA"] += 1
        fact_ids = {fact["fact_id"] for fact in evidence["facts"]}
        if not set(certificate["evidence_fact_ids"]) <= fact_ids:
            evidence_failures["CERTIFICATE_FACT_OUTSIDE_EVIDENCE"] += 1
        if set(evidence["media_ids"]) != set(pair["media"]["media_ids"]):
            evidence_failures["MEDIA_CLOSURE_MISMATCH"] += 1
        if row["world_graph_hash"] != pair["graph_reference"]["world_graph_hash"]:
            evidence_failures["WORLD_GRAPH_HASH_MISMATCH"] += 1
    if evidence_failures:
        failures.append({"gate": "EVIDENCE_CLOSURE", "counts": dict(evidence_failures)})

    unknown_paths = (
        [(root / value).resolve() for value in args.unknown_path]
        if args.unknown_path else
        [root / f"candidates/unknown/claims.{args.unknown_version}.jsonl"]
    )
    for path in unknown_paths:
        path.relative_to(root)
    unknown_source = [row for path in unknown_paths for row in load_jsonl(path)]
    unknown_by_id = {row["unknown_id"]: row for row in unknown_source}
    if len(unknown_by_id) != len(unknown_source):
        raise ValueError("DUPLICATE_UNKNOWN_ID_ACROSS_INPUTS")
    unknown_failures: Counter[str] = Counter()
    for claim in unknown_claims:
        source = unknown_by_id.get(claim["sample_id"])
        if source is None:
            unknown_failures["SOURCE_ROW_MISSING"] += 1
            continue
        certificate = json.loads((root / source["certificate_path"]).read_text())
        if list(unknown_cert_validator.iter_errors(certificate)):
            unknown_failures["CERTIFICATE_SCHEMA"] += 1
        references = claim["media"].get("source_references", [])
        roles = [item.get("role") for item in references]
        withheld = claim["media"].get("withheld_evidence", {})
        reference_members = {item.get("archive_member") for item in references}
        if source.get("source_dataset") == "ca_vqa":
            expected_support_roles = [f"support_frame_{index}" for index in range(1, 5)]
            if roles != expected_support_roles or len(reference_members) != 4:
                unknown_failures["SUPPORT_ROLE_SET"] += 1
            if withheld.get("role") != "reference_frame" or withheld.get("archive_member") in reference_members:
                unknown_failures["REFERENCE_ABLATION"] += 1
        elif source.get("source_dataset") == "spar":
            if len(roles) != len(set(roles)) or len(reference_members) != len(references):
                unknown_failures["AVAILABLE_VIEW_ROLE_SET"] += 1
            if (
                not str(withheld.get("role", "")).startswith("frame_")
                or withheld.get("role") in set(roles)
                or withheld.get("archive_member") in reference_members
            ):
                unknown_failures["VIEW_ABLATION"] += 1
        else:
            unknown_failures["UNSUPPORTED_UNKNOWN_SOURCE_DATASET"] += 1
        verification = certificate.get("verification", {})
        if verification != {"ablated_label": "UNKNOWN", "positive_witness_label": "SUPPORTED", "negative_witness_label": "CONTRADICTORY"}:
            unknown_failures["WITNESS_REPLAY"] += 1
    if unknown_failures:
        failures.append({"gate": "UNKNOWN", "counts": dict(unknown_failures)})

    split_paths = (
        [(root / value).resolve() for value in args.split_path]
        if args.split_path else
        [root / f"splits/{args.split_version}.seed_{args.seed}.jsonl"]
    )
    for path in split_paths:
        path.relative_to(root)
    split_rows = [row for path in split_paths for row in load_jsonl(path)]
    splits_by_world: dict[str, set[str]] = defaultdict(set)
    for row in split_rows:
        splits_by_world[row["global_world_id"]].add(row["split"])
    split_leakage_worlds = sorted(world for world, values in splits_by_world.items() if len(values) != 1)
    sampled_split_mismatches = sum(
        row["split"] not in splits_by_world.get(row["global_world_id"], set()) for row in sampled
    )
    if split_leakage_worlds or sampled_split_mismatches:
        failures.append({"gate": "SPLIT_LEAKAGE", "world_count": len(split_leakage_worlds), "sampled_mismatches": sampled_split_mismatches})

    report = {
        "schema_version": "1.0", "release": args.release,
        "status": "PASS" if not failures else "FAIL",
        "pair_count": len(pairs), "claim_count": len(claims), "unknown_claim_count": len(unknown_claims),
        "schema_error_counts": dict(schema_error_counts), "hash_failure_count": len(hash_failures),
        "text_checks": text_checks, "bad_text_counts": dict(bad_text_counts),
        "binary_surface_duplicate_rate": 1 - len(set(binary_texts)) / len(binary_texts) if binary_texts else 0.0,
        "unknown_surface_duplicate_rate": 1 - len(set(unknown_texts)) / len(unknown_texts) if unknown_texts else 0.0,
        "media_payload_key_hits": dict(payload_key_hits), "ca_media_role_failure_count": ca_role_failures,
        "evidence_closure_failures": dict(evidence_failures), "unknown_failures": dict(unknown_failures),
        "split_leakage_world_count": len(split_leakage_worlds), "sampled_split_mismatch_count": sampled_split_mismatches,
        "dataset_counts": dict(sorted(Counter(pair["source"]["source_dataset"] for pair in pairs).items())),
        "label_counts": dict(sorted(Counter(row["label"] for row in claims + unknown_claims).items())),
        "failures": failures,
    }
    report_path = root / "reports" / f"release_audit.{args.release}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
