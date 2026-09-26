"""Actual shared processor review and researcher-owned checklist. No human approval inferred."""
import html
import time
from collections import defaultdict
from v3common import *
from pipeline_v3 import Pipeline

CHECKS=['pre_visible','target_unique','count_scope_confirmed','action_amount_confirmed','source_gold_replayed',
        'same_underlying_world_mapping_confirmed','model_outputs_hidden_during_review']


def write_page(c,root,cards,requests,gold,presentations):
    out=root/'review'; records=[]; sections=[]
    for card in cards:
        gid=card['group_id']; deferred=card['review_status']=='DEFERRED_REFERENCE_FRAME'
        rr=[r for r in requests if r['group_id']==gid]
        pres=presentations.get(gid,{})
        combined=digest(dict(request_bundle=card.get('draft_request_bundle_sha256'),
                             presentations={k:v['presentation_hash'] for k,v in pres.items()},
                             source_truth=card['source_truth_sha256'],source_proof=card['source_proof_sha256']))
        row=dict(group_id=gid,world_id=card['world_id'],underlying_world_id=card['underlying_world_id'],level=card['level'],
            stratum=card['stratum'],received_snapshot_status=card['received_review_status'],
            new_review_status='DEFERRED_REFERENCE_FRAME' if deferred else 'PENDING_REVIEW',
            reviewer_name='',reviewed_at='',presentation_hash=next(iter(pres.values()))['presentation_hash'] if pres else '',
            review_bundle_sha256=combined,review_page_relative_path='index.html#'+gid,
            **{k:'NOT_APPLICABLE' if k=='action_amount_confirmed' and card['level']=='L1' else '' for k in CHECKS},
            post_no_media_witnesses_confirmed='NOT_APPLICABLE' if card['level']=='L1' or deferred else '',
            conditions_not_eligible='',notes='DEFERRED_BY_V3_PROTOCOL' if deferred else '')
        records.append(row)
        sections.append('<section id="'+gid+'" data-gid="'+gid+'"><h2>'+html.escape(card['world_id']+' — '+card['stratum'])+'</h2>')
        if deferred:
            sections.append('<p>DEFERRED_REFERENCE_FRAME：本轮暂缓，不进入核心，也不要求为它扩大本轮。</p></section>'); continue
        sections.append('<p>底层 world：'+html.escape(card['underlying_world_id'])+'；审核包 SHA256：<code>'+combined+'</code></p>')
        sections.append('<pre>'+html.escape(card['full_media_context'])+'</pre>')
        seen=set()
        for model,p in pres.items():
            if p['presentation_hash'] in seen: continue
            seen.add(p['presentation_hash'])
            sections.append('<p>实际 vision helper 输出；processor do_resize=False；下面分辨率不是上游高清图。纯视觉张量及 grid 已由共享 runner 实际计算并 hash。模型 '+model+'，hash '+p['presentation_hash']+'</p>')
            for i,img in enumerate(p['preview_files']):
                role=card['media'][i]['role']; src=os.path.relpath(img['path'],out)
                sections.append('<figure><figcaption>'+html.escape(f'Image {i+1}: {role}; {img["size"]}')+'</figcaption><a href="'+src+'"><img src="'+src+'"></a></figure>')
            sections.append('<details><summary>实际像素／grid 元数据</summary><pre>'+html.escape(json.dumps(p['visual'],indent=2))+'</pre></details>')
        for r in rr:
            sections.append('<details><summary>'+html.escape(r['condition']+' | '+r['target']+' | '+r['variant']+' | '+r['request_id'])+'</summary><pre>'+html.escape(r['payload']['system']+'\n'+r['payload']['text'])+'</pre></details>')
        private=[gold[r['request_id']] for r in rr]
        sections.append('<details><summary>第二步：核对来源 gold、动作依据与受限证据补全（非模型输入）</summary><pre>'+html.escape(json.dumps(dict(values=card['values'],action=card['action_expected'],source_truth_sha256=card['source_truth_sha256'],source_proof_sha256=card['source_proof_sha256'],private_gold=private),ensure_ascii=False,indent=2))+'</pre><a href="source_replays.jsonl">完整来源回放证据</a></details>')
        sections.append('<p>研究者审核结果：<select data-field="new_review_status">'+''.join('<option>'+s+'</option>' for s in ['PENDING_REVIEW','VERIFIED_FOR_A1','INSUFFICIENT_VISIBLE_EVIDENCE','ACTION_TARGET_UNCLEAR','REFERENCE_FRAME_UNCLEAR','DERIVED_QUERY_ERROR','SOURCE_GOLD_CONFLICT'])+'</select></p>')
        labels={'pre_visible':'实际呈现足以判断 PRE（未见不直接当 0）','target_unique':'查询/动作目标明确且唯一',
                'count_scope_confirmed':'类别、whole scene / reference image 范围已核对','action_amount_confirmed':'动作类型、作用数量、执行一次语义已确认',
                'source_gold_replayed':'已核对来源 PRE/action/POST 和回放证据','same_underlying_world_mapping_confirmed':'底层 world 别名映射已核对',
                'model_outputs_hidden_during_review':'审核时未查看本轮模型预测','post_no_media_witnesses_confirmed':'POST_NO_MEDIA 的两种补全确实都满足动作句；未确认将排除此条件'}
        for field,label in labels.items():
            if card['level']=='L1' and field in ['action_amount_confirmed','post_no_media_witnesses_confirmed']: continue
            sections.append('<label><input type="checkbox" data-field="'+field+'"> '+html.escape(label)+'</label><br>')
        sections.append('<p>其他不合格条件（英文 condition 名，分号分隔）：<input data-field="conditions_not_eligible"></p><p>审核备注：<textarea data-field="notes"></textarea></p></section>')
    csvsave(out/'researcher_records.csv',records)
    save(out/'review_bundle_manifest.json',dict(records=records,source='ACTUAL_SHARED_V3_PROCESSOR',human_review_completed=False,
        request_file_sha256=sha(out/'draft_requests.jsonl'),private_gold_sha256=sha(root/'private_gold/core_draft.jsonl'),
        reviewer_file='researcher_records.csv',image_note='EXACT_HELPER_OUTPUTS_NO_ADDITIONAL_PROCESSOR_RESIZE'))
    js=r'''
const rows = RECORDS;
const checks = CHECK_FIELDS;
document.getElementById('download').onclick = () => {
 const name=document.getElementById('reviewer').value.trim();
 if(!name){alert('请填写实际审核者姓名或账号，不能代签。');return;}
 const updated=rows.map(row=>({...row}));
 for(const row of updated){
  const section=document.getElementById(row.group_id);
  if(row.new_review_status==='DEFERRED_REFERENCE_FRAME')continue;
  section.querySelectorAll('[data-field]').forEach(el=>{row[el.dataset.field]=el.type==='checkbox'?(el.checked?'TRUE':''):el.value;});
  if(row.new_review_status==='VERIFIED_FOR_A1'){
   const missing=checks.filter(k=>row[k]!=='TRUE'&&row[k]!=='NOT_APPLICABLE');
   if(missing.length){alert(row.world_id+' 缺少检查：'+missing.join(', '));return;}
   if(row.level==='L4'&&row.post_no_media_witnesses_confirmed!=='TRUE'){
    row.conditions_not_eligible=[row.conditions_not_eligible,'POST_NO_MEDIA'].filter(Boolean).join(';');
   }
  }
  if(row.new_review_status!=='PENDING_REVIEW'){row.reviewer_name=name;row.reviewed_at=new Date().toISOString();}
 }
 const fields=Object.keys(updated[0]);
 const esc=x=>'"'+String(x??'').replaceAll('"','""')+'"';
 const csv=[fields.map(esc).join(','),...updated.map(r=>fields.map(k=>esc(r[k])).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download='researcher_records.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
'''.replace('RECORDS',json.dumps(records,ensure_ascii=False).replace('<','\\u003c')).replace('CHECK_FIELDS',json.dumps(CHECKS))
    page='''<!doctype html><meta charset="utf-8"><title>SpaceConflict A.1 core v3 研究者审核</title>
<style>body{font:16px sans-serif;margin:30px;max-width:1500px}section{border-top:3px solid #456;margin-top:35px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eee;padding:12px}figure{display:inline-block;width:45%;vertical-align:top}img{max-width:100%}input,textarea,select{font:inherit}textarea{width:90%}details{margin:10px}code{overflow-wrap:anywhere}</style>
<h1>A.1 core v3：研究者实际输入审核</h1>
<p>未包含模型预测。请先看媒体与问题，再展开来源证据核对。真实核心尚未运行。Codex 未代签任何 VERIFIED。</p>
<p>实际审核者姓名/账号：<input id="reviewer"> <button id="download">下载已填写的 researcher_records.csv</button></p>
<p>下载后将 CSV 放回服务器本目录，保留本目录的 review_bundle_manifest.json。也可直接编辑服务器 CSV。没有姓名、时间、必要检查项或 hash 不符时冻结工具会拒绝。无需审核本轮暂缓的 4 个二元关系 world。</p>
'''+''.join(sections)+'<script>'+js+'</script>'
    save(out/'index.html',page,'text')


