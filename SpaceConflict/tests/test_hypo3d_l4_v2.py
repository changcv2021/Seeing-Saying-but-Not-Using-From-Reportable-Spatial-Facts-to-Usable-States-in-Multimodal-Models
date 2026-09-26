from __future__ import annotations

import json
import os
import pickle
from pathlib import Path

from jsonschema import Draft202012Validator

from spaceconflict.hypo3d_l4.certificates import classify_strength, validate_certificate_separation
from spaceconflict.hypo3d_l4.count_claims import build_count_pair
from spaceconflict.hypo3d_l4.existence_claims import (
    build_existence_calibration_pair, select_existence_calibration_pairs,
)
from spaceconflict.hypo3d_l4.grounding_metadata import audit_grounding_metadata, iter_top_level_object
from spaceconflict.hypo3d_l4.geometry_relations import bbox_intervals, strict_separated_relation
from spaceconflict.hypo3d_l4.common import iter_branch_records, normalize_change_type
from spaceconflict.hypo3d_l4.normalize_qa import normalize_post_qa
from spaceconflict.hypo3d_l4.object_catalog import (
    UNVERIFIED_MIRROR_SOURCE_TYPE, extract_embodiedscan_object_catalog,
)
from spaceconflict.hypo3d_l4.parse_changes import parse_change
from spaceconflict.hypo3d_l4.pipeline import build_foundation_report, resolve_targets
from spaceconflict.hypo3d_l4.prestates import (
    build_count_prestate, explicit_quantity, ref_mentions_class,
    unique_catalog_class_mentioned,
)
from spaceconflict.hypo3d_l4.resolve_targets import resolve_intervention_targets
from spaceconflict.hypo3d_l4.restricted_pickle import load_restricted_annotation_pickle
from spaceconflict.hypo3d_l4.transition_rules import (
    addition_count, removal_count, replacement_identity,
)
from spaceconflict.hypo3d_l4.verification import (
    verify_count_claim, verify_count_pair_accessibly, verify_existence_claim,
)
from spaceconflict.hypo3d_l4.verify_l4 import _forbidden_keys, verification_status


ROOT = Path(__file__).resolve().parents[1]


def _record(change_type: str, context: str, question: str = "How many chairs remain now?", answer: str = "2") -> dict:
    annotations = {
        "scene0001_00": [{
            "change_type": change_type,
            "context_change": context,
            "questions_answers": [{
                "question_id": "q1", "question_type": "Semantic",
                "question": question, "answer": answer,
            }],
        }]
    }
    return next(iter_branch_records(annotations))


def test_change_type_and_stable_ids() -> None:
    assert normalize_change_type("Object Movement Change") == "MOVEMENT"
    first = _record("Object Removal Change", "The chair beside the door has been removed.")
    second = _record("Object Removal Change", "The chair beside the door has been removed.")
    assert first["change_id"] == second["change_id"]
    assert first["global_world_id"] == "hypo3d:scene0001_00"


def test_official_9dof_boxes_prove_only_strict_axis_separation() -> None:
    left = {"bbox_3d": [0, 0, 0, 1, 1, 1, 0, 0, 0]}
    right = {"bbox_3d": [2, 0, 0, 1, 1, 1, 0, 0, 0]}
    overlapping = {"bbox_3d": [0.25, 0, 0, 1, 1, 1, 0, 0, 0]}
    assert bbox_intervals(left["bbox_3d"])[0] == (-0.5, 0.5)
    assert strict_separated_relation(left, "LEFT_OF", right)
    assert strict_separated_relation(right, "RIGHT_OF", left)
    assert not strict_separated_relation(left, "LEFT_OF", overlapping)
    # A 90-degree Z rotation swaps the x/y extents under the official ZXY convention.
    rotated = bbox_intervals([0, 0, 0, 2, 4, 1, 1.5707963267948966, 0, 0])
    assert abs(rotated[0][0] + 2.0) < 1e-9 and abs(rotated[0][1] - 2.0) < 1e-9


