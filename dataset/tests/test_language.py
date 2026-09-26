from spaceconflict.generation.language import (
    TEMPLATES, _candidate, _pair_entity_aliases, _parse, _sample_duplicate_key,
    entity_description,
)


def _graph(subject="first_appear:chair@source_item:abc", object_="first_appear:table@source_item:abc"):
    return {
        "label": "SUPPORTED", "atoms": [{"subject": subject, "predicate": "BEFORE", "object": object_, "polarity": "positive"}],
        "context": {"time_scope": "whole_video", "reference_frame": "video_timeline", "scope": "whole_video", "state_id": "observed", "branch_id": "actual"},
    }


def test_entity_description_removes_only_internal_identity():
    assert entity_description("first_appear:office_chair@source_item:123") == "office chair"
    assert entity_description("query_target:omni:1") == "queried target"
    assert entity_description("spar_sample:1:bbox_target") == "bounding-box target"
    assert entity_description("mention:the_airplane_model@source_item:123") == "airplane model"
    assert entity_description("bbox_anchor:abc123:10_20_30_40") == "object marked by bounding box [10, 20, 30, 40]"


def test_all_templates_roundtrip():
    graph = _graph()
    for index in range(len(TEMPLATES)):
        candidate = _candidate("sc_pair_test", graph, index)
        parsed = _parse(candidate, graph)
        assert parsed is not None
        assert parsed["subject"] == graph["atoms"][0]["subject"]
        assert parsed["object"] == graph["atoms"][0]["object"]
        assert parsed["predicate"] == "BEFORE"


def test_after_inverse_templates_roundtrip() -> None:
    graph = _graph()
    atom = graph["atoms"][0]
    graph["atoms"][0] = {
        **atom,
        "subject": atom["object"],
        "predicate": "AFTER",
        "object": atom["subject"],
    }
    for index in range(len(TEMPLATES)):
        candidate = _candidate("sc_pair_inverse", graph, index)
        parsed = _parse(candidate, graph)
        assert parsed is not None
        assert parsed["predicate"] == "AFTER"
        assert parsed["subject"] == graph["atoms"][0]["subject"]
        assert parsed["object"] == graph["atoms"][0]["object"]


def test_pair_template_changes_only_entity_order():
    positive = _candidate("sc_pair_test", _graph(), 4)
    negative = _candidate("sc_pair_test", _graph("first_appear:table@source_item:abc", "first_appear:chair@source_item:abc"), 4)
    assert positive["surface_blueprint_id"] == negative["surface_blueprint_id"]


def test_interval_context_roundtrip():
    graph = _graph()
    graph["atoms"][0]["predicate"] = "LEFT_OF"
    graph["context"] = {
        "time_scope": {"start": 1.5, "end": 1.5}, "reference_frame": "observer",
        "scope": "time_interval", "state_id": "observed", "branch_id": "actual",
    }
    candidate = _candidate("sc_pair_interval", graph, 0)
    parsed = _parse(candidate, graph)
    assert parsed is not None
    assert parsed["context"] == graph["context"]


def test_ordered_frame_sequence_context_roundtrip() -> None:
    graph = _graph()
    graph["context"] = {
        **graph["context"], "time_scope": "whole_ordered_sequence",
    }
    for index in range(len(TEMPLATES)):
        parsed = _parse(_candidate("sc_pair_ordered_sequence", graph, index), graph)
        assert parsed is not None
        assert parsed["context"] == graph["context"]


def _ca_graph(predicate: str, subject: str = "class:bed", value=None):
    return {
        "label": "SUPPORTED",
        "atoms": [{"atom_id": "a", "subject": subject, "predicate": predicate, "object": None, "value": value, "polarity": "positive"}],
        "context": {
            "world_id": "arkitscenes:1", "media_id": "media:1", "view_id": "reference_frame:1:2",
            "frame_id": "1_2", "time_scope": None, "reference_frame": "ca_vqa_reference_frame",
            "scope": "reference_frame", "state_id": "observed", "branch_id": "actual",
        },
    }


def test_ca_visibility_roundtrip_all_families() -> None:
    graph = _ca_graph("VISIBLE_IN_FRAME")
    for index in range(len(TEMPLATES)):
        parsed = _parse(_candidate("p", graph, index), graph)
        assert parsed is not None
        assert parsed["subject"] == "class:bed"
        assert parsed["predicate"] == "VISIBLE_IN_FRAME"
        assert parsed["context"] == graph["context"]


def test_ca_count_roundtrip_all_families() -> None:
    graph = _ca_graph("COUNT", "class:door_bells", 2)
    for index in range(len(TEMPLATES)):
        parsed = _parse(_candidate("p", graph, index), graph)
        assert parsed is not None
        assert parsed["subject"] == "class:door_bells"
        assert parsed["predicate"] == "COUNT"
        assert parsed["value"] == 2


def test_context_language_avoids_redundant_actual_observed_phrase() -> None:
    for graph in (_graph(), _ca_graph("COUNT", "class:chairs", 2)):
        for index in range(len(TEMPLATES)):
            text = _candidate("p", graph, index)["natural_text"]
            assert "actual observed" not in text.casefold()


def test_duplicate_key_distinguishes_same_text_in_different_media_contexts() -> None:
    graph_a = _ca_graph("COUNT", "class:chairs", 2)
    graph_b = _ca_graph("COUNT", "class:chairs", 2)
    graph_b["context"] = {**graph_b["context"], "media_id": "media:2", "view_id": "reference_frame:2:2"}
    candidate_a = {**_candidate("a", graph_a, 0), "normalized": graph_a}
    candidate_b = {**_candidate("b", graph_b, 0), "normalized": graph_b}
    assert candidate_a["natural_text"] == candidate_b["natural_text"]
    assert _sample_duplicate_key(candidate_a) != _sample_duplicate_key(candidate_b)


def test_pair_randomized_aliases_roundtrip_and_share_entity_vocabulary() -> None:
    supported = _graph()
    contradictory = _graph("first_appear:table@source_item:abc", "first_appear:chair@source_item:abc")
    aliases = _pair_entity_aliases("sc_pair_alias_test", supported, contradictory)
    positive = _candidate("sc_pair_alias_test", supported, 0, entity_aliases=aliases)
    negative = _candidate("sc_pair_alias_test", contradictory, 0, entity_aliases=aliases)
    assert positive["entity_declaration"] == negative["entity_declaration"]
    assert "first appearance of the chair" in positive["natural_text"]
    assert "first appearance of the table" in positive["natural_text"]
    assert _parse(positive, supported)["subject"] == supported["atoms"][0]["subject"]
    assert _parse(negative, contradictory)["subject"] == contradictory["atoms"][0]["subject"]


def test_pair_alias_orientation_varies_independently_of_supported_role() -> None:
    supported = _graph()
    contradictory = _graph("first_appear:table@source_item:abc", "first_appear:chair@source_item:abc")
    orientations = {
        _pair_entity_aliases(f"pair_{index}", supported, contradictory)[supported["atoms"][0]["subject"]]
        for index in range(32)
    }
    assert orientations == {"entity A", "entity B"}
