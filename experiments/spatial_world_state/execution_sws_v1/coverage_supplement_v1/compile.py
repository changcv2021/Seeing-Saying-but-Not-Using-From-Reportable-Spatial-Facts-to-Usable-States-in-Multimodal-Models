"""Fixed source-only E5/E7/E9 supplements; never select by model output."""
import copy
import sys
from collections import Counter
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common_auto_v2 import *
from real_processor_v1 import verify
from real_compile_v1 import runtime_files
from real_design_v1 import SYSTEM, branch_spec, fact_value, question
from data_continuation_v1.prepare import source_guard
import e7_design_v1

BATCHES = dict(E7='e7_typed_expansion_v1_20260910', E5='e5_sequence_supplement_v1_20260910',
               E9='e9c_controls_v1_20260910', SETUP='typed_supplement_setup_v1_20260910')


def contract(schema):
    value = ('a nonnegative JSON integer, NOT a quoted string' if schema['domain'] == 'count'
             else 'one of these exact strings: ' + json.dumps(schema['values']))
    value += '; use the JSON literal null, not the string "null", when undetermined'
    if schema['kind'] == 'facts':
        return ('Return one JSON object with the single key "facts", whose value is a list of objects. '
                'Each object has exactly "query_id" and "value". Include each query ID exactly once: '
                + json.dumps(schema['query_ids']) + '. Each value is ' + value + '. No other keys, explanations or markdown.')
    if schema['kind'] == 'verdict':
        return 'Return exactly one JSON object with key "verdict" and value "SUPPORTED", "CONTRADICTORY", or "UNKNOWN".'
    return ('Return exactly one JSON object with key "value". Its value is ' + value
            + '. Even an undetermined answer must use the object {"value":null}, not bare null.')


