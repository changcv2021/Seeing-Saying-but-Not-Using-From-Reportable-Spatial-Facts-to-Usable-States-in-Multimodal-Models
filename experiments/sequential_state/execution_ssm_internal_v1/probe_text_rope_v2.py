"""Use only the separately repaired representation namespace, same frozen probe policy."""
from internal_common import *
def main():
    lock=load(OUT/'manifest/TEXT_ROPE_REPAIR_V2.json')
    for ref in lock['code']:check(ref)
    src=WAVE_CODE/'probe.py';text=src.read_text()
    for old,new in [("src=out/'representations'/a.model","src=out/'representations_v2'/a.model"),("dest=out/'probes'/a.model","dest=out/'probes_v2'/a.model")]:
        assert text.count(old)==1;text=text.replace(old,new)
    namespace={'__name__':'ssm_probe_text_rope_v2','__file__':str(src)}
    exec(compile(text,str(src),'exec'),namespace);namespace['main']()
if __name__=='__main__':main()
