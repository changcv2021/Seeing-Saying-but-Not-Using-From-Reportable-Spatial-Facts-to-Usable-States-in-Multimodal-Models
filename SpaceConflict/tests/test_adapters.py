from __future__ import annotations

from spaceconflict.adapters.spar import (
    adapt as adapt_spar,
    adapt_appearance_order,
    adapt_qualitative_relation,
)
from spaceconflict.adapters.omnispatial import adapt as adapt_omni
from spaceconflict.adapters.sti_bench import adapt as adapt_sti
from spaceconflict.adapters.vsi_bench import adapt as adapt_vsi
from spaceconflict.adapters.ca_vqa import adapt as adapt_ca
from spaceconflict.adapters.pipeline import _valid_media_report


def test_sti_relation_reconstructs_source_answer() -> None:
    row = {
        "Video": "000001.mp4", "Source": "Omni6DPose", "Task": "Spatial Relation",
        "QType": "Single Choice", "Question": "What is the positional relationship of the red suitcase relative to the teddy bear?",
        "Prompt": "", "time_start": 0.0, "time_end": 0.0,
        "Candidates": {"A": "Left", "B": "Right", "C": "Front", "D": "Back", "E": "Up"},
        "Answer": "C", "Answer Detail": "Front", "ID": 4, "scene": "desktop",
    }
    result = adapt_sti(row, 0)
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["predicate"] == "FRONT_OF"
    assert result.reconstructed_answer == "C"
    assert result.reconstruction_pass
    assert result.blocking_reject_codes == ["MISSING_MEDIA"]


def test_sti_numeric_task_is_rejected() -> None:
    row = {
        "Video": "x.mp4", "Source": "Waymo", "Task": "Trajectory Description", "QType": "Single Choice",
        "Question": "What is the trajectory?", "Prompt": "", "time_start": 0.0, "time_end": 1.0,
        "Candidates": {"A": "move forward 1m"}, "Answer": "A", "Answer Detail": "move forward 1m", "ID": 1, "scene": "outdoor",
    }
    result = adapt_sti(row, 0)
    assert result.status == "REJECTED"
    assert result.reject_codes == ["NUMERIC_DEPENDENCY"]


def test_sti_malformed_official_options_are_rejected() -> None:
    row = {
        "Video": "x.mp4", "Source": "Waymo", "Task": "Spatial Relation", "QType": "Single Choice",
        "Question": "Where is the boy relative to the woman?", "Prompt": "", "time_start": 1.0, "time_end": 2.0,
        "Candidates": {"A": "Front Back Right Left Up", "B": None, "C": None, "D": None, "E": None},
        "Answer": "B", "Answer Detail": "Back", "ID": 5, "scene": "outdoor",
    }
    result = adapt_sti(row, 0)
    assert result.status == "REJECTED"
    assert result.reject_codes == ["SOURCE_RECONSTRUCTION_FAIL"]


def test_vsi_count_reconstructs() -> None:
    row = {"id": 0, "dataset": "arkitscenes", "scene_name": "41069025", "question_type": "object_counting", "question": "How many table(s) are in this room?", "ground_truth": "4", "options": None}
    result = adapt_vsi(row, 0)
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["predicate"] == "COUNT"
    assert result.facts[0]["value"] == 4
    assert result.reconstruction_pass


def test_vsi_direction_resolves_option_semantics() -> None:
    row = {"id": 1, "dataset": "arkitscenes", "scene_name": "41069025", "question_type": "object_rel_direction_easy", "question": "If I am standing by the stove and facing the sofa, is the tv to the left or the right of the sofa?", "ground_truth": "A", "options": ["A. left", "B. right"]}
    result = adapt_vsi(row, 0)
    assert result.facts[0]["predicate"] == "LEFT_OF"
    assert result.reconstructed_answer == "A"
    assert result.reconstruction_pass


def test_vsi_appearance_builds_strict_chain() -> None:
    row = {"id": 2, "dataset": "scannetpp", "scene_name": "s", "question_type": "obj_appearance_order", "question": "What will be the first-time appearance order of the following categories in the video: cup, door, heater, ceiling light?", "ground_truth": "A", "options": ["A. cup, door, heater, ceiling light", "B. door, cup, heater, ceiling light"]}
    result = adapt_vsi(row, 0)
    assert [fact["predicate"] for fact in result.facts] == ["BEFORE", "BEFORE", "BEFORE"]
    assert result.reconstruction_pass


