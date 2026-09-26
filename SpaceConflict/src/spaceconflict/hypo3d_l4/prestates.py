from __future__ import annotations

import re
from typing import Any

from .resolve_targets import normalize_ref


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_LEADING_QUANTITY = re.compile(
    r"^(?P<count>an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
    re.IGNORECASE,
)
_NEUTRAL_COUNT_SUBJECT_SUFFIX = re.compile(r"\s+present$")


def explicit_quantity(ref_text: str) -> int | None:
    match = _LEADING_QUANTITY.match(ref_text.strip())
    if not match:
        return None
    value = match.group("count").casefold()
    if value in {"a", "an"}:
        return 1
    if value.isdigit():
        count = int(value)
        return count if count > 0 else None
    return NUMBER_WORDS[value]


def _class_forms(label: str) -> set[str]:
    base = normalize_ref(label)
    forms = {base}
    if base.endswith("y") and len(base) > 1:
        forms.add(base[:-1] + "ies")
    elif base.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(base + "es")
    else:
        forms.add(base + "s")
    return forms


def ref_mentions_class(ref_text: str, entity_class: str) -> bool:
    """Require an intervention noun phrase to explicitly name the counted class."""
    normalized_ref = normalize_ref(ref_text)
    return any(
        re.search(rf"(?:^|\s){re.escape(form)}(?:$|\s)", normalized_ref) is not None
        for form in _class_forms(entity_class)
    )


def unique_catalog_class_mentioned(catalog: dict[str, Any], ref_text: str) -> str | None:
    """Resolve a class noun only when the official catalog vocabulary is unambiguous.

    Longer labels win over their contained head noun (for example, ``coffee table``
    over ``table``); ties remain unresolved instead of being guessed.
    """
    labels = {
        normalize_ref(str(obj.get("class") or ""))
        for scene in catalog.get("scenes", {}).values()
        for obj in scene.get("objects", [])
    }
    matches = [label for label in labels if label and ref_mentions_class(ref_text, label)]
    if not matches:
        return None
    longest = max(len(label.split()) for label in matches)
    winners = sorted(label for label in matches if len(label.split()) == longest)
    return winners[0] if len(winners) == 1 else None


def count_annotated_class(scene: dict[str, Any], query_subject: str) -> tuple[str | None, int | None]:
    query = normalize_ref(query_subject)
    # "chairs present" and "chairs" denote the same counted class; unlike
    # color/shape/type modifiers, this suffix does not narrow the object set.
    query = _NEUTRAL_COUNT_SUBJECT_SUFFIX.sub("", query)
    exact_counts = {
        normalize_ref(str(label)): int(count)
        for label, count in (scene.get("exact_class_counts") or {}).items()
        if normalize_ref(str(label)) and isinstance(count, int) and count > 0
    }
    exact_matches = [
        entity_class for entity_class in exact_counts
        if query in _class_forms(entity_class)
    ]
    if len(exact_matches) == 1:
        entity_class = exact_matches[0]
        return entity_class, exact_counts[entity_class]
    if len(exact_matches) > 1:
        return None, None
    class_counts: dict[str, int] = {}
    matching_classes: list[str] = []
    for obj in scene.get("objects", []):
        entity_class = normalize_ref(str(obj.get("class") or ""))
        if not entity_class:
            continue
        class_counts[entity_class] = class_counts.get(entity_class, 0) + 1
    for entity_class in class_counts:
        if query in _class_forms(entity_class):
            matching_classes.append(entity_class)
    if len(matching_classes) != 1:
        return None, None
    entity_class = matching_classes[0]
    return entity_class, class_counts[entity_class]


