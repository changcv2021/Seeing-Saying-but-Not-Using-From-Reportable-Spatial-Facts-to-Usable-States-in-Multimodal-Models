from __future__ import annotations

from typing import Any

from .common import AdapterResult, fact, record_hash
from ..profiling.profile import HYPO3D_DIRECTION_ANSWERS, _hypo3d_candidate_kind


ADAPTER_VERSION = "hypo3d_v1_post_state_qa"
TOKEN_PREDICATES = {
    "left": "LEFT_OF",
    "right": "RIGHT_OF",
    "front": "FRONT_OF",
    "back": "BEHIND",
    "above": "ABOVE",
    "below": "BELOW",
    "higher": "ABOVE",
    "lower": "BELOW",
}


def _direction_predicates(answer: str) -> list[str]:
    predicates: list[str] = []
    for token in answer.casefold().split():
        predicate = TOKEN_PREDICATES[token]
        if predicate not in predicates:
            predicates.append(predicate)
    return predicates


def _reconstruct_direction(predicates: list[str], original: str) -> str | None:
    tokens = []
    reverse = {
        "LEFT_OF": "left", "RIGHT_OF": "right", "FRONT_OF": "front",
        "BEHIND": "back", "ABOVE": "above", "BELOW": "below",
    }
    for predicate in predicates:
        token = reverse[predicate]
        if token not in tokens:
            tokens.append(token)
    normalized = " ".join(tokens)
    original_normalized = " ".join(original.casefold().split())
    if original_normalized == "higher":
        normalized = "higher" if normalized == "above" else normalized
    elif original_normalized == "lower":
        normalized = "lower" if normalized == "below" else normalized
    return original if normalized == original_normalized else None


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    base_scene_id = str(row.get("base_scene_id", ""))
    branch_index = row.get("branch_index")
    question_id = str(row.get("question_id", ""))
    source_item_id = f"hypo3d:{base_scene_id}:branch:{branch_index}:qa:{question_id}"
    world_id = f"hypo3d:{base_scene_id}"
    source_hash = record_hash(row)
    question = str(row.get("question", ""))
    answer = str(row.get("answer", "")).strip()
    kind = _hypo3d_candidate_kind(question, answer)
    branch_id = f"branch:{branch_index}"
    base = dict(
        source_dataset="hypo3d",
        source_item_id=source_item_id,
        source_record_hash=source_hash,
        source_task=f"{row.get('change_type')}/{row.get('question_type')}",
        global_world_id=world_id,
        adapter_version=ADAPTER_VERSION,
        source_answer=answer,
        blocking_reject_codes=["MISSING_MEDIA"],
        media_locator={
            "base_scene_id": base_scene_id,
            "media_roles": {
                "camera_view": f"camera_view/{base_scene_id}.png",
                "top_view_label": f"top_view_label/{base_scene_id}.png",
                "top_view_no_label": f"top_view_no_label/{base_scene_id}.png",
                "top_view_no_label_rotated": f"top_view_no_label_rotated/{base_scene_id}.png",
                "top_view_with_label_rotated": f"top_view_with_label_rotated/{base_scene_id}.png",
            },
        },
    )
    required = {
        "base_scene_id": base_scene_id,
        "branch_index": branch_index,
        "context_change": row.get("context_change"),
        "change_type": row.get("change_type"),
        "question": question,
        "question_type": row.get("question_type"),
        "question_id": question_id,
        "answer": answer,
    }
    if any(value is None or value == "" for value in required.values()):
        return AdapterResult(status="REJECTED", reject_codes=["MALFORMED_SOURCE_RECORD"], **base)
    if kind is None:
        question_type = str(row.get("question_type"))
        reject_code = {
            "Scale": "METRIC_OR_COMMONSENSE_DEPENDENCY",
            "Scale Direction": "METRIC_OR_PATH_DEPENDENCY",
            "Semantic": "COMMONSENSE_OR_UNSUPPORTED_SEMANTIC",
            "Direction": "AMBIGUOUS_ENTITY_OR_UNSUPPORTED_RELATION",
        }.get(question_type, "UNSUPPORTED_OPERATOR")
        return AdapterResult(status="REJECTED", reject_codes=[reject_code], **base)

    context_extra = {
        "state_id": "post_intervention",
        "branch_id": branch_id,
        "time_scope": "post_intervention",
        "intervention": {
            "change_type": row["change_type"],
            "context_change": row["context_change"],
        },
        "source_question": question,
    }
    field_paths = [
        "base_scene_id", "branch_index", "context_change", "change_type",
        "questions_answers.question", "questions_answers.answer",
    ]
    facts: list[dict[str, Any]] = []
    if kind == "EXACT_COUNT":
        value = int(answer)
        facts.append(fact(
            subject=f"query_set:{source_item_id}", predicate="COUNT", object_=None,
            value=value, world_id=world_id,
            reference_frame="source_declared_post_intervention",
            scope="branch_post_state", source_item_id=source_item_id,
            source_record_hash=source_hash, source_dataset="Hypo3D",
            source_field_paths=field_paths, context_extra=context_extra,
        ))
        reconstructed: str | None = str(value)
        semantics: dict[str, Any] = {
            "kind": kind, "query_set_source_text": question, "count": value,
            "branch_id": branch_id, "context_change": row["context_change"],
        }
    else:
        if answer.casefold() not in HYPO3D_DIRECTION_ANSWERS:
            return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_DIRECTION_ANSWER"], **base)
        predicates = _direction_predicates(answer)
        for predicate in predicates:
            facts.append(fact(
                subject=f"query_subject:{source_item_id}", predicate=predicate,
                object_=f"query_reference:{source_item_id}", value=None,
                world_id=world_id, reference_frame="source_declared_post_intervention",
                scope="branch_post_state", source_item_id=source_item_id,
                source_record_hash=source_hash, source_dataset="Hypo3D",
                source_field_paths=field_paths, context_extra=context_extra,
            ))
        reconstructed = _reconstruct_direction(predicates, answer)
        semantics = {
            "kind": kind, "query_source_text": question,
            "ordered_predicates": predicates, "selected_answer_text": answer,
            "branch_id": branch_id, "context_change": row["context_change"],
        }
    if reconstructed != answer:
        return AdapterResult(
            status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"],
            reconstructed_answer=reconstructed, reconstruction_pass=False, **base,
        )
    return AdapterResult(
        status="WAITING_MEDIA", facts=facts, answer_semantics=semantics,
        reconstructed_answer=reconstructed, reconstruction_pass=True, **base,
    )
