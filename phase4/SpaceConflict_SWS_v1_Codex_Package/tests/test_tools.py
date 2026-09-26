from __future__ import annotations
import copy
import gzip
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from research_utils import (strict_json_loads, exact_claim_label, typed_equal,
                           validate_split_records, planned_counts, estimate_gpu_hours,
                           sha256_file, canonical_hash)
from submit_wave import validate_wave, commands, walltime
from pack_review import build_package, COPY_FILES


class JsonTests(unittest.TestCase):
    def test_unique_alias_not_implicitly_repaired(self):
        self.assertEqual(strict_json_loads('{"query_value":2}'), {"query_value": 2})
    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            strict_json_loads('{"value":1,"value":2}')
    def test_nested_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            strict_json_loads('{"x":{"k":1,"k":2}}')
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            strict_json_loads('{"value":NaN}')
    def test_bool_not_integer(self):
        self.assertFalse(typed_equal(True, 1))
    def test_hash_key_order_independent(self):
        self.assertEqual(canonical_hash({"x":1,"y":2}), canonical_hash({"y":2,"x":1}))


class EvidenceTests(unittest.TestCase):
    def test_supported(self):
        self.assertEqual(exact_claim_label([3], 3), "SUPPORTED")
    def test_contradictory(self):
        self.assertEqual(exact_claim_label([3], 2), "CONTRADICTORY")
    def test_insufficient_exact(self):
        self.assertEqual(exact_claim_label([3, 4], 3), "UNKNOWN")
    def test_partial_evidence_can_refute(self):
        self.assertEqual(exact_claim_label([3, 4, 5], 1), "CONTRADICTORY")
    def test_empty_not_unknown(self):
        with self.assertRaises(ValueError):
            exact_claim_label([], 1)
    def test_null_not_world_value(self):
        with self.assertRaises(ValueError):
            exact_claim_label([None], 1)


class SplitTests(unittest.TestCase):
    def test_same_world_conditions_allowed(self):
        rows=[{"record_id":"a","world_cluster_id":"W","split":"discovery"},
              {"record_id":"b","world_cluster_id":"W","split":"discovery"}]
        self.assertEqual(validate_split_records(rows), {"records":2,"world_clusters":1})
    def test_cross_split_blocked(self):
        rows=[{"record_id":"a","world_cluster_id":"W","split":"discovery"},
              {"record_id":"b","world_cluster_id":"W","split":"confirmation"}]
        with self.assertRaises(ValueError): validate_split_records(rows)
    def test_exposed_validation_blocked(self):
        with self.assertRaises(ValueError):
            validate_split_records([{"record_id":"a","world_cluster_id":"W","split":"validation","previously_exposed":True}])
    def test_history_is_discovery_not_holdout(self):
        rows=[{"record_id":"a","world_cluster_id":"W","split":"history"},
              {"record_id":"b","world_cluster_id":"W","split":"discovery"}]
        self.assertEqual(validate_split_records(rows)["world_clusters"],1)
    def test_duplicate_record_blocked(self):
        with self.assertRaises(ValueError):
            validate_split_records([{"record_id":"a","world_cluster_id":"W","split":"discovery"}]*2)


class PlanningTests(unittest.TestCase):
    def test_planned_counts(self):
        import yaml
        cfg=yaml.safe_load((ROOT/'config/study.yaml').read_text())
        result=planned_counts(cfg)
        self.assertEqual(result["per_model_total"],29928)
        self.assertEqual(result["all_models_total"],89784)
    def test_cost_uses_gpu_count(self):
        result=estimate_gpu_hours([{"profile":"TEST_ONLY","gpus_per_worker":2,"forward_count":100,
                                    "seconds_per_forward":30,"shards":2,"load_seconds":300}])
        self.assertEqual(result["total_gpu_hours"],2.0)
        self.assertFalse(result["queue_wait_included"])
    def test_cost_nan_blocked(self):
        with self.assertRaises(ValueError):
            estimate_gpu_hours([{"gpus_per_worker":1,"forward_count":10,"seconds_per_forward":float('nan'),"shards":1,"load_seconds":1}])
    def test_walltime(self):
        self.assertEqual(walltime(2.5),'02:30:00')


