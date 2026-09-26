from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from ..hashing import sha256_file
from .common import (
    RELATION_COMPLEMENT,
    identity_claim_text,
    output_hashes,
    read_jsonl,
    stable_id,
    write_json,
    write_jsonl,
)


def _witnesses(pair: dict[str, Any], reason: str, claim: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str], str]:
    graph = claim["graph"]
    action = pair["intervention"]
    if reason == "MISSING_PRE_COUNT":
        value = int(graph["value"])
        family = action["family"]
        delta = 1 if family == "ADD_AND_RECOUNT" else -1
        if family == "REPLACE_AND_RECOUNT":
            delta = int(action["parameters"]["count_deltas"][graph["subject"]])
        positive_pre = value - delta
        negative_pre = positive_pre + 1
        return (
            {"pre_count": positive_pre, "delta": delta, "post_count": value, "claim_holds": True},
            {"pre_count": negative_pre, "delta": delta, "post_count": value + 1, "claim_holds": False},
            ["PRE_STATE_COUNT", "SOURCE_MEDIA_SHOWING_COUNT"],
            "PRE_STATE_COUNT",
        )
    if reason == "REFERENCE_FRAME_AMBIGUITY":
        predicate = str(graph["predicate"])
        return (
            {"reference_frame": "source_world_axes", "post_predicate": predicate, "claim_holds": True},
            {"reference_frame": "axis_reversed_admissible_frame", "post_predicate": RELATION_COMPLEMENT[predicate], "claim_holds": False},
            ["REFERENCE_FRAME"],
            "SOURCE_DECLARED_REFERENCE_FRAME",
        )
    if reason == "UNRESOLVED_POST_IDENTITY":
        return (
            {"post_identity": "DISTINCT_INSTANCE", "same_instance": False, "claim_holds": True},
            {"post_identity": "IDENTITY_PRESERVED", "same_instance": True, "claim_holds": False},
            ["REPLACEMENT_IDENTITY_RULE"],
            "DETERMINISTIC_IDENTITY_TRANSITION",
        )
    if reason == "POST_STATE_UNDERSPECIFIED":
        predicate = str(graph["predicate"])
        return (
            {"allowed_destination": predicate, "claim_holds": True},
            {"allowed_destination": RELATION_COMPLEMENT[predicate], "claim_holds": False},
            ["DISCRETE_POST_RELATION"],
            "EXPLICIT_MOVEMENT_DESTINATION",
        )
    raise ValueError(f"Unsupported Unknown reason: {reason}")


def verify_unknown_sample(sample: dict[str, Any]) -> dict[str, Any]:
    reason = str(sample.get("unknown_axis") or "")
    positive = sample.get("positive_witness_completion") or {}
    negative = sample.get("negative_witness_completion") or {}
    errors: list[str] = []
    if reason not in {
        "MISSING_PRE_COUNT", "REFERENCE_FRAME_AMBIGUITY",
        "UNRESOLVED_POST_IDENTITY", "POST_STATE_UNDERSPECIFIED",
    }:
        errors.append("UNKNOWN_REASON_INVALID")
    if positive.get("claim_holds") is not True:
        errors.append("POSITIVE_WITNESS_INVALID")
    if negative.get("claim_holds") is not False:
        errors.append("NEGATIVE_WITNESS_INVALID")
    if positive == negative:
        errors.append("WITNESSES_NOT_DISTINCT")
    if not sample.get("missing_decisive_evidence"):
        errors.append("MISSING_EVIDENCE_NOT_EXPLICIT")
    if not sample.get("base_determinate_sample_id"):
        errors.append("BASE_DETERMINATE_SAMPLE_MISSING")
    if sample.get("pipeline_failure"):
        errors.append("PIPELINE_FAILURE_MISLABELED_UNKNOWN")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "satisfiable_with_claim": not errors,
        "satisfiable_with_negation": not errors,
        "independent_witness_verifier": "PASS" if not errors else "FAIL",
    }


def _eligible(pair: dict[str, Any], reason: str) -> bool:
    if pair.get("dependency_type") != "CORE" or pair.get("validation", {}).get("final_status") != "AUTO_ACCEPTED":
        return False
    family = str(pair.get("intervention", {}).get("family") or "")
    source_group = str(pair.get("source_group") or "")
    if reason == "MISSING_PRE_COUNT":
        return family == "ADD_AND_RECOUNT" and source_group == "REFERIT3D_EXACT_COUNT"
    if reason == "REFERENCE_FRAME_AMBIGUITY":
        return family in {"MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"} and source_group == "EMBODIEDSCAN_9DOF"
    if reason == "UNRESOLVED_POST_IDENTITY":
        return family == "REPLACE_AND_RECOUNT" and source_group == "FUSED_EMBODIEDSCAN_REFERIT3D"
    if reason == "POST_STATE_UNDERSPECIFIED":
        return family in {"MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"} and source_group == "3DSSG_EXPLICIT_RELATION"
    return False


