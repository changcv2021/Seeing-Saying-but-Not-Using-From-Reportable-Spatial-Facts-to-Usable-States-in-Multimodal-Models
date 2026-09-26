from __future__ import annotations

import inspect
from collections import Counter

from spaceconflict.l4_three_part.checker_b import check_transition_b
from spaceconflict.l4_three_part.common import (
    count_claim_text, graph_text_roundtrip, load_split_map, normalized_fact,
    relation_claim_text, resolve_unique_reference,
)
from spaceconflict.l4_three_part.controlled import (
    _make_action, select_controlled_candidates, verify_controlled_pair,
)
from spaceconflict.l4_three_part.engine_a import execute_transition_a
from spaceconflict.l4_three_part.native import build_post_fact_graphs, group_branches, verify_native_pair
from spaceconflict.l4_three_part.unknown import verify_unknown_sample


def _fact(predicate: str, subject: str, value=None, object_=None, scope="question_local"):
    return {
        "fact_id": f"pre:{predicate}:{subject}:{object_}", "predicate": predicate,
        "subject": subject, "object": object_, "value": value,
        "scope": scope, "state": "pre", "origin_type": "SOURCE_GT", "source_ref": "source",
    }


def _action(family: str):
    if family == "REMOVE_AND_RECOUNT":
        pre = [_fact("COUNT", "chair", 3, scope="whole_scene"), _fact("EXISTS_IN_WORLD", "chair_1", True)]
        post = [
            normalized_fact({"predicate": "COUNT", "subject": "chair", "value": 2, "scope": "whole_scene"}),
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "chair_1", "value": False}),
        ]
        params = {"target_id": "chair_1", "category": "chair", "count_deltas": {"chair": -1}}
    elif family == "ADD_AND_RECOUNT":
        pre = [_fact("COUNT", "chair", 2, scope="whole_scene")]
        post = [
            normalized_fact({"predicate": "COUNT", "subject": "chair", "value": 3, "scope": "whole_scene"}),
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "added_chair", "value": True}),
        ]
        params = {"category": "chair", "quantity": 1, "new_entity_id": "added_chair", "count_deltas": {"chair": 1}}
    elif family == "REPLACE_AND_RECOUNT":
        pre = [
            _fact("COUNT", "chair", 1, scope="whole_scene"),
            _fact("COUNT", "lamp", 2, scope="whole_scene"),
            _fact("EXISTS_IN_WORLD", "chair_1", True),
        ]
        post = [
            normalized_fact({"predicate": "COUNT", "subject": "chair", "value": 0, "scope": "whole_scene"}),
            normalized_fact({"predicate": "COUNT", "subject": "lamp", "value": 3, "scope": "whole_scene"}),
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "chair_1", "value": False}),
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "new_lamp", "value": True}),
            normalized_fact({"predicate": "SAME_INSTANCE", "subject": "new_lamp", "object": "chair_1", "value": False}),
        ]
        params = {
            "target_id": "chair_1", "new_entity_id": "new_lamp", "old_category": "chair",
            "new_category": "lamp", "count_deltas": {"chair": -1, "lamp": 1},
            "identity_deltas": {"new_lamp|chair_1": False},
        }
    elif family == "REPLACEMENT_IDENTITY":
        pre = [_fact("EXISTS_IN_WORLD", "chair_1", True)]
        post = [
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "chair_1", "value": False}),
            normalized_fact({"predicate": "EXISTS_IN_WORLD", "subject": "new_lamp", "value": True}),
            normalized_fact({"predicate": "SAME_INSTANCE", "subject": "new_lamp", "object": "chair_1", "value": False}),
        ]
        params = {"target_id": "chair_1", "new_entity_id": "new_lamp", "old_category": "chair", "new_category": "lamp"}
    else:
        pre = [_fact("LEFT_OF", "chair_1", object_="table_1")]
        post = [normalized_fact({"predicate": "RIGHT_OF", "subject": "chair_1", "object": "table_1"})]
        params = {
            ("target_id" if family == "MOVE_TO_OPPOSITE_SIDE" else "target_a_id"): "chair_1",
            ("anchor_id" if family == "MOVE_TO_OPPOSITE_SIDE" else "target_b_id"): "table_1",
            "pre_predicate": "LEFT_OF", "post_predicate": "RIGHT_OF", "axis": "horizontal",
            "reference_frame": "source_world_axes",
        }
    action = _make_action(
        family=family, parameters=params, pre_facts=pre, post_facts=post,
        text=f"Suppose action {family} is performed.", scene_id="scene_1",
    )
    return pre, action, post


