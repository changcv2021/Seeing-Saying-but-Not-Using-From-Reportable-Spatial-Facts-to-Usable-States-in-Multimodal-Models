from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json


NON_WORD = re.compile(r"[^a-z0-9]+")
SAFE_ATTRIBUTE_GROUPS = {"color", "shape", "state", "material", "texture"}
RELATION_TAIL = re.compile(
    r"\b(?:beside|near|next to|left of|right of|in front of|behind|above|below|"
    r"under|underneath|over|on|by|between|closest to|adjacent to|with|that|which)\b"
)
# These values cannot safely be attached to an object from an unparsed phrase.
AMBIGUOUS_ATTRIBUTE_VALUES = {"on", "off", "in", "inside", "left", "right"}


def normalize(value: Any) -> str:
    return " ".join(NON_WORD.sub(" ", str(value or "").casefold()).split())


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase and re.search(rf"(?:^|\s){re.escape(phrase)}(?:$|\s)", text))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def normalized_attributes(source: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for raw_group, raw_values in (source.get("attributes") or {}).items():
        group = normalize(raw_group)
        if group not in SAFE_ATTRIBUTE_GROUPS or not isinstance(raw_values, list):
            continue
        values = {normalize(value) for value in raw_values if normalize(value)}
        if values:
            result[group] = values
    return result


def build_scene_objects(
    object_payload: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for scan in object_payload.get("scans") or []:
        if not isinstance(scan, dict) or not scan.get("scan"):
            continue
        scene_id = str(scan["scan"])
        catalog_scene = catalog.get("scenes", {}).get(scene_id)
        if not isinstance(catalog_scene, dict):
            continue
        catalog_by_bbox = {
            int(obj["source_bbox_id"]): obj
            for obj in catalog_scene.get("objects") or []
            if isinstance(obj, dict) and isinstance(obj.get("source_bbox_id"), int)
        }
        objects = []
        for source in scan.get("objects") or []:
            raw_id = str(source.get("id") or "")
            label = normalize(source.get("label"))
            if not raw_id.isdigit() or not label:
                continue
            bbox_id = int(raw_id)
            catalog_object = catalog_by_bbox.get(bbox_id)
            if not catalog_object or normalize(catalog_object.get("class")) != label:
                continue
            objects.append({
                "object_id": str(catalog_object["object_id"]),
                "source_bbox_id": bbox_id,
                "label": label,
                "attributes": normalized_attributes(source),
            })
        if objects:
            result[scene_id] = objects
    return result


def attribute_mentions(
    target_head: str, same_class_objects: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    vocabulary: dict[str, set[str]] = defaultdict(set)
    for obj in same_class_objects:
        for group, values in obj["attributes"].items():
            vocabulary[group].update(values)
    mentions = [
        (group, value)
        for group, values in vocabulary.items()
        for value in values
        if value not in AMBIGUOUS_ATTRIBUTE_VALUES and contains_phrase(target_head, value)
    ]
    # Prefer the longest value when one attribute phrase contains another.
    selected: list[tuple[str, str]] = []
    for group, value in sorted(mentions, key=lambda item: (-len(item[1].split()), -len(item[1]))):
        if any(group == old_group and contains_phrase(old_value, value) for old_group, old_value in selected):
            continue
        selected.append((group, value))
    return sorted(selected)


def resolve_ref(
    ref_text: str, scene_objects: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    normalized_ref = normalize(ref_text)
    target_head = RELATION_TAIL.split(normalized_ref, maxsplit=1)[0].strip()
    matching_labels = sorted(
        {obj["label"] for obj in scene_objects if contains_phrase(target_head, obj["label"])},
        key=lambda value: (-len(value.split()), -len(value), value),
    )
    if not matching_labels:
        return None, "NO_EXACT_CLASS_PHRASE", {}
    target_label = matching_labels[0]
    same_class = [obj for obj in scene_objects if obj["label"] == target_label]
    if len(same_class) < 2:
        return None, "CLASS_ALREADY_UNIQUE_OR_NO_COMPETITOR", {"target_label": target_label}
    mentions = attribute_mentions(target_head, same_class)
    if not mentions:
        return None, "NO_SAFE_ATTRIBUTE_MENTION", {"target_label": target_label}

    supported: list[dict[str, Any]] = []
    explicitly_refuted: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    for obj in same_class:
        if all(value in obj["attributes"].get(group, set()) for group, value in mentions):
            supported.append(obj)
            continue
        # Open-world safe exclusion: a competitor is excluded only when an
        # annotation in the same attribute group explicitly gives another value.
        refuted_by = [
            (group, value, sorted(obj["attributes"].get(group, set())))
            for group, value in mentions
            if obj["attributes"].get(group) and value not in obj["attributes"][group]
        ]
        if refuted_by:
            explicitly_refuted.append({"object": obj, "refuted_by": refuted_by})
        else:
            unknown.append(obj)

    diagnostics = {
        "target_label": target_label,
        "same_class_count": len(same_class),
        "attribute_mentions": [{"group": group, "value": value} for group, value in mentions],
        "supported_count": len(supported),
        "explicitly_refuted_count": len(explicitly_refuted),
        "unknown_count": len(unknown),
    }
    if len(supported) != 1:
        return None, "ATTRIBUTE_SUPPORT_NOT_UNIQUE", diagnostics
    if unknown:
        return None, "OPEN_WORLD_COMPETITOR_NOT_REFUTED", diagnostics
    return supported[0], "PASS_OPEN_WORLD_SAFE_ATTRIBUTE", diagnostics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--existing-resolutions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_3dssg_attribute_grounding_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output_dir": str(args.output_dir)}, indent=2))
        return

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    object_payload = json.loads(args.objects.read_text(encoding="utf-8"))
    scene_objects = build_scene_objects(object_payload, catalog)
    del object_payload
    existing_keys = {
        (str(row["scene_id"]), str(row["change_id"]), str(row["question_id"]))
        for row in read_jsonl(args.existing_resolutions)
    }

    counts: Counter[str] = Counter()
    candidate_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    parsed_rows = read_jsonl(args.parsed)
    if args.limit is not None:
        parsed_rows = parsed_rows[: args.limit]
    for row in parsed_rows:
        scene_id = str(row["scene_id"])
        if scene_id.startswith("scene") or scene_id not in scene_objects:
            continue
        counts["parsed_3rscan_with_exact_catalog_alignment"] += 1
        key = (scene_id, str(row["change_id"]), str(row["question_id"]))
        if key in existing_keys:
            counts["already_resolved"] += 1
            continue
        refs = [str(value) for value in (row.get("intervention") or {}).get("target_ref_texts") or []]
        if not refs:
            counts["no_target_ref"] += 1
            continue
        resolved = []
        diagnostics = []
        failure = None
        for ref_text in refs:
            obj, status, details = resolve_ref(ref_text, scene_objects[scene_id])
            diagnostics.append({"target_ref_text": ref_text, "status": status, **details})
            counts[f"ref_status:{status}"] += 1
            if obj is None:
                failure = status
                break
            resolved.append((ref_text, obj, details))
        if failure is not None or len(resolved) != len(refs):
            if len(diagnostic_rows) < 5000:
                diagnostic_rows.append({
                    "scene_id": scene_id,
                    "change_id": row["change_id"],
                    "question_id": row["question_id"],
                    "diagnostics": diagnostics,
                    "status": "NOT_FORMALLY_RESOLVED",
                })
            continue

        evidence_ids = []
        resolved_targets = []
        for ref_text, obj, details in resolved:
            facts = [
                f"3dssg_attribute:{scene_id}:{obj['source_bbox_id']}:{item['group']}:{item['value']}"
                for item in details["attribute_mentions"]
            ]
            evidence_ids.extend(facts)
            resolved_targets.append({
                "target_ref_text": ref_text,
                "candidate_count": 1,
                "resolved_entity_id": obj["object_id"],
                "resolution_tier": "ANNOTATION_ALIGNED",
                "evidence_fact_ids": facts,
            })
        candidate_rows.append({
            "resolution_id": f"target_{scene_id}_{row['change_id']}_{row['question_id']}",
            "scene_id": scene_id,
            "change_id": row["change_id"],
            "question_id": row["question_id"],
            "branch_id": row["branch_id"],
            "resolver_version": "hypo3d_3dssg_attribute_resolver_v1",
            "new_entity_ids": list((row.get("intervention") or {}).get("new_entities") or []),
            "resolved_targets": resolved_targets,
            "resolved_anchors": [],
            "catalog_source_type": catalog.get("source_type"),
            "status": "PASS",
            "resolution_tier": "ANNOTATION_ALIGNED",
            "evidence_ids": sorted(set(evidence_ids)),
            "attribute_resolution_policy": "POSITIVE_SUPPORT_AND_ALL_SAME_CLASS_COMPETITORS_EXPLICITLY_REFUTED",
        })
        counts["new_formal_resolution"] += 1

    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    candidate_path = args.output_dir / "target_resolution_candidates.3dssg_attribute_v1.jsonl"
    diagnostic_path = args.output_dir / "diagnostics.3dssg_attribute_v1.jsonl"
    candidate_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in candidate_rows))
    diagnostic_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in diagnostic_rows))
    report = {
        "schema_version": "hypo3d_3dssg_attribute_grounding_audit_v1",
        "status": "ATTRIBUTE_GROUNDING_AUDITED",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "safe_attribute_groups": sorted(SAFE_ATTRIBUTE_GROUPS),
        "truth_policy": "OPEN_WORLD_SAFE_POSITIVE_ATTRIBUTE_AND_EXPLICIT_COMPETITOR_REFUTATION",
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (args.objects, args.parsed, args.catalog, args.existing_resolutions)
        },
        "output_hashes": {
            str(candidate_path): sha256_file(candidate_path),
            str(diagnostic_path): sha256_file(diagnostic_path),
        },
    }
    report_path = args.output_dir / "report.3dssg_attribute_v1.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
