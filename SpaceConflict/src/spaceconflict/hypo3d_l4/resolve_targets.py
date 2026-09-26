from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RESOLVER_VERSION = "hypo3d_target_resolver_v2_2"
_NON_WORD = re.compile(r"[^a-z0-9]+")
_RELATION_TAIL = re.compile(
    r"\b(?:beside|near|next to|left of|right of|in front of|behind|above|below|"
    r"under|underneath|over|on|by|between|closest to|adjacent to|with|that|which)\b",
    re.IGNORECASE,
)


def normalize_ref(value: str) -> str:
    text = _NON_WORD.sub(" ", value.casefold()).strip()
    for prefix in ("the ", "a ", "an "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return " ".join(text.split())


def load_object_catalog(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), dict):
        raise ValueError("Object catalog must contain an object-valued 'scenes' field")
    return value


def _aliases(obj: dict[str, Any]) -> set[str]:
    values = [obj.get("class"), obj.get("label"), *(obj.get("aliases") or [])]
    return {normalize_ref(str(value)) for value in values if value}


def _resolve_one(ref_text: str, objects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    normalized = normalize_ref(ref_text)
    exact = [obj for obj in objects if normalized in _aliases(obj)]
    if exact:
        return exact, "ANNOTATION_ALIGNED" if any(normalized != normalize_ref(str(obj.get("class") or "")) for obj in exact) else "UNIQUE_REFERENTIAL"
    head = _RELATION_TAIL.split(normalized, maxsplit=1)[0].strip()
    if head:
        head_matches = [
            obj for obj in objects
            if any(
                re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", head)
                for alias in _aliases(obj)
            )
        ]
        if len(head_matches) == 1:
            return head_matches, "UNIQUE_CLASS_IN_SCENE"
    return [], "UNRESOLVED"


def resolve_unique_object_ref(
    ref_text: str, objects: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    candidates, tier = _resolve_one(ref_text, objects)
    return (candidates[0], tier) if len(candidates) == 1 else (None, "UNRESOLVED")


def resolve_intervention_targets(
    parsed_row: dict[str, Any], catalog: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    intervention = parsed_row["intervention"]
    scene_id = parsed_row["scene_id"]
    target_refs = list(intervention.get("target_ref_texts") or [])
    new_entity_ids = list(intervention.get("new_entities") or [])
    base = {
        "resolution_id": f"target_{scene_id}_{parsed_row['change_id']}_{parsed_row['question_id']}",
        "scene_id": scene_id,
        "change_id": parsed_row["change_id"],
        "question_id": parsed_row["question_id"],
        "branch_id": parsed_row["branch_id"],
        "resolver_version": RESOLVER_VERSION,
        "new_entity_ids": new_entity_ids,
        "resolved_targets": [],
        "resolved_anchors": [],
        "catalog_source_type": catalog.get("source_type") if catalog else None,
    }
    if not target_refs:
        if intervention["type"] == "ADDITION" and new_entity_ids:
            base.update({
                "status": "PASS_NEW_ENTITY_ONLY",
                "resolution_tier": "BRANCH_LOCAL_NEW_ENTITY",
                "evidence_ids": [parsed_row["source_hash"]],
            })
            return base, None
        return None, "REJECT_TARGET_AMBIGUOUS"
    if catalog is None:
        return None, "REJECT_TARGET_ANNOTATION_MISSING"
    scene = catalog["scenes"].get(scene_id)
    if not isinstance(scene, dict) or not isinstance(scene.get("objects"), list):
        return None, "REJECT_TARGET_ANNOTATION_MISSING"
    objects = [obj for obj in scene["objects"] if isinstance(obj, dict) and obj.get("object_id")]
    tiers: list[str] = []
    evidence_ids: list[str] = []
    for ref_text in target_refs:
        candidates, tier = _resolve_one(ref_text, objects)
        if len(candidates) != 1:
            return None, "REJECT_TARGET_AMBIGUOUS"
        candidate = candidates[0]
        base["resolved_targets"].append({
            "target_ref_text": ref_text,
            "candidate_count": 1,
            "resolved_entity_id": str(candidate["object_id"]),
            "resolution_tier": tier,
            "evidence_fact_ids": [f"object_annotation:{scene_id}:{candidate['object_id']}"],
        })
        tiers.append(tier)
        evidence_ids.append(f"object_annotation:{scene_id}:{candidate['object_id']}")
    base.update({
        "status": "PASS", "resolution_tier": min(tiers), "evidence_ids": evidence_ids,
    })
    return base, None
