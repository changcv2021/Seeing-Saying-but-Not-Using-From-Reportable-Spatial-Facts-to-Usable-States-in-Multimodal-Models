"""Small offline regression tests; no remote downloads or source-data mutation."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/extract_structured3d_remote_zip.py"
spec = importlib.util.spec_from_file_location("s3d_extract", SCRIPT)
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)


class RangeTests(unittest.TestCase):
    def test_cached_seek_and_eof(self):
        with patch.object(extract.requests.Session, "head") as head:
            head.return_value.headers = {"Accept-Ranges": "bytes", "Content-Length": "6"}
            with extract.HTTPRangeReader("https://example.invalid/a", 4) as reader:
                reader.cache = b"abcdef"
                self.assertEqual(reader.read(2), b"ab")
                self.assertEqual(reader.seek(-2, io.SEEK_END), 4)
                self.assertEqual(reader.read(8), b"ef")
                self.assertEqual(reader.seek(9), 9)
                self.assertEqual(reader.read(), b"")
                self.assertEqual(reader.seek(-6, io.SEEK_CUR), 3)
                self.assertEqual(reader.read(1), b"d")
                with self.assertRaises(ValueError):
                    reader.seek(-1)

    def test_network_error_not_hidden_by_zipfile(self):
        class Broken(io.BytesIO):
            def read(self, *args):
                raise extract.RemoteRangeError("TRUNCATED_RANGE")
        with self.assertRaisesRegex(extract.RemoteRangeError, "TRUNCATED_RANGE"):
            zipfile.ZipFile(Broken(b"x" * 100))

    def test_truncated_body_retry_and_cache_key(self):
        calls = []
        def curl(command, **kwargs):
            calls.append(command)
            Path(command[command.index("--dump-header") + 1]).write_text(
                "HTTP/1.1 206 Partial Content\nContent-Range: bytes 0-5/6\n")
            Path(command[command.index("--output") + 1]).write_bytes(b"ab" if len(calls) == 1 else b"abcdef")
            return SimpleNamespace(returncode=18 if len(calls) == 1 else 0, stderr="truncated" if len(calls) == 1 else "")
        with patch.object(extract.requests.Session, "head") as head, patch.object(extract.subprocess, "run", side_effect=curl), patch.object(extract.time, "sleep"):
            head.return_value.headers = {"Accept-Ranges": "bytes", "Content-Length": "6"}
            with extract.HTTPRangeReader("https://example.invalid/a", 4) as reader:
                self.assertEqual(reader.read(6), b"abcdef")
            self.assertEqual(len(calls), 2)
            self.assertIn("?spaceconflict_retry=", calls[1][-1])
            self.assertEqual(calls[0][calls[0].index("--range") + 1], "-6")

    def test_resume_checks_hash_decode_and_visibility(self):
        row = dict(locator="spar/structured3d/images/scene_00806/image_color/12_1.jpg",
                   scene_id="scene_00806", view_id="12", camera_id="1", withheld=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "withheld_source_png" / extract.expected_member(row)
            buf = io.BytesIO()
            extract.Image.new("RGB", (2, 2)).save(buf, format="PNG")
            payload = buf.getvalue()
            extract.write_png_atomic(path, payload)
            prior = dict(row, status="PASS", source_png=str(path), source_size=len(payload),
                         source_sha256=hashlib.sha256(payload).hexdigest(),
                         source_crc32=f"{zlib.crc32(payload) & 0xffffffff:08x}")
            self.assertTrue(extract.verified_resume(row, prior, root))
            self.assertFalse(extract.verified_resume(dict(row, withheld=False), prior, root))
            self.assertFalse(extract.verified_resume(row, dict(prior, source_sha256="wrong"), root))
            self.assertFalse(extract.verified_resume(row, dict(prior, source_crc32="00000000"), root))

    def test_retry_round_checkpoint_and_offline_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            accessible, withheld = root / "accessible.jsonl", root / "withheld.jsonl"
            prefix = "spar/structured3d/images/scene_00806/image_color/"
            accessible.write_text(json.dumps(dict(base_dataset="structured3d", locator=prefix + "12_1.jpg")) + "\n")
            withheld.write_text(json.dumps(dict(base_dataset="structured3d", locator=prefix + "12_2.jpg")) + "\n")
            args = SimpleNamespace(accessible=accessible, withheld=withheld, output_root=root / "output",
                                   report=root / "report.json", only_scene=None, limit=None, dry_run=False,
                                   resume=True, seed=1, run_id="test", rounds=2, block_size=1024, jpeg_quality=95)
            buf, png = io.BytesIO(), io.BytesIO()
            extract.Image.new("RGB", (2, 2)).save(png, format="PNG")
            with zipfile.ZipFile(buf, "w") as archive:
                for row in extract.load_required(args):
                    archive.writestr(extract.expected_member(row), png.getvalue())
            original_read = zipfile.ZipFile.read
            calls = []
            def fail_once(archive, info, *args, **kwargs):
                calls.append(info.filename)
                if len(calls) == 1:
                    raise extract.RemoteRangeError("TEST_TRUNCATED_BODY")
                return original_read(archive, info, *args, **kwargs)
            with patch.object(extract, "parse_args", return_value=args), patch.object(extract, "HTTPRangeReader", side_effect=lambda *args: io.BytesIO(buf.getvalue())), patch.object(zipfile.ZipFile, "read", fail_once):
                self.assertEqual(extract.main(), 0)
            result = json.loads(args.report.read_text())
            self.assertEqual((result["passed"], result["failed"], result["pending"]), (2, 0, 0))
            self.assertEqual(len(result["attempt_history"]), 1)
            self.assertEqual(len(calls), 3)
            self.assertFalse((args.output_root / "materialized" / (prefix + "12_2.jpg")).exists())
            with patch.object(extract, "parse_args", return_value=args), patch.object(extract, "HTTPRangeReader", side_effect=AssertionError("Resume must not fetch remote data")):
                self.assertEqual(extract.main(), 0)
            self.assertEqual(json.loads(args.report.read_text())["resumed"], 2)


if __name__ == "__main__":
    unittest.main()
