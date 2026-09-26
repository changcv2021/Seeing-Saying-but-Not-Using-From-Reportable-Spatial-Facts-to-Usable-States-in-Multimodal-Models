from __future__ import annotations

from typing import Any


def verify_count_claim(
    *, pre_facts: list[dict[str, Any]], transition: dict[str, Any] | None,
    claim: dict[str, Any],
) -> dict[str, Any]:
    """Independent count verifier over accessible inputs only.

    The API intentionally has no source-answer, post-oracle, proof, operator, or
    gold-label argument.
    """
    if (
        claim.get("predicate") != "COUNT"
        or claim.get("state") != "post"
        or not isinstance(claim.get("value"), int)
    ):
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["SUPPORTED_COUNT_CLAIM"]}
    if transition is None:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["INTERVENTION"]}
    subject = str(claim.get("subject") or "")
    matching = [
        fact for fact in pre_facts
        if fact.get("predicate") == "COUNT" and str(fact.get("subject") or "") == subject
        and isinstance(fact.get("value"), int)
    ]
    if len(matching) != 1:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["EXACT_PRE_COUNT"]}
    rule_id = transition.get("rule_id")
    delta = transition.get("delta")
    if not isinstance(delta, int) or delta == 0:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["EXACT_CHANGE_DELTA"]}
    pre_count = int(matching[0]["value"])
    if rule_id == "ADDITION_INCREMENTS_CLASS_COUNT":
        derived = pre_count + delta
    elif rule_id == "REMOVAL_DECREMENTS_CLASS_COUNT" and pre_count >= delta:
        derived = pre_count - delta
    elif rule_id == "REPLACEMENT_UPDATES_CLASS_COUNT" and pre_count + delta >= 0:
        derived = pre_count + delta
    else:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["AUTHORIZED_TRANSITION_RULE"]}
    label = "SUPPORTED" if int(claim["value"]) == derived else "CONTRADICTORY"
    return {
        "label": label,
        "normalized_claim": claim,
        "evidence_ids": [str(matching[0]["fact_id"]), str(rule_id)],
        "missing_evidence": [],
        "co_truth_possible": False,
    }


def verify_count_pair_accessibly(
    *, pre_state_subgraph: dict[str, Any], accessible_transition: dict[str, Any],
    supported_claim: dict[str, Any], contradictory_claim: dict[str, Any],
    necessary_pre_fact_ids: list[str],
) -> dict[str, Any]:
    facts = [fact for fact in pre_state_subgraph.get("facts", []) if isinstance(fact, dict)]
    supported = verify_count_claim(pre_facts=facts, transition=accessible_transition, claim=supported_claim)
    contradictory = verify_count_claim(pre_facts=facts, transition=accessible_transition, claim=contradictory_claim)
    scene_only = verify_count_claim(pre_facts=facts, transition=None, claim=supported_claim)
    change_only = verify_count_claim(pre_facts=[], transition=accessible_transition, claim=supported_claim)
    ablations = {}
    for fact_id in necessary_pre_fact_ids:
        reduced = [fact for fact in facts if str(fact.get("fact_id")) != fact_id]
        ablations[fact_id] = verify_count_claim(
            pre_facts=reduced, transition=accessible_transition, claim=supported_claim,
        )["label"]
    errors = []
    if supported["label"] != "SUPPORTED":
        errors.append("SUPPORTED_CLAIM_NOT_VERIFIED")
    if contradictory["label"] != "CONTRADICTORY":
        errors.append("CONTRADICTORY_CLAIM_NOT_REFUTED")
    if scene_only["label"] != "UNKNOWN":
        errors.append("SCENE_ONLY_NOT_UNKNOWN")
    if change_only["label"] != "UNKNOWN":
        errors.append("CHANGE_ONLY_NOT_UNKNOWN")
    if any(label != "UNKNOWN" for label in ablations.values()):
        errors.append("NECESSARY_PRE_FACT_ABLATION_FAILED")
    return {
        "supported": supported,
        "contradictory": contradictory,
        "scene_only_label": scene_only["label"],
        "change_only_label": change_only["label"],
        "necessary_pre_fact_ablations": ablations,
        "intervention_ablation_label": scene_only["label"],
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def verify_existence_claim(
    *, transition: dict[str, Any] | None, claim: dict[str, Any],
) -> dict[str, Any]:
    """Verify deterministic post-existence from an explicit intervention only."""
    if (
        claim.get("predicate") != "EXISTS_IN_WORLD"
        or claim.get("state") != "post"
        or not isinstance(claim.get("value"), bool)
    ):
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["SUPPORTED_EXISTENCE_CLAIM"]}
    if transition is None:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["INTERVENTION"]}
    entity_id = str(claim.get("subject") or "")
    rule_id = str(transition.get("rule_id") or "")
    derived: bool | None = None
    if rule_id == "ADDITION_CREATES_ENTITY" and entity_id == str(transition.get("entity_id") or ""):
        derived = True
    elif rule_id == "REMOVAL_DELETES_ENTITY" and entity_id == str(transition.get("entity_id") or ""):
        derived = False
    elif rule_id == "REPLACEMENT_SWAPS_ENTITIES":
        if entity_id == str(transition.get("old_entity_id") or ""):
            derived = False
        elif entity_id == str(transition.get("new_entity_id") or ""):
            derived = True
    if derived is None:
        return {"label": "UNKNOWN", "normalized_claim": claim, "evidence_ids": [], "missing_evidence": ["AUTHORIZED_EXISTENCE_TRANSITION"]}
    return {
        "label": "SUPPORTED" if claim["value"] is derived else "CONTRADICTORY",
        "normalized_claim": claim, "evidence_ids": [rule_id], "missing_evidence": [],
        "co_truth_possible": False,
    }


def verify_existence_pair_accessibly(
    *, accessible_transition: dict[str, Any], supported_claim: dict[str, Any],
    contradictory_claim: dict[str, Any],
) -> dict[str, Any]:
    supported = verify_existence_claim(transition=accessible_transition, claim=supported_claim)
    contradictory = verify_existence_claim(transition=accessible_transition, claim=contradictory_claim)
    scene_only = verify_existence_claim(transition=None, claim=supported_claim)
    change_only = verify_existence_claim(transition=accessible_transition, claim=supported_claim)
    errors = []
    if supported["label"] != "SUPPORTED":
        errors.append("SUPPORTED_CLAIM_NOT_VERIFIED")
    if contradictory["label"] != "CONTRADICTORY":
        errors.append("CONTRADICTORY_CLAIM_NOT_REFUTED")
    if scene_only["label"] != "UNKNOWN":
        errors.append("SCENE_ONLY_NOT_UNKNOWN")
    if change_only["label"] not in {"SUPPORTED", "CONTRADICTORY"}:
        errors.append("CALIBRATION_CHANGE_ONLY_NOT_DETERMINATE")
    return {
        "supported": supported, "contradictory": contradictory,
        "scene_only_label": scene_only["label"], "change_only_label": change_only["label"],
        "necessary_pre_fact_ablations": {}, "intervention_ablation_label": scene_only["label"],
        "status": "PASS" if not errors else "FAIL", "errors": errors,
    }
