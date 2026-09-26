from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.resolve_targets import resolve_unique_object_ref


SPATIAL_RELATIONS = {
    "left", "right", "front", "behind", "close by", "inside",
    "higher than", "lower than", "supported by", "standing on",
    "lying on", "hanging on", "attached to", "standing in",
    "lying in", "hanging in",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized_label(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").split())


def catalog_objects(scene_id: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for index, obj in enumerate(source.get("objects") or []):
        label = normalized_label(obj.get("label"))
        raw_id = str(obj.get("id") or "")
        if not label or not raw_id.isdigit():
            continue
        result.append({
            "object_id": f"hypo3d:{scene_id}:3dssg:{int(raw_id):04d}",
            "class": label,
            "label": label,
            "aliases": [label],
            "source_instance_index": index,
            "source_label_id": int(obj["global_id"]) if str(obj.get("global_id") or "").isdigit() else None,
            "source_bbox_id": int(raw_id),
            "origin_type": "SOURCE_OBJECT_ANNOTATION",
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", type=Path, required=True)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_3dssg_coverage_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output_dir": str(args.output_dir)}, indent=2))
        return

    object_payload = json.loads(args.objects.read_text(encoding="utf-8"))
    relation_payload = json.loads(args.relationships.read_text(encoding="utf-8"))
    object_scans = {
        str(row.get("scan")): row for row in object_payload.get("scans") or []
        if isinstance(row, dict) and row.get("scan")
    }
    relation_scans = {
        str(row.get("scan")): row for row in relation_payload.get("scans") or []
        if isinstance(row, dict) and row.get("scan")
    }
    del object_payload, relation_payload

    branch_scene_ids = {str(row["scene_id"]) for row in read_jsonl(args.branches)}
    rscan_scene_ids = {scene_id for scene_id in branch_scene_ids if not scene_id.startswith("scene")}
    current_catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    current_scenes = current_catalog["scenes"]
    recovered = sorted(rscan_scene_ids & object_scans.keys() - current_scenes.keys())
    overlap = sorted(rscan_scene_ids & object_scans.keys() & current_scenes.keys())
    relationship_coverage = sorted(rscan_scene_ids & relation_scans.keys())

    counts: Counter[str] = Counter()
    counts["hypo_scene_count"] = len(branch_scene_ids)
    counts["hypo_3rscan_scene_count"] = len(rscan_scene_ids)
    counts["3dssg_object_scan_count"] = len(object_scans)
    counts["3dssg_relationship_scan_count"] = len(relation_scans)
    counts["hypo_3rscan_with_3dssg_objects"] = len(rscan_scene_ids & object_scans.keys())
    counts["hypo_3rscan_with_3dssg_relationships"] = len(relationship_coverage)
    counts["new_scene_catalog_candidates"] = len(recovered)
    counts["overlap_scene_count"] = len(overlap)

    recovered_rows: list[dict[str, Any]] = []
    object_lists: dict[str, list[dict[str, Any]]] = {}
    for scene_id in sorted(rscan_scene_ids & object_scans.keys()):
        objects = catalog_objects(scene_id, object_scans[scene_id])
        object_lists[scene_id] = objects
        counts["hypo_3rscan_3dssg_objects"] += len(objects)
        if scene_id in recovered:
            counts["new_scene_catalog_objects"] += len(objects)
            recovered_rows.append({
                "scene_id": scene_id,
                "source_scene_id": f"3rscan/{scene_id}",
                "object_count": len(objects),
                "relation_count": len((relation_scans.get(scene_id) or {}).get("relationships") or []),
            })

    for scene_id in overlap:
        official_by_id = {
            int(obj["source_bbox_id"]): normalized_label(obj.get("class"))
            for obj in current_scenes[scene_id].get("objects") or []
            if isinstance(obj.get("source_bbox_id"), int)
        }
        dssg_by_id = {
            int(obj["source_bbox_id"]): normalized_label(obj.get("class"))
            for obj in object_lists[scene_id]
        }
        for object_id in official_by_id.keys() & dssg_by_id.keys():
            counts["overlap_instance_id_match"] += 1
            if official_by_id[object_id] == dssg_by_id[object_id]:
                counts["overlap_instance_label_exact_match"] += 1
            else:
                counts["overlap_instance_label_mismatch"] += 1

    relation_names: Counter[str] = Counter()
    for scene_id in relationship_coverage:
        for relation in relation_scans[scene_id].get("relationships") or []:
            if not isinstance(relation, list) or len(relation) < 4:
                continue
            predicate = normalized_label(relation[3])
            relation_names[predicate] += 1
            counts["hypo_3rscan_relations"] += 1
            if predicate in SPATIAL_RELATIONS:
                counts["hypo_3rscan_spatial_relations"] += 1

    new_resolution_rows: list[dict[str, Any]] = []
    for row in read_jsonl(args.parsed)[: args.limit]:
        scene_id = str(row["scene_id"])
        if scene_id not in recovered:
            continue
        refs = list((row.get("intervention") or {}).get("target_ref_texts") or [])
        if not refs:
            continue
        resolved = []
        for ref_text in refs:
            obj, tier = resolve_unique_object_ref(str(ref_text), object_lists[scene_id])
            if obj is None:
                resolved = []
                break
            resolved.append({"ref_text": ref_text, "object_id": obj["object_id"], "tier": tier})
        if len(resolved) == len(refs):
            counts["new_scene_unique_class_target_records"] += 1
            new_resolution_rows.append({
                "scene_id": scene_id,
                "change_id": row["change_id"],
                "question_id": row["question_id"],
                "resolved_targets": resolved,
                "status": "AUDIT_CANDIDATE_OFFICIAL_3DSSG_UNIQUE_CLASS",
            })

    report = {
        "schema_version": "hypo3d_3dssg_coverage_audit_v1",
        "status": "HYPO3D_3DSSG_COVERAGE_AUDITED",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "spatial_relation_counts": {
            key: value for key, value in sorted(relation_names.items()) if key in SPATIAL_RELATIONS
        },
        "recovered_scene_ids": recovered,
        "truth_policy": "OFFICIAL_3DSSG_INSTANCE_IDS_AND_EXPLICIT_RELATION_EDGES_ONLY",
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (args.objects, args.relationships, args.branches, args.parsed, args.catalog)
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    (args.output_dir / "recovered_scenes.3dssg_v1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in recovered_rows)
    )
    (args.output_dir / "new_target_candidates.3dssg_v1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in new_resolution_rows)
    )
    (args.output_dir / "report.3dssg_coverage_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
