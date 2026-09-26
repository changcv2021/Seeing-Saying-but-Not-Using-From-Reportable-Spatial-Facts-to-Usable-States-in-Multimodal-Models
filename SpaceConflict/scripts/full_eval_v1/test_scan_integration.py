import io
import json
import hashlib
import tempfile
import tarfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from spar_media import view_plan, present
from integrate_downloaded_scans import matrix_key, process_pp

class Tests(unittest.TestCase):
    def fixture(self):
        frames=[f'spar/scannetpp/images/scene/image_color/{i*10}.jpg' for i in range(3)]
        manifest=dict(media_id='m',frame_count=3,ordered_frame_paths=frames,
                      bbox_grounding=dict(red_bbox=[[100,100,200,200]],blue_bbox=[[300,300,400,400]],bbox_img_idx=[[2,1]]))
        row=dict(media=dict(source_references=[dict(archive_member=frames[0],media_id='m',media_manifest='index')]))
        return frames,manifest,row
    def test_multiview_expansion(self):
        frames,manifest,row=self.fixture()
        plan=view_plan(row,'binary',{'m':manifest})
        self.assertEqual([r['locator'] for r in plan],frames)
        self.assertEqual(plan[0]['boxes'],[])
        self.assertEqual(plan[1]['boxes'][0]['color'],'blue')
        self.assertEqual(plan[2]['boxes'][0]['color'],'red')
    def test_unknown_never_restores_hidden_frame_or_box(self):
        frames,manifest,row=self.fixture()
        row['media']['source_references']=[dict(archive_member=frames[0],role='frame_0'),dict(archive_member=frames[1],role='frame_1')]
        candidate=dict(claim=dict(normalized=dict(context=dict(media_id='m'))))
        plan=view_plan(row,'unknown',{'m':manifest},candidate)
        self.assertEqual(len(plan),2)
        self.assertNotIn(frames[2],[r['locator'] for r in plan])
        self.assertNotIn('red',[b['color'] for r in plan for b in r['boxes']])
    def test_pose_matching_is_not_nearest_neighbor(self):
        identity=np.eye(4)
        other=identity.copy(); other[0,3]=0.01
        self.assertNotEqual(matrix_key(identity),matrix_key(other))
        self.assertIsNone(matrix_key(np.full((4,4),np.nan)))
    def test_pp_requires_camera_metadata_and_retains_native_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/'s.tar.gz'
            payload=io.BytesIO(); Image.new('RGB',(20,15)).save(payload,format='JPEG')
            meta=io.BytesIO(); np.savez(meta,images=np.array(['frame_000020.jpg']),trajectories=np.eye(4)[None],intrinsics=np.eye(3)[None])
            with tarfile.open(archive,'w:gz') as t:
                for name,data in [('s/images/frame_000020.jpg',payload.getvalue()),('s/images/frame_000030.jpg',payload.getvalue()),('s/scene_iphone_metadata.npz',meta.getvalue())]:
                    m=tarfile.TarInfo(name); m.size=len(data); t.addfile(m,io.BytesIO(data))
            wanted={f'spar/scannetpp/images/s/image_color/{n}.jpg' for n in (20,30)}
            args=('s',wanted,archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest(),root,False)
            result=process_pp(args)
            self.assertEqual(len(result['completed']),1)
            self.assertEqual(result['completed'][0]['provenance']['native_frame_id'],20)
            self.assertEqual(result['failed'][0]['reject_code'],'SCANNETPP_EXACT_FRAME_ABSENT_FROM_CAMERA_METADATA')
    def test_bbox_render_is_deterministic_and_raw_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); raw=root/'raw.jpg'; Image.new('RGB',(100,100),'white').save(raw)
            digest=hashlib.sha256(raw.read_bytes()).hexdigest()
            asset=dict(materialized_jpg=str(raw),materialized_sha256=digest)
            item=dict(locator='source',role='frame_0',boxes=[dict(color='red',xyxy=[100,100,200,200])])
            first=present(asset,item,root/'rendered'); second=present(asset,item,root/'rendered')
            self.assertEqual(first,second)
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(),digest)
            with Image.open(first['path']) as image:
                self.assertEqual(image.getpixel((10,10)),(255,0,0))

if __name__=='__main__': unittest.main()
