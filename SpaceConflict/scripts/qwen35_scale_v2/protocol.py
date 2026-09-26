"""Blind prompts matching the frozen SpaceConflict 7B evaluation."""
from spaceconflict.mllm_l4 import SYSTEM_PROMPT, user_prompt as l4_prompt

def messages_for(sample, budget):
    content = []
    for i, media in enumerate(sample.get('media') or [], 1):
        kind = media.get('kind', 'image')
        role = media.get('role') or f'media_{i}'
        content.append(dict(type='text', text=f'Evidence {kind} {i} ({role}):'))
        if kind == 'image':
            content.append(dict(type='image', image=media['path'], min_pixels=budget['min_pixels'], max_pixels=budget['max_pixels']))
        elif kind == 'video':
            content.append(dict(type='video', video=media['path'], nframes=budget['video_frames'], min_pixels=budget['min_pixels'], max_pixels=budget['video_max_pixels']))
        elif kind == 'video_frames':
            content.append(dict(type='video', video=media['paths'], sample_fps=media.get('sample_fps', 2.0), min_pixels=budget['min_pixels'], max_pixels=budget['video_max_pixels']))
        else:
            raise ValueError(f'UNSUPPORTED_MEDIA_KIND:{kind}')
    if sample['level'] == 'L4':
        prompt = l4_prompt(sample)
    else:
        prompt = ((sample.get('media_context', '')+'\n\n') if sample.get('media_context') else '') + (
            f"Spatial claim:\n{sample['claim_text']}\n\n"
            f"Accessible evidence: {len(sample.get('media') or [])} media item(s) supplied above.\n\n"
            'Return exactly one JSON object with this schema:\n'
            '{"label":"SUPPORTED|CONTRADICTORY|UNKNOWN","confidence":0.0,"reason":"brief explanation"}')
    content.append(dict(type='text', text=prompt))
    return [dict(role='system', content=SYSTEM_PROMPT), dict(role='user', content=content)]

def selected_rows(rows, count, index, limit=None):
    if count < 1 or not 0 <= index < count:
        raise ValueError('INVALID_SHARD')
    if limit is not None and limit <= 0:
        raise ValueError('INVALID_LIMIT')
    result = [r for i, r in enumerate(rows) if i % count == index]
    return result if limit is None else result[:limit]
