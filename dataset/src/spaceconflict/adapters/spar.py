from __future__ import annotations

import re
from typing import Any

from .common import AdapterResult, fact, record_hash, slug


ADAPTER_VERSION = "spar_v1.1_metadata_sample_local"
SPAR7M_APPEARANCE_ADAPTER_VERSION = "spar_7m_appearance_order_v1"
SPAR7M_RELATION_ADAPTER_VERSION = "spar_7m_qualitative_relation_v2"
SLOT_PREDICATES = [
    {"left": "LEFT_OF", "right": "RIGHT_OF"},
    {"above": "ABOVE", "below": "BELOW"},
    {"front": "FRONT_OF", "behind": "BEHIND"},
]


def _options(question: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for letter, value in re.findall(r"^([A-D])\.\s*(.*)$", question, flags=re.MULTILINE):
        result[letter] = [part.strip().casefold() for part in value.split(",")]
    return result


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    del row_index
    source_item_id = f"spar_tiny:{row['id']}"
    source_hash = record_hash(row)
    world_id = f"spar_sample:{row['id']}"
    base = dict(
        source_dataset="spar", source_item_id=source_item_id, source_record_hash=source_hash,
        source_task=row["task"], global_world_id=world_id, adapter_version=ADAPTER_VERSION,
        source_answer=row["answer"], blocking_reject_codes=["MISSING_MEDIA", "BLOCKED_LICENSE", "UNRESOLVED_WORLD_ID"],
        media_locator={"dataset": "jasonzhango/SPAR-Bench-Tiny", "revision": "ae9bbc5297fd277123c42b0628d1f40bf72f89f1", "row_id": row["id"], "view_count": len(row.get("image") or [])},
    )
    if row["task"] != "obj_spatial_relation_oc_mv":
        return AdapterResult(status="REJECTED", reject_codes=["NUMERIC_DEPENDENCY"], **base)
    options = _options(row["question"])
    selected = options.get(str(row["answer"]).upper())
    if selected is None or len(selected) != 3:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    facts = []
    subject = f"spar_sample:{row['id']}:bbox_target"
    observer = f"spar_sample:{row['id']}:observer_view_1"
    for index, token in enumerate(selected):
        if not token:
            continue
        predicate = SLOT_PREDICATES[index].get(token)
        if predicate is None:
            return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_OPERATOR"], **base)
        facts.append(fact(
            subject=subject, predicate=predicate, object_=observer, value=None, world_id=world_id,
            reference_frame="observer_view_1", scope="world_shared_across_views",
            source_item_id=source_item_id, source_record_hash=source_hash, source_dataset="SPAR",
            source_field_paths=["question", "answer", "task", "image"],
            context_extra={"view_id": "view_1", "time_scope": None},
        ))
    reconstructed = next((letter for letter, value in options.items() if value == selected), None)
    return AdapterResult(
        status="WAITING_MEDIA", facts=facts, answer_semantics={"ordered_relation_slots": selected},
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["answer"], **base,
    )


def adapt_appearance_order(row: dict[str, Any], row_index: int) -> AdapterResult:
    """Adapt a SPAR-7M first-appearance answer without inferring frame indices.

    The official QA answer supports only the strict order facts.  Individual
    object-to-frame groundings are deliberately not fabricated.
    """
    del row_index
    source_row = {
        key: row.get(key)
        for key in ("id", "qa_type", "qa_format", "question", "answer", "image", "split")
    }
    source_hash = record_hash(source_row)
    row_id = str(row.get("id", ""))
    base_dataset = str(row.get("base_dataset", "")).casefold()
    scene_id = str(row.get("scene_id", ""))
    source_item_id = f"spar7m:{base_dataset}:{row_id}"
    world_id = f"{base_dataset}:{scene_id}" if base_dataset and scene_id else None
    images = [str(path) for path in (row.get("image") or [])]
    base = dict(
        source_dataset="spar", source_item_id=source_item_id,
        source_record_hash=source_hash, source_task=str(row.get("qa_type", "")),
        global_world_id=world_id, adapter_version=SPAR7M_APPEARANCE_ADAPTER_VERSION,
        source_answer=row.get("answer"), blocking_reject_codes=[],
        media_locator={
            "dataset": "jasonzhango/SPAR-7M",
            "revision": str(row.get("source_revision", "")),
            "base_dataset": base_dataset, "scene_id": scene_id,
            "ordered_frame_paths": images, "frame_count": len(images),
            "validation_scope": "OFFICIAL_ANNOTATION_PATH_REFERENCES_ONLY",
        },
    )
    if row.get("qa_type") != "appearance_order":
        return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_OPERATOR"], **base)
    if base_dataset not in {"scannet", "scannetpp", "structured3d", "rxr"} or not scene_id:
        return AdapterResult(status="REJECTED", reject_codes=["UNRESOLVED_WORLD_ID"], **base)
    if len(images) < 2 or any(
        not path.startswith(f"spar/{base_dataset}/")
        or path.startswith("/") or ".." in path.split("/")
        for path in images
    ):
        return AdapterResult(status="REJECTED", reject_codes=["MISSING_MEDIA"], **base)
    question = str(row.get("question", "")).strip()
    if question.count("<image>") != len(images):
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    sequence = [part.strip() for part in str(row.get("answer", "")).split(",")]
    normalized = [slug(part) for part in sequence]
    if (
        len(sequence) != 4 or any(not part for part in sequence)
        or len(set(item.casefold() for item in sequence)) != 4
        or len(set(normalized)) != 4
        or any(part.casefold() not in question.casefold() for part in sequence)
    ):
        return AdapterResult(status="REJECTED", reject_codes=["AMBIGUOUS_ENTITY"], **base)
    facts = [
        fact(
            subject=f"first_appear:{slug(before)}", predicate="BEFORE",
            object_=f"first_appear:{slug(after)}", value=None,
            world_id=world_id, reference_frame="video_timeline", scope="whole_video",
            source_item_id=source_item_id, source_record_hash=source_hash,
            source_dataset="SPAR", source_field_paths=["answer", "image", "qa_type"],
            context_extra={"time_scope": "whole_ordered_sequence"},
        )
        for before, after in zip(sequence, sequence[1:])
    ]
    reconstructed = ", ".join(sequence)
    return AdapterResult(
        status="SOURCE_REFERENCE_VALID", facts=facts,
        answer_semantics={
            "first_appearance_sequence": sequence,
            "frame_grounding_status": "NOT_PROVIDED_BY_SOURCE_ANNOTATION",
        },
        reconstructed_answer=reconstructed,
        reconstruction_pass=reconstructed.casefold() == str(row.get("answer", "")).strip().casefold(),
        **base,
    )


def _qualitative_predicates(answer: str, task: str) -> list[str]:
    text = answer.casefold()
    predicates = []
    for pattern, predicate in (
        (r"\bleft\b", "LEFT_OF"), (r"\bright\b", "RIGHT_OF"),
        (r"\babove\b", "ABOVE"), (r"\bbelow\b", "BELOW"),
    ):
        if re.search(pattern, text):
            predicates.append(predicate)
    if task == "obj_spatial_relation_oc_mv":
        for pattern, predicate in ((r"\bfront\b", "FRONT_OF"), (r"\bbehind\b", "BEHIND")):
            if re.search(pattern, text):
                predicates.append(predicate)
    return predicates


def adapt_qualitative_relation(row: dict[str, Any], row_index: int) -> AdapterResult:
    """Project SPAR-7M prose answers onto their nonmetric relation dimensions."""
    del row_index
    source_row = {
        key: row.get(key)
        for key in (
            "id", "qa_type", "qa_format", "question", "answer", "image",
            "red_bbox", "green_bbox", "blue_bbox", "yellow_bbox", "bbox_img_idx", "split",
        )
    }
    source_hash = record_hash(source_row)
    task = str(row.get("qa_type", ""))
    row_id = str(row.get("id", ""))
    base_dataset = str(row.get("base_dataset", "")).casefold()
    scene_id = str(row.get("scene_id", ""))
    source_item_id = f"spar7m:{base_dataset}:{task}:{row_id}"
    world_id = f"{base_dataset}:{scene_id}" if base_dataset and scene_id else None
    images = [str(path) for path in (row.get("image") or [])]
    base = dict(
        source_dataset="spar", source_item_id=source_item_id,
        source_record_hash=source_hash, source_task=task, global_world_id=world_id,
        adapter_version=SPAR7M_RELATION_ADAPTER_VERSION, source_answer=row.get("answer"),
        blocking_reject_codes=[],
        media_locator={
            "dataset": "jasonzhango/SPAR-7M",
            "revision": str(row.get("source_revision", "")),
            "base_dataset": base_dataset, "scene_id": scene_id,
            "ordered_frame_paths": images, "frame_count": len(images),
            "bbox_grounding": {
                key: row.get(key) or []
                for key in ("red_bbox", "green_bbox", "blue_bbox", "yellow_bbox", "bbox_img_idx")
            },
            "validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY",
        },
    )
    allowed_tasks = {
        "obj_spatial_relation_oc_mv", "obj_spatial_relation_oo", "obj_spatial_relation_oo_mv",
    }
    if task not in allowed_tasks:
        return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_OPERATOR"], **base)
    if base_dataset not in {"scannet", "scannetpp", "structured3d", "rxr"} or not scene_id:
        return AdapterResult(status="REJECTED", reject_codes=["UNRESOLVED_WORLD_ID"], **base)
    if len(images) not in ({1} if task == "obj_spatial_relation_oo" else {3}) or any(
        not path.startswith(f"spar/{base_dataset}/")
        or path.startswith("/") or ".." in path.split("/")
        for path in images
    ):
        return AdapterResult(status="REJECTED", reject_codes=["MISSING_MEDIA"], **base)
    if str(row.get("question", "")).count("<image>") != len(images):
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    bbox_grounding = base["media_locator"]["bbox_grounding"]
    if not bbox_grounding["red_bbox"] or (
        task in {"obj_spatial_relation_oo", "obj_spatial_relation_oo_mv"}
        and not bbox_grounding["blue_bbox"]
    ):
        return AdapterResult(status="REJECTED", reject_codes=["AMBIGUOUS_ENTITY"], **base)
    raw_answer = str(row.get("answer", "")).strip()
    selected_option = None
    reconstruction_scope = "NONMETRIC_DIRECTIONAL_SEMANTICS_ONLY"
    option_semantics: dict[str, list[str]] = {}
    if raw_answer.upper() in {"A", "B", "C", "D"}:
        option_semantics = _options(str(row.get("question", "")))
        selected_option = option_semantics.get(raw_answer.upper())
        if selected_option is None:
            return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
        semantic_answer = ",".join(selected_option)
        reconstruction_scope = "EXACT_OPTION_LETTER_FROM_NONMETRIC_DIRECTIONAL_SEMANTICS"
    else:
        semantic_answer = raw_answer
    predicates = _qualitative_predicates(semantic_answer, task)
    exclusive_groups = (
        {"LEFT_OF", "RIGHT_OF"}, {"ABOVE", "BELOW"}, {"FRONT_OF", "BEHIND"},
    )
    if not predicates or any(len(set(predicates) & group) > 1 for group in exclusive_groups):
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    subject = "mention:red_bbox_target"
    object_ = (
        "mention:observer_primary_view"
        if task == "obj_spatial_relation_oc_mv" else "mention:blue_bbox_target"
    )
    facts = [
        fact(
            subject=subject, predicate=predicate, object_=object_, value=None,
            world_id=world_id, reference_frame="source_question_declared_perspective",
            scope="current_media", source_item_id=source_item_id,
            source_record_hash=source_hash, source_dataset="SPAR",
            source_field_paths=["answer", "image", "qa_type", "red_bbox", "blue_bbox", "bbox_img_idx"],
            context_extra={"view_id": "primary_view", "time_scope": None},
        )
        for predicate in predicates
    ]
    reconstruction_tokens = {
        "LEFT_OF": "left", "RIGHT_OF": "right", "ABOVE": "above",
        "BELOW": "below", "FRONT_OF": "front", "BEHIND": "behind",
    }
    reconstructed_semantics = ",".join(reconstruction_tokens[predicate] for predicate in predicates)
    if selected_option is not None:
        matches = [
            letter for letter, tokens in option_semantics.items()
            if _qualitative_predicates(",".join(tokens), task) == predicates
        ]
        reconstructed = matches[0] if len(matches) == 1 else None
        reconstruction_pass = reconstructed == raw_answer.upper()
    else:
        reconstructed = reconstructed_semantics
        reconstruction_pass = _qualitative_predicates(reconstructed, task) == predicates
    if not reconstruction_pass:
        return AdapterResult(
            status="REJECTED", facts=facts,
            answer_semantics={
                "qualitative_predicates": predicates,
                "reconstruction_scope": reconstruction_scope,
                "excluded_source_dimensions": ["closer_farther_metric_depth_language"],
            },
            reconstructed_answer=reconstructed, reconstruction_pass=False,
            reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base,
        )
    return AdapterResult(
        status="SOURCE_REFERENCE_VALID", facts=facts,
        answer_semantics={
            "qualitative_predicates": predicates,
            "reconstruction_scope": reconstruction_scope,
            "excluded_source_dimensions": ["closer_farther_metric_depth_language"],
        },
        reconstructed_answer=reconstructed,
        reconstruction_pass=reconstruction_pass,
        **base,
    )
