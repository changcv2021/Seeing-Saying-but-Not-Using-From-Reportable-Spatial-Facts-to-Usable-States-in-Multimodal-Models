import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from extract_official_rgbd_v2 import MediaReject, bounded_members, decode_rgb, recover_image


class FormatTests(unittest.TestCase):
    def encoded(self, fmt, mode='RGB'):
        image = Image.new(mode, (8, 6), 128 if mode == 'L' else 'red')
        buf = io.BytesIO(); image.save(buf, format=fmt); return buf.getvalue()

    def test_png_under_jpg_locator_preserves_source_bytes(self):
        payload = self.encoded('PNG')
        with tempfile.TemporaryDirectory() as root:
            row = recover_image(Path(root), 'spar/scannet/images/scene/image_color/7.jpg', payload, {'method':'TEST'})
            self.assertEqual(row['source_format'], 'PNG')
            self.assertTrue(row['materialized_jpg'].endswith('.png'))
            self.assertEqual(Path(row['source_file']).read_bytes(), payload)
            self.assertEqual(Path(row['materialized_jpg']).read_bytes(), payload)

    def test_jpeg_preserves_encoded_bytes(self):
        payload = self.encoded('JPEG'); meta, rendered = decode_rgb(payload)
        self.assertEqual(rendered, payload); self.assertEqual(meta['source_format'], 'JPEG')

    def test_grayscale_has_separate_lossless_rgb_input(self):
        payload = self.encoded('PNG', 'L')
        with tempfile.TemporaryDirectory() as root:
            row = recover_image(Path(root), 'frame.jpg', payload, {})
            self.assertEqual(Path(row['source_file']).read_bytes(), payload)
            with Image.open(row['materialized_jpg']) as image:
                self.assertEqual(image.mode, 'RGB'); self.assertEqual(image.getpixel((0,0)), (128,128,128))

    def test_malformed_is_structured_reject(self):
        with self.assertRaisesRegex(MediaReject, 'IMAGE_DECODE_FAILED'): decode_rgb(b'not an image')

    def test_depth_like_mode_is_not_silently_cast_to_rgb(self):
        image = Image.new('I;16', (8,6), 4000); buf = io.BytesIO(); image.save(buf, format='PNG')
        with self.assertRaisesRegex(MediaReject, 'NON_COLOR'): decode_rgb(buf.getvalue())

    def test_nonopaque_alpha_rejected(self):
        image = Image.new('RGBA', (8,6), (255,0,0,0)); buf=io.BytesIO(); image.save(buf,format='PNG')
        with self.assertRaisesRegex(MediaReject, 'NONOPAQUE'): decode_rgb(buf.getvalue())

    def test_bounded_tar_metadata_does_not_skip_records(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as archive:
            for i in range(200):
                member=tarfile.TarInfo(f'{i}.txt'); member.size=1
                archive.addfile(member, io.BytesIO(b'x'))
        buf.seek(0); names=[]
        with tarfile.open(fileobj=buf,mode='r|gz') as archive:
            for member in bounded_members(archive):
                names.append(member.name)
                self.assertEqual(archive.extractfile(member).read(), b'x')
                self.assertLessEqual(len(archive.members), 1)
        self.assertEqual(names, [f'{i}.txt' for i in range(200)])


if __name__ == '__main__': unittest.main()
