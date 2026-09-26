from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.prestates import explicit_quantity, ref_mentions_class
from spaceconflict.hypo3d_l4.resolve_targets import normalize_ref


RELATION_PHRASES = (
    ("in front of", "front"), ("to the left of", "left"),
    ("to the right of", "right"), ("left of", "left"),
    ("right of", "right"), ("underneath", "below"),
    ("below", "below"), ("under", "below"), ("above", "above"),
    ("behind", "back"), ("nearest to", "closest"),
    ("closest to", "closest"),
    ("farthest from", "farthest"), ("far away from", "farthest"),
    ("far from", "farthest"),
)
LEADING = re.compile(r"^(?:select|choose|find|pick|locate|identify)\s+")
RELATIVE_FILLER = re.compile(r"\b(?:that|which)\s+is\s+")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row["scene_id"]), str(row["change_id"]), str(row.get("question_id") or row.get("source_question_id"))


def normalized_descriptor(value: str) -> str:
    result = normalize_ref(value)
    result = LEADING.sub("", result)
    result = RELATIVE_FILLER.sub("", result)
    return " ".join(result.split())


def relation_parts(value: str) -> tuple[str, str, str] | None:
    text = normalized_descriptor(value)
    for phrase, relation in RELATION_PHRASES:
        if f" {phrase} " not in f" {text} ":
            continue
        head, tail = text.split(phrase, 1)
        if head.strip() and tail.strip():
            return head.strip(), relation, tail.strip()
    return None


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


def class_from_text(value: str, labels: set[str]) -> str | None:
    normalized = normalize_ref(value)
    matches = []
    for label in labels:
        forms = {label}
        if label.endswith("y") and len(label) > 1:
            forms.add(label[:-1] + "ies")
        elif label.endswith(("s", "x", "z", "ch", "sh")):
            forms.add(label + "es")
        else:
            forms.add(label + "s")
        if any(normalized == form or normalized.endswith(f" {form}") for form in forms):
            matches.append(label)
    if not matches:
        return None
    longest = max(len(label.split()) for label in matches)
    winners = {label for label in matches if len(label.split()) == longest}
    return next(iter(winners)) if len(winners) == 1 else None


