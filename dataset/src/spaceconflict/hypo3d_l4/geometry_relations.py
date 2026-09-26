from __future__ import annotations

import math
from typing import Any


PREDICATE_AXIS_SIGN = {
    "LEFT_OF": (0, -1), "RIGHT_OF": (0, 1),
    "BEHIND": (1, -1), "FRONT_OF": (1, 1),
    "BELOW": (2, -1), "ABOVE": (2, 1),
}
INVERSE_PREDICATE = {
    "LEFT_OF": "RIGHT_OF", "RIGHT_OF": "LEFT_OF",
    "BEHIND": "FRONT_OF", "FRONT_OF": "BEHIND",
    "BELOW": "ABOVE", "ABOVE": "BELOW",
}


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def _zxy_matrix(alpha: float, beta: float, gamma: float) -> list[list[float]]:
    """Match PyTorch3D ``euler_angles_to_matrix(angles, 'ZXY')``."""
    ca, sa = math.cos(alpha), math.sin(alpha)
    cb, sb = math.cos(beta), math.sin(beta)
    cg, sg = math.cos(gamma), math.sin(gamma)
    rz = [[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]]
    rx = [[1.0, 0.0, 0.0], [0.0, cb, -sb], [0.0, sb, cb]]
    ry = [[cg, 0.0, sg], [0.0, 1.0, 0.0], [-sg, 0.0, cg]]
    return _matmul(_matmul(rz, rx), ry)


def bbox_intervals(bbox_3d: list[float]) -> tuple[tuple[float, float], ...]:
    if len(bbox_3d) != 9 or not all(isinstance(value, (int, float)) for value in bbox_3d):
        raise ValueError("Expected a numeric 9-DoF bbox")
    cx, cy, cz, dx, dy, dz, alpha, beta, gamma = map(float, bbox_3d)
    if min(dx, dy, dz) <= 0 or not all(math.isfinite(value) for value in bbox_3d):
        raise ValueError("Invalid 9-DoF bbox")
    rotation = _zxy_matrix(alpha, beta, gamma)
    extents = []
    half = (dx / 2.0, dy / 2.0, dz / 2.0)
    for axis in range(3):
        extents.append(sum(abs(rotation[axis][source]) * half[source] for source in range(3)))
    centers = (cx, cy, cz)
    return tuple((centers[axis] - extents[axis], centers[axis] + extents[axis]) for axis in range(3))


def strict_separated_relation(
    subject: dict[str, Any], predicate: str, object_: dict[str, Any], *, margin: float = 0.02,
) -> bool:
    """Prove a relation only when the oriented boxes are disjoint on its axis."""
    if predicate not in PREDICATE_AXIS_SIGN:
        return False
    subject_bbox, object_bbox = subject.get("bbox_3d"), object_.get("bbox_3d")
    if not isinstance(subject_bbox, list) or not isinstance(object_bbox, list):
        return False
    subject_intervals = bbox_intervals(subject_bbox)
    object_intervals = bbox_intervals(object_bbox)
    axis, sign = PREDICATE_AXIS_SIGN[predicate]
    s_min, s_max = subject_intervals[axis]
    o_min, o_max = object_intervals[axis]
    return s_max + margin < o_min if sign < 0 else s_min > o_max + margin