def build_count_prestate(
    *, branch: dict[str, Any], parsed: dict[str, Any], oracle: dict[str, Any],
    resolution: dict[str, Any], catalog: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    atoms = oracle.get("normalized_atoms") or []
    if len(atoms) != 1 or atoms[0].get("predicate") != "COUNT":
        return None, "REJECT_PRESTATE_UNSUPPORTED_ORACLE"
    scene = catalog.get("scenes", {}).get(branch["scene_id"])
    if not isinstance(scene, dict):
        return None, "REJECT_PRESTATE_MISSING"
    atom = atoms[0]
    entity_class, pre_count = count_annotated_class(scene, str(atom["subject"]))
    if entity_class is None or pre_count is None:
        return None, "REJECT_PRECOUNT_MISSING"
    intervention = parsed["intervention"]
    change_type = intervention["type"]
    existence_transition: dict[str, Any] | None = None
    if change_type == "ADDITION":
        refs = intervention.get("new_entity_ref_texts") or []
        new_entities = intervention.get("new_entities") or []
        if len(refs) != 1:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        if not ref_mentions_class(str(refs[0]), entity_class):
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        delta = explicit_quantity(str(refs[0]))
        if delta is None:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        derived_post_count = pre_count + delta
        rule_id = "ADDITION_INCREMENTS_CLASS_COUNT"
        if delta == 1 and len(new_entities) == 1:
            existence_transition = {
                "rule_id": "ADDITION_CREATES_ENTITY",
                "entity_id": str(new_entities[0]), "entity_class": entity_class,
                "entity_role": "new", "derived_post_exists": True,
                "uses_post_oracle_as_premise": False,
            }
    elif change_type == "REMOVAL":
        targets = resolution.get("resolved_targets") or []
        refs = intervention.get("target_ref_texts") or []
        if len(targets) != 1 or len(refs) != 1:
            return None, "REJECT_TARGET_AMBIGUOUS"
        resolved_entity_id = str(targets[0].get("resolved_entity_id") or "")
        resolved_objects = [
            obj for obj in scene.get("objects", [])
            if str(obj.get("object_id") or "") == resolved_entity_id
        ]
        if len(resolved_objects) != 1:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        resolved_class = normalize_ref(str(resolved_objects[0].get("class") or ""))
        if resolved_class != entity_class:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        delta = 1
        derived_post_count = pre_count - 1
        rule_id = "REMOVAL_DECREMENTS_CLASS_COUNT"
        existence_transition = {
            "rule_id": "REMOVAL_DELETES_ENTITY",
            "entity_id": resolved_entity_id, "entity_class": entity_class,
            "entity_role": "old", "derived_post_exists": False,
            "uses_post_oracle_as_premise": False,
        }
    elif change_type == "REPLACEMENT":
        targets = resolution.get("resolved_targets") or []
        old_refs = intervention.get("target_ref_texts") or []
        new_refs = intervention.get("new_entity_ref_texts") or []
        if len(targets) != 1 or len(old_refs) != 1:
            return None, "REJECT_TARGET_AMBIGUOUS"
        if len(new_refs) != 1 or explicit_quantity(str(new_refs[0])) != 1:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        resolved_entity_id = str(targets[0].get("resolved_entity_id") or "")
        resolved_objects = [
            obj for obj in scene.get("objects", [])
            if str(obj.get("object_id") or "") == resolved_entity_id
        ]
        if len(resolved_objects) != 1:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        old_class = normalize_ref(str(resolved_objects[0].get("class") or ""))
        if not ref_mentions_class(str(old_refs[0]), old_class):
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        new_class = unique_catalog_class_mentioned(catalog, str(new_refs[0]))
        if new_class is None or new_class == old_class:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        signed_delta = (1 if entity_class == new_class else 0) - (1 if entity_class == old_class else 0)
        if signed_delta == 0 or pre_count + signed_delta < 0:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        delta = signed_delta
        derived_post_count = pre_count + signed_delta
        rule_id = "REPLACEMENT_UPDATES_CLASS_COUNT"
        new_entities = intervention.get("new_entities") or []
        if len(new_entities) != 1:
            return None, "REJECT_TRANSITION_PRECONDITION_FAIL"
        existence_transition = {
            "rule_id": "REPLACEMENT_SWAPS_ENTITIES",
            "old_entity_id": resolved_entity_id, "old_entity_class": old_class,
            "new_entity_id": str(new_entities[0]), "new_entity_class": new_class,
            "uses_post_oracle_as_premise": False,
        }
    else:
        return None, "REJECT_TRANSITION_RULE_UNAUTHORIZED"
    if derived_post_count != atom.get("value"):
        return None, "REJECT_SOURCE_ORACLE_TRANSITION_DISAGREEMENT"
    fact_id = f"pre_count_{branch['scene_id']}_{entity_class.replace(' ', '_')}_{pre_count}"
    exact_source = (scene.get("exact_class_count_sources") or {}).get(entity_class)
    fact_origin = "SOURCE_EXACT_CLASS_COUNT_ANNOTATION" if exact_source else "SOURCE_OBJECT_ANNOTATION_COUNT"
    fact = {
        "fact_id": fact_id, "subject": entity_class, "predicate": "COUNT",
        "value": pre_count, "state": "pre", "scope": "whole_scene",
        "origin_type": fact_origin,
        "source_scene_id": scene["source_scene_id"],
    }
    if exact_source:
        fact["source_annotation_ref"] = str(exact_source)
    return {
        "scene_id": branch["scene_id"],
        "change_id": branch["change_id"],
        "question_id": branch["question_id"],
        "branch_id": branch["branch_id"],
        "pre_state_subgraph": {
            "fact_ids": [fact_id],
            "facts": [fact],
            "scope": "question_scoped",
            "ground_truth_policy": "STRUCTURED_SOURCE_ANNOTATION_ONLY",
        },
        "accessible_transition": {
            "rule_id": rule_id,
            "delta": delta,
            "derived_post_count": derived_post_count,
            "uses_post_oracle_as_premise": False,
        },
        "existence_transition": existence_transition,
        "label_provenance_check": {
            "post_oracle_id": oracle["oracle_id"],
            "oracle_post_count": atom["value"],
            "derived_post_count": derived_post_count,
            "status": "PASS",
        },
        "affected_set_min": [f"count:{entity_class}"],
        "necessary_pre_fact_ids": [fact_id],
        "change_type": change_type,
        "operator_id": (
            "REPLACEMENT_COUNT_UPDATE_ERROR"
            if change_type == "REPLACEMENT" else "COUNT_UPDATE_OMISSION"
        ),
        "strength_candidate": "L4_CORE",
        "status": "PRESTATE_VALID_TRANSITION_REPLAY_PASS",
    }, None