def resolved_class(resolution: dict[str, Any] | None, scene: dict[str, Any] | None) -> str | None:
    targets = (resolution or {}).get("resolved_targets") or []
    if len(targets) != 1 or not isinstance(scene, dict):
        return None
    object_id = str(targets[0].get("resolved_entity_id") or "")
    matches = [
        normalize_ref(str(obj.get("class") or ""))
        for obj in scene.get("objects") or []
        if str(obj.get("object_id") or "") == object_id
    ]
    return matches[0] if len(matches) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sr3d", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--current-prestates", type=Path, required=True)
    parser.add_argument("--nr3d-target-candidates", type=Path, required=True)
    parser.add_argument("--nr3d-count-candidates", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_sr3d_coverage_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output_dir": str(args.output_dir)}, indent=2))
        return

    group_sets: dict[tuple[str, str], set[tuple[int, ...]]] = defaultdict(set)
    exact_descriptions: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    semantic_relations: dict[tuple[str, str, str, str], set[int]] = defaultdict(set)
    scene_labels: dict[str, set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    with args.sr3d.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            scene_id, label, count, target, distractors = decode_stimulus(row["stimulus_id"])
            if scene_id != row["scan_id"] or label != normalize_ref(row["instance_type"]):
                raise ValueError(f"Sr3D redundant fields disagree: {row['stimulus_id']}")
            ids = tuple(sorted((target, *distractors)))
            if len(ids) != count or len(set(ids)) != count or target != int(row["target_id"]):
                raise ValueError(f"Sr3D instance set invalid: {row['stimulus_id']}")
            group_sets[(scene_id, label)].add(ids)
            scene_labels[scene_id].add(label)
            description = normalized_descriptor(row["utterance"])
            if description:
                exact_descriptions[(scene_id, description)].add((label, target))
            relation = normalize_ref(row.get("reference_type") or "")
            anchor_types = ast.literal_eval(row.get("anchors_types") or "[]")
            anchor_ids = ast.literal_eval(row.get("anchor_ids") or "[]")
            if len(anchor_types) == 1 and len(anchor_ids) == 1 and relation:
                anchor_label = normalize_ref(anchor_types[0])
                semantic_relations[(scene_id, label, relation, anchor_label)].add(target)
                scene_labels[scene_id].add(anchor_label)
            counts[f"reference_type:{relation or 'EMPTY'}"] += 1
            counts["rows"] += 1
    exact_groups = {key: next(iter(values)) for key, values in group_sets.items() if len(values) == 1}
    counts["scene_class_groups"] = len(group_sets)
    counts["exact_consistent_scene_class_groups"] = len(exact_groups)
    counts["inconsistent_scene_class_groups"] = len(group_sets) - len(exact_groups)
    counts["scenes"] = len(scene_labels)
    counts["classes"] = len({label for labels in scene_labels.values() for label in labels})

    branches = read_jsonl(args.branches)
    parsed_rows = read_jsonl(args.parsed)
    if args.limit is not None:
        parsed_rows = parsed_rows[: args.limit]
    parsed = {record_key(row): row for row in parsed_rows}
    oracles = {record_key(row): row for row in read_jsonl(args.oracles)}
    resolutions = {record_key(row): row for row in read_jsonl(args.resolutions)}
    current_prestate_keys = {record_key(row) for row in read_jsonl(args.current_prestates)}
    nr3d_targets = {record_key(row): row for row in read_jsonl(args.nr3d_target_candidates)}
    nr3d_count_keys = {record_key(row) for row in read_jsonl(args.nr3d_count_candidates)}
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    scenes = catalog["scenes"]
    hypo_scannet = {str(row["scene_id"]) for row in branches if str(row["scene_id"]).startswith("scene")}
    sr3d_scenes = {key[0] for key in exact_groups}
    counts["hypo_scannet_scenes"] = len(hypo_scannet)
    counts["hypo_scannet_with_sr3d_exact_groups"] = len(hypo_scannet & sr3d_scenes)
    counts["hypo_scannet_without_sr3d_exact_groups"] = len(hypo_scannet - sr3d_scenes)

    target_candidates: list[dict[str, Any]] = []
    new_target_by_key: dict[tuple[str, str, str], tuple[str, int, str]] = {}
    for key in sorted(parsed):
        if key in resolutions or key in nr3d_targets or not key[0].startswith("scene"):
            continue
        refs = [str(value) for value in (parsed[key].get("intervention") or {}).get("target_ref_texts") or []]
        if len(refs) != 1:
            continue
        matches = exact_descriptions.get((key[0], normalized_descriptor(refs[0])), set())
        method = "EXACT_SR3D_UTTERANCE"
        if not matches:
            parts = relation_parts(refs[0])
            if parts is not None:
                target_class = class_from_text(parts[0], scene_labels.get(key[0], set()))
                anchor_class = class_from_text(parts[2], scene_labels.get(key[0], set()))
                if target_class and anchor_class:
                    target_ids = semantic_relations.get((key[0], target_class, parts[1], anchor_class), set())
                    matches = {(target_class, target_id) for target_id in target_ids}
                    method = "EXACT_SR3D_STRUCTURED_RELATION"
        if len(matches) != 1:
            if len(matches) > 1:
                counts["new_target_match_ambiguous"] += 1
            continue
        label, target_id = next(iter(matches))
        new_target_by_key[key] = (label, target_id, method)
        counts[f"new_target_resolution:{method}"] += 1
        target_candidates.append({
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "target_ref_text": refs[0], "target_class": label,
            "source_instance_id": target_id,
            "resolved_entity_id": f"hypo3d:{key[0]}:sr3d:{target_id:04d}",
            "resolution_tier": f"ANNOTATION_ALIGNED_{method}",
        })

    count_candidates: list[dict[str, Any]] = []
    for key in sorted(parsed.keys() & oracles.keys()):
        if key in current_prestate_keys or key in nr3d_count_keys:
            continue
        atoms = oracles[key].get("normalized_atoms") or []
        if len(atoms) != 1 or atoms[0].get("predicate") != "COUNT":
            continue
        matching = [
            (label, ids) for (scene_id, label), ids in exact_groups.items()
            if scene_id == key[0] and ref_mentions_class(str(atoms[0].get("subject") or ""), label)
        ]
        if len(matching) != 1:
            continue
        label, ids = matching[0]
        pre_count = len(ids)
        intervention = parsed[key]["intervention"]
        change_type = intervention.get("type")
        delta: int | None = None
        target_source = None
        if change_type == "ADDITION":
            refs = intervention.get("new_entity_ref_texts") or []
            if len(refs) == 1 and ref_mentions_class(str(refs[0]), label):
                delta = explicit_quantity(str(refs[0]))
        elif change_type in {"REMOVAL", "REPLACEMENT"}:
            old_class = resolved_class(resolutions.get(key), scenes.get(key[0]))
            if old_class is not None:
                target_source = "EXISTING_OFFICIAL_RESOLUTION"
            elif key in nr3d_targets:
                old_class, target_source = str(nr3d_targets[key]["target_class"]), "EXACT_NR3D_UTTERANCE"
            elif key in new_target_by_key:
                old_class, _, target_source = new_target_by_key[key]
            if change_type == "REMOVAL" and old_class == label:
                delta = -1
            elif change_type == "REPLACEMENT" and old_class is not None:
                refs = intervention.get("new_entity_ref_texts") or []
                if len(refs) == 1 and explicit_quantity(str(refs[0])) == 1:
                    delta = (-1 if old_class == label else 0) + (
                        1 if ref_mentions_class(str(refs[0]), label) else 0
                    )
                    if delta == 0:
                        delta = None
        if delta is None or pre_count + delta != atoms[0].get("value"):
            continue
        counts["new_replayable_count_prestate_candidate"] += 1
        count_candidates.append({
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "entity_class": label, "pre_count": pre_count, "delta": delta,
            "derived_post_count": pre_count + delta, "change_type": change_type,
            "target_resolution_source": target_source,
            "status": "AUDIT_CANDIDATE_EXACT_SR3D_STIMULUS_COUNT",
        })

    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    target_path = args.output_dir / "target_candidates.sr3d_v1.jsonl"
    count_path = args.output_dir / "count_candidates.sr3d_v1.jsonl"
    target_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in target_candidates))
    count_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in count_candidates))
    report = {
        "schema_version": "hypo3d_sr3d_coverage_audit_v1",
        "status": "SR3D_STRUCTURED_COVERAGE_AUDITED",
        "run_id": args.run_id, "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "truth_policy": "OFFICIAL_SR3D_STIMULUS_INSTANCE_SET_EXACT_UTTERANCE_OR_STRUCTURED_RELATION_ONLY",
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (
                args.sr3d, args.branches, args.parsed, args.oracles, args.resolutions,
                args.current_prestates, args.nr3d_target_candidates,
                args.nr3d_count_candidates, args.catalog,
            )
        },
        "output_hashes": {
            str(target_path): sha256_file(target_path), str(count_path): sha256_file(count_path),
        },
    }
    report_path = args.output_dir / "report.sr3d_coverage_v1.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