def main():
    a=arguments(__doc__).parse_args(); c,root=setup(a)
    if a.dry_run: print('PLANNED: actual processor presentation and researcher checklist; no generation'); return
    compute(); start=time.monotonic()
    precore=list(rows(root/'inputs/precore/requests.jsonl')); core=list(rows(root/'review/draft_requests.jsonl'))
    requests=precore+core; cards=list(rows(root/'review/candidate_panel.jsonl'))
    gold={g['request_id']:g for g in rows(root/'private_gold/core_draft.jsonl')}
    index=[]; bygroup=defaultdict(dict)
    for model in c['models']:
        pipe=Pipeline(c,model)
        for i,r in enumerate(requests,1):
            batch,pres,images=pipe.process(r)
            pdir=root/'review/presentations'/pres['presentation_hash']; previews=[]
            for j,img in enumerate(images or []):
                out=pdir/f'image_{j:03d}.png'
                out.parent.mkdir(parents=True,exist_ok=True)
                if not out.exists(): img.save(out)
                previews.append(dict(path=str(out),size=list(img.size)))
            pres['preview_files']=previews
            save(root/'review/rendered'/model/(r['request_id']+'.json'),pres)
            index.append(dict(model=model,request_id=r['request_id'],group_id=r['group_id'],condition=r['condition'],
                              presentation_hash=pres['presentation_hash'],rendered_prompt_sha256=pres['rendered_prompt_sha256'],
                              input_tokens=pres['input_tokens'],visual_fields=sorted(pres['visual'])))
            if images: bygroup[r['group_id']][model]=pres
            del batch
            if i%80==0 or i==len(requests): print(json.dumps(dict(model=model,rendered=i,total=len(requests),generation_requests=0)),flush=True)
        del pipe
    idx={(r['model'],r['request_id']):r for r in index}; flips=0
    for model in c['models']:
        for gid in {r['group_id'] for r in requests}:
            for cond in ['SELECT_MEDIA','SELECT_MEDIA_OBJECT','SMOKE_SELECT_MEDIA']:
                pair=[r for r in requests if r['group_id']==gid and r['condition']==cond]
                if not pair: continue
                assert len(pair)==2
                assert idx[model,pair[0]['request_id']]['presentation_hash']==idx[model,pair[1]['request_id']]['presentation_hash']
                flips+=1
    for r in requests:
        assert len({idx[m,r['request_id']]['presentation_hash'] for m in c['models']})==1
    save(root/'review/actual_input_index.jsonl',index,'jsonl')
    write_page(c,root,cards,core,gold,bygroup)
    save(root/'reports/processor_checks.json',dict(status='PASS',requests_per_model=len(requests),rendered_prompts=len(index),
         core_drafts_per_model=len(core),precore_requests_per_model=len(precore),media_target_flip_checks=flips,
         every_request_processed=True,visual_fields=sorted({k for r in index for k in r['visual_fields']}),source_media_hash_checked=True,
         all_models_same_visuals=True,wall_seconds=time.monotonic()-start,generated=0,human_review_completed=False))
    lock=dict(status='PRECORE_FROZEN_ENGINEERING_CHECKED_GPU_AUTHORIZATION_SEPARATE',run_id=c['run_id'],
              requests_per_model=len(precore),inputs_sha256=sha(root/'inputs/precore/requests.jsonl'),
              config_sha256=sha(a.config),code=code_entries(c),generation=c['generation'],
              model_manifest_hashes=load(root/'current_state_inventory.json')['models'])
    save(root/'manifest/precore_lock.json',lock)
    save(root/'LIVE_STATUS.json',dict(status='PARTIAL_BLOCKED_REVIEW_AND_GPU_BUDGET',core_responses=0,precore_responses=0,
         verified_worlds=0,candidate_l4_count=7,candidate_l1=5,deferred_binary=4,core_drafts_per_model=319,
         semantic_bridge_per_model=76,smoke_per_model=6,processor_status='PASS',
         gpu_end_to_end_status='NOT_RUN',review_page=str(root/'review/index.html')),frozen=False)
    print(json.dumps(load(root/'reports/processor_checks.json')))


if __name__=='__main__': main()
