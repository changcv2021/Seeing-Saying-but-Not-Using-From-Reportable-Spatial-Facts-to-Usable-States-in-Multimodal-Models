from __future__ import annotations

from typing import Any

from .common import fact_slot, normalized_fact


def execute_transition_a(
    pre_facts: list[dict[str, Any]], action: dict[str, Any],
) -> dict[str, Any]:
    """Generic fact-delta engine. It does not branch on action family."""
    if action.get("provenance") != "SPACECONFLICT_CONTROLLED_DSL":
        return {"status": "FAIL", "errors": ["DSL_ACTION_INVALID"], "post_facts": []}
    pre_by_slot = {fact_slot(fact): normalized_fact(fact, state="pre") for fact in pre_facts}
    delete_slots = [tuple(slot) for slot in action.get("delete_fact_slots") or []]
    errors: list[str] = []
    if len(pre_by_slot) != len(pre_facts):
        errors.append("DUPLICATE_PRE_FACT_SLOT")
    if any(slot not in pre_by_slot for slot in delete_slots):
        errors.append("DELETE_FACT_NOT_IN_PRESTATE")
    if len(set(delete_slots)) != len(delete_slots):
        errors.append("DUPLICATE_DELETE_FACT_SLOT")
    post_facts = [normalized_fact(fact, state="post") for fact in action.get("add_facts") or []]
    if any(fact.get("predicate") == "COUNT" and (not isinstance(fact.get("value"), int) or fact["value"] < 0) for fact in post_facts):
        errors.append("INVALID_POST_COUNT")
    if len({fact_slot(fact) for fact in post_facts}) != len(post_facts):
        errors.append("DUPLICATE_POST_FACT_SLOT")
    allowed_slots = {tuple(slot) for slot in action.get("allowed_post_fact_slots") or []}
    if any(fact_slot(fact) not in allowed_slots for fact in post_facts):
        errors.append("UNLISTED_POST_FACT_UPDATE")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "post_facts": sorted(post_facts, key=lambda fact: fact_slot(fact)),
        "engine_version": "controlled_transition_engine_a_v1",
    }

