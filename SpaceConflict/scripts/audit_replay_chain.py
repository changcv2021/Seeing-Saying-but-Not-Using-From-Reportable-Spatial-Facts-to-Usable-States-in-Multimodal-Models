#!/usr/bin/env python3
"""Audit every exported sample's private, replayable construction chain.

This complements the public-release audit. It verifies the hashes and semantic
links among canonical facts, world/evidence graphs, claim graphs, construction
traces, proof certificates, realization traces, verifier output, and exports.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PATH_ESCAPES_ROOT:{relative}") from exc
    return path


def normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def replay_semantic_merge(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay graphs.pipeline._merge_duplicates for one declared merge group."""
    group = sorted(facts, key=lambda row: row["fact_id"])
    selected = copy.deepcopy(group[0])
    selected["grounding"]["merged_equivalent_fact_ids"] = [row["fact_id"] for row in group]
    selected["grounding"]["merged_provenance"] = [row["provenance"] for row in group]
    selected.pop("canonical_fact_hash", None)
    selected.pop("fact_id", None)
    digest = hashlib.sha256(normalized(selected).encode("utf-8")).hexdigest()
    selected["fact_id"] = f"fact:{digest[:24]}"
    selected["canonical_fact_hash"] = f"sha256:{digest}"
    return selected


def slot_value(graph: dict[str, Any], slot: str) -> Any:
    atom = graph["atoms"][0]
    aliases = {"subject_id": "subject", "object_id": "object"}
    key = aliases.get(slot, slot)
    if key in atom:
        return atom.get(key)
    return graph["context"].get(key)


