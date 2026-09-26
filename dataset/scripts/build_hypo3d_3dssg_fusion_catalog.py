from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.registry import ROOT


FUSION_SOURCE_TYPE = "OFFICIAL_STRUCTURED_ANNOTATION_FUSION"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalize_label(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").split())


def build_objects(scene_id: str, row: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, str]]:
    objects: list[dict[str, Any]] = []
    id_map: dict[int, str] = {}
    for index, source in enumerate(row.get("objects") or []):
        label = normalize_label(source.get("label"))
        raw_id = str(source.get("id") or "")
        if not label or not raw_id.isdigit():
            continue
        bbox_id = int(raw_id)
        object_id = f"hypo3d:{scene_id}:3dssg:{bbox_id:04d}"
        obj = {
            "object_id": object_id,
            "class": label,
            "label": label,
            "aliases": [label],
            "source_instance_index": index,
            "source_bbox_id": bbox_id,
            "origin_type": "SOURCE_OBJECT_ANNOTATION",
        }
        if str(source.get("global_id") or "").isdigit():
            obj["source_label_id"] = int(source["global_id"])
        objects.append(obj)
        id_map[bbox_id] = object_id
    return objects, id_map


def build_relations(row: dict[str, Any] | None, id_map: dict[int, str]) -> list[dict[str, Any]]:
    relations = []
    for index, source in enumerate((row or {}).get("relationships") or []):
        if not isinstance(source, list) or len(source) < 4:
            continue
        try:
            subject_id, object_id = int(source[0]), int(source[1])
        except (TypeError, ValueError):
            continue
        if subject_id not in id_map or object_id not in id_map:
            continue
        predicate = normalize_label(source[3])
        if not predicate:
            continue
        relations.append({
            "relation_id": f"3dssg:{index:06d}",
            "subject_id": id_map[subject_id],
            "object_id": id_map[object_id],
            "predicate": predicate,
            "source_subject_instance_id": subject_id,
            "source_object_instance_id": object_id,
            "source_predicate_id": int(source[2]) if isinstance(source[2], int) else source[2],
            "origin_type": "SOURCE_RELATION_ANNOTATION",
        })
    return relations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-catalog", type=Path, required=True)
    parser.add_argument("--objects", type=Path, required=True)
    parser.add_argument("--relationships", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_3dssg_fusion_catalog_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output.exists() and not args.resume:
        raise FileExistsError(args.output)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output": str(args.output)}, indent=2))
        return

    catalog = json.loads(args.base_catalog.read_text(encoding="utf-8"))
    if catalog.get("source_type") != "EMBODIEDSCAN_OFFICIAL_ANNOTATION":
        raise ValueError("base catalog must be official EmbodiedScan annotation")
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
    selected_scenes = {str(row["scene_id"]) for row in read_jsonl(args.branches)}
    missing_3rscan = sorted(
        scene_id for scene_id in selected_scenes
        if not scene_id.startswith("scene") and scene_id not in catalog["scenes"] and scene_id in object_scans
    )
    if args.limit is not None:
        missing_3rscan = missing_3rscan[: args.limit]

    counts: Counter[str] = Counter()
    for scene_id in missing_3rscan:
        objects, id_map = build_objects(scene_id, object_scans[scene_id])
        relations = build_relations(relation_scans.get(scene_id), id_map)
        catalog["scenes"][scene_id] = {
            "source_scene_id": f"3rscan/{scene_id}",
            "objects": objects,
            "relations": relations,
        }
        counts["scene_added"] += 1
        counts["object_added"] += len(objects)
        counts["relation_added"] += len(relations)
        if relations:
            counts["scene_added_with_relations"] += 1

    catalog["source_type"] = FUSION_SOURCE_TYPE
    catalog["source_hashes"] = {
        **catalog.get("source_hashes", {}),
        str(args.base_catalog): sha256_file(args.base_catalog),
        str(args.objects): sha256_file(args.objects),
        str(args.relationships): sha256_file(args.relationships),
    }
    catalog["scenes"] = dict(sorted(catalog["scenes"].items()))
    schema = json.loads((ROOT / "schemas/hypo3d_object_catalog.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"catalog schema validation failed: {errors[0].message}")

    args.output.parent.mkdir(parents=True, exist_ok=args.resume)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = {
        "schema_version": "hypo3d_3dssg_fusion_catalog_build_v1",
        "status": "OFFICIAL_FUSION_CATALOG_VALID",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "total_scene_count": len(catalog["scenes"]),
        "total_object_count": sum(len(scene["objects"]) for scene in catalog["scenes"].values()),
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (args.base_catalog, args.objects, args.relationships, args.branches)
        },
        "output_hash": sha256_file(args.output),
    }
    (args.output.parent / "fusion_catalog_build_report.v1.json").write_bytes(canonical_json(report) + b"\n")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