def test_five_change_parsers_are_structural_not_identity_resolvers() -> None:
    cases = [
        ("Object Removal Change", "The chair beside the door has been removed.", "REMOVAL"),
        ("Object Addition Change", "A lamp has been added to the right of the sofa.", "ADDITION"),
        ("Object Replacement Change", "The trash can has been replaced by a floor lamp.", "REPLACEMENT"),
        ("Object Movement Change", "The desk has been moved to the right of the refrigerator.", "MOVEMENT"),
        ("Attribute Change", "The door has been changed from closed to open.", "ATTRIBUTE"),
    ]
    for raw_type, text, expected in cases:
        record = _record(raw_type, text)
        intervention, reject = parse_change(record)
        assert reject is None
        assert intervention is not None
        assert intervention["type"] == expected
        assert intervention["targets"] == []  # parsing text never manufactures a resolved ID


def test_count_and_direction_oracles_reconstruct_source_answer() -> None:
    count_record = _record(
        "Object Addition Change", "A coffee machine has been added.",
        "After the addition, what is the new count of coffee machines?", "4",
    )
    oracle, reject = normalize_post_qa(count_record)
    assert reject is None
    assert oracle is not None
    assert oracle["normalized_atoms"][0]["predicate"] == "COUNT"
    assert oracle["normalized_atoms"][0]["value"] == 4
    direction_record = _record(
        "Object Movement Change", "The table has been moved.",
        "How is the refrigerator relative to the table?", "Back left",
    )
    oracle, reject = normalize_post_qa(direction_record)
    assert reject is None
    assert oracle is not None
    assert [atom["predicate"] for atom in oracle["normalized_atoms"]] == ["BEHIND", "LEFT_OF"]
    assert oracle["model_input_visible"] is False


def test_yes_no_attribute_question_is_not_mislabeled_as_existence() -> None:
    record = _record(
        "Object Addition Change", "A poster has been added.",
        "Does the added poster have a higher placement position than the flowerpot?", "Yes",
    )
    oracle, reject = normalize_post_qa(record)
    assert oracle is None
    assert reject == "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"


def test_yes_no_relation_and_path_questions_are_not_existence_oracles() -> None:
    for question in (
        "Is there a couch to the right of the TV stand?",
        "Is there an object that blocks the direct path from the ottoman to the TV stand?",
        "Are there any chairs near the bag?",
    ):
        record = _record("Object Movement Change", "The chair has been moved.", question, "No")
        oracle, reject = normalize_post_qa(record)
        assert oracle is None
        assert reject == "REJECT_POST_ORACLE_SCOPE_AMBIGUOUS"


def test_pure_yes_no_existence_remains_reversible() -> None:
    record = _record(
        "Object Removal Change", "The chair has been removed.",
        "Is the chair still present in the scene?", "No",
    )
    oracle, reject = normalize_post_qa(record)
    assert reject is None and oracle is not None
    assert oracle["normalized_atoms"] == [{
        "subject": "chair", "predicate": "EXISTS_IN_WORLD", "object": None,
        "value": False, "scope": "whole_scene", "state": "post",
        "branch_id": record["branch_id"], "reference_frame": None,
    }]


def test_authorized_count_and_replacement_rules() -> None:
    assert removal_count("chair", 3).value == 2
    assert addition_count("lamp", 2).value == 3
    replacement = replacement_identity("old:trashcan", "new:lamp")
    assert [result.value for result in replacement] == [False, True, False]


def test_core_and_calibration_are_disjoint() -> None:
    assert classify_strength(
        full_label="SUPPORTED", scene_only_label="UNKNOWN", change_only_label="UNKNOWN",
        necessary_pre_fact_ids=["pre_count_chair_3"],
    ) == ("L4_CORE", None)
    assert classify_strength(
        full_label="SUPPORTED", scene_only_label="UNKNOWN", change_only_label="SUPPORTED",
        necessary_pre_fact_ids=[],
    ) == ("L4_CALIBRATION", None)


def test_hidden_oracle_cannot_leak_into_accessible_reasoning() -> None:
    certificate = {
        "strength_slice": "L4_CORE",
        "label_provenance_certificate": {"post_oracle_id": "post_q1"},
        "accessible_reasoning_certificate": {
            "proof_nodes": [{"id": "oracle", "type": "SOURCE_POST_ORACLE"}],
        },
        "dependency_checks": {
            "scene_only_label": "UNKNOWN", "change_only_label": "UNKNOWN",
        },
    }
    errors = validate_certificate_separation(certificate)
    assert "ORACLE_LEAK_IN_ACCESSIBLE_REASONING:SOURCE_POST_ORACLE" in errors


