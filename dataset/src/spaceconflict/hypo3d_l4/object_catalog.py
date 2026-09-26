from __future__ import annotations

from pathlib import Path
import math
from typing import Any

from ..hashing import sha256_file
from .restricted_pickle import load_restricted_annotation_pickle


OFFICIAL_SOURCE_TYPE = "EMBODIEDSCAN_OFFICIAL_ANNOTATION"
OFFICIAL_FUSION_SOURCE_TYPE = "OFFICIAL_STRUCTURED_ANNOTATION_FUSION"
UNVERIFIED_MIRROR_SOURCE_TYPE = "UNVERIFIED_THIRD_PARTY_MIRROR"
OFFICIAL_SOURCE_TYPES = {OFFICIAL_SOURCE_TYPE, OFFICIAL_FUSION_SOURCE_TYPE}
ALLOWED_SOURCE_TYPES = {*OFFICIAL_SOURCE_TYPES, UNVERIFIED_MIRROR_SOURCE_TYPE}


def _scene_id(item: dict[str, Any]) -> tuple[str, str] | None:
    raw = item.get("sample_idx") or item.get("scene_id")
    if not raw:
        lidar = item.get("lidar_points")
        if isinstance(lidar, dict):
            raw = lidar.get("lidar_path")
    if not raw:
        return None
    source = str(raw).replace("\\", "/").strip("/")
    parts = source.split("/")
    for index, part in enumerate(parts):
        if part in {"scannet", "3rscan"} and index + 1 < len(parts):
            candidate = parts[index + 1]
            if "." in candidate:
                candidate = candidate.split(".", 1)[0]
            return candidate, f"{part}/{candidate}"
    candidate = Path(source).stem
    return candidate, source


def _label_map(metainfo: dict[str, Any]) -> dict[int, str]:
    classes = metainfo.get("classes")
    if isinstance(classes, (list, tuple)):
        return {index: str(name) for index, name in enumerate(classes)}
    categories = metainfo.get("categories")
    if isinstance(categories, dict):
        if all(isinstance(value, int) for value in categories.values()):
            return {int(value): str(name) for name, value in categories.items()}
        if all(str(key).lstrip("-").isdigit() for key in categories):
            return {int(key): str(value) for key, value in categories.items()}
    return {}


def extract_embodiedscan_object_catalog(
    info_paths: list[Path], *, selected_scene_ids: set[str] | None = None,
    source_type: str = OFFICIAL_SOURCE_TYPE,
) -> dict[str, Any]:
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Unsupported object-catalog source type: {source_type}")
    scenes: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for path in info_paths:
        # Even hash-frozen annotations are parsed without arbitrary pickle globals.
        payload = load_restricted_annotation_pickle(path)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}: expected an object-valued EmbodiedScan info file")
        metainfo = payload.get("metainfo") or payload.get("metadata") or {}
        data_list = payload.get("data_list") or payload.get("infos")
        if not isinstance(metainfo, dict) or not isinstance(data_list, list):
            raise ValueError(f"{path}: missing metainfo/data_list")
        labels = _label_map(metainfo)
        if not labels:
            raise ValueError(f"{path}: cannot recover class names from metainfo")
        for item in data_list:
            if not isinstance(item, dict):
                continue
            identity = _scene_id(item)
            if identity is None:
                continue
            scene_id, source_scene_id = identity
            if selected_scene_ids is not None and scene_id not in selected_scene_ids:
                continue
            instances = item.get("instances")
            if not isinstance(instances, list):
                continue
            objects = []
            for index, instance in enumerate(instances):
                if not isinstance(instance, dict):
                    continue
                label_id = instance.get("bbox_label_3d")
                if not isinstance(label_id, int) or label_id not in labels:
                    continue
                label = labels[label_id].strip()
                if not label:
                    continue
                objects.append({
                    "object_id": f"hypo3d:{scene_id}:object:{index:04d}",
                    "class": label.casefold(),
                    "label": label,
                    "aliases": [label],
                    "source_instance_index": index,
                    "source_label_id": label_id,
                    "origin_type": "SOURCE_OBJECT_ANNOTATION",
                })
                bbox = instance.get("bbox_3d")
                if isinstance(bbox, (list, tuple)) and len(bbox) == 9:
                    numeric_bbox = [float(value) for value in bbox]
                    if not all(math.isfinite(value) for value in numeric_bbox):
                        raise ValueError(f"Non-finite bbox_3d for {scene_id}:{index}")
                    objects[-1]["bbox_3d"] = numeric_bbox
                    objects[-1]["bbox_3d_format"] = "XYZ_DXDYDZ_EULER_ZXY_RADIANS"
                    objects[-1]["coordinate_frame"] = "EMBODIEDSCAN_WORLD_X_RIGHT_Y_FRONT_Z_UP"
                bbox_id = instance.get("bbox_id")
                if isinstance(bbox_id, int):
                    objects[-1]["source_bbox_id"] = bbox_id
            candidate = {"source_scene_id": source_scene_id, "objects": objects, "relations": []}
            existing = scenes.get(scene_id)
            if existing is not None and existing != candidate:
                raise ValueError(f"Conflicting object annotations for scene {scene_id}")
            scenes[scene_id] = candidate
        hashes[str(path)] = sha256_file(path)
    return {
        "schema_version": "hypo3d_object_catalog_v2",
        "source_type": source_type,
        "source_hashes": dict(sorted(hashes.items())),
        "scenes": dict(sorted(scenes.items())),
    }
