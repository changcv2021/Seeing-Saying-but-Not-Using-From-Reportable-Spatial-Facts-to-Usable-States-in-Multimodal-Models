from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..registry import ROOT
from .controlled import build_controlled
from .native import build_native, freeze_existing_native
from .release import build_release
from .unknown import build_unknown


DEFAULT_MEDIA_ROOT = Path(
    "external/upstream/data/full_media_incoming/"
    "hypo3d/ffb21ab198e8d666b63e062d931ed33b60c67d0f"
)


def run_action(action: str, args: Any) -> dict[str, Any]:
    root = ROOT
    output_root = args.output_root or root / "l4/v3_0"
    media_root = args.media_root or DEFAULT_MEDIA_ROOT
    if action == "freeze-native":
        return freeze_existing_native(
            pairs_path=root / "accepted/hypo3d_l4_v2_official_referit3d_fusion_v2_8/pairs.count_l4_core_v2.jsonl",
            branches_path=root / "data/canonical/hypo3d_l4_v2/branches.jsonl",
            oracles_path=root / "transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl",
            resolutions_path=root / "transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_6/target_resolutions.v2_6.jsonl",
            split_path=root / "splits/world_split_hypo3d_v1.seed_20260826.jsonl",
            media_root=media_root, output_dir=output_root / "native/base",
            seed=args.seed, run_id=args.run_id, dry_run=args.dry_run, resume=args.resume,
        )
    if action == "build-native":
        return build_native(
            frozen_pairs_path=output_root / "native/base/accepted/pairs.l4_native_base_v3.jsonl",
            branches_path=root / "data/canonical/hypo3d_l4_v2/branches.jsonl",
            oracles_path=root / "transition_micrographs/hypo3d_l4_v2/post_state_oracles.v2_3.jsonl",
            parsed_path=root / "transition_micrographs/hypo3d_l4_v2/parsed_changes.v2_1.jsonl",
            resolutions_path=root / "transition_micrographs/hypo3d_l4_v2_official_referit3d_fusion_v2_6/target_resolutions.v2_6.jsonl",
            catalog_path=root / "data/canonical/hypo3d_l4_v2_official_referit3d_fusion_v2_6/object_catalog.v2.json",
            split_path=root / "splits/world_split_hypo3d_v1.seed_20260826.jsonl",
            media_root=media_root, config_path=root / "configs/l4_native_v3.yaml",
            output_dir=output_root / "native", seed=args.seed, run_id=args.run_id,
            limit=args.limit, dry_run=args.dry_run, resume=args.resume,
        )
    if action in {"build-controlled-pilot", "build-controlled-full"}:
        config_path = root / "configs/l4_controlled_v3.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        pilot = action == "build-controlled-pilot"
        section = config["pilot" if pilot else "full"]
        target_pairs = args.target_pairs or int(section["target_pairs"])
        scene_limit = args.scene_limit if args.scene_limit is not None else (int(section["scene_limit"]) if pilot else None)
        if args.limit is not None:
            target_pairs = min(target_pairs, args.limit)
        return build_controlled(
            catalog_path=root / config["source_catalog"], split_path=root / config["world_split"],
            media_root=media_root, config_path=config_path,
            output_dir=output_root / f"controlled/{'pilot' if pilot else 'full'}",
            target_pairs=target_pairs, scene_limit=scene_limit, seed=args.seed,
            run_id=args.run_id, dry_run=args.dry_run, resume=args.resume,
            reserved_pairs_path=output_root / "native/accepted/pairs.l4_native_v3.jsonl",
        )
    if action == "build-unknown":
        return build_unknown(
            controlled_pairs_path=output_root / "controlled/full/accepted/pairs.l4_controlled_v3.jsonl",
            config_path=root / "configs/l4_unknown_v3.yaml", output_dir=output_root / "unknown",
            seed=args.seed, run_id=args.run_id, limit=args.limit,
            dry_run=args.dry_run, resume=args.resume,
        )
    if action == "build-release":
        return build_release(
            native_pairs_path=output_root / "native/accepted/pairs.l4_native_v3.jsonl",
            native_inputs_path=output_root / "native/accepted/model_inputs.l4_native_v3.jsonl",
            native_gold_path=output_root / "native/accepted/gold.l4_native_v3.jsonl",
            controlled_pairs_path=output_root / "controlled/full/accepted/pairs.l4_controlled_v3.jsonl",
            controlled_inputs_path=output_root / "controlled/full/accepted/model_inputs.l4_controlled_v3.jsonl",
            controlled_gold_path=output_root / "controlled/full/accepted/gold.l4_controlled_v3.jsonl",
            unknown_path=output_root / "unknown/accepted/claims.l4_unknown_v3.jsonl",
            unknown_inputs_path=output_root / "unknown/accepted/model_inputs.l4_unknown_v3.jsonl",
            unknown_gold_path=output_root / "unknown/accepted/gold.l4_unknown_v3.jsonl",
            config_path=root / "configs/l4_release_v3.yaml", output_dir=output_root / "release",
            seed=args.seed, run_id=args.run_id, dry_run=args.dry_run, resume=args.resume,
        )
    raise ValueError(f"Unknown L4 three-part action: {action}")
