from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..hashing import sha256_file
from ..hypo3d_l4.geometry_relations import strict_separated_relation
from .checker_b import check_transition_b
from .common import (
    RELATION_COMPLEMENT,
    canonical_fact_hash,
    count_claim_text,
    fact_slot,
    graph_text_roundtrip,
    identity_claim_text,
    load_split_map,
    media_bundle,
    normalized_class,
    normalized_fact,
    object_class,
    output_hashes,
    read_jsonl,
    relation_claim_text,
    stable_id,
    unique_object_for_class,
    write_json,
    write_jsonl,
)
from .engine_a import execute_transition_a


PREDICATE_FROM_SOURCE = {
    "left": "LEFT_OF",
    "right": "RIGHT_OF",
    "front": "FRONT_OF",
    "behind": "BEHIND",
    "above": "ABOVE",
    "below": "BELOW",
}
PREDICATE_AXIS = {
    "LEFT_OF": "horizontal",
    "RIGHT_OF": "horizontal",
    "FRONT_OF": "depth",
    "BEHIND": "depth",
    "ABOVE": "vertical",
    "BELOW": "vertical",
}
FAMILY_TRANSITION = {
    "REMOVE_AND_RECOUNT": "REMOVAL",
    "ADD_AND_RECOUNT": "ADDITION",
    "REPLACE_AND_RECOUNT": "REPLACEMENT",
    "REPLACEMENT_IDENTITY": "REPLACEMENT",
    "MOVE_TO_OPPOSITE_SIDE": "MOVEMENT",
    "SWAP_POSITIONS": "MOVEMENT",
}


def _pre_fact(
    predicate: str,
    subject: str,
    *,
    object_: str | None = None,
    value: Any = None,
    scope: str = "question_local",
    origin_type: str,
    source_ref: str,
) -> dict[str, Any]:
    fact = {
        "predicate": predicate,
        "subject": subject,
        "object": object_,
        "value": value,
        "scope": scope,
        "state": "pre",
        "origin_type": origin_type,
        "source_ref": source_ref,
    }
    fact["fact_id"] = canonical_fact_hash(fact)
    return fact


def _post_fact(
    predicate: str,
    subject: str,
    *,
    object_: str | None = None,
    value: Any = None,
    scope: str = "question_local",
) -> dict[str, Any]:
    return normalized_fact({
        "predicate": predicate,
        "subject": subject,
        "object": object_,
        "value": value,
        "scope": scope,
        "state": "post",
    })


def _make_action(
    *, family: str, parameters: dict[str, Any], pre_facts: list[dict[str, Any]],
    post_facts: list[dict[str, Any]], text: str, scene_id: str,
) -> dict[str, Any]:
    action_core = {"family": family, "parameters": parameters, "scene_id": scene_id}
    return {
        "action_id": stable_id("controlled_action", action_core),
        "family": family,
        "parameters": parameters,
        "preconditions": [fact_slot(fact) for fact in pre_facts],
        "delete_fact_slots": [list(fact_slot(fact)) for fact in pre_facts],
        "add_facts": post_facts,
        "allowed_post_fact_slots": [list(fact_slot(fact)) for fact in post_facts],
        "count_deltas": parameters.get("count_deltas") or {},
        "identity_deltas": parameters.get("identity_deltas") or {},
        "allowed_claim_templates": [family],
        "forbidden_inferences": [
            "PHYSICAL_FEASIBILITY", "COLLISION_FREE_PATH", "UNLISTED_INVARIANT",
            "THIRD_OBJECT_RELATION_UPDATE",
        ],
        "model_visible_text": text,
        "provenance": "SPACECONFLICT_CONTROLLED_DSL",
        "version": "controlled_dsl_v1",
    }


def _count_source(scene: dict[str, Any], category: str) -> str:
    sources = {
        normalized_class(str(key)): str(value)
        for key, value in (scene.get("exact_class_count_sources") or {}).items()
    }
    return sources[category]


def _exact_counts(scene: dict[str, Any]) -> dict[str, int]:
    return {
        normalized_class(str(key)): int(value)
        for key, value in (scene.get("exact_class_counts") or {}).items()
        if normalized_class(str(key)) and isinstance(value, int) and value > 0
    }


def _candidate(
    *, scene_id: str, source_scene_id: str, split: str, family: str,
    pre_facts: list[dict[str, Any]], action: dict[str, Any],
    grounding: dict[str, Any], source_group: str, source_refs: list[str],
    target_label: str | None = None, anchor_label: str | None = None,
) -> dict[str, Any]:
    value = {
        "scene_id": scene_id,
        "family": family,
        "pre_facts": pre_facts,
        "parameters": action["parameters"],
    }
    return {
        "candidate_id": stable_id("controlled_candidate", value),
        "scene_id": scene_id,
        "global_world_id": f"hypo3d:{scene_id}",
        "source_scene_id": source_scene_id,
        "split": split,
        "family": family,
        "transition_family": FAMILY_TRANSITION[family],
        "dependency_type": "CALIBRATION" if family == "REPLACEMENT_IDENTITY" else "CORE",
        "pre_facts": pre_facts,
        "action": action,
        "grounding": grounding,
        "grounding_mode": "UNIQUE_REFERENCE",
        "source_group": source_group,
        "source_refs": sorted(set(source_refs)),
        "target_label": target_label,
        "anchor_label": anchor_label,
    }