def _unknown_claim(pair: dict[str, Any], reason: str) -> tuple[dict[str, Any], str]:
    if reason == "UNRESOLVED_POST_IDENTITY":
        params = pair["intervention"]["parameters"]
        graph = {
            "predicate": "SAME_INSTANCE", "subject": params["new_entity_id"],
            "object": params["target_id"], "value": False,
            "scope": "question_local", "state": "post",
        }
        text = identity_claim_text(params["old_category"], params["new_category"], False)
        return {"graph": graph, "text": text}, (
            f"Suppose the {params['old_category']} is substituted with a {params['new_category']}, "
            "but the identity semantics of the substitution are not specified."
        )
    claim = pair["supported_claim"]
    if reason == "REFERENCE_FRAME_AMBIGUITY":
        return claim, pair["intervention"]["model_visible_text"] + " No reference frame is specified."
    if reason == "POST_STATE_UNDERSPECIFIED":
        target, anchor = pair["intervention"]["parameters"], pair["intervention"]["parameters"]
        target_label = pair["supported_claim"]["graph"].get("subject_label") or "target object"
        anchor_label = pair["supported_claim"]["graph"].get("object_label") or "anchor object"
        return claim, f"Suppose the {target_label} is moved relative to the {anchor_label}, without specifying its final side."
    return claim, pair["intervention"]["model_visible_text"]


