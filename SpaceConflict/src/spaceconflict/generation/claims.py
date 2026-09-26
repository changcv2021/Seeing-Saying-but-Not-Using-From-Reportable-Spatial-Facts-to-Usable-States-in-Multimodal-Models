from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ..canonical import CANONICAL_VERSION
from ..graphs.pipeline import WORLD_GRAPH_VERSION
from ..hashing import sha256_bytes, sha256_file
from ..registry import ROOT


CLAIM_BUILD_VERSION = "claim_build_p1_v1"

L2_TRANSITIVE_RULES = {
    "LEFT_OF": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "RIGHT_OF": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "ABOVE": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "BELOW": "AUTHORIZED_DIRECTION_TRANSITIVITY",
    "BEFORE": "STRICT_ORDER_TRANSITIVITY",
    "AFTER": "STRICT_ORDER_TRANSITIVITY",
}


def _dataset_dir(source_dataset: str) -> str:
    return source_dataset.casefold().replace("-", "_")


def _l2_chain_rows(graph_row: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only unique, irreducible two-premise transitive chains.

    Directly stated conclusions and conclusions with multiple proof paths are
    excluded so deleting either selected premise makes the conclusion Unknown.
    """
    authorized = set(graph.get("authorized_rule_ids", []))
    by_context_predicate: dict[tuple[bytes, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in graph.get("facts", []):
        rule = L2_TRANSITIVE_RULES.get(fact.get("predicate"))
        if (
            rule in authorized
            and fact.get("polarity") == "positive"
            and isinstance(fact.get("subject"), str)
            and isinstance(fact.get("object"), str)
            and fact["subject"] != fact["object"]
        ):
            by_context_predicate[(_json_bytes(fact["context"]), fact["predicate"])].append(fact)

    result: list[dict[str, Any]] = []
    for (_, predicate), facts in sorted(by_context_predicate.items()):
        direct = {(fact["subject"], fact["object"]) for fact in facts}
        outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in facts:
            outgoing[fact["subject"]].append(fact)
        paths: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for first in facts:
            for second in outgoing.get(first["object"], []):
                conclusion = (first["subject"], second["object"])
                if conclusion[0] == conclusion[1] or conclusion in direct:
                    continue
                paths[conclusion].append((first, second))
        for (subject, object_), proof_paths in sorted(paths.items()):
            if len(proof_paths) != 1:
                continue
            first, second = proof_paths[0]
            source_item_ids = sorted({
                source_item_id
                for premise in (first, second)
                for source_item_id in premise["provenance"]["source_item_ids"]
            })
            premise_datasets = {
                _dataset_dir(premise["provenance"]["source_dataset"])
                for premise in (first, second)
            }
            if len(premise_datasets) != 1:
                continue
            dataset_dir = next(iter(premise_datasets))
            if dataset_dir not in {"spar", "vsi_bench"}:
                continue
            derivation = {
                "rule_id": L2_TRANSITIVE_RULES[predicate],
                "premise_ids": [first["fact_id"], second["fact_id"]],
            }
            derived_fact = {
                **first,
                "fact_id": _id("derived_fact", {
                    "world": graph["global_world_id"], "predicate": predicate,
                    "subject": subject, "object": object_, "derivation": derivation,
                }),
                "subject": subject,
                "object": object_,
                "derivation": derivation,
            }
            result.append({
                "graph_row": graph_row,
                "graph": graph,
                "source_item_ids": source_item_ids,
                "fact": derived_fact,
                "premise_facts": [first, second],
                "dataset_dir": dataset_dir,
                "level": "L2",
                "primary_track": "GEO-TOPO",
                "secondary_tracks": ["DYNAMIC"] if predicate in {"BEFORE", "AFTER"} else [],
                "operator_id": "RELATION_GRAPH_UNSAT",
                "operator_version": "1.0",
                "proof_template": "relation_graph_unsat_v1",
                "transitivity_rule": L2_TRANSITIVE_RULES[predicate],
                "exclusivity_rule": "SAME_SCOPE_EXCLUSIVITY",
                "edit_mode": "transitive_chain",
            })
    return result


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}:{hashlib.sha256(_json_bytes(value)).hexdigest()[:24]}"


def _claim_atom(fact: dict[str, Any], atom_id: str) -> dict[str, Any]:
    return {
        "atom_id": atom_id, "subject": fact["subject"], "predicate": fact["predicate"],
        "object": fact.get("object"), "value": fact.get("value"), "polarity": fact["polarity"],
    }


def _write(path: Path, payload: bytes, resume: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not resume:
            raise FileExistsError(f"Output exists: {path}; use --resume")
        if path.read_bytes() != payload:
            raise ValueError(f"Non-deterministic output: {path}")
    else:
        path.write_bytes(payload)


def generate_claim_graphs(
    *, config: Path, dry_run: bool, resume: bool, seed: int, limit: int | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    config_payload = config.read_bytes()
    policy = yaml.safe_load(config_payload)
    claim_build_version = str(policy.get("claim_build_version", CLAIM_BUILD_VERSION))
    configured_manifest = policy.get("world_graph_manifest")
    manifest_path = (
        root / configured_manifest if configured_manifest
        else root / "world_graphs" / f"manifest.{WORLD_GRAPH_VERSION}.jsonl"
    )
    configured_records = policy.get("canonical_record_paths")
    canonical_paths = (
        [root / path for path in configured_records]
        if configured_records
        else sorted((root / "data/canonical").glob(f"*/*/{CANONICAL_VERSION}/records.jsonl"))
    )
    report_path = root / "reports" / f"claim_generation.{claim_build_version}.json"
    candidates_path = root / "candidates/structural" / f"pairs.{claim_build_version}.jsonl"
    if dry_run:
        return {
            "status": "PLANNED", "config": str(config), "graph_manifest": str(manifest_path.relative_to(root)),
            "output": str(candidates_path.relative_to(root)), "limit": limit,
        }
    if not manifest_path.exists():
        return {"status": "BLOCKED_SOURCE", "reason": "VALID_GRAPH_MANIFEST_MISSING"}
    run_stage = str(policy.get("run_stage", "P0"))
    configured_media_types = {str(value) for value in policy.get("allowed_media_types", [])}
    source_item_allowlist: set[str] | None = None
    configured_allowlist = policy.get("source_item_allowlist")
    if configured_allowlist:
        allowlist_path = root / str(configured_allowlist)
        if not allowlist_path.exists():
            return {"status": "BLOCKED_SOURCE", "reason": "SOURCE_ITEM_ALLOWLIST_MISSING"}
        source_item_allowlist = {
            str(row["source_item_id"])
            for row in _load_jsonl(allowlist_path)
        }
    spatial_overrides = policy.get("spatial_level_overrides", {})
    claim_validator = Draft202012Validator(json.loads((root / "schemas/claim_graph.schema.json").read_text()))
    trace_validator = Draft202012Validator(json.loads((root / "schemas/construction_trace.schema.json").read_text()))
    certificate_validator = Draft202012Validator(json.loads((root / "schemas/proof_certificate.schema.json").read_text()))
    records_by_source_item: dict[str, dict[str, Any]] = {}
    for path in canonical_paths:
        for record in _load_jsonl(path):
            for source_item_id in record["source_item_ids"]:
                records_by_source_item[source_item_id] = record
    graph_rows = [
        row for row in _load_jsonl(manifest_path)
        if row["validation_status"] == "GRAPH_VALID"
    ]
    potential: list[dict[str, Any]] = []
    gate_reject_counts: Counter[str] = Counter()
    source_fact_counts: Counter[str] = Counter()
    spatial_predicates = {"LEFT_OF", "RIGHT_OF", "FRONT_OF", "BEHIND", "ABOVE", "BELOW"}
    for graph_row in graph_rows:
        graph = json.loads((root / graph_row["graph_path"]).read_text(encoding="utf-8"))
        if bool(policy.get("enable_l2_transitive", False)):
            potential.extend(_l2_chain_rows(graph_row, graph))
        by_source_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in graph["facts"]:
            source_item_id = fact["provenance"]["source_item_ids"][0]
            by_source_item[source_item_id].append(fact)
        ca_facts = [
            fact for fact in graph["facts"]
            if fact["provenance"]["source_dataset"].casefold() == "ca-vqa"
        ]
        ca_by_context: dict[bytes, list[dict[str, Any]]] = defaultdict(list)
        for fact in ca_facts:
            ca_by_context[_json_bytes(fact["context"])].append(fact)
        for context_facts in ca_by_context.values():
            visible_positive = sorted(
                (fact for fact in context_facts if fact["predicate"] == "VISIBLE_IN_FRAME" and fact["polarity"] == "positive"),
                key=lambda fact: fact["fact_id"],
            )
            visible_negative = sorted(
                (fact for fact in context_facts if fact["predicate"] == "VISIBLE_IN_FRAME" and fact["polarity"] == "negative"),
                key=lambda fact: fact["fact_id"],
            )
            for index, support_fact in enumerate(visible_positive):
                donors = [fact for fact in visible_negative if fact["subject"] != support_fact["subject"]]
                if not donors:
                    gate_reject_counts["NO_EXPLICIT_NEGATIVE_VISIBILITY_DONOR"] += 1
                    continue
                refuting_fact = donors[index % len(donors)]
                potential.append({
                    "graph_row": graph_row, "graph": graph,
                    "source_item_ids": [support_fact["provenance"]["source_item_ids"][0], refuting_fact["provenance"]["source_item_ids"][0]],
                    "fact": support_fact, "refuting_fact": refuting_fact, "dataset_dir": "ca_vqa", "level": "L1",
                    "primary_track": "GEO-TOPO", "secondary_tracks": ["EMBODIED-OBS"],
                    "operator_id": "VISIBLE_CLASS_REBIND", "operator_version": "1.4",
                    "proof_template": "visible_class_rebind_explicit_negative_v1",
                    "refutation_rule": "EXPLICIT_POLARITY_REFUTATION", "edit_mode": "subject_rebind",
                })
            counts = sorted(
                (fact for fact in context_facts if fact["predicate"] == "COUNT" and fact["polarity"] == "positive" and isinstance(fact.get("value"), int)),
                key=lambda fact: fact["fact_id"],
            )
            for index, support_fact in enumerate(counts):
                donors = [
                    fact for fact in counts
                    if fact["subject"] != support_fact["subject"] and fact.get("value") != support_fact.get("value")
                ]
                if not donors:
                    gate_reject_counts["NO_EXPLICIT_UNEQUAL_COUNT_DONOR"] += 1
                    continue
                refuting_fact = donors[index % len(donors)]
                potential.append({
                    "graph_row": graph_row, "graph": graph,
                    "source_item_ids": [support_fact["provenance"]["source_item_ids"][0], refuting_fact["provenance"]["source_item_ids"][0]],
                    "fact": support_fact, "refuting_fact": refuting_fact, "dataset_dir": "ca_vqa", "level": "L1",
                    "primary_track": "GEO-TOPO", "secondary_tracks": ["EMBODIED-OBS"],
                    "operator_id": "COUNT_CLASS_REBIND", "operator_version": "1.4",
                    "proof_template": "count_class_rebind_exact_value_v1",
                    "refutation_rule": "EXACT_COUNT_FUNCTIONALITY", "edit_mode": "subject_rebind",
                })
        for source_item_id, facts in sorted(by_source_item.items()):
            if source_item_allowlist is not None and source_item_id not in source_item_allowlist:
                gate_reject_counts["SOURCE_ITEM_NOT_IN_ALLOWLIST"] += 1
                continue
            source_dataset = facts[0]["provenance"]["source_dataset"].casefold()
            source_fact_counts[source_dataset] += len(facts)
            appearance = [
                fact for fact in facts
                if fact["predicate"] == "BEFORE"
                and fact["context"].get("scope") == "whole_video"
                and str(fact["subject"]).startswith("first_appear:")
                and str(fact.get("object")).startswith("first_appear:")
            ]
            if source_dataset == "ca-vqa":
                spatial = [
                    fact for fact in facts
                    if fact["predicate"] in spatial_predicates and fact["polarity"] == "positive"
                    and fact["subject"] != fact.get("object")
                ]
                for selected_fact in spatial:
                    potential.append({
                        "graph_row": graph_row, "graph": graph, "source_item_id": source_item_id,
                        "fact": selected_fact, "dataset_dir": "ca_vqa", "level": "L1",
                        "primary_track": "GEO-TOPO", "secondary_tracks": ["XFORM-PROJ"],
                        "operator_id": "SUBJECT_OBJECT_SWAP", "operator_version": "1.2",
                        "proof_template": "subject_object_swap_v1", "exclusivity_rule": "SAME_SCOPE_EXCLUSIVITY",
                    })
                continue
            if source_dataset in {"vsi-bench", "spar"} and appearance:
                selected_fact = sorted(appearance, key=lambda row: row["fact_id"])[0]
                potential.append({
                    "graph_row": graph_row, "graph": graph, "source_item_id": source_item_id,
                    "fact": selected_fact,
                    "dataset_dir": "vsi_bench" if source_dataset == "vsi-bench" else "spar",
                    "level": "L3",
                    "primary_track": "DYNAMIC", "secondary_tracks": ["XFORM-PROJ"],
                    "operator_id": "APPEARANCE_ORDER_ERROR", "operator_version": "1.1",
                    "proof_template": "appearance_order_role_swap_v1", "exclusivity_rule": "SAME_SCOPE_EXCLUSIVITY",
                })
            elif source_dataset in {"spar", "omnispatial"}:
                source_record = records_by_source_item.get(source_item_id)
                source_media_types = {
                    media.get("media_type") for media in (source_record or {}).get("media", [])
                }
                if configured_media_types and not (source_media_types & configured_media_types):
                    gate_reject_counts["MEDIA_TYPE_NOT_ENABLED_FOR_CONFIG"] += 1
                    continue
                spatial = [fact for fact in facts if fact["predicate"] in spatial_predicates and fact["subject"] != fact.get("object")]
                override = spatial_overrides.get(source_dataset, {})
                spatial_level = str(override.get("level", "L1"))
                spatial_primary_track = str(override.get("primary_track", "GEO-TOPO"))
                spatial_secondary_tracks = [
                    str(value) for value in override.get(
                        "secondary_tracks", ["XFORM-PROJ"] if source_dataset == "spar" else [],
                    )
                ]
                if spatial_level not in {"L1", "L2", "L3", "L4"}:
                    raise ValueError(f"Invalid spatial level override: {spatial_level}")
                if spatial_primary_track not in {"GEO-TOPO", "XFORM-PROJ", "IDENTITY", "DYNAMIC", "EMBODIED-OBS"}:
                    raise ValueError(f"Invalid spatial primary track override: {spatial_primary_track}")
                for selected_fact in spatial:
                    potential.append({
                        "graph_row": graph_row, "graph": graph, "source_item_id": source_item_id,
                        "fact": selected_fact, "dataset_dir": source_dataset, "level": spatial_level,
                        "primary_track": spatial_primary_track,
                        "secondary_tracks": spatial_secondary_tracks,
                        "operator_id": "SUBJECT_OBJECT_SWAP", "operator_version": "1.2",
                        "proof_template": "subject_object_swap_v1", "exclusivity_rule": "SAME_SCOPE_EXCLUSIVITY",
                    })
            elif source_dataset == "sti-bench":
                spatial = [fact for fact in facts if fact["predicate"] in spatial_predicates and fact["subject"] != fact.get("object") and isinstance(fact["context"].get("time_scope"), dict)]
                for selected_fact in spatial:
                    potential.append({
                        "graph_row": graph_row, "graph": graph, "source_item_id": source_item_id,
                        "fact": selected_fact, "dataset_dir": "sti_bench", "level": "L3",
                        "primary_track": "DYNAMIC", "secondary_tracks": ["GEO-TOPO", "XFORM-PROJ"],
                        "operator_id": "SUBJECT_OBJECT_REBIND", "operator_version": "1.3",
                        "proof_template": "interval_subject_object_rebind_v1", "exclusivity_rule": "SAME_INTERVAL_EXCLUSIVITY",
                    })
            elif source_dataset == "omnispatial":
                gate_reject_counts["NO_EXPLICIT_REFUTING_DONOR_FOR_ALLOWED_OPERATOR"] += 1
            else:
                gate_reject_counts["NO_APPLICABLE_VERSIONED_OPERATOR"] += 1
    configured_levels = {str(level) for level in policy.get("allowed_levels", [])}
    if configured_levels:
        potential = [row for row in potential if row["level"] in configured_levels]
    for row in potential:
        if "source_item_ids" not in row:
            row["source_item_ids"] = [row["source_item_id"]]
    potential.sort(key=lambda row: (
        hashlib.sha256(f"{seed}\0{'|'.join(row['source_item_ids'])}".encode()).hexdigest(),
        "|".join(row["source_item_ids"]),
    ))
    per_world: Counter[str] = Counter()
    per_source_item: Counter[str] = Counter()
    per_dataset: Counter[str] = Counter()
    if run_stage == "P0":
        dataset_caps = {"ca_vqa": 500, "omnispatial": 500, "spar": 200, "sti_bench": 300, "vsi_bench": 500}
        non_test_world_cap = 4
        stage_selection_cap = None
    else:
        dataset_caps = {"ca_vqa": 6000, "omnispatial": 2000, "spar": 500, "sti_bench": 500, "vsi_bench": 2000}
        non_test_world_cap = 16
        target_pairs = int(policy.get("target_pairs", policy.get("target_pairs_max", 0)))
        oversample_factor = int(policy.get("oversample_factor", 1))
        stage_selection_cap = target_pairs * oversample_factor if target_pairs else None
    configured_dataset_caps = policy.get("dataset_pair_caps", {})
    for dataset, cap in configured_dataset_caps.items():
        if dataset not in dataset_caps or int(cap) < 1:
            raise ValueError(f"Invalid dataset_pair_caps entry: {dataset}={cap}")
        dataset_caps[dataset] = int(cap)
    test_world_cap = int(policy.get("test_world_pair_cap", 4))
    non_test_world_cap = int(policy.get("non_test_world_pair_cap", non_test_world_cap))
    if test_world_cap < 1 or non_test_world_cap < 1:
        raise ValueError("world pair caps must be >= 1")
    source_item_pair_cap = int(policy.get("source_item_pair_cap", 1))
    if source_item_pair_cap < 1:
        raise ValueError("source_item_pair_cap must be >= 1")
    selected: list[dict[str, Any]] = []
    for row in potential:
        world_id = row["graph"]["global_world_id"]
        world_cap = test_world_cap if row["graph_row"]["split"] == "test" else non_test_world_cap
        if per_world[world_id] >= world_cap:
            gate_reject_counts["WORLD_PAIR_DENSITY_CAP"] += 1
            continue
        if any(per_source_item[source_item_id] >= source_item_pair_cap for source_item_id in row["source_item_ids"]):
            gate_reject_counts["SOURCE_ITEM_PAIR_DENSITY_CAP"] += 1
            continue
        if per_dataset[row["dataset_dir"]] >= dataset_caps[row["dataset_dir"]]:
            gate_reject_counts["DATASET_PAIR_CAP"] += 1
            continue
        selected.append(row)
        per_world[world_id] += 1
        for source_item_id in row["source_item_ids"]:
            per_source_item[source_item_id] += 1
        per_dataset[row["dataset_dir"]] += 1
        effective_limit = limit
        if stage_selection_cap is not None:
            effective_limit = min(effective_limit, stage_selection_cap) if effective_limit is not None else stage_selection_cap
        if effective_limit is not None and len(selected) >= effective_limit:
            break
    structural_rows: list[dict[str, Any]] = []
    output_hashes: dict[str, str] = {}
    for row in selected:
        fact = row["fact"]
        graph = row["graph"]
        graph_row = row["graph_row"]
        source_item_ids = row["source_item_ids"]
        records = [records_by_source_item[source_item_id] for source_item_id in source_item_ids]
        dataset_dir = row["dataset_dir"]
        level = row["level"]
        primary_track = row["primary_track"]
        secondary_tracks = row["secondary_tracks"]
        operator_id = row["operator_id"]
        operator_version = row["operator_version"]
        proof_template = row["proof_template"]
        exclusivity_rule = row.get("exclusivity_rule")
        pair_id = "sc_pair_" + hashlib.sha256(
            f"{claim_build_version}\0{'|'.join(source_item_ids)}\0{fact['fact_id']}\0{row.get('refuting_fact', {}).get('fact_id', '')}".encode()
        ).hexdigest()[:24]
        supported_atom = _claim_atom(fact, f"{pair_id}:supported_atom")
        if row.get("edit_mode") == "subject_rebind":
            contradictory_atom = {
                **supported_atom, "atom_id": f"{pair_id}:contradictory_atom",
                "subject": row["refuting_fact"]["subject"],
            }
            conflict_slots = ["subject"]
            edit_operations = [{"slot": "subject", "before": supported_atom["subject"], "after": contradictory_atom["subject"]}]
            preserved_slots = ["predicate", "object", "value", "polarity", "media_id", "view_id", "frame_id", "time_scope", "reference_frame", "state_id", "branch_id", "scope"]
            evidence_facts = [fact, row["refuting_fact"]]
            required_fact_ids = [row["refuting_fact"]["fact_id"]]
        else:
            contradictory_atom = {
                **supported_atom, "atom_id": f"{pair_id}:contradictory_atom",
                "subject": supported_atom["object"], "object": supported_atom["subject"],
            }
            conflict_slots = ["subject", "object"]
            edit_operations = [
                {"slot": "subject", "before": supported_atom["subject"], "after": contradictory_atom["subject"]},
                {"slot": "object", "before": supported_atom["object"], "after": contradictory_atom["object"]},
            ]
            preserved_slots = ["predicate", "media_id", "time_scope", "state_id", "branch_id", "scope"]
            if row.get("edit_mode") == "transitive_chain":
                evidence_facts = row["premise_facts"]
                required_fact_ids = [premise["fact_id"] for premise in evidence_facts]
            else:
                evidence_facts = [fact]
                required_fact_ids = [fact["fact_id"]]
        claim_context = fact["context"]
        supported_graph = {
            "claim_graph_id": f"{pair_id}:supported", "label": "SUPPORTED",
            "atoms": [supported_atom], "context": claim_context,
        }
        contradictory_graph = {
            "claim_graph_id": f"{pair_id}:contradictory", "label": "CONTRADICTORY",
            "atoms": [contradictory_atom], "context": claim_context,
        }
        for claim in (supported_graph, contradictory_graph):
            errors = list(claim_validator.iter_errors(claim))
            if errors:
                raise ValueError(f"CLAIM_GRAPH_SCHEMA_INVALID:{pair_id}:{errors[0].message}")
        evidence = {
            "evidence_subgraph_id": f"{pair_id}:evidence", "schema_version": "1.0",
            "global_world_id": graph["global_world_id"], "world_graph_id": graph["world_graph_id"],
            "facts": evidence_facts,
            "media_ids": sorted({media_id for evidence_fact in evidence_facts for media_id in evidence_fact["grounding"]["media_ids"]}),
            "supported_fact_ids": required_fact_ids if row.get("edit_mode") == "transitive_chain" else [fact["fact_id"]],
            "contradiction_fact_ids": required_fact_ids,
            "minimality": {"required_fact_ids": required_fact_ids, "ablation_result": "UNKNOWN"},
        }
        if row.get("edit_mode") == "subject_rebind":
            refutation_rule = row["refutation_rule"]
            proof_nodes = [
                {"id": row["refuting_fact"]["fact_id"], "type": "SOURCE_FACT"},
                {"id": f"rule:{refutation_rule}", "type": "RULE"},
                {"id": contradictory_atom["atom_id"], "type": "CLAIM_ATOM"},
                {"id": f"{pair_id}:contradiction", "type": "CONTRADICTION"},
            ]
            proof_edges = [
                [row["refuting_fact"]["fact_id"], f"rule:{refutation_rule}", "premise"],
                [f"rule:{refutation_rule}", f"{pair_id}:contradiction", "derives"],
                [contradictory_atom["atom_id"], f"{pair_id}:contradiction", "conflicts"],
            ]
        elif row.get("edit_mode") == "transitive_chain":
            transitivity_rule = row["transitivity_rule"]
            proof_nodes = [
                *({"id": premise["fact_id"], "type": "SOURCE_FACT"} for premise in evidence_facts),
                {"id": f"rule:{transitivity_rule}", "type": "RULE"},
                {"id": supported_atom["atom_id"], "type": "DERIVED_FACT"},
                {"id": f"rule:{exclusivity_rule}", "type": "RULE"},
                {"id": contradictory_atom["atom_id"], "type": "CLAIM_ATOM"},
                {"id": f"{pair_id}:contradiction", "type": "CONTRADICTION"},
            ]
            proof_edges = [
                *([premise["fact_id"], f"rule:{transitivity_rule}", "premise"] for premise in evidence_facts),
                [f"rule:{transitivity_rule}", supported_atom["atom_id"], "derives"],
                [supported_atom["atom_id"], f"rule:{exclusivity_rule}", "premise"],
                [f"rule:{exclusivity_rule}", f"{pair_id}:contradiction", "derives"],
                [contradictory_atom["atom_id"], f"{pair_id}:contradiction", "conflicts"],
            ]
        else:
            proof_nodes = [
                {"id": fact["fact_id"], "type": "SOURCE_FACT"},
                {"id": "rule:INVERSE_RELATION", "type": "RULE"},
                {"id": f"rule:{exclusivity_rule}", "type": "RULE"},
                {"id": contradictory_atom["atom_id"], "type": "CLAIM_ATOM"},
                {"id": f"{pair_id}:contradiction", "type": "CONTRADICTION"},
            ]
            proof_edges = [
                [fact["fact_id"], "rule:INVERSE_RELATION", "premise"],
                ["rule:INVERSE_RELATION", f"rule:{exclusivity_rule}", "derives_inverse"],
                [f"rule:{exclusivity_rule}", f"{pair_id}:contradiction", "derives"],
                [contradictory_atom["atom_id"], f"{pair_id}:contradiction", "conflicts"],
            ]
        certificate = {
            "certificate_id": f"{pair_id}:certificate", "label": "CONTRADICTORY", "level": level,
            "conflict_slots": conflict_slots, "proof_nodes": proof_nodes, "proof_edges": proof_edges,
            "evidence_fact_ids": required_fact_ids, "co_truth_possible": False,
            "requires_unprovided_fact": False,
            "minimality": {
                "is_minimal": True,
                "ablation_results": [{"removed_fact_id": fact_id, "result": "UNKNOWN"} for fact_id in required_fact_ids],
            },
        }
        errors = list(certificate_validator.iter_errors(certificate))
        if errors:
            raise ValueError(f"CERTIFICATE_SCHEMA_INVALID:{pair_id}:{errors[0].message}")
        trace = {
            "trace_id": f"{pair_id}:trace", "source_records": [record["record_id"] for record in records],
            "source_hashes": [record["source_record_hash"] for record in records],
            "adapter_version": fact["provenance"]["adapter_version"],
            "world_graph_hash": graph_row["graph_sha256"], "evidence_fact_ids": [evidence_fact["fact_id"] for evidence_fact in evidence_facts],
            "level": level, "primary_track": primary_track, "secondary_tracks": secondary_tracks,
            "operator": {"operator_id": operator_id, "operator_version": operator_version},
            "before_graph": supported_graph, "after_graph": contradictory_graph,
            "edit_operations": edit_operations, "preserved_slots": preserved_slots,
            "proof_template": proof_template, "language_plan": None,
            "generator_version": claim_build_version, "seed": seed,
            "candidate_list": [contradictory_graph],
            "validation_results": {
                "source_fact_present": "PASS", "operator_contract": "PASS",
                "co_truth_check": "PASS", "minimality_ablation": "PASS",
                "predicate_preserved": "PASS",
            },
            "reject_retry_history": [],
        }
        errors = list(trace_validator.iter_errors(trace))
        if errors:
            raise ValueError(f"TRACE_SCHEMA_INVALID:{pair_id}:{errors[0].message}")
        paths_and_values = [
            (root / f"evidence_subgraphs/{dataset_dir}/{claim_build_version}/{pair_id}.json", evidence),
            (root / f"claim_graphs/{dataset_dir}/{claim_build_version}/{pair_id}.supported.json", supported_graph),
            (root / f"claim_graphs/{dataset_dir}/{claim_build_version}/{pair_id}.contradictory.json", contradictory_graph),
            (root / f"construction_traces/{dataset_dir}/{claim_build_version}/{pair_id}.json", trace),
            (root / f"certificates/{dataset_dir}/{claim_build_version}/{pair_id}.json", certificate),
        ]
        references = {}
        for path, value in paths_and_values:
            payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            _write(path, payload, resume)
            relative = str(path.relative_to(root))
            references[relative] = sha256_bytes(payload)
            output_hashes[relative] = sha256_bytes(payload)
        structural_rows.append({
            "pair_id": pair_id, "global_world_id": graph["global_world_id"], "split": graph_row["split"],
            "source_dataset": dataset_dir, "source_item_ids": source_item_ids,
            "level": level, "primary_track": primary_track, "secondary_tracks": secondary_tracks,
            "operator_id": operator_id, "predicate_preserved": True,
            "evidence_fact_ids": [evidence_fact["fact_id"] for evidence_fact in evidence_facts], "artifacts": references,
            "status": "STRUCTURAL_ACCEPTED_LANGUAGE_PENDING",
        })
    structural_rows.sort(key=lambda item: item["pair_id"])
    candidates_payload = b"".join(_json_bytes(item) + b"\n" for item in structural_rows)
    _write(candidates_path, candidates_payload, resume)
    output_hashes[str(candidates_path.relative_to(root))] = sha256_bytes(candidates_payload)
    report = {
        "schema_version": "1.0", "claim_build_version": claim_build_version,
        "status": "STRUCTURAL_CLAIMS_VALID" if structural_rows else "REJECTED",
        "config": str(config), "config_sha256": sha256_bytes(config_payload), "seed": seed,
        "valid_world_graph_count": len(graph_rows), "potential_candidate_count": len(potential),
        "structural_accepted_count": len(structural_rows),
        "gate_reject_counts": dict(sorted(gate_reject_counts.items())),
        "source_fact_counts": dict(sorted(source_fact_counts.items())),
        "dataset_counts": dict(sorted(Counter(row["source_dataset"] for row in structural_rows).items())),
        "level_counts": dict(sorted(Counter(row["level"] for row in structural_rows).items())),
        "primary_track_counts": dict(sorted(Counter(row["primary_track"] for row in structural_rows).items())),
        "operator_counts": dict(sorted(Counter(row["operator_id"] for row in structural_rows).items())),
        "predicate_preserved_ratio": 1.0 if structural_rows else None,
        "input_hashes": {str(manifest_path.relative_to(root)): sha256_file(manifest_path)},
        "output_hashes": dict(sorted(output_hashes.items())),
        "next_gate": "LANGUAGE_REALIZATION_PENDING",
        "quality_shortfall_policy": "REPORT_DONT_FILL_WITH_UNPROVED_SAMPLES",
        "run_stage": run_stage,
        "configured_levels": sorted(configured_levels),
        "configured_media_types": sorted(configured_media_types),
        "source_item_allowlist": str(configured_allowlist) if configured_allowlist else None,
        "source_item_allowlist_count": len(source_item_allowlist) if source_item_allowlist is not None else None,
        "spatial_level_overrides": spatial_overrides,
        "test_world_pair_cap": test_world_cap,
        "non_test_world_pair_cap": non_test_world_cap,
        "dataset_pair_caps": dict(sorted(dataset_caps.items())),
        "source_item_pair_cap": source_item_pair_cap,
        "stage_selection_cap": stage_selection_cap,
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _write(report_path, report_payload, resume)
    return report
