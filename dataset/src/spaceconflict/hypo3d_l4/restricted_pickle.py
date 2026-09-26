from __future__ import annotations

import builtins
import _codecs
import collections
import pickle
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

try:
    from numpy._core import multiarray as _np_multiarray
except ImportError:  # NumPy 1.x compatibility
    from numpy.core import multiarray as _np_multiarray


_SAFE_GLOBALS: dict[tuple[str, str], Any] = {
    # Python 2-compatible protocol-2 pickles encode byte strings through this
    # pure codec primitive.  It has no filesystem, network, or process effects.
    ("_codecs", "encode"): _codecs.encode,
    ("builtins", "complex"): builtins.complex,
    ("builtins", "frozenset"): builtins.frozenset,
    ("builtins", "set"): builtins.set,
    ("builtins", "slice"): builtins.slice,
    ("collections", "OrderedDict"): collections.OrderedDict,
    ("numpy", "dtype"): np.dtype,
    ("numpy", "ndarray"): np.ndarray,
    ("numpy.core.multiarray", "_reconstruct"): _np_multiarray._reconstruct,
    ("numpy.core.multiarray", "scalar"): _np_multiarray.scalar,
    ("numpy._core.multiarray", "_reconstruct"): _np_multiarray._reconstruct,
    ("numpy._core.multiarray", "scalar"): _np_multiarray.scalar,
}


class RestrictedAnnotationUnpickler(pickle.Unpickler):
    """Unpickle primitive annotation containers without arbitrary imports."""

    def find_class(self, module: str, name: str) -> Any:
        allowed = _SAFE_GLOBALS.get((module, name))
        if allowed is None:
            raise pickle.UnpicklingError(f"forbidden pickle global: {module}.{name}")
        return allowed

    def persistent_load(self, pid: object) -> Any:
        raise pickle.UnpicklingError(f"persistent pickle IDs are forbidden: {pid!r}")


def load_restricted_annotation_pickle(source: Path | BinaryIO) -> Any:
    if isinstance(source, Path):
        with source.open("rb") as handle:
            return RestrictedAnnotationUnpickler(handle).load()
    return RestrictedAnnotationUnpickler(source).load()
