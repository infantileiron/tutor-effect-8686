import{store}from'../stores/business.js';import{esc,num}from'../utils/format.js';import{table}from'../components/common/table.js';import{notice}from'../components/common/notice.js';import{badge}from'../components/common/status.js';import{resultPanel}from'../components/common/report.js';import{GROUPS,RECRUIT_KIND,SOURCE}from'../constants/enums.js';
export const recruitState={keys:{initial:null,supplementary:null},planId:null,batchId:null,reportId:null};
const pct=r=>r==null?'—':Math.round(r*100)+'%';
const editor=()=>store.user&&store.user.role!=='viewer';
const time=t=>esc((t||'').slice(0,19).replace('T',' '));
function overviewSection(){
 if(!store.overview)return'';
 const ov=store.overview;
 const rows=ov.plans.map(p=>[`<b>${esc(p.title)}</b>`,esc(p.campus),`${p.target_control} / ${p.target_intervention}`,`${p.locked_control} / ${p.locked_intervention}`,`${p.pending_control} / ${p.pending_intervention}`,pct(p.ratio),String(p.eligible_free),p.reasons.length?`<ul class=reason-list>${p.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:'<span class=muted>—</span>']);
 return `<div class=section-title><h2>候选与占用</h2><span>可分配候选 ${ov.candidates_free} / ${ov.candidates_total} 人 · 每人同期只占一个名额</span></div>${table(['方案','教学点','目标 对/干','已锁定 对/干','待分配 对/干','达成率','合格候选','缺额原因'],rows)}`;
}
function actionsSection(){
 if(!editor())return notice('当前角色可查看招募情况，不能发起、锁定或退出。');
 return `<div class=section-title><h2>招募操作</h2><span>先最大化各方案最低达成比例，再最大化总人数</span></div><div class=recruit-actions><button id=recruit-initial class=primary>发起联合招募 →</button><button id=recruit-supplementary class=quiet>发起补招（填充退出空缺）→</button></div>${notice('招募生成「待分配」批次，核对后锁定生效；网络重试使用同一幂等键，不会重复占位。')}`;
}
function batchDetail(){
 const d=store.batchDetail;
 if(!d||d.id!==recruitState.batchId)return'';
 const plans=(d.summary?.plans||[]).map(p=>`<li><b>${esc(p.title)}</b>：本轮 ${p.assigned_control+p.assigned_intervention} / ${p.target_control+p.target_intervention} 人（达成 ${pct(p.ratio)}）${p.reasons.length?`<ul class=reason-list>${p.reasons.map(r=>`<li>${esc(r.message)}</li>`).join('')}</ul>`:''}</li>`).join('');
 const rows=d.assignments.map(a=>[esc(a.student_code),esc(a.student_name),esc(a.plan_title),esc(GROUPS[a.group]||a.group),badge(a.status)]);
 return `<section class=result-sheet><span class=eyebrow>BATCH № ${d.id} · ${esc(RECRUIT_KIND[d.kind]||d.kind)}</span><h2>分配明细 ${badge(d.status)}</h2><ul>${plans}</ul>${table(['编号','姓名','方案','组别','状态'],rows)}</section>`;
}
function batchesSection(){
 if(!store.recruitments.length)return notice('还没有招募批次。先发起联合招募。');
 const rows=store.recruitments.map(b=>[`№ ${b.id}`,esc(RECRUIT_KIND[b.kind]||b.kind),badge(b.status),time(b.created_at),`${b.counts.pending||0} / ${b.counts.locked||0} / ${b.counts.withdrawn||0}`,`${pct(b.summary?.min_ratio)} · 共 ${b.summary?.total_assigned??0} 人`,`${b.status==='pending'&&editor()?`<button class=text-btn data-lock=${b.id}>锁定 →</button>`:''}<button class=text-btn data-batch-detail=${b.id}>明细</button>`]);
 return `<div class=section-title><h2>招募批次</h2><span>待分配 → 已锁定；退出名额进入补招池</span></div>${table(['批次','类型','状态','创建时间 UTC','待/锁/退','最低达成率 · 总人数','操作'],rows)}${batchDetail()}`;
}
function rosterSection(){
 const plans=store.plans.filter(p=>p.target_control+p.target_intervention>0);
 if(!plans.length)return notice('还没有设置两组目标人数的方案。请先在「辅导分组」填写目标人数。');
 const pid=recruitState.planId??plans[0].id;
 const plan=plans.find(p=>p.id===+pid);
 const r=store.roster;
 let body=notice('正在加载名单…');
 if(r&&r.plan_id===+pid){
  const occ=r.occupancy;
  const rows=r.assignments.map(a=>[esc(a.student.code),esc(a.student.name),esc(a.student.campus),esc(GROUPS[a.group]||a.group),badge(a.status),a.student.score==null?'—':num(a.student.score,1),['pending','locked'].includes(a.status)&&editor()?`<button class=text-btn data-withdraw=${a.id}>退出</button>`:'']);
  const basis=r.reports.map(rep=>`<button class=history-entry data-roster-report=${rep.id}>№ ${rep.id}　${esc(SOURCE[rep.source]||rep.source)} ${badge(rep.status)}<small>${time(rep.created_at)} UTC${rep.published?' · 已签核':''}</small></button>`).join('');
  const report=store.reports.find(x=>x.id===recruitState.reportId);
  body=`<p class=method>已锁定 对 ${occ.locked_control} / 干 ${occ.locked_intervention} · 待分配 对 ${occ.pending_control} / 干 ${occ.pending_intervention} · 目标 对 ${plan?plan.target_control:'—'} / 干 ${plan?plan.target_intervention:'—'}</p>${table(['编号','姓名','教学点','组别','状态','成绩','操作'],rows)}<div class=section-title><h2>检验依据</h2><span>检验只读已锁定名单；报告快照不受退出/补招影响</span></div><div class=run-history>${basis||notice('还没有检验报告。')}</div><section class=result-sheet>${report?resultPanel(report):'<div class=empty>选择一份报告查看检验依据与样本快照。</div>'}</section>`;
 }
 return `<div class=section-title><h2>各研究名单</h2><span>退出释放名额供补招</span></div><label class=report-selector>研究方案<select id=roster-plan>${plans.map(p=>`<option value=${p.id} ${p.id===+pid?'selected':''}>${esc(p.title)}</option>`).join('')}</select></label>${body}`;
}
export function recruitmentPage(){
 return `<header class=page-head><div><span class=eyebrow>03 / JOINT RECRUITMENT</span><h1>联合招募</h1><p>多研究共享候选时联合分配名额：先最大化各方案最低达成比例，再最大化总人数。</p></div></header>${overviewSection()}${actionsSection()}${batchesSection()}${rosterSection()}`;
}
