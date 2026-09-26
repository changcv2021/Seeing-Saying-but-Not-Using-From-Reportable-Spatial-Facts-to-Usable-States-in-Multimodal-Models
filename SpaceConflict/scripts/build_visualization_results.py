#!/usr/bin/env python3
"""Build paper tables, figures, audits, and English qualitative examples.

This is a read-only analysis over frozen SpaceConflict releases.  It never
changes release artifacts and it never fabricates model results.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
NEGATION_RE = re.compile(r"\b(?:no|not|never|neither|nor|without|isn't|aren't|wasn't|weren't|doesn't|don't|didn't|cannot|can't)\b", re.I)
PRONOUN_RE = re.compile(r"\b(?:it|its|they|them|their|this|that|these|those|he|she|his|her)\b", re.I)
HASHLIKE_TOKEN_RE = re.compile(r"^[0-9a-f]{6,}$", re.I)
WORDCLOUD_STOPWORDS = {
    # Standard English function words.
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "may", "might", "more", "most",
    "no", "not", "of", "on", "or", "our", "ours", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "then", "there", "these", "they", "this", "those", "to", "too",
    "was", "we", "were", "what", "when", "where", "which", "while", "who", "will", "with", "would", "you",
    "your", "yours", "after", "before", "during", "within", "according", "considering", "let", "denote",
    # Repeated benchmark realization/context scaffolding, removed per the guide.
    "actual", "available", "category", "change", "claim", "context", "current", "declared", "designated",
    "entity", "evidence", "exactly", "fixed", "frame", "image", "instance", "instances", "media", "object",
    "observed", "question", "reference", "represented", "scene", "scope", "source", "support", "total",
    "visible", "view", "views", "post", "pre", "state",
    # Numeric words and high-frequency realization scaffolding identified in
    # the exact companion frequencies (not semantic object/relation content).
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "number", "bbox", "bounding", "box", "marked", "target", "queried",
    "perspective", "origin", "observer", "primary", "red", "blue", "images", "hypothetical",
    "intervention", "following", "complete", "stated", "once",
}
WORDCLOUD_DIRECTIONAL_TERMS = {
    # Spatial directions, comparative geometry, and their realization verbs.
    "left", "right", "above", "below", "behind", "front", "ahead", "across", "under", "underneath",
    "over", "near", "nearer", "nearest", "far", "farther", "farthest", "between", "beside", "alongside",
    "inside", "outside", "north", "south", "east", "west", "upper", "lower", "top", "bottom",
    "position", "positioned", "positioning", "lies", "located", "direction", "side", "opposite",
    # Temporal-direction/order realizations are removed for the same reason: they
    # otherwise dominate L2/L3 and hide scene-content nouns.
    "first", "last", "appearance", "appears", "occur", "occurs", "occurred", "earlier", "later",
    "before", "afterward", "precedes", "preceded", "comes", "timeline", "video", "videos", "second",
    "seconds", "viewed",
}


def parse_args(default_action: str = "all") -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/visualization_results_v1.yaml")
    parser.add_argument("--release-version", default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--l4-track-annotation-file", default=None, help="Optional versioned pair_id-to-track overlay; frozen L4 inputs remain unchanged.")
    parser.add_argument("--action", choices=["all", "tables", "main-figures", "supp-figures", "audits", "examples", "manifest"], default=default_action)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=None, help="Debug-only maximum records per JSONL input.")
    parser.add_argument("--resume", action="store_true", help="Reuse the output directory; deterministic files are overwritten.")
    parser.add_argument("--dry-run", action="store_true", help="Validate paths/configuration and print the planned actions without writing outputs.")
    return parser.parse_args()


def resolved(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def iter_jsonl(path: Path, limit: int | None = None) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        emitted = 0
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Non-object JSONL record at {path}:{line_number}")
            yield line_number, value
            emitted += 1
            if limit is not None and emitted >= limit:
                return


def require(record: dict[str, Any], fields: list[str], path: Path, line_number: int) -> None:
    missing = [field for field in fields if field not in record]
    if missing:
        raise ValueError(f"Missing required fields {missing} at {path}:{line_number}")


def json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def csv_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(df: pd.DataFrame) -> str:
    def clean(value: Any) -> str:
        if pd.isna(value):
            return "Not available"
        return str(value).replace("|", "\\|").replace("\n", " ")

    headers = [clean(x) for x in df.columns]
    rows = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for values in df.itertuples(index=False, name=None):
        rows.append("| " + " | ".join(clean(x) for x in values) + " |")
    return "\n".join(rows) + "\n"


def export_table(out: Path, stem: str, rows: list[dict[str, Any]], caption: str) -> None:
    df = pd.DataFrame(rows)
    table_dir = out / ("tables/main" if stem.startswith("table_main_") else "tables/supplementary")
    table_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(table_dir / f"{stem}.csv", index=False)
    json_dump(table_dir / f"{stem}.json", rows)
    (table_dir / f"{stem}.md").write_text(f"# {caption}\n\n{markdown_table(df)}", encoding="utf-8")
    try:
        latex = df.to_latex(index=False, escape=True, caption=caption, label=f"tab:{stem}")
        (table_dir / f"{stem}.tex").write_text(latex, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - CSV/JSON/Markdown remain authoritative.
        (table_dir / f"{stem}.tex.error.txt").write_text(str(exc), encoding="utf-8")


def save_figure(fig: plt.Figure, out: Path, stem: str, supplementary: bool = False) -> None:
    directory = out / ("figures/supplementary" if supplementary else "figures/main")
    directory.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf", "svg"):
        kwargs = {"dpi": 240} if suffix == "png" else {}
        fig.savefig(directory / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white", **kwargs)
    plt.close(fig)


def tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "")]


def normalize_surface(text: str) -> str:
    return " ".join(tokens(text))


def entropy(counter: collections.Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    return -sum((v / total) * math.log2(v / total) for v in counter.values() if v)


def safe_pct(numerator: int | float, denominator: int | float) -> float | None:
    return (100.0 * numerator / denominator) if denominator else None


def atom_from_claim(claim: dict[str, Any]) -> dict[str, Any]:
    normalized = claim.get("normalized", {})
    atoms = normalized.get("atoms", []) if isinstance(normalized, dict) else []
    if atoms:
        atom = dict(atoms[0])
        context = normalized.get("context", {})
        if isinstance(context, dict):
            atom.update({f"context.{k}": v for k, v in context.items()})
        return atom
    graph = claim.get("graph", {})
    return dict(graph) if isinstance(graph, dict) else {}


def changed_slots(supported: dict[str, Any], contradictory: dict[str, Any]) -> list[str]:
    a, b = atom_from_claim(supported), atom_from_claim(contradictory)
    ignored = {"atom_id", "claim_graph_id", "label"}
    keys = sorted((set(a) | set(b)) - ignored)
    return [key.replace("context.", "") for key in keys if a.get(key) != b.get(key)] or ["Not recoverable"]


def media_view_count(media: dict[str, Any]) -> int:
    refs = media.get("source_references", [])
    count = 0
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and isinstance(ref.get("frame_roles"), dict):
                count += len(ref["frame_roles"])
            elif isinstance(ref, dict) and isinstance(ref.get("support_frames"), list):
                count += 1 + len(ref["support_frames"])
            else:
                count += 1
    if count:
        return count
    ids = media.get("media_ids", [])
    return len(ids) if isinstance(ids, list) else int(bool(ids))


def l4_claim_text(claim: dict[str, Any]) -> str:
    value = claim.get("text", "")
    if isinstance(value, dict):
        return str(value.get("natural_text") or value.get("claim") or value.get("text") or "")
    return str(value)


def predicate_from_claim(claim: dict[str, Any]) -> str:
    atom = atom_from_claim(claim)
    return str(atom.get("predicate") or "Not available")


def prepare_data(cfg: dict[str, Any], limit: int | None) -> dict[str, Any]:
    inp = cfg["inputs"]
    base_pairs_path = resolved(Path(inp["base_release_dir"]) / "pairs.jsonl")
    base_unknown_path = resolved(Path(inp["base_release_dir"]) / "unknown_challenge.jsonl")
    sampled_path = resolved(inp["base_sampled_pairs"])
    l4_pairs_path = resolved(inp["l4_pair_file"])
    l4_unknown_path = resolved(inp["l4_unknown_file"])

    l4_track_annotations: dict[str, dict[str, Any]] = {}
    annotation_name = inp.get("l4_track_annotation_file")
    if annotation_name:
        annotation_path = resolved(annotation_name)
        for line_number, annotation in iter_jsonl(annotation_path, limit):
            require(annotation, ["pair_id", "primary_track", "secondary_tracks", "operator_id"], annotation_path, line_number)
            pid = str(annotation["pair_id"])
            if pid in l4_track_annotations:
                raise ValueError(f"Duplicate L4 track annotation for {pid}")
            l4_track_annotations[pid] = annotation

    quota = read_json(resolved(inp["base_quota_report"]))

    # The frozen Unknown export is intentionally compact. Some Unknown parents
    # belong to the proof-valid pool but were not quota-selected as binary pairs.
    # Recover their released metadata from the exact hashed candidate inputs named
    # by the quota report instead of incorrectly forcing a join to final pairs.
    unknown_meta: dict[str, dict[str, Any]] = {}
    for candidate_name in quota.get("input_hashes", {}):
        if not candidate_name.startswith("candidates/unknown/"):
            continue
        candidate_path = resolved(candidate_name)
        for line_number, item in iter_jsonl(candidate_path, limit):
            uid = item.get("unknown_id") or item.get("sample_id")
            if not uid:
                raise ValueError(f"Missing unknown_id at {candidate_path}:{line_number}")
            unknown_meta[str(uid)] = item

    proof_counts: collections.Counter[str] = collections.Counter()
    proof_meta: dict[str, dict[str, Any]] = {}
    for candidate_name in quota.get("input_hashes", {}):
        if not candidate_name.startswith("candidates/auto_accepted/"):
            continue
        candidate_path = resolved(candidate_name)
        for line_number, item in iter_jsonl(candidate_path, limit):
            dataset = item.get("source_dataset") or item.get("source", {}).get("source_dataset")
            if not dataset:
                raise ValueError(f"Missing source_dataset at {candidate_path}:{line_number}")
            pid = item.get("pair_id")
            if not pid:
                raise ValueError(f"Missing pair_id at {candidate_path}:{line_number}")
            proof_counts[str(dataset)] += 1
            proof_meta[str(pid)] = {
                "source_key": str(dataset),
                "world": item.get("global_world_id") or item.get("source", {}).get("global_world_id"),
                "split": item.get("split"),
                "level": item.get("level"),
                "primary_track": item.get("primary_track", "Not annotated in proof-valid parent"),
                "operator": item.get("operator_id", "Not annotated"),
                "style": item.get("selected_style_family", "Not annotated"),
                "changed_slots": changed_slots(item.get("supported_claim", {}), item.get("contradictory_claim", {})),
            }

    sampled_meta: dict[str, dict[str, Any]] = {}
    for line_number, item in iter_jsonl(sampled_path, limit):
        require(item, ["pair_id", "split"], sampled_path, line_number)
        sampled_meta[item["pair_id"]] = {
            "split": item["split"],
            "style": item.get("selected_style_family", "Not annotated"),
        }

    pairs: list[dict[str, Any]] = []
    pair_index: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []
    for line_number, item in iter_jsonl(base_pairs_path, limit):
        require(item, ["pair_id", "source", "media", "task", "supported_claim", "contradictory_claim"], base_pairs_path, line_number)
        pid = item["pair_id"]
        if pid not in sampled_meta:
            raise ValueError(f"Pair {pid} has no sampled split metadata")
        source_key = str(item["source"]["source_dataset"])
        media = item["media"]
        mids = media.get("media_ids", [])
        media_signature = "|".join(sorted(map(str, mids))) if isinstance(mids, list) else str(mids)
        secondary = item["task"].get("secondary_diagnostic_tags", [])
        changed = changed_slots(item["supported_claim"], item["contradictory_claim"])
        row = {
            "pair_id": pid,
            "source_key": source_key,
            "source": cfg["source_display_names"].get(source_key, source_key),
            "world": item["source"]["global_world_id"],
            "split": sampled_meta[pid]["split"],
            "level": item["task"]["level"],
            "primary_track": item["task"].get("primary_diagnostic_tag", "Not annotated in released pair"),
            "secondary_tracks": list(secondary) if isinstance(secondary, list) else [],
            "operator": item["task"].get("operator_id", "Not annotated"),
            "changed_slots": changed,
            "changed_slot": "+".join(changed),
            "media_type": media.get("media_type", "Not annotated"),
            "media_group": source_key + ":" + media_signature,
            "view_count": media_view_count(media),
            "branch": atom_from_claim(item["supported_claim"]).get("context.branch_id", "actual"),
            "origin": "L1-L3 released pair",
            "dependency_type": "Not applicable",
            "native_subtype": "Not applicable",
            "transition_family": "Not applicable",
            "grounding_mode": "Not annotated",
            "style": sampled_meta[pid]["style"],
            "source_item_ids": item["source"].get("source_item_ids", []),
            "raw": item,
        }
        pairs.append(row)
        pair_index[pid] = row
        for label, key in (("SUPPORTED", "supported_claim"), ("CONTRADICTORY", "contradictory_claim")):
            claim = item[key]
            claims.append({
                **{k: row[k] for k in ("pair_id", "source_key", "source", "world", "split", "level", "primary_track", "operator", "changed_slot", "media_type", "style")},
                "sample_id": f"{pid}:{label.lower()}",
                "label": label,
                "text": str(claim.get("natural_text", "")),
                "predicate": predicate_from_claim(claim),
                "unknown_reason": "Not applicable",
            })

    for line_number, item in iter_jsonl(l4_pairs_path, limit):
        require(item, ["pair_id", "global_world_id", "split", "supported_claim", "contradictory_claim", "l4_origin"], l4_pairs_path, line_number)
        pid = item["pair_id"]
        source_key = "hypo3d_native" if item["l4_origin"] == "SOURCE_NATIVE" else "hypo3d_controlled"
        media = item.get("media", {})
        media_values = [str(v) for v in media.values() if v] if isinstance(media, dict) else []
        changed = item.get("edit", {}).get("changed_slots") or changed_slots(item["supported_claim"], item["contradictory_claim"])
        task = item.get("task", {})
        track_annotation = l4_track_annotations.get(pid, {})
        primary = task.get("primary_track") or track_annotation.get("primary_track") or cfg["analysis_policy"]["l4_missing_track_label"]
        secondary = task.get("secondary_tracks") or track_annotation.get("secondary_tracks") or []
        operator = task.get("operator_id") or track_annotation.get("operator_id") or item.get("intervention", {}).get("operator_id") or item.get("intervention", {}).get("action_type") or "Not annotated"
        row = {
            "pair_id": pid,
            "source_key": source_key,
            "source": cfg["source_display_names"][source_key],
            "world": item["global_world_id"],
            "split": item["split"],
            "level": "L4",
            "primary_track": primary,
            "secondary_tracks": list(secondary),
            "operator": operator,
            "changed_slots": list(changed),
            "changed_slot": "+".join(changed),
            "media_type": "intervention_conditioned",
            "media_group": f"{item['global_world_id']}|{item.get('branch_id', pid)}",
            "view_count": len(media_values),
            "branch": item.get("branch_id", pid),
            "origin": item["l4_origin"],
            "dependency_type": item.get("dependency_type", "Not annotated"),
            "native_subtype": item.get("native_subtype") or "Not applicable",
            "transition_family": item.get("transition_family", "Not annotated"),
            "grounding_mode": item.get("grounding_mode", "Not annotated"),
            "style": item.get("realizer_version", "Not annotated"),
            "source_item_ids": [x for x in (item.get("source", {}).get("question_id"), item.get("source", {}).get("change_id")) if x],
            "track_annotation_source": "released" if task.get("primary_track") else (track_annotation.get("annotation_version") or "missing"),
            "raw": item,
        }
        pairs.append(row)
        pair_index[pid] = row
        for label, key in (("SUPPORTED", "supported_claim"), ("CONTRADICTORY", "contradictory_claim")):
            claim = item[key]
            claims.append({
                **{k: row[k] for k in ("pair_id", "source_key", "source", "world", "split", "level", "primary_track", "operator", "changed_slot", "media_type", "style")},
                "sample_id": f"{pid}:{label.lower()}",
                "label": label,
                "text": l4_claim_text(claim),
                "predicate": predicate_from_claim(claim),
                "unknown_reason": "Not applicable",
            })

    if limit is None:
        released_l4_ids = {row["pair_id"] for row in pairs if row["level"] == "L4"}
        unused_annotations = sorted(set(l4_track_annotations) - released_l4_ids)
        if unused_annotations:
            raise ValueError(f"L4 track overlay contains unknown pair IDs: {unused_annotations[:5]}")

    unknown: list[dict[str, Any]] = []
    for line_number, item in iter_jsonl(base_unknown_path, limit):
        require(item, ["sample_id", "pair_id", "claim", "label"], base_unknown_path, line_number)
        parent = pair_index.get(item["pair_id"])
        meta = unknown_meta.get(item["sample_id"])
        if meta is None:
            raise ValueError(f"Unknown sample {item['sample_id']} is absent from the quota-declared Unknown input pools")
        proof_parent = proof_meta.get(item["pair_id"])
        if parent is None and proof_parent is None:
            raise ValueError(f"Unknown sample {item['sample_id']} has no released or proof-valid parent metadata: {item['pair_id']}")
        withheld = item.get("media", {}).get("withheld_evidence", {})
        role = withheld.get("role", "unspecified view") if isinstance(withheld, dict) else "unspecified view"
        if parent is not None:
            parent_fields = {k: parent[k] for k in ("pair_id", "source_key", "source", "world", "split", "level", "primary_track", "operator", "changed_slot", "media_type", "style")}
        else:
            source_key = str(meta.get("source_dataset") or proof_parent["source_key"])
            parent_fields = {
                "pair_id": item["pair_id"],
                "source_key": source_key,
                "source": cfg["source_display_names"].get(source_key, source_key),
                "world": meta.get("global_world_id") or proof_parent["world"],
                "split": meta.get("split") or proof_parent["split"],
                "level": proof_parent["level"],
                "primary_track": proof_parent["primary_track"],
                "operator": proof_parent["operator"],
                "changed_slot": "+".join(proof_parent["changed_slots"]),
                "media_type": item.get("media", {}).get("media_type", "Not annotated"),
                "style": proof_parent["style"],
            }
        row = {
            **parent_fields,
            "sample_id": item["sample_id"],
            "label": "UNKNOWN",
            "text": str(item["claim"]),
            "predicate": "Not recoverable from released Unknown record",
            "unknown_reason": meta.get("unknown_reason", cfg["analysis_policy"]["base_unknown_reason"]),
            "unknown_detail": role,
            "unknown_origin": "EVIDENCE_ABLATION",
            "source_group": parent_fields["source"],
            "pipeline_failure": False,
            "witness_complete": "Audited by parent release chain",
            "raw": item,
        }
        unknown.append(row)
        claims.append({k: v for k, v in row.items() if k != "raw"})

    for line_number, item in iter_jsonl(l4_unknown_path, limit):
        require(item, ["sample_id", "global_world_id", "split", "label", "unknown_axis", "model_input"], l4_unknown_path, line_number)
        row = {
            "pair_id": item.get("base_determinate_sample_id", "Not available"),
            "source_key": "hypo3d_controlled",
            "source": "L4 Unknown",
            "world": item["global_world_id"],
            "split": item["split"],
            "level": "L4",
            "primary_track": cfg["analysis_policy"]["l4_missing_track_label"],
            "operator": "Unknown evidence intervention",
            "changed_slot": "withheld_evidence",
            "media_type": "intervention_conditioned",
            "style": "l4_unknown_v3",
            "sample_id": item["sample_id"],
            "label": "UNKNOWN",
            "text": str(item["model_input"].get("claim_text", "")),
            "predicate": str(item.get("claim_graph", {}).get("predicate", "Not available")),
            "unknown_reason": item["unknown_axis"],
            "unknown_detail": "+".join(map(str, item.get("missing_decisive_evidence", []))),
            "unknown_origin": item.get("unknown_origin", "Not annotated"),
            "source_group": item.get("source_group", "Not annotated"),
            "pipeline_failure": bool(item.get("pipeline_failure", False)),
            "witness_complete": bool(item.get("positive_witness_completion")) and bool(item.get("negative_witness_completion")),
            "raw": item,
        }
        unknown.append(row)
        claims.append({k: v for k, v in row.items() if k != "raw"})

    return {
        "pairs": pairs,
        "claims": claims,
        "unknown": unknown,
        "pair_index": pair_index,
        "proof_counts": proof_counts,
        "quota": quota,
        "release_audit": read_json(resolved(inp["base_release_audit"])),
        "replay_audit": read_json(resolved(inp["base_replay_audit"])),
        "shortcut_audit": read_json(resolved(inp["base_shortcut_audit"])),
        "l4_manifest": read_json(resolved(inp["l4_manifest"])),
        "l4_audit": read_json(resolved(inp["l4_final_audit"])),
        "l4_native": read_json(resolved(inp["l4_native_report"])),
        "l4_controlled": read_json(resolved(inp["l4_controlled_report"])),
        "l4_unknown_report": read_json(resolved(inp["l4_unknown_report"])),
    }


def count_rows(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    counter: collections.Counter[tuple[Any, ...]] = collections.Counter(tuple(item.get(k, "Not annotated") for k in keys) for item in items)
    return [{**{key: values[i] for i, key in enumerate(keys)}, "Count": count} for values, count in sorted(counter.items(), key=lambda x: tuple(map(str, x[0])))]


def build_tables(out: Path, cfg: dict[str, Any], data: dict[str, Any]) -> None:
    pairs, claims, unknown = data["pairs"], data["claims"], data["unknown"]
    source_keys = list(cfg["source_display_names"])
    table1: list[dict[str, Any]] = []
    for key in source_keys:
        selected = [p for p in pairs if p["source_key"] == key]
        meta = cfg["source_metadata"][key]
        table1.append({
            "Source": cfg["source_display_names"][key],
            "World unit": meta["world_unit"],
            "Media type(s)": ", ".join(sorted({p["media_type"] for p in selected})) or "No released pairs",
            "Native GT / QA information": meta["native_information"],
            "Released level(s)": ", ".join(sorted({p["level"] for p in selected})) or "None",
            "Released primary track(s)": ", ".join(sorted({p["primary_track"] for p in selected})) or "None",
            "Planned track scope": ", ".join(cfg["planned_tracks"][key]),
            "Final accepted pairs": len(selected),
            "Unique binary-pair worlds": len({p["world"] for p in selected}),
            "Release mode": meta["release_mode"],
        })
    export_table(out, "table_main_1_source_roles", table1, "Table 1. Source roles and released coverage")

    table2: list[dict[str, Any]] = []
    for split in ("train", "dev", "test", "Overall"):
        ps = pairs if split == "Overall" else [p for p in pairs if p["split"] == split]
        us = unknown if split == "Overall" else [u for u in unknown if u["split"] == split]
        released_worlds = {p["world"] for p in ps} | {u["world"] for u in us}
        table2.append({
            "Split": split,
            "Released worlds (pairs or Unknown)": len(released_worlds),
            "Binary-pair media groups": len({p["media_group"] for p in ps}),
            "Branches": len({(p["world"], p["branch"]) for p in ps if p["level"] == "L4"}),
            "Minimal pairs": len(ps),
            "Binary claims": 2 * len(ps),
            "Unknown claims": len(us),
            "All claims": 2 * len(ps) + len(us),
        })
    export_table(out, "table_main_2_overall_split_statistics", table2, "Table 2. Composite release statistics by world-disjoint split")

    l4 = [p for p in pairs if p["level"] == "L4"]
    l4_groups = [
        ("L4 Native — Direct", lambda p: p["origin"] == "SOURCE_NATIVE" and p["native_subtype"] == "DIRECT"),
        ("L4 Native — Aggregated", lambda p: p["origin"] == "SOURCE_NATIVE" and p["native_subtype"] == "AGGREGATED"),
        ("L4 Controlled — Core", lambda p: p["origin"] == "BENCHMARK_CONTROLLED" and p["dependency_type"] == "CORE"),
        ("L4 Controlled — Calibration", lambda p: p["origin"] == "BENCHMARK_CONTROLLED" and p["dependency_type"] == "CALIBRATION"),
    ]
    table3: list[dict[str, Any]] = []
    for label, test in l4_groups:
        group = [p for p in l4 if test(p)]
        table3.append({
            "L4 component": label,
            "Pairs": len(group),
            "Percent of L4 pairs": round(safe_pct(len(group), len(l4)) or 0, 2),
            "Worlds": len({p["world"] for p in group}),
            "Train / Dev / Test": " / ".join(str(sum(p["split"] == split for p in group)) for split in ("train", "dev", "test")),
            "Transition families": ", ".join(sorted({p["transition_family"] for p in group})),
            "Grounding": ", ".join(sorted({p["grounding_mode"] for p in group})),
        })
    table3.append({
        "L4 component": "L4 Unknown",
        "Pairs": "Not applicable",
        "Percent of L4 pairs": "Not applicable",
        "Worlds": len({u["world"] for u in unknown if u["level"] == "L4"}),
        "Train / Dev / Test": " / ".join(str(sum(u["level"] == "L4" and u["split"] == split for u in unknown)) for split in ("train", "dev", "test")),
        "Transition families": f"{sum(u['level'] == 'L4' for u in unknown)} Unknown claims",
        "Grounding": "Positive and negative witness completions",
    })
    export_table(out, "table_main_3_l4_three_part_composition", table3, "Table 3. L4 three-part composition")

    worlds_by_split = {s: ({p["world"] for p in pairs if p["split"] == s} | {u["world"] for u in unknown if u["split"] == s}) for s in ("train", "dev", "test")}
    leakage = len((worlds_by_split["train"] & worlds_by_split["dev"]) | (worlds_by_split["train"] & worlds_by_split["test"]) | (worlds_by_split["dev"] & worlds_by_split["test"]))
    l4_audit = data["l4_audit"]
    ra, replay, shortcut = data["release_audit"], data["replay_audit"], data["shortcut_audit"]
    duplicate_unknown = len(unknown) - len({normalize_surface(u["text"]) for u in unknown})
    binary = [c for c in claims if c["label"] != "UNKNOWN"]
    table4 = [
        {"Audit": "World overlap across train/dev/test", "Failures": leakage, "Denominator": len(set().union(*worlds_by_split.values())), "Result": "PASS" if leakage == 0 else "FAIL", "Scope": "Composite release"},
        {"Audit": "L1–L3 release audit", "Failures": len(ra.get("failures", [])), "Denominator": ra["pair_count"], "Result": ra["status"], "Scope": "production_available_v10"},
        {"Audit": "L1–L3 replay-chain audit", "Failures": replay["failure_count"], "Denominator": replay["pair_count"], "Result": replay["status"], "Scope": "production_available_v10"},
        {"Audit": "L4 schema validation", "Failures": sum(l4_audit["schema_validation"].values()), "Denominator": l4_audit["counts"]["binary_pairs"] + l4_audit["counts"]["unknown_claims"], "Result": l4_audit["status"], "Scope": "L4 v3.3"},
        {"Audit": "L4 media file presence/hash", "Failures": l4_audit["media"]["missing"] + l4_audit["media"]["hash_fail"], "Denominator": l4_audit["counts"]["unique_media_files"], "Result": "PASS", "Scope": "L4 v3.3"},
        {"Audit": "Duplicate Unknown surfaces", "Failures": duplicate_unknown, "Denominator": len(unknown), "Result": "PASS" if duplicate_unknown == 0 else "REVIEW", "Scope": "Composite release"},
        {"Audit": "Explicit negation in binary claims", "Failures": sum(bool(NEGATION_RE.search(c["text"])) for c in binary), "Denominator": len(binary), "Result": "DESCRIPTIVE", "Scope": "Composite release"},
        {"Audit": "Static text-only label shortcut", "Failures": "Not applicable", "Denominator": "0.50 majority baseline", "Result": f"accuracy={shortcut['controls']['text_only']['accuracy']:.2f}; {shortcut['controls']['text_only']['leakage_assessment']}", "Scope": "L1–L3 construction-time control; not an MLLM result"},
    ]
    export_table(out, "table_main_4_quality_audits", table4, "Table 4. Automatic quality, reproducibility, and leakage audits")

    # Supplementary A: registry, capabilities, and proof-valid-to-release yield.
    a1 = [{
        "Source key": key,
        "Display name": cfg["source_display_names"][key],
        "Enabled in composite": any(p["source_key"] == key for p in pairs),
        "Pairs": sum(p["source_key"] == key for p in pairs),
        "Worlds": len({p["world"] for p in pairs if p["source_key"] == key}),
        "Release mode": cfg["source_metadata"][key]["release_mode"],
    } for key in source_keys]
    export_table(out, "table_supp_A1_source_registry", a1, "Table A1. Source registry snapshot")
    a2 = [{
        "Source": cfg["source_display_names"][key],
        "Released levels": ", ".join(sorted({p["level"] for p in pairs if p["source_key"] == key})) or "None",
        "Released primary tracks": ", ".join(sorted({p["primary_track"] for p in pairs if p["source_key"] == key})) or "None",
        "Planned track scope": ", ".join(cfg["planned_tracks"][key]),
        "Important limitation": "Primary track is reported as unannotated when absent; no analysis-time inference is used." if key.startswith("hypo3d") else "Coverage is measured from accepted released pairs.",
    } for key in source_keys]
    export_table(out, "table_supp_A2_contract_capabilities", a2, "Table A2. Contract and released capability coverage")
    accepted_by_source = collections.Counter(p["source_key"] for p in pairs if p["level"] != "L4")
    a3 = []
    for key in ("spar", "ca_vqa", "vsi_bench", "sti_bench", "omnispatial"):
        proof = data["proof_counts"].get(key, 0)
        accepted = accepted_by_source.get(key, 0)
        a3.append({"Source": cfg["source_display_names"][key], "Proof-valid candidate pairs": proof, "Final accepted pairs": accepted, "Quota/cap exclusions": proof - accepted, "Acceptance among proof-valid candidates (%)": round(safe_pct(accepted, proof) or 0, 2), "Denominator definition": "Proof-valid AUTO_ACCEPTED parent pool"})
    a3.extend([
        {"Source": "Hypo3D Native", "Proof-valid candidate pairs": data["l4_native"]["funnel"]["eligible_candidates"] + data["l4_native"]["funnel"]["frozen_pairs_available"], "Final accepted pairs": data["l4_native"]["counts"]["accepted_pairs"], "Quota/cap exclusions": "Stages overlap; see native funnel", "Acceptance among proof-valid candidates (%)": "Not reported across overlapping frozen/new pools", "Denominator definition": "Eligible new candidates plus frozen-pair pool"},
        {"Source": "Controlled scenes", "Proof-valid candidate pairs": data["l4_controlled"]["funnel"]["raw_candidates"], "Final accepted pairs": data["l4_controlled"]["counts"]["accepted_pairs"], "Quota/cap exclusions": data["l4_controlled"]["funnel"]["raw_candidates"] - data["l4_controlled"]["counts"]["accepted_pairs"], "Acceptance among proof-valid candidates (%)": round(safe_pct(data["l4_controlled"]["counts"]["accepted_pairs"], data["l4_controlled"]["funnel"]["raw_candidates"]) or 0, 2), "Denominator definition": "Deterministically generated controlled candidates"},
    ])
    export_table(out, "table_supp_A3_construction_yield", a3, "Table A3. Construction yield with denominator definitions")

    export_table(out, "table_supp_B1_dataset_by_level", count_rows(pairs, "source", "level"), "Table B1. Source by level")
    export_table(out, "table_supp_B2_dataset_by_primary_track", count_rows(pairs, "source", "primary_track"), "Table B2. Source by released primary track")
    export_table(out, "table_supp_B3_level_by_primary_track", count_rows(pairs, "level", "primary_track"), "Table B3. Level by released primary track")
    all_tags = []
    for p in pairs:
        all_tags.append({"Level": p["level"], "Tag role": "Primary", "Diagnostic tag": p["primary_track"], "Pair ID": p["pair_id"]})
        all_tags.extend({"Level": p["level"], "Tag role": "Secondary", "Diagnostic tag": tag, "Pair ID": p["pair_id"]} for tag in p["secondary_tracks"])
    tag_counts = collections.Counter((x["Level"], x["Tag role"], x["Diagnostic tag"]) for x in all_tags)
    export_table(out, "table_supp_B4_all_diagnostic_tags", [{"Level": a, "Tag role": b, "Diagnostic tag": c, "Count": n} for (a, b, c), n in sorted(tag_counts.items())], "Table B4. Primary and secondary diagnostic tags")
    export_table(out, "table_supp_B5_modality_by_level", count_rows(pairs, "media_type", "level"), "Table B5. Modality by level")
    export_table(out, "table_supp_B6_operator_level_changed_slot", count_rows(pairs, "operator", "level", "changed_slot"), "Table B6. Operator, level, and changed slot")

    export_table(out, "table_supp_C1_l4_origin_subtype", count_rows(l4, "origin", "native_subtype", "dependency_type"), "Table C1. L4 origin and subtype")
    export_table(out, "table_supp_C2_l4_transition_family", count_rows(l4, "origin", "transition_family"), "Table C2. L4 transition families")
    controlled = data["l4_controlled"]
    export_table(out, "table_supp_C3_controlled_provenance", [{"Source group": k, "Pairs": v, "Percent of controlled pairs": round(100 * v / controlled["counts"]["accepted_pairs"], 2)} for k, v in sorted(controlled["counts"]["source_groups"].items())], "Table C3. Controlled-scene provenance")
    export_table(out, "table_supp_C4_controlled_transition_checks", [{"Quality gate": k, "Passed": v, "Denominator / scope": "All applicable controlled accepted pairs"} for k, v in sorted(controlled["quality_gates"].items())], "Table C4. Controlled transition quality gates")

    reason_rows = count_rows(unknown, "level", "unknown_reason", "unknown_origin")
    export_table(out, "table_supp_D1_unknown_reason_level", reason_rows, "Table D1. Unknown reason by level")
    d2 = []
    for u in unknown:
        d2.append({"Level": u["level"], "Unknown reason": u["unknown_reason"], "Pipeline failure": u["pipeline_failure"], "Witness-completion status": u["witness_complete"]})
    d2c = collections.Counter(tuple(r.values()) for r in d2)
    export_table(out, "table_supp_D2_unknown_validity", [{"Level": k[0], "Unknown reason": k[1], "Pipeline failure": k[2], "Witness-completion status": k[3], "Count": v} for k, v in sorted(d2c.items(), key=lambda x: tuple(map(str, x[0])))], "Table D2. Unknown validity and witness checks")

    reject_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for reason, n in data["quota"].get("cap_reject_counts", {}).items():
        reject_counts[("L1–L3 quota selection", reason)] += n
    for path_key, scope in (("l4_native_rejects", "L4 Native"), ("l4_controlled_rejects", "L4 Controlled")):
        path = resolved(cfg["inputs"][path_key])
        for _, item in iter_jsonl(path):
            reject_counts[(scope, str(item.get("reason", "MALFORMED_REASON_MISSING")))] += 1
    e1 = [{"Pipeline scope": scope, "Reject code": reason, "Count": n} for (scope, reason), n in sorted(reject_counts.items())]
    export_table(out, "table_supp_E1_rejection_reasons", e1, "Table E1. Structured rejection reasons")

    language_rows = []
    for c in claims:
        tt = tokens(c["text"])
        language_rows.append({
            "Label": c["label"], "Level": c["level"], "Source": c["source"], "Words": len(tt),
            "Characters": len(c["text"]), "Explicit negation": bool(NEGATION_RE.search(c["text"])),
            "Pronoun present": bool(PRONOUN_RE.search(c["text"])), "Entity mentions": len(set(re.findall(r"\bentity\s+[A-Z]\b", c["text"]))),
            "Clause heuristic": 1 + len(re.findall(r"[,;:]|\b(?:and|but|while|because|which|that)\b", c["text"], re.I)),
            "Style / realizer": c["style"], "Predicate": c["predicate"], "Changed slot": c["changed_slot"],
        })
    lang_df = pd.DataFrame(language_rows)
    f1 = []
    for label, frame in lang_df.groupby("Label"):
        f1.append({"Label": label, "Claims": len(frame), "Mean words": round(frame["Words"].mean(), 3), "Median words": round(frame["Words"].median(), 3), "Min words": int(frame["Words"].min()), "Max words": int(frame["Words"].max()), "Explicit negation count": int(frame["Explicit negation"].sum()), "Pronoun count": int(frame["Pronoun present"].sum()), "Mean clause heuristic": round(frame["Clause heuristic"].mean(), 3)})
    export_table(out, "table_supp_F1_language_length_balance", f1, "Table F1. Language length and surface balance")
    export_table(out, "table_supp_F2_realization_family", [{"Label": a, "Style / realizer": b, "Count": n} for (a, b), n in sorted(collections.Counter((c["label"], c["style"]) for c in claims).items())], "Table F2. Realization family by label")
    label_surface = []
    for label in ("SUPPORTED", "CONTRADICTORY"):
        subset = [c for c in claims if c["label"] == label]
        label_surface.append({"Label": label, "Claims": len(subset), "Unique exact surfaces": len({c["text"] for c in subset}), "Unique normalized surfaces": len({normalize_surface(c["text"]) for c in subset}), "Style entropy (bits)": round(entropy(collections.Counter(c["style"] for c in subset)), 4), "Explicit-negation rate (%)": round(safe_pct(sum(bool(NEGATION_RE.search(c["text"])) for c in subset), len(subset)) or 0, 4)})
    export_table(out, "table_supp_F3_label_surface_balance", label_surface, "Table F3. Binary label surface balance")

    media_splits: dict[str, set[str]] = collections.defaultdict(set)
    source_item_splits: dict[str, set[str]] = collections.defaultdict(set)
    for p in pairs:
        media_splits[p["media_group"]].add(p["split"])
        for sid in p["source_item_ids"]:
            source_item_splits[f"{p['source_key']}:{sid}"].add(p["split"])
    g1 = [
        {"Leakage key": "global_world_id (binary pairs and Unknown)", "Cross-split overlaps": leakage, "Unique keys": len({p["world"] for p in pairs} | {u["world"] for u in unknown}), "Policy": "Must be zero"},
        {"Leakage key": "media_group", "Cross-split overlaps": sum(len(v) > 1 for v in media_splits.values()), "Unique keys": len(media_splits), "Policy": "Reported; world split is authoritative"},
        {"Leakage key": "source_item_id", "Cross-split overlaps": sum(len(v) > 1 for v in source_item_splits.values()), "Unique keys": len(source_item_splits), "Policy": "Reported with source namespace"},
    ]
    export_table(out, "table_supp_G1_split_leakage", g1, "Table G1. Cross-split leakage audit")
    surfaces = collections.defaultdict(set)
    normalized = collections.defaultdict(set)
    for c in claims:
        surfaces[c["text"]].add(c["split"])
        normalized[normalize_surface(c["text"])].add(c["split"])
    g2 = [
        {"Duplicate definition": "Exact binary-claim surface", "Duplicate claims": len(binary) - len({c["text"] for c in binary}), "Denominator": len(binary), "Cross-split duplicate surfaces": sum(len(v) > 1 for k, v in surfaces.items() if any(c["label"] != "UNKNOWN" and c["text"] == k for c in claims)), "Notes": "Exact Unicode string"},
        {"Duplicate definition": "Normalized all-claim surface", "Duplicate claims": len(claims) - len(normalized), "Denominator": len(claims), "Cross-split duplicate surfaces": sum(len(v) > 1 for v in normalized.values()), "Notes": cfg["analysis_policy"]["exact_duplicate_normalization"]},
        {"Duplicate definition": "Semantic near duplicate", "Duplicate claims": "Not available", "Denominator": len(claims), "Cross-split duplicate surfaces": "Not available", "Notes": "No declared semantic threshold in the release; not guessed."},
    ]
    export_table(out, "table_supp_G2_duplicate_audit", g2, "Table G2. Exact, normalized, and semantic duplicate audit")

    base_pairs = [p for p in pairs if p["level"] != "L4"]
    base_unknown = [u for u in unknown if u["level"] != "L4"]
    i1 = [
        {"Release view": "production_available_v10", "Levels": "L1–L3", "Worlds (pairs or Unknown)": len({p["world"] for p in base_pairs} | {u["world"] for u in base_unknown}), "Pairs": len(base_pairs), "Binary claims": 2 * len(base_pairs), "Unknown claims": len(base_unknown), "Status": data["release_audit"]["status"]},
        {"Release view": cfg["release_version"], "Levels": "L1–L4", "Worlds (pairs or Unknown)": len({p["world"] for p in pairs} | {u["world"] for u in unknown}), "Pairs": len(pairs), "Binary claims": 2 * len(pairs), "Unknown claims": len(unknown), "Status": "Composite read-only analysis view; both source releases retain their manifests"},
    ]
    export_table(out, "table_supp_I1_release_evolution", i1, "Table I1. Release evolution")

    # Data tables used directly by figures.
    exports = out / "data_exports"
    exports.mkdir(parents=True, exist_ok=True)
    csv_dump(exports / "pair_analysis_rows.csv", [{k: v for k, v in p.items() if k != "raw" and k not in {"secondary_tracks", "changed_slots", "source_item_ids"}} for p in pairs])
    csv_dump(exports / "claim_language_rows.csv", language_rows)
    json_dump(exports / "analysis_summary.json", {
        "released_worlds_including_unknown": len({p["world"] for p in pairs} | {u["world"] for u in unknown}),
        "binary_pair_worlds": len({p["world"] for p in pairs}), "binary_pair_media_groups": len({p["media_group"] for p in pairs}),
        "minimal_pairs": len(pairs), "binary_claims": len(binary), "unknown_claims": len(unknown),
        "levels": dict(collections.Counter(p["level"] for p in pairs)),
        "sources": dict(collections.Counter(p["source"] for p in pairs)),
    })


def heatmap(ax: plt.Axes, rows: list[str], cols: list[str], counter: collections.Counter[tuple[str, str]], title: str, percent_by_row: bool = True) -> None:
    matrix = np.array([[counter.get((row, col), 0) for col in cols] for row in rows], dtype=float)
    display = matrix.copy()
    if percent_by_row:
        denom = matrix.sum(axis=1, keepdims=True)
        display = np.divide(matrix, denom, out=np.zeros_like(matrix), where=denom != 0) * 100
    im = ax.imshow(display, cmap="Blues", aspect="auto", vmin=0)
    ax.set_xticks(range(len(cols)), cols, rotation=35, ha="right")
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title(title, loc="left", fontweight="bold")
    for i in range(len(rows)):
        for j in range(len(cols)):
            value = int(matrix[i, j])
            label = f"{value:,}\n{display[i,j]:.1f}%" if percent_by_row else f"{value:,}"
            ax.text(j, i, label, ha="center", va="center", fontsize=7, color="white" if display[i, j] > max(35, display.max() * .55) else "#222")
    plt.colorbar(im, ax=ax, fraction=0.035, pad=0.02, label="Row percentage" if percent_by_row else "Count")


def wordcloud_frequencies(claims: list[dict[str, Any]]) -> dict[str, collections.Counter[str]]:
    """Return guide-compliant frequencies for L1-L4 binary claims and Unknown."""
    groups = {name: collections.Counter() for name in ("L1", "L2", "L3", "L4", "UNKNOWN")}
    for claim in claims:
        if claim["label"] == "UNKNOWN":
            group = "UNKNOWN"
        elif claim["level"] in {"L1", "L2", "L3", "L4"}:
            group = claim["level"]
        else:
            continue
        clean_tokens = [
            token for token in tokens(claim["text"])
            if token not in WORDCLOUD_STOPWORDS and token not in WORDCLOUD_DIRECTIONAL_TERMS and not any(character.isdigit() for character in token) and not HASHLIKE_TOKEN_RE.fullmatch(token) and len(token) > 1
        ]
        groups[group].update(clean_tokens)
    return groups


def wordcloud_contrastive_salience(
    groups: dict[str, collections.Counter[str]],
) -> tuple[dict[str, collections.Counter[str]], dict[str, int], dict[str, float]]:
    """Score frequent vocabulary higher when it occurs in fewer benchmark groups."""
    group_count = len(groups)
    document_frequency: collections.Counter[str] = collections.Counter()
    for counter in groups.values():
        document_frequency.update(counter.keys())
    idf = {
        token: math.log((group_count + 1.0) / (frequency + 0.5))
        for token, frequency in document_frequency.items()
    }
    salience: dict[str, collections.Counter[str]] = {}
    for group, counter in groups.items():
        scores: collections.Counter[str] = collections.Counter()
        for token, count in counter.items():
            scores[token] = math.sqrt(count) * (0.25 + idf[token]) ** 2
        salience[group] = scores
    return salience, dict(document_frequency), idf


def draw_deterministic_wordcloud(
    ax: plt.Axes,
    frequencies: collections.Counter[str],
    title: str,
    seed: int,
    max_words: int = 32,
    cmap_name: str = "Blues",
    token_denominator: int | None = None,
) -> None:
    """Place score-scaled words on a deterministic spiral without extra packages."""
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(title, loc="left", fontweight="bold", fontsize=12)
    items = frequencies.most_common(max_words)
    if not items:
        ax.text(.5, .5, "No eligible tokens", ha="center", va="center")
        return
    values = np.array([count for _, count in items], dtype=float)
    roots = np.sqrt(values)
    span = roots.max() - roots.min()
    rng = random.Random(seed)
    placed: list[tuple[float, float, float, float]] = []
    cmap = plt.get_cmap(cmap_name)
    for rank, (word, count) in enumerate(items):
        scale = (roots[rank] - roots.min()) / span if span else 1.0
        fontsize = 10.0 + 26.0 * scale
        # Approximate DejaVu Sans extents in axes coordinates.  Deliberately
        # conservative boxes keep the final vector text from touching.
        width = min(.74, .0165 * len(word) * fontsize / 12.0)
        height = .038 * fontsize / 12.0
        phase = rng.uniform(0, 2 * math.pi)
        position = None
        for attempt in range(1800):
            if attempt == 0:
                x, y = .5, .51
            else:
                radius = .0180 * math.sqrt(attempt)
                theta = phase + attempt * 2.399963229728653
                x = .5 + radius * math.cos(theta)
                y = .50 + .74 * radius * math.sin(theta)
            candidate = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
            if candidate[0] < .015 or candidate[1] < .03 or candidate[2] > .985 or candidate[3] > .96:
                continue
            overlap = any(not (candidate[2] + .010 < box[0] or candidate[0] - .010 > box[2] or candidate[3] + .012 < box[1] or candidate[1] - .012 > box[3]) for box in placed)
            if not overlap:
                position = (x, y, candidate)
                break
        if position is None:
            continue
        x, y, box = position
        placed.append(box)
        ax.text(x, y, word, ha="center", va="center", fontsize=fontsize,
                color=cmap(.90 - .45 * (rank / max(1, len(items) - 1))),
                fontweight="bold" if rank < 7 else "normal", transform=ax.transAxes)
    denominator = token_denominator if token_denominator is not None else int(sum(frequencies.values()))
    ax.text(.99, .01, f"n={denominator:,} retained tokens", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7, color="#666")


def build_main_figures(out: Path, cfg: dict[str, Any], data: dict[str, Any]) -> None:
    pairs = data["pairs"]
    # Figure 1: construction pipeline with a real English pair from the release.
    example = sorted(pairs, key=lambda x: x["pair_id"])[0]["raw"]
    if "natural_text" in example["supported_claim"]:
        pos = example["supported_claim"]["natural_text"]
        neg = example["contradictory_claim"]["natural_text"]
    else:
        pos = l4_claim_text(example["supported_claim"])
        neg = l4_claim_text(example["contradictory_claim"])
    fig, ax = plt.subplots(figsize=(15, 7.8))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    boxes = [
        (0.02, 0.63, 0.15, 0.18, "Upstream evidence\nsource GT / QA / media"),
        (0.21, 0.63, 0.15, 0.18, "Canonical world\nand evidence graph"),
        (0.40, 0.63, 0.15, 0.18, "Truth-fixed claim\nand typed edit"),
        (0.59, 0.63, 0.15, 0.18, "Proof certificate\nand independent replay"),
        (0.78, 0.63, 0.19, 0.18, "World-disjoint split\nand frozen release"),
    ]
    for i, (x, y, w, h, label) in enumerate(boxes):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015", facecolor="#EAF2F8", edgecolor="#2C3E50", linewidth=1.5))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10, fontweight="bold")
        if i < len(boxes) - 1:
            nx = boxes[i + 1][0]
            ax.add_patch(FancyArrowPatch((x + w, y + h / 2), (nx, y + h / 2), arrowstyle="-|>", mutation_scale=14, color="#555"))
    ax.text(0.02, 0.93, "SpaceConflict: evidence-to-release construction pipeline", fontsize=18, fontweight="bold")
    ax.text(0.02, 0.87, "Language is realized only after claim truth is fixed. Missing evidence becomes UNKNOWN, not FALSE.", fontsize=11, color="#444")
    ax.add_patch(FancyBboxPatch((0.03, 0.09), 0.94, 0.37, boxstyle="round,pad=0.02", facecolor="#FAFAFA", edgecolor="#888"))
    ax.text(0.05, 0.41, f"Released English minimal-pair example ({example['pair_id']})", fontsize=11, fontweight="bold")
    ax.text(0.05, 0.31, "SUPPORTED", color=cfg["colors"]["SUPPORTED"], fontsize=10, fontweight="bold")
    ax.text(0.23, 0.31, textwrap.fill(pos, 105), fontsize=8.7, va="center")
    ax.text(0.05, 0.18, "CONTRADICTORY", color=cfg["colors"]["CONTRADICTORY"], fontsize=10, fontweight="bold")
    ax.text(0.23, 0.18, textwrap.fill(neg, 105), fontsize=8.7, va="center")
    save_figure(fig, out, "figure_main_1_pipeline_overview")
    json_dump(out / "data_exports/figure_main_1_pipeline_overview.json", {"pair_id": example["pair_id"], "supported": pos, "contradictory": neg})

    # Figure 2: four coverage panels.
    sources = [cfg["source_display_names"][k] for k in cfg["source_display_names"]]
    levels = ["L1", "L2", "L3", "L4"]
    tracks = ["GEO-TOPO", "XFORM-PROJ", "IDENTITY", "DYNAMIC", "EMBODIED-OBS", cfg["analysis_policy"]["l4_missing_track_label"]]
    modalities = sorted({p["media_type"] for p in pairs})
    slots = sorted({p["changed_slot"] for p in pairs})
    fig, axes = plt.subplots(2, 2, figsize=(16, 12), constrained_layout=True)
    heatmap(axes[0,0], sources, levels, collections.Counter((p["source"], p["level"]) for p in pairs), "(a) Source × level")
    heatmap(axes[0,1], levels, tracks, collections.Counter((p["level"], p["primary_track"]) for p in pairs), "(b) Level × released primary track")
    heatmap(axes[1,0], modalities, levels, collections.Counter((p["media_type"], p["level"]) for p in pairs), "(c) Modality × level")
    slot_counter = collections.Counter(p["changed_slot"] for p in pairs)
    axes[1,1].barh(slots, [slot_counter[s] for s in slots], color="#4C78A8")
    axes[1,1].set_title("(d) Changed-slot distribution", loc="left", fontweight="bold")
    axes[1,1].set_xlabel("Minimal pairs")
    for y, slot in enumerate(slots):
        axes[1,1].text(slot_counter[slot], y, f" {slot_counter[slot]:,}", va="center", fontsize=8)
    fig.suptitle("Released coverage of levels, tracks, modalities, and semantic edits", fontsize=17, fontweight="bold")
    save_figure(fig, out, "figure_main_2_coverage_panels")
    csv_dump(out / "data_exports/figure_main_2_source_level.csv", count_rows(pairs, "source", "level"))
    csv_dump(out / "data_exports/figure_main_2_level_track.csv", count_rows(pairs, "level", "primary_track"))
    csv_dump(out / "data_exports/figure_main_2_modality_level.csv", count_rows(pairs, "media_type", "level"))
    csv_dump(out / "data_exports/figure_main_2_changed_slots.csv", [{"Changed slot": k, "Count": v} for k, v in sorted(slot_counter.items())])

    # Figure 3: comparable within-pipeline funnels, never aggregate incompatible raw units.
    q = data["quota"]
    l4n, l4c = data["l4_native"], data["l4_controlled"]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), constrained_layout=True, gridspec_kw={"width_ratios": [1.35, 1, .75]})
    base_stages = ["Proof-valid\nparent pool", "Quota-selected\npairs", "Release-audit\nPASS", "Replay-chain\nPASS"]
    base_values = [q["input_auto_accepted_count"], q["selected_pair_count"], data["release_audit"]["pair_count"], data["replay_audit"]["pair_count"]]
    axes[0].plot(base_stages, base_values, marker="o", linewidth=3, color="#4C78A8")
    axes[0].fill_between(range(len(base_values)), base_values, alpha=.12, color="#4C78A8")
    axes[0].set_title("(a) L1–L3 proof-valid selection", loc="left", fontweight="bold")
    axes[0].set_ylabel("Minimal pairs")
    for i, v in enumerate(base_values): axes[0].text(i, v, f" {v:,}", va="bottom", ha="center")
    native_stages = ["Raw QA", "Normalized\npost oracles", "Post-fact\ngraphs", "Eligible\nnew candidates", "Accepted\npairs"]
    native_values = [l4n["funnel"]["raw_qa_records"], l4n["funnel"]["normalized_post_oracles"], l4n["funnel"]["post_fact_graphs"], l4n["funnel"]["eligible_candidates"], l4n["funnel"]["accepted_pairs"]]
    ctrl_stages = ["Raw controlled\ncandidates", "Selected", "Accepted"]
    ctrl_values = [l4c["funnel"]["raw_candidates"], l4c["funnel"]["selected"], l4c["funnel"]["accepted"]]
    axes[1].plot(range(len(native_values)), native_values, marker="o", linewidth=2.5, color=cfg["colors"]["SOURCE_NATIVE"])
    axes[1].set_xticks(range(len(native_stages)), native_stages, rotation=15, ha="right")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Records / candidates (log scale)")
    axes[1].set_title("(b) L4 Native", loc="left", fontweight="bold")
    axes[1].grid(axis="y", alpha=.25)
    for i, v in enumerate(native_values): axes[1].text(i, v, f" {v:,}", va="bottom", ha="center", fontsize=8)
    axes[2].plot(range(len(ctrl_values)), ctrl_values, marker="s", linewidth=2.5, color=cfg["colors"]["BENCHMARK_CONTROLLED"])
    axes[2].set_xticks(range(len(ctrl_stages)), ctrl_stages, rotation=15, ha="right")
    axes[2].set_yscale("log")
    axes[2].set_title("(c) L4 Controlled", loc="left", fontweight="bold")
    axes[2].grid(axis="y", alpha=.25)
    for i, v in enumerate(ctrl_values): axes[2].text(i, v, f" {v:,}", va="bottom", ha="center", fontsize=8)
    fig.suptitle("Construction yield is shown only within comparable pipeline units", fontsize=16, fontweight="bold")
    save_figure(fig, out, "figure_main_3_construction_validation_funnels")
    csv_dump(out / "data_exports/figure_main_3_funnels.csv", ([{"Pipeline": "L1–L3", "Stage": s.replace("\n", " "), "Count": v} for s,v in zip(base_stages,base_values)] + [{"Pipeline": "L4 Native", "Stage": s.replace("\n", " "), "Count": v} for s,v in zip(native_stages,native_values)] + [{"Pipeline": "L4 Controlled", "Stage": s.replace("\n", " "), "Count": v} for s,v in zip(ctrl_stages,ctrl_values)]))


def build_supp_figures(out: Path, cfg: dict[str, Any], data: dict[str, Any]) -> None:
    pairs, claims, unknown = data["pairs"], data["claims"], data["unknown"]
    # B1: pair density per world.
    density = collections.Counter(p["world"] for p in pairs)
    values = np.array(sorted(density.values()))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    axes[0].hist(values, bins=np.arange(.5, values.max()+1.5), color="#4C78A8", edgecolor="white")
    axes[0].set(xlabel="Minimal pairs per world", ylabel="Worlds", title="(a) Pair density histogram")
    axes[1].plot(np.sort(values), np.arange(1, len(values)+1)/len(values), color="#E45756")
    axes[1].set(xlabel="Minimal pairs per world", ylabel="Cumulative fraction of worlds", title="(b) Empirical CDF")
    save_figure(fig, out, "figure_supp_B1_pairs_per_world", True)
    csv_dump(out / "data_exports/figure_supp_B1_pairs_per_world.csv", [{"World": k, "Pairs": v} for k,v in sorted(density.items())])

    # B2: media-group views and L4 branches.
    media_views: dict[str, int] = {}
    for p in pairs: media_views[p["media_group"]] = max(media_views.get(p["media_group"], 0), p["view_count"])
    branches = collections.Counter(p["world"] for p in pairs if p["level"] == "L4")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
    axes[0].hist(list(media_views.values()), bins=range(0, max(media_views.values())+2), color="#72B7B2", edgecolor="white")
    axes[0].set(xlabel="Materialized/referenced views per media group", ylabel="Media groups", title="(a) Media-group size")
    axes[1].hist(list(branches.values()), bins=range(0, max(branches.values())+2), color="#F58518", edgecolor="white")
    axes[1].set(xlabel="Accepted L4 branches/pairs per world", ylabel="Worlds", title="(b) L4 branch density")
    save_figure(fig, out, "figure_supp_B2_media_and_branch_density", True)
    csv_dump(out / "data_exports/figure_supp_B2_media_groups.csv", [{"Media group": k, "Views": v} for k,v in sorted(media_views.items())])

    # C1–C3.
    l4n, l4c = data["l4_native"], data["l4_controlled"]
    fig, ax = plt.subplots(figsize=(11, 5))
    stages = ["Native raw QA", "Native normalized", "Native eligible", "Native accepted", "Controlled raw", "Controlled selected", "Controlled accepted"]
    vals = [l4n["funnel"]["raw_qa_records"], l4n["funnel"]["normalized_post_oracles"], l4n["funnel"]["eligible_candidates"], l4n["funnel"]["accepted_pairs"], l4c["funnel"]["raw_candidates"], l4c["funnel"]["selected"], l4c["funnel"]["accepted"]]
    ax.bar(stages, vals, color=["#4C78A8"]*4+["#F58518"]*3)
    ax.set_yscale("log"); ax.set_ylabel("Records / candidates (log scale)"); ax.tick_params(axis="x", rotation=30)
    ax.set_title("L4 Native and Controlled construction funnels", loc="left", fontweight="bold")
    save_figure(fig, out, "figure_supp_C1_l4_origin_funnels", True)
    transition = collections.Counter(p["transition_family"] for p in pairs if p["level"] == "L4")
    fig, ax = plt.subplots(figsize=(8, 5)); ax.bar(transition.keys(), transition.values(), color="#E45756"); ax.set_ylabel("Minimal pairs"); ax.set_title("L4 transition-family distribution", loc="left", fontweight="bold"); ax.tick_params(axis="x", rotation=25)
    save_figure(fig, out, "figure_supp_C2_transition_distribution", True)
    csv_dump(out / "data_exports/figure_supp_C2_transition_distribution.csv", [{"Transition family": k, "Pairs": v} for k,v in sorted(transition.items())])
    groups = [("Native", "CORE"), ("Native", "CALIBRATION"), ("Controlled", "CORE"), ("Controlled", "CALIBRATION")]
    values = []
    l4pairs = [p for p in pairs if p["level"] == "L4"]
    for origin, dep in groups:
        oc = "SOURCE_NATIVE" if origin == "Native" else "BENCHMARK_CONTROLLED"
        values.append(sum(p["origin"] == oc and p["dependency_type"] == dep for p in l4pairs))
    fig, ax = plt.subplots(figsize=(7, 5)); ax.bar(["Native", "Controlled"], [values[0], values[2]], label="Core", color="#4C78A8"); ax.bar(["Native", "Controlled"], [values[1], values[3]], bottom=[values[0], values[2]], label="Calibration", color="#F58518"); ax.legend(); ax.set_ylabel("Minimal pairs"); ax.set_title("L4 core and calibration composition", loc="left", fontweight="bold")
    save_figure(fig, out, "figure_supp_C3_core_calibration", True)

    # D1 reason heatmap and D2 real English evidence-ablation schematic.
    levels = ["L1", "L2", "L3", "L4"]
    reasons = sorted({u["unknown_reason"] for u in unknown})
    fig, ax = plt.subplots(figsize=(12, 4.5)); heatmap(ax, levels, reasons, collections.Counter((u["level"], u["unknown_reason"]) for u in unknown), "Unknown reason × level", percent_by_row=False)
    save_figure(fig, out, "figure_supp_D1_unknown_reason_level", True)
    csv_dump(out / "data_exports/figure_supp_D1_unknown_reason_level.csv", count_rows(unknown, "level", "unknown_reason"))
    l4u = next(u for u in unknown if u["level"] == "L4" and u["unknown_origin"] == "EVIDENCE_ABLATION")
    fig, ax = plt.subplots(figsize=(13, 5.8)); ax.axis("off"); ax.set_xlim(0,1); ax.set_ylim(0,1)
    for x, title, body, color in [(0.03,"Available evidence", "Intervention and retained evidence", "#D9EAD3"), (0.37,"Withheld decisive evidence", l4u["unknown_detail"], "#FCE5CD"), (0.71,"Released label", "UNKNOWN\nBoth truth completions remain satisfiable", "#D9D2E9")]:
        ax.add_patch(FancyBboxPatch((x,.48),.25,.24,boxstyle="round,pad=.02",facecolor=color,edgecolor="#555")); ax.text(x+.125,.64,title,ha="center",fontweight="bold"); ax.text(x+.125,.54,textwrap.fill(body,32),ha="center",va="center",fontsize=9)
    ax.add_patch(FancyArrowPatch((.28,.60),(.37,.60),arrowstyle="-|>",mutation_scale=15)); ax.add_patch(FancyArrowPatch((.62,.60),(.71,.60),arrowstyle="-|>",mutation_scale=15))
    ax.text(.03,.89,"Evidence-ablation UNKNOWN construction",fontsize=16,fontweight="bold"); ax.text(.03,.32,"English claim",fontweight="bold"); ax.text(.03,.22,textwrap.fill(l4u["text"],150),fontsize=9); ax.text(.03,.08,f"Released sample: {l4u['sample_id']}  |  Reason: {l4u['unknown_reason']}",fontsize=8,color="#555")
    save_figure(fig, out, "figure_supp_D2_evidence_ablation_schematic", True)
    json_dump(out / "data_exports/figure_supp_D2_evidence_ablation_schematic.json", {k:l4u[k] for k in ("sample_id","text","unknown_reason","unknown_detail")})

    # E1–E2.
    accepted = collections.Counter(p["source_key"] for p in pairs if p["level"] != "L4")
    sources = [k for k in data["proof_counts"]]
    x = np.arange(len(sources)); proof = [data["proof_counts"][k] for k in sources]; final = [accepted[k] for k in sources]
    fig, ax = plt.subplots(figsize=(10,5)); ax.bar(x-.18, proof, .36, label="Proof-valid candidates", color="#9ECAE1"); ax.bar(x+.18, final, .36, label="Final accepted", color="#3182BD"); ax.set_xticks(x,[cfg["source_display_names"].get(k,k) for k in sources],rotation=25,ha="right"); ax.set_ylabel("Minimal pairs"); ax.legend(); ax.set_title("L1–L3 source construction yield",loc="left",fontweight="bold")
    save_figure(fig,out,"figure_supp_E1_source_funnels",True)
    rejects = collections.Counter()
    for k,v in data["quota"].get("cap_reject_counts",{}).items(): rejects[k]+=v
    for key in ("l4_native_rejects","l4_controlled_rejects"):
        for _,item in iter_jsonl(resolved(cfg["inputs"][key])): rejects[item.get("reason","MISSING")]+=1
    ordered=rejects.most_common(); cum=np.cumsum([v for _,v in ordered])/sum(rejects.values())*100
    fig, ax = plt.subplots(figsize=(12,5.5)); ax.bar(range(len(ordered)),[v for _,v in ordered],color="#E45756"); ax.set_xticks(range(len(ordered)),[k for k,_ in ordered],rotation=35,ha="right"); ax.set_ylabel("Rejected records"); ax2=ax.twinx(); ax2.plot(range(len(ordered)),cum,color="#222",marker="o"); ax2.set_ylabel("Cumulative percent"); ax2.set_ylim(0,105); ax.set_title("Structured rejection Pareto chart",loc="left",fontweight="bold")
    save_figure(fig,out,"figure_supp_E2_rejection_pareto",True)
    csv_dump(out/"data_exports/figure_supp_E2_rejection_pareto.csv",[{"Reject code":k,"Count":v,"Cumulative percent":round(cum[i],3)} for i,(k,v) in enumerate(ordered)])

    # F1–F4 language diagnostics.
    labels=["SUPPORTED","CONTRADICTORY","UNKNOWN"]
    fig,ax=plt.subplots(figsize=(9,5)); arrays=[[len(tokens(c["text"])) for c in claims if c["label"]==lab] for lab in labels]; ax.boxplot(arrays,tick_labels=labels,showfliers=False); ax.set_ylabel("English word tokens per claim"); ax.set_title("Claim-length distribution by released label",loc="left",fontweight="bold")
    save_figure(fig,out,"figure_supp_F1_claim_length",True)
    pred=collections.Counter(c["predicate"] for c in claims); top=pred.most_common(15); fig,ax=plt.subplots(figsize=(10,6)); ax.barh([k for k,_ in reversed(top)],[v for _,v in reversed(top)],color="#54A24B"); ax.set_xlabel("Claims"); ax.set_title("Most frequent released predicates",loc="left",fontweight="bold")
    save_figure(fig,out,"figure_supp_F2_predicate_frequency",True); csv_dump(out/"data_exports/figure_supp_F2_predicate_frequency.csv",[{"Predicate":k,"Claims":v} for k,v in top])
    slot_style=collections.Counter((c["changed_slot"],c["style"]) for c in claims if c["label"]!="UNKNOWN"); slots=sorted({k[0] for k in slot_style}); styles=[x for x,_ in collections.Counter(c["style"] for c in claims if c["label"]!="UNKNOWN").most_common(12)]; fig,ax=plt.subplots(figsize=(13,max(4,len(slots)*.45))); heatmap(ax,slots,styles,slot_style,"Changed slot × realization family (top 12)",percent_by_row=True); save_figure(fig,out,"figure_supp_F3_slot_realization",True)
    binary=[c for c in claims if c["label"] in {"SUPPORTED","CONTRADICTORY"}]; vocab=collections.Counter(); by={lab:collections.Counter() for lab in ("SUPPORTED","CONTRADICTORY")}
    for c in binary: by[c["label"]].update(tokens(c["text"])); vocab.update(set(tokens(c["text"])))
    scores=[]; alpha=.5; va=len(set(by["SUPPORTED"])|set(by["CONTRADICTORY"])); ts=sum(by["SUPPORTED"].values()); tc=sum(by["CONTRADICTORY"].values())
    for tok in set(by["SUPPORTED"])|set(by["CONTRADICTORY"]):
        if by["SUPPORTED"][tok]+by["CONTRADICTORY"][tok] < 20: continue
        score=math.log((by["SUPPORTED"][tok]+alpha)/(ts+alpha*va))-math.log((by["CONTRADICTORY"][tok]+alpha)/(tc+alpha*va)); scores.append((tok,score,by["SUPPORTED"][tok],by["CONTRADICTORY"][tok]))
    selected=sorted(scores,key=lambda x:x[1])[:12]+sorted(scores,key=lambda x:x[1])[-12:]; fig,ax=plt.subplots(figsize=(10,8)); colors=[cfg["colors"]["CONTRADICTORY"] if s<0 else cfg["colors"]["SUPPORTED"] for _,s,_,_ in selected]; ax.barh([t for t,_,_,_ in selected],[s for _,s,_,_ in selected],color=colors); ax.axvline(0,color="#333",linewidth=.8); ax.set_xlabel("Log odds: Supported − Contradictory"); ax.set_title("Token log-odds diagnostic (additive smoothing α=0.5)",loc="left",fontweight="bold")
    save_figure(fig,out,"figure_supp_F4_token_log_odds",True); csv_dump(out/"data_exports/figure_supp_F4_token_log_odds.csv",[{"Token":t,"Log odds":s,"Supported count":a,"Contradictory count":b} for t,s,a,b in selected])

    # F5–F6: informal word clouds plus their exact, auditable frequencies.
    wc_groups = wordcloud_frequencies(claims)
    wc_salience, wc_document_frequency, wc_idf = wordcloud_contrastive_salience(wc_groups)
    cloud_ranks = {
        group: {token: rank for rank, (token, _) in enumerate(scores.most_common(), 1)}
        for group, scores in wc_salience.items()
    }
    wc_rows: list[dict[str, Any]] = []
    for group, counter in wc_groups.items():
        denominator = sum(counter.values())
        for rank, (token, count) in enumerate(counter.most_common(), 1):
            wc_rows.append({
                "Group": group,
                "Frequency rank": rank,
                "Cloud salience rank": cloud_ranks[group][token],
                "Token": token,
                "Count": count,
                "Retained-token denominator": denominator,
                "Frequency (%)": round(safe_pct(count, denominator) or 0, 6),
                "Group document frequency": wc_document_frequency[token],
                "Smoothed IDF": round(wc_idf[token], 8),
                "Contrastive salience": round(wc_salience[group][token], 8),
                "Selected in word cloud": cloud_ranks[group][token] <= 32,
            })
    csv_dump(out / "data_exports/figure_supp_F5_wordcloud_token_frequencies.csv", wc_rows)
    json_dump(out / "data_exports/figure_supp_F5_wordcloud_policy.json", {
        "status": "SUPPLEMENTARY_INFORMAL_OVERVIEW",
        "groups": ["L1", "L2", "L3", "L4", "UNKNOWN"],
        "scope": "Binary claims for L1-L4; all Unknown claims for UNKNOWN",
        "tokenization": cfg["analysis_policy"]["tokenization"],
        "numbers_removed": True,
        "alphanumeric_and_hashlike_identifiers_removed": {"any_digit": True, "hash_regex": HASHLIKE_TOKEN_RE.pattern},
        "stopwords_and_template_tokens_removed": sorted(WORDCLOUD_STOPWORDS),
        "directional_and_temporal_relation_terms_removed": sorted(WORDCLOUD_DIRECTIONAL_TERMS),
        "selection_formula": "sqrt(count) * (0.25 + log((G + 1) / (group_document_frequency + 0.5)))^2",
        "selection_purpose": "Downweight vocabulary shared across all groups and emphasize group-distinctive content.",
        "font_size_metric": "contrastive salience",
        "max_words_drawn_per_panel": 32,
        "layout": "L1-L4 in a large 2x2 figure; Unknown in a separate figure",
        "interpretation": "The figure is an informal contrastive overview. Exact counts, denominators, document frequencies, IDF values, and salience scores are exported in CSV.",
    })
    palettes = {"L1": "Blues", "L2": "Greens", "L3": "Oranges", "L4": "Purples", "UNKNOWN": "cividis_r"}
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), constrained_layout=True)
    for index, group in enumerate(("L1", "L2", "L3", "L4")):
        draw_deterministic_wordcloud(
            axes.flat[index], wc_salience[group], group, int(cfg["seed"]) + index,
            max_words=32, cmap_name=palettes[group], token_denominator=sum(wc_groups[group].values()),
        )
    fig.suptitle("Contrastive English object and scene-content word clouds by level", fontsize=18, fontweight="bold")
    save_figure(fig, out, "figure_supp_F5_wordcloud_by_level", True)

    fig, ax = plt.subplots(figsize=(10, 6.8), constrained_layout=True)
    draw_deterministic_wordcloud(
        ax, wc_salience["UNKNOWN"], "UNKNOWN", int(cfg["seed"]) + 4,
        max_words=36, cmap_name=palettes["UNKNOWN"], token_denominator=sum(wc_groups["UNKNOWN"].values()),
    )
    fig.suptitle("Contrastive English object and scene-content word cloud: Unknown", fontsize=17, fontweight="bold")
    save_figure(fig, out, "figure_supp_F5b_unknown_wordcloud", True)

    fig, axes = plt.subplots(2, 3, figsize=(16, 10), constrained_layout=True)
    for index, group in enumerate(("L1", "L2", "L3", "L4", "UNKNOWN")):
        selected_tokens = [token for token, _ in wc_salience[group].most_common(15)]
        labels = list(reversed(selected_tokens))
        counts = [wc_groups[group][token] for token in labels]
        axes.flat[index].barh(labels, counts, color=plt.get_cmap(palettes[group])(np.linspace(.45, .90, len(labels))))
        axes.flat[index].set_title(f"{group} — selected by contrastive salience", loc="left", fontweight="bold")
        axes.flat[index].set_xlabel("Exact retained-token count")
        axes.flat[index].tick_params(axis="y", labelsize=8)
    axes.flat[5].axis("off")
    axes.flat[5].text(
        .04, .84, "Exact companion to Figure F5",
        fontsize=14, fontweight="bold", va="top", transform=axes.flat[5].transAxes,
    )
    axes.flat[5].text(
        .04, .70,
        textwrap.fill(
            "Tokens are selected by contrastive salience, while bar lengths show exact corpus counts. "
            "Full frequencies, denominators, document frequencies, IDF values, and salience scores are "
            "available in the CSV export.",
            47,
        ),
        fontsize=10.5, linespacing=1.25, va="top", transform=axes.flat[5].transAxes,
    )
    fig.suptitle("Exact counts for contrastively selected object and scene-content tokens", fontsize=17, fontweight="bold")
    save_figure(fig, out, "figure_supp_F6_token_frequency_by_level", True)

    # G1 concentration curve.
    counts=np.array(sorted(collections.Counter(p["world"] for p in pairs).values())); cumulative=np.insert(np.cumsum(counts)/counts.sum(),0,0); x=np.linspace(0,1,len(cumulative)); fig,ax=plt.subplots(figsize=(6,6)); ax.plot(x,cumulative,label="Observed",color="#4C78A8",linewidth=2.5); ax.plot([0,1],[0,1],linestyle="--",color="#777",label="Uniform"); ax.set(xlabel="Cumulative fraction of worlds",ylabel="Cumulative fraction of pairs",title="World-level pair concentration"); ax.legend(); save_figure(fig,out,"figure_supp_G1_world_concentration",True); csv_dump(out/"data_exports/figure_supp_G1_world_concentration.csv",[{"World fraction":float(a),"Pair fraction":float(b)} for a,b in zip(x,cumulative)])


def build_examples(out: Path, cfg: dict[str, Any], data: dict[str, Any]) -> None:
    pairs, unknown = data["pairs"], data["unknown"]
    selected: list[tuple[str, dict[str, Any]]] = []
    for level in ("L1","L2","L3"):
        for p in sorted((p for p in pairs if p["level"]==level), key=lambda x:x["pair_id"])[:2]: selected.append((level,p))
    l4_specs=[("L4 Native — Direct",lambda p:p["level"]=="L4" and p["origin"]=="SOURCE_NATIVE" and p["native_subtype"]=="DIRECT"),("L4 Native — Aggregated",lambda p:p["level"]=="L4" and p["origin"]=="SOURCE_NATIVE" and p["native_subtype"]=="AGGREGATED"),("L4 Controlled — Core",lambda p:p["level"]=="L4" and p["origin"]=="BENCHMARK_CONTROLLED" and p["dependency_type"]=="CORE"),("L4 Controlled — Calibration",lambda p:p["level"]=="L4" and p["origin"]=="BENCHMARK_CONTROLLED" and p["dependency_type"]=="CALIBRATION")]
    for label,test in l4_specs: selected.append((label,sorted((p for p in pairs if test(p)),key=lambda x:x["pair_id"])[0]))
    lines=["# SpaceConflict qualitative examples","","All claims below are copied verbatim from released English benchmark records. No question text was synthesized for this document.",""]
    index=[]
    for label,p in selected:
        raw=p["raw"]; sup=raw["supported_claim"].get("natural_text") if "natural_text" in raw["supported_claim"] else l4_claim_text(raw["supported_claim"]); con=raw["contradictory_claim"].get("natural_text") if "natural_text" in raw["contradictory_claim"] else l4_claim_text(raw["contradictory_claim"])
        lines.extend([f"## {label}: `{p['pair_id']}`","",f"- Source: {p['source']}",f"- Split: {p['split']}",f"- World: `{p['world']}`",f"- Operator: `{p['operator']}`",f"- Changed slot: `{p['changed_slot']}`",f"- Media type: `{p['media_type']}`"])
        if p["level"]=="L4": lines.append(f"- Intervention: {raw.get('intervention',{}).get('text') or raw.get('intervention',{}).get('source_text') or raw.get('model_input',{}).get('intervention_text','Not available')}")
        lines.extend(["",f"**Supported claim:** {sup}","",f"**Contradictory claim:** {con}",""])
        index.append({"Case":label,"Pair ID":p["pair_id"],"Source":p["source"],"Split":p["split"],"World":p["world"],"Supported":sup,"Contradictory":con})
    lines.extend(["## Unknown cases",""])
    reason_seen=set()
    for u in sorted(unknown,key=lambda x:(x["level"],x["unknown_reason"],x["sample_id"])):
        key=(u["level"],u["unknown_reason"])
        if key in reason_seen: continue
        reason_seen.add(key); lines.extend([f"### {u['level']} — {u['unknown_reason']}: `{u['sample_id']}`","",f"- Source: {u['source']}",f"- Split: {u['split']}",f"- World: `{u['world']}`",f"- Withheld or missing evidence: `{u['unknown_detail']}`","",f"**Unknown claim:** {u['text']}",""])
        index.append({"Case":f"{u['level']} Unknown — {u['unknown_reason']}","Pair ID":u["sample_id"],"Source":u["source"],"Split":u["split"],"World":u["world"],"Supported":"Not applicable","Contradictory":u["text"]})
    exdir=out/"examples"; exdir.mkdir(parents=True,exist_ok=True); (exdir/"qualitative_examples.md").write_text("\n".join(lines),encoding="utf-8"); csv_dump(exdir/"qualitative_example_index.csv",index); json_dump(exdir/"qualitative_example_index.json",index)


def make_readme(out: Path, cfg: dict[str, Any], data: dict[str, Any]) -> None:
    pairs, unknown=data["pairs"],data["unknown"]
    released_worlds = {p["world"] for p in pairs} | {u["world"] for u in unknown}
    track_policy = (
        "Missing released primary-track fields are filled only in the analysis layer from the versioned, "
        "rule-based L4 track overlay. The frozen release remains unchanged."
        if cfg["inputs"].get("l4_track_annotation_file") else
        "Missing released primary-track annotations are reported as `Not annotated in released pair`; "
        "they are not inferred from operator names."
    )
    text=f"""# SpaceConflict table and visualization results