def test_target_resolution_never_guesses_without_annotations() -> None:
    record = _record("Object Removal Change", "The chair beside the door has been removed.")
    intervention, reject = parse_change(record)
    assert reject is None and intervention is not None
    parsed = {
        "scene_id": record["scene_id"], "change_id": record["change_id"],
        "question_id": record["question_id"], "branch_id": record["branch_id"],
        "source_hash": record["source_hash"], "intervention": intervention,
    }
    resolution, reject = resolve_intervention_targets(parsed, None)
    assert resolution is None
    assert reject == "REJECT_TARGET_ANNOTATION_MISSING"


def test_target_resolution_accepts_only_a_unique_head_class_in_scene() -> None:
    record = _record("Object Removal Change", "The black chair beside the door has been removed.")
    intervention, reject = parse_change(record)
    assert reject is None and intervention is not None
    parsed = {
        "scene_id": record["scene_id"], "change_id": record["change_id"],
        "question_id": record["question_id"], "branch_id": record["branch_id"],
        "source_hash": record["source_hash"], "intervention": intervention,
    }
    unique_catalog = {"source_type": "EMBODIEDSCAN_OFFICIAL_ANNOTATION", "scenes": {
        record["scene_id"]: {"objects": [
            {"object_id": "chair_0", "class": "chair", "aliases": ["chair"]},
            {"object_id": "door_0", "class": "door", "aliases": ["door"]},
        ]}
    }}
    resolution, resolution_reject = resolve_intervention_targets(parsed, unique_catalog)
    assert resolution_reject is None and resolution is not None
    assert resolution["resolved_targets"][0]["resolved_entity_id"] == "chair_0"
    assert resolution["resolved_targets"][0]["resolution_tier"] == "UNIQUE_CLASS_IN_SCENE"

    ambiguous_catalog = json.loads(json.dumps(unique_catalog))
    ambiguous_catalog["scenes"][record["scene_id"]]["objects"].append(
        {"object_id": "chair_1", "class": "chair", "aliases": ["chair"]}
    )
    unresolved, ambiguous_reject = resolve_intervention_targets(parsed, ambiguous_catalog)
    assert unresolved is None
    assert ambiguous_reject == "REJECT_TARGET_AMBIGUOUS"


def test_catalog_target_resolution_uses_a_new_immutable_artifact_version(tmp_path: Path) -> None:
    parsed = tmp_path / "parsed.jsonl"
    catalog = tmp_path / "catalog.json"
    without_catalog = resolve_targets(
        parsed_changes=parsed, object_catalog=None, output_dir=tmp_path,
        dry_run=True, resume=False, limit=None, scene_id=None, change_id=None,
        question_id=None,
    )
    with_catalog = resolve_targets(
        parsed_changes=parsed, object_catalog=catalog, output_dir=tmp_path,
        dry_run=True, resume=False, limit=None, scene_id=None, change_id=None,
        question_id=None,
    )
    assert without_catalog["output"].endswith("target_resolutions.v2.jsonl")
    assert with_catalog["output"].endswith("target_resolutions.v2_2.jsonl")


def test_foundation_report_writes_json_and_markdown(tmp_path: Path) -> None:
    inputs = []
    for name in ("branches.jsonl", "parsed.jsonl", "oracles.jsonl", "targets.jsonl"):
        path = tmp_path / name
        path.write_text("", encoding="utf-8")
        inputs.append(path)
    result = build_foundation_report(
        branch_index=inputs[0], parsed_changes=inputs[1], post_oracles=inputs[2],
        target_resolutions=inputs[3], output_dir=tmp_path / "report", dry_run=False,
        resume=False,
    )
    assert result["status"] == "FOUNDATION_VALID_PRESTATE_BLOCKED"
    assert (tmp_path / "report/foundation_status.v2.json").is_file()
    assert (tmp_path / "report/foundation_status.v2.md").is_file()


