from __future__ import annotations

from typing import Any

from .common import RELATION_COMPLEMENT, fact_slot, normalized_fact


def _one(
    pre_facts: list[dict[str, Any]], predicate: str, subject: str, object_: str | None = None,
) -> dict[str, Any] | None:
    matches = [
        fact for fact in pre_facts
        if str(fact.get("predicate")) == predicate
        and str(fact.get("subject")) == subject
        and str(fact.get("object") or "") == str(object_ or "")
    ]
    return matches[0] if len(matches) == 1 else None


def _post(predicate: str, subject: str, *, object_: str | None = None, value: Any = None, scope: str = "question_local") -> dict[str, Any]:
    return normalized_fact({
        "predicate": predicate,
        "subject": subject,
        "object": object_,
        "value": value,
        "scope": scope,
        "state": "post",
    })


def check_transition_b(
    pre_facts: list[dict[str, Any]], action: dict[str, Any],
) -> dict[str, Any]:
    """Independent family-specific checker; ignores Engine A's add/delete lists."""
    family = str(action.get("family") or "")
    params = action.get("parameters") or {}
    errors: list[str] = []
    post: list[dict[str, Any]] = []
    if family == "REMOVE_AND_RECOUNT":
        target, category = str(params.get("target_id") or ""), str(params.get("category") or "")
        count = _one(pre_facts, "COUNT", category)
        exists = _one(pre_facts, "EXISTS_IN_WORLD", target)
        if count is None or exists is None or exists.get("value") is not True or int(count.get("value", -1)) < 1:
            errors.append("REJECT_TRANSITION_PRECONDITION_FAIL")
        else:
            post = [
                _post("COUNT", category, value=int(count["value"]) - 1, scope=str(count.get("scope") or "whole_scene")),
                _post("EXISTS_IN_WORLD", target, value=False),
            ]
    elif family == "ADD_AND_RECOUNT":
        category, new_id = str(params.get("category") or ""), str(params.get("new_entity_id") or "")
        count = _one(pre_facts, "COUNT", category)
        quantity = params.get("quantity")
        if count is None or not isinstance(quantity, int) or quantity != 1 or not new_id:
            errors.append("REJECT_TRANSITION_PRECONDITION_FAIL")
        else:
            post = [
                _post("COUNT", category, value=int(count["value"]) + 1, scope=str(count.get("scope") or "whole_scene")),
                _post("EXISTS_IN_WORLD", new_id, value=True),
            ]
    elif family == "REPLACE_AND_RECOUNT":
        old_id = str(params.get("target_id") or "")
        new_id = str(params.get("new_entity_id") or "")
        old_category = str(params.get("old_category") or "")
        new_category = str(params.get("new_category") or "")
        old_count = _one(pre_facts, "COUNT", old_category)
        new_count = _one(pre_facts, "COUNT", new_category)
        exists = _one(pre_facts, "EXISTS_IN_WORLD", old_id)
        if (
            not old_id or not new_id or old_category == new_category
            or old_count is None or new_count is None or exists is None
            or exists.get("value") is not True or int(old_count.get("value", -1)) < 1
        ):
            errors.append("REJECT_TRANSITION_PRECONDITION_FAIL")
        else:
            post = [
                _post("COUNT", old_category, value=int(old_count["value"]) - 1, scope=str(old_count.get("scope") or "whole_scene")),
                _post("COUNT", new_category, value=int(new_count["value"]) + 1, scope=str(new_count.get("scope") or "whole_scene")),
                _post("EXISTS_IN_WORLD", old_id, value=False),
                _post("EXISTS_IN_WORLD", new_id, value=True),
                _post("SAME_INSTANCE", new_id, object_=old_id, value=False),
            ]
    elif family == "REPLACEMENT_IDENTITY":
        old_id = str(params.get("target_id") or "")
        new_id = str(params.get("new_entity_id") or "")
        exists = _one(pre_facts, "EXISTS_IN_WORLD", old_id)
        if not old_id or not new_id or exists is None or exists.get("value") is not True:
            errors.append("REJECT_TRANSITION_PRECONDITION_FAIL")
        else:
            post = [
                _post("EXISTS_IN_WORLD", old_id, value=False),
                _post("EXISTS_IN_WORLD", new_id, value=True),
                _post("SAME_INSTANCE", new_id, object_=old_id, value=False),
            ]
    elif family in {"MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"}:
        target = str(params.get("target_id") or params.get("target_a_id") or "")
        anchor = str(params.get("anchor_id") or params.get("target_b_id") or "")
        pre_predicate = str(params.get("pre_predicate") or "")
        relation = _one(pre_facts, pre_predicate, target, anchor)
        if relation is None or pre_predicate not in RELATION_COMPLEMENT:
            errors.append("REJECT_TRANSITION_PRECONDITION_FAIL")
        else:
            post = [_post(RELATION_COMPLEMENT[pre_predicate], target, object_=anchor)]
    else:
        errors.append("REJECT_UNAUTHORIZED_RULE")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "post_facts": sorted(post, key=lambda fact: fact_slot(fact)),
        "checker_version": "controlled_transition_checker_b_v1",
    }
