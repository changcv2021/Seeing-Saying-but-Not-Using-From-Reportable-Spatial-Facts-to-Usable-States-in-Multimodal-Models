#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, median
from typing import Any

from analyze_pilot_2k import classifier_report, entropy, load_jsonl, word_ngrams


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--quota-version", required=True)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language-report", action="append")
    args = parser.parse_args()
    root = args.root.resolve()
    sampled_path = root / f"sampled/pairs.{args.quota_version}.seed_{args.seed}.jsonl"
    release_dir = root / "release" / args.release
    quota_path = root / f"reports/quota.{args.quota_version}.seed_{args.seed}.json"
    sampled = load_jsonl(sampled_path)
    claims = load_jsonl(release_dir / "claims.jsonl")
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    quota = json.loads(quota_path.read_text(encoding="utf-8"))
    language_report_paths = (
        [(root / value).resolve() for value in args.language_report]
        if args.language_report else
        [root / "reports/language_realization.realization_p1_v2.json"]
    )
    lexicalizations: Counter[str] = Counter()
    for path in language_report_paths:
        path.relative_to(root)
        report = json.loads(path.read_text(encoding="utf-8"))
        lexicalizations.update(report["selected_relation_lexicalization_counts"])
    sampled_by_id = {row["pair_id"]: row for row in sampled}
    examples: list[dict[str, Any]] = []
    for claim in claims:
        row = sampled_by_id[claim["pair_id"]]
        examples.append({
            "text": claim["claim"], "label": claim["label"], "split": row["split"],
            "dataset": row["source_dataset"], "level": row["level"],
            "operator": row["operator_id"], "prompt_family": row["selected_style_family"],
        })
    classifiers = {
        target: classifier_report(examples, target, args.seed)
        for target in ("label", "dataset", "level", "operator", "prompt_family")
    }
    pair_claims: dict[str, list[str]] = defaultdict(list)
    for claim in claims:
        pair_claims[claim["pair_id"]].append(claim["claim"])
    overlaps = []
    for values in pair_claims.values():
        left, right = word_ngrams(values[0]), word_ngrams(values[1])
        overlaps.append(len(left & right) / len(left | right) if left | right else 1.0)
    lengths = [len(re.findall(r"\w+", row["claim"])) for row in claims]
    styles = Counter(row["selected_style_family"] for row in sampled)
    dataset_style: dict[str, Counter[str]] = defaultdict(Counter)
    operator_style: dict[str, Counter[str]] = defaultdict(Counter)
    dataset_level: Counter[str] = Counter()
    dataset_track: Counter[str] = Counter()
    level_track: Counter[str] = Counter()
    changed_slots: Counter[str] = Counter()
    predicate_changed_count = 0
    world_counts = Counter(row["global_world_id"] for row in sampled)
    test_world_counts = Counter(row["global_world_id"] for row in sampled if row["split"] == "test")
    for row in sampled:
        dataset_style[row["source_dataset"]][row["selected_style_family"]] += 1
        operator_style[row["operator_id"]][row["selected_style_family"]] += 1
        dataset_level[f"{row['source_dataset']}|{row['level']}"] += 1
        dataset_track[f"{row['source_dataset']}|{row['primary_track']}"] += 1
        level_track[f"{row['level']}|{row['primary_track']}"] += 1
        supported = row["supported_claim"]["normalized"]
        contradictory = row["contradictory_claim"]["normalized"]
        left_atom, right_atom = supported["atoms"][0], contradictory["atoms"][0]
        slots = [
            key for key in ("subject", "predicate", "object", "value", "polarity")
            if left_atom.get(key) != right_atom.get(key)
        ]
        slots.extend(
            f"context.{key}" for key in sorted(set(supported["context"]) | set(contradictory["context"]))
            if supported["context"].get(key) != contradictory["context"].get(key)
        )
        changed_slots["+".join(slots) if slots else "NONE"] += 1
        predicate_changed_count += int(left_atom.get("predicate") != right_atom.get("predicate"))
    explicit_negation = sum(
        bool(re.search(r"\b(?:not|no|never|without)\b", row["claim"], re.I)) for row in claims
    )
    report = {
        "schema_version": "1.0", "stage": "P2", "release": args.release,
        "status": (
            "RELEASE_CANDIDATE" if manifest["release_candidate_eligible"]
            else "VERIFIED_AVAILABLE_RELEASE_WITH_COVERAGE_SHORTFALLS"
        ),
        "seed": args.seed, "selected_pair_count": len(sampled),
        "claim_count": len(claims), "unknown_count": manifest["unknown_claim_count"],
        "text_only_classifiers": classifiers,
        "corpus_checks": {
            "exact_surface_duplicate_rate": 1 - len({row["claim"] for row in claims}) / len(claims),
            "normalized_surface_duplicate_rate": 1 - len({" ".join(row["claim"].casefold().split()) for row in claims}) / len(claims),
            "mean_within_pair_bigram_jaccard": fmean(overlaps),
            "syntax_family_entropy": entropy(styles),
            "length_words": {"min": min(lengths), "median": median(lengths), "mean": fmean(lengths), "max": max(lengths)},
            "explicit_negation_claim_count": explicit_negation,
            "style_distribution": dict(sorted(styles.items())),
            "lexicalization_distribution": dict(sorted(lexicalizations.items())),
            "dataset_style_distribution": {key: dict(sorted(value.items())) for key, value in sorted(dataset_style.items())},
            "operator_style_distribution": {key: dict(sorted(value.items())) for key, value in sorted(operator_style.items())},
        },
        "pairs_per_world": {
            "world_count": len(world_counts), "mean": fmean(world_counts.values()), "max": max(world_counts.values()),
            "test_world_count": len(test_world_counts),
            "test_mean": fmean(test_world_counts.values()) if test_world_counts else 0.0,
            "test_max": max(test_world_counts.values(), default=0),
        },
        "coverage": {
            "dataset_counts": quota["dataset_counts"], "level_counts": quota["level_counts"],
            "primary_track_counts": quota["primary_track_counts"], "operator_counts": quota["operator_counts"],
            "modality_counts": quota["modality_counts"], "split_counts": quota["split_counts"],
            "shortfalls": quota["missing_requirements"],
            "dataset_by_level": dict(sorted(dataset_level.items())),
            "dataset_by_primary_track": dict(sorted(dataset_track.items())),
            "level_by_primary_track": dict(sorted(level_track.items())),
        },
        "generation_accounting": {
            "changed_slot_distribution": dict(sorted(changed_slots.items())),
            "predicate_changed_count": predicate_changed_count,
            "predicate_changed_ratio": predicate_changed_count / len(sampled),
            "predicate_preserved_ratio": 1 - predicate_changed_count / len(sampled),
            "input_auto_accepted_count": quota["input_auto_accepted_count"],
            "selected_pair_count": quota["selected_pair_count"],
            "quota_cap_reject_counts": quota["cap_reject_counts"],
        },
        "release_candidate_eligible": manifest["release_candidate_eligible"],
        "quality_policy": quota["quality_policy"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
