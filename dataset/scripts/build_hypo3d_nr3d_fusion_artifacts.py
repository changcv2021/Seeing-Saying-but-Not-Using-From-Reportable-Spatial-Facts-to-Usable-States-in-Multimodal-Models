from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.resolve_targets import normalize_ref
from spaceconflict.registry import ROOT


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row["scene_id"]), str(row["change_id"]), str(row["question_id"])


def decode_stimulus(value: str) -> tuple[str, str, int, int, tuple[int, ...]]:
    parts = value.split("-", maxsplit=4)
    if len(parts) not in {4, 5}:
        raise ValueError(f"malformed stimulus_id: {value}")
    scene_id, label, raw_count, raw_target = parts[:4]
    distractors = tuple(int(item) for item in (parts[4].split("-") if len(parts) == 5 else []) if item)
    count, target = int(raw_count), int(raw_target)
    if len(distractors) != count - 1:
        raise ValueError(f"stimulus count mismatch: {value}")
    return scene_id, normalize_ref(label.replace("_", " ")), count, target, distractors


def load_nr3d(path: Path) -> tuple[
    dict[tuple[str, str], tuple[int, ...]], dict[tuple[str, str], set[tuple[str, int]]]
]:
    groups: dict[tuple[str, str], set[tuple[int, ...]]] = defaultdict(set)
    descriptions: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            scene_id, label, count, target, distractors = decode_stimulus(row["stimulus_id"])
            if scene_id != row["scan_id"] or label != normalize_ref(row["instance_type"]):
                raise ValueError(f"Nr3D redundant fields disagree: {row['stimulus_id']}")
            ids = tuple(sorted((target, *distractors)))
            if len(ids) != count or len(set(ids)) != count or target != int(row["target_id"]):
                raise ValueError(f"Nr3D instance set invalid: {row['stimulus_id']}")
            groups[(scene_id, label)].add(ids)
            description = normalize_ref(row["utterance"])
            if description:
                descriptions[(scene_id, description)].add((label, target))
    inconsistent = [key for key, values in groups.items() if len(values) != 1]
    if inconsistent:
        raise ValueError(f"inconsistent Nr3D scene/class groups: {inconsistent[:3]}")
    return {key: next(iter(values)) for key, values in groups.items()}, descriptions