def test_addition_new_entity_is_branch_local_without_fake_target_id() -> None:
    record = _record("Object Addition Change", "A floor lamp has been added.")
    intervention, reject = parse_change(record)
    assert reject is None and intervention is not None
    parsed = {
        "scene_id": record["scene_id"], "change_id": record["change_id"],
        "question_id": record["question_id"], "branch_id": record["branch_id"],
        "source_hash": record["source_hash"], "intervention": intervention,
    }
    resolution, reject = resolve_intervention_targets(parsed, None)
    assert reject is None
    assert resolution is not None
    assert resolution["status"] == "PASS_NEW_ENTITY_ONLY"


def test_new_json_schemas_are_well_formed() -> None:
    for name in (
        "hypo3d_branch_record.schema.json", "post_state_oracle.schema.json",
        "local_transition_micrograph.schema.json", "l4_certificate_v2.schema.json",
        "hypo3d_object_catalog.schema.json",
        "hypo3d_grounding_inventory.schema.json",
    ):
        schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_official_embodiedscan_info_can_be_reduced_to_object_catalog(tmp_path: Path) -> None:
    source = tmp_path / "embodiedscan_infos_train.pkl"
    payload = {
        "metainfo": {"categories": {"chair": 0, "table": 1}},
        "data_list": [{
            "sample_idx": "scannet/scene0001_00",
            "instances": [
                {"bbox_label_3d": 0, "bbox_id": 7, "bbox_3d": [1, 2, 3, 4, 5, 6, 0, 0, 0]},
                {"bbox_label_3d": 0}, {"bbox_label_3d": 1},
            ],
        }],
    }
    source.write_bytes(pickle.dumps(payload))
    catalog = extract_embodiedscan_object_catalog([source], selected_scene_ids={"scene0001_00"})
    objects = catalog["scenes"]["scene0001_00"]["objects"]
    assert [obj["class"] for obj in objects] == ["chair", "chair", "table"]
    assert objects[0]["object_id"] != objects[1]["object_id"]
    assert objects[0]["source_bbox_id"] == 7
    assert objects[0]["bbox_3d"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 0.0, 0.0, 0.0]
    assert objects[0]["bbox_3d_format"] == "XYZ_DXDYDZ_EULER_ZXY_RADIANS"
    provisional = extract_embodiedscan_object_catalog(
        [source], selected_scene_ids={"scene0001_00"},
        source_type=UNVERIFIED_MIRROR_SOURCE_TYPE,
    )
    assert provisional["source_type"] == "UNVERIFIED_THIRD_PARTY_MIRROR"


def test_restricted_annotation_pickle_accepts_numpy_but_rejects_code_execution(tmp_path: Path) -> None:
    import numpy as np

    safe = tmp_path / "safe.pkl"
    safe.write_bytes(pickle.dumps({"array": np.asarray([[1, 2], [3, 4]], dtype=np.float32)}))
    loaded = load_restricted_annotation_pickle(safe)
    assert loaded["array"].tolist() == [[1.0, 2.0], [3.0, 4.0]]

    protocol_two = tmp_path / "protocol_two_bytes.pkl"
    protocol_two.write_bytes(pickle.dumps({"bytes": b"EmbodiedScan"}, protocol=2))
    assert load_restricted_annotation_pickle(protocol_two)["bytes"] == b"EmbodiedScan"

    marker = tmp_path / "must_not_exist"

    class Exploit:
        def __reduce__(self):
            return os.system, (f"touch {marker}",)

    malicious = tmp_path / "malicious.pkl"
    malicious.write_bytes(pickle.dumps(Exploit()))
    try:
        load_restricted_annotation_pickle(malicious)
    except pickle.UnpicklingError as error:
        assert "forbidden pickle global" in str(error)
    else:
        raise AssertionError("malicious pickle unexpectedly loaded")
    assert not marker.exists()


