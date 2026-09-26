from __future__ import annotations

import pytest

from spaceconflict.l4_tracks import derive_missing_track_annotation


def _pair(origin, transition, predicate, *, family=None, intervention_type=None, frame=None, axis=None):
    intervention = {}
    if family:
        intervention["family"] = family
    if intervention_type:
        intervention["type"] = intervention_type
    if frame or axis:
        intervention["parameters"] = {"reference_frame": frame, "axis": axis}
    return {
        "pair_id": "pair_1",
        "l4_origin": origin,
        "transition_family": transition,
        "intervention": intervention,
        "supported_claim": {"graph": {"predicate": predicate}},
        "edit": {"changed_slots": ["predicate" if predicate in {"LEFT_OF", "RIGHT_OF"} else "value"]},
    }


def test_controlled_axis_transform_is_xform_proj() -> None:
    pair = _pair(
        "BENCHMARK_CONTROLLED", "MOVEMENT", "LEFT_OF",
        family="SWAP_POSITIONS", frame="source_world_axes", axis="horizontal",
    )
    result = derive_missing_track_annotation(pair)
    assert result["primary_track"] == "XFORM-PROJ"
    assert result["secondary_tracks"] == ["DYNAMIC", "GEO-TOPO"]


def test_native_movement_without_frame_is_geo_topo() -> None:
    pair = _pair("SOURCE_NATIVE", "MOVEMENT", "FRONT_OF", intervention_type="MOVEMENT")
    result = derive_missing_track_annotation(pair)
    assert result["primary_track"] == "GEO-TOPO"
    assert result["secondary_tracks"] == ["DYNAMIC"]


def test_replacement_identity_is_identity() -> None:
    pair = _pair("BENCHMARK_CONTROLLED", "REPLACEMENT", "SAME_INSTANCE", family="REPLACEMENT_IDENTITY")
    result = derive_missing_track_annotation(pair)
    assert result["primary_track"] == "IDENTITY"
    assert result["operator_id"] == "REPLACEMENT_IDENTITY_ERROR"


def test_replacement_recount_is_dynamic_with_identity_secondary() -> None:
    pair = _pair("BENCHMARK_CONTROLLED", "REPLACEMENT", "COUNT", family="REPLACE_AND_RECOUNT")
    result = derive_missing_track_annotation(pair)
    assert result["primary_track"] == "DYNAMIC"
    assert result["secondary_tracks"] == ["GEO-TOPO", "IDENTITY"]


def test_attribute_persistence_is_identity() -> None:
    pair = _pair("SOURCE_NATIVE", "ATTRIBUTE", "EXISTS_IN_WORLD", intervention_type="ATTRIBUTE")
    result = derive_missing_track_annotation(pair)
    assert result["primary_track"] == "IDENTITY"


def test_released_track_is_not_overwritten() -> None:
    pair = _pair("SOURCE_NATIVE", "MOVEMENT", "LEFT_OF", intervention_type="MOVEMENT")
    pair["task"] = {"primary_track": "DYNAMIC"}
    with pytest.raises(ValueError, match="already has"):
        derive_missing_track_annotation(pair)