class Batch:
    def __init__(self, c, root, kind):
        self.c, self.root, self.kind = c, root, kind
        self.name = BATCHES[kind]; self.requests = []; self.gold = []; self.matched = []; self.panels = []

    def emit(self, w, condition, schema, expected, body, media, family, *, role='NEUTRAL', target='S0', proof=None):
        r = dict(experiment='E9' if self.kind == 'SETUP' else self.kind, condition=condition,
                 world_cluster_id=w, split='symbolic_control' if self.kind in ('E9', 'SETUP') else 'discovery',
                 logical_bundle_id=digest([self.name, w]), sample_family=family,
                 source_type='SYNTHETIC_SYMBOLIC' if self.kind in ('E9', 'SETUP') else 'CONTROLLED_SOURCE_EXTENSION',
                 payload=dict(system=SYSTEM, text=body + '\nOUTPUT CONTRACT: ' + contract(schema), media=media),
                 schema=schema, requested_tokens=512, information_role=role, target_state=target,
                 queried_fact_id='q1', view_variant='FULL' if media else 'NO_MEDIA', wording='FIXED_V1',
                 models=self.c['models'], review_status=self.c['review']['default_review_status'],
                 scientific_review_grade='AUTO_ONLY_PROVISIONAL')
        rid = 'sws_supp_' + digest([self.name, w, r['payload'], schema])[:24]
        r['request_id'] = rid; r['model_independent_request_hash'] = digest(r)
        self.requests.append(r)
        self.gold.append(dict(request_id=rid, world_cluster_id=w, expected=expected, proof=proof,
                              ordinary_input_gold_leak=False, source_type=r['source_type']))
        return rid

    def publish(self, sources):
        out = self.root / 'batches' / self.name
        rs = self.requests
        assert len({r['request_id'] for r in rs}) == len(rs)
        worlds = sorted({r['world_cluster_id'] for r in rs}, key=lambda w: digest([self.c['seed'], 'SUPPLEMENT_SHARD', w]))
        save(out / 'public_inputs/requests.jsonl', rs, 'jsonl')
        save(out / 'private_gold/request_gold.jsonl', self.gold, 'jsonl')
        save(out / 'private_gold/matched_structure.jsonl', self.matched, 'jsonl')
        save(out / 'private_gold/world_panel.jsonl', self.panels, 'jsonl')
        aliases = [dict(request_id=r['request_id'], experiment=r['experiment'], condition=r['condition'],
                        wording=r.get('wording', 'FIXED_V1'), view_variant=r.get('view_variant', 'FULL')) for r in rs]
        save(out / 'private_gold/logical_aliases.jsonl', aliases, 'jsonl')
        # Whole world / own-response DAG stays on one worker; no cross-model barriers.
        n_shards = 1 if self.kind == 'SETUP' else 4
        shards = []
        for sid in range(n_shards):
            ws = worlds[sid::n_shards]; rr = [r for r in rs if r['world_cluster_id'] in ws]
            path = out / f'public_inputs/shard_{sid:03}.jsonl'; save(path, rr, 'jsonl')
            shards.append(dict(shard=sid, worlds=ws, requests=len(rr), request_file=entry(path)))
        save(out / 'manifest/shards.json', shards)
        code = runtime_files(self.c)
        code += [entry(CODE / n) for n in ('e7_design_v1.py', 'e7_worker_v1.py', 'e7_processor_v1.py', 'e7_score_v1.py')]
        code += [entry(HERE / n) for n in ('compile.py', 'runner.py', 'job.sh', 'analysis.py', 'submit.py', 'scorer_adapter.py')]
        public = [entry(out / n) for n in ('public_inputs/requests.jsonl', 'manifest/shards.json')] + [r['request_file'] for r in shards]
        private = [entry(out / 'private_gold' / n) for n in ('request_gold.jsonl', 'matched_structure.jsonl', 'world_panel.jsonl', 'logical_aliases.jsonl')]
        save(out / 'manifest/REQUEST_LOCK.json', dict(batch=self.name, code=code, public_inputs=public,
            private_inputs=private, source_refs=sources, models=self.c['models'], source_selection='ALL_PREVIOUSLY_FROZEN_WORLDS_NO_OUTPUT_ACCESS',
            semantic_retries=0, human_gate=False, scientific_grade='AUTO_ONLY_PROVISIONAL',
            output_cap=512, parser='SWS_V3_SCORING_VIEW_PLUS_ORIGINAL_STRICT',
            source_truth_boundary='CONTROLLED_COUNT_EXTENSION_NOT_NATIVE_L4_OR_PIXEL_COMPLETE_FUSION',
            prefix_policy='LOGICAL_SHARED_PREFIX' if self.kind == 'E7' else None))
        result = dict(batch=self.name, kind=self.kind, status='FROZEN_NOT_INFERRED', worlds=len(worlds),
                      requests_per_model=len(rs), shards=shards, source_refs=sources,
                      counts=dict(Counter(r['condition'] for r in rs)))
        save(out / 'reports/COMPILE_ACCEPTANCE.json', result)
        return result


def e7(b, panel):
    e7_design_v1.BATCH = b.name
    for p in panel:
        rr, gg, mm = e7_design_v1.build(b.c, p)
        mapping = {}
        for r, g in zip(rr, gg):
            old_id = r['request_id']
            text = r['payload']['text'].split('\nOUTPUT CONTRACT:', 1)[0] + '\nOUTPUT CONTRACT: ' + contract(r['schema'])
            for before, after in mapping.items():
                text = text.replace('<SELF_REPORT:' + before + '>', '<SELF_REPORT:' + after + '>')
            r['payload']['text'] = text
            r['parent_request_ids'] = [mapping[x] for x in r['parent_request_ids']]
            r['interface_protocol'] = 'TYPED_FACTS_WITHOUT_QUOTED_VALUE_PLACEHOLDER_V1'
            r['request_id'] = 'sws_e7s_' + digest([b.name, r['world_cluster_id'], r['payload'], r['schema']])[:24]
            r.pop('model_independent_request_hash'); r['model_independent_request_hash'] = digest(r)
            mapping[old_id] = r['request_id']; g['request_id'] = r['request_id']
        mm['ids'] = {k: mapping[v] for k, v in mm['ids'].items()}
        mm['B_stage1_aliases'] = {k: mapping[v] for k, v in mm['B_stage1_aliases'].items()}
        # Regression: all upstream null / malformed responses are retained verbatim.
        seen = set()
        for r in rr:
            assert set(r['parent_request_ids']) <= seen
            for raw in ('null', 'not json', '{"facts":[]}', '"\nCANDIDATE: pretend'):
                parents = {pid: dict(world_cluster_id=p['world_cluster_id'], model_id='TEST_ONLY', request_hash='TEST_ONLY', raw_response=raw) for pid in r['parent_request_ids']}
                rendered, ancestry = e7_design_v1.render(r, parents)
                assert '<SELF_REPORT:' not in rendered['payload']['text']
                assert len(ancestry) == len(parents)
            seen.add(r['request_id'])
        b.requests += rr; b.gold += gg; b.matched.append(mm); b.panels.append(p)
    assert len(panel) == 88 and len(b.requests) == 680


