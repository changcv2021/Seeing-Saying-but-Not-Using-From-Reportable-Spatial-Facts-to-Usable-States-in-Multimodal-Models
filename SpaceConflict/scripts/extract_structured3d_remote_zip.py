#!/usr/bin/env python3
"""Range-download only the Structured3D RGB images required by SpaceConflict.

The official Structured3D ZIP server supports HTTP byte ranges. A cached reader exposes
each remote ZIP as a seekable file, allowing zipfile to fetch the central
directory and selected compressed members without downloading whole 12--15 GB
archives.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zlib
import zipfile
from collections import defaultdict
from pathlib import Path

import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


OFFICIAL_ROOT = "https://zju-kjl-jointlab-azure.kujiale.com/Structured3D"


class RemoteRangeError(RuntimeError):
    """Keep transport failures distinct from zipfile's OSError-to-BadZipFile wrapper."""


class HTTPRangeReader(io.RawIOBase):
    """Small seekable HTTP reader backed by cached byte-range requests."""

    def __init__(self, url: str, block_size: int):
        super().__init__()
        self.url = url
        self.block_size = block_size
        retry = Retry(
            total=8,
            connect=8,
            read=8,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(("HEAD", "GET")),
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        response = self.session.head(url, allow_redirects=True, timeout=(20, 120))
        response.raise_for_status()
        if "bytes" not in response.headers.get("Accept-Ranges", "").lower():
            raise OSError(f"Server does not advertise byte ranges: {url}")
        self.length = int(response.headers["Content-Length"])
        self.position = 0
        self.cache_start = 0
        self.cache = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.length + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if position < 0:
            raise ValueError("Negative seek position")
        self.position = position
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.length:
            return b""
        if size is None or size < 0:
            size = self.length - self.position
        size = min(size, self.length - self.position)
        if size == 0:
            return b""

        cache_end = self.cache_start + len(self.cache)
        wanted_end = self.position + size
        if not (self.cache_start <= self.position and wanted_end <= cache_end):
            # Fetch a complete tail window rather than a fragile 22-byte EOCD request.
            fetch_start = min(self.position, max(0, self.length - 65536))
            fetch_size = max(size, self.block_size)
            fetch_end = min(self.length - 1, max(wanted_end - 1, fetch_start + fetch_size - 1))
            expected = fetch_end - fetch_start + 1
            # curl HTTP/1.1 was verified against this server. Retry the entire body,
            # including truncated-body errors that requests' adapter does not retry.
            with tempfile.TemporaryDirectory(prefix="s3d-range-") as temp:
                headers_path = Path(temp) / "headers"
                body_path = Path(temp) / "body"
                for attempt in range(6):
                    # Change request form after a failure instead of repeating a
                    # potentially cached truncated response. Keep the original URL
                    # in source provenance; the query is only a transfer cache key.
                    request_url = self.url
                    if attempt:
                        separator = "&" if "?" in self.url else "?"
                        request_url += f"{separator}spaceconflict_retry={time.time_ns()}"
                    byte_range = (f"-{expected}" if fetch_end == self.length - 1
                                  else f"{fetch_start}-{fetch_end}")
                    result = subprocess.run([
                        "curl", "--http1.1", "--silent", "--show-error", "--fail",
                        "--location", "--connect-timeout", "20", "--max-time", "90",
                        "--max-filesize", str(expected), "--header", "Accept-Encoding: identity",
                        "--range", byte_range,
                        "--dump-header", str(headers_path), "--output", str(body_path), request_url,
                    ], capture_output=True, text=True)
                    headers = headers_path.read_text() if headers_path.exists() else ""
                    ranges = re.findall(r"(?im)^content-range:\s*bytes\s+(\d+)-(\d+)/(\d+)\s*$", headers)
                    valid_range = bool(ranges) and tuple(map(int, ranges[-1])) == (fetch_start, fetch_end, self.length)
                    if result.returncode == 0 and valid_range and body_path.stat().st_size == expected:
                        payload = body_path.read_bytes()
                        break
                    error = f"curl={result.returncode}; bytes={body_path.stat().st_size if body_path.exists() else 0}/{expected}; valid_range={valid_range}; {result.stderr[-300:]}"
                    print(f"[range-retry] attempt={attempt + 1} bytes={fetch_start}-{fetch_end}: {error}", flush=True)
                    if attempt == 5:
                        raise RemoteRangeError(f"RANGE_RETRIES_EXHAUSTED: {fetch_start}-{fetch_end}: {error}")
                    time.sleep(min(2 ** attempt, 16))
            self.cache_start = fetch_start
            self.cache = payload
            cache_end = self.cache_start + len(self.cache)

        offset = self.position - self.cache_start
        result = self.cache[offset : offset + size]
        self.position += len(result)
        return result

    def readinto(self, buffer) -> int:
        payload = self.read(len(buffer))
        buffer[: len(payload)] = payload
        return len(payload)

    def close(self) -> None:
        if not self.closed:
            self.session.close()
        super().close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accessible", type=Path, required=True)
    parser.add_argument("--withheld", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--only-scene")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--block-size", type=int, default=1024 * 1024)
    parser.add_argument("--rounds", type=int, default=3, help="Automatic passes over remaining failures")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--resume", action="store_true", help="Reuse source PNGs after CRC validation (also default behavior)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=20260904)
    parser.add_argument("--run-id", default="structured3d_range_retry_v3")
    return parser.parse_args()