def _controlled_candidate(family="ADD_AND_RECOUNT"):
    pre, action, post = _action(family)
    if family == "REPLACEMENT_IDENTITY":
        supported = next(f for f in post if f["predicate"] == "SAME_INSTANCE")
        contradictory = {**supported, "value": True}
        supported_text = "After this hypothetical change, the new lamp is a different instance from the original chair."
        contradictory_text = "After this hypothetical change, the new lamp is the same instance as the original chair."
        dependency = "CALIBRATION"
    elif family in {"MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"}:
        supported = {**post[0], "subject_label": "chair", "object_label": "table"}
        contradictory = {**supported, "predicate": "LEFT_OF"}
        supported_text = relation_claim_text("chair", "RIGHT_OF", "table")
        contradictory_text = relation_claim_text("chair", "LEFT_OF", "table")
        dependency = "CORE"
    else:
        supported = next(f for f in post if f["predicate"] == "COUNT")
        contradictory = {**supported, "value": supported["value"] - 1}
        supported_text = count_claim_text(supported["subject"], supported["value"])
        contradictory_text = count_claim_text(contradictory["subject"], contradictory["value"])
        dependency = "CORE"
    candidate = {"pre_facts": pre, "action": action, "family": family, "dependency_type": dependency}
    return candidate, {"graph": supported, "text": supported_text}, {"graph": contradictory, "text": contradictory_text}


def test_branch_grouping() -> None:
    rows = [
        {"scene_id": "s", "change_id": "c", "question_id": "q1", "branch_id": "b", "context_change_raw": "move", "change_type": "MOVEMENT", "global_world_id": "hypo3d:s", "source_hash": "h1", "source_revision": "r"},
        {"scene_id": "s", "change_id": "c", "question_id": "q2", "branch_id": "b", "context_change_raw": "move", "change_type": "MOVEMENT", "global_world_id": "hypo3d:s", "source_hash": "h2", "source_revision": "r"},
    ]
    grouped, rejects = group_branches(rows)
    assert not rejects and grouped[0]["source_qa_ids"] == ["q1", "q2"]


def test_qa_to_post_fact() -> None:
    branch = {("s", "c"): {"branch_id": "b"}}
    oracle = {"scene_id": "s", "change_id": "c", "source_question_id": "q", "oracle_id": "o", "source_reconstruction": "PASS", "normalized_atoms": [{"predicate": "COUNT", "subject": "chairs", "value": 2}], "provenance": {"source_hash": "h"}}
    graphs, rejects = build_post_fact_graphs([oracle], branch)
    assert not rejects and graphs[0]["facts"][0]["predicate"] == "COUNT"


def test_source_qa_reconstruction() -> None:
    branch = {("s", "c"): {"branch_id": "b"}}
    oracle = {"scene_id": "s", "change_id": "c", "source_question_id": "q", "source_reconstruction": "FAIL", "normalized_atoms": []}
    graphs, rejects = build_post_fact_graphs([oracle], branch)
    assert not graphs and rejects[0]["reason"] == "REJECT_SOURCE_RECONSTRUCTION_FAIL"


def test_equivalent_fact_dedup() -> None:
    branch = {("s", "c"): {"branch_id": "b"}}
    rows = [
        {"scene_id": "s", "change_id": "c", "source_question_id": f"q{i}", "oracle_id": f"o{i}", "source_reconstruction": "PASS", "normalized_atoms": [{"predicate": "COUNT", "subject": "chair", "value": 2}], "provenance": {"source_hash": f"h{i}"}}
        for i in range(2)
    ]
    graphs, _ = build_post_fact_graphs(rows, branch)
    assert len(graphs[0]["facts"]) == 1 and len(graphs[0]["facts"][0]["source_pointers"]) == 2


def test_unique_target_resolution() -> None:
    scene = {"objects": [{"object_id": "chair_1", "class": "chair"}, {"object_id": "table_1", "class": "table"}]}
    assert resolve_unique_reference(scene, "the chair now")["object_id"] == "chair_1"
    scene["objects"].append({"object_id": "chair_2", "class": "chair"})
    assert resolve_unique_reference(scene, "the chair") is None


def test_branch_split_consistency(tmp_path) -> None:
    path = tmp_path / "split.jsonl"
    path.write_text('{"global_world_id":"hypo3d:s","split":"test"}\n')
    assert load_split_map(path) == {"hypo3d:s": "test"}


