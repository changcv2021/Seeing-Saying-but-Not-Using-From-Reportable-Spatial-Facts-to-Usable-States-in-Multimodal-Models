from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json
from spaceconflict.hypo3d_l4.resolve_targets import normalize_ref


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row["scene_id"]), str(row["change_id"]), str(row.get("question_id") or row.get("source_question_id"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vg", type=Path, required=True)
    parser.add_argument("--parsed", type=Path, required=True)
    parser.add_argument("--oracles", type=Path, required=True)
    parser.add_argument("--resolutions", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    source_to_scene = {
        str(scene["source_scene_id"]): scene_id for scene_id, scene in catalog["scenes"].items()
    }
    bbox_to_object = {
        (str(scene["source_scene_id"]), int(obj["source_bbox_id"])): str(obj["object_id"])
        for scene in catalog["scenes"].values()
        for obj in scene["objects"]
        if isinstance(obj.get("source_bbox_id"), int)
    }
    vg_payload = json.loads(args.vg.read_text(encoding="utf-8"))
    phrases: dict[tuple[str, str], set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for split in ("train", "val"):
        for row in vg_payload.get(split, []):
            scan_id = str(row.get("scan_id") or "")
            if scan_id not in source_to_scene:
                continue
            counts["hypo_vg_records"] += 1
            text = str(row.get("text") or "")
            tokens = row.get("tokens_positive") or {}
            ids = [*(row.get("target_id") or []), *(row.get("anchor_ids") or [])]
            for raw_id in ids:
                try:
                    bbox_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                object_id = bbox_to_object.get((scan_id, bbox_id))
                if object_id is None:
                    continue
                spans = tokens.get(str(raw_id), tokens.get(raw_id, []))
                for span in spans or []:
                    if not isinstance(span, list) or len(span) != 2:
                        continue
                    start, end = span
                    if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(text)):
                        continue
                    phrase = normalize_ref(text[start:end])
                    if phrase:
                        phrases[(scan_id, phrase)].add(object_id)
                        counts["grounded_phrase_occurrences"] += 1
    del vg_payload
    counts["unique_grounded_phrases"] = len(phrases)
    counts["hypo_scenes_with_vg_phrases"] = len({scan_id for scan_id, _ in phrases})

    parsed = {key(row): row for row in read_jsonl(args.parsed)}
    oracles = {key(row): row for row in read_jsonl(args.oracles)}
    resolutions = {key(row): row for row in read_jsonl(args.resolutions)}
    candidates: list[dict[str, Any]] = []
    for current_key, parsed_row in sorted(parsed.items()):
        scene = catalog["scenes"].get(current_key[0])
        if not isinstance(scene, dict):
            continue
        scan_id = str(scene["source_scene_id"])
        intervention = parsed_row["intervention"]
        resolution = resolutions.get(current_key)
        target_resolved = bool(resolution and resolution.get("resolved_targets")) or intervention.get("type") == "ADDITION"
        target_refs = intervention.get("target_ref_texts") or []
        if not target_resolved and len(target_refs) == 1:
            object_ids = phrases.get((scan_id, normalize_ref(str(target_refs[0]))), set())
            if len(object_ids) == 1:
                counts["new_exact_target_resolutions"] += 1
                candidates.append({
                    "scene_id": current_key[0], "change_id": current_key[1], "question_id": current_key[2],
                    "role": "target", "ref_text": target_refs[0],
                    "resolved_entity_id": next(iter(object_ids)),
                    "resolution_tier": "MMSCAN_VG_EXACT_GROUNDED_SPAN",
                })
            elif len(object_ids) > 1:
                counts["reject_exact_target_phrase_ambiguous"] += 1

        if intervention.get("type") == "MOVEMENT" and current_key in oracles:
            explicit = intervention.get("explicit_relations") or []
            if len(explicit) == 1:
                anchor_ref = str(explicit[0].get("anchor_ref_text") or "")
                object_ids = phrases.get((scan_id, normalize_ref(anchor_ref)), set())
                if len(object_ids) == 1:
                    counts["movement_exact_anchor_resolutions"] += 1
                    candidates.append({
                        "scene_id": current_key[0], "change_id": current_key[1], "question_id": current_key[2],
                        "role": "anchor", "ref_text": anchor_ref,
                        "resolved_entity_id": next(iter(object_ids)),
                        "resolution_tier": "MMSCAN_VG_EXACT_GROUNDED_SPAN",
                    })
                elif len(object_ids) > 1:
                    counts["reject_exact_anchor_phrase_ambiguous"] += 1

    report = {
        "schema_version": "hypo3d_mmscan_vg_grounding_audit_v1",
        "status": "MMSCAN_VG_EXACT_GROUNDING_AUDITED",
        "counts": dict(sorted(counts.items())),
        "candidate_record_count": len(candidates),
        "truth_policy": "EXACT_NORMALIZED_HUMAN_GROUNDING_SPAN_AND_UNIQUE_BBOX_ID_ONLY",
        "input_hashes": {str(path): sha256_file(path) for path in (
            args.vg, args.parsed, args.oracles, args.resolutions, args.catalog,
        )},
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "candidates.mmscan_vg_exact_grounding_v1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in candidates)
    )
    (args.output_dir / "report.mmscan_vg_exact_grounding_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