def test_spar_relation_bundle_reconstructs() -> None:
    row = {
        "id": 800, "img_type": "multi_view", "format_type": "select", "task": "obj_spatial_relation_oc_mv", "source": "scannet",
        "image": [{}, {}, {}],
        "question": "Where is sink (bbox)?\nA. left, above, behind\nB. right, below, front\nC. left, below, front\nD. right, above, front\nYour answer can only include one option.",
        "answer": "B",
    }
    result = adapt_spar(row, 0)
    assert [fact["predicate"] for fact in result.facts] == ["RIGHT_OF", "BELOW", "FRONT_OF"]
    assert result.reconstruction_pass
    assert "BLOCKED_LICENSE" in result.blocking_reject_codes
    assert "UNRESOLVED_WORLD_ID" in result.blocking_reject_codes


def test_spar_7m_appearance_order_preserves_scene_and_ordered_media() -> None:
    row = {
        "id": "scene01_7", "qa_type": "appearance_order", "qa_format": "fill",
        "question": (
            "Frame-1: <image>\nFrame-2: <image>\n"
            "Track first appearances of chair, table, lamp, and door."
        ),
        "answer": "chair, table, lamp, door",
        "image": [
            "spar/scannet/images/scene01/frame0.jpg",
            "spar/scannet/images/scene01/frame1.jpg",
        ],
        "split": "train", "base_dataset": "scannet", "scene_id": "scene01",
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
    }
    result = adapt_appearance_order(row, 0)
    assert result.status == "SOURCE_REFERENCE_VALID"
    assert result.global_world_id == "scannet:scene01"
    assert [item["predicate"] for item in result.facts] == ["BEFORE", "BEFORE", "BEFORE"]
    assert result.reconstruction_pass
    assert result.media_locator["frame_count"] == 2
    assert result.answer_semantics["frame_grounding_status"] == "NOT_PROVIDED_BY_SOURCE_ANNOTATION"


def test_spar_7m_relation_excludes_metric_depth_language() -> None:
    row = {
        "id": "scene01_8", "qa_type": "obj_spatial_relation_oo", "qa_format": "sentence",
        "question": "<image>\nWhere is the red bbox relative to the blue bbox?",
        "answer": "The red object is to the left and below. It appears closer.",
        "image": ["spar/scannet/images/scene01/frame.jpg"], "split": "train",
        "red_bbox": [[1, 2, 3, 4]], "blue_bbox": [[5, 6, 7, 8]],
        "green_bbox": [], "yellow_bbox": [], "bbox_img_idx": [[0], [0]],
        "base_dataset": "scannet", "scene_id": "scene01",
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
    }
    result = adapt_qualitative_relation(row, 0)
    assert result.status == "SOURCE_REFERENCE_VALID"
    assert [item["predicate"] for item in result.facts] == ["LEFT_OF", "BELOW"]
    assert result.reconstruction_pass
    assert result.answer_semantics["excluded_source_dimensions"] == [
        "closer_farther_metric_depth_language"
    ]


def test_spar_7m_object_camera_relation_keeps_front_axis() -> None:
    row = {
        "id": "scene01_9", "qa_type": "obj_spatial_relation_oc_mv", "qa_format": "sentence",
        "question": "<image>\n<image>\n<image>\nWhere is the red bbox?",
        "answer": "The red object is right and above. It appears to the front.",
        "image": [f"spar/scannet/images/scene01/frame{i}.jpg" for i in range(3)],
        "split": "train", "red_bbox": [[1, 2, 3, 4]], "blue_bbox": [],
        "green_bbox": [], "yellow_bbox": [], "bbox_img_idx": [[0]],
        "base_dataset": "scannet", "scene_id": "scene01",
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
    }
    result = adapt_qualitative_relation(row, 0)
    assert [item["predicate"] for item in result.facts] == ["RIGHT_OF", "ABOVE", "FRONT_OF"]
    assert result.reconstruction_pass


