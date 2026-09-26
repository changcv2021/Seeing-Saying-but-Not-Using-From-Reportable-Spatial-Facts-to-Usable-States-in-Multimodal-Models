from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq

from ..registry import ROOT


REVISIONS = {
    "ca_vqa": "080812355c21a40f437ed03d4ae558d35bfa2929",
    "sti_bench": "6b1009261689d3d5244bc2338ab5f83e3fb55875",
    "vsi_bench": "bdcadb3fea447621a828a24911801faba3587c12",
    "spar": "ae9bbc5297fd277123c42b0628d1f40bf72f89f1",
    "omnispatial": "6691f3288bb1ff207d6ead4d841b505de08a6fd8",
    "hypo3d": "ffb21ab198e8d666b63e062d931ed33b60c67d0f",
}

STI_NUMERIC_TASKS = {
    "Displacement & Path Length", "Speed & Acceleration", "Pose Estimation",
    "3D Video Grounding", "Dimensional Measurement", "Ego-Centric Orientation",
    "Trajectory Description",
}
VSI_NUMERIC_TASKS = {
    "object_size_estimation", "object_abs_distance", "object_rel_distance",
    "room_size_estimation", "object_rel_direction_medium", "object_rel_direction_hard",
}
VSI_ADAPTER_WHITELIST = {"object_counting", "object_rel_direction_easy", "obj_appearance_order"}
HYPO3D_DIRECTION_ANSWERS = {
    "left", "right", "front", "back", "above", "below", "higher", "lower",
    "front left", "front right", "back left", "back right",
}
HYPO3D_RELATION_CUES = (
    " relative to ", " in relation to ", " in comparison to ", " compared to ",
    " positioned in relation to ", " situated in relation to ", " with respect to ",
)


def _omni_answer(row: dict[str, Any]) -> str | None:
    options = row.get("options")
    answer = row.get("answer")
    if not isinstance(options, list) or not isinstance(answer, int) or not 0 <= answer < len(options):
        return None
    return str(options[answer]).strip()


def _omni_candidate_kind(row: dict[str, Any]) -> str | None:
    answer = _omni_answer(row)
    if answer is None:
        return None
    question = str(row.get("question", "")).casefold()
    if answer.isdigit() and ("how many" in question or question.startswith("count ")):
        return "EXACT_COUNT"
    direction_tokens = set(answer.casefold().replace("-", " ").split())
    if (
        row.get("task_type") == "Perspective_Taking"
        and direction_tokens
        and direction_tokens <= {"left", "right", "front", "forward", "rear", "back", "above", "below", "upper", "lower"}
        and any(cue in question for cue in ("perspective", "left or right", "left/right", "if you", "if you're", "if i "))
    ):
        return "PERSPECTIVE_DIRECTION"
    return None


def _distribution(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter("<NULL>" if value is None else str(value) for value in values).items()))


def _top_distribution(values: Iterable[Any], limit: int = 50) -> dict[str, int]:
    return dict(Counter("<NULL>" if value is None else str(value) for value in values).most_common(limit))


def _missing_rates(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, float]:
    total = len(rows) or 1
    return {field: sum(row.get(field) is None or row.get(field) == "" for row in rows) / total for field in fields}


def _duration_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values), "min": min(values), "median": statistics.median(values),
        "mean": statistics.fmean(values), "max": max(values),
    }


def _hypo3d_candidate_kind(question: str, answer: Any) -> str | None:
    """Return only certificate-safe post-state QA families.

    This is deliberately narrower than the upstream task labels.  Hypo3D's
    ``Scale`` and ``Scale Direction`` groups also contain metric, path,
    affordance, and commonsense questions that SpaceConflict must reject.
    """
    normalized_question = " ".join(question.casefold().split())
    normalized_answer = str(answer).strip().casefold()
    if normalized_answer.isdigit() and any(
        cue in normalized_question
        for cue in ("how many", "number of", "total number", "total count", "current count", "new count")
    ):
        return "EXACT_COUNT"
    if normalized_answer in HYPO3D_DIRECTION_ANSWERS:
        if normalized_answer in {"higher", "lower"} and "higher or lower" in normalized_question:
            return "VERTICAL_RELATION"
        if any(cue in normalized_question for cue in HYPO3D_RELATION_CUES):
            return "POST_STATE_RELATION"
    return None


