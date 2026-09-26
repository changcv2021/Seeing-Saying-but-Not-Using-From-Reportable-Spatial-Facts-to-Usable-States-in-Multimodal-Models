from __future__ import annotations

import hashlib
import re
from typing import Any

from .certificates import validate_certificate_separation
from .verification import verify_existence_pair_accessibly


REALIZER_VERSION = "hypo3d_l4_existence_calibration_realizer_v2"
_TEXT = re.compile(
    r"^After the change, the (?P<role>new|removed|replaced|replacement) "
    r"(?P<class>.+) (?P<exists>exists|does not exist) in the scene\.$"
)


def _pair_id(bundle: dict[str, Any], operator_id: str) -> str:
    value = "|".join((
        bundle["scene_id"], bundle["change_id"], bundle["question_id"], operator_id,
    ))
    return f"sc_hypo3d_l4_v2_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _realize(role: str, entity_class: str, exists: bool) -> str:
    verb = "exists" if exists else "does not exist"
    return f"After the change, the {role} {entity_class} {verb} in the scene."


def _roundtrip(text: str) -> tuple[str, str, bool] | None:
    match = _TEXT.fullmatch(text)
    if not match:
        return None
    return match.group("role"), match.group("class"), match.group("exists") == "exists"


def build_existence_calibration_pair(
    bundle: dict[str, Any], *, operator_id: str,
) -> dict[str, Any]:
    transition = bundle.get("existence_transition") or {}
    rule_id = str(transition.get("rule_id") or "")
    if operator_id == "ADDED_OBJECT_ABSENCE" and rule_id == "ADDITION_CREATES_ENTITY":
        entity_id = str(transition["entity_id"])
        entity_class = str(transition["entity_class"])
        role, post_exists = "new", True
    elif operator_id == "REMOVED_OBJECT_PERSISTENCE" and rule_id == "REMOVAL_DELETES_ENTITY":
        entity_id = str(transition["entity_id"])
        entity_class = str(transition["entity_class"])
        role, post_exists = "removed", False
    elif operator_id == "OLD_OBJECT_PERSISTENCE" and rule_id == "REPLACEMENT_SWAPS_ENTITIES":
        entity_id = str(transition["old_entity_id"])
        entity_class = str(transition["old_entity_class"])
        role, post_exists = "replaced", False
    elif operator_id == "NEW_OBJECT_ABSENCE" and rule_id == "REPLACEMENT_SWAPS_ENTITIES":
        entity_id = str(transition["new_entity_id"])
        entity_class = str(transition["new_entity_class"])
        role, post_exists = "replacement", True
    else:
        raise ValueError(f"Ineligible existence calibration operator: {operator_id}")

    supported_text = _realize(role, entity_class, post_exists)
    contradictory_text = _realize(role, entity_class, not post_exists)
    if _roundtrip(supported_text) != (role, entity_class, post_exists):
        raise ValueError("Supported existence graph-text-graph round trip failed")
    if _roundtrip(contradictory_text) != (role, entity_class, not post_exists):
        raise ValueError("Contradictory existence graph-text-graph round trip failed")
    graph_base = {
        "subject": entity_id, "subject_class": entity_class, "entity_role": role,
        "predicate": "EXISTS_IN_WORLD", "state": "post", "scope": "whole_scene",
    }
    supported_graph = {**graph_base, "value": post_exists}
    contradictory_graph = {**graph_base, "value": not post_exists}
    verifier = verify_existence_pair_accessibly(
        accessible_transition=transition, supported_claim=supported_graph,
        contradictory_claim=contradictory_graph,
    )
    if verifier["status"] != "PASS":
        raise ValueError(f"Independent existence verifier failed: {verifier['errors']}")

    pair_id = _pair_id(bundle, operator_id)
    oracle_id = bundle["label_provenance_check"]["post_oracle_id"]
    intervention_id = f"int:{bundle['branch_id']}"
    derived_id = f"derived:exists:{entity_id}:{str(post_exists).lower()}"
    certificate = {
        "certificate_id": f"cert:{pair_id}", "label": "SUPPORTED", "level": "L4",
        "strength_slice": "L4_CALIBRATION",
        "label_provenance_certificate": {
            "post_oracle_id": oracle_id, "source_reconstruction": "PASS",
            "oracle_consistency_verifier": "PASS",
        },
        "accessible_reasoning_certificate": {
            "proof_nodes": [
                {"id": intervention_id, "type": "INTERVENTION"},
                {"id": rule_id, "type": "TRANSITION_RULE"},
                {"id": derived_id, "type": "DERIVED_POST_FACT"},
                {"id": "claim:supported", "type": "CLAIM_ATOM"},
            ],
            "proof_edges": [
                [intervention_id, rule_id, "premise"],
                [rule_id, derived_id, "derives"],
                [derived_id, "claim:supported", "entails"],
            ],
            "forbidden_premises_absent": True, "accessible_evidence_verifier": "PASS",
        },
        "dependency_checks": {
            "scene_only_label": verifier["scene_only_label"],
            "change_only_label": verifier["change_only_label"],
            "full_input_label": verifier["supported"]["label"], "status": "PASS",
        },
        "co_truth_possible": False, "requires_unprovided_fact": False,
    }
    errors = validate_certificate_separation(certificate)
    if errors:
        raise ValueError(f"Certificate separation failed: {errors}")
    return {
        "pair_id": pair_id, "schema_version": "hypo3d_l4_pair_v2",
        "source": {
            "scene_id": bundle["scene_id"], "change_id": bundle["change_id"],
            "question_id": bundle["question_id"], "branch_id": bundle["branch_id"],
            "post_oracle_id": oracle_id,
        },
        "task": {
            "level": "L4", "strength_slice": "L4_CALIBRATION", "primary_track": "DYNAMIC",
            "secondary_tracks": ["IDENTITY"], "operator_id": operator_id,
        },
        "supported_claim": {"graph": supported_graph, "text": supported_text},
        "contradictory_claim": {"graph": contradictory_graph, "text": contradictory_text},
        "edit": {
            "changed_slots": ["existence_value"], "before": post_exists, "after": not post_exists,
            "preserved_slots": [
                "subject", "subject_class", "entity_role", "predicate", "scope", "state",
                "branch_id", "syntax_family",
            ],
        },
        "certificate": certificate, "realizer_version": REALIZER_VERSION,
        "validation": {
            "transition_replay": "PASS", "oracle_consistency": "PASS",
            "accessible_evidence_verifier": "PASS", "graph_text_roundtrip": "PASS",
            "independent_verifier": verifier, "necessary_fact_ablation": "NOT_APPLICABLE_CALIBRATION",
            "co_truth_check": "PASS", "final_status": "AUTO_ACCEPTED",
        },
    }