def test_grounding_metadata_is_streamed_and_kept_out_of_transition_truth(tmp_path: Path) -> None:
    metadata = tmp_path / "embodiedscan_infos_full_updated.json"
    metadata.write_text(json.dumps({
        "scannet/scene0001_00": {
            "axis_align_matrix": [1, 0, 0, 1],
            "scannet/posed_images/scene0001_00/00000.jpg": {
                "pose": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                "depth": "scannet/posed_images/scene0001_00/00000.png",
            }
        },
        "3rscan/other-scene": {},
    }), encoding="utf-8")
    assert [key for key, _ in iter_top_level_object(metadata, chunk_size=17)] == [
        "scannet/scene0001_00", "3rscan/other-scene",
    ]
    annotations = tmp_path / "hypo3d.json"
    annotations.write_text(json.dumps({"scene0001_00": []}), encoding="utf-8")
    result = audit_grounding_metadata(
        metadata_path=metadata, annotation_path=annotations, output_dir=tmp_path / "report",
        dry_run=False, resume=False,
    )
    assert result["status"] == "GROUNDING_AUDITED"
    inventory = json.loads((tmp_path / "report/grounding_inventory.v2_1.json").read_text())
    assert inventory["covered_scene_count"] == 1
    assert inventory["truth_boundary"].endswith("NOT_OBJECT_OR_TRANSITION_TRUTH")


def test_addition_count_prestate_replays_without_oracle_as_accessible_premise() -> None:
    record = _record(
        "Object Addition Change", "Two black chairs have been added to the room.",
        "How many chairs are now in the room?", "3",
    )
    intervention, reject = parse_change(record)
    oracle, oracle_reject = normalize_post_qa(record)
    assert reject is None and oracle_reject is None
    assert intervention is not None and oracle is not None
    parsed = {
        "scene_id": record["scene_id"], "change_id": record["change_id"],
        "question_id": record["question_id"], "branch_id": record["branch_id"],
        "source_hash": record["source_hash"], "intervention": intervention,
    }
    resolution, target_reject = resolve_intervention_targets(parsed, None)
    assert target_reject is None and resolution is not None
    catalog = {
        "scenes": {record["scene_id"]: {
            "source_scene_id": "scannet/scene0001_00",
            "objects": [{"object_id": "chair_0", "class": "chair"}], "relations": [],
        }}
    }
    bundle, prestate_reject = build_count_prestate(
        branch=record, parsed=parsed, oracle=oracle, resolution=resolution, catalog=catalog,
    )
    assert prestate_reject is None and bundle is not None
    assert explicit_quantity("Two black chairs") == 2
    assert bundle["accessible_transition"]["derived_post_count"] == 3
    assert bundle["accessible_transition"]["uses_post_oracle_as_premise"] is False
    assert bundle["label_provenance_check"]["status"] == "PASS"
    pair = build_count_pair(bundle)
    assert pair["validation"]["final_status"] == "AUTO_ACCEPTED"
    assert pair["validation"]["independent_verifier"]["status"] == "PASS"

    assert pair["validation"]["independent_verifier"]["scene_only_label"] == "UNKNOWN"
    assert pair["validation"]["independent_verifier"]["change_only_label"] == "UNKNOWN"
    assert set(pair["validation"]["independent_verifier"]["necessary_pre_fact_ablations"].values()) == {"UNKNOWN"}
    assert pair["edit"]["changed_slots"] == ["count_value"]
    assert pair["supported_claim"]["graph"]["value"] == 3
    assert pair["contradictory_claim"]["graph"]["value"] == 1
    certificate_schema = json.loads((ROOT / "schemas/l4_certificate_v2.schema.json").read_text())
    Draft202012Validator(certificate_schema).validate(pair["certificate"])


def test_exact_class_count_annotation_overrides_partial_object_nodes() -> None:
    record = _record(
        "Object Addition Change", "One whiteboard has been added to the room.",
        "How many whiteboards are now in the room?", "3",
    )
    intervention, reject = parse_change(record)
    oracle, oracle_reject = normalize_post_qa(record)
    assert reject is None and oracle_reject is None
    assert intervention is not None and oracle is not None
    parsed = {
        "scene_id": record["scene_id"], "change_id": record["change_id"],
        "question_id": record["question_id"], "branch_id": record["branch_id"],
        "source_hash": record["source_hash"], "intervention": intervention,
    }
    resolution, target_reject = resolve_intervention_targets(parsed, None)
    assert target_reject is None and resolution is not None
    catalog = {
        "scenes": {record["scene_id"]: {
            "source_scene_id": "scannet/scene0001_00",
            "objects": [{"object_id": "whiteboard_0", "class": "whiteboard"}],
            "relations": [],
            "exact_class_counts": {"whiteboard": 2},
            "exact_class_count_sources": {
                "whiteboard": "ReferIt3D/Nr3D@test:scene0001_00:whiteboard"
            },
        }}
    }
    bundle, prestate_reject = build_count_prestate(
        branch=record, parsed=parsed, oracle=oracle, resolution=resolution, catalog=catalog,
    )
    assert prestate_reject is None and bundle is not None
    fact = bundle["pre_state_subgraph"]["facts"][0]
    assert fact["value"] == 2
    assert fact["origin_type"] == "SOURCE_EXACT_CLASS_COUNT_ANNOTATION"
    assert fact["source_annotation_ref"].startswith("ReferIt3D/Nr3D@")


