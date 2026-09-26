from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.geometry_relations import INVERSE_PREDICATE, strict_separated_relation
from spaceconflict.hypo3d_l4.resolve_targets import resolve_unique_object_ref


RELATION_MAP = {
    "left_of": "LEFT_OF", "right_of": "RIGHT_OF", "in_front_of": "FRONT_OF",
    "behind": "BEHIND", "above": "ABOVE", "below": "BELOW",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row["scene_id"]), str(row["change_id"]), str(row.get("question_id") or row.get("source_question_id"))


def resolve_unique(scene: dict[str, Any], ref_text: str) -> dict[str, Any] | None:
    resolved, _ = resolve_unique_object_ref(ref_text, list(scene.get("objects", [])))
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    parsed = {key(row): row for row in read_jsonl(args.parsed)}
    oracles = {key(row): row for row in read_jsonl(args.oracles)}
    resolutions = {key(row): row for row in read_jsonl(args.resolutions)}
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    counters: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []

    for current_key in sorted(parsed.keys() & oracles.keys()):
        oracle = oracles[current_key]
        atoms = oracle.get("normalized_atoms") or []
        if len(atoms) != 1 or atoms[0].get("predicate") not in INVERSE_PREDICATE:
            continue
        counters["single_relation_oracle"] += 1
        intervention = parsed[current_key]["intervention"]
        if intervention.get("type") != "MOVEMENT":
            counters["reject_not_movement"] += 1
            continue
        explicit = intervention.get("explicit_relations") or []
        if len(explicit) != 1 or explicit[0].get("predicate_text") not in RELATION_MAP:
            counters["reject_no_single_supported_explicit_relation"] += 1
            continue
        relation = RELATION_MAP[str(explicit[0]["predicate_text"])]
        resolution = resolutions.get(current_key)
        targets = resolution.get("resolved_targets") if isinstance(resolution, dict) else None
        scene = catalog.get("scenes", {}).get(current_key[0])
        if not isinstance(scene, dict) or not isinstance(targets, list) or len(targets) != 1:
            counters["reject_target_or_scene_unresolved"] += 1
            continue
        object_by_id = {str(obj.get("object_id")): obj for obj in scene.get("objects", [])}
        target = object_by_id.get(str(targets[0].get("resolved_entity_id")))
        resolved_anchors = resolution.get("resolved_anchors") or []
        anchor = (
            object_by_id.get(str(resolved_anchors[0].get("resolved_entity_id")))
            if len(resolved_anchors) == 1
            else resolve_unique(scene, str(explicit[0].get("anchor_ref_text") or ""))
        )
        if target is None or anchor is None:
            counters["reject_anchor_unresolved"] += 1
            continue
        atom = atoms[0]
        subject_ref, object_ref = str(atom.get("subject") or ""), str(atom.get("object") or "")
        subject_obj, object_obj = resolve_unique(scene, subject_ref), resolve_unique(scene, object_ref)
        if subject_obj is target:
            desired_relation, third = str(atom["predicate"]), object_obj
        elif object_obj is target:
            desired_relation, third = INVERSE_PREDICATE[str(atom["predicate"])], subject_obj
        else:
            counters["reject_oracle_target_unresolved"] += 1
            continue
        if desired_relation != relation:
            counters["reject_relation_not_transitive_match"] += 1
            continue
        if third is None or third is anchor or third is target:
            counters["reject_no_distinct_third_object"] += 1
            continue
        if not strict_separated_relation(anchor, relation, third):
            counters["reject_anchor_third_geometry_not_proven"] += 1
            continue
        counters["proof_safe_transitive_core_candidate"] += 1
        candidates.append({
            "scene_id": current_key[0], "change_id": current_key[1], "question_id": current_key[2],
            "target_id": target["object_id"], "anchor_id": anchor["object_id"],
            "third_object_id": third["object_id"], "relation": relation,
            "post_oracle_id": oracle["oracle_id"],
            "proof_rule": "EXPLICIT_MOVE_RELATION_PLUS_STRICT_PRE_RELATION_TRANSITIVITY",
        })

    report = {
        "schema_version": "hypo3d_geometry_relation_feasibility_v2_1",
        "status": "GEOMETRY_RELATION_FEASIBILITY_AUDITED",
        "counts": dict(sorted(counters.items())),
        "candidate_count": len(candidates),
        "truth_policy": "OFFICIAL_9DOF_BBOX_STRICT_AXIS_SEPARATION_ONLY",
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (args.parsed, args.oracles, args.resolutions, args.catalog)
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "candidates.geometry_relation_core_v2_1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in candidates)
    )
    (args.output_dir / "report.geometry_relation_core_v2_1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