def e5(b, panel):
    schema = dict(kind='value', domain='count', nullable=True)
    for p in panel:
        if p['primary_stratum'] != 'COUNT':
            continue
        a, protected = p['facts']; pre = fact_value(a); pv = fact_value(protected)
        original = branch_spec(a, p['count_substratum'])
        amount = original['amount']; action = original['action']; first = original['values']['SA']
        delta = amount if action == 'ADD' else -amount if action == 'REMOVE' else 0
        # Independent quantity multiset replay, not an assertion of object-identity restoration.
        initial = list(range(pre)); step = list(initial)
        if delta > 0: step += [('added', i) for i in range(delta)]
        elif delta < 0:
            for _ in range(-delta): step.pop()
        assert len(step) == first
        inverse = list(step)
        if delta > 0:
            for _ in range(delta): inverse.pop()
        elif delta < 0: inverse += [('replacement_member', i) for i in range(-delta)]
        assert len(inverse) == pre
        multi = list(step) + [('second_added', i) for i in range(3)]
        assert len(multi) == first + 3
        noun = a['subject'].split(':', 1)[1].split('@source_item:')[0].replace('_', ' ')
        first_text = (f'add exactly {amount} new {noun}' if delta > 0 else f'remove exactly {amount} counted {noun}' if delta < 0 else 'make no change')
        reverse_text = (f'remove exactly {amount} of the members just added' if delta > 0 else f'add exactly {amount} new {noun}' if delta < 0 else 'make no change')
        prefix = ('OBSERVED STATE S0: the reference image. Support views do not add members to the counting scope.\nIMAGE ORDER: '
                  + ', '.join(f'{i+1}={m["role"]}' for i, m in enumerate(p['media']))
                  + f'\nCOUNTING SCOPE: {noun} counted in the reference image, not a whole-room census.\n')
        ids = {}
        for sequence, second_text, final in [('INVERSE', reverse_text, pre), ('TWO_STEP', 'add exactly 3 new ' + noun, first + 3)]:
            actions = (f'AUTHORIZED HYPOTHETICAL BRANCH S2, starting independently from S0:\nSTEP 1: {first_text}.\n'
                       f'STEP 2: {second_text}.\nThe two steps are sequential within S2. The recorded S0 and all other categories stay unchanged. '
                       'Only quantities are queried; no original object-identity restoration is asserted. Do not recount occlusion after this symbolic edit.\n')
            for slot, f, target, value in [('TARGET', a, 'S2', final), ('BASE', a, 'S0', pre), ('PROTECTED', protected, 'S2', pv)]:
                cond = sequence + '_' + slot
                ids[cond] = b.emit(p['world_cluster_id'], cond, schema, dict(value=value),
                    prefix + actions + 'TARGET: ' + target + '\nQUERY: ' + question(f, target), p['media'],
                    'COUNT_CONTROLLED_SEQUENCE', role='AUTHORIZED_INTERVENTION', target=target,
                    proof=dict(source_fact_ids=[a['fact_id'], protected['fact_id']], pre=pre, first=first,
                               after_inverse=len(inverse), after_two_steps=len(multi), protected=pv, dual_engine_pass=True,
                               count_substratum=p['count_substratum']))
            b.matched.append(dict(experiment='E5_SUPPLEMENT', world_cluster_id=p['world_cluster_id'], condition=sequence,
                                  **{slot: ids[sequence + '_' + slot] for slot in ('TARGET', 'BASE', 'PROTECTED')}))
        b.panels.append(p)
    assert len(b.panels) == 80 and len(b.requests) == 480