def test_spar_7m_relation_reconstructs_choice_letter() -> None:
    row = {
        "id": "scene01_10", "qa_type": "obj_spatial_relation_oc_mv", "qa_format": "choice",
        "question": (
            "<image>\n<image>\n<image>\nWhere is the red bbox?\n"
            "A. left, below, front\nB. right, , behind\n"
            "C. right, below, \nD. right, below, front\n"
            "Your answer can only include one option."
        ),
        "answer": "D", "image": [f"spar/scannet/images/scene01/frame{i}.jpg" for i in range(3)],
        "split": "train", "red_bbox": [[1, 2, 3, 4]], "blue_bbox": [],
        "green_bbox": [], "yellow_bbox": [], "bbox_img_idx": [[2]],
        "base_dataset": "scannet", "scene_id": "scene01",
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
    }
    result = adapt_qualitative_relation(row, 0)
    assert [item["predicate"] for item in result.facts] == ["RIGHT_OF", "BELOW", "FRONT_OF"]
    assert result.reconstructed_answer == "D"
    assert result.reconstruction_pass


def test_spar_7m_relation_rejects_choice_ambiguous_after_metric_projection() -> None:
    row = {
        "id": "scene01_11", "qa_type": "obj_spatial_relation_oo", "qa_format": "choice",
        "question": (
            "<image>\nWhere is red relative to blue?\n"
            "A. left, closer\nB. left, farther\nC. right, closer\nD. above, closer"
        ),
        "answer": "A", "image": ["spar/scannet/images/scene01/frame.jpg"],
        "split": "train", "red_bbox": [[1, 2, 3, 4]], "blue_bbox": [[5, 6, 7, 8]],
        "green_bbox": [], "yellow_bbox": [], "bbox_img_idx": [[0], [0]],
        "base_dataset": "scannet", "scene_id": "scene01",
        "source_revision": "0fe664cbada1e7c1173fd743e0f781882eebf777",
    }
    result = adapt_qualitative_relation(row, 0)
    assert result.status == "REJECTED"
    assert result.reject_codes == ["SOURCE_RECONSTRUCTION_FAIL"]
    assert not result.reconstruction_pass


def test_omnispatial_direction_bundle_is_claim_local() -> None:
    row = {
        "id": "2_0", "question": "From the player's perspective, where is the ball?",
        "options": ["right", "left rear", "front", "below"], "answer": 1,
        "task_type": "Perspective_Taking", "sub_task_type": "Allocentric",
    }
    result = adapt_omni(row, 0)
    assert result.status == "WAITING_MEDIA"
    assert [fact["predicate"] for fact in result.facts] == ["LEFT_OF", "BEHIND"]
    assert result.global_world_id == "omnispatial:perspective_taking:2"
    assert result.reconstruction_pass


def test_omnispatial_malformed_options_are_rejected() -> None:
    row = {
        "id": "0_0", "question": "Which cube?", "options": [], "answer": 2,
        "task_type": "Complex_Logic", "sub_task_type": "Geometric_Reasoning",
    }
    result = adapt_omni(row, 0)
    assert result.status == "REJECTED"
    assert result.reject_codes == ["MALFORMED_SOURCE_OPTIONS"]


def _ca_row(task: str, question: str, answer: str) -> dict:
    return {
        "task": task, "id": "45260857_00050_6", "capture_id": "45260857",
        "reference_index": "00050", "qa_index": "6", "question": question, "answer": answer,
        "media_roles": {
            "reference_frame": "images/r", "support_frame_1": "images/s1",
            "support_frame_2": "images/s2", "support_frame_3": "images/s3",
            "support_frame_4": "images/s4",
        },
        "source_record_hash": "sha256:" + "1" * 64,
    }


def test_ca_binary_preserves_explicit_negative_visibility() -> None:
    result = adapt_ca(_ca_row("binary", "Is there a bed in the image?", "No"), 0)
    assert result.status == "WAITING_MEDIA"
    assert result.global_world_id == "arkitscenes:45260857"
    assert result.facts[0]["predicate"] == "VISIBLE_IN_FRAME"
    assert result.facts[0]["subject"] == "class:bed"
    assert result.facts[0]["polarity"] == "negative"
    assert result.reconstructed_answer == "No"
    assert result.reconstruction_pass