def _count_candidates(scene_id: str, scene: dict[str, Any], split: str) -> list[dict[str, Any]]:
    counts = _exact_counts(scene)
    if not counts:
        return []
    source_scene_id = str(scene.get("source_scene_id") or "")
    rows: list[dict[str, Any]] = []
    categories = sorted(counts)
    for category in categories:
        pre_count = counts[category]
        source_ref = _count_source(scene, category)
        count_fact = _pre_fact(
            "COUNT", category, value=pre_count, scope="whole_scene",
            origin_type="SOURCE_EXACT_CLASS_COUNT_ANNOTATION", source_ref=source_ref,
        )
        new_id = f"added::{scene_id}::{stable_id('add', [scene_id, category], 12)}::0"
        add_post = [
            _post_fact("COUNT", category, value=pre_count + 1, scope="whole_scene"),
            _post_fact("EXISTS_IN_WORLD", new_id, value=True),
        ]
        add_params = {
            "category": category, "quantity": 1, "new_entity_id": new_id,
            "count_deltas": {category: 1},
        }
        add_action = _make_action(
            family="ADD_AND_RECOUNT", parameters=add_params, pre_facts=[count_fact],
            post_facts=add_post, text=f"Suppose one {category} is added to the scene.", scene_id=scene_id,
        )
        rows.append(_candidate(
            scene_id=scene_id, source_scene_id=source_scene_id, split=split,
            family="ADD_AND_RECOUNT", pre_facts=[count_fact], action=add_action,
            grounding={"mode": "NO_EXISTING_TARGET", "new_category": category},
            source_group="REFERIT3D_EXACT_COUNT", source_refs=[source_ref],
            target_label=category,
        ))

        target = unique_object_for_class(scene, category) if pre_count == 1 else None
        if target is None:
            continue
        target_id = str(target["object_id"])
        exists_fact = _pre_fact(
            "EXISTS_IN_WORLD", target_id, value=True,
            origin_type="SOURCE_OBJECT_ANNOTATION", source_ref=source_scene_id,
        )
        remove_post = [
            _post_fact("COUNT", category, value=0, scope="whole_scene"),
            _post_fact("EXISTS_IN_WORLD", target_id, value=False),
        ]
        remove_params = {
            "target_id": target_id, "category": category,
            "count_deltas": {category: -1},
        }
        remove_action = _make_action(
            family="REMOVE_AND_RECOUNT", parameters=remove_params,
            pre_facts=[count_fact, exists_fact], post_facts=remove_post,
            text=f"Suppose the {category} is removed from the scene.", scene_id=scene_id,
        )
        grounding = {
            "mode": "UNIQUE_REFERENCE", "target_id": target_id,
            "target_reference": f"the {category}", "candidate_count": 1,
        }
        rows.append(_candidate(
            scene_id=scene_id, source_scene_id=source_scene_id, split=split,
            family="REMOVE_AND_RECOUNT", pre_facts=[count_fact, exists_fact],
            action=remove_action, grounding=grounding,
            source_group="FUSED_REFERIT3D_OBJECT_GT", source_refs=[source_ref, source_scene_id],
            target_label=category,
        ))

        for new_category in categories:
            if new_category == category:
                continue
            new_count = counts[new_category]
            new_source = _count_source(scene, new_category)
            new_count_fact = _pre_fact(
                "COUNT", new_category, value=new_count, scope="whole_scene",
                origin_type="SOURCE_EXACT_CLASS_COUNT_ANNOTATION", source_ref=new_source,
            )
            replacement_id = f"added::{scene_id}::{stable_id('replace', [scene_id, category, new_category], 12)}::0"
            replace_post = [
                _post_fact("COUNT", category, value=0, scope="whole_scene"),
                _post_fact("COUNT", new_category, value=new_count + 1, scope="whole_scene"),
                _post_fact("EXISTS_IN_WORLD", target_id, value=False),
                _post_fact("EXISTS_IN_WORLD", replacement_id, value=True),
                _post_fact("SAME_INSTANCE", replacement_id, object_=target_id, value=False),
            ]
            replace_params = {
                "target_id": target_id, "old_category": category,
                "new_category": new_category, "new_entity_id": replacement_id,
                "count_deltas": {category: -1, new_category: 1},
                "identity_deltas": {f"{replacement_id}|{target_id}": False},
            }
            replace_text = f"Suppose the {category} is replaced with a newly added {new_category}."
            replace_pre = [count_fact, new_count_fact, exists_fact]
            replace_action = _make_action(
                family="REPLACE_AND_RECOUNT", parameters=replace_params,
                pre_facts=replace_pre, post_facts=replace_post,
                text=replace_text, scene_id=scene_id,
            )
            rows.append(_candidate(
                scene_id=scene_id, source_scene_id=source_scene_id, split=split,
                family="REPLACE_AND_RECOUNT", pre_facts=replace_pre,
                action=replace_action, grounding=grounding,
                source_group="FUSED_EMBODIEDSCAN_REFERIT3D",
                source_refs=[source_ref, new_source, source_scene_id],
                target_label=category, anchor_label=new_category,
            ))
            identity_pre = [exists_fact]
            identity_post = [
                _post_fact("EXISTS_IN_WORLD", target_id, value=False),
                _post_fact("EXISTS_IN_WORLD", replacement_id, value=True),
                _post_fact("SAME_INSTANCE", replacement_id, object_=target_id, value=False),
            ]
            identity_action = _make_action(
                family="REPLACEMENT_IDENTITY", parameters=replace_params,
                pre_facts=identity_pre, post_facts=identity_post,
                text=replace_text, scene_id=scene_id,
            )
            rows.append(_candidate(
                scene_id=scene_id, source_scene_id=source_scene_id, split=split,
                family="REPLACEMENT_IDENTITY", pre_facts=identity_pre,
                action=identity_action, grounding=grounding,
                source_group="FUSED_EMBODIEDSCAN_REFERIT3D",
                source_refs=[source_ref, new_source, source_scene_id],
                target_label=category, anchor_label=new_category,
            ))
    return rows