This directory is a deterministic, read-only analysis view over two frozen inputs:

- `release/production_available_v10` for L1–L3;
- `l4/v3_3/release` for L4.

It contains {len(released_worlds):,} released worlds (the union of binary-pair and Unknown worlds), {len(pairs):,} minimal pairs, {2*len(pairs):,} binary claims, and {len(unknown):,} Unknown claims. The analysis does not modify or merge the frozen source artifacts; their manifests and hashes remain authoritative.

## Directory map

- `tables/main/`: four paper-facing tables in CSV, JSON, Markdown, and LaTeX.
- `tables/supplementary/`: detailed composition, L4, Unknown, language, rejection, leakage, and release-history tables.
- `figures/main/`: three paper-facing figures in PNG, PDF, and SVG.
- `figures/supplementary/`: auditable supplementary diagnostics in PNG, PDF, and SVG.
- `data_exports/`: the exact CSV/JSON values plotted in every figure.
- `examples/`: released English claim examples with IDs and provenance.
- `manifests/`: run metadata, input/output hashes, consistency audit, and captions.
- `configs/`: frozen configuration snapshot used by this run.

## Interpretation constraints

- Counts use `minimal_pair` for binary items and `claim` for Unknown; every binary pair contributes exactly two claims.
- Every percentage in the tables has an explicit denominator or a denominator definition.
- {track_policy}
- Raw source datasets use incompatible units, so the main funnel never sums raw QA, media, and controlled-candidate counts into a single number.
- Semantic near-duplicate rates and media duration are reported as unavailable when no declared detector/metadata exists.
- No external MLLM accuracy, Pair Accuracy, or leaderboard value is included. The 0.50 text-only diagnostic is a previously executed construction-time static shortcut audit, not an MLLM benchmark result.
- Large supplementary word clouds are provided in a 2×2 L1–L4 layout, with Unknown shown separately. Stopwords, template scaffolding, numbers, and directional or temporal-relation terms are removed. Selection and font size use an exported contrastive-salience score that downweights cross-level vocabulary; exact token counts and smoothed log-odds figures remain authoritative.
"""
    out.mkdir(parents=True,exist_ok=True); (out/"README.md").write_text(text,encoding="utf-8")
    level_counts = collections.Counter(p["level"] for p in pairs)
    source_counts = collections.Counter(p["source"] for p in pairs)
    non_predicate = sum("predicate" not in p["changed_slots"] for p in pairs)
    l4 = [p for p in pairs if p["level"] == "L4"]
    native = sum(p["origin"] == "SOURCE_NATIVE" for p in l4)
    controlled = sum(p["origin"] == "BENCHMARK_CONTROLLED" for p in l4)
    calibration = sum(p["dependency_type"] == "CALIBRATION" for p in l4)
    l4_unknown = [u for u in unknown if u["level"] == "L4"]
    evidence_ablation = sum(u["unknown_origin"] == "EVIDENCE_ABLATION" for u in l4_unknown)
    binary_claims = [c for c in data["claims"] if c["label"] != "UNKNOWN"]
    explicit_negation = sum(bool(NEGATION_RE.search(c["text"])) for c in binary_claims)
    if cfg["inputs"].get("l4_track_annotation_file"):
        l4_track_note = (
            "The frozen L4 release contains incomplete primary-track fields; this analysis fills them from a "
            "versioned rule-based overlay derived from the released question, intervention operation, claim "
            "predicate, and explicit reference-frame metadata, without modifying release JSONL files. Remaining "
            f"unassigned L4 pairs: {sum(p['primary_track'] == cfg['analysis_policy']['l4_missing_track_label'] for p in l4):,}."
        )
    else:
        missing_l4 = sum(p["primary_track"] == cfg["analysis_policy"]["l4_missing_track_label"] for p in l4)
        l4_track_note = (
            f"Released L4 primary-track annotations are incomplete: {missing_l4:,}/{len(l4):,} L4 pairs lack "
            "that field, so this analysis reports them as unannotated and does not infer tracks from operator names."
        )
    paper_text = f"""# Paper-ready dataset results text