def test_ca_binary_qualitative_relation_reconstructs() -> None:
    result = adapt_ca(_ca_row("binary", "Is the bottle behind of the book?", "Yes"), 0)
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["predicate"] == "BEHIND"
    assert result.facts[0]["polarity"] == "positive"
    assert result.reconstruction_pass


def test_ca_to_the_right_does_not_absorb_preposition_into_subject() -> None:
    result = adapt_ca(
        _ca_row("binary", "Is the glass object to the right of the metal object?", "Yes"), 0
    )
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["subject"] == "mention:glass_object"
    assert result.facts[0]["predicate"] == "RIGHT_OF"
    assert result.facts[0]["object"] == "mention:metal_object"


def test_ca_cardinality_reconstructs_exact_count() -> None:
    result = adapt_ca(_ca_row("cardinality", "How many door bells are in the image?", "1"), 0)
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["predicate"] == "COUNT"
    assert result.facts[0]["subject"] == "class:door_bells"
    assert result.facts[0]["value"] == 1
    assert result.reconstruction_pass


def test_ca_multichoice_requires_unique_semantic_option() -> None:
    valid = adapt_ca(_ca_row(
        "multichoice",
        "How many chairs are in the image?\nA. 1\nB. 2\nC. 0\nD. 4\nAnswer with the option's letter from the given choices directly.",
        "B",
    ), 0)
    assert valid.status == "WAITING_MEDIA"
    assert valid.facts[0]["value"] == 2
    duplicate = adapt_ca(_ca_row(
        "multichoice",
        "How many chairs are in the image?\nA. 1\nB. 2\nC. 0\nD. 2\nAnswer with the option's letter from the given choices directly.",
        "B",
    ), 0)
    assert duplicate.status == "REJECTED"
    assert duplicate.reject_codes == ["SOURCE_RECONSTRUCTION_FAIL"]


def test_ca_multichoice_qualitative_relation_reconstructs_yes() -> None:
    result = adapt_ca(_ca_row(
        "multichoice",
        "Is the bottle behind of the book?\nA. yes\nB. no\nAnswer with the option's letter from the given choices directly.",
        "A",
    ), 0)
    assert result.status == "WAITING_MEDIA"
    assert result.facts[0]["subject"] == "mention:bottle"
    assert result.facts[0]["predicate"] == "BEHIND"
    assert result.facts[0]["object"] == "mention:book"
    assert result.facts[0]["polarity"] == "positive"
    assert result.reconstruction_pass


def test_ca_train_record_preserves_content_world_and_tfrecord_provenance() -> None:
    row = {
        "task": "binary", "id": "train:binary:00000:0:0",
        "capture_id": "bundle_abc", "reference_index": "record_0", "qa_index": "0",
        "question": "Is there a chair in the image?", "answer": "Yes",
        "media_roles": {"reference_frame": "tfrecord://binary/00000#record=0&images=0"},
        "source_record_hash": "sha256:" + "1" * 64,
        "global_world_id": "ca_vqa_train:bundle_abc",
        "adapter_version": "ca_vqa_train_tfrecord_v1",
        "source_locator": {"shard": 0, "record_index": 0, "qa_index": 0},
        "source_media_field_paths": ["tfrecord.images[0]"],
        "blocking_reject_codes": [],
    }
    result = adapt_ca(row, 0)
    assert result.status == "WAITING_MEDIA"
    assert result.global_world_id == "ca_vqa_train:bundle_abc"
    assert result.adapter_version == "ca_vqa_train_tfrecord_v1"
    assert result.blocking_reject_codes == []
    assert result.media_locator["source_locator"]["record_index"] == 0
    assert result.facts[0]["provenance"]["source_field_paths"] == [
        "id", "question", "answer", "tfrecord.images[0]",
    ]


def test_media_report_selection_requires_valid_status(tmp_path) -> None:
    report_dir = tmp_path / "reports" / "ca_vqa"
    report_dir.mkdir(parents=True)
    (report_dir / "media_validation.z_invalid.json").write_text(
        '{"status":"REJECTED"}\n', encoding="utf-8"
    )
    valid = report_dir / "media_validation.a_valid.json"
    valid.write_text('{"status":"PILOT_MEDIA_VALID"}\n', encoding="utf-8")
    assert _valid_media_report("ca_vqa", tmp_path) == valid
