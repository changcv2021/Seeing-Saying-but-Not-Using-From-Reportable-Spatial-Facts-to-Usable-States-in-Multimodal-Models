# Dataset construction

The SpaceConflict construction package lives here. Read [data organization](../docs/DATA.md) and [source terms](../DATA_TERMS.md) before using upstream assets.

| Directory | Purpose |
|---|---|
| `src/spaceconflict/` | Source adapters, canonical worlds, transformations, verifiers and CLI |
| `contracts/`, `schemas/`, `operators/` | Source contracts and task definitions |
| `configs/` | Versioned construction configurations |
| `scripts/` | Acquisition, construction, media preparation and shared historical model-runner implementations |
| `tests/` | Construction unit tests; some require unbundled source-discovery artifacts |
| `release/`, `l4/` | Construction-level release records and L4-specific assets |
| `research/` | Earlier diagnostic dependencies preserved for existing runners |

Full benchmark and SFT train/dev/test files remain under [`artifacts/model_results/`](../artifacts/model_results/), not duplicated here. From the repository root:

```bash
python tools/validate_data.py
```

Source media is not included. `tools/resolve_media.py` relocates legally obtained media using hashes. The Python package is still named `spaceconflict`; only its source directory changed. Read the root requirements and `pyproject.toml` before installing construction dependencies. Validation does not download or reconstruct data.
