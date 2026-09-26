from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.resolve_targets import normalize_ref


RELATIONS = (
    ("in front of", "FRONT_OF"),
    ("to the left of", "LEFT_OF"),
    ("to the right of", "RIGHT_OF"),
    ("left of", "LEFT_OF"),
    ("right of", "RIGHT_OF"),
    ("underneath", "BELOW"),
    ("below", "BELOW"),
    ("under", "BELOW"),
    ("above", "ABOVE"),
    ("behind", "BEHIND"),
    ("beside", "BESIDE"),
    ("next to", "BESIDE"),
    ("adjacent to", "BESIDE"),
    ("nearest to", "NEAR"),
    ("closest to", "NEAR"),
    ("close to", "NEAR"),
    ("near", "NEAR"),
    ("farthest from", "FAR"),
    ("far away from", "FAR"),
    ("far from", "FAR"),
    ("on top of", "ABOVE"),
)
LEADING = re.compile(r"^(?:select|choose|find|pick|locate|identify)\s+")
RELATIVE_FILLER = re.compile(r"\b(?:that|which)\s+is\s+")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["scene_id"]),
        str(row["change_id"]),
        str(row.get("question_id") or row.get("source_question_id")),
    )


def parse_xlsx(path: Path) -> list[dict[str, str]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = [
            "".join(node.text or "" for node in item.findall(".//m:t", ns))
            for item in shared.findall("m:si", ns)
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for row in sheet.findall(".//m:row", ns):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", ns):
            ref = str(cell.get("r") or "")
            value_node = cell.find("m:v", ns)
            value = "" if value_node is None else str(value_node.text or "")
            if cell.get("t") == "s" and value:
                value = strings[int(value)]
            if ref and ref[0] in "ABCDE":
                values["ABCDE".index(ref[0])] = value
        rows.append([values.get(index, "").strip() for index in range(5)])
    if not rows or rows[0] != ["scene_id", "Front", "Back", "Left", "Right"]:
        raise ValueError("Unexpected Axis Definition.xlsx schema")
    return [
        {"scene_id": row[0], "Front": row[1], "Back": row[2], "Left": row[3], "Right": row[4]}
        for row in rows[1:]
    ]


def normalized_descriptor(text: str) -> str:
    value = normalize_ref(text)
    value = LEADING.sub("", value)
    value = RELATIVE_FILLER.sub("", value)
    return " ".join(value.split())


def relation_parts(text: str) -> tuple[str, str, str] | None:
    value = normalized_descriptor(text)
    for phrase, predicate in RELATIONS:
        marker = f" {phrase} "
        if marker not in f" {value} ":
            continue
        head, tail = value.split(phrase, 1)
        head, tail = head.strip(), tail.strip()
        if head and tail:
            return head, predicate, tail
    return None


def aliases(obj: dict[str, Any]) -> set[str]:
    values = [obj.get("class"), obj.get("label"), *(obj.get("aliases") or [])]
    return {normalize_ref(str(value)) for value in values if value}


def class_from_text(text: str, objects: list[dict[str, Any]]) -> str | None:
    value = normalize_ref(text)
    matches = {
        alias
        for obj in objects
        for alias in aliases(obj)
        if re.search(rf"(?:^|\s){re.escape(alias)}(?:$|\s)", value)
    }
    if not matches:
        return None
    longest = max(len(item.split()) for item in matches)
    winners = {item for item in matches if len(item.split()) == longest}
    return next(iter(winners)) if len(winners) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis", type=Path, required=True)
    parser.add_argument("--vg", dest="vg_paths", action="append", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="omitted_sources_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    scenes = catalog["scenes"]
    source_to_scene = {str(row["source_scene_id"]): scene_id for scene_id, row in scenes.items()}
    bbox_to_object = {
        (str(scene["source_scene_id"]), int(obj["source_bbox_id"])): str(obj["object_id"])
        for scene in scenes.values()
        for obj in scene["objects"]
        if isinstance(obj.get("source_bbox_id"), int)
    }
    object_by_scene = {
        scene_id: [obj for obj in scene["objects"] if isinstance(obj, dict)]
        for scene_id, scene in scenes.items()
    }

    counts: Counter[str] = Counter()
    axis_rows = parse_xlsx(args.axis)
    axis_by_scene = {row["scene_id"]: row for row in axis_rows}
    counts["axis_scene_rows"] = len(axis_rows)
    counts["axis_scenes_with_anchor"] = sum(
        any(row[direction] for direction in ("Front", "Back", "Left", "Right"))
        for row in axis_rows
    )
    counts["axis_anchor_cells"] = sum(
        bool(row[direction])
        for row in axis_rows
        for direction in ("Front", "Back", "Left", "Right")
    )
    for row in axis_rows:
        objects = object_by_scene.get(row["scene_id"], [])
        if not objects:
            counts["axis_scene_without_official_object_catalog"] += 1
            continue
        for direction in ("Front", "Back", "Left", "Right"):
            label = row[direction]
            if not label:
                continue
            label_class = class_from_text(label, objects)
            if label_class is None:
                counts["axis_anchor_class_unresolved"] += 1
                continue
            candidates = [obj for obj in objects if label_class in aliases(obj)]
            if len(candidates) == 1:
                counts["axis_anchor_unique_object"] += 1
            else:
                counts["axis_anchor_object_ambiguous"] += 1

    full_text_index: dict[tuple[str, str], set[tuple[str, tuple[str, ...]]]] = defaultdict(set)
    semantic_index: dict[tuple[str, str, str, str], set[tuple[str, tuple[str, ...]]]] = defaultdict(set)
    for path in args.vg_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"{path}: expected list-valued EmbodiedScan VG")
        for row in payload[: args.limit]:
            if not isinstance(row, dict):
                continue
            scan_id = str(row.get("scan_id") or "")
            if scan_id not in source_to_scene:
                continue
            try:
                target_bbox_id = int(row["target_id"])
            except (KeyError, TypeError, ValueError):
                continue
            target_object = bbox_to_object.get((scan_id, target_bbox_id))
            if target_object is None:
                continue
            anchor_objects = tuple(
                object_id
                for raw_id in (row.get("anchor_ids") or [])
                if (object_id := bbox_to_object.get((scan_id, int(raw_id)))) is not None
            )
            text_value = normalized_descriptor(str(row.get("text") or ""))
            full_text_index[(scan_id, text_value)].add((target_object, anchor_objects))
            counts["embodiedscan_vg_hypo_records"] += 1
            parts = relation_parts(text_value)
            anchors = row.get("anchors") or []
            if parts is None or len(anchors) != 1 or len(anchor_objects) != 1:
                continue
            target_class = normalize_ref(str(row.get("target") or ""))
            anchor_class = normalize_ref(str(anchors[0]))
            semantic_index[(scan_id, target_class, parts[1], anchor_class)].add(
                (target_object, anchor_objects)
            )
            counts["embodiedscan_vg_structured_relation_records"] += 1

    parsed = {record_key(row): row for row in read_jsonl(args.parsed)}
    oracles = {record_key(row): row for row in read_jsonl(args.oracles)}
    resolutions = {record_key(row): row for row in read_jsonl(args.resolutions)}
    candidates: list[dict[str, Any]] = []
    for key in sorted(parsed.keys() & oracles.keys()):
        row = parsed[key]
        intervention = row["intervention"]
        scene = scenes.get(key[0])
        if not isinstance(scene, dict):
            continue
        scan_id = str(scene["source_scene_id"])
        current = resolutions.get(key)
        already_resolved = bool(current and current.get("resolved_targets"))
        target_refs = intervention.get("target_ref_texts") or []
        if not already_resolved and len(target_refs) == 1:
            ref = str(target_refs[0])
            exact = full_text_index.get((scan_id, normalized_descriptor(ref)), set())
            method = "EMBODIEDSCAN_VG_EXACT_FULL_TEXT"
            matches = exact
            if not matches:
                parts = relation_parts(ref)
                objects = object_by_scene.get(key[0], [])
                if parts is not None:
                    target_class = class_from_text(parts[0], objects)
                    anchor_class = class_from_text(parts[2], objects)
                    if target_class and anchor_class:
                        matches = semantic_index.get(
                            (scan_id, target_class, parts[1], anchor_class), set()
                        )
                        method = "EMBODIEDSCAN_VG_EXACT_STRUCTURED_RELATION"
            target_ids = {item[0] for item in matches}
            if len(target_ids) == 1:
                counts["new_exact_embodiedscan_vg_target_candidates"] += 1
                candidates.append({
                    "scene_id": key[0], "change_id": key[1], "question_id": key[2],
                    "role": "target", "ref_text": ref,
                    "resolved_entity_id": next(iter(target_ids)), "resolution_tier": method,
                })
            elif len(target_ids) > 1:
                counts["reject_embodiedscan_vg_target_ambiguous"] += 1

        atoms = oracles[key].get("normalized_atoms") or []
        if any(atom.get("predicate") in {"LEFT_OF", "RIGHT_OF", "FRONT_OF", "BEHIND"} for atom in atoms):
            counts["direction_oracle_records"] += 1
            axis = axis_by_scene.get(key[0])
            if axis and any(axis[d] for d in ("Front", "Back", "Left", "Right")):
                counts["direction_oracle_with_axis_anchor"] += 1

    report = {
        "schema_version": "hypo3d_omitted_grounding_sources_audit_v1",
        "status": "OMITTED_GROUNDING_SOURCES_AUDITED",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "candidate_count": len(candidates),
        "truth_policy": (
            "OFFICIAL_AXIS_METADATA_AND_EXACT_EMBODIEDSCAN_VG_FULL_TEXT_OR_"
            "EXACT_STRUCTURED_RELATION_ONLY"
        ),
        "input_hashes": {
            str(path): sha256_file(path)
            for path in [args.axis, *args.vg_paths, args.parsed, args.oracles, args.resolutions, args.catalog]
        },
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    (args.output_dir / "candidates.embodiedscan_vg_v1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in candidates)
    )
    (args.output_dir / "report.omitted_grounding_sources_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
