from __future__ import annotations

from typing import Any

from .common import AdapterResult, fact, record_hash, slug


ADAPTER_VERSION = "omnispatial_v1_claim_local"
TOKEN_PREDICATES = {
    "left": "LEFT_OF", "right": "RIGHT_OF", "front": "FRONT_OF", "forward": "FRONT_OF",
    "rear": "BEHIND", "back": "BEHIND", "above": "ABOVE", "upper": "ABOVE",
    "below": "BELOW", "lower": "BELOW",
}


def _selected_answer(row: dict[str, Any]) -> str | None:
    options = row.get("options")
    answer = row.get("answer")
    if not isinstance(options, list) or not isinstance(answer, int) or not 0 <= answer < len(options):
        return None
    return str(options[answer]).strip()


def _candidate_kind(row: dict[str, Any], selected: str) -> str | None:
    question = str(row.get("question", "")).casefold()
    if selected.isdigit() and ("how many" in question or question.startswith("count ")):
        return "EXACT_COUNT"
    tokens = set(selected.casefold().replace("-", " ").split())
    if (
        row.get("task_type") == "Perspective_Taking" and tokens and
        tokens <= set(TOKEN_PREDICATES) and
        any(cue in question for cue in ("perspective", "left or right", "left/right", "if you", "if you're", "if i "))
    ):
        return "PERSPECTIVE_DIRECTION"
    return None


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    del row_index
    raw_id = str(row.get("id"))
    task_type = str(row.get("task_type"))
    item_id = raw_id.rsplit("_", 1)[0]
    source_item_id = f"omni:{slug(task_type)}:{raw_id}"
    world_id = f"omnispatial:{slug(task_type)}:{item_id}"
    source_hash = record_hash(row)
    selected = _selected_answer(row)
    base = dict(
        source_dataset="omnispatial", source_item_id=source_item_id,
        source_record_hash=source_hash,
        source_task=f"{task_type}/{row.get('sub_task_type')}",
        global_world_id=world_id, adapter_version=ADAPTER_VERSION,
        source_answer=row.get("answer"), blocking_reject_codes=["MISSING_MEDIA"],
        media_locator={
            "archive": "OmniSpatial-full.zip", "task_type": task_type,
            "raw_qa_id": raw_id, "item_id": item_id,
        },
    )
    if selected is None:
        return AdapterResult(status="REJECTED", reject_codes=["MALFORMED_SOURCE_OPTIONS"], **base)
    kind = _candidate_kind(row, selected)
    if kind is None:
        numeric = row.get("sub_task_type") in {"Motion_Analysis", "Geospatial_Strategy"}
        return AdapterResult(
            status="REJECTED", reject_codes=["NUMERIC_DEPENDENCY" if numeric else "UNSUPPORTED_OPERATOR"],
            **base,
        )
    facts: list[dict[str, Any]] = []
    if kind == "EXACT_COUNT":
        facts.append(fact(
            subject=f"query_set:{source_item_id}", predicate="COUNT", object_=None,
            value=int(selected), world_id=world_id, reference_frame="source_question_declared",
            scope="current_media", source_item_id=source_item_id, source_record_hash=source_hash,
            source_dataset="OmniSpatial", source_field_paths=["question", "options", "answer"],
            context_extra={"time_scope": None},
        ))
        semantics: dict[str, Any] = {
            "kind": kind, "query_set_source_text": row["question"], "count": int(selected),
        }
    else:
        predicates = []
        for token in selected.casefold().replace("-", " ").split():
            predicate = TOKEN_PREDICATES[token]
            if predicate not in predicates:
                predicates.append(predicate)
        for predicate in predicates:
            facts.append(fact(
                subject=f"query_target:{source_item_id}", predicate=predicate,
                object_=f"perspective_reference:{source_item_id}", value=None,
                world_id=world_id, reference_frame="source_question_declared_perspective",
                scope="current_media", source_item_id=source_item_id, source_record_hash=source_hash,
                source_dataset="OmniSpatial", source_field_paths=["question", "options", "answer"],
                context_extra={"time_scope": None},
            ))
        semantics = {
            "kind": kind, "query_source_text": row["question"],
            "ordered_predicates": predicates, "selected_answer_text": selected,
        }
    exact_indices = [index for index, option in enumerate(row["options"]) if str(option).strip() == selected]
    reconstructed = exact_indices[0] if len(exact_indices) == 1 else None
    if reconstructed != row["answer"]:
        return AdapterResult(
            status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"],
            reconstructed_answer=reconstructed, reconstruction_pass=False, **base,
        )
    return AdapterResult(
        status="WAITING_MEDIA", facts=facts, answer_semantics=semantics,
        reconstructed_answer=reconstructed, reconstruction_pass=True, **base,
    )
