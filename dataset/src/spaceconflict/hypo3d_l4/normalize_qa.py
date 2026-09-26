from __future__ import annotations

import re
from typing import Any


NORMALIZER_VERSION = "hypo3d_post_qa_normalizer_v2_3"
DIRECTION_MAP = {
    "left": "LEFT_OF", "right": "RIGHT_OF", "front": "FRONT_OF", "back": "BEHIND",
    "above": "ABOVE", "below": "BELOW", "higher": "ABOVE", "lower": "BELOW",
}
_COUNT = re.compile(
    r"(?:how many|what (?:is|will be) the (?:new |current |total )?(?:number|count) of)\s+(?P<subject>.+?)(?:\s+(?:are|is|remain|remains|will remain|exist|exists|can be found|in the|now\b)|\?|$)",
    re.IGNORECASE,
)
_RELATIVE = re.compile(
    r"(?:position|location|direction)\s+of\s+(?P<subject>.+?)\s+(?:relative to|in relation to|with respect to|compared to)\s+(?P<object>.+?)(?:\?|$)",
    re.IGNORECASE,
)
_RELATIVE_SHORT = re.compile(
    r"(?:how|where)\s+is\s+(?P<subject>.+?)(?:\s+(?:positioned|located|situated))?\s+(?:relative to|in relation to|with respect to|compared to)\s+(?P<object>.+?)(?:\?|$)",
    re.IGNORECASE,
)
_THERE_EXISTENCE = re.compile(
    r"(?:is there|are there)\s+(?P<subject>.+?)(?:\s+in the (?:scene|room))?(?:\?|$)",
    re.IGNORECASE,
)
_DOES_EXIST = re.compile(
    r"^does\s+(?P<subject>.+?)\s+exist(?:\s+in the (?:scene|room|world))?\s*\?$",
    re.IGNORECASE,
)
_PRESENT_EXISTENCE = re.compile(
    r"^(?:is|are)\s+(?P<subject>.+?)\s+(?:still\s+)?(?:present|available|there)(?:\s+in the (?:scene|room|world))?\s*\?$",
    re.IGNORECASE,
)
_NON_EXISTENCE_SEMANTICS = re.compile(
    r"\b(?:left|right|above|below|behind|front|near|beside|between|under|over|next|"
    r"blocking|blocked|obstructing|obstructed|path|route|reachable|reach|used|use|"
    r"that|which|who|whose|with|without|other|another|remaining)\b",
    re.IGNORECASE,
)


def _clean_entity(text: str) -> str:
    value = " ".join(text.strip(" .,?;:").split()).casefold()
    for prefix in ("a ", "an ", "the "):
        if value.startswith(prefix):
            value = value[len(prefix):]
    return value


def _pure_existence_subject(match: re.Match[str]) -> str | None:
    raw = " ".join(match.group("subject").strip().split())
    if _NON_EXISTENCE_SEMANTICS.search(raw):
        return None
    subject = _clean_entity(raw)
    if subject.startswith("any "):
        subject = subject[4:]
    if not subject or len(subject.split()) > 6:
        return None
    return subject


def _direction_tokens(answer: str) -> list[str] | None:
    tokens = answer.casefold().replace("-", " ").split()
    if not tokens or any(token not in DIRECTION_MAP for token in tokens):
        return None
    return tokens


def normalize_post_qa(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    question = str(record.get("source_question_raw") or "").strip()
    answer = str(record.get("source_answer_raw") or "").strip()
    if not question:
        return None, "REJECT_MISSING_SOURCE_QUESTION"
    if not answer:
        return None, "REJECT_MISSING_SOURCE_ANSWER"
    atoms: list[dict[str, Any]] = []
    reconstructed: str | None = None
    if answer.isdigit():
        match = _COUNT.search(question)
        if not match:
            return None, "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"
        subject = _clean_entity(match.group("subject"))
        if not subject:
            return None, "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"
        atoms.append({
            "subject": subject, "predicate": "COUNT", "object": None, "value": int(answer),
            "scope": "whole_scene", "state": "post", "branch_id": record["branch_id"],
            "reference_frame": None,
        })
        reconstructed = str(int(answer))
    elif answer.casefold() in {"yes", "no"}:
        match = (
            _THERE_EXISTENCE.fullmatch(question)
            or _DOES_EXIST.fullmatch(question)
            or _PRESENT_EXISTENCE.fullmatch(question)
        )
        if not match:
            return None, "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"
        subject = _pure_existence_subject(match)
        if subject is None:
            return None, "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"
        atoms.append({
            "subject": subject, "predicate": "EXISTS_IN_WORLD",
            "object": None, "value": answer.casefold() == "yes", "scope": "whole_scene",
            "state": "post", "branch_id": record["branch_id"], "reference_frame": None,
        })
        reconstructed = answer
    else:
        tokens = _direction_tokens(answer)
        match = _RELATIVE.search(question) or _RELATIVE_SHORT.search(question)
        if tokens is None or match is None:
            return None, "REJECT_POST_ORACLE_NORMALIZATION_FAIL"
        subject = _clean_entity(match.group("subject"))
        object_ = _clean_entity(match.group("object"))
        for token in tokens:
            atoms.append({
                "subject": subject, "predicate": DIRECTION_MAP[token], "object": object_, "value": None,
                "scope": "question_relation", "state": "post", "branch_id": record["branch_id"],
                "reference_frame": "source_declared",
            })
        reconstructed = answer
    if reconstructed.casefold() != answer.casefold():
        return None, "REJECT_POST_ORACLE_NORMALIZATION_FAIL"
    return {
        "oracle_id": f"post_{record['scene_id']}_{record['change_id']}_{record['question_id']}",
        "scene_id": record["scene_id"],
        "change_id": record["change_id"],
        "branch_id": record["branch_id"],
        "origin": "SOURCE_POST_QA",
        "source_question_id": record["question_id"],
        "source_answer_raw": answer,
        "normalized_atoms": atoms,
        "source_reconstruction": "PASS",
        "reconstructed_answer": reconstructed,
        "model_input_visible": False,
        "provenance": {
            "source_hash": record["source_hash"],
            "source_field_paths": record["source_field_paths"],
            "normalizer_version": NORMALIZER_VERSION,
        },
    }, None