## Benchmark scale and coverage

The composite analysis view contains {len(released_worlds):,} world-disjoint environments, {len({p['media_group'] for p in pairs}):,} binary-pair media groups, {len(pairs):,} minimal pairs ({2 * len(pairs):,} binary claims), and {len(unknown):,} Unknown claims. The pair distribution is L1 {level_counts['L1']:,} ({safe_pct(level_counts['L1'], len(pairs)):.2f}%), L2 {level_counts['L2']:,} ({safe_pct(level_counts['L2'], len(pairs)):.2f}%), L3 {level_counts['L3']:,} ({safe_pct(level_counts['L3'], len(pairs)):.2f}%), and L4 {level_counts['L4']:,} ({safe_pct(level_counts['L4'], len(pairs)):.2f}%). The largest source contribution is {source_counts.most_common(1)[0][0]} with {source_counts.most_common(1)[0][1]:,} pairs; source-level counts and denominators are reported in Tables 1, A1, and A3.

## Semantic edits and L4 composition

The contradictory member changes a non-predicate slot in {non_predicate:,}/{len(pairs):,} pairs ({safe_pct(non_predicate, len(pairs)):.2f}%), showing that the corpus is not dominated by simple predicate-antonym replacement. The L4 slice contains {native:,} source-native pairs ({safe_pct(native, len(l4)):.2f}%) and {controlled:,} benchmark-controlled pairs ({safe_pct(controlled, len(l4)):.2f}%); {calibration:,}/{len(l4):,} L4 pairs ({safe_pct(calibration, len(l4)):.2f}%) belong to a declared calibration dependency. Its {len(l4_unknown):,} Unknown claims include {evidence_ablation:,}/{len(l4_unknown):,} evidence-ablation cases ({safe_pct(evidence_ablation, len(l4_unknown)):.2f}%). {l4_track_note}