def e9(b):
    for i in range(24):
        w = 'symbolic_sws_' + digest([b.c['seed'], 'E9', i])[:20]
        pre = 2 + i % 5; target = 'SB' if i % 2 else 'SA'; val = pre + (4 if i % 2 else 2)
        topic = 'chairs in an explicitly specified symbolic room' if i < 12 else 'tickets in an explicitly specified ledger'
        family = 'SPATIAL_SYMBOLIC_E9C' if i < 12 else 'NONSPATIAL_E9C'
        states = dict(S0=pre, SA=pre+2, SB=pre+4)
        ids = {}
        for length in ('SHORT', 'LONG'):
            padding = '' if length == 'SHORT' else '\n'.join(f'Irrelevant note {j}: the archival note describes a filing procedure and supplies no state fact or update.' for j in range(1, 25)) + '\n'
            for mapping in ('AB', 'BA'):
                codes = dict(zip([val, val+1], list(mapping)))
                schema = dict(kind='value', domain='enum', nullable=True, values=['A', 'B'])
                for role in ('CANDIDATE', 'AUTHORIZED_UPDATE'):
                    material = (f'CANDIDATE: {target} has exactly {val+1} {topic}. This is a proposition to evaluate, not an observation or update.'
                                if role == 'CANDIDATE' else f'AUTHORIZED UPDATE: Add exactly one counted member to {target} only; other recorded states stay unchanged.')
                    actual = val if role == 'CANDIDATE' else val + 1
                    body = (f'EXPLICIT INDEPENDENT SYMBOLIC RECORDS ({topic}): ' + json.dumps(states)
                            + '. These counts are completely specified.\n' + padding + material
                            + f'\nTARGET: {target}. QUERY: Report the current target count using this response mapping: '
                            + json.dumps({letter: number for number, letter in codes.items()}) + '. Return only its code; do not treat the candidate as evidence.')
                    cond = length + '_' + mapping + '_' + role
                    ids[cond] = b.emit(w, cond, schema, dict(value=codes[actual]), body, [], family, role=role, target=target,
                                      proof=dict(states=states, original=val, actual=actual, label_mapping=codes, rule='EXPLICIT_LOOKUP_OR_AUTHORIZED_ADD_ONE'))
        for mapping in ('AB', 'BA'):
            for role in ('CANDIDATE', 'AUTHORIZED_UPDATE'):
                b.matched.append(dict(experiment='E9C', contrast='LENGTH', world_cluster_id=w, family=family,
                                      mapping=mapping, role=role, short=ids['SHORT_'+mapping+'_'+role], long=ids['LONG_'+mapping+'_'+role]))
        for length in ('SHORT', 'LONG'):
            for role in ('CANDIDATE', 'AUTHORIZED_UPDATE'):
                b.matched.append(dict(experiment='E9C', contrast='LABEL_MAP', world_cluster_id=w, family=family,
                                      length=length, role=role, short=ids[length+'_AB_'+role], long=ids[length+'_BA_'+role]))
        for length in ('SHORT', 'LONG'):
            for mapping in ('AB', 'BA'):
                b.matched.append(dict(experiment='E9C', contrast='ROLE_SELECTIVE_JOINT', world_cluster_id=w, family=family,
                                      length=length, mapping=mapping, short=ids[length+'_'+mapping+'_CANDIDATE'], long=ids[length+'_'+mapping+'_AUTHORIZED_UPDATE']))
        typ = i % 3
        schema = dict(kind='value', domain='count', nullable=True)
        if typ == 0:
            cond='COPY_NULL'; body='SYMBOLIC RECORD: {"target":null}. Copy the target field without inferring another value.'; expected=dict(value=None)
        elif typ == 1:
            cond='SINGLE_STATE_LOOKUP'; body=f'EXACT SYMBOLIC RECORD: only state X is supplied. X contains exactly {val} members. TARGET: X. Report the count.'; expected=dict(value=val)
        else:
            cond='PARTIAL_BOUND_CONTRADICTION'; body=f'PARTIAL SYMBOLIC EVIDENCE: target count is at least {val}, with no upper bound. CANDIDATE: the count is exactly 0. Evaluate the claim.'
            schema=dict(kind='verdict', domain='count', nullable=True); expected=dict(verdict='CONTRADICTORY')
        b.emit(w, cond, schema, expected, body, [], family, proof=dict(rule='EXPLICIT_SYMBOLIC_RECORD', source_world_index=i))
    assert len(b.requests) == 216


