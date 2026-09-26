from __future__ import annotations

import re
from typing import Any


PARSER_VERSION = "hypo3d_change_parser_v2_1"
_SPACE = re.compile(r"\s+")
_LEADING = re.compile(r"^(?:in the (?:scene|room),?\s*)", re.IGNORECASE)
_PASSIVE = {
    "REMOVAL": re.compile(r"^(?P<target>.+?)\s+(?:has been|have been|was|were|is|are|will be)\s+(?:removed|cleared|eliminated|taken away)\b(?P<tail>.*)$", re.IGNORECASE),
    "ADDITION": re.compile(r"^(?P<entity>.+?)\s+(?:has been|have been|was|were|is|are|will be)\s+(?:added|placed|positioned|installed|introduced|hung|set up)\b(?P<tail>.*)$", re.IGNORECASE),
    "MOVEMENT": re.compile(r"^(?P<target>.+?)\s+(?:has been|have been|was|were|is|are|will be)\s+(?:moved|relocated|positioned|placed|turned|pulled|shifted|hung|rearranged|rotated)\b(?P<tail>.*)$", re.IGNORECASE),
    "ATTRIBUTE": re.compile(r"^(?P<target>.+?)\s+(?:has been|have been|has|have|was|were|is|are)\s+(?P<tail>.+)$", re.IGNORECASE),
}
_IMPERATIVE = {
    "REMOVAL": re.compile(r"^(?:remove|delete)\s+(?P<target>.+)$", re.IGNORECASE),
    "ADDITION": re.compile(r"^(?:add|introduce)\s+(?P<entity>.+)$", re.IGNORECASE),
    "MOVEMENT": re.compile(r"^(?:move|relocate)\s+(?P<target>.+?)(?P<tail>\s+(?:to|from|beside|near|left|right|above|below|front|behind)\b.*)?$", re.IGNORECASE),
}
_REPLACEMENT_PASSIVE = re.compile(
    r"^(?P<old>.+?)\s+(?:has been|have been|was|were|is|are|will be)\s+replaced\s+(?:with|by)\s+(?P<new>.+)$",
    re.IGNORECASE,
)
_REPLACEMENT_IMPERATIVE = re.compile(
    r"^replace\s+(?P<old>.+?)\s+(?:with|by)\s+(?P<new>.+)$", re.IGNORECASE
)
_RELATION = re.compile(
    r"\b(?P<relation>left of|right of|in front of|behind|above|below|inside|in|beside|next to)\s+(?P<anchor>.+)$",
    re.IGNORECASE,
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = _SPACE.sub(" ", value).strip(" .,;:")
    text = _LEADING.sub("", text).strip(" .,;:")
    return text or None


def _relation_from_text(text: str | None) -> list[dict[str, str]]:
    if not text:
        return []
    match = _RELATION.search(text)
    if not match:
        return []
    relation = match.group("relation").casefold().replace(" ", "_")
    return [{"predicate_text": relation, "anchor_ref_text": _clean(match.group("anchor")) or ""}]


def parse_change(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    change_type = str(record.get("change_type") or "UNKNOWN")
    raw = _clean(str(record.get("context_change_raw") or ""))
    if not raw:
        return None, "REJECT_MISSING_CONTEXT_CHANGE"
    result: dict[str, Any] = {
        "intervention_id": f"int_{record['scene_id']}_{record['change_id']}",
        "type": change_type,
        "targets": [],
        "new_entities": [],
        "anchors": [],
        "explicit_relations": [],
        "source_text": str(record["context_change_raw"]),
        "parser_version": PARSER_VERSION,
        "parse_status": "PASS",
    }
    if change_type == "REPLACEMENT":
        match = _REPLACEMENT_PASSIVE.match(raw) or _REPLACEMENT_IMPERATIVE.match(raw)
        if not match:
            return None, "REJECT_CHANGE_PARSE_UNSUPPORTED"
        old_ref, new_ref = _clean(match.group("old")), _clean(match.group("new"))
        if not old_ref or not new_ref:
            return None, "REJECT_CHANGE_PARSE_UNSUPPORTED"
        result["target_ref_texts"] = [old_ref]
        result["new_entity_ref_texts"] = [new_ref]
        result["new_entities"] = [f"{record['branch_id']}:entity:new_0001"]
        result["explicit_relations"] = _relation_from_text(new_ref)
        return result, None
    match = (_PASSIVE.get(change_type) or re.compile(r"a^" )).match(raw)
    if not match and change_type in _IMPERATIVE:
        match = _IMPERATIVE[change_type].match(raw)
    if not match:
        return None, "REJECT_CHANGE_TYPE_AMBIGUOUS" if change_type == "UNKNOWN" else "REJECT_CHANGE_PARSE_UNSUPPORTED"
    groups = match.groupdict()
    target_ref = _clean(groups.get("target"))
    entity_ref = _clean(groups.get("entity"))
    tail = _clean(groups.get("tail"))
    if change_type == "ADDITION":
        if not entity_ref:
            return None, "REJECT_CHANGE_PARSE_UNSUPPORTED"
        result["new_entity_ref_texts"] = [entity_ref]
        result["new_entities"] = [f"{record['branch_id']}:entity:new_0001"]
        result["explicit_relations"] = _relation_from_text(f"{entity_ref} {tail or ''}")
    else:
        if not target_ref:
            return None, "REJECT_CHANGE_PARSE_UNSUPPORTED"
        result["target_ref_texts"] = [target_ref]
        result["explicit_relations"] = _relation_from_text(tail)
    result["anchors"] = [
        relation["anchor_ref_text"] for relation in result["explicit_relations"]
        if relation.get("anchor_ref_text")
    ]
    return result, None
