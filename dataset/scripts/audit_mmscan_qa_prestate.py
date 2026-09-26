from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.hashing import sha256_file
from spaceconflict.hypo3d_l4.common import canonical_json


DIRECTION_TOKEN = {
    "left": "LEFT_OF",
    "right": "RIGHT_OF",
    "front": "FRONT_OF",
    "back": "BEHIND",
    "above": "ABOVE",
    "below": "BELOW",
}
TRANSITION_FIELDS = {"change_id", "branch_id", "context_change", "intervention", "post_state"}
TRANSITION_WORDS = re.compile(
    r"\b(?:hypothetical|after the change|after moving|after removing|after adding|"
    r"moved|removed|replaced|relocated|intervention)\b",
    re.IGNORECASE,
)
RELATIVE_QUESTION = re.compile(
    r"(?:position|location|direction)\s+of\s+(.+?)\s+"
    r"(?:relative to|in relation to|with respect to|compared to)\s+(.+?)(?:\?|$)",
    re.IGNORECASE,
)


def exact_direction_answer(answer: str) -> list[str] | None:
    value = " ".join(re.sub(r"[^a-z]+", " ", answer.casefold()).split())
    for prefix in ("it is ", "the answer is ", "the direction is "):
        if value.startswith(prefix):
            value = value[len(prefix):]
    tokens = value.split()
    if not tokens or any(token not in DIRECTION_TOKEN for token in tokens):
        return None
    return [DIRECTION_TOKEN[token] for token in tokens]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--run-id", default="mmscan_qa_prestate_v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.output_dir.exists() and not args.resume:
        raise FileExistsError(args.output_dir)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    source_to_scene = {
        str(scene["source_scene_id"]): scene_id
        for scene_id, scene in catalog["scenes"].items()
    }
    bbox_ids = {
        (str(scene["source_scene_id"]), int(obj["source_bbox_id"]))
        for scene in catalog["scenes"].values()
        for obj in scene["objects"]
        if isinstance(obj.get("source_bbox_id"), int)
    }

    payload = json.loads(args.qa.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("MMScan QA must be a split-valued object")
    counts: Counter[str] = Counter()
    subclasses: Counter[str] = Counter()
    fields: set[str] = set()
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    diagnostic_candidates: list[dict[str, Any]] = []

    for split in ("train", "val"):
        rows = payload.get(split) or []
        if not isinstance(rows, list):
            raise ValueError(f"MMScan QA split {split} is not a list")
        for row in rows[: args.limit]:
            if not isinstance(row, dict):
                continue
            counts["all_records"] += 1
            fields.update(str(key) for key in row)
            scan_id = str(row.get("scan_id") or "")
            if scan_id not in source_to_scene:
                continue
            counts["hypo_scene_records"] += 1
            subclass = str(row.get("sub_class") or "UNKNOWN")
            subclasses[subclass] += 1
            if len(samples[subclass]) < 2:
                samples[subclass].append({
                    "scan_id": scan_id,
                    "question": row.get("question"),
                    "answers": row.get("answers"),
                    "object_ids": row.get("object_ids"),
                    "object_names": row.get("object_names"),
                })
            if TRANSITION_FIELDS & set(row):
                counts["records_with_transition_field"] += 1
            question = str(row.get("question") or "")
            if TRANSITION_WORDS.search(question):
                counts["records_with_transition_language"] += 1
            if row.get("input_bboxes_id") is not None or row.get("input_bboxes") is not None:
                counts["records_with_input_bbox"] += 1
            if row.get("output_bboxes_id") is not None or row.get("output_bboxes") is not None:
                counts["records_with_output_bbox"] += 1

            answers = row.get("answers") or []
            direction_atoms = None
            for answer in answers:
                direction_atoms = exact_direction_answer(str(answer))
                if direction_atoms:
                    break
            if not direction_atoms:
                continue
            counts["exact_categorical_direction_answer"] += 1
            match = RELATIVE_QUESTION.search(question)
            if match is None:
                counts["direction_answer_without_supported_relative_question"] += 1
                continue
            ids = row.get("object_ids") or []
            names = row.get("object_names") or []
            if len(ids) != 2 or len(names) != 2:
                counts["direction_relation_without_exactly_two_objects"] += 1
                continue
            try:
                aligned = all((scan_id, int(raw_id)) in bbox_ids for raw_id in ids)
            except (TypeError, ValueError):
                aligned = False
            if not aligned:
                counts["direction_relation_object_ids_not_in_catalog"] += 1
                continue
            counts["diagnostic_direction_relations_two_aligned_ids"] += 1
            diagnostic_candidates.append({
                "scan_id": scan_id,
                "scene_id": source_to_scene[scan_id],
                "record_id": row.get("ID"),
                "question": question,
                "answer": next(str(a) for a in answers if exact_direction_answer(str(a))),
                "normalized_predicates": direction_atoms,
                "object_ids": ids,
                "object_names": names,
                "status": "DIAGNOSTIC_ONLY_OBJECT_ROLE_ORDER_NOT_DOCUMENTED",
            })

    missing_transition_fields = sorted(TRANSITION_FIELDS - fields)
    report = {
        "schema_version": "mmscan_qa_prestate_audit_v1",
        "status": "MMSCAN_QA_PRESTATE_AUDITED",
        "run_id": args.run_id,
        "seed": args.seed,
        "counts": dict(sorted(counts.items())),
        "hypo_scene_subclass_counts": dict(sorted(subclasses.items())),
        "observed_fields": sorted(fields),
        "missing_transition_fields": missing_transition_fields,
        "diagnostic_candidate_count": len(diagnostic_candidates),
        "formal_prestate_candidate_count": 0,
        "formal_exclusion_reason": (
            "README_DOCUMENTS_OBJECT_IDS_AS_INVOLVED_GT_ONLY_AND_DOES_NOT_DOCUMENT_"
            "SUBJECT_OBJECT_ROLE_ORDER; STATIC_QA_HAS_NO_HYPO3D_BRANCH_ID"
        ),
        "truth_policy": "STATIC_PRE_SCENE_QA_ONLY_NEVER_POST_TRANSITION_TRUTH",
        "input_hashes": {str(path): sha256_file(path) for path in (args.qa, args.catalog)},
        "subclass_samples": dict(sorted(samples.items())),
    }
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    args.output_dir.mkdir(parents=True, exist_ok=args.resume)
    (args.output_dir / "diagnostic_direction_candidates.v1.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in diagnostic_candidates)
    )
    (args.output_dir / "report.mmscan_qa_prestate_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