def test_exact_class_count_accepts_only_neutral_present_suffix() -> None:
    from spaceconflict.hypo3d_l4.prestates import count_annotated_class

    scene = {
        "objects": [],
        "exact_class_counts": {"chair": 2, "monitor": 3, "table": 4},
    }
    assert count_annotated_class(scene, "chairs present") == ("chair", 2)
    assert count_annotated_class(scene, "monitors present") == ("monitor", 3)
    assert count_annotated_class(scene, "round tables") == (None, None)


def test_independent_count_verifier_has_an_accessible_input_barrier() -> None:
    claim = {"subject": "chair", "predicate": "COUNT", "value": 3, "state": "post", "scope": "whole_scene"}
    fact = {"fact_id": "pre_chair_1", "subject": "chair", "predicate": "COUNT", "value": 1}
    transition = {"rule_id": "ADDITION_INCREMENTS_CLASS_COUNT", "delta": 2}
    assert verify_count_claim(pre_facts=[fact], transition=transition, claim=claim)["label"] == "SUPPORTED"
    assert verify_count_claim(pre_facts=[fact], transition=None, claim=claim)["label"] == "UNKNOWN"
    assert verify_count_claim(pre_facts=[], transition=transition, claim=claim)["label"] == "UNKNOWN"
    audit = verify_count_pair_accessibly(
        pre_state_subgraph={"facts": [fact]}, accessible_transition=transition,
        supported_claim=claim, contradictory_claim={**claim, "value": 1},
        necessary_pre_fact_ids=["pre_chair_1"],
    )
    assert audit["status"] == "PASS"
    assert audit["necessary_pre_fact_ablations"] == {"pre_chair_1": "UNKNOWN"}


def test_l4_model_input_truth_boundary_detects_nested_leakage() -> None:
    safe = {
        "claim": "There are three chairs.",
        "media": {"top_view_label": {"path": "top_view_label/scene.png"}},
    }
    assert _forbidden_keys(safe) == set()
    assert _forbidden_keys({**safe, "metadata": {"post_oracle_id": "oracle_1"}}) == {
        "post_oracle_id"
    }


def test_verification_status_distinguishes_p0_met_from_shortfall() -> None:
    assert verification_status(
        accepted_count=0, calibration_ratio_pass=True, p0_minimum=100,
    ) == "VERIFIED_CANDIDATE_SET_EMPTY"
    assert verification_status(
        accepted_count=99, calibration_ratio_pass=True, p0_minimum=100,
    ) == "VERIFIED_CANDIDATE_SET_VALID_P0_SHORTFALL"
    assert verification_status(
        accepted_count=100, calibration_ratio_pass=True, p0_minimum=100,
    ) == "VERIFIED_CANDIDATE_SET_VALID_P0_MET"
    assert verification_status(
        accepted_count=100, calibration_ratio_pass=False, p0_minimum=100,
    ) == "REJECT_CALIBRATION_RATIO_EXCEEDED"