## Automatic quality and leakage controls

The composite world-overlap audit finds 0/{len(released_worlds):,} global-world identifiers shared across train, development, and test. The L1–L3 release and replay-chain audits both pass with zero recorded failures over 9,812 pairs, while the L4 v3.3 audit reports zero schema failures over 1,136 pairs plus 300 Unknown records and zero missing or hash-failing files among 2,205 unique media files. Explicit negation occurs in {explicit_negation:,}/{len(binary_claims):,} binary claims ({safe_pct(explicit_negation, len(binary_claims)):.3f}%). The executed L1–L3 static text-only shortcut diagnostic remains at its 0.50 majority baseline; this is a construction-time leakage control, not an MLLM benchmark result. Exact and normalized duplicate diagnostics, including 16 repeated Unknown surfaces in the composite view, are reported rather than silently removed.

## Scope statement

These results describe benchmark construction and data quality only. No external MLLM accuracy, Pair Accuracy, leaderboard score, or model ablation is fabricated. Native and controlled raw funnels retain separate denominators because their upstream units are not comparable.
"""
    (out/"PAPER_RESULTS_TEXT_EN.md").write_text(paper_text, encoding="utf-8")


def captions(out: Path, cfg: dict[str, Any]) -> None:
    track_caption = (
        "Missing released L4 primary-track fields are supplied by the versioned derived track overlay."
        if cfg["inputs"].get("l4_track_annotation_file") else
        "Missing L4 primary-track fields are explicitly retained as unannotated."
    )
    text=f"""# Figure and table captions

