"""Deterministic, auditable track annotations for the frozen L4 v3.3 release.

The functions in this module never modify a release record.  They derive a
versioned analysis overlay from the released intervention, claim graph, and
edit metadata, following the track definitions in the benchmark build guide.
"""

from __future__ import annotations

from typing import Any


ANNOTATION_VERSION = "l4_track_annotation_v1"
ALLOWED_TRACKS = {"GEO-TOPO", "XFORM-PROJ", "IDENTITY", "DYNAMIC", "EMBODIED-OBS"}
RELATION_PREDICATES = {"LEFT_OF", "RIGHT_OF", "FRONT_OF", "BEHIND", "ABOVE", "BELOW"}


def _nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _features(pair: dict[str, Any]) -> dict[str, Any]:
    intervention = pair.get("intervention") or {}
    parameters = intervention.get("parameters") or {}
    graph = (pair.get("supported_claim") or {}).get("graph") or {}
    return {
        "l4_origin": pair.get("l4_origin"),
        "transition_family": pair.get("transition_family"),
        "intervention_family": intervention.get("family"),
        "intervention_type": intervention.get("type"),
        "claim_predicate": graph.get("predicate"),
        "changed_slots": list((pair.get("edit") or {}).get("changed_slots") or []),
        "reference_frame": parameters.get("reference_frame") or intervention.get("reference_frame"),
        "axis": parameters.get("axis") or intervention.get("axis"),
    }


def _result(
    pair: dict[str, Any],
    *,
    primary: str,
    secondary: list[str],
    operator_id: str,
    rule_id: str,
    rationale: str,
    confidence: float,
) -> dict[str, Any]:
    if primary not in ALLOWED_TRACKS:
        raise ValueError(f"Invalid primary track {primary!r}")
    secondary = list(dict.fromkeys(secondary))
    if primary in secondary or any(track not in ALLOWED_TRACKS for track in secondary):
        raise ValueError(f"Invalid secondary tracks for {pair.get('pair_id')}: {secondary}")
    return {
        "pair_id": str(pair["pair_id"]),
        "annotation_version": ANNOTATION_VERSION,
        "annotation_status": "DERIVED_RULE_BASED",
        "primary_track": primary,
        "secondary_tracks": secondary,
        "operator_id": operator_id,
        "rule_id": rule_id,
        "confidence": confidence,
        "rationale": rationale,
        "decision_features": _features(pair),
    }