def test_wave_fixture(base: Path) -> dict:
    for name in ('authority.txt','gate.json','shards.json'):
        (base/name).write_text('TEST_FIXTURE_NOT_REAL_AUTHORIZATION\n')
    return {
      "status":"READY_FROZEN_WAVE","authorization_status":"CONFIRMED_EXISTING_OR_CURRENT_USER",
      "authorization_evidence":str(base/'authority.txt'),"authorization_sha256":sha256_file(base/'authority.txt'),
      "site_limits_verified":True,"account":"TEST","partition":"TEST","qos":"TEST",
      "total_gpu_hours_ceiling":100,"spent_gpu_hours":0,"reserved_gpu_hours_outside_wave":0,
      "concurrent_gpu_ceiling":4,"outside_wave_gpu_slots":0,
      "site_array_running_tasks_ceiling":4,"outside_wave_running_task_slots":0,
      "site_submitted_tasks_ceiling":20,"outside_wave_submitted_tasks":0,"site_max_wall_hours":6,
      "arrays":[{"name":"TEST","model_id":"qwen35_9b","shards":8,"parallelism":4,"gpus":1,
        "cpus":4,"mem_gb":64,"wall_hours":3,"scientific_gate_pass":True,"smoke_pass":True,
        "gate_file":str(base/'gate.json'),"gate_sha256":sha256_file(base/'gate.json'),
        "shard_table":str(base/'shards.json'),"shard_table_sha256":sha256_file(base/'shards.json'),
        "dependencies":[12345]}]}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.plan=test_wave_fixture(self.base)
    def tearDown(self): self.tmp.cleanup()
    def test_valid_wave_reservation(self):
        self.assertEqual(validate_wave(self.plan)["reserved_new_gpu_hours"],24)
    def test_unresolved_authority_blocks(self):
        self.plan['authorization_status']='UNRESOLVED'
        with self.assertRaises(ValueError): validate_wave(self.plan)
    def test_other_arrays_count_toward_global_cap(self):
        self.plan['outside_wave_gpu_slots']=1
        with self.assertRaises(ValueError): validate_wave(self.plan)
    def test_reserved_budget_includes_pending(self):
        self.plan['reserved_gpu_hours_outside_wave']=80
        with self.assertRaises(ValueError): validate_wave(self.plan)
    def test_gate_hash_blocks(self):
        self.plan['arrays'][0]['gate_sha256']='wrong'
        with self.assertRaises(ValueError): validate_wave(self.plan)
    def test_afterany_not_inference_gate(self):
        self.plan['arrays'][0]['dependency_type']='afterany'
        with self.assertRaises(ValueError): validate_wave(self.plan)
    def test_submission_command_spaces_are_arguments(self):
        cmd=commands(self.plan, self.base/'worker.sh', self.base/'repo with spaces', self.base/'run')[0][1]
        self.assertIn('--dependency=afterok:12345',cmd)
        self.assertIn('--array=0-7%4',cmd)
        self.assertIn(str(self.base/'repo with spaces'),cmd)
        self.assertEqual(cmd[0],'sbatch')


def package_fixture(base: Path) -> tuple[Path,Path,dict]:
    src=base/'stage'; src.mkdir()
    for name in COPY_FILES:
        (src/name).write_text('TEST TEMPLATE\n',encoding='utf-8')
    raw={"model_id":"TEST_MODEL","model_revision":"test-revision","request_id":"r0",
         "world_cluster_id":"world-test","experiment":"TEST_ONLY","split":"discovery",
         "prompt":"Synthetic test prompt","raw_response":"{\"value\":0}"}
    (src/'02_CLAIM_EVIDENCE_MATRIX.json').write_text(json.dumps({"claims":[{"status":"TEST_ONLY","request_refs":[{"model_id":"TEST_MODEL","request_id":"r0"}]}]}))
    (src/'03_WORLD_DIAGNOSIS.csv').write_text('model_id,world_cluster_id\nTEST_MODEL,world-test\n')
    (src/'05_MATCHED_CASES.jsonl').write_text(json.dumps({"case_id":"TEST_ONLY","requests":[raw]})+'\n')
    (src/'07_MECHANISTIC_EFFECTS.csv').write_text('status,donor_model_id,donor_request_id,recipient_model_id,recipient_request_id\nNOT_RUN,,,,\n')
    response_path=base/'raw.jsonl'; response_path.write_text(json.dumps(raw)+'\n')
    return src,response_path,raw


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.src,self.responses,self.raw=package_fixture(self.base)
    def tearDown(self): self.tmp.cleanup()
    def test_full_archive_and_hashes(self):
        out=self.base/'out.zip'
        result=build_package(self.src,self.responses,out,part_mib=0.001)
        self.assertEqual(result['responses'],1)
        self.assertEqual(result['missing_evidence_refs'],0)
        self.assertEqual(result['scientific_status'],'NOT_CERTIFIED_BY_PACKAGER')
        with zipfile.ZipFile(out) as z:
            lines=z.read('SHA256SUMS.txt').decode().splitlines()
            import hashlib
            for line in lines:
                expected,name=line.split('  ',1)
                self.assertEqual(expected,hashlib.sha256(z.read(name)).hexdigest())
            rows=gzip.decompress(z.read('09_FULL_RESPONSES/responses_0000.jsonl.gz')).decode().splitlines()
            self.assertEqual(json.loads(rows[0])['raw_response'],self.raw['raw_response'])
    def test_missing_ref_blocks_package(self):
        (self.src/'02_CLAIM_EVIDENCE_MATRIX.json').write_text(json.dumps({"request_refs":[{"model_id":"TEST_MODEL","request_id":"missing"}]}))
        with self.assertRaises(ValueError): build_package(self.src,self.responses,self.base/'bad.zip')
        self.assertFalse((self.base/'bad.zip').exists())
    def test_changed_example_blocks_package(self):
        r=copy.deepcopy(self.raw); r['raw_response']='fabricated example'
        (self.src/'05_MATCHED_CASES.jsonl').write_text(json.dumps({"requests":[r]})+'\n')
        with self.assertRaises(ValueError): build_package(self.src,self.responses,self.base/'bad.zip')
    def test_duplicate_response_blocks(self):
        self.responses.write_text((json.dumps(self.raw)+'\n')*2)
        with self.assertRaises(ValueError): build_package(self.src,self.responses,self.base/'bad.zip')
    def test_existing_zip_not_overwritten(self):
        out=self.base/'out.zip'; out.write_text('old')
        with self.assertRaises(ValueError): build_package(self.src,self.responses,out)
        self.assertEqual(out.read_text(),'old')


if __name__ == '__main__': unittest.main()