def setup_batch(b):
    cases = [
        (dict(kind='facts', domain='count', nullable=True, query_ids=['q1','q2']), dict(facts={'q1':2,'q2':0}), 'EXACT SYMBOLIC RECORDS: q1=2; q2=0. Copy each value.'),
        (dict(kind='facts', domain='count', nullable=True, query_ids=['q0','qA','qB','qP']), dict(facts={'q0':1,'qA':0,'qB':4,'qP':2}), 'EXACT SYMBOLIC RECORDS: q0=1; qA=0; qB=4; qP=2. Copy each value.'),
        (dict(kind='facts', domain='enum', values=['YES','NO'], nullable=True, query_ids=['q1','q2']), dict(facts={'q1':'YES','q2':'NO'}), 'EXACT SYMBOLIC RECORDS: q1=YES; q2=NO. Copy each value.'),
        (dict(kind='value', domain='count', nullable=True), dict(value=None), 'EXACT SYMBOLIC RECORD: target=null. Copy the target field.'),
    ]
    for i, (s, expected, text) in enumerate(cases):
        b.emit('setup_supplement_'+str(i), 'SETUP_'+str(i), s, expected, text, [], 'SYMBOLIC_INTERFACE_SETUP', proof=dict(rule='EXPLICIT_RECORD'))


def main():
    a=arguments(__doc__).parse_args(); c, root=setup(a)
    audit=source_guard(); panels=[]; refs=[]
    for i in range(1,5):
        src=root/'batches'/f'ca_source_d{i:02}_20260910'
        lock=load(src/'manifest/REQUEST_LOCK.json'); verify(lock['code']+lock['public_inputs']+lock['private_inputs'])
        panels += list(rows(src/'private_gold/world_panel.jsonl'))
        refs += [entry(src/'manifest/REQUEST_LOCK.json'), entry(src/'private_gold/world_panel.jsonl')]
    assert len(panels)==88 and len({p['world_cluster_id'] for p in panels})==88
    assert all(p['split']=='discovery' for p in panels)
    result=[]
    for kind, fn in [('SETUP',setup_batch),('E7',e7),('E5',e5),('E9',e9)]:
        b=Batch(c,root,kind)
        fn(b,panels) if kind in ('E7','E5') else fn(b)
        result.append(b.publish(refs if kind in ('E7','E5') else [entry(root/'manifest/E9_request_lock.json')]))
    old_e7=sum(1 for _ in rows(root/'batches/e7_d01_v1_20260910/public_inputs/requests.jsonl'))
    old_e9=sum(1 for _ in rows(root/'public_inputs/E9/requests.jsonl'))
    assert old_e7+680<=960 and old_e9+216<=1000
    save(root/'preparation/coverage_supplement_v1_20260910/ACCEPTANCE.json',dict(status='PASS_COMPILED_NOT_INFERRED',
        batches=result, source_guard=dict(audit), no_outcome_selection=True, job_id=os.environ['SLURM_JOB_ID'],
        E7_unique_worlds=88,E7_world_target=96,E7_generations_old_plus_new=old_e7+680,
        E5_added_per_world=6,E9_generations_old_plus_new=old_e9+216,
        remaining_gaps=['E7_8_WORLD_SHORTFALL_NO_FILLER_SELECTION','NATIVE_TIME_BRANCH','PIXEL_COMPLETE_MULTIVIEW_NECESSITY',
                        'GLOBAL_UNEXPOSED_HOLDOUT_RECONCILIATION','M2_MATCHED_INTERVENTION_MANIFEST'],
        historical_raw_gold_scores_read_only=True))
    print(json.dumps(dict(status='SUPPLEMENTS_FROZEN',batches=[{k:r[k] for k in ('batch','worlds','requests_per_model')} for r in result])),flush=True)


if __name__=='__main__':main()