def build_unknown(
    *, controlled_pairs_path: Path, config_path: Path, output_dir: Path,
    seed: int, run_id: str, limit: int | None, dry_run: bool, resume: bool,
) -> dict[str, Any]:
    outputs = {
        "samples": output_dir / "accepted/claims.l4_unknown_v3.jsonl",
        "model_inputs": output_dir / "accepted/model_inputs.l4_unknown_v3.jsonl",
        "gold": output_dir / "accepted/gold.l4_unknown_v3.jsonl",
        "rejects": output_dir / "rejected/rejects.l4_unknown_v3.jsonl",
        "report": output_dir / "reports/unknown_build_report.v3.json",
    }
    if dry_run:
        return {"status": "PLANNED", "outputs": {key: str(value) for key, value in outputs.items()}}
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    pairs = read_jsonl(controlled_pairs_path)
    requested = int(config["target_claims"])
    if limit is not None:
        requested = min(requested, limit)
    configured_targets = {str(key): int(value) for key, value in config["reason_targets"].items()}
    total_configured = sum(configured_targets.values())
    raw = {key: requested * value / total_configured for key, value in configured_targets.items()}
    targets = {key: int(value) for key, value in raw.items()}
    for key in sorted(raw, key=lambda item: (-(raw[item] - targets[item]), item))[:requested - sum(targets.values())]:
        targets[key] += 1
    selected: list[tuple[dict[str, Any], str]] = []
    used_pairs: set[str] = set()
    used_test_worlds: set[str] = set()
    reason_counts = Counter()
    ordered = sorted(pairs, key=lambda pair: hashlib.sha256(f"{seed}:{pair['pair_id']}".encode()).hexdigest())
    for reason in targets:
        for pair in ordered:
            if reason_counts[reason] >= targets[reason]:
                break
            if pair["pair_id"] in used_pairs or not _eligible(pair, reason):
                continue
            if pair["split"] == "test" and pair["base_scene_id"] in used_test_worlds:
                continue
            selected.append((pair, reason))
            used_pairs.add(pair["pair_id"])
            reason_counts[reason] += 1
            if pair["split"] == "test":
                used_test_worlds.add(pair["base_scene_id"])
    samples, model_inputs, gold, rejects = [], [], [], []
    for pair, reason in selected:
        claim, intervention_text = _unknown_claim(pair, reason)
        positive, negative, withheld, resolving = _witnesses(pair, reason, claim)
        sample_id = stable_id("sc_l4_unknown", {"base": pair["pair_id"], "reason": reason})
        evidence_origin = "EVIDENCE_ABLATION" if reason in set(config["evidence_ablation_reasons"]) else "SOURCE_UNDERSPECIFICATION"
        available_media = {} if reason == "MISSING_PRE_COUNT" else pair["media"]
        sample = {
            "schema_version": "spaceconflict_l4_unknown_v3",
            "sample_id": sample_id,
            "label": "UNKNOWN",
            "level": "L4",
            "l4_origin": "L4_UNKNOWN",
            "unknown_origin": evidence_origin,
            "unknown_axis": reason,
            "base_determinate_sample_id": pair["pair_id"],
            "global_world_id": pair["global_world_id"],
            "base_scene_id": pair["base_scene_id"],
            "branch_id": f"{pair['branch_id']}::unknown::{reason.casefold()}",
            "split": pair["split"],
            "source_group": pair["source_group"],
            "model_input": {
                "media": available_media,
                "intervention_text": intervention_text,
                "claim_text": claim["text"],
            },
            "available_evidence_ids": [pair["intervention"]["action_id"]],
            "withheld_evidence_ids": withheld,
            "claim_graph": claim["graph"],
            "positive_witness_completion": positive,
            "negative_witness_completion": negative,
            "missing_decisive_evidence": withheld,
            "resolving_evidence_type": resolving,
            "would_be_level_if_resolved": "L4",
            "pipeline_failure": False,
        }
        validation = verify_unknown_sample(sample)
        sample["validation"] = {**validation, "final_status": "AUTO_ACCEPTED" if validation["status"] == "PASS" else "REJECTED"}
        if validation["status"] != "PASS":
            rejects.append({"sample_id": sample_id, "reason": "REJECT_VERIFIER_DISAGREEMENT", "errors": validation["errors"]})
            continue
        samples.append(sample)
        model_inputs.append({
            "sample_id": sample_id, "level": "L4", "base_scene_id": pair["base_scene_id"],
            "branch_id": sample["branch_id"], "split": pair["split"],
            "media": available_media, "intervention_text": intervention_text, "claim_text": claim["text"],
        })
        gold.append({"sample_id": sample_id, "label": "UNKNOWN"})
    source_counts = Counter(row["source_group"] for row in samples)
    ablation_count = sum(row["unknown_origin"] == "EVIDENCE_ABLATION" for row in samples)
    count = len(samples)
    gates = {
        "target_met": count == requested,
        "positive_negative_witness_pass": all(row["validation"]["status"] == "PASS" for row in samples),
        "evidence_ablation_fraction_pass": ablation_count / count >= float(config["evidence_ablation_min_fraction"]) if count else False,
        "single_reason_fraction_pass": all(value / count <= float(config["single_reason_max_fraction"]) for value in reason_counts.values()) if count else False,
        "single_source_fraction_pass": all(value / count <= float(config["single_source_max_fraction"]) for value in source_counts.values()) if count else False,
        "test_world_density_pass": len([row for row in samples if row["split"] == "test"]) == len({row["base_scene_id"] for row in samples if row["split"] == "test"}),
        "reject_not_unknown_pass": not any(row.get("pipeline_failure") for row in samples),
    }
    status = "UNKNOWN_ACCEPTED" if all(gates.values()) else "UNKNOWN_SHORTFALL_OR_GATE_FAIL"
    write_jsonl(outputs["samples"], samples, resume=resume)
    write_jsonl(outputs["model_inputs"], model_inputs, resume=resume)
    write_jsonl(outputs["gold"], gold, resume=resume)
    write_jsonl(outputs["rejects"], rejects, resume=resume)
    report = {
        "schema_version": "l4_unknown_build_report_v3", "status": status,
        "run_id": run_id, "seed": seed, "config_snapshot": config,
        "target_claims": requested, "accepted_claims": count, "rejected": len(rejects),
        "reason_counts": dict(sorted(reason_counts.items())),
        "source_group_counts": dict(sorted(source_counts.items())),
        "origin_counts": dict(sorted(Counter(row["unknown_origin"] for row in samples).items())),
        "split_counts": dict(sorted(Counter(row["split"] for row in samples).items())),
        "evidence_ablation_fraction": ablation_count / count if count else 0.0,
        "quality_gates": gates,
        "input_hashes": {str(controlled_pairs_path): sha256_file(controlled_pairs_path), str(config_path): sha256_file(config_path)},
    }
    write_json(outputs["report"], report, resume=resume)
    return {**report, "outputs": {key: str(value) for key, value in outputs.items()}, "output_hashes": output_hashes(outputs.values())}