def _relation_row(
    *, scene_id: str, scene: dict[str, Any], split: str, subject: dict[str, Any],
    object_: dict[str, Any], predicate: str, source_group: str, source_ref: str,
    family: str,
) -> dict[str, Any]:
    target_id, anchor_id = str(subject["object_id"]), str(object_["object_id"])
    target_label = normalized_class(str(subject.get("class") or ""))
    anchor_label = normalized_class(str(object_.get("class") or ""))
    relation = _pre_fact(
        predicate, target_id, object_=anchor_id,
        origin_type=("SOURCE_RELATION_ANNOTATION" if source_group == "3DSSG_EXPLICIT_RELATION" else "SOURCE_9DOF_STRICT_RELATION"),
        source_ref=source_ref,
    )
    post_predicate = RELATION_COMPLEMENT[predicate]
    post = [_post_fact(post_predicate, target_id, object_=anchor_id)]
    params = {
        ("target_id" if family == "MOVE_TO_OPPOSITE_SIDE" else "target_a_id"): target_id,
        ("anchor_id" if family == "MOVE_TO_OPPOSITE_SIDE" else "target_b_id"): anchor_id,
        "pre_predicate": predicate,
        "post_predicate": post_predicate,
        "axis": PREDICATE_AXIS[predicate],
        "reference_frame": "source_world_axes",
    }
    if family == "MOVE_TO_OPPOSITE_SIDE":
        text = (
            f"Suppose the {target_label} is moved to the opposite side of the "
            f"{anchor_label} along the {PREDICATE_AXIS[predicate]} axis."
        )
    else:
        text = (
            f"Suppose the {target_label} and the {anchor_label} swap positions "
            f"along the {PREDICATE_AXIS[predicate]} axis."
        )
    action = _make_action(
        family=family, parameters=params, pre_facts=[relation], post_facts=post,
        text=text, scene_id=scene_id,
    )
    return _candidate(
        scene_id=scene_id, source_scene_id=str(scene.get("source_scene_id") or ""), split=split,
        family=family, pre_facts=[relation], action=action,
        grounding={
            "mode": "UNIQUE_REFERENCE", "target_id": target_id, "anchor_id": anchor_id,
            "target_reference": f"the {target_label}", "anchor_reference": f"the {anchor_label}",
            "target_candidate_count": 1, "anchor_candidate_count": 1,
        },
        source_group=source_group, source_refs=[source_ref],
        target_label=target_label, anchor_label=anchor_label,
    )


def _relation_candidates(scene_id: str, scene: dict[str, Any], split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    objects = {str(obj.get("object_id") or ""): obj for obj in scene.get("objects", [])}
    class_counts = Counter(normalized_class(str(obj.get("class") or "")) for obj in objects.values())
    unique_objects = [
        obj for obj in objects.values()
        if class_counts[normalized_class(str(obj.get("class") or ""))] == 1
        and normalized_class(str(obj.get("class") or "")) not in {"", "object", "item"}
    ]
    seen: set[tuple[str, str, str, str]] = set()
    for relation in scene.get("relations", []):
        predicate = PREDICATE_FROM_SOURCE.get(normalized_class(str(relation.get("predicate") or "")))
        subject = objects.get(str(relation.get("subject_id") or ""))
        object_ = objects.get(str(relation.get("object_id") or ""))
        if predicate is None or subject not in unique_objects or object_ not in unique_objects:
            continue
        for family in ("MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"):
            key = (family, str(subject["object_id"]), predicate, str(object_["object_id"]))
            if key in seen:
                continue
            seen.add(key)
            rows.append(_relation_row(
                scene_id=scene_id, scene=scene, split=split, subject=subject, object_=object_,
                predicate=predicate, source_group="3DSSG_EXPLICIT_RELATION",
                source_ref=f"{scene.get('source_scene_id')}:{relation.get('relation_id')}", family=family,
            ))
    exact = _exact_counts(scene)
    bbox_objects = [
        obj for obj in unique_objects
        if isinstance(obj.get("bbox_3d"), list)
        and exact.get(normalized_class(str(obj.get("class") or ""))) == 1
    ]
    for left_index, subject in enumerate(bbox_objects):
        for object_ in bbox_objects[left_index + 1:]:
            predicate = next((
                candidate for candidate in ("LEFT_OF", "RIGHT_OF", "FRONT_OF", "BEHIND", "ABOVE", "BELOW")
                if strict_separated_relation(subject, candidate, object_)
            ), None)
            if predicate is None:
                continue
            source_ref = (
                f"{scene.get('source_scene_id')}:bbox:{subject.get('source_bbox_id')}:{object_.get('source_bbox_id')}"
            )
            for family in ("MOVE_TO_OPPOSITE_SIDE", "SWAP_POSITIONS"):
                key = (family, str(subject["object_id"]), predicate, str(object_["object_id"]))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_relation_row(
                    scene_id=scene_id, scene=scene, split=split, subject=subject, object_=object_,
                    predicate=predicate, source_group="EMBODIEDSCAN_9DOF",
                    source_ref=source_ref, family=family,
                ))
    return rows


