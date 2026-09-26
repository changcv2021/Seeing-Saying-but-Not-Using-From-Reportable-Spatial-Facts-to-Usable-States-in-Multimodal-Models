from spaceconflict.generation.language import _candidate
from spaceconflict.generation.verification import independent_label


def _graph(subject, object_):
    return {
        "label": "IGNORED", "atoms": [{"subject": subject, "predicate": "BEFORE", "object": object_, "polarity": "positive"}],
        "context": {"time_scope": "whole_video", "reference_frame": "video_timeline", "scope": "whole_video", "state_id": "observed", "branch_id": "actual"},
    }


def _fact(subject, object_):
    return {
        "fact_id": "fact:1", "subject": subject, "predicate": "BEFORE", "object": object_, "polarity": "positive",
        "context": {"time_scope": "whole_video", "reference_frame": "video_timeline", "scope": "whole_video", "state_id": "observed", "branch_id": "actual"},
    }


def test_independent_verifier_supported_contradictory_unknown():
    a, b = "first_appear:chair@source_item:x", "first_appear:table@source_item:x"
    fact = _fact(a, b)
    supported_graph = _graph(a, b)
    contradictory_graph = _graph(b, a)
    supported = _candidate("sc_pair_test", supported_graph, 0)
    contradictory = _candidate("sc_pair_test", contradictory_graph, 0)
    assert independent_label(candidate=supported, entity_graph=supported_graph, world_facts=[fact])["label"] == "SUPPORTED"
    assert independent_label(candidate=contradictory, entity_graph=contradictory_graph, world_facts=[fact])["label"] == "CONTRADICTORY"
    assert independent_label(candidate=contradictory, entity_graph=contradictory_graph, world_facts=[])["label"] == "UNKNOWN"


def test_inverse_relation_is_equivalent_and_same_order_inverse_refutes() -> None:
    a, b = "first_appear:chair@source_item:x", "first_appear:table@source_item:x"
    fact = _fact(a, b)
    equivalent = {
        "label": "SUPPORTED",
        "atoms": [{"subject": b, "predicate": "AFTER", "object": a, "polarity": "positive"}],
        "context": _graph(a, b)["context"],
    }
    conflicting = {
        "label": "CONTRADICTORY",
        "atoms": [{"subject": a, "predicate": "AFTER", "object": b, "polarity": "positive"}],
        "context": _graph(a, b)["context"],
    }
    equivalent_candidate = _candidate("inverse", equivalent, 0)
    conflicting_candidate = _candidate("inverse_conflict", conflicting, 0)
    assert independent_label(candidate=equivalent_candidate, entity_graph=equivalent, world_facts=[fact])["label"] == "SUPPORTED"
    assert independent_label(candidate=conflicting_candidate, entity_graph=conflicting, world_facts=[fact])["label"] == "CONTRADICTORY"


def _ca_context():
    return {
        "world_id": "arkitscenes:1", "media_id": "media:1", "view_id": "reference_frame:1:2",
        "frame_id": "1_2", "time_scope": None, "reference_frame": "ca_vqa_reference_frame",
        "scope": "reference_frame", "state_id": "observed", "branch_id": "actual",
    }


def test_independent_verifier_uses_explicit_negative_visibility() -> None:
    graph = {
        "label": "CONTRADICTORY",
        "atoms": [{"subject": "class:chair", "predicate": "VISIBLE_IN_FRAME", "object": None, "value": None, "polarity": "positive"}],
        "context": _ca_context(),
    }
    candidate = _candidate("p", graph, 0)
    negative_fact = {
        "fact_id": "fact:no-chair", "subject": "class:chair", "predicate": "VISIBLE_IN_FRAME",
        "object": None, "value": None, "polarity": "negative", "context": _ca_context(),
    }
    assert independent_label(candidate=candidate, entity_graph=graph, world_facts=[negative_fact])["label"] == "CONTRADICTORY"


def test_independent_verifier_uses_exact_count_functionality() -> None:
    graph = {
        "label": "CONTRADICTORY",
        "atoms": [{"subject": "class:chairs", "predicate": "COUNT", "object": None, "value": 2, "polarity": "positive"}],
        "context": _ca_context(),
    }
    candidate = _candidate("p", graph, 0)
    actual_count = {
        "fact_id": "fact:count", "subject": "class:chairs", "predicate": "COUNT",
        "object": None, "value": 3, "polarity": "positive", "context": _ca_context(),
    }
    assert independent_label(candidate=candidate, entity_graph=graph, world_facts=[actual_count])["label"] == "CONTRADICTORY"


def test_independent_verifier_replays_unique_two_fact_l2_chain() -> None:
    a = "first_appear:chair@source_item:x"
    b = "first_appear:table@source_item:x"
    c = "first_appear:door@source_item:x"
    first = _fact(a, b)
    first["fact_id"] = "fact:first"
    second = _fact(b, c)
    second["fact_id"] = "fact:second"
    supported_graph = _graph(a, c)
    contradictory_graph = _graph(c, a)
    supported = _candidate("l2_supported", supported_graph, 0)
    contradictory = _candidate("l2_contradictory", contradictory_graph, 0)
    rules = {"STRICT_ORDER_TRANSITIVITY", "SAME_SCOPE_EXCLUSIVITY"}

    supported_result = independent_label(
        candidate=supported, entity_graph=supported_graph,
        world_facts=[first, second], authorized_rule_ids=rules,
    )
    contradictory_result = independent_label(
        candidate=contradictory, entity_graph=contradictory_graph,
        world_facts=[first, second], authorized_rule_ids=rules,
    )
    assert supported_result["label"] == "SUPPORTED"
    assert supported_result["suggested_level"] == "L2"
    assert supported_result["evidence_fact_ids"] == ["fact:first", "fact:second"]
    assert contradictory_result["label"] == "CONTRADICTORY"
    assert contradictory_result["suggested_level"] == "L2"

    equivalent_inverse_graph = {
        **supported_graph,
        "atoms": [{**supported_graph["atoms"][0], "subject": c, "predicate": "AFTER", "object": a}],
    }
    equivalent_inverse = _candidate("l2_equivalent_inverse", equivalent_inverse_graph, 0)
    assert independent_label(
        candidate=equivalent_inverse, entity_graph=equivalent_inverse_graph,
        world_facts=[first, second], authorized_rule_ids=rules,
    )["label"] == "SUPPORTED"

    for remaining in ([first], [second]):
        assert independent_label(
            candidate=contradictory, entity_graph=contradictory_graph,
            world_facts=remaining, authorized_rule_ids=rules,
        )["label"] == "UNKNOWN"
    assert independent_label(
        candidate=supported, entity_graph=supported_graph,
        world_facts=[first, second], authorized_rule_ids=set(),
    )["label"] == "UNKNOWN"