def derive_missing_track_annotation(pair: dict[str, Any]) -> dict[str, Any]:
    """Assign tracks to one L4 pair whose released ``task.primary_track`` is absent."""

    pair_id = _nonempty_string(pair.get("pair_id"))
    if pair_id is None:
        raise ValueError("L4 pair is missing pair_id")
    task = pair.get("task") or {}
    if _nonempty_string(task.get("primary_track")) is not None:
        raise ValueError(f"Pair {pair_id} already has a released primary_track")

    features = _features(pair)
    origin = features["l4_origin"]
    predicate = features["claim_predicate"]
    transition = features["transition_family"]

    if origin == "BENCHMARK_CONTROLLED":
        family = features["intervention_family"]
        if family in {"REMOVE_AND_RECOUNT", "ADD_AND_RECOUNT"}:
            if predicate != "COUNT":
                raise ValueError(f"{pair_id}: {family} must produce a COUNT claim")
            return _result(
                pair,
                primary="DYNAMIC",
                secondary=["GEO-TOPO"],
                operator_id="COUNT_UPDATE_ERROR",
                rule_id="CONTROLLED_RECOUNT_DYNAMIC",
                rationale="The contradiction is a post-intervention count update error; exact scene cardinality is an additional spatial-graph dependency.",
                confidence=1.0,
            )
        if family == "REPLACE_AND_RECOUNT":
            if predicate != "COUNT":
                raise ValueError(f"{pair_id}: REPLACE_AND_RECOUNT must produce a COUNT claim")
            return _result(
                pair,
                primary="DYNAMIC",
                secondary=["GEO-TOPO", "IDENTITY"],
                operator_id="REPLACEMENT_COUNT_UPDATE_ERROR",
                rule_id="CONTROLLED_REPLACEMENT_RECOUNT_DYNAMIC",
                rationale="The contradiction is caused by an incorrect post-replacement count; category cardinality and old/new instance distinction are supporting dependencies.",
                confidence=1.0,
            )
        if family == "REPLACEMENT_IDENTITY":
            if predicate != "SAME_INSTANCE":
                raise ValueError(f"{pair_id}: REPLACEMENT_IDENTITY must produce a SAME_INSTANCE claim")
            return _result(
                pair,
                primary="IDENTITY",
                secondary=["DYNAMIC"],
                operator_id="REPLACEMENT_IDENTITY_ERROR",
                rule_id="CONTROLLED_REPLACEMENT_IDENTITY",
                rationale="The claim directly changes whether the replacement and original object are the same instance; the replacement event supplies the secondary transition dependency.",
                confidence=1.0,
            )
        if family in {"MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"}:
            if predicate not in RELATION_PREDICATES:
                raise ValueError(f"{pair_id}: {family} must produce a directional relation claim")
            if not features["reference_frame"] or not features["axis"]:
                raise ValueError(f"{pair_id}: {family} lacks an explicit reference frame or axis")
            return _result(
                pair,
                primary="XFORM-PROJ",
                secondary=["DYNAMIC", "GEO-TOPO"],
                operator_id="WRONG_POST_RELATION",
                rule_id="CONTROLLED_AXIS_TRANSFORM",
                rationale="The operation explicitly transforms positions along a declared world axis and reference frame; the resulting post-state relation also depends on transition and geometry.",
                confidence=1.0,
            )
        raise ValueError(f"{pair_id}: unsupported controlled intervention family {family!r}")

    if origin == "SOURCE_NATIVE":
        intervention_type = features["intervention_type"]
        if predicate in RELATION_PREDICATES and transition == "MOVEMENT" and intervention_type == "MOVEMENT":
            if features["reference_frame"]:
                return _result(
                    pair,
                    primary="XFORM-PROJ",
                    secondary=["DYNAMIC", "GEO-TOPO"],
                    operator_id="NATIVE_RELATION_COMPLEMENT",
                    rule_id="NATIVE_MOVEMENT_EXPLICIT_FRAME",
                    rationale="The source-native movement question carries an explicit reference frame, so the frame-qualified post relation is primary.",
                    confidence=0.98,
                )
            return _result(
                pair,
                primary="GEO-TOPO",
                secondary=["DYNAMIC"],
                operator_id="NATIVE_RELATION_COMPLEMENT",
                rule_id="NATIVE_MOVEMENT_RELATION",
                rationale="The claim pair directly contrasts mutually exclusive spatial relations; the source intervention is required to select the post-state relation, but no explicit projection/reference-frame field is released.",
                confidence=0.95,
            )
        if predicate == "COUNT" and transition in {"ADDITION", "REMOVAL", "REPLACEMENT"}:
            secondary = ["GEO-TOPO"]
            if transition == "REPLACEMENT":
                secondary.append("IDENTITY")
            return _result(
                pair,
                primary="DYNAMIC",
                secondary=secondary,
                operator_id="NATIVE_COUNT_POST_FACT",
                rule_id="NATIVE_POST_COUNT_DYNAMIC",
                rationale="The question asks for an exact post-state count after an addition, removal, or replacement; scene cardinality is a supporting dependency.",
                confidence=0.98,
            )
        if predicate == "EXISTS_IN_WORLD" and transition == "ATTRIBUTE":
            return _result(
                pair,
                primary="IDENTITY",
                secondary=["DYNAMIC"],
                operator_id="NATIVE_EXISTENCE_FLIP",
                rule_id="NATIVE_ATTRIBUTE_PERSISTENCE",
                rationale="The direct conflict concerns persistence of a particular object instance across an attribute change, while the intervention supplies the temporal branch.",
                confidence=0.92,
            )
        if predicate == "EXISTS_IN_WORLD" and transition in {"ADDITION", "REMOVAL", "REPLACEMENT"}:
            return _result(
                pair,
                primary="DYNAMIC",
                secondary=["IDENTITY"],
                operator_id="NATIVE_EXISTENCE_FLIP",
                rule_id="NATIVE_POST_EXISTENCE_DYNAMIC",
                rationale="The direct decision is whether a specific instance exists after an object-level intervention; instance persistence is the secondary dependency.",
                confidence=0.96,
            )
        raise ValueError(
            f"{pair_id}: unsupported native combination transition={transition!r}, "
            f"intervention_type={intervention_type!r}, predicate={predicate!r}"
        )

    raise ValueError(f"{pair_id}: unsupported l4_origin {origin!r}")

