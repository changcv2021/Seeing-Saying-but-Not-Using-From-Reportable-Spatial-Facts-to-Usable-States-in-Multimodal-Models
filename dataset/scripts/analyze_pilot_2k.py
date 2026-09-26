#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, median
from typing import Any

from scipy.stats import binomtest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_command_json(path: Path) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(path.read_text(encoding="utf-8"))
    return value


def entropy(counts: Counter[str]) -> dict[str, float]:
    total = sum(counts.values())
    if total == 0:
        return {"bits": 0.0, "normalized": 0.0}
    probabilities = [count / total for count in counts.values()]
    bits = -sum(value * math.log2(value) for value in probabilities)
    maximum = math.log2(len(counts)) if len(counts) > 1 else 0.0
    return {"bits": bits, "normalized": bits / maximum if maximum else 0.0}


def word_ngrams(text: str, n: int = 2) -> set[tuple[str, ...]]:
    words = re.findall(r"[\w]+", text.casefold())
    return {tuple(words[index:index + n]) for index in range(max(0, len(words) - n + 1))}


def classifier_report(examples: list[dict[str, Any]], target: str, seed: int) -> dict[str, Any]:
    train = [row for row in examples if row["split"] == "train"]
    test = [row for row in examples if row["split"] == "test"]
    train_classes = {row[target] for row in train}
    known_test = [row for row in test if row[target] in train_classes]
    unseen_test = len(test) - len(known_test)
    if len(train_classes) < 2 or not known_test:
        return {"status": "NOT_ESTIMABLE", "train_classes": sorted(train_classes), "test_count": len(test), "unseen_test_class_count": unseen_test}
    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=30000, sublinear_tf=True),
        LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced"),
    )
    train_text = [row["text"] for row in train]
    train_target = [row[target] for row in train]
    test_text = [row["text"] for row in known_test]
    test_target = [row[target] for row in known_test]
    model.fit(train_text, train_target)
    prediction = model.predict(test_text)
    accuracy = float(accuracy_score(test_target, prediction))
    majority = max(Counter(test_target).values()) / len(test_target)
    result: dict[str, Any] = {
        "status": "ESTIMATED", "train_count": len(train), "test_count": len(test),
        "evaluated_test_count": len(known_test), "unseen_test_class_count": unseen_test,
        "class_count": len(train_classes), "accuracy": accuracy,
        "balanced_accuracy": float(balanced_accuracy_score(test_target, prediction)),
        "macro_f1": float(f1_score(test_target, prediction, average="macro")),
        "majority_baseline": majority,
        "accuracy_minus_majority": accuracy - majority,
        "binomial_greater_than_majority_p": float(
            binomtest(int((prediction == test_target).sum()), len(test_target), majority, alternative="greater").pvalue
        ),
    }
    if target == "label" and len(train_classes) == 2:
        classes = list(model[-1].classes_)
        positive = "SUPPORTED"
        if positive in classes and len(set(test_target)) == 2:
            probabilities = model.predict_proba(test_text)[:, classes.index(positive)]
            result["roc_auc"] = float(roc_auc_score([value == positive for value in test_target], probabilities))
        result["leakage_assessment"] = (
            "REBALANCE_REQUIRED" if accuracy >= 0.55 and result["binomial_greater_than_majority_p"] < 0.01
            else "NO_MATERIAL_LABEL_LEAKAGE_DETECTED"
        )
        result["assessment_rule"] = "accuracy >= 0.55 and one-sided binomial p < 0.01"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--structural-run-dir", type=Path)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--wall-seconds", type=float, default=177.0)
    parser.add_argument("--allocated-cpus", type=int, default=2)
    parser.add_argument("--proof-version", default="proof_verification_p1_v1")
    parser.add_argument("--quota-version", default="quota_pilot_2k_v1")
    parser.add_argument("--release", default="pilot_verified_2k_v1")
    args = parser.parse_args()
    root = args.root.resolve()
    run_dir = args.run_dir.resolve()
    structural_run_dir = args.structural_run_dir.resolve() if args.structural_run_dir else run_dir
    reports = {
        "claim_generation": load_command_json(structural_run_dir / "claim_generation.json"),
        **{
            name: load_command_json(run_dir / f"{name}.json")
            for name in (
                "language_realization", "text_verification", "proof_verification",
                "unknown_generation", "quota", "export",
            )
        },
    }
    sampled = load_jsonl(root / f"sampled/pairs.{args.quota_version}.seed_{args.seed}.jsonl")
    release_claims = load_jsonl(root / f"release/{args.release}/claims.jsonl")
    sampled_by_id = {row["pair_id"]: row for row in sampled}
    examples = []
    for claim in release_claims:
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
    for row in release_claims:
        pair_claims[row["pair_id"]].append(row["claim"])
    bigram_overlaps = []
    for values in pair_claims.values():
        if len(values) != 2:
            continue
        left, right = word_ngrams(values[0]), word_ngrams(values[1])
        bigram_overlaps.append(len(left & right) / len(left | right) if left | right else 1.0)
    lengths = [len(re.findall(r"\w+", row["claim"])) for row in release_claims]
    style_counts = Counter(row["selected_style_family"] for row in sampled)
    dataset_style: dict[str, Counter[str]] = defaultdict(Counter)
    operator_style: dict[str, Counter[str]] = defaultdict(Counter)
    world_counts = Counter(row["global_world_id"] for row in sampled)
    test_world_counts = Counter(row["global_world_id"] for row in sampled if row["split"] == "test")
    for row in sampled:
        dataset_style[row["source_dataset"]][row["selected_style_family"]] += 1
        operator_style[row["operator_id"]][row["selected_style_family"]] += 1
    structural = reports["claim_generation"]
    text = reports["text_verification"]
    proof = reports["proof_verification"]
    unknown = reports["unknown_generation"]
    quota = reports["quota"]
    structural_counts = structural["dataset_counts"]
    verified_rows = load_jsonl(root / f"candidates/auto_accepted/pairs.{args.proof_version}.jsonl")
    verified_counts = Counter(row["source_dataset"] for row in verified_rows)
    cell_rates = {
        dataset: {
            "structural_count": count, "verified_count": verified_counts[dataset],
            "verification_acceptance_rate": verified_counts[dataset] / count if count else 0.0,
        }
        for dataset, count in sorted(structural_counts.items())
    }
    if quota["selected_pair_count"] != 2000 or proof["status"] != "VERIFIER_VALID":
        pilot_status = "PILOT_INCOMPLETE"
    elif classifiers["label"].get("leakage_assessment") == "REBALANCE_REQUIRED":
        pilot_status = "PILOT_2K_LANGUAGE_REBALANCE_REQUIRED"
    else:
        pilot_status = "PILOT_2K_COMPLETE_WITH_COVERAGE_SHORTFALLS"
    report = {
        "schema_version": "1.0", "stage": "P1", "status": pilot_status,
        "seed": args.seed,
        "candidate_count": structural["potential_candidate_count"],
        "structural_accepted_count": structural["structural_accepted_count"],
        "structural_pass_rate": structural["structural_accepted_count"] / structural["potential_candidate_count"],
        "text_verified_count": text["accepted_pair_count"],
        "verifier_pass_rate": proof["auto_accepted_count"] / proof["input_pair_count"],
        "final_acceptance_rate": proof["auto_accepted_count"] / structural["structural_accepted_count"],
        "selected_pair_count": quota["selected_pair_count"],
        "unknown_count": unknown["auto_accepted_unknown_count"],
        "unknown_target": unknown["target_claim_count"],
        "unknown_rate_per_verified_pair": unknown["auto_accepted_unknown_count"] / proof["auto_accepted_count"],
        "roundtrip_failure_rate": text["reject_code_counts"].get("GRAPH_TEXT_DRIFT", 0) / text["input_pair_count"],
        "exact_sample_duplicate_rate": text["exact_sample_duplicate_rate"],
        "surface_text_reuse_rate": text["surface_text_reuse_rate"],
        "pair_style_reject_rate": text["reject_code_counts"].get("PAIR_STYLE_LEAKAGE", 0) / text["input_pair_count"],
        "text_only_classifiers": classifiers,
        "corpus_checks": {
            "exact_surface_duplicate_rate": 1 - len({row["claim"] for row in release_claims}) / len(release_claims),
            "normalized_surface_duplicate_rate": 1 - len({" ".join(row["claim"].casefold().split()) for row in release_claims}) / len(release_claims),
            "mean_within_pair_bigram_jaccard": fmean(bigram_overlaps),
            "syntax_family_entropy": entropy(style_counts),
            "length_words": {"min": min(lengths), "median": median(lengths), "mean": fmean(lengths), "max": max(lengths)},
            "explicit_negation_claim_count": sum(bool(re.search(r"\b(?:not|no|never|without)\b", row["claim"], re.I)) for row in release_claims),
            "style_distribution": dict(sorted(style_counts.items())),
            "lexicalization_distribution": reports["language_realization"]["selected_relation_lexicalization_counts"],
            "dataset_style_distribution": {key: dict(sorted(value.items())) for key, value in sorted(dataset_style.items())},
            "operator_style_distribution": {key: dict(sorted(value.items())) for key, value in sorted(operator_style.items())},
        },
        "cell_acceptance_rates": cell_rates,
        "pairs_per_world": {
            "world_count": len(world_counts), "mean": fmean(world_counts.values()), "max": max(world_counts.values()),
            "test_world_count": len(test_world_counts), "test_mean": fmean(test_world_counts.values()),
            "test_max": max(test_world_counts.values()),
        },
        "cost_proxy": {
            "slurm_job_id": 8074928, "wall_seconds": args.wall_seconds,
            "allocated_cpus": args.allocated_cpus, "requested_memory_gb": 32,
            "wall_seconds_per_verified_pair": args.wall_seconds / proof["auto_accepted_count"],
            "allocated_cpu_seconds_per_verified_pair": args.wall_seconds * args.allocated_cpus / proof["auto_accepted_count"],
            "note": "resource-allocation proxy; download and prior canonicalization costs excluded",
        },
        "coverage": {
            "dataset_counts": quota["dataset_counts"], "level_counts": quota["level_counts"],
            "primary_track_counts": quota["primary_track_counts"], "operator_counts": quota["operator_counts"],
            "modality_counts": quota["modality_counts"], "split_counts": quota["split_counts"],
            "shortfalls": quota["missing_requirements"],
        },
    }
    output = root / f"reports/pilot_2k.{args.release}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"].startswith("PILOT_2K_COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