class Audit:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()
        self.examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def fail(self, code: str, pair_id: str, detail: Any = None) -> None:
        self.counts[code] += 1
        if len(self.examples[code]) < 10:
            row: dict[str, Any] = {"id": pair_id}
            if detail is not None:
                row["detail"] = detail
            self.examples[code].append(row)

    def require(self, condition: bool, code: str, pair_id: str, detail: Any = None) -> None:
        if not condition:
            self.fail(code, pair_id, detail)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", default="pilot_verified_2k_v2")
    parser.add_argument("--quota-version", default="quota_pilot_2k_v2")
    parser.add_argument("--unknown-version", default="unknown_p1_v2")
    parser.add_argument("--realization-version", default="realization_p1_v2")
    parser.add_argument("--proof-version", default="proof_verification_p1_v2")
    parser.add_argument("--canonical-version", default="canonical_v4")
    parser.add_argument("--proof-path", action="append")
    parser.add_argument("--realization-path", action="append")
    parser.add_argument("--unknown-path", action="append")
    parser.add_argument("--additional-canonical-path", action="append", default=[])
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()
    root = args.root.resolve()
    release_dir = root / "release" / args.release
    audit = Audit()

    pairs = read_jsonl(release_dir / "pairs.jsonl")
    claims = read_jsonl(release_dir / "claims.jsonl")
    unknown_exports = read_jsonl(release_dir / "unknown_challenge.jsonl")
    sampled_path = root / "sampled" / f"pairs.{args.quota_version}.seed_{args.seed}.jsonl"
    sampled = read_jsonl(sampled_path)
    sampled_by_id = {row["pair_id"]: row for row in sampled}
    auto_accepted_paths = (
        [safe_path(root, value) for value in args.proof_path]
        if args.proof_path else
        [root / "candidates" / "auto_accepted" / f"pairs.{args.proof_version}.jsonl"]
    )
    auto_accepted_rows = [row for path in auto_accepted_paths for row in read_jsonl(path)]
    auto_accepted_by_id = {row["pair_id"]: row for row in auto_accepted_rows}
    if len(auto_accepted_by_id) != len(auto_accepted_rows):
        raise ValueError("DUPLICATE_AUTO_ACCEPTED_PAIR_ID_ACROSS_INPUTS")
    pairs_by_id = {row["pair_id"]: row for row in pairs}
    claims_by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        claims_by_pair[claim["pair_id"]].append(claim)

    realization_paths = (
        [safe_path(root, value) for value in args.realization_path]
        if args.realization_path else
        [root / "realization_traces" / f"traces.{args.realization_version}.jsonl"]
    )
    realization_rows = [row for path in realization_paths for row in read_jsonl(path)]
    realization_by_id = {row["pair_id"]: row for row in realization_rows}
    if len(realization_by_id) != len(realization_rows):
        raise ValueError("DUPLICATE_REALIZATION_PAIR_ID_ACROSS_INPUTS")
    schema_validators = {
        name: Draft202012Validator(json.loads((root / "schemas" / filename).read_text(encoding="utf-8")))
        for name, filename in {
            "claim_graph": "claim_graph.schema.json",
            "certificate": "proof_certificate.schema.json",
            "trace": "construction_trace.schema.json",
            "unknown_certificate": "unknown_certificate.schema.json",
        }.items()
    }

    world_cache: dict[str, tuple[dict[str, Any], str, dict[str, dict[str, Any]]]] = {}
    evidence_facts: dict[str, dict[str, Any]] = {}
    canonical_needed_ids: set[str] = set()
    evidence_fact_owners: dict[str, set[str]] = defaultdict(set)
    checked_artifact_paths: set[str] = set()
    artifact_count = 0
    world_reference_count = 0
    provenance_fact_count = 0

    for pair in pairs:
        pair_id = pair["pair_id"]
        row = sampled_by_id.get(pair_id)
        if row is None:
            audit.fail("SAMPLED_PAIR_MISSING", pair_id)
            continue
        audit.require(row.get("status") == "AUTO_ACCEPTED", "PAIR_NOT_AUTO_ACCEPTED", pair_id, row.get("status"))
        audit.require(row.get("source_item_ids") == pair["source"].get("source_item_ids"), "SOURCE_ITEM_EXPORT_MISMATCH", pair_id)
        audit.require(row.get("source_dataset") == pair["source"].get("source_dataset"), "SOURCE_DATASET_EXPORT_MISMATCH", pair_id)

        required_paths = {
            row["certificate_path"], row["evidence_subgraph_path"],
            row["supported_graph_path"], row["contradictory_graph_path"],
        }
        trace_paths = [path for path in row.get("artifacts", {}) if path.startswith("construction_traces/")]
        audit.require(len(trace_paths) == 1, "CONSTRUCTION_TRACE_PATH_COUNT", pair_id, trace_paths)
        if not trace_paths:
            continue
        trace_relative = trace_paths[0]
        required_paths.add(trace_relative)
        audit.require(required_paths <= set(row.get("artifacts", {})), "ARTIFACT_MANIFEST_INCOMPLETE", pair_id)
        artifact_ok = True
        for relative, expected in row.get("artifacts", {}).items():
            artifact_count += 1
            try:
                path = safe_path(root, relative)
            except ValueError:
                audit.fail("ARTIFACT_UNSAFE_PATH", pair_id, relative)
                artifact_ok = False
                continue
            if not path.is_file():
                audit.fail("ARTIFACT_MISSING", pair_id, relative)
                artifact_ok = False
                continue
            if relative not in checked_artifact_paths:
                actual = sha256(path)
                checked_artifact_paths.add(relative)
            else:
                actual = sha256(path)
            if actual != expected:
                audit.fail("ARTIFACT_HASH_MISMATCH", pair_id, {"path": relative, "expected": expected, "actual": actual})
                artifact_ok = False
        if not artifact_ok:
            continue

        certificate = json.loads(safe_path(root, row["certificate_path"]).read_text(encoding="utf-8"))
        evidence = json.loads(safe_path(root, row["evidence_subgraph_path"]).read_text(encoding="utf-8"))
        supported = json.loads(safe_path(root, row["supported_graph_path"]).read_text(encoding="utf-8"))
        contradictory = json.loads(safe_path(root, row["contradictory_graph_path"]).read_text(encoding="utf-8"))
        trace = json.loads(safe_path(root, trace_relative).read_text(encoding="utf-8"))
        for kind, value in (("certificate", certificate), ("claim_graph", supported), ("claim_graph", contradictory), ("trace", trace)):
            errors = list(schema_validators[kind].iter_errors(value))
            audit.require(not errors, f"{kind.upper()}_SCHEMA", pair_id, errors[0].message if errors else None)

        world_relative = row["world_graph_path"]
        if world_relative not in world_cache:
            world_path = safe_path(root, world_relative)
            if not world_path.is_file():
                audit.fail("WORLD_GRAPH_MISSING", pair_id, world_relative)
                continue
            world = json.loads(world_path.read_text(encoding="utf-8"))
            world_cache[world_relative] = (world, sha256(world_path), {fact["fact_id"]: fact for fact in world["facts"]})
        world, world_hash, world_fact_map = world_cache[world_relative]
        world_reference_count += 1
        expected_world_hashes = {
            row["world_graph_hash"], trace["world_graph_hash"],
            pair["graph_reference"]["world_graph_hash"],
        }
        audit.require(expected_world_hashes == {world_hash}, "WORLD_GRAPH_HASH_CHAIN", pair_id, sorted(expected_world_hashes | {world_hash}))
        audit.require(world.get("validation_status") == "GRAPH_VALID", "WORLD_GRAPH_NOT_VALID", pair_id, world.get("validation_status"))
        audit.require(world.get("global_world_id") == row["global_world_id"] == evidence.get("global_world_id"), "WORLD_ID_CHAIN", pair_id)
        audit.require(world.get("world_graph_id") == evidence.get("world_graph_id") == pair["graph_reference"]["world_graph_id"], "WORLD_GRAPH_ID_CHAIN", pair_id)

        evidence_map = {fact["fact_id"]: fact for fact in evidence["facts"]}
        for fact_id, fact in evidence_map.items():
            evidence_facts.setdefault(fact_id, fact)
            canonical_needed_ids.add(fact_id)
            canonical_needed_ids.update(fact.get("grounding", {}).get("merged_equivalent_fact_ids", []))
            evidence_fact_owners[fact_id].add(pair_id)
            provenance = fact.get("provenance", {})
            provenance_fact_count += 1
            audit.require(fact_id in world_fact_map and normalized(world_fact_map.get(fact_id)) == normalized(fact), "EVIDENCE_WORLD_FACT_MISMATCH", pair_id, fact_id)
            audit.require(bool(provenance.get("source_item_ids")), "PROVENANCE_SOURCE_ID_MISSING", pair_id, fact_id)
            audit.require(str(provenance.get("source_record_hash", "")).startswith("sha256:"), "PROVENANCE_HASH_MISSING", pair_id, fact_id)
            audit.require(bool(provenance.get("source_field_paths")), "PROVENANCE_FIELD_PATH_MISSING", pair_id, fact_id)
            audit.require(provenance.get("origin_type") != "MODEL_PREDICTED", "MODEL_PREDICTED_FACT", pair_id, fact_id)
        source_ids = {
            item for fact in evidence["facts"]
            for item in fact.get("provenance", {}).get("source_item_ids", [])
        }
        source_hashes = {
            fact.get("provenance", {}).get("source_record_hash") for fact in evidence["facts"]
            if fact.get("provenance", {}).get("source_record_hash")
        }
        audit.require(set(row["source_item_ids"]) <= source_ids, "PAIR_SOURCE_IDS_OUTSIDE_EVIDENCE", pair_id)
        audit.require(set(pair["source"].get("source_hashes", [])) <= source_hashes, "PAIR_SOURCE_HASHES_OUTSIDE_EVIDENCE", pair_id)
        audit.require(set(trace["source_hashes"]) == set(pair["source"].get("source_hashes", [])), "TRACE_SOURCE_HASH_MISMATCH", pair_id)

        audit.require(normalized(trace["before_graph"]) == normalized(supported), "TRACE_BEFORE_GRAPH_MISMATCH", pair_id)
        audit.require(normalized(trace["after_graph"]) == normalized(contradictory), "TRACE_AFTER_GRAPH_MISMATCH", pair_id)
        audit.require(normalized(row["supported_claim"]["normalized"]) == normalized(supported), "SAMPLED_SUPPORTED_GRAPH_MISMATCH", pair_id)
        audit.require(normalized(row["contradictory_claim"]["normalized"]) == normalized(contradictory), "SAMPLED_CONTRADICTORY_GRAPH_MISMATCH", pair_id)
        audit.require(normalized(pair["supported_claim"]["normalized"]) == normalized(supported), "EXPORTED_SUPPORTED_GRAPH_MISMATCH", pair_id)
        audit.require(normalized(pair["contradictory_claim"]["normalized"]) == normalized(contradictory), "EXPORTED_CONTRADICTORY_GRAPH_MISMATCH", pair_id)
        audit.require(trace["trace_id"] == pair["construction_trace_id"], "TRACE_ID_MISMATCH", pair_id)
        audit.require(certificate["certificate_id"] == pair["certificate_id"], "CERTIFICATE_ID_MISMATCH", pair_id)
        audit.require(trace["operator"]["operator_id"] == row["operator_id"] == pair["task"]["operator_id"], "OPERATOR_CHAIN", pair_id)
        audit.require(trace["level"] == row["level"] == pair["task"]["level"] == certificate["level"], "LEVEL_CHAIN", pair_id)
        audit.require(trace["primary_track"] == row["primary_track"] == pair["task"]["primary_diagnostic_tag"], "PRIMARY_TRACK_CHAIN", pair_id)
        audit.require(set(trace.get("secondary_tracks", [])) == set(row.get("secondary_tracks", [])) == set(pair["task"].get("secondary_diagnostic_tags", [])), "SECONDARY_TRACK_CHAIN", pair_id)

        edit_slots = {edit["slot"] for edit in trace["edit_operations"]}
        audit.require(edit_slots == set(certificate["conflict_slots"]), "EDIT_CONFLICT_SLOT_MISMATCH", pair_id, {"edit": sorted(edit_slots), "certificate": certificate["conflict_slots"]})
        for edit in trace["edit_operations"]:
            slot = edit["slot"]
            audit.require(edit["before"] == slot_value(supported, slot), "EDIT_BEFORE_VALUE_MISMATCH", pair_id, slot)
            audit.require(edit["after"] == slot_value(contradictory, slot), "EDIT_AFTER_VALUE_MISMATCH", pair_id, slot)
            audit.require(edit["before"] != edit["after"], "EDIT_IS_NOOP", pair_id, slot)
        for slot in trace["preserved_slots"]:
            audit.require(slot_value(supported, slot) == slot_value(contradictory, slot), "PRESERVED_SLOT_CHANGED", pair_id, slot)

        certificate_facts = set(certificate["evidence_fact_ids"])
        audit.require(certificate_facts == set(evidence["contradiction_fact_ids"]), "CERTIFICATE_CONTRADICTION_FACT_MISMATCH", pair_id)
        audit.require(certificate_facts <= set(evidence_map), "CERTIFICATE_FACT_OUTSIDE_EVIDENCE", pair_id)
        audit.require(set(evidence["minimality"]["required_fact_ids"]) == certificate_facts, "MINIMALITY_FACT_MISMATCH", pair_id)
        proof_nodes = {node["id"] for node in certificate["proof_nodes"]}
        proof_endpoints = {item for edge in certificate["proof_edges"] for item in edge[:2]}
        audit.require(proof_endpoints <= proof_nodes, "PROOF_EDGE_DANGLING", pair_id, sorted(proof_endpoints - proof_nodes))
        required_rules = {node["id"].removeprefix("rule:") for node in certificate["proof_nodes"] if node["type"] == "RULE"}
        audit.require(required_rules <= set(world.get("authorized_rule_ids", [])), "UNAUTHORIZED_PROOF_RULE", pair_id, sorted(required_rules - set(world.get("authorized_rule_ids", []))))
        verifier = row.get("independent_verifier", {})
        audit.require(verifier.get("certificate_replay") == "PASS", "VERIFIER_CERTIFICATE_REPLAY", pair_id)
        audit.require(verifier.get("supported", {}).get("label") == "SUPPORTED", "VERIFIER_SUPPORTED_LABEL", pair_id)
        audit.require(verifier.get("contradictory", {}).get("label") == "CONTRADICTORY", "VERIFIER_CONTRADICTORY_LABEL", pair_id)
        audit.require(set(verifier.get("contradictory", {}).get("evidence_fact_ids", [])) == certificate_facts, "VERIFIER_CERTIFICATE_FACT_MISMATCH", pair_id)

        realization = realization_by_id.get(pair_id)
        if realization is None:
            audit.fail("REALIZATION_TRACE_MISSING", pair_id)
        else:
            audit.require(realization["realization_plan_id"] == row["realization_plan_id"], "REALIZATION_PLAN_ID_MISMATCH", pair_id)
            audit.require(set(realization["selected_candidate_ids"]) == set(row["selected_candidate_ids"]), "SELECTED_CANDIDATE_ID_MISMATCH", pair_id)
            audit.require(realization["plan"]["style_family"] == row["selected_style_family"], "STYLE_FAMILY_MISMATCH", pair_id)
        selected_texts = {
            row["supported_claim"]["candidate_id"]: row["supported_claim"]["natural_text"],
            row["contradictory_claim"]["candidate_id"]: row["contradictory_claim"]["natural_text"],
        }
        audit.require(set(selected_texts) == set(row["selected_candidate_ids"]), "SELECTED_TEXT_ID_MISMATCH", pair_id)
        audit.require(pair["supported_claim"]["natural_text"] == row["supported_claim"]["natural_text"], "SUPPORTED_TEXT_EXPORT_MISMATCH", pair_id)
        audit.require(pair["contradictory_claim"]["natural_text"] == row["contradictory_claim"]["natural_text"], "CONTRADICTORY_TEXT_EXPORT_MISMATCH", pair_id)
        exported_claims = claims_by_pair.get(pair_id, [])
        audit.require(len(exported_claims) == 2, "EXPORTED_PAIR_CLAIM_COUNT", pair_id, len(exported_claims))
        expected_text_by_label = {
            "SUPPORTED": row["supported_claim"]["natural_text"],
            "CONTRADICTORY": row["contradictory_claim"]["natural_text"],
        }
        for exported in exported_claims:
            audit.require(exported["claim"] == expected_text_by_label.get(exported["label"]), "CLAIM_TEXT_EXPORT_MISMATCH", pair_id, exported["label"])
        for claim_side in (row["supported_claim"], row["contradictory_claim"]):
            text = claim_side["natural_text"]
            for alignment in claim_side["text_graph_alignment"]:
                start, end = alignment["char_span"]
                audit.require(0 <= start <= end <= len(text) and text[start:end] == alignment["surface_text"], "TEXT_ALIGNMENT_SPAN_MISMATCH", pair_id, alignment.get("slot"))
        audit.require(all(value == "pass" or key == "final_status" and value == "AUTO_ACCEPTED" for key, value in pair["validation"].items()), "EXPORTED_VALIDATION_STATUS", pair_id, pair["validation"])

    # Verify that every evidence fact is byte-for-byte represented at the
    # deterministic canonical boundary and tied to its canonical record.
    canonical_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    canonical_files = sorted((root / "data" / "canonical").glob(f"*/*/{args.canonical_version}/records.jsonl"))
    canonical_files.extend(safe_path(root, value) for value in args.additional_canonical_path)
    canonical_files = sorted(set(canonical_files))
    for path in canonical_files:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                for fact in record.get("facts", []):
                    if fact.get("fact_id") in canonical_needed_ids:
                        canonical_matches[fact["fact_id"]].append({
                            "fact": fact,
                            "record_id": record.get("record_id"),
                            "source_item_ids": record.get("source_item_ids", []),
                            "source_record_hash": record.get("source_record_hash"),
                        })
    direct_canonical_fact_count = 0
    merged_canonical_fact_count = 0
    for fact_id, fact in evidence_facts.items():
        owners = sorted(evidence_fact_owners[fact_id])
        matches = canonical_matches.get(fact_id, [])
        owner = owners[0] if owners else fact_id
        merged_ids = fact.get("grounding", {}).get("merged_equivalent_fact_ids", [])
        valid_direct = len(matches) == 1 and normalized(matches[0]["fact"]) == normalized(fact)
        valid_merge = False
        merge_sources: list[dict[str, Any]] = []
        if merged_ids:
            source_matches = [canonical_matches.get(item, []) for item in merged_ids]
            if all(len(items) == 1 for items in source_matches):
                merge_sources = [items[0] for items in source_matches]
                replayed = replay_semantic_merge([item["fact"] for item in merge_sources])
                valid_merge = normalized(replayed) == normalized(fact)
        audit.require(valid_direct or valid_merge, "CANONICAL_FACT_REPLAY", owner, {
            "fact_id": fact_id,
            "direct_match_count": len(matches),
            "merged_equivalent_fact_ids": merged_ids,
            "merge_source_match_counts": [len(canonical_matches.get(item, [])) for item in merged_ids],
        })
        direct_canonical_fact_count += int(valid_direct)
        merged_canonical_fact_count += int(valid_merge)
        if len(matches) == 1:
            match = matches[0]
            provenance = fact["provenance"]
            audit.require(normalized(match["fact"]) == normalized(fact), "CANONICAL_EVIDENCE_FACT_MISMATCH", owner, fact_id)
            audit.require(set(provenance["source_item_ids"]) <= set(match["source_item_ids"]), "CANONICAL_RECORD_SOURCE_ID_MISMATCH", owner, fact_id)
            audit.require(provenance["source_record_hash"] == match["source_record_hash"], "CANONICAL_RECORD_HASH_MISMATCH", owner, fact_id)
        elif valid_merge:
            merged_provenance = fact["grounding"].get("merged_provenance", [])
            audit.require(
                {normalized(item["fact"]["provenance"]) for item in merge_sources}
                == {normalized(item) for item in merged_provenance},
                "MERGED_PROVENANCE_MISMATCH", owner, fact_id,
            )

    unknown_source_paths = (
        [safe_path(root, value) for value in args.unknown_path]
        if args.unknown_path else
        [root / "candidates" / "unknown" / f"claims.{args.unknown_version}.jsonl"]
    )
    unknown_rows = [row for path in unknown_source_paths for row in read_jsonl(path)]
    unknown_by_id = {row["unknown_id"]: row for row in unknown_rows}
    if len(unknown_by_id) != len(unknown_rows):
        raise ValueError("DUPLICATE_UNKNOWN_ID_ACROSS_INPUTS")
    unknown_checked = 0
    for exported in unknown_exports:
        unknown_id = exported["sample_id"]
        source = unknown_by_id.get(unknown_id)
        if source is None:
            audit.fail("UNKNOWN_SOURCE_ROW_MISSING", unknown_id)
            continue
        unknown_checked += 1
        certificate_path = safe_path(root, source["certificate_path"])
        audit.require(certificate_path.is_file(), "UNKNOWN_CERTIFICATE_MISSING", unknown_id)
        if not certificate_path.is_file():
            continue
        actual_hash = sha256(certificate_path)
        audit.require(actual_hash == source["certificate_sha256"], "UNKNOWN_CERTIFICATE_HASH", unknown_id, {"expected": source["certificate_sha256"], "actual": actual_hash})
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        errors = list(schema_validators["unknown_certificate"].iter_errors(certificate))
        audit.require(not errors, "UNKNOWN_CERTIFICATE_SCHEMA", unknown_id, errors[0].message if errors else None)
        parent = auto_accepted_by_id.get(source["parent_pair_id"])
        audit.require(parent is not None, "UNKNOWN_PARENT_NOT_AUTO_ACCEPTED", unknown_id, source["parent_pair_id"])
        if parent is not None:
            audit.require(parent.get("status") == "AUTO_ACCEPTED", "UNKNOWN_PARENT_STATUS", unknown_id, parent.get("status"))
            audit.require(certificate["source_world_graph_hash"] == parent["world_graph_hash"], "UNKNOWN_PARENT_WORLD_HASH", unknown_id)
            parent_world_path = safe_path(root, parent["world_graph_path"])
            audit.require(parent_world_path.is_file(), "UNKNOWN_PARENT_WORLD_MISSING", unknown_id, parent["world_graph_path"])
            if parent_world_path.is_file():
                audit.require(sha256(parent_world_path) == parent["world_graph_hash"], "UNKNOWN_PARENT_WORLD_FILE_HASH", unknown_id)
            audit.require(parent.get("independent_verifier", {}).get("certificate_replay") == "PASS", "UNKNOWN_PARENT_VERIFIER", unknown_id)
        audit.require(exported["pair_id"] == source["parent_pair_id"] == certificate["parent_pair_id"], "UNKNOWN_PARENT_CHAIN", unknown_id)
        audit.require(exported["claim"] == source["claim"]["natural_text"], "UNKNOWN_TEXT_EXPORT_MISMATCH", unknown_id)
        audit.require(source["unknown_reason"] == certificate["unknown_reason"], "UNKNOWN_REASON_CHAIN", unknown_id)
        roles = [item.get("role") for item in exported["media"].get("source_references", [])]
        audit.require(set(roles) == set(certificate["available_evidence_ids"]), "UNKNOWN_AVAILABLE_EVIDENCE_CHAIN", unknown_id)
        audit.require(exported["media"].get("withheld_evidence", {}).get("role") in certificate["missing_decisive_evidence"], "UNKNOWN_WITHHELD_EVIDENCE_CHAIN", unknown_id)
        audit.require(certificate["satisfiable_with_claim"] and certificate["satisfiable_with_negation"], "UNKNOWN_WITNESS_SAT", unknown_id)

    failure_count = sum(audit.counts.values())
    report = {
        "schema_version": "1.0",
        "audit_version": "replay_chain_audit_v1",
        "release": args.release,
        "status": "PASS" if failure_count == 0 else "FAIL",
        "pair_count": len(pairs),
        "claim_count": len(claims),
        "unknown_count": len(unknown_exports),
        "sampled_pair_count": len(sampled),
        "artifact_reference_count": artifact_count,
        "artifact_unique_path_count": len(checked_artifact_paths),
        "world_reference_count": world_reference_count,
        "world_unique_path_count": len(world_cache),
        "evidence_unique_fact_count": len(evidence_facts),
        "provenance_fact_reference_count": provenance_fact_count,
        "canonical_file_count": len(canonical_files),
        "canonical_direct_fact_count": direct_canonical_fact_count,
        "canonical_merged_fact_count": merged_canonical_fact_count,
        "canonical_replayed_fact_count": direct_canonical_fact_count + merged_canonical_fact_count,
        "auto_accepted_parent_pool_count": len(auto_accepted_by_id),
        "realization_trace_count": len(realization_by_id),
        **({"proof_input_paths": [str(path.relative_to(root)) for path in auto_accepted_paths]} if args.proof_path else {}),
        **({"realization_input_paths": [str(path.relative_to(root)) for path in realization_paths]} if args.realization_path else {}),
        **({"unknown_input_paths": [str(path.relative_to(root)) for path in unknown_source_paths]} if args.unknown_path else {}),
        "unknown_checked_count": unknown_checked,
        "failure_count": failure_count,
        "failure_counts": dict(sorted(audit.counts.items())),
        "failure_examples": dict(sorted(audit.examples.items())),
        "verified_chain": [
            "canonical_record_and_fact", "world_graph", "evidence_subgraph",
            "supported_claim_graph", "typed_semantic_edit", "contradictory_claim_graph",
            "construction_trace", "proof_certificate", "realization_plan",
            "natural_text_alignment", "independent_verifier", "AUTO_ACCEPTED_export",
            "unknown_parent_and_witness_certificate",
        ],
    }
    output = root / "reports" / f"replay_chain_audit.{args.release}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if failure_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