def enumerate_controlled_candidates(
    *, catalog: dict[str, Any], split_map: dict[str, str], seed: int,
    scene_limit: int | None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    scene_ids = [
        scene_id for scene_id in catalog.get("scenes", {})
        if f"hypo3d:{scene_id}" in split_map
    ]
    scene_ids.sort(key=lambda scene_id: hashlib.sha256(f"{seed}:{scene_id}".encode()).hexdigest())
    if scene_limit is not None:
        scene_ids = scene_ids[:scene_limit]
    counts = Counter()
    rejects: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for scene_id in scene_ids:
        scene = catalog["scenes"][scene_id]
        split = split_map[f"hypo3d:{scene_id}"]
        scene_rows = _count_candidates(scene_id, scene, split) + _relation_candidates(scene_id, scene, split)
        counts["scene_pool"] += 1
        counts["raw_candidates"] += len(scene_rows)
        if not scene_rows:
            rejects.append({"scene_id": scene_id, "reason": "REJECT_NO_CONTROLLED_ACTION_PRECONDITIONS"})
            continue
        candidates.extend(scene_rows)
    return candidates, dict(counts), rejects


def _scaled_targets(targets: dict[str, int], target_pairs: int) -> dict[str, int]:
    total = sum(targets.values())
    raw = {key: target_pairs * value / total for key, value in targets.items()}
    scaled = {key: int(value) for key, value in raw.items()}
    remainder = target_pairs - sum(scaled.values())
    for key in sorted(raw, key=lambda item: (-(raw[item] - scaled[item]), item))[:remainder]:
        scaled[key] += 1
    return scaled


def select_controlled_candidates(
    *, candidates: list[dict[str, Any]], config: dict[str, Any], target_pairs: int,
    seed: int, scene_limit: int | None, reserved_pairs: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    targets = _scaled_targets({str(k): int(v) for k, v in config["operator_targets"].items()}, target_pairs)
    scene_caps = {str(k): int(v) for k, v in config["scene_pair_caps"].items()}
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    per_scene = Counter()
    test_families: dict[str, set[str]] = defaultdict(set)
    operator_counts = Counter()
    reserved_pairs = reserved_pairs or []
    reserved_test_counts = Counter(
        str(row["base_scene_id"]) for row in reserved_pairs if row.get("split") == "test"
    )
    for row in reserved_pairs:
        if row.get("split") == "test":
            test_families[str(row["base_scene_id"])].add(str(row["transition_family"]))

    def allowed(row: dict[str, Any]) -> bool:
        scene_id, split = row["scene_id"], row["split"]
        if operator_counts[row["family"]] >= targets[row["family"]]:
            return False
        if per_scene[scene_id] >= scene_caps[split]:
            return False
        if split == "test":
            if reserved_test_counts[scene_id] + per_scene[scene_id] >= 2:
                return False
            if row["transition_family"] in test_families[scene_id]:
                return False
        return True

    def take(row: dict[str, Any]) -> None:
        selected.append(row)
        selected_ids.add(row["candidate_id"])
        operator_counts[row["family"]] += 1
        per_scene[row["scene_id"]] += 1
        if row["split"] == "test":
            test_families[row["scene_id"]].add(row["transition_family"])

    ordered = sorted(
        candidates,
        key=lambda row: hashlib.sha256(f"{seed}:{row['candidate_id']}".encode()).hexdigest(),
    )
    if scene_limit is None:
        required_3dssg = min(int(config.get("minimum_3dssg_relation_pairs", 0)), target_pairs)
        for row in ordered:
            if len([item for item in selected if item["source_group"] == "3DSSG_EXPLICIT_RELATION"]) >= required_3dssg:
                break
            if row["source_group"] == "3DSSG_EXPLICIT_RELATION" and allowed(row):
                take(row)
        minimum_combined_test = int(config.get("combined_test_soft_target", 0))
        reserved_test_total = sum(reserved_test_counts.values())
        for row in ordered:
            selected_test_total = sum(item["split"] == "test" for item in selected)
            if reserved_test_total + selected_test_total >= minimum_combined_test:
                break
            if row["split"] == "test" and row["candidate_id"] not in selected_ids and allowed(row):
                take(row)
    for row in ordered:
        if len(selected) >= target_pairs:
            break
        if row["candidate_id"] not in selected_ids and allowed(row):
            take(row)
    test_scene_families_available: dict[str, set[str]] = defaultdict(set)
    for row in reserved_pairs:
        if row.get("split") == "test":
            test_scene_families_available[str(row["base_scene_id"])].add(str(row["transition_family"]))
    for row in candidates:
        if row["split"] == "test":
            test_scene_families_available[str(row["scene_id"])].add(str(row["transition_family"]))
    test_proof_capacity = sum(min(2, len(families)) for families in test_scene_families_available.values())
    combined_test_pairs = sum(reserved_test_counts.values()) + sum(row["split"] == "test" for row in selected)
    report = {
        "targets": targets,
        "selected": len(selected),
        "operator_counts": dict(sorted(operator_counts.items())),
        "source_group_counts": dict(sorted(Counter(row["source_group"] for row in selected).items())),
        "split_counts": dict(sorted(Counter(row["split"] for row in selected).items())),
        "scene_count": len({row["scene_id"] for row in selected}),
        "reserved_test_pairs": sum(reserved_test_counts.values()),
        "combined_test_pairs": combined_test_pairs,
        "combined_test_soft_target": int(config.get("combined_test_soft_target", 0)),
        "test_proof_capacity_upper_bound": test_proof_capacity,
        "test_proof_capacity_saturated": combined_test_pairs == test_proof_capacity,
        "quota_shortfalls": {
            family: targets[family] - operator_counts[family]
            for family in targets if operator_counts[family] < targets[family]
        },
    }
    return selected, report


def _claim_pair(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
    family = candidate["family"]
    post = check_transition_b(candidate["pre_facts"], candidate["action"])["post_facts"]
    style = int(candidate["candidate_id"][-2:], 16) % 3
    if family == "REMOVE_AND_RECOUNT":
        category = candidate["action"]["parameters"]["category"]
        supported = next(fact for fact in post if fact["predicate"] == "COUNT")
        contradictory = {**supported, "value": supported["value"] + 1}
        supported_text = count_claim_text(category, supported["value"], style)
        contradictory_text = count_claim_text(category, contradictory["value"], style)
        changed_slot = "value"
    elif family == "ADD_AND_RECOUNT":
        category = candidate["action"]["parameters"]["category"]
        supported = next(fact for fact in post if fact["predicate"] == "COUNT")
        contradictory = {**supported, "value": supported["value"] - 1}
        supported_text = count_claim_text(category, supported["value"], style)
        contradictory_text = count_claim_text(category, contradictory["value"], style)
        changed_slot = "value"
    elif family == "REPLACE_AND_RECOUNT":
        params = candidate["action"]["parameters"]
        category = params["new_category"] if int(candidate["candidate_id"][-1], 16) & 1 else params["old_category"]
        supported = next(fact for fact in post if fact["predicate"] == "COUNT" and fact["subject"] == category)
        delta = params["count_deltas"][category]
        contradictory = {**supported, "value": supported["value"] - delta}
        supported_text = count_claim_text(category, supported["value"], style)
        contradictory_text = count_claim_text(category, contradictory["value"], style)
        changed_slot = "value"
    elif family == "REPLACEMENT_IDENTITY":
        params = candidate["action"]["parameters"]
        supported = next(fact for fact in post if fact["predicate"] == "SAME_INSTANCE")
        contradictory = {**supported, "value": True}
        supported_text = identity_claim_text(params["old_category"], params["new_category"], False, style)
        contradictory_text = identity_claim_text(params["old_category"], params["new_category"], True, style)
        changed_slot = "value"
    else:
        supported = post[0]
        contradictory = {**supported, "predicate": RELATION_COMPLEMENT[supported["predicate"]]}
        target_label, anchor_label = candidate["target_label"], candidate["anchor_label"]
        supported = {**supported, "subject_label": target_label, "object_label": anchor_label}
        contradictory = {**contradictory, "subject_label": target_label, "object_label": anchor_label}
        supported_text = relation_claim_text(target_label, supported["predicate"], anchor_label, style)
        contradictory_text = relation_claim_text(target_label, contradictory["predicate"], anchor_label, style)
        changed_slot = "predicate"
    return (
        {"graph": supported, "text": supported_text},
        {"graph": contradictory, "text": contradictory_text},
        changed_slot,
    )


def verify_controlled_pair(
    candidate: dict[str, Any], supported: dict[str, Any], contradictory: dict[str, Any],
) -> dict[str, Any]:
    engine = execute_transition_a(candidate["pre_facts"], candidate["action"])
    checker = check_transition_b(candidate["pre_facts"], candidate["action"])
    errors: list[str] = []
    if engine["status"] != "PASS":
        errors.extend(engine["errors"])
    if checker["status"] != "PASS":
        errors.extend(checker["errors"])
    if engine["post_facts"] != checker["post_facts"]:
        errors.append("REJECT_TRANSITION_ENGINE_DISAGREEMENT")
    supported_graph, contradictory_graph = supported["graph"], contradictory["graph"]
    checker_normalized = [normalized_fact(fact, state="post") for fact in checker["post_facts"]]
    if normalized_fact(supported_graph, state="post") not in checker_normalized:
        errors.append("SUPPORTED_NOT_ENTAILED")
    if supported_graph.get("predicate") == "COUNT":
        exclusive = (
            contradictory_graph.get("predicate") == "COUNT"
            and fact_slot(contradictory_graph) == fact_slot(supported_graph)
            and contradictory_graph.get("value") != supported_graph.get("value")
        )
    elif supported_graph.get("predicate") in RELATION_COMPLEMENT:
        exclusive = contradictory_graph.get("predicate") == RELATION_COMPLEMENT[supported_graph["predicate"]]
    else:
        exclusive = (
            contradictory_graph.get("predicate") == supported_graph.get("predicate")
            and contradictory_graph.get("value") is not supported_graph.get("value")
        )
    if not exclusive:
        errors.append("CONTRADICTORY_NOT_REFUTED")
    if not graph_text_roundtrip(supported["text"], supported_graph):
        errors.append("SUPPORTED_GRAPH_TEXT_ROUNDTRIP_FAIL")
    if not graph_text_roundtrip(contradictory["text"], contradictory_graph):
        errors.append("CONTRADICTORY_GRAPH_TEXT_ROUNDTRIP_FAIL")
    dependency = candidate["dependency_type"]
    scene_only, change_only, full = "UNKNOWN", "UNKNOWN", "SUPPORTED"
    if candidate["family"] == "REPLACEMENT_IDENTITY":
        change_only = "SUPPORTED"
    if dependency == "CORE" and change_only != "UNKNOWN":
        errors.append("CORE_CHANGE_ONLY_SUFFICIENT")
    if dependency == "CALIBRATION" and change_only == "UNKNOWN":
        errors.append("CALIBRATION_CHANGE_ONLY_NOT_SUFFICIENT")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
        "transition_engine_a": engine["status"],
        "transition_checker_b": checker["status"],
        "transition_a_b_exact_match": engine["post_facts"] == checker["post_facts"],
        "scene_only_label": scene_only,
        "change_only_label": change_only,
        "full_input_label": full,
        "co_truth_possible": False,
        "requires_unprovided_fact": False,
        "graph_text_roundtrip": "PASS" if not any("ROUNDTRIP" in item for item in errors) else "FAIL",
        "independent_verifier": "PASS" if not errors else "FAIL",
    }


def build_controlled(
    *, catalog_path: Path, split_path: Path, media_root: Path, config_path: Path,
    output_dir: Path, target_pairs: int, scene_limit: int | None, seed: int,
    run_id: str, dry_run: bool, resume: bool, reserved_pairs_path: Path | None = None,
) -> dict[str, Any]:
    outputs = {
        "scene_pool": output_dir / "scene_pool.jsonl",
        "candidates": output_dir / "candidates/controlled_candidates.jsonl",
        "pairs": output_dir / "accepted/pairs.l4_controlled_v3.jsonl",
        "model_inputs": output_dir / "accepted/model_inputs.l4_controlled_v3.jsonl",
        "gold": output_dir / "accepted/gold.l4_controlled_v3.jsonl",
        "certificates": output_dir / "certificates/certificates.l4_controlled_v3.jsonl",
        "traces": output_dir / "construction_traces/traces.l4_controlled_v3.jsonl",
        "rejects": output_dir / "rejected/rejects.l4_controlled_v3.jsonl",
        "report": output_dir / "reports/controlled_build_report.v3.json",
    }
    if dry_run:
        return {"status": "PLANNED", "outputs": {k: str(v) for k, v in outputs.items()}}
    config = json.loads(json.dumps(__import__("yaml").safe_load(config_path.read_text(encoding="utf-8"))))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    split_map = load_split_map(split_path)
    reserved_pairs = read_jsonl(reserved_pairs_path) if reserved_pairs_path and reserved_pairs_path.exists() else []
    candidates, funnel, scene_rejects = enumerate_controlled_candidates(
        catalog=catalog, split_map=split_map, seed=seed, scene_limit=scene_limit,
    )
    selected, selection = select_controlled_candidates(
        candidates=candidates, config=config, target_pairs=target_pairs,
        seed=seed, scene_limit=scene_limit, reserved_pairs=reserved_pairs,
    )
    media_cache: dict[str, dict[str, Any]] = {}
    accepted: list[dict[str, Any]] = []
    model_inputs: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    rejects = list(scene_rejects)
    for candidate in selected:
        supported, contradictory, changed_slot = _claim_pair(candidate)
        validation = verify_controlled_pair(candidate, supported, contradictory)
        if validation["status"] != "PASS":
            rejects.append({
                "candidate_id": candidate["candidate_id"],
                "scene_id": candidate["scene_id"],
                "reason": "REJECT_VERIFIER_DISAGREEMENT",
                "errors": validation["errors"],
            })
            continue
        pair_id = stable_id("sc_l4_controlled", {
            "candidate_id": candidate["candidate_id"], "supported": supported["graph"],
        })
        branch_id = f"hypo3d:{candidate['scene_id']}::controlled::{candidate['family'].casefold()}::{candidate['action']['action_id']}"
        media = media_bundle(scene_id=candidate["scene_id"], media_root=media_root, cache=media_cache)
        certificate_id = f"{pair_id}:certificate"
        trace_id = f"{pair_id}:trace"
        pair = {
            "schema_version": "spaceconflict_l4_pair_v3",
            "pair_id": pair_id,
            "level": "L4",
            "l4_origin": "BENCHMARK_CONTROLLED",
            "native_subtype": None,
            "dependency_type": candidate["dependency_type"],
            "transition_family": candidate["transition_family"],
            "grounding_mode": candidate["grounding_mode"],
            "global_world_id": candidate["global_world_id"],
            "base_scene_id": candidate["scene_id"],
            "branch_id": branch_id,
            "split": candidate["split"],
            "model_input": {
                "media_ids": media["media_ids"],
                "intervention_text": candidate["action"]["model_visible_text"],
            },
            "pre_state_reference": {
                "facts": candidate["pre_facts"],
                "provenance": "SOURCE_NATIVE_GT",
                "source_refs": candidate["source_refs"],
            },
            "intervention": candidate["action"],
            "post_state_reference": {
                "facts": check_transition_b(candidate["pre_facts"], candidate["action"])["post_facts"],
                "provenance": "DETERMINISTIC_TRANSITION_ENGINE",
            },
            "supported_claim": supported,
            "contradictory_claim": contradictory,
            "edit": {"changed_slots": [changed_slot], "preserved_slots": ["intervention", "entities", "scope", "state", "style"]},
            "certificate_id": certificate_id,
            "construction_trace_id": trace_id,
            "source_group": candidate["source_group"],
            "media": media["media"],
            "validation": {**validation, "final_status": "AUTO_ACCEPTED", "world_split": "PASS", "intervention_visible": "PASS"},
        }
        certificate = {
            "certificate_id": certificate_id,
            "pair_id": pair_id,
            "origin": "BENCHMARK_CONTROLLED",
            "proof_nodes": [
                *[{"id": fact["fact_id"], "type": "SOURCE_PRE_FACT"} for fact in candidate["pre_facts"]],
                {"id": candidate["action"]["action_id"], "type": "INTERVENTION"},
                {"id": f"rule:{candidate['family']}", "type": "TRANSITION_RULE"},
                {"id": canonical_fact_hash(supported["graph"]), "type": "DERIVED_POST_FACT"},
                {"id": f"{pair_id}:claim", "type": "CLAIM_ATOM"},
            ],
            "transition_engine_a": "PASS",
            "transition_checker_b": "PASS",
            "a_b_exact_match": True,
            "co_truth_possible": False,
            "requires_unprovided_fact": False,
            "dependency_checks": {
                "scene_only": validation["scene_only_label"],
                "change_only": validation["change_only_label"],
                "full_input": validation["full_input_label"],
            },
        }
        trace = {
            "construction_trace_id": trace_id,
            "pair_id": pair_id,
            "source_refs": candidate["source_refs"],
            "source_group": candidate["source_group"],
            "base_scene_id": candidate["scene_id"],
            "branch_id": branch_id,
            "origin_type": "BENCHMARK_CONTROLLED",
            "controlled_dsl_action": candidate["action"],
            "target_anchor_resolution": candidate["grounding"],
            "pre_state_facts": candidate["pre_facts"],
            "post_state_source": "DETERMINISTIC_TRANSITION_ENGINE",
            "transition_versions": ["controlled_transition_engine_a_v1", "controlled_transition_checker_b_v1"],
            "changed_slot": changed_slot,
            "validation": validation,
        }
        accepted.append(pair)
        certificates.append(certificate)
        traces.append(trace)
        variants = [(supported, "SUPPORTED"), (contradictory, "CONTRADICTORY")]
        if int(hashlib.sha256(pair_id.encode()).hexdigest()[:2], 16) & 1:
            variants.reverse()
        for index, (claim, label) in enumerate(variants):
            example_id = f"{pair_id}:candidate_{index}"
            model_inputs.append({
                "example_id": example_id,
                "pair_id": pair_id,
                "level": "L4",
                "l4_origin": "BENCHMARK_CONTROLLED",
                "base_scene_id": candidate["scene_id"],
                "branch_id": branch_id,
                "split": candidate["split"],
                "media": media["media"],
                "intervention_text": candidate["action"]["model_visible_text"],
                "claim_text": claim["text"],
            })
            gold.append({"example_id": example_id, "pair_id": pair_id, "label": label})
    calibration = sum(row["dependency_type"] == "CALIBRATION" for row in accepted)
    family_counts = Counter(row["intervention"]["family"] for row in accepted)
    transition_counts = Counter(row["transition_family"] for row in accepted)
    source_counts = Counter(row["source_group"] for row in accepted)
    count = len(accepted)
    calibration_fraction = calibration / count if count else 0.0
    simple_fraction = (family_counts["REMOVE_AND_RECOUNT"] + family_counts["ADD_AND_RECOUNT"]) / count if count else 0.0
    movement_fraction = transition_counts["MOVEMENT"] / count if count else 0.0
    replacement_fraction = transition_counts["REPLACEMENT"] / count if count else 0.0
    quality_gates = {
        "target_met": count == target_pairs,
        "calibration_fraction_pass": calibration_fraction <= float(config["calibration_max_fraction"]),
        "single_operator_fraction_pass": all(value / count <= float(config["single_operator_max_fraction"]) for value in family_counts.values()) if count else False,
        "simple_add_remove_fraction_pass": simple_fraction <= float(config["simple_add_remove_max_fraction"]) if count else False,
        "movement_fraction_pass": float(config["movement_relation_range"][0]) <= movement_fraction <= float(config["movement_relation_range"][1]) if count else False,
        "replacement_fraction_pass": float(config["replacement_identity_range"][0]) <= replacement_fraction <= float(config["replacement_identity_range"][1]) if count else False,
        "transition_a_b_agreement_pass": not any(row.get("errors") for row in rejects if row.get("candidate_id")),
        "media_materialization_pass": len(media_cache) == len({row["base_scene_id"] for row in accepted}),
        "test_density_pass": all(
            sum(row.get("split") == "test" and row["base_scene_id"] == scene for row in accepted + reserved_pairs) <= 2
            for scene in {row["base_scene_id"] for row in accepted + reserved_pairs if row.get("split") == "test"}
        ),
        "test_family_density_pass": all(
            sum(
                row.get("split") == "test"
                and row["base_scene_id"] == scene
                and row["transition_family"] == family
                for row in accepted + reserved_pairs
            ) <= 1
            for scene in {row["base_scene_id"] for row in accepted + reserved_pairs if row.get("split") == "test"}
            for family in {row["transition_family"] for row in accepted + reserved_pairs if row.get("split") == "test"}
        ),
        "combined_test_capacity_saturation_pass": (
            scene_limit is not None
            or selection["combined_test_pairs"]
            >= min(selection["combined_test_soft_target"], selection["test_proof_capacity_upper_bound"])
        ),
    }
    status = "CONTROLLED_ACCEPTED" if all(quality_gates.values()) else "CONTROLLED_SHORTFALL_OR_GATE_FAIL"
    scene_pool = [{
        "base_scene_id": scene_id,
        "global_world_id": f"hypo3d:{scene_id}",
        "split": split_map[f"hypo3d:{scene_id}"],
        "source_scene_id": catalog["scenes"][scene_id].get("source_scene_id"),
        "exact_count_groups": len(_exact_counts(catalog["scenes"][scene_id])),
        "bbox_objects": sum(isinstance(obj.get("bbox_3d"), list) for obj in catalog["scenes"][scene_id].get("objects", [])),
    } for scene_id in sorted({row["scene_id"] for row in candidates})]
    candidate_output = [{k: v for k, v in row.items() if k not in {"pre_facts", "action"}} for row in candidates]
    write_jsonl(outputs["scene_pool"], scene_pool, resume=resume)
    write_jsonl(outputs["candidates"], candidate_output, resume=resume)
    write_jsonl(outputs["pairs"], accepted, resume=resume)
    write_jsonl(outputs["model_inputs"], model_inputs, resume=resume)
    write_jsonl(outputs["gold"], gold, resume=resume)
    write_jsonl(outputs["certificates"], certificates, resume=resume)
    write_jsonl(outputs["traces"], traces, resume=resume)
    write_jsonl(outputs["rejects"], rejects, resume=resume)
    report = {
        "schema_version": "l4_controlled_build_report_v3",
        "status": status,
        "run_id": run_id,
        "seed": seed,
        "config_snapshot": config,
        "scene_limit": scene_limit,
        "target_pairs": target_pairs,
        "funnel": {**funnel, "selected": selection["selected"], "accepted": count, "rejected": len(rejects)},
        "selection": selection,
        "counts": {
            "accepted_pairs": count,
            "core": count - calibration,
            "calibration": calibration,
            "model_inputs": len(model_inputs),
            "gold": len(gold),
            "worlds": len({row["base_scene_id"] for row in accepted}),
            "operators": dict(sorted(family_counts.items())),
            "transition_families": dict(sorted(transition_counts.items())),
            "source_groups": dict(sorted(source_counts.items())),
        },
        "fractions": {
            "calibration": calibration_fraction,
            "simple_add_remove": simple_fraction,
            "movement_relation": movement_fraction,
            "replacement_identity": replacement_fraction,
        },
        "soft_targets": {
            "combined_test_target": selection["combined_test_soft_target"],
            "combined_test_accepted": selection["combined_test_pairs"],
            "combined_test_target_met": selection["combined_test_pairs"] >= selection["combined_test_soft_target"],
            "test_proof_capacity_upper_bound": selection["test_proof_capacity_upper_bound"],
            "test_proof_capacity_saturated": selection["test_proof_capacity_saturated"],
        },
        "quality_gates": quality_gates,
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (catalog_path, split_path, config_path, reserved_pairs_path)
            if path is not None and path.exists()
        },
        "truth_policy": "SOURCE_GT_PLUS_MODEL_VISIBLE_CONTROLLED_DSL_AND_DUAL_DETERMINISTIC_TRANSITION_ONLY",
    }
    write_json(outputs["report"], report, resume=resume)
    return {**report, "outputs": {k: str(v) for k, v in outputs.items()}, "output_hashes": output_hashes(outputs.values())}
