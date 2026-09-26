from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.prestates import explicit_quantity, ref_mentions_class
from spaceconflict.hypo3d_l4.resolve_targets import normalize_ref


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row["scene_id"]),
        str(row["change_id"]),
        str(row.get("question_id") or row.get("source_question_id")),
    )


def decode_stimulus(value: str) -> tuple[str, str, int, int, tuple[int, ...]]:
    parts = value.split("-", maxsplit=4)
    if len(parts) not in {4, 5}:
        raise ValueError(f"malformed stimulus_id: {value}")
    scene_id, label, raw_count, raw_target = parts[:4]
    distractors = tuple(int(item) for item in (parts[4].split("-") if len(parts) == 5 else []) if item)
    count = int(raw_count)
    target = int(raw_target)
    if len(distractors) != count - 1:
        raise ValueError(f"stimulus count mismatch: {value}")
    return scene_id, normalize_ref(label.replace("_", " ")), count, target, distractors


def load_nr3d(path: Path) -> tuple[
    dict[tuple[str, str], tuple[int, ...]],
    dict[tuple[str, str], set[tuple[str, int]]],
    Counter[str],
]:
    group_sets: dict[tuple[str, str], set[tuple[int, ...]]] = defaultdict(set)
    descriptions: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    counts: Counter[str] = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = {"stimulus_id", "utterance", "scan_id", "instance_type", "target_id"}
        if not expected.issubset(reader.fieldnames or []):
            raise ValueError(f"missing Nr3D columns: {sorted(expected - set(reader.fieldnames or []))}")
        for row in reader:
            scene_id, label, count, target, distractors = decode_stimulus(row["stimulus_id"])
            if (
                scene_id != row["scan_id"]
                or label != normalize_ref(row["instance_type"])
                or target != int(row["target_id"])
            ):
                raise ValueError(f"redundant Nr3D fields disagree: {row['stimulus_id']}")
            instance_ids = tuple(sorted((target, *distractors)))
            if len(instance_ids) != count or len(set(instance_ids)) != count:
                raise ValueError(f"invalid instance set: {row['stimulus_id']}")
            group_sets[(scene_id, label)].add(instance_ids)
            description = normalize_ref(row["utterance"])
            if description:
                descriptions[(scene_id, description)].add((label, target))
            counts["rows"] += 1
    exact_groups = {
        key: next(iter(values))
        for key, values in group_sets.items()
        if len(values) == 1
    }
    counts["scene_class_groups"] = len(group_sets)
    counts["exact_consistent_scene_class_groups"] = len(exact_groups)
    counts["inconsistent_scene_class_groups"] = len(group_sets) - len(exact_groups)
    counts["scenes"] = len({key[0] for key in group_sets})
    counts["classes"] = len({key[1] for key in group_sets})
    counts["unique_normalized_descriptions"] = len(descriptions)
    return exact_groups, descriptions, counts