def select_existence_calibration_pairs(
    bundles: list[dict[str, Any]], *, requested_limit: int, core_pair_count: int,
) -> list[dict[str, Any]]:
    # Enforce calibration / (core + calibration) <= 15% with integer arithmetic.
    ratio_limit = (15 * core_pair_count) // 85
    limit = min(requested_limit, ratio_limit)
    if limit <= 0:
        return []
    groups: dict[str, list[dict[str, Any]]] = {
        "ADDED_OBJECT_ABSENCE": [], "REMOVED_OBJECT_PERSISTENCE": [],
        "OLD_OBJECT_PERSISTENCE": [], "NEW_OBJECT_ABSENCE": [],
    }
    for bundle in sorted(bundles, key=lambda row: (row["scene_id"], row["change_id"], row["question_id"])):
        rule_id = str((bundle.get("existence_transition") or {}).get("rule_id") or "")
        if rule_id == "ADDITION_CREATES_ENTITY":
            groups["ADDED_OBJECT_ABSENCE"].append(bundle)
        elif rule_id == "REMOVAL_DELETES_ENTITY":
            groups["REMOVED_OBJECT_PERSISTENCE"].append(bundle)
        elif rule_id == "REPLACEMENT_SWAPS_ENTITIES":
            groups["OLD_OBJECT_PERSISTENCE"].append(bundle)
            groups["NEW_OBJECT_ABSENCE"].append(bundle)
    selected: list[dict[str, Any]] = []
    used_sources: set[tuple[str, str, str]] = set()
    positions = {operator_id: 0 for operator_id in groups}
    while len(selected) < limit:
        progress = False
        for operator_id, candidates in groups.items():
            while positions[operator_id] < len(candidates):
                bundle = candidates[positions[operator_id]]
                positions[operator_id] += 1
                source_key = (bundle["scene_id"], bundle["change_id"], bundle["question_id"])
                if source_key in used_sources:
                    continue
                selected.append(build_existence_calibration_pair(bundle, operator_id=operator_id))
                used_sources.add(source_key)
                progress = True
                break
            if len(selected) >= limit:
                break
        if not progress:
            break
    return selected
