"""Evidence-linked work-in-progress report, not a premature final review ZIP."""
from bc_common import *

def main():
    a=cli(__doc__).parse_args();c,sws,out=context(a)
    if a.dry_run:print('Create report skeleton and explicit outstanding evidence ledger.');return
    dest=out/'P9'
    save(dest/'REPORT_TEMPLATE_CN.md',
        '# SpaceConflict 行为证据闭合报告（进行中，非最终结论）\n\n'
        '## RQ1：完整 failure landscape\n\n复用既有 E0，不新跑 test。按模型、L1–L4、S/C/U、pair 分层。\n\n'
        '## RQ2：候选陈述是否额外破坏事实\n\n依据 P1_E2 与 C1：逐 world 的 neutral/false/sham/true/protected，报告条件化分母与 CI。\n\n'
        '## RQ3：合法更新失败在哪一环\n\n依据 P2_E5 和新增 e5_measurement_v1：初始事实、两步动作、中间状态与最终三端点。缺项不能推断。\n\n'
        '## RQ4：多状态保持与选择\n\n依据 E8、P6 与 C1 非退化状态集合。二元关系或 oracle 高分不作内部机制证据。\n\n'
        '## RQ5：泛化边界\n\nC1 尚须实际完成三模型推理。计数小面板不能替代 non-count、多视图必要性、原生时间或真实 observation 的证据。\n\n'
        '## 反例与限制\n\n保留零效应、负效应、模型差异、措辞敏感性、invalid/null/not_run 和 NOT_DIAGNOSABLE。人工审核按研究者豁免，AUTO_ONLY_PROVISIONAL。\n\n'
        '## 未完成工作\n\n此模板不是最终报告；完成资格、补测、统计和原始响应索引闭合后，才生成指南规定的 REVIEW.zip。\n','text')
    claims=[dict(claim_id=k,claim=v,status='UNRESOLVED',confirmation_status='DISCOVERY',evidence_tables=[],raw_request_ids=[],
        counterevidence=[],remaining_explanations=['PENDING_PAIRED_ANALYSIS_AND_HELDOUT_CONFIRMATION']) for k,v in [
        ('H1','False candidate causes more unlicensed fact change than same-value sham'),
        ('H2','Licensed update can fail despite correct initial fact and action reports'),
        ('H3','Updated target can coexist with damage to base or protected facts'),
        ('H4','Nondegenerate state selection can fail despite correct joint-state reports'),
        ('H5','Behavior generalizes beyond count when source-qualified controls exist')]]
    save(dest/'CLAIM_EVIDENCE_TEMPLATE.json',claims)
    save(dest/'ACCEPTANCE.json',dict(status='TEMPLATE_READY_NOT_FINAL_REPORT',code=entry(__file__),job_id=os.environ['SLURM_JOB_ID'],final_zip_created=False))
    print('REPORT_TEMPLATE_READY_NOT_FINAL',flush=True)

if __name__=='__main__':main()
