"""CPU allocation only: validate repaired imports and frozen setup processor path.

No model weights, generation, real-world responses, or private gold are opened.
The prior Phase A preservation manifest is verified, not regenerated.
"""
import importlib.util
import subprocess
import time
from common import *


def main():
    a = arguments(__doc__).parse_args()
    cfg, root = setup(a)
    if a.dry_run:
        print('PLANNED: imports, frozen hashes, all setup processor inputs; no generation')
        return
    require_compute()
    started = time.monotonic()
    report = dict(status='RUNNING',job_id=os.environ['SLURM_JOB_ID'],
                  scope='LAUNCHER_IMPORT_AND_SETUP_PROCESSOR_PREFLIGHT_NOT_MODEL_EVALUATION',
                  generated_responses=0,model_weights_loaded=False,private_gold_opened=False,
                  python=sys.executable,pythonpath=os.environ.get('PYTHONPATH'),checks=[])
    target = root/'reports/launcher_v2_preflight'/('job_'+os.environ['SLURM_JOB_ID']+'.json')
    try:
        lock = load(root/'manifest/setup_v1_lock.json')
        assert sha(a.config) == lock['config_sha256'], 'CONFIG_CHANGED'
        for e in lock['code']:
            assert sha(e['path']) == e['sha256'], 'FROZEN_CODE_CHANGED:'+e['path']
        manifest = root/'inputs/setup_v1/requests.jsonl'
        assert sha(manifest) == lock['inputs_sha256'], 'INPUTS_CHANGED'
        req = list(rows(manifest))
        assert len(req) == lock['requests'] == 142
        assert all(r['level']=='SETUP_ONLY' and not r['payload']['media'] and r['models']==cfg['models'] for r in req)
        report['checks'].append('FROZEN_CONFIG_CODE_AND_142_SETUP_INPUTS_PASS')
        campaign = load(Path(cfg['campaign'])/'config.json')
        legacy = Path(cfg['campaign'])/'code'
        sys.path.insert(0,str(legacy))
        import protocol
        import spaceconflict.mllm_l4 as project_module
        assert Path(project_module.__file__).resolve() == (Path(cfg['project'])/'src/spaceconflict/mllm_l4.py').resolve()
        report['resolved_imports'] = [entry(protocol.__file__),entry(project_module.__file__)]
        report['checks'].append('LEGACY_PROTOCOL_AND_EXACT_PROJECT_MODULE_IMPORT_PASS')
        import torch
        import transformers
        from transformers import AutoModelForMultimodalLM, AutoProcessor
        from infer import tensor_hash
        from scorer import selftest
        torch.set_num_threads(int(os.environ.get('SLURM_CPUS_PER_TASK','1')))
        report['versions'] = dict(torch=torch.__version__,transformers=transformers.__version__)
        report['scorer_tests'] = selftest()
        helper = legacy/'vision_process_frozen.py'
        assert sha(helper) == campaign['vision_helper_sha256'], 'VISION_HELPER_CHANGED'
        spec = importlib.util.spec_from_file_location('a1_preflight_vision',helper)
        vision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vision)
        models = []
        for key in cfg['models']:
            mc = next(m for m in campaign['models'] if m['key']==key)
            mm = load(mc['manifest_path'])
            assert (mm['model_id'],mm['revision']) == (mc['model'],mc['revision'])
            processor = AutoProcessor.from_pretrained(mc['model_path'],local_files_only=True,use_fast=True)
            json.dumps(processor.to_dict())  # Same environment serialization as inference.
            prompt_hashes = []
            for r in req:
                messages = protocol.messages_for(dict(level='L1',claim_text='',media=[]),campaign['media_budget'])
                messages[0]['content'] = r['payload']['system']
                messages[1]['content'][-1] = dict(type='text',text=r['payload']['text'])
                rendered = processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
                assert '<think>' not in rendered or '</think>' in rendered, 'THINKING_MODE_OPEN'
                imgs,vids,vkwargs = vision.process_vision_info(messages,image_patch_size=16,return_video_kwargs=True,return_video_metadata=True)
                assert not imgs and not vids
                batch = processor(text=[rendered],images=imgs,return_tensors='pt',do_resize=False)
                visual = {k:dict(shape=list(v.shape),dtype=str(v.dtype),sha256=tensor_hash(v)) for k,v in batch.items()
                          if torch.is_tensor(v) and k not in ['input_ids','attention_mask']}
                assert visual == {}, 'UNEXPECTED_SETUP_VISUAL_FIELDS'
                marker = load(root/'review/actual_presentations'/digest(visual)/'manifest.json')
                assert marker['visual']=={} and marker['media']==[]
                prompt_hashes.append(dict(request_id=r['request_id'],sha256=hashlib.sha256(rendered.encode()).hexdigest(),
                                          input_tokens=int(batch['input_ids'].shape[-1])))
            models.append(dict(model=key,revision=mc['revision'],processor_requests=len(prompt_hashes),
                               prompt_hashes=prompt_hashes,empty_visual_shared_marker_pass=True))
            print(json.dumps(dict(model=key,processor_requests=len(prompt_hashes),generation_requests=0)),flush=True)
            subprocess.run([sys.executable,str(CODE/'src/infer.py'),'--config',str(a.config),'--run-id',a.run_id,
                            '--seed',str(a.seed),'--resume','--dry-run','--stage','setup_v1','--model',key],check=True)
        report['models'] = models
        report['checks'].append('ALL_426_PROCESSOR_PATHS_AND_THREE_INFER_DRY_RUNS_PASS')
        baseline = list(rows(root/'manifest/phase_a_files_before.jsonl'))
        changes = [e['path'] for e in baseline if not Path(e['path']).is_file() or sha(e['path'])!=e['sha256']]
        report['phase_a_preservation'] = dict(files_checked=len(baseline),changed_files=changes)
        assert not changes, 'PHASE_A_FILES_CHANGED'
        report['checks'].append('PHASE_A_READ_ONLY_BASELINE_PASS')
        report['launcher'] = entry(CODE/'scripts/job_launcher_v2.sh')
        report['preflight_code'] = entry(__file__)
        report['setup_lock'] = entry(root/'manifest/setup_v1_lock.json')
        report['status'] = 'PASS'
    except Exception as exc:
        report.update(status='FAIL',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report['wall_seconds'] = time.monotonic()-started
        report['timestamp_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        save(target,report,frozen=True)
        print(json.dumps(dict(status=report['status'],report=str(target))),flush=True)


if __name__ == '__main__':
    main()