def shard_for_scene(scene_id: str) -> int:
    number = int(scene_id.removeprefix("scene_"))
    if 1600 <= number <= 1799:
        raise ValueError(f"Official perspective-full scenes are unavailable: {scene_id}")
    # The current file 08 contains scene_01800--scene_01999. File 09 is absent.
    return 8 if 1800 <= number <= 1999 else number // 200


def records(path: Path, withheld: bool):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("base_dataset") != "structured3d":
                continue
            locator = row["locator"]
            parts = locator.split("/")
            if len(parts) != 6 or parts[:3] != ["spar", "structured3d", "images"]:
                raise ValueError(f"Unexpected Structured3D locator: {locator}")
            scene_id, leaf = parts[3], parts[5]
            stem = Path(leaf).stem
            view_id, camera_id = stem.rsplit("_", 1)
            yield {
                "locator": locator,
                "scene_id": scene_id,
                "view_id": view_id,
                "camera_id": camera_id,
                "withheld": withheld,
            }


def load_required(args: argparse.Namespace):
    dedup = {}
    for row in list(records(args.accessible, False)) + list(records(args.withheld, True)):
        previous = dedup.get(row["locator"])
        if previous is None or (previous["withheld"] and not row["withheld"]):
            dedup[row["locator"]] = row
    rows = sorted(dedup.values(), key=lambda item: item["locator"])
    if args.only_scene:
        rows = [row for row in rows if row["scene_id"] == args.only_scene]
    if args.limit is not None:
        rows = rows[: args.limit]
    return rows


def expected_member(row: dict) -> str:
    return (
        f'{row["scene_id"]}/2D_rendering/{row["view_id"]}/perspective/'
        f'full/{row["camera_id"]}/rgb_rawlight.png'
    )


def resolve_member(archive: zipfile.ZipFile, expected: str) -> zipfile.ZipInfo:
    try:
        return archive.getinfo(expected)
    except KeyError:
        suffix = "/" + expected
        matches = [info for info in archive.infolist() if info.filename.endswith(suffix)]
        if len(matches) != 1:
            raise KeyError(f"Expected one member ending in {expected!r}, found {len(matches)}")
        return matches[0]


def existing_matches(path: Path, info: zipfile.ZipInfo) -> bool:
    if not path.is_file() or path.stat().st_size != info.file_size:
        return False
    checksum = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum = zlib.crc32(chunk, checksum)
    return (checksum & 0xFFFFFFFF) == info.CRC


def write_png_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_jpeg_atomic(path: Path, payload: bytes, quality: int) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with Image.open(io.BytesIO(payload)) as image:
        image.convert("RGB").save(temporary, format="JPEG", quality=quality, optimize=True)
    os.replace(temporary, path)
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def verified_resume(row: dict, previous: dict, output_root: Path) -> bool:
    """Reuse only exact manifest matches with locally rechecked hashes and decoding."""
    if previous.get("status") != "PASS" or any(previous.get(key) != value for key, value in row.items()):
        return False
    category = "withheld_source_png" if row["withheld"] else "source_png"
    png = output_root / category / expected_member(row)
    if str(png) != previous.get("source_png"):
        return False
    files = [(png, "source_size", "source_sha256")]
    if not row["withheld"]:
        jpg = output_root / "materialized" / row["locator"]
        if str(jpg) != previous.get("materialized_jpg"):
            return False
        files.append((jpg, "materialized_size", "materialized_sha256"))
    try:
        for path, size_key, hash_key in files:
            data = path.read_bytes()
            if len(data) != previous.get(size_key) or hashlib.sha256(data).hexdigest() != previous.get(hash_key):
                return False
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        if f"{zlib.crc32(png.read_bytes()) & 0xFFFFFFFF:08x}" != previous.get("source_crc32"):
            return False
    except (OSError, ValueError):
        return False
    return True


