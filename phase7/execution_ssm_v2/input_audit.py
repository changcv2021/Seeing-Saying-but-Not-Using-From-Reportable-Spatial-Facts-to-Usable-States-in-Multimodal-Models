"""CPU actual-processor audit, including S0-sham positions and rendered visual hashes."""
from collections import defaultdict,Counter
from v2_common import *
def main():
    a=cli(__doc__).parse_args();c,_=context(a);i1=ROOT/'I1';out=i1/'input_audit'
    lk=load(i1/'manifest/INPUT_LOCK.json')
    for ref in lk['public_inputs']:check(ref)
    sys.path.insert(0,str(Path(c['project'])/'src'));sys.path.insert(0,str(Path(c['project'])/'research/state_binding_phase_a1/core_execution_v3'))
    from pipeline_v3 import Pipeline,install_gold_guard
    sys.path.insert(0,str(SPACE/'phase6/execution_ssm_internal_v1'))
    from representations import token_anchors
    guard=install_gold_guard();pipe=Pipeline(dict(c,visual_hash_version='PURE_MEDIA_TENSORS_V3_SHARED_RUNTIME'),'qwen35_9b')
    reqs={r['request_id']:r for r in rows(i1/'public_inputs/requests.jsonl')};panel=list(rows(i1/'public_inputs/panel.jsonl'));records={};checks=[]
    for ci,case in enumerate(panel,1):
        for query,kinds in case['requests'].items():
            vals={};positions={}
            for kind,rid in kinds.items():
                r=reqs[rid];assert set(r['payload'])=={'system','text','media'}
                if rid not in records:
                    batch,pres,_=pipe.process(r);anchors,mapping=token_anchors(pipe,batch,pres,r['payload']['text'])
                    assert all(x is not None for x in anchors.values())
                    rec=dict(request_id=rid,model='qwen35_9b',request_hash=r['model_independent_request_hash'],presentation=pres,input_token_ids=batch['input_ids'][0].tolist(),
                        anchors=anchors,token_alignment=mapping,human_verified=False,review_status='HUMAN_REVIEW_WAIVED_BY_RESEARCHER',raw_status='NOT_ACCESSED')
                    records[rid]=rec
                rec=records[rid];vals[kind]=rec['presentation']['presentation_hash'];positions[kind]=rec['anchors']
            # Same images and order for all three variants, and oracle/sham are both before A1.
            assert len(set(vals.values()))==1
            info=reqs[kinds['INFORMATIVE_S0']]['payload']['text'];sham=reqs[kinds['SAME_VALUE_SHAM']]['payload']['text'];base=reqs[kinds['BASE']]['payload']['text']
            assert info.index('ORACLE INITIAL FACT:')<info.index('ACTION_1:') and sham.index('UNRELATED REGISTER:')<sham.index('ACTION_1:')
            oldf=f'exactly {case["program"]["s0"]}'
            assert oldf in info.split('ACTION_1:')[0] and oldf in sham.split('ACTION_1:')[0]
            il=info.split('ORACLE INITIAL FACT:',1)[1].split('\n',1)[0];sl=sham.split('UNRELATED REGISTER:',1)[1].split('\n',1)[0]
            checks.append(dict(case_id=case['case_id'],world_cluster_id=case['world_cluster_id'],query=query,same_visual_hash=True,
                informative_insertion_tokens=len(pipe.processor.tokenizer.encode('ORACLE INITIAL FACT:'+il,add_special_tokens=False)),
                sham_insertion_tokens=len(pipe.processor.tokenizer.encode('UNRELATED REGISTER:'+sl,add_special_tokens=False)),
                same_numeric_value=True,insertion_before_A1=True,exact_token_length_matching=False,anchors=positions))
        pipe.image_cache.clear()
        if ci%10==0:print(json.dumps(dict(stage='I1_INPUT_AUDIT',cases=ci,requests=len(records))),flush=True)
    save(out/'ACTUAL_PROCESSOR_RECORDS.jsonl',records.values(),'jsonl');csvsave(out/'DONOR_MATCHING_AUDIT.csv',checks)
    save(out/'ACCEPTANCE.json',dict(status='PASS_AUTOMATIC',requests=len(records),cases=len(panel),same_value_visual_and_insertion_checks=len(checks),
        human_verified=False,source_input_lock=entry(i1/'manifest/INPUT_LOCK.json'),actual_records=entry(out/'ACTUAL_PROCESSOR_RECORDS.jsonl'),
        matching=entry(out/'DONOR_MATCHING_AUDIT.csv'),gold_access_audit=guard,limitation='Sham/informative lexical role and token length differ; exact lengths and semantic positions are reported. No output-conditioned padding search.'))
if __name__=='__main__':main()
