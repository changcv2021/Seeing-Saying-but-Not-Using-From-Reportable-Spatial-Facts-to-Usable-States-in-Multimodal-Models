from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..hashing import sha256_file
from ..hypo3d_l4.common import canonical_json, jsonl_bytes, write_versioned
from ..hypo3d_l4.resolve_targets import normalize_ref


MEDIA_ROLES = (
    "camera_view",
    "top_view_label",
    "top_view_no_label",
    "top_view_no_label_rotated",
    "top_view_with_label_rotated",
)
RELATION_COMPLEMENT = {
    "LEFT_OF": "RIGHT_OF",
    "RIGHT_OF": "LEFT_OF",
    "FRONT_OF": "BEHIND",
    "BEHIND": "FRONT_OF",
    "ABOVE": "BELOW",
    "BELOW": "ABOVE",
}
RELATION_PHRASE = {
    "LEFT_OF": "to the left of",
    "RIGHT_OF": "to the right of",
    "FRONT_OF": "in front of",
    "BEHIND": "behind",
    "ABOVE": "above",
    "BELOW": "below",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def stable_id(prefix: str, value: Any, length: int = 24) -> str:
    digest = hashlib.sha256(canonical_json(value)).hexdigest()[:length]
    return f"{prefix}_{digest}"


def load_split_map(path: Path) -> dict[str, str]:
    rows = read_jsonl(path)
    split_map: dict[str, str] = {}
    for row in rows:
        world_id = str(row.get("global_world_id") or "")
        split = str(row.get("split") or "")
        if not world_id or split not in {"train", "dev", "test"}:
            raise ValueError(f"Malformed split row in {path}: {row}")
        if world_id in split_map and split_map[world_id] != split:
            raise ValueError(f"World assigned to multiple splits: {world_id}")
        split_map[world_id] = split
    return split_map


def normalized_class(label: str) -> str:
    return normalize_ref(label)


def class_forms(label: str) -> set[str]:
    base = normalized_class(label)
    forms = {base}
    if base.endswith("y") and len(base) > 1:
        forms.add(base[:-1] + "ies")
    elif base.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(base + "es")
    else:
        forms.add(base + "s")
    return forms


def class_in_text(text: str, label: str) -> bool:
    normalized = normalized_class(text)
    return any(
        re.search(rf"(?:^|\s){re.escape(form)}(?:$|\s)", normalized) is not None
        for form in class_forms(label)
    )


def object_class(scene: dict[str, Any], object_id: str) -> str | None:
    matches = [
        normalized_class(str(obj.get("class") or ""))
        for obj in scene.get("objects", [])
        if str(obj.get("object_id") or "") == object_id
    ]
    return matches[0] if len(matches) == 1 and matches[0] else None


def unique_object_for_class(scene: dict[str, Any], label: str) -> dict[str, Any] | None:
    normalized = normalized_class(label)
    matches = [
        obj for obj in scene.get("objects", [])
        if normalized_class(str(obj.get("class") or "")) == normalized
    ]
    return matches[0] if len(matches) == 1 else None


def resolve_unique_reference(scene: dict[str, Any], reference: str) -> dict[str, Any] | None:
    cleaned = re.sub(r"\b(now|currently|present)\b", " ", reference.casefold())
    labels = sorted({
        normalized_class(str(obj.get("class") or ""))
        for obj in scene.get("objects", [])
        if normalized_class(str(obj.get("class") or ""))
    }, key=lambda item: (-len(item.split()), item))
    matches = [label for label in labels if class_in_text(cleaned, label)]
    if not matches:
        return None
    longest = len(matches[0].split())
    winners = [label for label in matches if len(label.split()) == longest]
    if len(winners) != 1:
        return None
    return unique_object_for_class(scene, winners[0])


def fact_slot(fact: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(fact.get("predicate") or ""),
        str(fact.get("subject") or ""),
        str(fact.get("object") or ""),
        str(fact.get("scope") or ""),
    )


def normalized_fact(fact: dict[str, Any], *, state: str | None = None) -> dict[str, Any]:
    value = {
        "predicate": str(fact.get("predicate") or ""),
        "subject": str(fact.get("subject") or ""),
        "object": fact.get("object"),
        "value": fact.get("value"),
        "scope": str(fact.get("scope") or "question_local"),
        "state": state or str(fact.get("state") or "post"),
    }
    return value


def canonical_fact_hash(fact: dict[str, Any]) -> str:
    return stable_id("fact", normalized_fact(fact), 24)


def media_bundle(
    *, scene_id: str, media_root: Path, cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if scene_id in cache:
        return cache[scene_id]
    roles: dict[str, Any] = {}
    for role in MEDIA_ROLES:
        path = media_root / role / f"{scene_id}.png"
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing source media: {path}")
        roles[role] = {
            "path": f"{role}/{scene_id}.png",
            "sha256": sha256_file(path),
        }
    bundle = {
        "media_ids": [f"hypo3d:{scene_id}:{role}" for role in MEDIA_ROLES],
        "media": roles,
        "source_media_hashes": {role: value["sha256"] for role, value in roles.items()},
        "overlay": None,
    }
    cache[scene_id] = bundle
    return bundle


def count_claim_text(subject: str, value: int, family: int = 0) -> str:
    templates = (
        "After this hypothetical change, the scene contains {value} {subject}.",
        "Once the stated intervention is complete, there are {value} {subject} in the scene.",
        "Following the hypothetical intervention, the number of {subject} in the scene is {value}.",
    )
    return templates[family % len(templates)].format(subject=subject, value=value)


def relation_claim_text(subject: str, predicate: str, object_: str, family: int = 0) -> str:
    phrase = RELATION_PHRASE[predicate]
    templates = (
        "After this hypothetical change, the {subject} is {phrase} the {object}.",
        "Once the stated intervention is complete, the {subject} lies {phrase} the {object}.",
        "Following the hypothetical intervention, the {subject} will be {phrase} the {object}.",
    )
    return templates[family % len(templates)].format(subject=subject, phrase=phrase, object=object_)


def existence_claim_text(subject: str, value: bool, family: int = 0) -> str:
    if value:
        variants = (
            f"After this hypothetical change, {subject} exists in the scene.",
            f"Once the stated intervention is complete, {subject} remains present.",
        )
    else:
        variants = (
            f"After this hypothetical change, {subject} does not exist in the scene.",
            f"Once the stated intervention is complete, {subject} is absent.",
        )
    return variants[family % len(variants)]


def identity_claim_text(old_label: str, new_label: str, same: bool, family: int = 0) -> str:
    relation = "the same instance as" if same else "a different instance from"
    templates = (
        "After this hypothetical change, the new {new} is {relation} the original {old}.",
        "Once the replacement is complete, the new {new} is {relation} the former {old}.",
        "Following the hypothetical replacement, the new {new} is {relation} the old {old}.",
    )
    return templates[family % len(templates)].format(new=new_label, relation=relation, old=old_label)


def graph_text_roundtrip(text: str, graph: dict[str, Any]) -> bool:
    predicate = str(graph.get("predicate") or "")
    value = graph.get("value")
    lowered = " ".join(text.casefold().split())
    if predicate == "COUNT" and isinstance(value, int):
        return str(value) in lowered and normalized_class(str(graph.get("subject") or "")) in normalized_class(lowered)
    if predicate in RELATION_PHRASE:
        return (
            RELATION_PHRASE[predicate] in lowered
            and normalized_class(str(graph.get("subject_label") or graph.get("subject") or "")) in normalized_class(lowered)
            and normalized_class(str(graph.get("object_label") or graph.get("object") or "")) in normalized_class(lowered)
        )
    if predicate == "EXISTS_IN_WORLD" and isinstance(value, bool):
        negative = "does not exist" in lowered or " is absent" in lowered
        return negative is (not value)
    if predicate == "SAME_INSTANCE" and isinstance(value, bool):
        same = "same instance" in lowered
        different = "different instance" in lowered
        return (same and value and not different) or (different and not value and not same)
    return False


def write_json(path: Path, value: Any, *, resume: bool) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    write_versioned(path, payload, resume=resume)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], *, resume: bool) -> None:
    write_versioned(path, jsonl_bytes(rows), resume=resume)


def output_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path): sha256_file(path) for path in paths}