def _profile_sti(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    revision = REVISIONS["sti_bench"]
    path = root / "data" / "raw" / "sti_bench" / revision / "qa.parquet"
    rows = pq.read_table(path).to_pylist()
    worlds = {(row["Source"], row["Video"]) for row in rows}
    composite_ids = [(row["Source"], row["Video"], row["ID"]) for row in rows]
    task_counts = Counter(row["Task"] for row in rows)
    spatial_objects = [
        row for row in rows
        if row["Task"] == "Spatial Relation"
        and not row["Question"].startswith("What is the orientation of the camera mounted")
        and row["Answer Detail"] in {"Left", "Right", "Front", "Back"}
        and row["Candidates"].get(row["Answer"]) == row["Answer Detail"]
    ]
    durations = [float(row["time_end"] - row["time_start"]) for row in rows]
    profile = {
        "dataset": "sti_bench", "source_revision": revision, "profile_scope": "full_qa_metadata",
        "record_count": len(rows), "qa_count": len(rows), "image_count": 0,
        "video_count": len(worlds), "world_count": len(worlds), "view_count": None,
        "frame_count": None, "time_interval_count": len({(r["Source"], r["Video"], r["time_start"], r["time_end"]) for r in rows}),
        "instance_count": None, "track_count": None, "context_change_count": 0, "branch_count": 0,
        "question_type_distribution": dict(sorted(task_counts.items())),
        "answer_type_distribution": _distribution(row["QType"] for row in rows),
        "answer_value_distribution": _top_distribution(row["Answer Detail"] for row in rows),
        "missing_field_rate": _missing_rates(rows, list(rows[0])),
        "duplicate_id_rate": 1 - len(set(composite_ids)) / len(composite_ids),
        "missing_media_rate": 1.0,
        "world_qa_density": {"mean": len(rows) / len(worlds), "max": max(Counter((r["Source"], r["Video"]) for r in rows).values())},
        "duration_distribution": _duration_summary(durations),
        "task_metric_dependency_rate": sum(count for task, count in task_counts.items() if task in STI_NUMERIC_TASKS) / len(rows),
        "adapter_candidate_count": len(spatial_objects),
        "adapter_candidate_rate": len(spatial_objects) / len(rows),
        "media_validation_status": "PENDING_PILOT_MEDIA",
    }
    inventory = [
        {"task": task, "count": count, "policy": "candidate" if task == "Spatial Relation" else "reject", "reason": "object_relation_subset_only" if task == "Spatial Relation" else "NUMERIC_DEPENDENCY"}
        for task, count in sorted(task_counts.items())
    ]
    return profile, inventory, rows[:10]


def _profile_vsi(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    revision = REVISIONS["vsi_bench"]
    path = root / "data" / "raw" / "vsi_bench" / revision / "test.jsonl"
    with path.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    worlds = {(row["dataset"], row["scene_name"]) for row in rows}
    task_counts = Counter(row["question_type"] for row in rows)
    candidate_count = sum(count for task, count in task_counts.items() if task in VSI_ADAPTER_WHITELIST)
    profile = {
        "dataset": "vsi_bench", "source_revision": revision, "profile_scope": "full_qa_metadata",
        "record_count": len(rows), "qa_count": len(rows), "image_count": 0,
        "video_count": len(worlds), "world_count": len(worlds), "view_count": None,
        "frame_count": None, "time_interval_count": None, "instance_count": None,
        "track_count": None, "context_change_count": 0, "branch_count": 0,
        "question_type_distribution": dict(sorted(task_counts.items())),
        "answer_type_distribution": {"multiple_choice": sum(r["options"] is not None for r in rows), "free_form": sum(r["options"] is None for r in rows)},
        "answer_value_distribution": _top_distribution(row["ground_truth"] for row in rows),
        "missing_field_rate": _missing_rates(rows, list(rows[0])),
        "duplicate_id_rate": 1 - len({row["id"] for row in rows}) / len(rows),
        "missing_media_rate": 1.0,
        "world_qa_density": {"mean": len(rows) / len(worlds), "max": max(Counter((r["dataset"], r["scene_name"]) for r in rows).values())},
        "duration_distribution": {"count": 0, "min": None, "median": None, "mean": None, "max": None},
        "task_metric_dependency_rate": sum(count for task, count in task_counts.items() if task in VSI_NUMERIC_TASKS) / len(rows),
        "adapter_candidate_count": candidate_count, "adapter_candidate_rate": candidate_count / len(rows),
        "media_validation_status": "PENDING_PILOT_MEDIA",
    }
    inventory = []
    for task, count in sorted(task_counts.items()):
        if task in VSI_ADAPTER_WHITELIST:
            policy, reason = "candidate", "DETERMINISTIC_TEMPLATE_SUPPORTED"
        elif task in VSI_NUMERIC_TASKS:
            policy, reason = "reject", "NUMERIC_DEPENDENCY"
        else:
            policy, reason = "reject", "UNSUPPORTED_TASK"
        inventory.append({"task": task, "count": count, "policy": policy, "reason": reason})
    return profile, inventory, rows[:10]


def _profile_spar(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    revision = REVISIONS["spar"]
    raw = root / "data" / "raw" / "spar" / revision
    info = json.loads((raw / "dataset_info.json").read_text(encoding="utf-8"))
    first_rows = [item["row"] for item in json.loads((raw / "first_rows.json").read_text(encoding="utf-8"))["rows"]]
    relation_rows = [item["row"] for item in json.loads((raw / "filtered_obj_spatial_relation_oc_mv.json").read_text(encoding="utf-8"))["rows"]]
    rows = first_rows + relation_rows
    task_counts = Counter(row["task"] for row in rows)
    split = info["dataset_info"]["default"]["splits"]["test"]
    profile = {
        "dataset": "spar", "source_revision": revision, "profile_scope": "schema_plus_150_stratified_rows",
        "record_count": split["num_examples"], "qa_count": split["num_examples"], "local_sampled_qa_count": len(rows),
        "image_count": None, "video_count": None, "world_count": None, "view_count": None,
        "frame_count": None, "time_interval_count": None, "instance_count": None, "track_count": None,
        "context_change_count": 0, "branch_count": 0,
        "question_type_distribution_sample": dict(sorted(task_counts.items())),
        "answer_type_distribution_sample": _distribution(row["format_type"] for row in rows),
        "answer_value_distribution_sample": _top_distribution(row["answer"] for row in rows),
        "missing_field_rate_sample": _missing_rates(rows, list(rows[0])),
        "duplicate_id_rate_sample": 1 - len({row["id"] for row in rows}) / len(rows),
        "missing_media_rate": 1.0, "world_qa_density": None,
        "duration_distribution": {"count": 0, "min": None, "median": None, "mean": None, "max": None},
        "task_metric_dependency_rate_sample": len(first_rows) / len(rows),
        "adapter_candidate_count": len(relation_rows), "adapter_candidate_rate_in_profiled_rows": len(relation_rows) / len(rows),
        "full_dataset_profile_status": "REQUIRES_COMPUTE_NODE_OR_METADATA_ONLY_PARQUET_ACCESS",
        "media_validation_status": "PENDING_PILOT_MEDIA",
    }
    inventory = [
        {"task": task, "count": count, "policy": "candidate" if task == "obj_spatial_relation_oc_mv" else "reject", "reason": "DETERMINISTIC_DISCRETE_RELATION_BUNDLE" if task == "obj_spatial_relation_oc_mv" else "NUMERIC_DEPENDENCY"}
        for task, count in sorted(task_counts.items())
    ]
    examples = [{key: value for key, value in row.items() if key != "image"} for row in rows[:5] + relation_rows[:5]]
    return profile, inventory, examples


def _profile_omnispatial(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    revision = REVISIONS["omnispatial"]
    path = root / "data/raw/omnispatial" / revision / "data.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("OmniSpatial data.json must contain a list")
    task_counts = Counter((row.get("task_type"), row.get("sub_task_type")) for row in rows)
    candidate_kinds = Counter(kind for row in rows if (kind := _omni_candidate_kind(row)))
    malformed = sum(_omni_answer(row) is None for row in rows)
    worlds = {
        (str(row.get("task_type")), str(row.get("id", "")).rsplit("_", 1)[0]) for row in rows
    }
    world_density = Counter(
        (str(row.get("task_type")), str(row.get("id", "")).rsplit("_", 1)[0]) for row in rows
    )
    profile = {
        "dataset": "omnispatial", "source_revision": revision, "profile_scope": "full_qa_metadata",
        "record_count": len(rows), "qa_count": len(rows), "image_count": None,
        "video_count": None, "world_count": len(worlds), "view_count": None, "frame_count": None,
        "time_interval_count": None, "instance_count": None, "track_count": None,
        "context_change_count": 0, "branch_count": 0,
        "question_type_distribution": {
            f"{task}/{subtask}": count for (task, subtask), count in sorted(task_counts.items())
        },
        "answer_type_distribution": {"multiple_choice": len(rows) - malformed, "malformed_options": malformed},
        "answer_value_distribution": _top_distribution(_omni_answer(row) for row in rows),
        "missing_field_rate": _missing_rates(rows, ["id", "question", "options", "answer", "task_type", "sub_task_type"]),
        "duplicate_id_rate": 1 - len({(row.get("task_type"), row.get("id")) for row in rows}) / len(rows),
        "cross_task_raw_id_collision_count": len(rows) - len({row.get("id") for row in rows}),
        "missing_media_rate": 1.0,
        "world_qa_density": {"mean": len(rows) / len(worlds), "max": max(world_density.values())},
        "duration_distribution": {"count": 0, "min": None, "median": None, "mean": None, "max": None},
        "task_metric_dependency_rate": sum(
            row.get("sub_task_type") in {"Motion_Analysis", "Geospatial_Strategy"} for row in rows
        ) / len(rows),
        "adapter_candidate_count": sum(candidate_kinds.values()),
        "adapter_candidate_rate": sum(candidate_kinds.values()) / len(rows),
        "adapter_candidate_kind_distribution": dict(sorted(candidate_kinds.items())),
        "media_validation_status": "PENDING_PILOT_MEDIA",
    }
    inventory = []
    for (task, subtask), count in sorted(task_counts.items()):
        candidate_count = sum(
            _omni_candidate_kind(row) is not None
            for row in rows if row.get("task_type") == task and row.get("sub_task_type") == subtask
        )
        inventory.append({
            "task": f"{task}/{subtask}", "count": count,
            "policy": "candidate_subset" if candidate_count else "reject",
            "reason": f"DETERMINISTIC_WHITELIST_ROWS={candidate_count}" if candidate_count else "NO_CERTIFICATE_SAFE_TEMPLATE",
        })
    examples = []
    example_counts: Counter[str] = Counter()
    for row in rows:
        task = f"{row.get('task_type')}/{row.get('sub_task_type')}"
        if example_counts[task] < 2:
            examples.append(row)
            example_counts[task] += 1
    return profile, inventory, examples


def _profile_hypo3d(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    revision = REVISIONS["hypo3d"]
    results_path = root / "runs/download_hypo3d_slurm_8073072/results.tsv"
    with results_path.open("r", encoding="utf-8") as handle:
        header = next(handle).rstrip("\n").split("\t")
        rows = [dict(zip(header, line.rstrip("\n").split("\t"))) for line in handle if line.strip()]
    media_rows = [row for row in rows if row["path"].casefold().endswith(".png")]
    group_counts = Counter(Path(row["path"]).parts[0] for row in media_rows)
    scene_keys = {Path(row["path"]).stem for row in media_rows}
    failures = [row for row in rows if row["status"] not in {"DOWNLOADED_AND_VERIFIED", "ALREADY_VALID"}]
    annotation_path = root / "data" / "raw" / "hypo3d" / revision / "hypo3d.json"
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    if not isinstance(annotations, dict):
        raise ValueError("Hypo3D annotation root must be an object keyed by base_scene_id")
    branches: list[dict[str, Any]] = []
    qa_rows: list[dict[str, Any]] = []
    for base_scene_id, changes in annotations.items():
        if not isinstance(changes, list):
            raise ValueError(f"Hypo3D scene {base_scene_id!r} must contain a branch list")
        for branch_index, branch in enumerate(changes):
            if not isinstance(branch, dict):
                raise ValueError(f"Hypo3D branch {base_scene_id}:{branch_index} must be an object")
            branch_row = {"base_scene_id": base_scene_id, "branch_index": branch_index, **branch}
            branches.append(branch_row)
            for qa in branch.get("questions_answers", []):
                qa_rows.append({
                    "base_scene_id": base_scene_id,
                    "branch_index": branch_index,
                    "context_change": branch.get("context_change"),
                    "change_type": branch.get("change_type"),
                    **qa,
                })
    question_types = Counter(str(row.get("question_type")) for row in qa_rows)
    change_types = Counter(str(row.get("change_type")) for row in branches)
    answer_types = Counter(
        "exact_integer" if str(row.get("answer", "")).strip().isdigit()
        else "yes_no" if str(row.get("answer", "")).strip().casefold() in {"yes", "no"}
        else "open_text"
        for row in qa_rows
    )
    candidate_kinds = Counter(
        kind for row in qa_rows
        if (kind := _hypo3d_candidate_kind(str(row.get("question", "")), row.get("answer"))) is not None
    )
    media_groups = set(group_counts)
    scene_keys_by_group = {
        group: {
            Path(row["path"]).stem
            for row in media_rows if Path(row["path"]).parts[0] == group
        }
        for group in media_groups
    }
    missing_scene_group_links = sum(
        base_scene_id not in scene_keys_by_group[group]
        for base_scene_id in annotations
        for group in media_groups
    )
    expected_scene_group_links = len(annotations) * len(media_groups)
    question_ids = [str(row.get("question_id")) for row in qa_rows]
    profile = {
        "dataset": "hypo3d", "source_revision": revision,
        "profile_scope": "official_hypo3d_annotations_and_downloaded_media_snapshot",
        "record_count": len(branches), "qa_count": len(qa_rows), "image_count": len(media_rows), "video_count": 0,
        "world_count": len(annotations), "view_count": len(media_rows), "frame_count": None,
        "time_interval_count": 0, "instance_count": None, "track_count": None,
        "context_change_count": len(branches), "branch_count": len(branches),
        "change_type_distribution": dict(sorted(change_types.items())),
        "question_type_distribution": dict(sorted(question_types.items())),
        "answer_type_distribution": dict(sorted(answer_types.items())),
        "answer_value_distribution": _top_distribution(row.get("answer") for row in qa_rows),
        "missing_field_rate": _missing_rates(
            qa_rows,
            ["base_scene_id", "branch_index", "context_change", "change_type", "question", "question_type", "question_id", "answer"],
        ),
        "duplicate_id_rate": 1 - len(set(question_ids)) / (len(question_ids) or 1),
        "missing_media_rate": (
            len(failures) + missing_scene_group_links
        ) / ((len(rows) + expected_scene_group_links) or 1),
        "missing_scene_group_links": missing_scene_group_links,
        "expected_scene_group_links": expected_scene_group_links,
        "world_qa_density": {
            "mean": len(qa_rows) / (len(annotations) or 1),
            "max": max(Counter(row["base_scene_id"] for row in qa_rows).values(), default=0),
        },
        "duration_distribution": {"count": 0, "min": None, "median": None, "mean": None, "max": None},
        "task_metric_dependency_rate": 1 - sum(candidate_kinds.values()) / (len(qa_rows) or 1),
        "adapter_candidate_count": sum(candidate_kinds.values()),
        "adapter_candidate_rate": sum(candidate_kinds.values()) / (len(qa_rows) or 1),
        "adapter_candidate_kind_distribution": dict(sorted(candidate_kinds.items())),
        "media_group_distribution": dict(sorted(group_counts.items())),
        "annotation_file": "hypo3d.json",
        "annotation_bytes": annotation_path.stat().st_size,
        "annotation_sha256": "sha256:bcfabc2539df7bb3aea9172ae8d3b9022bee72ced5b4af0251213f0cce4e34cb",
        "annotation_google_drive_file_id": "1nTPN5fzjgcjYkHWNKi229Qxt1nUBoLMV",
        "benchmark_annotation_status": "OFFICIAL_ANNOTATIONS_ACQUIRED",
        "media_validation_status": (
            "MEDIA_HASH_AND_ANNOTATION_LINKAGE_VALID"
            if not failures and not missing_scene_group_links else "MEDIA_OR_LINKAGE_PARTIAL"
        ),
    }
    inventory = []
    for question_type, count in sorted(question_types.items()):
        candidate_count = sum(
            _hypo3d_candidate_kind(str(row.get("question", "")), row.get("answer")) is not None
            for row in qa_rows if str(row.get("question_type")) == question_type
        )
        inventory.append({
            "task": question_type,
            "count": count,
            "policy": "deterministic_whitelist" if candidate_count else "reject",
            "reason": f"CERTIFICATE_SAFE_QA={candidate_count};REJECT_METRIC_PATH_COMMONSENSE_AND_UNPARSED={count-candidate_count}",
        })
    examples = qa_rows[:10]
    return profile, inventory, examples


def _profile_ca_vqa(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    from ..adapters.ca_vqa import adapt

    revision = REVISIONS["ca_vqa"]
    staging = root / "data/staging/ca_vqa" / revision / "ca_vqa_val_metadata_v1"
    rows: list[dict[str, Any]] = []
    for task in ("binary", "cardinality", "multichoice"):
        with (staging / f"{task}.jsonl").open("r", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    task_counts = Counter(row["task"] for row in rows)
    adapter_results = [adapt(row, index) for index, row in enumerate(rows)]
    adapter_candidates = sum(result.status == "WAITING_MEDIA" for result in adapter_results)
    numeric_rejects = sum("NUMERIC_DEPENDENCY" in result.reject_codes for result in adapter_results)
    captures = {row["capture_id"] for row in rows}
    frame_bundles = {(row["capture_id"], row["reference_index"]) for row in rows}
    media_paths = {path for row in rows for path in row["media_roles"].values()}
    profile = {
        "dataset": "ca_vqa", "source_revision": revision,
        "profile_scope": "full_validation_metadata_for_allowed_nonmetric_tasks",
        "record_count": len(rows), "qa_count": len(rows), "image_count": len(media_paths),
        "video_count": 0, "world_count": len(captures), "view_count": len(media_paths),
        "frame_count": len(media_paths), "time_interval_count": 0, "instance_count": None,
        "track_count": None, "context_change_count": 0, "branch_count": 0,
        "question_type_distribution": dict(sorted(task_counts.items())),
        "answer_type_distribution": {
            "yes_no": task_counts["binary"], "exact_integer": task_counts["cardinality"],
            "multiple_choice_exact_integer": task_counts["multichoice"],
        },
        "answer_value_distribution": _top_distribution(row["answer"] for row in rows),
        "missing_field_rate": _missing_rates(rows, ["id", "capture_id", "reference_index", "question", "answer", "media_roles"]),
        "duplicate_id_rate": 1 - len({(row["task"], row["id"]) for row in rows}) / (len(rows) or 1),
        "missing_media_rate": 0.0, "reference_frame_bundle_count": len(frame_bundles),
        "world_qa_density": {
            "mean": len(rows) / (len(captures) or 1),
            "max": max(Counter(row["capture_id"] for row in rows).values(), default=0),
        },
        "duration_distribution": {"count": 0, "min": None, "median": None, "mean": None, "max": None},
        "task_metric_dependency_rate": numeric_rejects / (len(rows) or 1),
        "adapter_candidate_count": adapter_candidates,
        "adapter_candidate_rate": adapter_candidates / (len(rows) or 1),
        "excluded_task_families": ["grounding2d", "grounding3d", "regression"],
        "media_validation_status": "PILOT_MEDIA_VALID",
    }
    inventory = [
        {"task": task, "count": task_counts[task], "policy": "template_filter", "reason": "DETERMINISTIC_NONMETRIC_SUBSET_ONLY"}
        for task in ("binary", "cardinality", "multichoice")
    ] + [
        {"task": task, "count": 0, "policy": "reject", "reason": reason}
        for task, reason in (
            ("grounding2d", "NUMERIC_GROUNDING_OUTPUT"),
            ("grounding3d", "NUMERIC_GROUNDING_OUTPUT"),
            ("regression", "NUMERIC_DEPENDENCY"),
        )
    ]
    examples = [
        {key: row[key] for key in ("task", "id", "capture_id", "reference_index", "question", "answer")}
        for row in rows[:10]
    ]
    return profile, inventory, examples


def profile_dataset(dataset: str, *, dry_run: bool, root: Path = ROOT) -> dict[str, Any]:
    handlers = {
        "ca_vqa": _profile_ca_vqa,
        "sti_bench": _profile_sti, "vsi_bench": _profile_vsi, "spar": _profile_spar,
        "omnispatial": _profile_omnispatial,
        "hypo3d": _profile_hypo3d,
    }
    if dataset not in handlers:
        return {"dataset": dataset, "status": "BLOCKED_SOURCE", "reason": "NO_LOCAL_METADATA_PROFILE_HANDLER"}
    if dry_run:
        return {"dataset": dataset, "status": "PLANNED", "outputs": [f"reports/{dataset}/profile.json", f"reports/{dataset}/profile.md", f"reports/{dataset}/task_inventory.csv", f"reports/{dataset}/field_examples.jsonl"]}
    profile, inventory, examples = handlers[dataset](root)
    report_dir = root / "reports" / dataset
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"# {dataset} metadata profile", "", f"- Scope: `{profile['profile_scope']}`",
        f"- QA records: {profile['qa_count']}", f"- Worlds: {profile['world_count']}",
        f"- Adapter candidates before media validation: {profile['adapter_candidate_count']}",
        f"- Missing local media rate: {profile['missing_media_rate']:.1%}",
        f"- Metric/numeric dependency rate: {profile['task_metric_dependency_rate' if 'task_metric_dependency_rate' in profile else 'task_metric_dependency_rate_sample']:.1%}",
        "", (
            "Media references passed the recorded validation gate."
            if profile["missing_media_rate"] == 0
            else "These are metadata-stage candidates only; missing media prevents benchmark acceptance."
        ),
    ]
    (report_dir / "profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (report_dir / "task_inventory.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["task", "count", "policy", "reason"])
        writer.writeheader(); writer.writerows(inventory)
    with (report_dir / "field_examples.jsonl").open("w", encoding="utf-8") as handle:
        for row in examples:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"dataset": dataset, "status": "PROFILED", "profile": profile}