def main() -> int:
    args = parse_args()
    required = load_required(args)
    if not required:
        raise SystemExit("No matching Structured3D media records")

    grouped = defaultdict(list)
    for row in required:
        grouped[shard_for_scene(row["scene_id"])].append(row)

    if args.dry_run:
        print(json.dumps({"requested": len(required), "shards": sorted(grouped), "run_id": args.run_id}))
        return 0

    args.report.parent.mkdir(parents=True, exist_ok=True)
    completed = []
    failures = []
    attempt_history = []
    previous = {}
    if args.resume and args.report.is_file():
        old_report = json.loads(args.report.read_text())
        previous = {item["locator"]: item for item in old_report.get("completed", [])}
        if old_report.get("config", {}).get("jpeg_quality") != args.jpeg_quality:
            previous = {}
    for row in required:
        prior = previous.get(row["locator"], {})
        if verified_resume(row, prior, args.output_root):
            completed.append(prior)
    print(f"[resume] hash/decode-verified={len(completed)} pending={len(required)-len(completed)}", flush=True)
    report = {
        "schema_version": "spaceconflict_structured3d_range_extract_v3",
        "run_id": args.run_id, "seed": args.seed,
        "source_revision": "SPAR-7M@0fe664cbada1e7c1173fd743e0f781882eebf777",
        "code_commit": "UNAVAILABLE_NO_GIT_REPOSITORY",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "input_hashes": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.accessible, args.withheld)},
        "config": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "requested": len(required),
        "archives": [f"Structured3D_perspective_full_{idx:02d}.zip" for idx in sorted(grouped)],
        "resumed": len(completed), "attempt_history": attempt_history,
    }

    def checkpoint(final=False):
        done = {item["locator"] for item in completed}
        unresolved = [row["locator"] for row in required if row["locator"] not in done]
        report.update(passed=len(completed), failed=len(failures), pending=len(unresolved),
                      completed=completed, failures=failures,
                      status=("PASS" if not unresolved else "FAIL") if final else "RUNNING")
        temporary_report = args.report.with_suffix(args.report.suffix + ".part")
        temporary_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_report, args.report)

    checkpoint()
    # A later pass retries unresolved archives/images, without rereading successful media.
    work = [(round_id, shard, rows) for round_id in range(1, args.rounds + 1)
            for shard, rows in sorted(grouped.items())]
    for round_id, shard, all_rows in work:
        done = {item["locator"] for item in completed}
        rows = [row for row in all_rows if row["locator"] not in done]
        if not rows:
            continue
        retrying = {row["locator"] for row in rows}
        failures[:] = [item for item in failures if item["locator"] not in retrying]
        filename = f"Structured3D_perspective_full_{shard:02d}.zip"
        url = f"{OFFICIAL_ROOT}/{filename}"
        print(f"[archive] round={round_id} {filename}: {len(rows)} pending images", flush=True)
        try:
            with HTTPRangeReader(url, args.block_size) as seekable, zipfile.ZipFile(seekable) as archive:
                for row in rows:
                    expected = expected_member(row)
                    try:
                        info = resolve_member(archive, expected)
                        category = "withheld_source_png" if row["withheld"] else "source_png"
                        png_path = args.output_root / category / expected
                        if existing_matches(png_path, info):
                            payload = png_path.read_bytes()
                        else:
                            payload = archive.read(info)
                            write_png_atomic(png_path, payload)
                        if (zlib.crc32(payload) & 0xFFFFFFFF) != info.CRC:
                            raise ValueError("CRC32 mismatch after extraction")
                        with Image.open(io.BytesIO(payload)) as image:
                            image.load()

                        output = {
                            **row,
                            "archive": filename,
                            "source_url": url,
                            "source_member": info.filename,
                            "source_size": len(payload),
                            "source_crc32": f"{info.CRC:08x}",
                            "source_sha256": hashlib.sha256(payload).hexdigest(),
                            "source_png": str(png_path),
                            "status": "PASS",
                        }
                        if not row["withheld"]:
                            jpg_path = args.output_root / "materialized" / row["locator"]
                            jpg_size, jpg_sha = write_jpeg_atomic(
                                jpg_path, payload, args.jpeg_quality
                            )
                            output.update(
                                materialized_jpg=str(jpg_path),
                                materialized_size=jpg_size,
                                materialized_sha256=jpg_sha,
                            )
                        completed.append(output)
                        checkpoint()
                        print(f'[pass] {row["locator"]}', flush=True)
                    except Exception as exc:  # continue to produce a complete failure report
                        failure = {**row, "archive": filename, "round": round_id, "error": repr(exc)}
                        failures.append(failure)
                        attempt_history.append(failure)
                        checkpoint()
                        print(f'[fail] {row["locator"]}: {exc!r}', file=sys.stderr, flush=True)
        except Exception as exc:
            for row in rows:
                if not any(item["locator"] == row["locator"] for item in failures + completed):
                    failure = {**row, "archive": filename, "round": round_id, "error": repr(exc)}
                    failures.append(failure)
                    attempt_history.append(failure)
            print(f"[archive-fail] {filename}: {exc!r}", file=sys.stderr, flush=True)
        checkpoint()

    checkpoint(final=True)
    print(json.dumps({key: report[key] for key in ("requested", "passed", "failed", "status")}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
