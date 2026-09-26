#!/usr/bin/env python3
"""Audit whether SPAR-7M single-image bbox relations support strict L2 chains.

Entity identity is asserted only when two annotations use the exact same image
path and exact same integer bbox.  Directional relations are normalized to
LEFT_OF or ABOVE before enumerating unique two-premise transitive paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spaceconflict.adapters.spar import adapt_qualitative_relation
from spaceconflict.hashing import sha256_file


SCAN_VERSION = "spar_7m_l2_bbox_chain_scan_v1"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _bbox(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 1:
        return None
    box = value[0]
    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(v, int) for v in box):
        return None
    return tuple(box)


def _normalized_edge(predicate: str, red: str, blue: str) -> tuple[str, str, str] | None:
    if predicate == "LEFT_OF":
        return predicate, red, blue
    if predicate == "RIGHT_OF":
        return "LEFT_OF", blue, red
    if predicate == "ABOVE":
        return predicate, red, blue
    if predicate == "BELOW":
        return "ABOVE", blue, red
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    input_path = args.input.resolve()
    report_path = args.report.resolve()
    candidates_path = args.candidates.resolve()
    rows_checked = 0
    single_image_rows = 0
    accepted_rows = 0
    reject_counts: Counter[str] = Counter()
    # (image, normalized predicate) -> (subject bbox, object bbox) -> provenance list
    groups: dict[tuple[str, str], dict[tuple[str, str], list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    with input_path.open("r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle):
            if not line.strip():
                continue
            rows_checked += 1
            row = json.loads(line)
            if row.get("qa_type") != "obj_spatial_relation_oo":
                continue
            single_image_rows += 1
            images = row.get("image") or []
            red_box, blue_box = _bbox(row.get("red_bbox")), _bbox(row.get("blue_bbox"))
            if len(images) != 1 or red_box is None or blue_box is None or red_box == blue_box:
                reject_counts["INVALID_SINGLE_IMAGE_BBOX_IDENTITY"] += 1
                continue
            adapted = adapt_qualitative_relation(row, row_index)
            if adapted.status != "SOURCE_REFERENCE_VALID":
                for code in adapted.reject_codes or ["ADAPTER_REJECTED"]:
                    reject_counts[code] += 1
                continue
            accepted_rows += 1
            image = str(images[0])
            red = "bbox:" + ",".join(map(str, red_box))
            blue = "bbox:" + ",".join(map(str, blue_box))
            for fact in adapted.facts:
                edge = _normalized_edge(fact["predicate"], red, blue)
                if edge is None:
                    continue
                predicate, subject, object_ = edge
                groups[(image, predicate)][(subject, object_)].append({
                    "source_item_id": adapted.source_item_id,
                    "source_record_hash": adapted.source_record_hash,
                    "original_predicate": fact["predicate"],
                    "question": row.get("question"),
                    "answer": row.get("answer"),
                    "base_dataset": row.get("base_dataset"),
                    "scene_id": row.get("scene_id"),
                })

    candidates: list[dict[str, Any]] = []
    direct_conclusion_exclusions = 0
    ambiguous_path_exclusions = 0
    source_inconsistency_exclusions = 0
    for (image, predicate), edge_map in sorted(groups.items()):
        direct = set(edge_map)
        # Any pair stated in both directions is unsuitable source evidence.
        inconsistent_nodes = {
            node for subject, object_ in direct if (object_, subject) in direct
            for node in (subject, object_)
        }
        outgoing: dict[str, list[str]] = defaultdict(list)
        for subject, object_ in sorted(direct):
            outgoing[subject].append(object_)
        paths: dict[tuple[str, str], list[str]] = defaultdict(list)
        for subject, middle in sorted(direct):
            for object_ in outgoing.get(middle, []):
                if subject == object_:
                    continue
                paths[(subject, object_)].append(middle)
        for (subject, object_), middles in sorted(paths.items()):
            if (subject, object_) in direct:
                direct_conclusion_exclusions += 1
                continue
            unique_middles = sorted(set(middles))
            if len(unique_middles) != 1:
                ambiguous_path_exclusions += 1
                continue
            middle = unique_middles[0]
            if {subject, middle, object_} & inconsistent_nodes:
                source_inconsistency_exclusions += 1
                continue
            first_rows = sorted(edge_map[(subject, middle)], key=lambda x: x["source_item_id"])
            second_rows = sorted(edge_map[(middle, object_)], key=lambda x: x["source_item_id"])
            source_item_ids = sorted({
                row["source_item_id"] for row in first_rows + second_rows
            })
            if len(source_item_ids) < 2:
                continue
            candidate_core = {
                "image": image, "predicate": predicate,
                "subject": subject, "middle": middle, "object": object_,
                "source_item_ids": source_item_ids,
            }
            candidates.append({
                "candidate_id": "spar_l2_chain:" + hashlib.sha256(_json_bytes(candidate_core)).hexdigest()[:24],
                **candidate_core,
                "base_dataset": first_rows[0]["base_dataset"],
                "scene_id": first_rows[0]["scene_id"],
                "premise_1_provenance": first_rows,
                "premise_2_provenance": second_rows,
                "identity_policy": "EXACT_SAME_IMAGE_PATH_AND_INTEGER_BBOX",
                "direct_conclusion_absent": True,
                "unique_two_premise_path": True,
            })

    candidates.sort(key=lambda row: row["candidate_id"])
    predicate_counts = Counter(row["predicate"] for row in candidates)
    dataset_counts = Counter(str(row["base_dataset"]) for row in candidates)
    world_counts = Counter(f"{row['base_dataset']}:{row['scene_id']}" for row in candidates)
    candidate_payload = b"".join(_json_bytes(row) + b"\n" for row in candidates)
    relative_candidates = str(candidates_path.relative_to(root))
    report = {
        "schema_version": "1.0", "scan_version": SCAN_VERSION,
        "status": "STRICT_L2_CHAINS_FOUND" if candidates else "NO_STRICT_L2_CHAINS_FOUND",
        "run_id": args.run_id,
        "input": str(input_path.relative_to(root)), "input_sha256": sha256_file(input_path),
        "rows_checked": rows_checked, "single_image_rows": single_image_rows,
        "adapter_accepted_rows": accepted_rows, "adapter_reject_counts": dict(sorted(reject_counts.items())),
        "image_predicate_groups": len(groups), "strict_candidate_count": len(candidates),
        "candidate_world_count": len(world_counts), "candidate_predicate_counts": dict(sorted(predicate_counts.items())),
        "candidate_dataset_counts": dict(sorted(dataset_counts.items())),
        "direct_conclusion_exclusions": direct_conclusion_exclusions,
        "ambiguous_path_exclusions": ambiguous_path_exclusions,
        "source_inconsistency_exclusions": source_inconsistency_exclusions,
        "identity_policy": "EXACT_SAME_IMAGE_PATH_AND_INTEGER_BBOX",
        "minimality_policy": "UNIQUE_TWO_PREMISE_PATH_AND_NO_DIRECT_CONCLUSION",
        "media_validation_scope": "OFFICIAL_ANNOTATION_PATH_AND_BBOX_REFERENCES_ONLY_NO_LOCAL_PIXEL_BYTES",
        "output_hashes": {relative_candidates: "sha256:" + hashlib.sha256(candidate_payload).hexdigest()},
    }
    report_payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
    for path, payload in ((candidates_path, candidate_payload), (report_path, report_payload)):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not args.resume:
                raise FileExistsError(path)
            if path.read_bytes() != payload:
                raise ValueError(f"NON_DETERMINISTIC_OUTPUT:{path}")
        else:
            path.write_bytes(payload)
    print(report_payload.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
