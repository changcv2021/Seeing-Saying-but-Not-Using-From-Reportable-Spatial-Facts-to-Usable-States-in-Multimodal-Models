from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransitionResult:
    rule_id: str
    predicate: str
    subject: str
    value: object
    affected_set_min: tuple[str, ...]


def removal_exists(target_id: str) -> TransitionResult:
    return TransitionResult(
        "REMOVAL_TARGET_NO_LONGER_EXISTS", "EXISTS_IN_WORLD", target_id, False,
        (f"exists:{target_id}",),
    )


def removal_count(entity_class: str, pre_count: int, removed_count: int = 1) -> TransitionResult:
    if pre_count < 0 or removed_count < 1 or removed_count > pre_count:
        raise ValueError("Removal count rule preconditions failed")
    return TransitionResult(
        "REMOVAL_DECREMENTS_CLASS_COUNT", "COUNT", entity_class, pre_count - removed_count,
        (f"count:{entity_class}",),
    )


def addition_exists(new_entity_id: str) -> TransitionResult:
    return TransitionResult(
        "ADDITION_NEW_ENTITY_EXISTS", "EXISTS_IN_WORLD", new_entity_id, True,
        (f"exists:{new_entity_id}",),
    )


def addition_count(entity_class: str, pre_count: int, added_count: int = 1) -> TransitionResult:
    if pre_count < 0 or added_count < 1:
        raise ValueError("Addition count rule preconditions failed")
    return TransitionResult(
        "ADDITION_INCREMENTS_CLASS_COUNT", "COUNT", entity_class, pre_count + added_count,
        (f"count:{entity_class}",),
    )


def replacement_identity(old_entity_id: str, new_entity_id: str) -> list[TransitionResult]:
    if old_entity_id == new_entity_id:
        raise ValueError("Replacement requires distinct old and new branch-local identities")
    return [
        TransitionResult("REPLACEMENT_REMOVES_OLD_ENTITY", "EXISTS_IN_WORLD", old_entity_id, False, (f"exists:{old_entity_id}",)),
        TransitionResult("REPLACEMENT_ADDS_NEW_ENTITY", "EXISTS_IN_WORLD", new_entity_id, True, (f"exists:{new_entity_id}",)),
        TransitionResult("REPLACEMENT_CREATES_DISTINCT_IDENTITY", "SAME_INSTANCE", f"{old_entity_id}|{new_entity_id}", False, (f"identity:{old_entity_id}:{new_entity_id}",)),
    ]


def movement_identity(target_id: str) -> TransitionResult:
    return TransitionResult(
        "MOVEMENT_PRESERVES_IDENTITY", "EXISTS_IN_WORLD", target_id, True,
        (f"identity:{target_id}",),
    )

