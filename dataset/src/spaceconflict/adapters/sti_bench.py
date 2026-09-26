from __future__ import annotations

import re
from typing import Any

from .common import AdapterResult, fact, option_map, record_hash, slug


ADAPTER_VERSION = "sti_bench_v1.1_metadata"
RELATIONS = {"Left": "LEFT_OF", "Right": "RIGHT_OF", "Front": "FRONT_OF", "Back": "BEHIND"}
RELATION_QUESTION = re.compile(
    r"^(?:What is the positional relationship of|Where is)\s+(?P<subject>.+?)\s+relative to\s+(?P<object>.+?)(?:\s+from the observer's perspective)?\s*\?$",
    flags=re.IGNORECASE,
)


def adapt(row: dict[str, Any], row_index: int) -> AdapterResult:
    source_item_id = f"sti:{slug(row['Source'])}:{row['Video']}:{row['ID']}:{row_index}"
    source_hash = record_hash(row)
    world_id = f"sti:{slug(row['Source'])}:{row['Video'].rsplit('.', 1)[0]}"
    base = dict(
        source_dataset="sti_bench", source_item_id=source_item_id, source_record_hash=source_hash,
        source_task=str(row["Task"]), global_world_id=world_id, adapter_version=ADAPTER_VERSION,
        source_answer=row["Answer"], blocking_reject_codes=["MISSING_MEDIA"],
        media_locator={"relative_path": f"videos/{row['Video']}", "time_start": row["time_start"], "time_end": row["time_end"]},
    )
    if row["Task"] != "Spatial Relation":
        return AdapterResult(status="REJECTED", reject_codes=["NUMERIC_DEPENDENCY"], **base)
    if row["Question"].startswith("What is the orientation of the camera mounted"):
        return AdapterResult(status="REJECTED", reject_codes=["MISSING_REFERENCE_FRAME"], **base)
    predicate = RELATIONS.get(str(row["Answer Detail"]))
    if predicate is None:
        return AdapterResult(status="REJECTED", reject_codes=["UNSUPPORTED_OPERATOR"], **base)
    match = RELATION_QUESTION.fullmatch(str(row["Question"]).strip())
    if not match:
        return AdapterResult(status="REJECTED", reject_codes=["AMBIGUOUS_ENTITY"], **base)
    subject_surface = match.group("subject").strip()
    object_surface = match.group("object").strip()
    options = option_map(row["Candidates"])
    reconstructed = next((letter for letter, value in options.items() if value.casefold() == str(row["Answer Detail"]).casefold()), None)
    if reconstructed != row["Answer"]:
        return AdapterResult(status="REJECTED", reject_codes=["SOURCE_RECONSTRUCTION_FAIL"], **base)
    candidate_fact = fact(
        subject=f"mention:{slug(subject_surface)}", predicate=predicate,
        object_=f"mention:{slug(object_surface)}", value=None, world_id=world_id,
        reference_frame="observer", scope="time_interval", source_item_id=source_item_id,
        source_record_hash=source_hash, source_dataset="STI-Bench",
        source_field_paths=["Question", "Answer", "Answer Detail", "time_start", "time_end"],
        context_extra={"time_scope": {"start": row["time_start"], "end": row["time_end"]}},
    )
    semantics = {"subject_surface": subject_surface, "predicate": predicate, "object_surface": object_surface}
    return AdapterResult(
        status="WAITING_MEDIA", facts=[candidate_fact], answer_semantics=semantics,
        reconstructed_answer=reconstructed, reconstruction_pass=reconstructed == row["Answer"], **base,
    )