## Main figures

1. **Construction pipeline.** Source evidence is normalized into replayable graphs before claim truth and typed edits are fixed; language realization precedes independent replay, world-disjoint splitting, and release. The displayed English minimal pair is copied from a released record.
2. **Coverage.** Counts and within-row percentages show source-by-level, level-by-released-primary-track, modality-by-level, and changed-slot coverage. {track_caption}
3. **Construction and validation funnels.** The L1–L3 panel begins at the proof-valid parent pool. Native and controlled L4 pipelines are shown separately on a log scale because their upstream units differ.

## Main tables

1. **Source roles.** Source authority, released and planned coverage, observed scale, world-unit convention, and release mode.
2. **Overall statistics.** World-disjoint split statistics with worlds, media groups, L4 branches, minimal pairs, binary claims, and Unknown claims.
3. **L4 composition.** Native Direct, Native Aggregated, Controlled Core, Controlled Calibration, and Unknown components.
4. **Quality audits.** Executed release, replay, schema, media, leakage, duplication, negation, and static shortcut checks with denominators.

## Supplementary language figures

- **Figure F5: contrastive word clouds by level.** Large 2×2 English object and scene-content overview for L1–L4 binary claims. Stopwords, template scaffolding, numbers, and directional or temporal-relation terms are removed. Cross-level vocabulary is downweighted with the declared contrastive-salience score.
- **Figure F5b: Unknown word cloud.** The same contrastive policy applied to all Unknown claims in a separate, larger panel.
- **Figure F6: exact token frequencies.** Quantitative companion showing exact corpus counts for the tokens selected by contrastive salience; full counts, denominators, document frequencies, IDF values, and scores are exported as CSV.
"""
    (out/"manifests").mkdir(parents=True,exist_ok=True); (out/"manifests/captions.md").write_text(text,encoding="utf-8")


def git_commit() -> str:
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNVERSIONED"


def write_manifest(out: Path, cfg_path: Path, cfg: dict[str, Any], args: argparse.Namespace, started: str) -> None:
    input_paths=[]
    for value in cfg["inputs"].values():
        path=resolved(value)
        if path.is_file(): input_paths.append(path)
        elif path.is_dir():
            for name in ("manifest.json","pairs.jsonl","unknown_challenge.jsonl"): 
                if (path/name).is_file(): input_paths.append(path/name)
    input_paths=sorted(set(input_paths))
    output_paths=sorted(p for p in out.rglob("*") if p.is_file() and "artifact_manifest" not in p.name)
    manifest={
        "schema_version":"spaceconflict_visualization_manifest_v1", "status":"PASS", "run_id":args.run_id,
        "release_version":cfg["release_version"], "seed":args.seed, "started_at":started,
        "completed_at":dt.datetime.now(dt.timezone.utc).isoformat(), "code_commit":git_commit(),
        "host":platform.node(), "python":platform.python_version(), "matplotlib":matplotlib.__version__, "pandas":pd.__version__, "numpy":np.__version__,
        "command":" ".join(sys.argv), "config":str(cfg_path.relative_to(ROOT)), "config_hash":sha256_file(cfg_path),
        "input_hashes":{str(p.relative_to(ROOT)):sha256_file(p) for p in input_paths},
        "output_hashes":{str(p.relative_to(out)):sha256_file(p) for p in output_paths},
        "success_counts":{
            "main_tables":len(list((out/"tables/main").glob("*.csv"))), "supplementary_tables":len(list((out/"tables/supplementary").glob("*.csv"))),
            "main_figure_files":len(list((out/"figures/main").glob("*.*"))), "supplementary_figure_files":len(list((out/"figures/supplementary").glob("*.*"))),
        }, "failure_counts":{}, "limitations":["No external MLLM results are available.","Semantic near-duplicate audit was not run because no threshold/model is declared."] + ([] if cfg["inputs"].get("l4_track_annotation_file") else ["Missing primary-track annotations are reported, not inferred."])
    }
    json_dump(out/"manifests/artifact_manifest.json",manifest)
    csv_dump(out/"manifests/artifact_manifest.csv",[{"Path":k,"SHA-256":v} for k,v in manifest["output_hashes"].items()])
    # Cross-format and required-artifact audit.
    required=[out/"tables/main"/f"table_main_{i}_{name}.csv" for i,name in [(1,"source_roles"),(2,"overall_split_statistics"),(3,"l4_three_part_composition"),(4,"quality_audits")]]
    required += [out/"figures/main"/f"figure_main_{i}_{name}.{ext}" for i,name in [(1,"pipeline_overview"),(2,"coverage_panels"),(3,"construction_validation_funnels")] for ext in ("png","pdf","svg")]
    missing=[str(p.relative_to(out)) for p in required if not p.exists()]
    audit={"status":"PASS" if not missing else "FAIL","required_artifact_count":len(required),"missing_required_artifacts":missing,"main_table_csv_count":manifest["success_counts"]["main_tables"],"supplementary_table_csv_count":manifest["success_counts"]["supplementary_tables"],"all_figure_stems_have_png_pdf_svg":all({p.suffix for p in p.parent.glob(p.stem+".*")} >= {".png",".pdf",".svg"} for p in (out/"figures/main").glob("*.png"))}
    json_dump(out/"manifests/consistency_audit.json",audit)
    if missing: raise RuntimeError(f"Missing required outputs: {missing}")


def run(default_action: str = "all") -> None:
    args=parse_args(default_action)
    cfg_path=resolved(args.config)
    with cfg_path.open(encoding="utf-8") as handle: cfg=yaml.safe_load(handle)
    if cfg.get("schema_version")!="spaceconflict_visualization_results_v1": raise ValueError("Unsupported visualization config schema")
    if args.release_version: cfg["release_version"]=args.release_version
    if args.l4_track_annotation_file: cfg["inputs"]["l4_track_annotation_file"] = args.l4_track_annotation_file
    args.seed=cfg["seed"] if args.seed is None else args.seed
    args.run_id=args.run_id or f"vis_{cfg['release_version']}_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"
    random.seed(args.seed); np.random.seed(args.seed)
    out=resolved(args.output_dir or cfg["output_dir"])
    missing=[]
    for name,value in cfg["inputs"].items():
        if not resolved(value).exists(): missing.append({"input":name,"path":str(resolved(value))})
    if missing: raise FileNotFoundError(json.dumps(missing,indent=2))
    plan={"status":"DRY_RUN_OK" if args.dry_run else "RUNNING","action":args.action,"release_version":cfg["release_version"],"output":str(out),"seed":args.seed,"run_id":args.run_id,"input_count":len(cfg["inputs"]),"limit":args.limit}
    print(json.dumps(plan,indent=2))
    if args.dry_run: return
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    out.mkdir(parents=True,exist_ok=True)
    (out/"configs").mkdir(exist_ok=True); (out/"configs"/cfg_path.name).write_text(cfg_path.read_text(encoding="utf-8"),encoding="utf-8")
    data=prepare_data(cfg,args.limit)
    actions={args.action} if args.action!="all" else {"tables","main-figures","supp-figures","audits","examples","manifest"}
    # Audits depend on the exported tables, and manifest describes the complete bundle.
    if "tables" in actions or "audits" in actions: build_tables(out,cfg,data)
    if "main-figures" in actions: build_main_figures(out,cfg,data)
    if "supp-figures" in actions: build_supp_figures(out,cfg,data)
    if "examples" in actions: build_examples(out,cfg,data)
    make_readme(out,cfg,data); captions(out,cfg)
    if "manifest" in actions: write_manifest(out,cfg_path,cfg,args,started)
    print(json.dumps({"status":"PASS","output":str(out),"pairs":len(data["pairs"]),"claims":len(data["claims"]),"unknown":len(data["unknown"])},indent=2))


if __name__ == "__main__":
    run()