def resolved_class(
    resolution: dict[str, Any] | None,
    scene: dict[str, Any] | None,
) -> str | None:
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
    parser.add_argument("--nr3d", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--current-prestates", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="hypo3d_nr3d_coverage_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)
    if args.dry_run:
        print(json.dumps({"status": "PLANNED", "output_dir": str(args.output_dir)}, indent=2))
        return

    exact_groups, descriptions, counts = load_nr3d(args.nr3d)
    branches = read_jsonl(args.branches)
    parsed_rows = read_jsonl(args.parsed)
    if args.limit is not None:
        parsed_rows = parsed_rows[: args.limit]
    parsed = {record_key(row): row for row in parsed_rows}
    oracles = {record_key(row): row for row in read_jsonl(args.oracles)}
    resolutions = {record_key(row): row for row in read_jsonl(args.resolutions)}
    current_prestate_keys = {record_key(row) for row in read_jsonl(args.current_prestates)}
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    scenes = catalog["scenes"]

    hypo_scannet = {str(row["scene_id"]) for row in branches if str(row["scene_id"]).startswith("scene")}
    nr3d_scenes = {key[0] for key in exact_groups}
    counts["hypo_scannet_scenes"] = len(hypo_scannet)
    counts["hypo_scannet_with_nr3d_exact_groups"] = len(hypo_scannet & nr3d_scenes)
    counts["hypo_scannet_without_nr3d_exact_groups"] = len(hypo_scannet - nr3d_scenes)
    missing_catalog = {scene_id for scene_id in hypo_scannet if scene_id not in scenes}
    counts["hypo_scannet_missing_current_catalog"] = len(missing_catalog)
    counts["missing_catalog_scene_recovered_by_nr3d"] = len(missing_catalog & nr3d_scenes)

    overlap_comparisons = Counter()
    for (scene_id, label), instance_ids in exact_groups.items():
        if scene_id not in hypo_scannet or scene_id not in scenes:
            continue
        current = [
            obj for obj in scenes[scene_id].get("objects") or []
            if normalize_ref(str(obj.get("class") or "")) == label
        ]
        current_ids = {
            int(obj["source_bbox_id"])
            for obj in current if isinstance(obj.get("source_bbox_id"), int)
        }
        overlap_comparisons["groups"] += 1
        if len(current) == len(instance_ids):
            overlap_comparisons["count_equal"] += 1
        else:
            overlap_comparisons["count_mismatch"] += 1
        if current_ids == set(instance_ids):
            overlap_comparisons["instance_id_set_equal"] += 1
        elif current_ids:
            overlap_comparisons["instance_id_set_mismatch"] += 1
    for name, value in overlap_comparisons.items():
        counts[f"overlap:{name}"] = value

    target_candidates: list[dict[str, Any]] = []
    new_target_by_key: dict[tuple[str, str, str], tuple[str, int]] = {}
    for key in sorted(parsed.keys()):
        if key in resolutions or not key[0].startswith("scene"):
            continue
        refs = list((parsed[key].get("intervention") or {}).get("target_ref_texts") or [])
        if len(refs) != 1:
            continue
        matches = descriptions.get((key[0], normalize_ref(str(refs[0]))), set())
        if len(matches) != 1:
            if len(matches) > 1:
                counts["exact_description_target_ambiguous"] += 1
            continue
        label, target_id = next(iter(matches))
        new_target_by_key[key] = (label, target_id)
        counts["new_exact_description_target_resolution"] += 1
        target_candidates.append({
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "target_ref_text": refs[0], "target_class": label,
            "source_instance_id": target_id,
            "resolved_entity_id": f"hypo3d:{key[0]}:nr3d:{target_id:04d}",
            "resolution_tier": "ANNOTATION_ALIGNED_EXACT_NR3D_UTTERANCE",
        })

    count_candidates: list[dict[str, Any]] = []
    for key in sorted(parsed.keys() & oracles.keys()):
        atom_list = oracles[key].get("normalized_atoms") or []
        if len(atom_list) != 1 or atom_list[0].get("predicate") != "COUNT":
            continue
        query_subject = str(atom_list[0].get("subject") or "")
        matching_groups = [
            (label, ids) for (scene_id, label), ids in exact_groups.items()
            if scene_id == key[0] and ref_mentions_class(query_subject, label)
        ]
        if len(matching_groups) != 1:
            continue
        label, instance_ids = matching_groups[0]
        pre_count = len(instance_ids)
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
            elif key in new_target_by_key:
                old_class = new_target_by_key[key][0]
                target_source = "EXACT_NR3D_UTTERANCE"
            if change_type == "REMOVAL" and old_class == label:
                delta = -1
            elif change_type == "REPLACEMENT" and old_class is not None:
                new_refs = intervention.get("new_entity_ref_texts") or []
                if len(new_refs) == 1 and explicit_quantity(str(new_refs[0])) == 1:
                    old_delta = -1 if old_class == label else 0
                    new_delta = 1 if ref_mentions_class(str(new_refs[0]), label) else 0
                    if old_delta + new_delta != 0:
                        delta = old_delta + new_delta
        if delta is None or pre_count + delta != atom_list[0].get("value"):
            continue
        if key in current_prestate_keys:
            counts["nr3d_replay_matches_existing_prestate"] += 1
            continue
        counts["new_replayable_count_prestate_candidate"] += 1
        count_candidates.append({
            "scene_id": key[0], "change_id": key[1], "question_id": key[2],
            "entity_class": label, "pre_count": pre_count, "delta": delta,
            "derived_post_count": pre_count + delta,
            "change_type": change_type, "target_resolution_source": target_source,
            "status": "AUDIT_CANDIDATE_EXACT_NR3D_STIMULUS_COUNT",
        })

    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    target_path = args.output_dir / "target_candidates.nr3d_v1.jsonl"
    count_path = args.output_dir / "count_candidates.nr3d_v1.jsonl"
    target_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in target_candidates))
    count_path.write_bytes(b"".join(canonical_json(row) + b"\n" for row in count_candidates))
    report = {
        "schema_version": "hypo3d_nr3d_coverage_audit_v1",
        "status": "NR3D_STRUCTURED_COVERAGE_AUDITED",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "truth_policy": "OFFICIAL_NR3D_STIMULUS_INSTANCE_SET_AND_EXACT_UTTERANCE_MATCH_ONLY",
        "input_hashes": {
            str(path): sha256_file(path)
            for path in (
                args.nr3d, args.branches, args.parsed, args.oracles, args.resolutions,
                args.current_prestates, args.catalog,
            )
        },
        "output_hashes": {
            str(target_path): sha256_file(target_path),
            str(count_path): sha256_file(count_path),
        },
    }
    report_path = args.output_dir / "report.nr3d_coverage_v1.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