def load_exact_stimulus_groups(path: Path, source_name: str) -> dict[tuple[str, str], tuple[int, ...]]:
    groups: dict[tuple[str, str], set[tuple[int, ...]]] = defaultdict(set)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scene_id, label, count, target, distractors = decode_stimulus(row["stimulus_id"])
            ids = tuple(sorted((target, *distractors)))
            if (
                scene_id != row["scan_id"] or label != normalize_ref(row["instance_type"])
                or target != int(row["target_id"]) or len(ids) != count or len(set(ids)) != count
            ):
                raise ValueError(f"{source_name} redundant fields disagree: {row['stimulus_id']}")
            groups[(scene_id, label)].add(ids)
    inconsistent = [key for key, values in groups.items() if len(values) != 1]
    if inconsistent:
        raise ValueError(f"inconsistent {source_name} scene/class groups: {inconsistent[:3]}")
    return {key: next(iter(values)) for key, values in groups.items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nr3d", type=Path, required=True)
    parser.add_argument("--sr3d", type=Path, required=True)
    parser.add_argument("--sr3d-target-candidates", type=Path, required=True)
    parser.add_argument("--base-catalog", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--existing-resolutions", type=Path, required=True)
    parser.add_argument("--output-catalog", type=Path, required=True)
    parser.add_argument("--output-resolutions", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_nr3d_fusion_v2_6")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    outputs = [args.output_catalog, args.output_resolutions]
    if any(path.exists() for path in outputs) and not args.resume:
        raise FileExistsError(next(path for path in outputs if path.exists()))
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "outputs": [str(path) for path in outputs]}, indent=2))
        return

    nr3d_groups, descriptions = load_nr3d(args.nr3d)
    sr3d_groups = load_exact_stimulus_groups(args.sr3d, "Sr3D+")
    counts: Counter[str] = Counter()
    exact_groups: dict[tuple[str, str], tuple[int, ...]] = {}
    group_sources: dict[tuple[str, str], str] = {}
    for key in sorted(nr3d_groups.keys() | sr3d_groups.keys()):
        nr3d_ids, sr3d_ids = nr3d_groups.get(key), sr3d_groups.get(key)
        if nr3d_ids is not None and sr3d_ids is not None and nr3d_ids != sr3d_ids:
            counts["cross_source_scene_class_conflict_excluded"] += 1
            continue
        exact_groups[key] = nr3d_ids if nr3d_ids is not None else sr3d_ids  # type: ignore[assignment]
        if nr3d_ids is not None and sr3d_ids is not None:
            group_sources[key] = "ReferIt3D/Nr3D+Sr3D+"
            counts["cross_source_scene_class_exact_agreement"] += 1
        elif nr3d_ids is not None:
            group_sources[key] = "ReferIt3D/Nr3D"
            counts["nr3d_only_scene_class"] += 1
        else:
            group_sources[key] = "ReferIt3D/Sr3D+"
            counts["sr3d_only_scene_class"] += 1
    catalog = json.loads(args.base_catalog.read_text(encoding="utf-8"))
    if catalog.get("source_type") != "OFFICIAL_STRUCTURED_ANNOTATION_FUSION":
        raise ValueError("base catalog must be an official structured annotation fusion")
    selected_scenes = {str(row["scene_id"]) for row in read_jsonl(args.branches)}
    parsed = read_jsonl(args.parsed)
    if args.limit is not None:
        parsed = parsed[: args.limit]
    existing_keys = {record_key(row) for row in read_jsonl(args.existing_resolutions)}

    for (scene_id, label), object_ids in sorted(exact_groups.items()):
        if scene_id not in selected_scenes:
            continue
        if scene_id not in catalog["scenes"]:
            catalog["scenes"][scene_id] = {
                "source_scene_id": f"scannet/{scene_id}", "objects": [], "relations": [],
            }
            counts["scene_added"] += 1
        scene = catalog["scenes"][scene_id]
        scene.setdefault("exact_class_counts", {})[label] = len(object_ids)
        scene.setdefault("exact_class_count_sources", {})[label] = (
            f"{group_sources[(scene_id, label)]}@725a5d31:{scene_id}:{label}"
        )
        counts["exact_scene_class_count_added"] += 1

    resolution_rows: list[dict[str, Any]] = []
    object_ids_added: set[tuple[str, int]] = set()
    object_node_by_native: dict[tuple[str, int], str] = {}
    for row in parsed:
        key = record_key(row)
        if key in existing_keys or not key[0].startswith("scene"):
            continue
        refs = [str(value) for value in (row.get("intervention") or {}).get("target_ref_texts") or []]
        if len(refs) != 1:
            continue
        matches = descriptions.get((key[0], normalize_ref(refs[0])), set())
        if len(matches) != 1:
            continue
        label, source_object_id = next(iter(matches))
        scene = catalog["scenes"].get(key[0])
        if not isinstance(scene, dict) or label not in (scene.get("exact_class_counts") or {}):
            continue
        object_id = f"hypo3d:{key[0]}:nr3d:{source_object_id:04d}"
        object_key = (key[0], source_object_id)
        if object_key not in object_ids_added and not any(
            str(obj.get("object_id")) == object_id for obj in scene["objects"]
        ):
            scene["objects"].append({
                "object_id": object_id, "class": label, "label": label,
                "aliases": [label], "source_instance_index": source_object_id,
                "source_native_object_id": source_object_id,
                "source_annotation_namespace": "ReferIt3D/Nr3D/ScanNet_objectId",
                "origin_type": "SOURCE_OBJECT_ANNOTATION",
            })
            object_ids_added.add(object_key)
            object_node_by_native[object_key] = object_id
            counts["target_object_node_added"] += 1
        evidence_id = f"nr3d_exact_utterance:{key[0]}:{source_object_id}"
        resolution_rows.append({
            "resolution_id": f"target_{key[0]}_{key[1]}_{key[2]}",
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "branch_id": row["branch_id"],
            "resolver_version": "hypo3d_nr3d_exact_utterance_resolver_v1",
            "new_entity_ids": list((row.get("intervention") or {}).get("new_entities") or []),
            "resolved_targets": [{
                "target_ref_text": refs[0], "candidate_count": 1,
                "resolved_entity_id": object_id, "resolution_tier": "ANNOTATION_ALIGNED",
                "evidence_fact_ids": [evidence_id],
            }],
            "resolved_anchors": [], "catalog_source_type": catalog["source_type"],
            "status": "PASS", "resolution_tier": "ANNOTATION_ALIGNED",
            "evidence_ids": [evidence_id],
        })
        counts["exact_utterance_resolution_added"] += 1

    parsed_by_key = {record_key(row): row for row in parsed}
    for candidate in read_jsonl(args.sr3d_target_candidates):
        key = record_key(candidate)
        if key in existing_keys or key not in parsed_by_key:
            continue
        label = normalize_ref(str(candidate["target_class"]))
        source_object_id = int(candidate["source_instance_id"])
        scene = catalog["scenes"].get(key[0])
        if (
            not isinstance(scene, dict)
            or label not in (scene.get("exact_class_counts") or {})
            or source_object_id not in exact_groups.get((key[0], label), ())
        ):
            counts["sr3d_target_candidate_rejected_missing_exact_group"] += 1
            continue
        object_key = (key[0], source_object_id)
        object_id = object_node_by_native.get(object_key)
        if object_id is None:
            object_id = f"hypo3d:{key[0]}:referit3d:{source_object_id:04d}"
            scene["objects"].append({
                "object_id": object_id, "class": label, "label": label,
                "aliases": [label], "source_instance_index": source_object_id,
                "source_native_object_id": source_object_id,
                "source_annotation_namespace": "ReferIt3D/ScanNet_objectId",
                "origin_type": "SOURCE_OBJECT_ANNOTATION",
            })
            object_ids_added.add(object_key)
            object_node_by_native[object_key] = object_id
            counts["target_object_node_added"] += 1
        method = str(candidate["resolution_tier"])
        evidence_id = f"sr3d_grounding:{method}:{key[0]}:{source_object_id}"
        row = parsed_by_key[key]
        resolution_rows.append({
            "resolution_id": f"target_{key[0]}_{key[1]}_{key[2]}",
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "branch_id": row["branch_id"],
            "resolver_version": "hypo3d_sr3d_strict_grounding_resolver_v1",
            "new_entity_ids": list((row.get("intervention") or {}).get("new_entities") or []),
            "resolved_targets": [{
                "target_ref_text": candidate["target_ref_text"], "candidate_count": 1,
                "resolved_entity_id": object_id, "resolution_tier": "ANNOTATION_ALIGNED",
                "evidence_fact_ids": [evidence_id],
            }],
            "resolved_anchors": [], "catalog_source_type": catalog["source_type"],
            "status": "PASS", "resolution_tier": "ANNOTATION_ALIGNED",
            "evidence_ids": [evidence_id],
        })
        counts["sr3d_strict_resolution_added"] += 1

    catalog["source_hashes"] = {
        **catalog.get("source_hashes", {}),
        str(args.nr3d): sha256_file(args.nr3d),
        str(args.sr3d): sha256_file(args.sr3d),
        str(args.sr3d_target_candidates): sha256_file(args.sr3d_target_candidates),
        str(args.base_catalog): sha256_file(args.base_catalog),
    }
    for scene in catalog["scenes"].values():
        scene["objects"] = sorted(scene["objects"], key=lambda obj: str(obj["object_id"]))
        if "exact_class_counts" in scene:
            scene["exact_class_counts"] = dict(sorted(scene["exact_class_counts"].items()))
            scene["exact_class_count_sources"] = dict(sorted(scene["exact_class_count_sources"].items()))
    catalog["scenes"] = dict(sorted(catalog["scenes"].items()))
    schema = json.loads((ROOT / "schemas/hypo3d_object_catalog.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"catalog schema validation failed: {errors[0].message}")

    args.output_catalog.parent.mkdir(parents=True, exist_ok=args.resume)
    args.output_resolutions.parent.mkdir(parents=True, exist_ok=args.resume)
    args.output_catalog.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_resolutions.write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in sorted(resolution_rows, key=record_key))
    )
    report = {
        "schema_version": "hypo3d_nr3d_fusion_build_v1",
        "status": "NR3D_OFFICIAL_FUSION_ARTIFACTS_VALID",
        "run_id": args.run_id, "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "total_scene_count": len(catalog["scenes"]),
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (
                args.nr3d, args.sr3d, args.sr3d_target_candidates, args.base_catalog,
                args.branches, args.parsed, args.existing_resolutions,
            )
        },
        "output_hashes": {
            str(args.output_catalog): sha256_file(args.output_catalog),
            str(args.output_resolutions): sha256_file(args.output_resolutions),
        },
    }
    report_path = args.output_catalog.parent / "nr3d_fusion_build_report.v1.json"
    report_path.write_bytes(canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
