"""Canonical state serialization shared by all supervised levels."""
import json

RELATION_VARIABLES={'LEFT_OF':'horizontal_relation','RIGHT_OF':'horizontal_relation',
 'ABOVE':'vertical_relation','BELOW':'vertical_relation','FRONT_OF':'depth_relation','BEHIND':'depth_relation',
 'BEFORE':'temporal_order','AFTER':'temporal_order','INSIDE':'containment','CONTAINS':'containment'}
VALUE_VARIABLES={'COUNT':'count','EXISTS_IN_WORLD':'existence','VISIBLE_IN_FRAME':'visibility','SAME_INSTANCE':'identity'}

def validate_state(state):
    if not isinstance(state,dict):raise ValueError('STATE_OBJECT')
    if set(state)-{'entities','variable','frame','value'} or not {'entities','variable','value'}<=set(state):raise ValueError('STATE_FIELDS')
    if not isinstance(state['entities'],list) or not state['entities'] or any(not isinstance(x,str) or not x for x in state['entities']):raise ValueError('STATE_ENTITIES')
    if state['variable'] not in set(RELATION_VARIABLES.values())|set(VALUE_VARIABLES.values()):raise ValueError('STATE_VARIABLE')
    if state['variable']=='count':
        if type(state['value']) is not int or state['value']<0:raise ValueError('STATE_COUNT')
    elif state['variable'] in ('existence','visibility','identity'):
        if type(state['value']) is not bool:raise ValueError('STATE_BOOLEAN')
    elif not isinstance(state['value'],str) or RELATION_VARIABLES.get(state['value'])!=state['variable']:raise ValueError('STATE_RELATION')
    if 'frame' in state and (not isinstance(state['frame'],str) or not state['frame']):raise ValueError('STATE_FRAME')
    return True

def canonicalize_state(state):
    validate_state(state)
    return {k:state[k] for k in ('entities','variable','frame','value') if k in state}

def serialize_state(state):
    return '<STATE>\n'+'\n'.join(k+': '+json.dumps(v,ensure_ascii=False) for k,v in canonicalize_state(state).items())+'\n</STATE>'

def parse_state(text):
    if not isinstance(text,str):raise ValueError('STATE_TEXT')
    lines=text.strip().splitlines()
    if len(lines)<2:raise ValueError('STATE_BOUNDARY')
    if lines[0]!='<STATE>' or lines[-1]!='</STATE>':raise ValueError('STATE_BOUNDARY')
    obj={}
    for line in lines[1:-1]:
        k,v=line.split(': ',1)
        if k in obj:raise ValueError('DUPLICATE_FIELD')
        obj[k]=json.loads(v)
    return canonicalize_state(obj)