def test_count_prestate_rejects_intervention_class_mismatch() -> None:
    assert ref_mentions_class("Two black chairs", "chair")
    assert not ref_mentions_class("Two black tables", "chair")
    branch = {
        "scene_id": "scene0001_00", "change_id": "change_1", "question_id": "question_1",
        "branch_id": "branch_1",
    }
    oracle = {
        "oracle_id": "oracle_1",
        "normalized_atoms": [{"predicate": "COUNT", "subject": "chairs", "value": 0}],
    }
    catalog = {
        "scenes": {"scene0001_00": {
            "source_scene_id": "scannet/scene0001_00",
            "objects": [
                {"object_id": "chair_0", "class": "chair"},
                {"object_id": "table_0", "class": "table"},
            ],
            "relations": [],
        }}
    }
    addition, addition_reject = build_count_prestate(
        branch=branch,
        parsed={"intervention": {"type": "ADDITION", "new_entity_ref_texts": ["One table"]}},
        oracle=oracle, resolution={"resolved_targets": []}, catalog=catalog,
    )
    assert addition is None
    assert addition_reject == "REJECT_TRANSITION_PRECONDITION_FAIL"

    removal, removal_reject = build_count_prestate(
        branch=branch,
        parsed={"intervention": {"type": "REMOVAL", "target_ref_texts": ["the table"]}},
        oracle=oracle,
        resolution={"resolved_targets": [{"resolved_entity_id": "table_0"}]},
        catalog=catalog,
    )
    assert removal is None
    assert removal_reject == "REJECT_TRANSITION_PRECONDITION_FAIL"


def test_replacement_count_prestate_requires_old_and_new_classes() -> None:
    branch = {
        "scene_id": "scene0001_00", "change_id": "change_1", "question_id": "question_1",
        "branch_id": "branch_1",
    }
    catalog = {
        "scenes": {"scene0001_00": {
            "source_scene_id": "scannet/scene0001_00",
            "objects": [
                {"object_id": "door_0", "class": "door"},
                {"object_id": "curtain_0", "class": "curtain"},
                {"object_id": "table_0", "class": "table"},
                {"object_id": "coffee_table_0", "class": "coffee table"},
            ],
            "relations": [],
        }}
    }
    assert unique_catalog_class_mentioned(catalog, "a coffee table") == "coffee table"
    parsed = {"intervention": {
        "type": "REPLACEMENT", "target_ref_texts": ["the door"],
        "new_entity_ref_texts": ["a curtain"], "new_entities": ["new_curtain_0"],
    }}
    oracle = {
        "oracle_id": "oracle_1",
        "normalized_atoms": [{"predicate": "COUNT", "subject": "curtains", "value": 2}],
    }
    resolution = {"resolved_targets": [{"resolved_entity_id": "door_0"}]}
    bundle, reject = build_count_prestate(
        branch=branch, parsed=parsed, oracle=oracle, resolution=resolution, catalog=catalog,
    )
    assert reject is None and bundle is not None
    assert bundle["accessible_transition"] == {
        "rule_id": "REPLACEMENT_UPDATES_CLASS_COUNT", "delta": 1,
        "derived_post_count": 2, "uses_post_oracle_as_premise": False,
    }
    pair = build_count_pair(bundle)
    assert pair["task"]["operator_id"] == "REPLACEMENT_COUNT_UPDATE_ERROR"
    assert pair["task"]["secondary_tracks"] == ["GEO-TOPO", "IDENTITY"]
    assert pair["validation"]["independent_verifier"]["status"] == "PASS"

    old_pair = build_existence_calibration_pair(bundle, operator_id="OLD_OBJECT_PERSISTENCE")
    new_pair = build_existence_calibration_pair(bundle, operator_id="NEW_OBJECT_ABSENCE")
    assert old_pair["task"]["strength_slice"] == "L4_CALIBRATION"
    assert old_pair["certificate"]["dependency_checks"]["change_only_label"] == "SUPPORTED"
    assert old_pair["supported_claim"]["graph"]["value"] is False
    assert new_pair["supported_claim"]["graph"]["value"] is True
    assert select_existence_calibration_pairs(
        [bundle], requested_limit=4, core_pair_count=1,
    ) == []  # the 15% cap permits no calibration pair for one core pair

    removal_direction = verify_count_claim(
        pre_facts=[{"fact_id": "pre_door", "predicate": "COUNT", "subject": "door", "value": 1}],
        transition={"rule_id": "REPLACEMENT_UPDATES_CLASS_COUNT", "delta": -1},
        claim={"predicate": "COUNT", "subject": "door", "value": 0, "state": "post"},
    )
    assert removal_direction["label"] == "SUPPORTED"

    unknown_without_intervention = verify_existence_claim(
        transition=None, claim=old_pair["supported_claim"]["graph"],
    )
    assert unknown_without_intervention["label"] == "UNKNOWN"
