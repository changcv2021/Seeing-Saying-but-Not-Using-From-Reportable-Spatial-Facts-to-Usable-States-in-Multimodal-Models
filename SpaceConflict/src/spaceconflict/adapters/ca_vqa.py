from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .common import AdapterResult, fact, slug


ADAPTER_VERSION = "ca_vqa_val_v2"
BINARY_PATTERN = re.compile(r"^Is there (?:a |an |the )?(.+?) in the image\?$", re.IGNORECASE)
COUNT_PATTERN = re.compile(r"^How many (.+?) (?:are|is) in the image\?$", re.IGNORECASE)
OPTION_PATTERN = re.compile(r"^([A-D])\.\s*([0-9]+)\s*$", re.MULTILINE)
CHOICE_PATTERN = re.compile(r"^([A-D])\.\s*(.+?)\s*$", re.MULTILINE)
RELATION_PATTERN = re.compile(
    r"^Is the (.+?) (to the left|to the right|in front|front|behind|above|below|left|right)(?: of)? the (.+?)\?$",
    re.IGNORECASE,
)
RELATION_PREDICATES = {
    "left": "LEFT_OF", "right": "RIGHT_OF", "front": "FRONT_OF", "in front": "FRONT_OF",
    "to the left": "LEFT_OF", "to the right": "RIGHT_OF",
    "behind": "BEHIND", "above": "ABOVE", "below": "BELOW",
}
METRIC_CUES = (
    " taller ", " higher ", " lower ", " shorter ", " longer ", " wider ", " narrower ",
    " closer ", " farther ", " larger ", " smaller ", " distance ", " length ", " width ",
    " height ", " size ", " cm", " meter", " metre",
)


def _unsupported_code(question: str) -> str:
    normalized = f" {question.casefold()} "
    return "NUMERIC_DEPENDENCY" if any(cue in normalized for cue in METRIC_CUES) else "UNSUPPORTED_OPERATOR"


def _base(row: dict[str, Any]) -> dict[str, Any]:
    source_item_id = f"ca_vqa:{row['task']}:{row['id']}"
    world_id = f"arkitscenes:{row['capture_id']}"
    roles = dict(row["media_roles"])
    return {
        "source_dataset": "ca_vqa",
        "source_item_id": source_item_id,
        "source_record_hash": row["source_record_hash"],
        "source_task": row["task"],
        "global_world_id": row.get("global_world_id", world_id),
        "adapter_version": row.get("adapter_version", ADAPTER_VERSION),
        "source_answer": row["answer"],
        "blocking_reject_codes": row.get("blocking_reject_codes", ["MISSING_MEDIA"]),
        "media_locator": {
            "capture_id": row["capture_id"],
            "reference_index": row["reference_index"],
            "qa_index": row["qa_index"],
            "frame_roles": roles,
            **({"source_locator": row["source_locator"]} if row.get("source_locator") else {}),
        },
    }


def _source_paths(row: dict[str, Any], *qa_fields: str) -> list[str]:
    media_fields = row.get("source_media_field_paths") or [
        "reference_frame", "support_frame_1", "support_frame_2",
        "support_frame_3", "support_frame_4",
    ]
    return [*qa_fields, *media_fields]


def _context(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "view_id": f"reference_frame:{row['capture_id']}:{row['reference_index']}",
        "frame_id": f"{row['capture_id']}_{row['reference_index']}",
        "time_scope": None,
    }


def _class_subject(label: str) -> str:
    return f"class:{slug(label)}"


