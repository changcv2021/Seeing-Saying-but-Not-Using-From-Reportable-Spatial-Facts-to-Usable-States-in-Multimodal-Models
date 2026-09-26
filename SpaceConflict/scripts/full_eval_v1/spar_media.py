"""Source-grounded SPAR view expansion and deterministic bbox presentation."""
import hashlib
import io
import json
from pathlib import Path
from PIL import Image, ImageDraw

def locator(ref):
    return ref.get('archive_member') or ref.get('relative_path')

def view_plan(row, component, manifests, candidate=None):
    refs = row['media'].get('source_references') or []
    if not refs:
        raise ValueError('EMPTY_SPAR_REFERENCES')
    key = refs[0].get('media_manifest_key') or refs[0].get('media_id')
    if component == 'unknown' and candidate:
        key = candidate['claim']['normalized']['context'].get('media_id')
    manifest = manifests.get(key)
    if refs[0].get('media_manifest') and not manifest:
        raise ValueError(f'SPAR_MEDIA_MANIFEST_NOT_FOUND:{key}')
    if component == 'binary' and manifest:
        frames = manifest['ordered_frame_paths']
        if locator(refs[0]) != frames[0] or len(frames) != manifest['frame_count']:
            raise ValueError('SPAR_MEDIA_MANIFEST_FRAME_MISMATCH')
        plan = [dict(locator=path, role=f'frame_{i}', frame_index=i) for i,path in enumerate(frames)]
    else:
        # Unknown: do NOT expand its parent, even if all parent images exist.
        plan = []
        for i, ref in enumerate(refs):
            path = locator(ref)
            indices = [n for n,x in enumerate(manifest['ordered_frame_paths']) if x == path] if manifest else []
            role = ref.get('role', f'frame_{i}')
            index = int(role[6:]) if role.startswith('frame_') and role[6:].isdigit() else (indices[0] if len(indices)==1 else None)
            if manifest and index is not None and manifest['ordered_frame_paths'][index] != path:
                raise ValueError('SPAR_UNKNOWN_FRAME_IDENTITY_MISMATCH')
            plan.append(dict(locator=path, role=role, frame_index=index))
    for item in plan:
        item['boxes'] = []
    if manifest:
        grounding = manifest['bbox_grounding']
        active = [(color, grounding.get(color+'_bbox') or []) for color in ('red','green','blue','yellow')]
        active = [(c,b) for c,b in active if b]
        indices = grounding.get('bbox_img_idx') or []
        if len(indices)==1 and isinstance(indices[0],list):
            indices = indices[0]
        if manifest['frame_count']==1:
            indices = [0]*len(active)
        if len(indices)!=len(active):
            raise ValueError('SPAR_BBOX_FRAME_SCHEMA_UNSUPPORTED')
        for (color,boxes), index in zip(active, indices):
            if not isinstance(index,int) or not 0<=index<manifest['frame_count']:
                raise ValueError('SPAR_BBOX_FRAME_INDEX_INVALID')
            for box in boxes:
                if len(box)!=4 or not all(isinstance(v,(int,float)) for v in box) or box[2]<=box[0] or box[3]<=box[1]:
                    raise ValueError('SPAR_BBOX_COORDINATES_INVALID')
                for item in plan:
                    if item['frame_index']==index:
                        item['boxes'].append(dict(color=color, xyxy=box))
    if component=='unknown':
        allowed = {locator(ref) for ref in refs}
        if any(item['locator'] not in allowed for item in plan):
            raise ValueError('WITHHELD_EVIDENCE_EXPOSED')
    return plan

def present(asset, item, output):
    path = Path(asset['materialized_jpg'])
    expected = asset['materialized_sha256'].removeprefix('sha256:')
    if not item['boxes']:
        return dict(kind='image', path=str(path), role=item['role'], sha256=expected, source_locator=item['locator'])
    descriptor = dict(source_sha256=expected, boxes=item['boxes'], policy='normalized_xyxy_1000_outline_v1')
    key = hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()
    target = output/f'{key}.png'
    if not target.exists():
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest()!=expected:
            raise ValueError('SPAR_SOURCE_IMAGE_HASH_MISMATCH')
        with Image.open(io.BytesIO(payload)) as im:
            im = im.convert('RGB')
            draw=ImageDraw.Draw(im)
            for box in item['boxes']:
                xy = [max(0,min(im.width-1,round(v*im.width/1000))) if i%2==0
                      else max(0,min(im.height-1,round(v*im.height/1000))) for i,v in enumerate(box['xyxy'])]
                draw.rectangle(xy, outline=box['color'], width=max(2,round(min(im.size)/250)))
            output.mkdir(parents=True, exist_ok=True)
            im.save(target, format='PNG')
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    return dict(kind='image', path=str(target), role=item['role'], sha256=digest,
                source_locator=item['locator'], presentation=descriptor)
