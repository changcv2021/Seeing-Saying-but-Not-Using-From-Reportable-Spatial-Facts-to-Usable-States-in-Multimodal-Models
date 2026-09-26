from __future__ import annotations

import re
from typing import Any

from .common import AdapterResult, fact, option_map, record_hash, slug


ADAPTER_VERSION = "vsi_bench_v1_metadata"
COUNT_RE = re.compile(r"^How many (?P<category>.+?)\(s\) are in this room\?$", re.IGNORECASE)
DIRECTION_RE = re.compile(
    r"^If I am standing by the (?P<origin>.+?) and facing the (?P<facing>.+?), is the (?P<subject>.+?) to the left or the right of the (?P<object>.+?)\?$",
    re.IGNORECASE,
)
APPEARANCE_RE = re.compile(r"^What will be the first-time appearance order of the following categories in the video: (?P<categories>.+)\?$", re.IGNORECASE)
NUMERIC_TASKS = {
    "object_size_estimation", "object_abs_distance", "object_rel_distance", "room_size_estimation",
    "object_rel_direction_medium", "object_rel_direction_hard",
}


def _base(row: dict[str, Any]) -> dict[str, Any]:
    source_item_id = f"vsi:{row['id']}"
    return {
        "source_dataset": "vsi_bench", "source_item_id": source_item_id,
        "source_record_hash": record_hash(row), "source_task": row["question_type"],
        "global_world_id": f"{row['dataset']}:{row['scene_name']}", "adapter_version": ADAPTER_VERSION,
        "source_answer": row["ground_truth"], "blocking_reject_codes": ["MISSING_MEDIA"],
        "media_locator": {"archive": f"{row['dataset']}.zip", "scene_name": row["scene_name"]},
    }


def _adapt_count(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    match = COUNT_RE.fullmatch(row["question"].strip())
    if not match or not str(row["ground_truth"]).isdigit():
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    category = match.group("category").strip()
    value = int(row["ground_truth"])
    candidate_fact = fact(
        subject=f"class:{slug(category)}", predicate="COUNT", object_=None, value=value,
        world_id=base["global_world_id"], reference_frame="allocentric", scope="whole_video",
        source_item_id=base["source_item_id"], source_record_hash=base["source_record_hash"],
        source_dataset="VSI-Bench", source_field_paths=["question", "ground_truth", "question_type"],
        context_extra={"time_scope": "whole_video", "count_scope": "whole_video"},
    )
    reconstructed = str(value)
    return AdapterResult(status="WAITING_MEDIA", facts=[candidate_fact], answer_semantics={"category": category, "count": value}, reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == str(row["ground_truth"]), **base)


def _adapt_direction(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    match = DIRECTION_RE.fullmatch(row["question"].strip())
    if not match or match.group("facing").casefold() != match.group("object").casefold():
        return AdapterResult(status="REJECTED", reject_codes=["MISSING_REFERENCE_FRAME"], **base)
    try:
        options = option_map(row["options"])
    except ValueError:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    selected = options.get(str(row["ground_truth"]).upper(), "").casefold()
    predicate = {"left": "LEFT_OF", "right": "RIGHT_OF"}.get(selected)
    if predicate is None:
        return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_OPERATOR"], **base)
    subject, object_, origin = match.group("subject").strip(), match.group("object").strip(), match.group("origin").strip()
    reconstructed = next((letter for letter, value in options.items() if value.casefold() == selected), None)
    candidate_fact = fact(
        subject=f"mention:{slug(subject)}", predicate=predicate, object_=f"mention:{slug(object_)}", value=None,
        world_id=base["global_world_id"], reference_frame=f"agent_at:{slug(origin)}:facing:{slug(object_)}",
        scope="whole_video", source_item_id=base["source_item_id"], source_record_hash=base["source_record_hash"],
        source_dataset="VSI-Bench", source_field_paths=["question", "options", "ground_truth"],
        context_extra={"time_scope": "whole_video"},
    )
    semantics = {"origin_surface": origin, "facing_surface": object_, "subject_surface": subject, "predicate": predicate, "object_surface": object_}
    return AdapterResult(status="WAITING_MEDIA", facts=[candidate_fact], answer_semantics=semantics, reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["ground_truth"], **base)


def _adapt_appearance(row: dict[str, Any], base: dict[str, Any]) -> AdapterResult:
    match = APPEARANCE_RE.fullmatch(row["question"].strip())
    if not match:
        return AdapterResult(status="REJECTED", reject_codes=["TIME_SCOPE_AMBIGUOUS"], **base)
    query_categories = [part.strip().casefold() for part in match.group("categories").split(",")]
    try:
        options = option_map(row["options"])
    except ValueError:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    selected_text = options.get(str(row["ground_truth"]).upper())
    if selected_text is None:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    sequence = [part.strip() for part in selected_text.split(",")]
    if len(sequence) != len(set(item.casefold() for item in sequence)) or sorted(item.casefold() for item in sequence) != sorted(query_categories):
        return AdapterResult(status="REJECTED", reject_codes=["AMBIGUOUS_ENTITY"], **base)
    facts = []
    for before, after in zip(sequence, sequence[1:]):
        facts.append(fact(
            subject=f"first_appear:{slug(before)}", predicate="BEFORE", object_=f"first_appear:{slug(after)}", value=None,
            world_id=base["global_world_id"], reference_frame="video_timeline", scope="whole_video",
            source_item_id=base["source_item_id"], source_record_hash=base["source_record_hash"],
            source_dataset="VSI-Bench", source_field_paths=["question", "options", "ground_truth"],
            context_extra={"time_scope": "whole_video"},
        ))
    normalized_sequence = [slug(item) for item in sequence]
    reconstructed = None
    for letter, value in options.items():
        if [slug(part) for part in value.split(",")] == normalized_sequence:
            reconstructed = letter
            break
    return AdapterResult(status="WAITING_MEDIA", facts=facts, answer_semantics={"first_appearance_sequence": sequence}, reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["ground_truth"], **base)


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    del row_index
    base = _base(row)
    task = row["question_type"]
    if task == "object_counting":
        return _adapt_count(row, base)
    if task == "object_rel_direction_easy":
        return _adapt_direction(row, base)
    if task == "obj_appearance_order":
        return _adapt_appearance(row, base)
    code = "NUMERIC_DEPENDENCY" if task in NUMERIC_TASKS else "UNSUPPORTED_OPERATOR"
    return AdapterResult(status="REJECTED", reject_codes=[code], **base)

