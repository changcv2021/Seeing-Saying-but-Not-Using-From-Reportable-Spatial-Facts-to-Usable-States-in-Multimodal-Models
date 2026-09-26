"""Atomic, version-bound checkpoints including optimizer/scheduler and all RNGs."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import uuid


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path); tmp = path.with_name(path.name+'.tmp.'+uuid.uuid4().hex)
    with tmp.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def rng_state():
    import numpy as np
    import torch
    return dict(python=random.getstate(), numpy=np.random.get_state(),
                torch=torch.get_rng_state(), cuda=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [])


def restore_rng(state):
    import numpy as np
    import torch
    random.setstate(state['python']); np.random.set_state(state['numpy']); torch.set_rng_state(state['torch'])
    if state['cuda']: torch.cuda.set_rng_state_all(state['cuda'])


def save_checkpoint(directory, model, optimizer, scheduler, progress, fingerprint, adapter=True):
    import torch
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    name = f"step_{progress['step']:07d}"
    final = directory/name
    if final.exists():
        raise FileExistsError('PRESERVE_COMMITTED_CHECKPOINT:' + str(final))
    temp = directory/(name+'.incomplete.'+uuid.uuid4().hex); temp.mkdir()
    captured_rng = rng_state()
    if adapter: model.save_pretrained(temp/'adapter', safe_serialization=True)
    else: torch.save(model.state_dict(), temp/'weights.pt')
    payload = dict(format_version=1, fingerprint=fingerprint, progress=copy.deepcopy(progress),
        optimizer=optimizer.state_dict(), scheduler=scheduler.state_dict(), rng=captured_rng)
    torch.save(payload, temp/'training_state.pt')
    hashes = {str(p.relative_to(temp)): file_sha(p) for p in temp.rglob('*') if p.is_file()}
    for rel in hashes:
        with (temp/rel).open('rb') as f: os.fsync(f.fileno())
    atomic_json(temp/'COMMITTED.json', dict(step=progress['step'], fingerprint=fingerprint, hashes=hashes,
        saved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), includes_full_training_state=True))
    os.replace(temp, final)
    atomic_json(directory/'LATEST.json', dict(name=name, step=progress['step'], fingerprint=fingerprint))
    # Serialization must not change the stochastic sequence of uninterrupted work.
    restore_rng(captured_rng)
    return final


def latest_checkpoint(directory, fingerprint):
    directory = Path(directory); pointer = directory/'LATEST.json'
    ref = None
    if pointer.exists():
        ref = json.loads(pointer.read_text())
        if ref['fingerprint'] != fingerprint or not re.fullmatch(r'step_[0-9]+',ref['name']):
            raise ValueError('CHECKPOINT_POINTER_OR_CONFIG_MISMATCH')
        if not (directory/ref['name']/'COMMITTED.json').is_file():
            raise ValueError('CHECKPOINT_POINTER_NOT_COMMITTED')
    # A crash may occur after directory commit but before LATEST pointer rename.
    # Recover the highest fully committed step, never an incomplete temp folder.
    candidates = [p for p in directory.glob('step_*') if re.fullmatch(r'step_[0-9]+',p.name)
                  and (p/'COMMITTED.json').is_file()]
    if not candidates: return None
    p = max(candidates,key=lambda x:int(x.name.split('_')[1]))
    committed = json.loads((p/'COMMITTED.json').read_text())
    if committed['fingerprint'] != fingerprint or committed['step'] != int(p.name.split('_')[1]):
        raise ValueError('CHECKPOINT_COMMIT_MISMATCH')
    for rel, expected in committed['hashes'].items():
        if file_sha(p/rel) != expected: raise ValueError('CHECKPOINT_CORRUPT:' + rel)
    return p


def restore_checkpoint(path, model, optimizer, scheduler, fingerprint, adapter=True):
    import torch
    path = Path(path); commit = json.loads((path/'COMMITTED.json').read_text())
    if commit['fingerprint'] != fingerprint: raise ValueError('CHECKPOINT_CONFIG_MISMATCH')
    for rel, expected in commit['hashes'].items():
        if file_sha(path/rel) != expected: raise ValueError('CHECKPOINT_CORRUPT:' + rel)
    # These are only our own validated, local checkpoints, not untrusted downloads.
    state = torch.load(path/'training_state.pt', map_location='cpu', weights_only=False)
    if state['fingerprint'] != fingerprint: raise ValueError('CHECKPOINT_STATE_MISMATCH')
    if adapter:
        from safetensors.torch import load_file
        from peft import set_peft_model_state_dict
        set_peft_model_state_dict(model, load_file(path/'adapter/adapter_model.safetensors'))
    else:
        model.load_state_dict(torch.load(path/'weights.pt', map_location='cpu', weights_only=True))
    optimizer.load_state_dict(state['optimizer']); scheduler.load_state_dict(state['scheduler'])
    restore_rng(state['rng'])
    return state['progress']


class StopAtBoundary:
    def __init__(self): self.requested = False; self.signal = None
    def handle(self, signum, frame): self.requested = True; self.signal = signum
    def install(self):
        signal.signal(signal.SIGUSR1, self.handle)
        signal.signal(signal.SIGTERM, self.handle)
        return self
