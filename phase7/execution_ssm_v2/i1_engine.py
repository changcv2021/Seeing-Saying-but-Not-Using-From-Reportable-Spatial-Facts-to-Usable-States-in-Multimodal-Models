"""Frozen engine subclass: reuse the tested full-prefix replay, add v2 semantic anchors."""
from v2_common import *
sys.path.insert(0,str(SPACE/'phase6/execution_ssm_i2_v1'))
from engine import Engine

class I1Engine(Engine):
    def __init__(self,c,key,dest):
        super().__init__(c,key,dest)
        relative=load(ROOT/'I1/manifest/PROTOCOL.json')['relative_depths']
        self.depths=[round(x*(len(self.layers)-1)) for x in relative]
        assert len(set(self.depths))==8
        self.config.update(relative_depths=relative,actual_layers=self.depths,engine='SSM_V2_I1_BLOCK_OUTPUT',
                           engine_reference=entry(SPACE/'phase6/execution_ssm_i2_v1/engine.py'))
        self.config['layers']=[dict(index=i,type=getattr(self.layers[i],'block_type',None)) for i in self.depths]
    def process(self,r):
        inputs,pres=super().process(r)
        old=pres['anchors'];names={'P_CONTEXT_END':'P_PRE','P_A1_END':'P_A1','P_A2_END':'P_A2','P_QUERY':'P_QUERY'}
        pres['anchors']={name:old[key] for name,key in names.items()}
        assert list(pres['anchors'].values())==sorted(pres['anchors'].values())
        return inputs,pres