def test_remove_and_recount() -> None:
    pre, action, expected = _action("REMOVE_AND_RECOUNT")
    assert check_transition_b(pre, action)["post_facts"] == sorted(expected, key=lambda f: (f["predicate"], f["subject"], str(f["object"]), f["scope"]))


def test_add_and_recount() -> None:
    pre, action, _ = _action("ADD_AND_RECOUNT")
    assert check_transition_b(pre, action)["status"] == "PASS"


def test_replace_and_recount() -> None:
    pre, action, post = _action("REPLACE_AND_RECOUNT")
    result = check_transition_b(pre, action)
    assert result["status"] == "PASS" and any(f["predicate"] == "SAME_INSTANCE" for f in result["post_facts"])


def test_replacement_identity() -> None:
    pre, action, _ = _action("REPLACEMENT_IDENTITY")
    result = check_transition_b(pre, action)
    assert next(f for f in result["post_facts"] if f["predicate"] == "SAME_INSTANCE")["value"] is False


def test_move_to_opposite_side() -> None:
    pre, action, _ = _action("MOVE_TO_OPPOSITE_SIDE")
    assert check_transition_b(pre, action)["post_facts"][0]["predicate"] == "RIGHT_OF"


def test_swap_positions() -> None:
    pre, action, _ = _action("SWAP_POSITIONS")
    assert check_transition_b(pre, action)["post_facts"][0]["predicate"] == "RIGHT_OF"


def test_precondition_rejection() -> None:
    _, action, _ = _action("REMOVE_AND_RECOUNT")
    assert check_transition_b([], action)["status"] == "FAIL"


def test_no_unlisted_fact_update() -> None:
    pre, action, _ = _action("ADD_AND_RECOUNT")
    action["add_facts"].append(normalized_fact({"predicate": "COUNT", "subject": "table", "value": 8}))
    assert "UNLISTED_POST_FACT_UPDATE" in execute_transition_a(pre, action)["errors"]


def test_engine_a_checker_b_exact_match() -> None:
    for family in ("REMOVE_AND_RECOUNT", "ADD_AND_RECOUNT", "REPLACE_AND_RECOUNT", "REPLACEMENT_IDENTITY", "MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"):
        pre, action, _ = _action(family)
        assert execute_transition_a(pre, action)["post_facts"] == check_transition_b(pre, action)["post_facts"]


def test_independent_code_paths() -> None:
    assert inspect.getsourcefile(execute_transition_a) != inspect.getsourcefile(check_transition_b)
    assert "family ==" not in inspect.getsource(execute_transition_a)


def test_mismatch_rejection() -> None:
    pre, action, _ = _action("ADD_AND_RECOUNT")
    next(f for f in action["add_facts"] if f["predicate"] == "COUNT")["value"] = 99
    assert execute_transition_a(pre, action)["post_facts"] != check_transition_b(pre, action)["post_facts"]


def test_scene_only_insufficient() -> None:
    candidate, supported, contradictory = _controlled_candidate()
    assert verify_controlled_pair(candidate, supported, contradictory)["scene_only_label"] == "UNKNOWN"


def test_change_only_insufficient() -> None:
    candidate, supported, contradictory = _controlled_candidate()
    assert verify_controlled_pair(candidate, supported, contradictory)["change_only_label"] == "UNKNOWN"


def test_full_input_sufficient() -> None:
    candidate, supported, contradictory = _controlled_candidate()
    assert verify_controlled_pair(candidate, supported, contradictory)["full_input_label"] == "SUPPORTED"


def test_calibration_tagging() -> None:
    candidate, supported, contradictory = _controlled_candidate("REPLACEMENT_IDENTITY")
    result = verify_controlled_pair(candidate, supported, contradictory)
    assert result["status"] == "PASS" and result["change_only_label"] == "SUPPORTED"


def _unknown(reason="MISSING_PRE_COUNT", pipeline_failure=False):
    return {
        "unknown_axis": reason, "base_determinate_sample_id": "base", "pipeline_failure": pipeline_failure,
        "missing_decisive_evidence": ["fact"],
        "positive_witness_completion": {"claim_holds": True, "world": 1},
        "negative_witness_completion": {"claim_holds": False, "world": 2},
    }


def test_unknown_positive_witness() -> None:
    assert verify_unknown_sample(_unknown())["satisfiable_with_claim"]


def test_unknown_negative_witness() -> None:
    assert verify_unknown_sample(_unknown())["satisfiable_with_negation"]