def _binary(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    match = BINARY_PATTERN.fullmatch(row["question"].strip())
    answer = row["answer"].strip().casefold()
    if match is None or answer not in {"yes", "no"}:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    label = match.group(1).strip()
    direct_fact = fact(
        subject=_class_subject(label), predicate="VISIBLE_IN_FRAME", object_=None, value=None,
        world_id=base["global_world_id"], reference_frame="ca_vqa_reference_frame",
        scope="reference_frame", source_item_id=base["source_item_id"],
        source_record_hash=base["source_record_hash"], source_dataset="CA-VQA",
        source_field_paths=_source_paths(row, "id", "question", "answer"),
        context_extra=_context(row),
    )
    direct_fact["polarity"] = "positive" if answer == "yes" else "negative"
    reconstructed = "Yes" if direct_fact["polarity"] == "positive" else "No"
    return AdapterResult(
        status="WAITING_MEDIA", facts=[direct_fact],
        answer_semantics={"kind": "BINARY_VISIBILITY", "entity_source_text": label, "polarity": direct_fact["polarity"]},
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["answer"].strip(), **base,
    )


def _count(row: dict[str, Any], base: dict[str, Any], *, multichoice: bool) -> AdapterResult:
    question = row["question"].strip()
    match = COUNT_PATTERN.fullmatch(question.splitlines()[0] if multichoice else question)
    if match is None:
        return AdapterResult(status="REJECTED", reject_codes=[_unsupported_code(row["question"])], **base)
    label = match.group(1).strip()
    if multichoice:
        options = {letter: int(value) for letter, value in OPTION_PATTERN.findall(row["question"])}
        selected_letter = row["answer"].strip().upper()
        selected = options.get(selected_letter)
        if selected is None or Counter(options.values())[selected] != 1:
            return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
        reconstructed = next(letter for letter, value in options.items() if value == selected)
        source_paths = _source_paths(row, "id", "question.options", "answer")
    else:
        if not row["answer"].strip().isdigit():
            return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
        selected = int(row["answer"].strip())
        reconstructed = str(selected)
        source_paths = _source_paths(row, "id", "question", "answer")
    direct_fact = fact(
        subject=_class_subject(label), predicate="COUNT", object_=None, value=selected,
        world_id=base["global_world_id"], reference_frame="ca_vqa_reference_frame",
        scope="reference_frame", source_item_id=base["source_item_id"],
        source_record_hash=base["source_record_hash"], source_dataset="CA-VQA",
        source_field_paths=source_paths, context_extra=_context(row),
    )
    return AdapterResult(
        status="WAITING_MEDIA", facts=[direct_fact],
        answer_semantics={"kind": "EXACT_REFERENCE_FRAME_COUNT", "entity_source_text": label, "count": selected},
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["answer"].strip(), **base,
    )


def _multichoice_relation(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    question = row["question"].strip()
    prompt = question.splitlines()[0]
    match = RELATION_PATTERN.fullmatch(prompt)
    options = {letter: value.strip().casefold() for letter, value in CHOICE_PATTERN.findall(question)}
    selected_letter = row["answer"].strip().upper()
    selected = options.get(selected_letter)
    if match is None or selected not in {"yes", "no"} or Counter(options.values())[selected] != 1:
        return AdapterResult(status="REJECTED", reject_codes=[_unsupported_code(row["question"])], **base)
    subject_text, relation_text, object_text = match.groups()
    direct_fact = fact(
        subject=f"mention:{slug(subject_text)}", predicate=RELATION_PREDICATES[relation_text.casefold()],
        object_=f"mention:{slug(object_text)}", value=None,
        world_id=base["global_world_id"], reference_frame="ca_vqa_reference_frame",
        scope="reference_frame", source_item_id=base["source_item_id"],
        source_record_hash=base["source_record_hash"], source_dataset="CA-VQA",
        source_field_paths=_source_paths(row, "id", "question", "question.options", "answer"),
        context_extra=_context(row),
    )
    direct_fact["polarity"] = "positive" if selected == "yes" else "negative"
    reconstructed = next(letter for letter, value in options.items() if value == selected)
    return AdapterResult(
        status="WAITING_MEDIA", facts=[direct_fact],
        answer_semantics={
            "kind": "REFERENCE_FRAME_QUALITATIVE_RELATION", "subject_source_text": subject_text,
            "object_source_text": object_text, "predicate": direct_fact["predicate"],
            "polarity": direct_fact["polarity"],
        },
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == selected_letter, **base,
    )


def _binary_relation(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    match = RELATION_PATTERN.fullmatch(row["question"].strip())
    answer = row["answer"].strip().casefold()
    if match is None or answer not in {"yes", "no"}:
        return AdapterResult(status="REJECTED", reject_codes=[_unsupported_code(row["question"])], **base)
    subject_text, relation_text, object_text = match.groups()
    direct_fact = fact(
        subject=f"mention:{slug(subject_text)}", predicate=RELATION_PREDICATES[relation_text.casefold()],
        object_=f"mention:{slug(object_text)}", value=None,
        world_id=base["global_world_id"], reference_frame="ca_vqa_reference_frame",
        scope="reference_frame", source_item_id=base["source_item_id"],
        source_record_hash=base["source_record_hash"], source_dataset="CA-VQA",
        source_field_paths=_source_paths(row, "id", "question", "answer"),
        context_extra=_context(row),
    )
    direct_fact["polarity"] = "positive" if answer == "yes" else "negative"
    reconstructed = "Yes" if direct_fact["polarity"] == "positive" else "No"
    return AdapterResult(
        status="WAITING_MEDIA", facts=[direct_fact],
        answer_semantics={
            "kind": "REFERENCE_FRAME_QUALITATIVE_RELATION", "subject_source_text": subject_text,
            "object_source_text": object_text, "predicate": direct_fact["predicate"],
            "polarity": direct_fact["polarity"],
        },
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["answer"].strip(), **base,
    )


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    del row_index
    required = {"task", "id", "capture_id", "reference_index", "qa_index", "question", "answer", "media_roles", "source_record_hash"}
    if required - set(row):
        fallback = {
            "source_dataset": "ca_vqa", "source_item_id": f"ca_vqa:malformed:{row.get('id', 'unknown')}",
            "source_record_hash": row.get("source_record_hash", "sha256:" + "0" * 64),
            "source_task": str(row.get("task", "unknown")), "global_world_id": None,
            "adapter_version": ADAPTER_VERSION, "source_answer": row.get("answer"),
            "blocking_reject_codes": [], "media_locator": None,
        }
        return AdapterResult(status="REJECTED", reject_codes=["MISSING_SOURCE_FIELD"], **fallback)
    base = _base(row)
    if row["task"] == "binary":
        if BINARY_PATTERN.fullmatch(row["question"].strip()):
            return _binary(row, base)
        return _binary_relation(row, base)
    if row["task"] == "cardinality":
        return _count(row, base, multichoice=False)
    if row["task"] == "multichoice":
        if COUNT_PATTERN.fullmatch(row["question"].strip().splitlines()[0]):
            return _count(row, base, multichoice=True)
        return _multichoice_relation(row, base)
    return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_TASK"], **base)
