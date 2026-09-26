"""Tiny local regression checks; no archive download or benchmark scan."""
import gzip
import io
import tempfile
import tarfile
import unittest
from pathlib import Path
from recover_official_rgbd import ConcatenatedParts


class RecoveryTests(unittest.TestCase):
    def test_stream_reads_across_split_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            paths = [Path(root)/str(i) for i in range(4)]
            for path, value in zip(paths, (b'ab', b'', b'cde', b'f')): path.write_bytes(value)
            with ConcatenatedParts(paths) as reader:
                self.assertEqual(reader.read(3), b'abc')
                self.assertEqual(reader.read(5), b'def')
                self.assertEqual(reader.read(2), b'')
                self.assertEqual(reader.total_read, 6)

    def test_split_gzip_tar_native_member(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as archive:
            member = tarfile.TarInfo('spar/scannet/images/scene0000_00/image_color/13.jpg')
            member.size = 8
            archive.addfile(member, io.BytesIO(b'example!'))
        payload = data.getvalue()
        with tempfile.TemporaryDirectory() as root:
            paths = []
            for i in range(0, len(payload), 11):
                path = Path(root)/str(i); path.write_bytes(payload[i:i+11]); paths.append(path)
            with ConcatenatedParts(paths) as source, tarfile.open(fileobj=source, mode='r|gz') as archive:
                member = next(iter(archive))
                self.assertEqual(member.name, 'spar/scannet/images/scene0000_00/image_color/13.jpg')
                self.assertEqual(archive.extractfile(member).read(), b'example!')


if __name__ == '__main__': unittest.main()
