"""Source-only balanced query-contract factorial. No prediction reads."""
from v2_common import *
from state_contracts import Program,Action
def main():
    a=cli(__doc__).parse_args();c,root=context(a)
    from data_continuation_v1.prepare import source_guard
    guard=source_guard();src=OLD_ROOT/'batches/B2'
    ps=list(rows(src/'private_gold/world_panel.jsonl'))
    originals={r['world_cluster_id']:r for r in rows(src/'public_inputs/requests.jsonl') if r['condition']=='FINAL'}
    assert len(ps)==len(originals)==96
    semantic={'S0':'before Action 1 and before Action 2','S1':'immediately after Action 1 but before Action 2','S2':'immediately after Action 2 has acted on the result of Action 1'}
    definitions='STATE DEFINITIONS: S0 is before both actions. S1 is immediately after Action 1 and before Action 2. S2 is immediately after Action 2, applied to S1.'
    reqs=[];gold=[]
    for p in ps:
        prog=Program(p['program']['s0'],Action(**p['program']['a1']),Action(**p['program']['a2']),p['program']['source_type'])
        assert (prog.s1,prog.s2)==(p['s1'],p['s2'])
        base=originals[p['world_cluster_id']];prefix=base['payload']['text'].split('\nTARGET:')[0]
        output='\nOUTPUT CONTRACT:'+base['payload']['text'].split('\nOUTPUT CONTRACT:',1)[1]
        for target,val in [('S0',prog.s0),('S1',prog.s1),('S2',prog.s2)]:
            prompts={
                'T1':'TARGET: '+target+'. QUERY: What is the value of register R at the target state?',
                'T2':'QUERY: What is the value of register R '+semantic[target]+'?',
                'T3':definitions+'\nTARGET: '+target+'. QUERY: What is the value of register R at the target state?',
                'T4':definitions+'\nTARGET: '+target+'. QUERY: What is the value of register R at the target state?\nDo not return '+('S2' if target!='S2' else 'S1')+'. Return '+target+' only.'}
            for wording,q in prompts.items():
                r=request(base,'W1_TARGET',wording+'_'+target,prefix+'\n'+q+output,target)
                reqs.append(r);gold.append(dict(request_id=r['request_id'],world_cluster_id=p['world_cluster_id'],expected=dict(value=val),proof=p,wording=wording,target=target))
    protocol=dict(design='FULL_FACTORIAL_96_PROGRAMS_X_4_CONTRACTS_X_3_TARGETS',states=list(semantic),
        implementation_choice='Guide requests balanced S0/S1/S2: use every target for every program and wording, not an accuracy-selected subset.',
        primary='T1 versus T2 and T3 for S1; T4 repetition secondary; distinguish S1 != S2',
        uncertainty_cluster='program_family (16 independent generation families); also report 96 programs',
        program_split='Historical memberships retained as history, no fresh confirmation claim',
        target_metadata_fixed_only_in_new_requests=True,semantic_retry=0,selection_guard=guard)
    publish('W1_TARGET',reqs,gold,ps,protocol,[entry(src/'private_gold/world_panel.jsonl'),entry(src/'public_inputs/requests.jsonl')],Path(__file__))
if __name__=='__main__':main()
