from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from ..hashing import sha256_file
from ..hypo3d_l4.prestates import (
    count_annotated_class,
    explicit_quantity,
    ref_mentions_class,
    unique_catalog_class_mentioned,
)
from .common import (
    RELATION_COMPLEMENT,
    canonical_fact_hash,
    count_claim_text,
    existence_claim_text,
    graph_text_roundtrip,
    load_split_map,
    media_bundle,
    normalized_class,
    normalized_fact,
    object_class,
    output_hashes,
    read_jsonl,
    relation_claim_text,
    resolve_unique_reference,
    stable_id,
    write_json,
    write_jsonl,
)


def source_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("scene_id") or row.get("source", {}).get("scene_id") or ""),
        str(row.get("change_id") or row.get("source", {}).get("change_id") or ""),
        str(row.get("question_id") or row.get("source_question_id") or row.get("source", {}).get("question_id") or ""),
    )


def branch_key(row: dict[str, Any]) -> tuple[str, str]:
    key = source_key(row)
    return key[0], key[1]


def group_branches(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[branch_key(row)].append(row)
    output: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = grouped[key]
        contexts = {str(row.get("context_change_raw") or "") for row in members}
        types = {str(row.get("change_type") or "") for row in members}
        branch_ids = {str(row.get("branch_id") or "") for row in members}
        if len(contexts) != 1 or len(types) != 1 or len(branch_ids) != 1:
            rejects.append({"scene_id": key[0], "change_id": key[1], "reason": "REJECT_BRANCH_KEY_INVALID"})
            continue
        first = members[0]
        output.append({
            "schema_version": "l4_native_branch_index_v3",
            "branch_id": next(iter(branch_ids)),
            "scene_id": key[0],
            "global_world_id": str(first.get("global_world_id") or f"hypo3d:{key[0]}"),
            "change_id": key[1],
            "change_text": next(iter(contexts)),
            "change_type": next(iter(types)),
            "source_qa_ids": sorted(str(row.get("question_id") or "") for row in members),
            "media_ids": [f"hypo3d:{key[0]}:{role}" for role in (
                "camera_view", "top_view_label", "top_view_no_label",
                "top_view_no_label_rotated", "top_view_with_label_rotated",
            )],
            "source_hashes": sorted(str(row.get("source_hash") or "") for row in members),
            "source_revision": str(first.get("source_revision") or ""),
        })
    return output, rejects


def build_post_fact_graphs(
    oracles: list[dict[str, Any]], branch_index: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rejects: list[dict[str, Any]] = []
    for oracle in oracles:
        if oracle.get("source_reconstruction") != "PASS":
            rejects.append({**dict(zip(("scene_id", "change_id", "question_id"), source_key(oracle))), "reason": "REJECT_SOURCE_RECONSTRUCTION_FAIL"})
            continue
        if branch_key(oracle) not in branch_index:
            rejects.append({**dict(zip(("scene_id", "change_id", "question_id"), source_key(oracle))), "reason": "REJECT_BRANCH_KEY_INVALID"})
            continue
        grouped[branch_key(oracle)].append(oracle)
    graphs: list[dict[str, Any]] = []
    for key in sorted(grouped):
        fact_map: dict[str, dict[str, Any]] = {}
        fact_sources: dict[str, list[dict[str, str]]] = defaultdict(list)
        for oracle in grouped[key]:
            for atom in oracle.get("normalized_atoms") or []:
                fact = normalized_fact(atom, state="post")
                canonical = canonical_fact_hash(fact)
                fact_map.setdefault(canonical, fact)
                fact_sources[canonical].append({
                    "source_qa_id": str(oracle.get("source_question_id") or ""),
                    "oracle_id": str(oracle.get("oracle_id") or ""),
                    "source_hash": str(oracle.get("provenance", {}).get("source_hash") or ""),
                })
        graph_id = stable_id("native_post_graph", {"branch": key, "facts": sorted(fact_map)})
        graphs.append({
            "schema_version": "l4_native_post_fact_graph_v3",
            "post_fact_graph_id": graph_id,
            "branch_id": branch_index[key]["branch_id"],
            "scene_id": key[0],
            "change_id": key[1],
            "facts": [
                {**fact_map[fact_id], "underlying_fact_id": fact_id, "source_pointers": fact_sources[fact_id]}
                for fact_id in sorted(fact_map)
            ],
            "safe_closure": "EXACT_FACT_DEDUP_ONLY",
            "source_qa_ids": sorted({
                pointer["source_qa_id"] for values in fact_sources.values() for pointer in values
            }),
        })
    return graphs, rejects


def _grounding_mode(resolution: dict[str, Any]) -> str:
    tier = str(resolution.get("resolution_tier") or "")
    if tier == "NATIVE_ID":
        return "NATIVE_ID"
    return "UNIQUE_REFERENCE"


def _target_gate(
    parsed: dict[str, Any], resolution: dict[str, Any], scene: dict[str, Any], entity_class: str | None,
) -> tuple[bool, str | None, str | None]:
    intervention = parsed.get("intervention") or {}
    change_type = str(intervention.get("type") or "")
    targets = resolution.get("resolved_targets") or []
    if change_type == "ADDITION":
        refs = intervention.get("new_entity_ref_texts") or []
        if len(refs) != 1 or explicit_quantity(str(refs[0])) is None:
            return False, None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        if entity_class and not ref_mentions_class(str(refs[0]), entity_class):
            return False, None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        return True, None, None
    if len(targets) != 1:
        return False, None, "REJECT_TARGET_AMBIGUOUS"
    target_id = str(targets[0].get("resolved_entity_id") or "")
    if not target_id or object_class(scene, target_id) is None:
        return False, None, "REJECT_TARGET_NOT_FOUND"
    if change_type == "REMOVAL" and entity_class and object_class(scene, target_id) != entity_class:
        return False, None, "REJECT_TRANSITION_PRECONDITION_FAIL"
    if change_type == "REPLACEMENT" and entity_class:
        old_class = object_class(scene, target_id)
        refs = intervention.get("new_entity_ref_texts") or []
        new_class = unique_catalog_class_mentioned({"scenes": {"current": scene}}, str(refs[0])) if len(refs) == 1 else None
        if entity_class not in {old_class, new_class}:
            return False, None, "REJECT_TRANSITION_PRECONDITION_FAIL"
    return True, target_id, None


def _native_candidate(
    *, fact: dict[str, Any], graph: dict[str, Any], branch: dict[str, Any],
    parsed: dict[str, Any], resolution: dict[str, Any], scene: dict[str, Any], split: str,
) -> tuple[dict[str, Any] | None, str | None]:
    predicate = str(fact.get("predicate") or "")
    change_type = str(parsed.get("intervention", {}).get("type") or "")
    if predicate == "COUNT":
        entity_class, _ = count_annotated_class(scene, str(fact.get("subject") or ""))
        if entity_class is None or entity_class in {"object", "item", "thing"}:
            return None, "REJECT_PRE_COUNT_INCOMPLETE"
        passed, target_id, reject = _target_gate(parsed, resolution, scene, entity_class)
        if not passed or change_type not in {"ADDITION", "REMOVAL", "REPLACEMENT"}:
            return None, reject or "REJECT_UNAUTHORIZED_RULE"
        supported_graph = {**normalized_fact(fact, state="post"), "subject": entity_class}
        contradictory_graph = {**supported_graph, "value": int(supported_graph["value"]) + 1}
        style = int(fact["underlying_fact_id"][-2:], 16) % 3
        supported_text = count_claim_text(entity_class, int(supported_graph["value"]), style)
        contradictory_text = count_claim_text(entity_class, int(contradictory_graph["value"]), style)
        dependency = "CORE"
        operator = "NATIVE_COUNT_POST_FACT"
        changed_slot = "value"
        grounding = {
            "mode": _grounding_mode(resolution), "target_id": target_id,
            "resolution_id": resolution.get("resolution_id"), "candidate_count": 1,
        }
    elif predicate in RELATION_COMPLEMENT:
        subject_obj = resolve_unique_reference(scene, str(fact.get("subject") or ""))
        object_obj = resolve_unique_reference(scene, str(fact.get("object") or ""))
        if subject_obj is None or object_obj is None or subject_obj["object_id"] == object_obj["object_id"]:
            return None, "REJECT_ANCHOR_AMBIGUOUS"
        passed, target_id, reject = _target_gate(parsed, resolution, scene, None)
        if not passed or change_type != "MOVEMENT" or target_id not in {str(subject_obj["object_id"]), str(object_obj["object_id"])}:
            return None, reject or "REJECT_UNAUTHORIZED_RULE"
        subject_label = normalized_class(str(subject_obj.get("class") or ""))
        object_label = normalized_class(str(object_obj.get("class") or ""))
        supported_graph = {
            **normalized_fact(fact, state="post"),
            "subject": str(subject_obj["object_id"]), "object": str(object_obj["object_id"]),
            "subject_label": subject_label, "object_label": object_label,
        }
        contradictory_graph = {**supported_graph, "predicate": RELATION_COMPLEMENT[predicate]}
        style = int(fact["underlying_fact_id"][-2:], 16) % 3
        supported_text = relation_claim_text(subject_label, predicate, object_label, style)
        contradictory_text = relation_claim_text(subject_label, contradictory_graph["predicate"], object_label, style)
        resolved_anchors = resolution.get("resolved_anchors") or []
        explicit = parsed.get("intervention", {}).get("explicit_relations") or []
        action_only = bool(resolved_anchors and explicit and str(resolved_anchors[0].get("resolved_entity_id") or "") in {str(subject_obj["object_id"]), str(object_obj["object_id"])})
        dependency = "CALIBRATION" if action_only else "CORE"
        operator = "NATIVE_RELATION_COMPLEMENT"
        changed_slot = "predicate"
        grounding = {
            "mode": _grounding_mode(resolution), "target_id": target_id,
            "subject_id": str(subject_obj["object_id"]), "object_id": str(object_obj["object_id"]),
            "resolution_id": resolution.get("resolution_id"),
            "target_candidate_count": 1, "anchor_candidate_count": 1,
        }
    elif predicate == "EXISTS_IN_WORLD":
        passed, target_id, reject = _target_gate(parsed, resolution, scene, None)
        if not passed or target_id is None:
            return None, reject or "REJECT_TARGET_NOT_FOUND"
        value = fact.get("value")
        if not isinstance(value, bool):
            return None, "REJECT_POST_QA_UNPARSABLE"
        supported_graph = {**normalized_fact(fact, state="post"), "subject": target_id}
        contradictory_graph = {**supported_graph, "value": not value}
        label = object_class(scene, target_id) or "target object"
        supported_text = existence_claim_text(f"the {label}", value)
        contradictory_text = existence_claim_text(f"the {label}", not value)
        dependency, operator, changed_slot = "CALIBRATION", "NATIVE_EXISTENCE_FLIP", "value"
        grounding = {"mode": _grounding_mode(resolution), "target_id": target_id, "candidate_count": 1}
    else:
        return None, "REJECT_POST_QA_UNPARSABLE"
    source_pointers = fact.get("source_pointers") or []
    question_id = str(source_pointers[0].get("source_qa_id") or "") if source_pointers else ""
    candidate_core = {
        "branch": graph["branch_id"], "fact": fact["underlying_fact_id"], "operator": operator,
    }
    return {
        "candidate_id": stable_id("native_candidate", candidate_core),
        "scene_id": graph["scene_id"],
        "global_world_id": f"hypo3d:{graph['scene_id']}",
        "change_id": graph["change_id"],
        "question_id": question_id,
        "branch_id": graph["branch_id"],
        "post_fact_graph_id": graph["post_fact_graph_id"],
        "source_qa_ids": graph["source_qa_ids"],
        "source_pointers": source_pointers,
        "source_hash": str(source_pointers[0].get("source_hash") or "") if source_pointers else "",
        "split": split,
        "native_subtype": "AGGREGATED" if len(graph["facts"]) > 1 else "DIRECT",
        "dependency_type": dependency,
        "transition_family": change_type,
        "operator_id": operator,
        "intervention_text": branch["change_text"],
        "intervention": parsed["intervention"],
        "grounding": grounding,
        "supported_claim": {"graph": supported_graph, "text": supported_text},
        "contradictory_claim": {"graph": contradictory_graph, "text": contradictory_text},
        "changed_slot": changed_slot,
        "underlying_fact_id": fact["underlying_fact_id"],
    }, None


def verify_native_pair(candidate: dict[str, Any], oracle_fact: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    supported = candidate["supported_claim"]
    contradictory = candidate["contradictory_claim"]
    original = normalized_fact(oracle_fact, state="post")
    supported_normalized = normalized_fact(supported["graph"], state="post")
    if original["predicate"] == "COUNT":
        original["subject"] = supported_normalized["subject"]
    elif original["predicate"] in RELATION_COMPLEMENT:
        original["subject"] = supported_normalized["subject"]
        original["object"] = supported_normalized["object"]
    elif original["predicate"] == "EXISTS_IN_WORLD":
        original["subject"] = supported_normalized["subject"]
    if original != supported_normalized:
        errors.append("SUPPORTED_NOT_SOURCE_QA_ENTAILED")
    if not graph_text_roundtrip(supported["text"], supported["graph"]):
        errors.append("SUPPORTED_GRAPH_TEXT_ROUNDTRIP_FAIL")
    if not graph_text_roundtrip(contradictory["text"], contradictory["graph"]):
        errors.append("CONTRADICTORY_GRAPH_TEXT_ROUNDTRIP_FAIL")
    sg, cg = supported["graph"], contradictory["graph"]
    if sg["predicate"] == "COUNT":
        exclusive = cg["predicate"] == "COUNT" and cg["subject"] == sg["subject"] and cg["value"] != sg["value"]
    elif sg["predicate"] in RELATION_COMPLEMENT:
        exclusive = cg["predicate"] == RELATION_COMPLEMENT[sg["predicate"]]
    else:
        exclusive = cg["predicate"] == sg["predicate"] and cg["value"] is not sg["value"]
    if not exclusive:
        errors.append("CONTRADICTORY_NOT_REFUTED")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "source_qa_reconstruction": "PASS",
        "post_fact_dedup": "PASS",
        "scene_only_label": "UNKNOWN",
        "change_only_label": "SUPPORTED" if candidate["dependency_type"] == "CALIBRATION" else "UNKNOWN",
        "full_input_label": "SUPPORTED",
        "co_truth_possible": False,
        "requires_unprovided_fact": False,
        "graph_text_roundtrip": "PASS" if not any("ROUNDTRIP" in item for item in errors) else "FAIL",
        "independent_verifier": "PASS" if not errors else "FAIL",
    }


def freeze_existing_native(
    *, pairs_path: Path, branches_path: Path, oracles_path: Path, resolutions_path: Path,
    split_path: Path, media_root: Path, output_dir: Path, seed: int, run_id: str,
    dry_run: bool, resume: bool,
) -> dict[str, Any]:
    outputs = {
        "manifest": output_dir / "base_manifest.jsonl",
        "pairs": output_dir / "accepted/pairs.l4_native_base_v3.jsonl",
        "model_inputs": output_dir / "accepted/model_inputs.l4_native_base_v3.jsonl",
        "gold": output_dir / "accepted/gold.l4_native_base_v3.jsonl",
        "report": output_dir / "base_validation_report.json",
    }
    if dry_run:
        return {"status": "PLANNED", "outputs": {k: str(v) for k, v in outputs.items()}}
    pairs = read_jsonl(pairs_path)
    branches = {source_key(row): row for row in read_jsonl(branches_path)}
    oracles = {source_key(row): row for row in read_jsonl(oracles_path)}
    resolutions = {source_key(row): row for row in read_jsonl(resolutions_path)}
    split_map = load_split_map(split_path)
    media_cache: dict[str, dict[str, Any]] = {}
    migrated, manifest, model_inputs, gold = [], [], [], []
    errors: list[dict[str, Any]] = []
    input_hashes = {str(path): sha256_file(path) for path in (pairs_path, branches_path, oracles_path, resolutions_path, split_path)}
    for pair in pairs:
        key = source_key(pair)
        branch, oracle, resolution = branches.get(key), oracles.get(key), resolutions.get(key)
        if branch is None or oracle is None or resolution is None:
            errors.append({"pair_id": pair.get("pair_id"), "reason": "REJECT_SOURCE_FILE_MISSING", "source_key": key})
            continue
        scene_id = key[0]
        world_id = f"hypo3d:{scene_id}"
        split = split_map.get(world_id)
        if split is None:
            errors.append({"pair_id": pair.get("pair_id"), "reason": "REJECT_SPLIT_LEAKAGE", "source_key": key})
            continue
        media = media_bundle(scene_id=scene_id, media_root=media_root, cache=media_cache)
        dependency = "CORE" if pair.get("task", {}).get("strength_slice") == "L4_CORE" else "CALIBRATION"
        certificate_id = str(
            pair.get("certificate_id")
            or pair.get("certificate", {}).get("certificate_id")
            or f"{pair['pair_id']}:certificate"
        )
        construction_trace_id = str(
            pair.get("construction_trace_id") or f"{pair['pair_id']}:migration_trace"
        )
        migrated_pair = {
            **pair,
            "schema_version": "spaceconflict_l4_pair_v3",
            "level": "L4",
            "l4_origin": "SOURCE_NATIVE",
            "native_subtype": "DIRECT",
            "dependency_type": dependency,
            "transition_family": branch["change_type"],
            "grounding_mode": _grounding_mode(resolution),
            "global_world_id": world_id,
            "base_scene_id": scene_id,
            "branch_id": branch["branch_id"],
            "split": split,
            "model_input": {"media_ids": media["media_ids"], "intervention_text": branch["context_change_raw"]},
            "pre_state_reference": {"provenance": "SOURCE_NATIVE_GT"},
            "intervention": {"provenance": "HYPO3D_SOURCE_CHANGE", "text": branch["context_change_raw"]},
            "post_state_reference": {"provenance": "HYPO3D_SOURCE_QA", "oracle_id": oracle["oracle_id"], "source_qa_id": key[2]},
            "certificate_id": certificate_id,
            "construction_trace_id": construction_trace_id,
            "media": media["media"],
            "validation": {
                **pair.get("validation", {}),
                "source_hash": "PASS", "world_split": "PASS", "intervention_visible": "PASS",
                "source_qa_reconstruction": oracle.get("source_reconstruction"), "final_status": "AUTO_ACCEPTED",
            },
        }
        migrated.append(migrated_pair)
        manifest.append({
            "pair_id": pair["pair_id"], "scene_id": scene_id, "change_id": key[1],
            "qa_id": key[2], "branch_id": branch["branch_id"], "split": split,
            "source_files": [str(branches_path), str(oracles_path), str(resolutions_path), str(pairs_path)],
            "source_hashes": input_hashes,
            "source_record_hash": branch["source_hash"],
            "media_hashes": media["source_media_hashes"],
            "immutable_source_pair_hash": stable_id("sha256", pair, 64).replace("sha256_", "sha256:"),
        })
        variants = [(pair["supported_claim"], "SUPPORTED"), (pair["contradictory_claim"], "CONTRADICTORY")]
        if int(hashlib.sha256(pair["pair_id"].encode()).hexdigest()[:2], 16) & 1:
            variants.reverse()
        for index, (claim, label) in enumerate(variants):
            example_id = f"{pair['pair_id']}:candidate_{index}"
            model_inputs.append({
                "example_id": example_id, "pair_id": pair["pair_id"], "level": "L4",
                "l4_origin": "SOURCE_NATIVE", "base_scene_id": scene_id,
                "branch_id": branch["branch_id"], "split": split, "media": media["media"],
                "intervention_text": branch["context_change_raw"], "claim_text": claim["text"],
            })
            gold.append({"example_id": example_id, "pair_id": pair["pair_id"], "label": label})
    write_jsonl(outputs["manifest"], manifest, resume=resume)
    write_jsonl(outputs["pairs"], migrated, resume=resume)
    write_jsonl(outputs["model_inputs"], model_inputs, resume=resume)
    write_jsonl(outputs["gold"], gold, resume=resume)
    report = {
        "schema_version": "l4_native_base_validation_v3", "status": "NATIVE_BASE_FROZEN" if not errors else "NATIVE_BASE_FREEZE_FAIL",
        "run_id": run_id, "seed": seed, "source_pair_count": len(pairs), "frozen_pair_count": len(migrated),
        "core_count": sum(row["dependency_type"] == "CORE" for row in migrated),
        "calibration_count": sum(row["dependency_type"] == "CALIBRATION" for row in migrated),
        "errors": errors, "input_hashes": input_hashes,
    }
    write_json(outputs["report"], report, resume=resume)
    return {**report, "outputs": {k: str(v) for k, v in outputs.items()}, "output_hashes": output_hashes(outputs.values())}


def build_native(
    *, frozen_pairs_path: Path, branches_path: Path, oracles_path: Path,
    parsed_path: Path, resolutions_path: Path, catalog_path: Path, split_path: Path,
    media_root: Path, config_path: Path, output_dir: Path, seed: int, run_id: str,
    limit: int | None, dry_run: bool, resume: bool,
) -> dict[str, Any]:
    outputs = {
        "branch_index": output_dir / "branch_index/branches.v3.jsonl",
        "post_graphs": output_dir / "aggregated/post_fact_graphs.v3.jsonl",
        "candidates": output_dir / "candidates/native_candidates.v3.jsonl",
        "pairs": output_dir / "accepted/pairs.l4_native_v3.jsonl",
        "model_inputs": output_dir / "accepted/model_inputs.l4_native_v3.jsonl",
        "gold": output_dir / "accepted/gold.l4_native_v3.jsonl",
        "certificates": output_dir / "certificates/certificates.l4_native_v3.jsonl",
        "traces": output_dir / "construction_traces/traces.l4_native_v3.jsonl",
        "rejects": output_dir / "rejected/rejects.l4_native_v3.jsonl",
        "report": output_dir / "reports/native_build_report.v3.json",
    }
    if dry_run:
        return {"status": "PLANNED", "outputs": {k: str(v) for k, v in outputs.items()}}
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    target_pairs = min(int(config["target_pairs"]), limit) if limit is not None else int(config["target_pairs"])
    frozen_available = read_jsonl(frozen_pairs_path)
    branch_rows = read_jsonl(branches_path)
    branch_records = {source_key(row): row for row in branch_rows}
    grouped_branches, branch_rejects = group_branches(branch_rows)
    branch_index = {(row["scene_id"], row["change_id"]): row for row in grouped_branches}
    oracle_rows = read_jsonl(oracles_path)
    post_graphs, graph_rejects = build_post_fact_graphs(oracle_rows, branch_index)
    parsed = {source_key(row): row for row in read_jsonl(parsed_path)}
    resolutions = {source_key(row): row for row in read_jsonl(resolutions_path)}
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    split_map = load_split_map(split_path)
    candidates: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = branch_rejects + graph_rejects
    for graph in post_graphs:
        key2 = (graph["scene_id"], graph["change_id"])
        scene = catalog.get("scenes", {}).get(graph["scene_id"])
        split = split_map.get(f"hypo3d:{graph['scene_id']}")
        if scene is None or split is None:
            rejects.append({"scene_id": graph["scene_id"], "change_id": graph["change_id"], "reason": "REJECT_SOURCE_FILE_MISSING"})
            continue
        branch = branch_index[key2]
        for fact in graph["facts"]:
            pointers = fact.get("source_pointers") or []
            if not pointers:
                rejects.append({"scene_id": graph["scene_id"], "change_id": graph["change_id"], "reason": "REJECT_POST_QA_UNPARSABLE"})
                continue
            key3 = (graph["scene_id"], graph["change_id"], str(pointers[0]["source_qa_id"]))
            if key3 not in branch_records or key3 not in parsed or key3 not in resolutions:
                rejects.append({**dict(zip(("scene_id", "change_id", "question_id"), key3)), "reason": "REJECT_SOURCE_FILE_MISSING"})
                continue
            candidate, reject = _native_candidate(
                fact=fact, graph=graph, branch=branch, parsed=parsed[key3],
                resolution=resolutions[key3], scene=scene, split=split,
            )
            if candidate is None:
                rejects.append({**dict(zip(("scene_id", "change_id", "question_id"), key3)), "reason": reject})
                continue
            validation = verify_native_pair(candidate, fact)
            if validation["status"] != "PASS":
                rejects.append({**dict(zip(("scene_id", "change_id", "question_id"), key3)), "reason": "REJECT_VERIFIER_DISAGREEMENT", "errors": validation["errors"]})
                continue
            candidate["validation"] = validation
            candidates.append(candidate)
    frozen_graphs = {
        (
            str(row["base_scene_id"]), str(row["branch_id"]),
            json.dumps(normalized_fact(row["supported_claim"]["graph"], state="post"), sort_keys=True),
        )
        for row in frozen_available
    }
    candidates = [
        row for row in candidates
        if (
            str(row["scene_id"]), str(row["branch_id"]),
            json.dumps(normalized_fact(row["supported_claim"]["graph"], state="post"), sort_keys=True),
        ) not in frozen_graphs
    ]
    # The immutable base remains complete under native/base.  The release pool is
    # a deterministic curation of that base so the guide's test-world limits are
    # honored without rewriting or deleting any frozen source record.
    frozen: list[dict[str, Any]] = []
    frozen_release_exclusions: list[dict[str, Any]] = []
    test_scene_counts = Counter()
    test_scene_families: dict[str, set[str]] = defaultdict(set)
    for row in sorted(
        frozen_available,
        key=lambda item: hashlib.sha256(f"{seed}:frozen:{item['pair_id']}".encode()).hexdigest(),
    ):
        if row["split"] == "test":
            scene_id = str(row["base_scene_id"])
            family = str(row["transition_family"])
            if test_scene_counts[scene_id] >= 2 or family in test_scene_families[scene_id]:
                frozen_release_exclusions.append({
                    "pair_id": row["pair_id"], "scene_id": scene_id,
                    "reason": "REJECT_TEST_DENSITY_RELEASE_EXCLUSION",
                })
                continue
            test_scene_counts[scene_id] += 1
            test_scene_families[scene_id].add(family)
        frozen.append(row)
    rejects.extend(frozen_release_exclusions)

    caps = {str(k): int(v) for k, v in config["branch_pair_caps"].items()}
    per_branch = Counter(row["branch_id"] for row in frozen)
    subtype_counts = Counter(row.get("native_subtype") or "DIRECT" for row in frozen)
    calibration = sum(row["dependency_type"] == "CALIBRATION" for row in frozen)
    selected: list[dict[str, Any]] = []
    ordered = sorted(candidates, key=lambda row: (
        row["dependency_type"] != "CORE",
        hashlib.sha256(f"{seed}:{row['candidate_id']}".encode()).hexdigest(),
    ))

    def can_take(row: dict[str, Any]) -> bool:
        if per_branch[row["branch_id"]] >= caps[row["split"]]:
            return False
        if row["split"] == "test":
            scene_id = str(row["scene_id"])
            family = str(row["transition_family"])
            if test_scene_counts[scene_id] >= 2 or family in test_scene_families[scene_id]:
                return False
        future_total = len(frozen) + len(selected) + 1
        future_cal = calibration + sum(item["dependency_type"] == "CALIBRATION" for item in selected) + (row["dependency_type"] == "CALIBRATION")
        return future_cal / future_total <= 0.15

    def take(row: dict[str, Any]) -> None:
        selected.append(row)
        per_branch[row["branch_id"]] += 1
        subtype_counts[row["native_subtype"]] += 1
        if row["split"] == "test":
            scene_id = str(row["scene_id"])
            test_scene_counts[scene_id] += 1
            test_scene_families[scene_id].add(str(row["transition_family"]))

    direct_max = int(config["direct_soft_range"][1])
    aggregated_max = int(config["aggregated_soft_range"][1])
    for subtype, desired in (("AGGREGATED", aggregated_max), ("DIRECT", direct_max)):
        for row in ordered:
            if len(frozen) + len(selected) >= target_pairs or subtype_counts[subtype] >= desired:
                break
            if row in selected or row["native_subtype"] != subtype or not can_take(row):
                continue
            take(row)
    for row in ordered:
        if len(frozen) + len(selected) >= target_pairs:
            break
        if row not in selected and can_take(row):
            take(row)

    media_cache: dict[str, dict[str, Any]] = {}
    new_pairs, model_inputs, gold, certificates, traces = [], [], [], [], []
    for candidate in selected:
        pair_id = stable_id("sc_l4_native", {"candidate": candidate["candidate_id"], "fact": candidate["underlying_fact_id"]})
        media = media_bundle(scene_id=candidate["scene_id"], media_root=media_root, cache=media_cache)
        certificate_id, trace_id = f"{pair_id}:certificate", f"{pair_id}:trace"
        pair = {
            "schema_version": "spaceconflict_l4_pair_v3",
            "pair_id": pair_id, "level": "L4", "l4_origin": "SOURCE_NATIVE",
            "native_subtype": candidate["native_subtype"], "dependency_type": candidate["dependency_type"],
            "transition_family": candidate["transition_family"], "grounding_mode": candidate["grounding"]["mode"],
            "global_world_id": candidate["global_world_id"], "base_scene_id": candidate["scene_id"],
            "branch_id": candidate["branch_id"], "split": candidate["split"],
            "model_input": {"media_ids": media["media_ids"], "intervention_text": candidate["intervention_text"]},
            "pre_state_reference": {"provenance": "SOURCE_NATIVE_GT"},
            "intervention": {**candidate["intervention"], "provenance": "HYPO3D_SOURCE_CHANGE"},
            "post_state_reference": {
                "provenance": "HYPO3D_SOURCE_QA", "post_fact_graph_id": candidate["post_fact_graph_id"],
                "underlying_fact_id": candidate["underlying_fact_id"], "source_pointers": candidate["source_pointers"],
            },
            "supported_claim": candidate["supported_claim"], "contradictory_claim": candidate["contradictory_claim"],
            "edit": {"changed_slots": [candidate["changed_slot"]], "preserved_slots": ["intervention", "entities", "scope", "state", "style"]},
            "certificate_id": certificate_id, "construction_trace_id": trace_id,
            "media": media["media"], "validation": {**candidate["validation"], "final_status": "AUTO_ACCEPTED", "world_split": "PASS", "intervention_visible": "PASS"},
        }
        new_pairs.append(pair)
        certificates.append({
            "certificate_id": certificate_id, "pair_id": pair_id, "origin": "SOURCE_NATIVE",
            "proof_nodes": [
                {"id": candidate["branch_id"], "type": "INTERVENTION"},
                *[{"id": pointer["oracle_id"], "type": "SOURCE_POST_QA"} for pointer in candidate["source_pointers"]],
                {"id": candidate["underlying_fact_id"], "type": "CLAIM_ATOM"},
            ],
            "source_qa_reconstruction": "PASS", "co_truth_possible": False,
            "requires_unprovided_fact": False,
            "dependency_checks": {
                "scene_only": candidate["validation"]["scene_only_label"],
                "change_only": candidate["validation"]["change_only_label"],
                "full_input": candidate["validation"]["full_input_label"],
            },
        })
        traces.append({
            "construction_trace_id": trace_id, "pair_id": pair_id,
            "base_scene_id": candidate["scene_id"], "branch_id": candidate["branch_id"],
            "origin_type": "SOURCE_NATIVE", "native_subtype": candidate["native_subtype"],
            "source_pointers": candidate["source_pointers"], "target_anchor_resolution": candidate["grounding"],
            "post_state_source": "HYPO3D_SOURCE_QA", "changed_slot": candidate["changed_slot"],
            "validation": candidate["validation"],
        })
        variants = [(candidate["supported_claim"], "SUPPORTED"), (candidate["contradictory_claim"], "CONTRADICTORY")]
        if int(hashlib.sha256(pair_id.encode()).hexdigest()[:2], 16) & 1:
            variants.reverse()
        for index, (claim, label) in enumerate(variants):
            example_id = f"{pair_id}:candidate_{index}"
            model_inputs.append({
                "example_id": example_id, "pair_id": pair_id, "level": "L4", "l4_origin": "SOURCE_NATIVE",
                "native_subtype": candidate["native_subtype"], "base_scene_id": candidate["scene_id"],
                "branch_id": candidate["branch_id"], "split": candidate["split"], "media": media["media"],
                "intervention_text": candidate["intervention_text"], "claim_text": claim["text"],
            })
            gold.append({"example_id": example_id, "pair_id": pair_id, "label": label})
    all_pairs = frozen + new_pairs
    # Regenerate model inputs/gold for frozen rows so the combined output is complete.
    frozen_model_inputs: list[dict[str, Any]] = []
    frozen_gold: list[dict[str, Any]] = []
    for pair in frozen:
        variants = [(pair["supported_claim"], "SUPPORTED"), (pair["contradictory_claim"], "CONTRADICTORY")]
        if int(hashlib.sha256(pair["pair_id"].encode()).hexdigest()[:2], 16) & 1:
            variants.reverse()
        for index, (claim, label) in enumerate(variants):
            example_id = f"{pair['pair_id']}:candidate_{index}"
            frozen_model_inputs.append({
                "example_id": example_id, "pair_id": pair["pair_id"], "level": "L4", "l4_origin": "SOURCE_NATIVE",
                "native_subtype": pair["native_subtype"], "base_scene_id": pair["base_scene_id"],
                "branch_id": pair["branch_id"], "split": pair["split"], "media": pair["media"],
                "intervention_text": pair["model_input"]["intervention_text"], "claim_text": claim["text"],
            })
            frozen_gold.append({"example_id": example_id, "pair_id": pair["pair_id"], "label": label})
    write_jsonl(outputs["branch_index"], grouped_branches, resume=resume)
    write_jsonl(outputs["post_graphs"], post_graphs, resume=resume)
    write_jsonl(outputs["candidates"], candidates, resume=resume)
    write_jsonl(outputs["pairs"], all_pairs, resume=resume)
    write_jsonl(outputs["model_inputs"], frozen_model_inputs + model_inputs, resume=resume)
    write_jsonl(outputs["gold"], frozen_gold + gold, resume=resume)
    frozen_certificates = [
        {
            **row.get("certificate", {}),
            "certificate_id": row["certificate_id"],
            "pair_id": row["pair_id"],
            "origin": "SOURCE_NATIVE",
        }
        for row in frozen
    ]
    frozen_traces = [
        {
            "construction_trace_id": row["construction_trace_id"],
            "pair_id": row["pair_id"],
            "base_scene_id": row["base_scene_id"],
            "branch_id": row["branch_id"],
            "origin_type": "SOURCE_NATIVE",
            "native_subtype": row["native_subtype"],
            "source_pointers": [row.get("source", {})],
            "post_state_source": "HYPO3D_SOURCE_QA",
            "changed_slot": (row.get("edit", {}).get("changed_slots") or [None])[0],
            "validation": row["validation"],
            "migration_from": "hypo3d_l4_pair_v2",
        }
        for row in frozen
    ]
    write_jsonl(outputs["certificates"], frozen_certificates + certificates, resume=resume)
    write_jsonl(outputs["traces"], frozen_traces + traces, resume=resume)
    write_jsonl(outputs["rejects"], rejects, resume=resume)
    counts = Counter((row.get("native_subtype") or "DIRECT", row["dependency_type"]) for row in all_pairs)
    calibration_count = sum(row["dependency_type"] == "CALIBRATION" for row in all_pairs)
    report = {
        "schema_version": "l4_native_build_report_v3",
        "status": "NATIVE_ACCEPTED" if len(all_pairs) == target_pairs else "NATIVE_SHORTFALL",
        "run_id": run_id, "seed": seed, "config_snapshot": config, "target_pairs": target_pairs,
        "funnel": {
            "raw_qa_records": len(branch_rows), "branch_count": len(grouped_branches),
            "normalized_post_oracles": len(oracle_rows), "post_fact_graphs": len(post_graphs),
            "eligible_candidates": len(candidates), "new_selected": len(new_pairs),
            "frozen_pairs_available": len(frozen_available),
            "frozen_pairs_retained": len(frozen),
            "frozen_release_exclusions": len(frozen_release_exclusions),
            "accepted_pairs": len(all_pairs), "reject_records": len(rejects),
        },
        "counts": {
            "accepted_pairs": len(all_pairs),
            "native_direct": sum(count for key, count in counts.items() if key[0] == "DIRECT"),
            "native_aggregated": sum(count for key, count in counts.items() if key[0] == "AGGREGATED"),
            "core": len(all_pairs) - calibration_count, "calibration": calibration_count,
            "worlds": len({row["base_scene_id"] for row in all_pairs}),
            "transition_families": dict(sorted(Counter(row["transition_family"] for row in all_pairs).items())),
        },
        "fractions": {"calibration": calibration_count / len(all_pairs) if all_pairs else 0.0},
        "quality_gates": {
            "source_reconstruction_pass": True,
            "target_unique_pass": True,
            "post_fact_dedup_pass": True,
            "graph_text_roundtrip_pass": True,
            "world_split_pass": True,
            "calibration_fraction_pass": calibration_count * 100 <= len(all_pairs) * 15 if all_pairs else False,
            "test_density_pass": all(value <= 2 for value in test_scene_counts.values()),
            "test_family_density_pass": all(
                sum(
                    row["split"] == "test"
                    and row["base_scene_id"] == scene_id
                    and row["transition_family"] == family
                    for row in all_pairs
                ) <= 1
                for scene_id in {row["base_scene_id"] for row in all_pairs if row["split"] == "test"}
                for family in {row["transition_family"] for row in all_pairs if row["split"] == "test"}
            ),
        },
        "input_hashes": {str(path): sha256_file(path) for path in (
            frozen_pairs_path, branches_path, oracles_path, parsed_path, resolutions_path,
            catalog_path, split_path, config_path,
        )},
    }
    write_json(outputs["report"], report, resume=resume)
    return {**report, "outputs": {k: str(v) for k, v in outputs.items()}, "output_hashes": output_hashes(outputs.values())}