def test_reject_not_unknown() -> None:
    assert verify_unknown_sample(_unknown(pipeline_failure=True))["status"] == "FAIL"


def test_evidence_ablation() -> None:
    assert verify_unknown_sample(_unknown("REFERENCE_FRAME_AMBIGUITY"))["status"] == "PASS"


def test_unknown_quota() -> None:
    reasons = Counter(["a"] * 75 + ["b"] * 75 + ["c"] * 75 + ["d"] * 75)
    assert max(reasons.values()) / sum(reasons.values()) == 0.25


def test_intervention_visible() -> None:
    candidate, _, _ = _controlled_candidate()
    assert candidate["action"]["model_visible_text"]


def test_pair_intervention_equal() -> None:
    candidate, supported, contradictory = _controlled_candidate()
    assert candidate["action"]["model_visible_text"] == candidate["action"]["model_visible_text"]
    assert supported["graph"]["subject"] == contradictory["graph"]["subject"]


def test_single_changed_slot() -> None:
    _, supported, contradictory = _controlled_candidate()
    differences = [key for key in supported["graph"] if supported["graph"].get(key) != contradictory["graph"].get(key)]
    assert differences == ["value"]


def test_graph_text_roundtrip() -> None:
    graph = {"predicate": "COUNT", "subject": "chair", "value": 3}
    assert graph_text_roundtrip(count_claim_text("chair", 3), graph)


def test_no_label_marker() -> None:
    candidate, supported, contradictory = _controlled_candidate()
    text = " ".join((candidate["action"]["model_visible_text"], supported["text"], contradictory["text"])).casefold()
    assert "supported" not in text and "contradictory" not in text and "gold label" not in text


def test_no_action_only_leak_for_core() -> None:
    candidate, supported, contradictory = _controlled_candidate("MOVE_TO_OPPOSITE_SIDE")
    assert verify_controlled_pair(candidate, supported, contradictory)["change_only_label"] == "UNKNOWN"


def test_base_scene_single_split() -> None:
    rows = [{"base_scene_id": "s", "split": "train"}, {"base_scene_id": "s", "split": "train"}]
    assert len({row["split"] for row in rows}) == 1


def test_native_controlled_same_world_split() -> None:
    native = {"global_world_id": "hypo3d:s", "split": "dev"}
    controlled = {"global_world_id": "hypo3d:s", "split": "dev"}
    assert native["split"] == controlled["split"]


def test_unknown_base_sample_same_split() -> None:
    base, unknown = {"split": "test"}, {"split": "test"}
    assert base["split"] == unknown["split"]


def test_paraphrase_same_split() -> None:
    variants = [{"pair_id": "p", "split": "train"}, {"pair_id": "p", "split": "train"}]
    assert len({row["split"] for row in variants}) == 1


def test_combined_test_density_reserves_native_slots() -> None:
    reserved = [{
        "base_scene_id": "s", "split": "test", "transition_family": "MOVEMENT",
    }]
    candidates = [
        {
            "candidate_id": "c1", "scene_id": "s", "split": "test",
            "family": "ADD_AND_RECOUNT", "transition_family": "ADDITION",
            "source_group": "REFERIT3D_EXACT_COUNT",
        },
        {
            "candidate_id": "c2", "scene_id": "s", "split": "test",
            "family": "REMOVE_AND_RECOUNT", "transition_family": "REMOVAL",
            "source_group": "FUSED_REFERIT3D_OBJECT_GT",
        },
        {
            "candidate_id": "c3", "scene_id": "s", "split": "test",
            "family": "MOVE_TO_OPPOSITE_SIDE", "transition_family": "MOVEMENT",
            "source_group": "EMBODIEDSCAN_9DOF",
        },
    ]
    config = {
        "operator_targets": {
            "ADD_AND_RECOUNT": 1, "REMOVE_AND_RECOUNT": 1,
            "MOVE_TO_OPPOSITE_SIDE": 1,
        },
        "scene_pair_caps": {"train": 6, "dev": 6, "test": 2},
        "minimum_3dssg_relation_pairs": 0,
        "combined_test_soft_target": 2,
    }
    selected, report = select_controlled_candidates(
        candidates=candidates, config=config, target_pairs=3, seed=1,
        scene_limit=None, reserved_pairs=reserved,
    )
    assert len(selected) == 1
    assert selected[0]["transition_family"] != "MOVEMENT"
    assert report["combined_test_pairs"] == 2
