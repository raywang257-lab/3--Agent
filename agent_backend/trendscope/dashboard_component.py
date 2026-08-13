from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st


_DASHBOARD_HTML = """<div id="trendscope-dashboard"></div>"""

_DASHBOARD_CSS = r"""
:host { display:block; color:#162033; font-family:Arial,"PingFang SC","Microsoft YaHei",sans-serif; }
* { box-sizing:border-box; }
button,input { font:inherit; }
button { cursor:pointer; }
.app-shell { min-height:100vh; display:flex; background:#f7f9fc; border-radius:10px; overflow:hidden; }
.sidebar { width:188px; flex:0 0 188px; min-height:1180px; background:linear-gradient(180deg,#051d3b,#061a35 85%); color:#fff; padding:25px 10px; display:flex; flex-direction:column; }
.brand { display:flex; align-items:center; gap:10px; padding:0 10px 24px; }
.brand-mark { width:34px; height:34px; border:2px solid #1683ff; color:#1683ff; border-radius:50%; display:grid; place-items:center; font-size:24px; }
.brand strong { display:block; font-size:19px; letter-spacing:-.3px; }
.brand small { display:block; font-size:12px; margin-top:3px; color:#eef5ff; }
.sidebar nav { display:flex; flex-direction:column; gap:8px; }
.sidebar nav button { border:0; background:transparent; color:#e8eff9; display:flex; align-items:center; gap:14px; padding:13px 16px; border-radius:6px; text-align:left; font-weight:600; }
.sidebar nav button span { font-size:20px; width:20px; text-align:center; }
.sidebar nav button.active { background:#1268f3; color:#fff; box-shadow:0 5px 18px #00162d; }
.sidebar nav button:hover { background:#0b315d; }
.collapse { margin-top:auto; border:0; background:transparent; color:#d9e4f1; text-align:left; padding:12px; }
.workspace { flex:1; min-width:0; padding:16px 18px 28px; max-width:1500px; margin:0 auto; }
.topbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; gap:18px; }
.topbar h1 { font-size:23px; margin:0 0 7px; letter-spacing:.2px; }
.topbar h1 i { display:inline-block; height:20px; border-left:1px solid #9aa4b5; margin:0 8px -3px; }
.topbar p { margin:0; color:#667187; font-size:12px; }
.info-dot { border:1px solid #8f9aad; border-radius:50%; font-size:9px; padding:0 4px; }
.top-actions { display:flex; align-items:center; gap:8px; }
.top-actions button,.role-chip { height:38px; border:1px solid #d9e0ea; background:#fff; border-radius:6px; padding:0 13px; color:#1d293e; font-weight:600; font-size:12px; display:inline-flex; align-items:center; white-space:nowrap; }
.top-actions .primary { background:#1268f3; border-color:#1268f3; color:#fff; }
.top-actions .icon-btn { font-size:19px; padding:0 12px; }
.role-chip { color:#344258; font-weight:500; }
.decision-banner { min-height:78px; background:#fff; border:1px solid #dfe5ee; border-radius:7px; display:flex; align-items:center; padding:13px 18px; gap:13px; margin-bottom:12px; }
.alert-icon { width:34px; height:34px; border:3px solid #ed3131; border-radius:50%; color:#ed3131; font-size:23px; font-weight:800; display:grid; place-items:center; flex:0 0 auto; }
.decision-copy { flex:1; }
.decision-copy h2 { font-size:17px; margin:0 0 7px; }
.decision-copy p { margin:0; color:#58657b; font-size:12px; }
.decision-actions { display:flex; gap:8px; }
.decision-actions button { height:36px; min-width:108px; border:1px solid #d7dee8; background:#fff; border-radius:5px; font-size:12px; }
.decision-actions .urgent { background:#ed3131; color:#fff; border-color:#ed3131; }
.decision-actions .watch { border-color:#f5ad38; color:#d77c00; background:#fffaf0; }
.funnel { min-height:92px; background:#fff; border:1px solid #dfe5ee; border-radius:7px; display:flex; align-items:center; padding:10px 14px; margin-bottom:12px; }
.funnel-stage { flex:1; min-width:125px; display:flex; align-items:center; gap:10px; position:relative; }
.stage-icon { width:33px; height:33px; border-radius:50%; display:grid; place-items:center; background:#eaf2ff; color:#1268f3; font-size:18px; }
.stage-icon.c1 { background:#eafaf4; color:#0ba66a; }.stage-icon.c2 { background:#fff4dd; color:#d98700; }.stage-icon.c3 { background:#f1ecff; color:#7249e9; }
.funnel-stage small,.funnel-stage strong,.funnel-stage em { display:block; }
.funnel-stage small { color:#667187; font-size:10px; }.funnel-stage strong { font-size:18px; margin:2px 0; }.funnel-stage em { color:#9a5e00; font-size:9px; font-style:normal; }
.arrow { position:absolute; right:9px; color:#a8b1bf; font-weight:400; }
.coverage { width:225px; border-left:1px solid #dfe5ee; padding-left:14px; }
.coverage p { margin:0 0 8px; font-size:10px; color:#68748a; }.coverage strong { color:#ed3131; }.coverage button { border:0; background:transparent; color:#1268f3; padding:0; font-size:10px; }
.analysis-grid { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(310px,.88fr); gap:12px; align-items:start; }
.left-column,.right-column { min-width:0; display:flex; flex-direction:column; gap:12px; }
.panel,.hotspot-card { background:#fff; border:1px solid #dfe5ee; border-radius:7px; }
.panel-head { min-height:43px; border-bottom:1px solid #e5e9ef; display:flex; align-items:center; justify-content:space-between; padding:0 14px; }
.panel-head h2,.section-head h2 { font-size:15px; margin:0; }.panel-head h2 span,.section-head h2 span { color:#7c8798; font-weight:400; }
.title-tabs { display:flex; align-items:center; gap:7px; }.title-tabs h2 { margin-right:8px; }
.title-tabs button { border:0; background:transparent; color:#667187; padding:6px 9px; font-size:10px; border-radius:4px; }.title-tabs button.selected { background:#eaf2ff; color:#1268f3; font-weight:700; }
.panel-head p { margin:0; font-size:9px; color:#7c8798; }
.legend { height:30px; display:flex; align-items:center; gap:17px; padding:0 15px; font-size:9px; color:#5f6b7f; }.legend span { display:flex; align-items:center; gap:5px; }.legend i,.breakdown i { width:8px; height:8px; border-radius:50%; display:inline-block; }.blue { background:#1769ff; }.green { background:#10a66a; }.amber { background:#f59e0b; }.purple { background:#7249e9; }.legend em { margin-left:auto; font-style:normal; }
.trend-canvas { width:100%; height:185px; display:block; }
.section-head { display:flex; align-items:center; justify-content:space-between; margin:2px 1px 8px; }.section-head button { border:1px solid #dce2eb; background:#fff; border-radius:5px; height:32px; padding:0 12px; font-size:10px; }
.hotspot-card { display:flex; gap:10px; padding:12px; transition:.15s; cursor:pointer; }
.hotspot-card.selected { border-color:#1769ff; box-shadow:0 0 0 1px #1769ff; }.hotspot-card:hover { transform:translateY(-1px); box-shadow:0 7px 22px #17233d13; }
.rank { width:25px; height:25px; border-radius:4px; background:#eff3f8; color:#5e6b7f; display:grid; place-items:center; font-weight:700; font-size:11px; flex:0 0 auto; }
.selected .rank { background:#1769ff; color:#fff; }
.hotspot-main { flex:1; min-width:0; }.hotspot-title { display:flex; align-items:flex-start; gap:9px; }.hotspot-title h3 { font-size:13px; margin:3px 0 9px; flex:1; line-height:1.35; }.action-badge { font-size:9px; padding:4px 8px; border-radius:12px; white-space:nowrap; }.urgent { background:#fff0f0; color:#dc2929; }.watch { background:#fff6e6; color:#cd7600; }.risk { background:#eef2f7; color:#58657b; }
.signal-chips { display:flex; gap:7px; flex-wrap:wrap; }.signal-chips span { border:1px solid #e2e7ee; background:#fafbfd; padding:5px 7px; border-radius:4px; font-size:9px; color:#6b7688; }.signal-chips b { color:#273247; }.signal-chips .up { color:#ed3131; }
.insight-grid { display:grid; grid-template-columns:1fr 1fr; gap:5px 16px; margin-top:9px; }.insight-grid p { margin:0; font-size:9px; color:#68748a; line-height:1.45; }.insight-grid p:last-child { grid-column:1/-1; }.insight-grid b { color:#293448; }
.source-links { display:flex; align-items:center; gap:6px; margin-top:9px; }.source-links a { text-decoration:none; border:1px solid #dfe5ee; background:#fff; color:#273247; padding:4px 6px; border-radius:4px; font-size:9px; }.source-links i { display:inline-grid; place-items:center; width:17px; height:17px; border-radius:3px; background:#edf3ff; color:#1769ff; font-style:normal; font-weight:700; margin-right:4px; }.source-links span { margin-left:auto; font-size:9px; color:#7a8597; }
.view-all { width:100%; height:35px; border:0; background:transparent; color:#1268f3; font-size:10px; }
.signal-composition { display:grid; grid-template-columns:90px 1fr; padding:13px; gap:10px; }
.donut { width:76px; height:76px; border-radius:50%; background:conic-gradient(#1769ff 0 35%,#10a66a 35% 60%,#7249e9 60% 80%,#f59e0b 80%); display:grid; place-items:center; position:relative; }.donut:after { content:""; position:absolute; inset:13px; background:#fff; border-radius:50%; }.donut span { position:relative; z-index:1; text-align:center; font-size:9px; color:#6c7789; }.donut b { color:#263247; }
.breakdown { display:grid; grid-template-columns:1fr 1fr; gap:5px; align-content:center; }.breakdown p { margin:0; font-size:9px; color:#667187; display:flex; align-items:center; gap:5px; }.breakdown b { margin-left:auto; color:#263247; }
.confidence { grid-column:1/-1; border-top:1px solid #e1e6ed; padding-top:9px; display:grid; grid-template-columns:1.4fr 1fr 1fr; gap:7px; }.confidence p { margin:0; font-size:9px; color:#5f6b7f; }.confidence b,.confidence small { display:block; }.confidence small { margin-top:3px; color:#7a8597; }
.source-path { display:flex; justify-content:space-around; padding:13px 10px 7px; }.source-node { position:relative; text-align:center; min-width:46px; }.source-node i { width:24px; height:24px; background:#edf3ff; color:#1769ff; border-radius:4px; display:grid; place-items:center; margin:0 auto 4px; font-size:8px; font-style:normal; font-weight:800; }.source-node b { display:block; font-size:8px; }.source-node small { font-size:8px; color:#7c8798; }.source-node span { position:absolute; left:calc(100% + 2px); top:5px; color:#8792a3; }.propagation>p { margin:0 14px 10px; font-size:9px; color:#6c7789; }
.evidence-list { padding:6px 9px 10px; }.evidence-row { min-height:37px; margin-top:6px; border:1px solid #e1e6ed; border-radius:5px; display:grid; grid-template-columns:20px 54px 1fr; align-items:center; gap:6px; padding:6px 8px; font-size:9px; }.evidence-row i { width:18px; height:18px; border-radius:50%; display:grid; place-items:center; background:#13aa6e; color:#fff; font-style:normal; font-weight:800; }.evidence-row.e1 i { background:#f3a016; }.evidence-row.e2 i { background:#ef3838; }
.agent-box { background:transparent; }.ask-row { min-height:48px; border:1.5px solid #1769ff; border-radius:6px; background:#fff; display:flex; align-items:center; padding:0 11px; gap:8px; }.ask-row>span { color:#1769ff; }.ask-row input { flex:1; border:0; outline:0; font-size:10px; min-width:0; }.ask-row button { border:0; background:#6e9df0; color:#fff; border-radius:50%; width:25px; height:25px; }.quick-actions { display:grid; grid-template-columns:1.15fr 1fr .9fr; gap:7px; margin-top:8px; }.quick-actions button { height:39px; background:#fff; border:1px solid #dfe4ec; border-radius:5px; font-size:9px; }
.empty { padding:35px; text-align:center; color:#68748a; }.toast { position:fixed; right:28px; bottom:26px; background:#17243a; color:#fff; padding:11px 16px; border-radius:6px; box-shadow:0 10px 30px #1b26364d; font-size:12px; z-index:10; }
@media(max-width:1100px){.role-chip{display:none}.analysis-grid{grid-template-columns:1fr}.right-column{display:grid;grid-template-columns:1fr 1fr}.agent-box{grid-column:1/-1}.decision-actions button{min-width:92px}.sidebar{width:168px;flex-basis:168px}}
@media(max-width:760px){.sidebar{width:62px;flex-basis:62px;padding:18px 7px}.brand span:last-child,.sidebar nav button:not(.active){font-size:0}.sidebar nav button{justify-content:center;padding:13px}.sidebar nav button.active{font-size:0}.collapse{display:none}.workspace{padding:12px}.topbar,.decision-banner{align-items:flex-start;flex-direction:column}.top-actions{flex-wrap:wrap}.decision-actions{width:100%}.decision-actions button{min-width:0;flex:1}.funnel{display:grid;grid-template-columns:1fr 1fr}.arrow{display:none}.coverage{border-left:0;border-top:1px solid #dfe5ee;width:auto;grid-column:1/-1;padding:10px}.right-column{display:flex}.insight-grid{grid-template-columns:1fr}.confidence{grid-template-columns:1fr}.source-links{flex-wrap:wrap}.source-links span{margin-left:0}}
"""

_DASHBOARD_JS = r"""
export default function(component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component
  const root = parentElement.querySelector('#trendscope-dashboard')
  if (!root) return
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
  const safeUrl = (value) => /^https?:\/\//i.test(String(value ?? '')) ? esc(value) : '#'
  const state = parentElement.__trendScopeState ?? { selected: 0, range: '24h', toastTimer: null }
  parentElement.__trendScopeState = state
  const events = Array.isArray(data?.events) ? data.events : []
  if (state.selected >= events.length) state.selected = 0
  const selected = events[state.selected] || null
  const summary = data?.summary || {}
  const funnel = data?.funnel || {}
  const counts = data?.counts || {}
  const notice = data?.notice || ''
  const sources = selected?.sources || []
  const evidence = selected?.evidence || []
  const eventCards = events.slice(0, 6).map((item, index) => `
    <article class="hotspot-card ${state.selected === index ? 'selected' : ''}" data-event-index="${index}">
      <span class="rank">${index + 1}</span><div class="hotspot-main">
        <div class="hotspot-title"><h3>${esc(item.title)}</h3><span class="action-badge ${esc(item.tone)}">${esc(item.action)}</span></div>
        <div class="signal-chips"><span>价值分　<b>${esc(item.score)}</b></span><span>增长　<b class="up">${esc(item.growth)}</b></span><span>覆盖　<b>${esc(item.platforms)}</b></span><span>独立信源　<b>${esc(item.sourceCount)}</b></span></div>
        ${state.selected === index ? `<div class="insight-grid"><p><b>为何上榜：</b>${esc(item.why)}</p><p><b>建议动作：</b>${esc(item.advice)}</p><p><b>争议焦点：</b>${esc(item.debate)}</p><p><b>风险：</b>${esc(item.risk)}</p><p><b>影响对象：</b>${esc(item.impact)}</p></div><div class="source-links">${(item.sources || []).slice(0,3).map(s => `<a href="${safeUrl(s.url)}" target="_blank" rel="noopener"><i>${esc(s.short)}</i>${esc(s.name)}　↗</a>`).join('')}<span>${esc(item.sourceCount)} 个独立信源</span></div>` : ''}
      </div></article>`).join('')
  root.innerHTML = `<main class="app-shell">
    <aside class="sidebar"><div class="brand"><span class="brand-mark">◎</span><span><strong>TrendScope</strong><small>热点雷达</small></span></div>
      <nav>${[['⌖','今日决策'],['◉','热点监控'],['▣','专题分析'],['▥','分析报告'],['◫','数据源']].map((x,i)=>`<button class="${i===0?'active':''}" data-toast="${x[1]}模块为演示入口"><span>${x[0]}</span>${x[1]}</button>`).join('')}</nav><button class="collapse">‹　收起菜单</button></aside>
    <section class="workspace">
      <header class="topbar"><div><h1>${esc(data?.industry || 'AI 编程工具')} <i></i> 热点决策台</h1><p>${data?.demo ? '演示样板　·　' : '持续监控　·　'}数据截至 ${esc(summary.updatedAt || '等待首次分析')}　·　最近 7 天　<span class="info-dot">i</span></p></div>
        <div class="top-actions"><span class="role-chip">♙　AI 产品与竞争情报</span><button data-toast="执行日志可在页面底部查看">▤　查看执行日志</button><button class="primary" id="update-analysis">↻　更新分析</button><button class="icon-btn" data-toast="暂无更多操作">⋮</button></div></header>
      <section class="decision-banner"><span class="alert-icon">!</span><div class="decision-copy"><h2>${esc(counts.headline)}</h2><p>${esc(counts.subline)}</p></div><div class="decision-actions"><button class="urgent" data-select-tone="urgent">立即跟进　<b>${esc(counts.urgent)}</b></button><button class="watch" data-select-tone="watch">持续观察　<b>${esc(counts.watch)}</b></button><button data-select-tone="risk">暂不处理　<b>${esc(counts.risk)}</b></button></div></section>
      <section class="funnel"><div class="funnel-stage"><span class="stage-icon c0">▤</span><div><small>原始信息</small><strong>${esc(funnel.raw)} 条</strong><em>去重 ${esc(funnel.duplicates)}</em></div><b class="arrow">→</b></div><div class="funnel-stage"><span class="stage-icon c1">▽</span><div><small>相关信息</small><strong>${esc(funnel.related)} 条</strong><em>低相关 ${esc(funnel.filtered)}</em></div><b class="arrow">→</b></div><div class="funnel-stage"><span class="stage-icon c2">⌁</span><div><small>独立事件</small><strong>${esc(funnel.events)} 个</strong><em>候选 ${esc(funnel.candidates)}</em></div><b class="arrow">→</b></div><div class="funnel-stage"><span class="stage-icon c3">☆</span><div><small>高价值热点</small><strong>${esc(funnel.high)} 个</strong><em></em></div></div><div class="coverage"><p>覆盖 ${esc(funnel.sources)} 个来源　·　<strong>${esc(funnel.warnings)} 个来源异常</strong></p><button data-toast="重复 ${esc(funnel.duplicates)}、低相关 ${esc(funnel.filtered)}、候选 ${esc(funnel.candidates)}">查看筛选原因　›</button></div></section>
      <div class="analysis-grid"><div class="left-column"><section class="panel"><div class="panel-head"><div class="title-tabs"><h2>趋势与爆发信号</h2><button class="range ${state.range==='24h'?'selected':''}" data-range="24h">24 小时</button><button class="range ${state.range==='7d'?'selected':''}" data-range="7d">7 天</button></div><p>生命周期：萌芽　→　爆发　→　<b>扩散</b>　→　衰退</p></div><div class="legend"><span><i class="blue"></i>${esc(events[0]?.shortTitle || '事件 1')}</span><span><i class="green"></i>${esc(events[1]?.shortTitle || '事件 2')}</span><span><i class="amber"></i>${esc(events[2]?.shortTitle || '事件 3')}</span><em>虚线为同类基线</em></div><canvas class="trend-canvas" aria-label="热点讨论量趋势图"></canvas></section>
        <section><div class="section-head"><h2>值得关注的热点 <span>（共 ${data?.totalEvents ?? events.length} 个）</span></h2><button data-toast="已按行动优先级排序">按行动优先级　⌄</button></div>${eventCards || '<div class="panel empty">本轮暂时没有通过事件门槛的候选</div>'}<button class="view-all" data-toast="完整事件列表已加载">查看其余热点　↓</button></section></div>
        <aside class="right-column"><section class="panel"><div class="panel-head"><h2>选中热点 <span>｜判断依据</span></h2></div><div class="signal-composition"><div class="donut"><span>信号<br><b>构成</b></span></div><div class="breakdown"><p><i class="blue"></i>相关性 <b>${esc(selected?.breakdown?.relevance || 0)}%</b></p><p><i class="green"></i>跨平台 <b>${esc(selected?.breakdown?.crossPlatform || 0)}%</b></p><p><i class="purple"></i>核心信源 <b>${esc(selected?.breakdown?.sourceStrength || 0)}%</b></p><p><i class="amber"></i>增长信号 <b>${esc(selected?.breakdown?.growth || 0)}%</b></p></div><div class="confidence"><p><b>业务相关性：${esc(selected?.priority || '待评估')}</b><small>${esc(selected?.action || '等待分析')}</small></p><p><b>事件真实性：${esc(selected?.truth || '信息不足')}</b></p><p><b>聚类置信度：${esc(selected?.cluster || '不适用')}</b></p></div></div></section>
          <section class="panel propagation"><div class="panel-head"><h2>传播路径</h2></div><div class="source-path">${sources.slice(0,4).map((s,i)=>`<div class="source-node"><i>${esc(s.short)}</i><b>${esc(s.name)}</b><small>${esc(s.time)}</small>${i < Math.min(sources.length,4)-1?'<span>→</span>':''}</div>`).join('') || '<span class="empty">暂无可回溯来源</span>'}</div>${sources.length?`<p>首发信源：<b>${esc(sources[0].name)}</b></p>`:''}</section>
          <section class="panel"><div class="panel-head"><h2>关键证据与反方观点</h2></div><div class="evidence-list">${evidence.slice(0,3).map((e,i)=>`<div class="evidence-row e${i}"><i>${i===0?'✓':i===1?'−':'!'}</i><b>${esc(e.label)}</b><span>${esc(e.text)}</span></div>`).join('') || '<div class="empty">尚无结构化主张证据</div>'}</div></section>
          <section class="agent-box"><div class="ask-row"><span>✦</span><input id="question" placeholder="追问：为什么继续扩散？还有哪些反对证据？"><button id="ask">➤</button></div><div class="quick-actions"><button data-toast="竞品简报已加入报告任务">▤　生成竞品简报</button><button data-toast="选题建议已生成">✎　生成选题</button><button data-toast="预警已设置">♧　设置预警</button></div></section></aside></div>
      ${notice ? `<div class="toast">${esc(notice)}</div>` : ''}
    </section></main>`
  const toast = (message) => { let old = root.querySelector('.toast'); if(old) old.remove(); const el=document.createElement('div'); el.className='toast'; el.textContent=message; root.appendChild(el); clearTimeout(state.toastTimer); state.toastTimer=setTimeout(()=>el.remove(),2200) }
  root.querySelectorAll('[data-toast]').forEach(el => el.onclick = () => toast(el.dataset.toast))
  root.querySelectorAll('[data-event-index]').forEach(el => el.onclick = () => { state.selected=Number(el.dataset.eventIndex); setStateValue('selected', state.selected) })
  root.querySelectorAll('[data-select-tone]').forEach(el => el.onclick = () => { const idx=events.findIndex(x=>x.tone===el.dataset.selectTone); if(idx>=0){state.selected=idx;setStateValue('selected',idx)} })
  root.querySelectorAll('[data-range]').forEach(el => el.onclick = () => {state.range=el.dataset.range;root.querySelectorAll('[data-range]').forEach(x=>x.classList.toggle('selected',x.dataset.range===state.range));drawChart(root.querySelector('.trend-canvas'), state.range, state.selected)})
  const update = root.querySelector('#update-analysis'); if(update) update.onclick=()=>{update.disabled=true;update.textContent='更新中…';setTriggerValue('update',Date.now())}
  const ask = root.querySelector('#ask'); if(ask) ask.onclick=()=>{const q=root.querySelector('#question')?.value?.trim(); if(q) toast(`已提交追问：${q}`)}
  drawChart(root.querySelector('.trend-canvas'), state.range, state.selected)
  function drawChart(canvas, range, selectedIndex){
    if(!canvas) return; const ratio=devicePixelRatio||1; const rect=canvas.getBoundingClientRect(); canvas.width=rect.width*ratio; canvas.height=rect.height*ratio; const ctx=canvas.getContext('2d'); ctx.scale(ratio,ratio); const w=rect.width,h=rect.height,p={l:40,r:16,t:24,b:27},iw=w-p.l-p.r,ih=h-p.t-p.b; ctx.font='9px Arial'; ctx.strokeStyle='#e7ebf2';ctx.fillStyle='#7b8599';for(let i=0;i<=4;i++){const y=p.t+ih*i/4;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(w-p.r,y);ctx.stroke();ctx.fillText(i===4?'0':`${(1600-i*400)/1000}k`,7,y+3)}
    const labels=range==='24h'?['00:00','04:00','08:00','12:00','16:00','20:00','24:00']:['8/06','8/07','8/08','8/09','8/10','8/11','8/12'];labels.forEach((x,i)=>ctx.fillText(x,p.l+iw*i/(labels.length-1)-12,h-7));
    const a24=[[25,35,48,55,60,85,160,305,550,760,900,1030,1210,1410,1390,1240,1080,1040],[20,28,36,44,60,90,170,290,390,440,490,540,585,610,590,610,620,618],[12,16,25,30,42,65,110,190,270,320,340,360,370,380,370,355,345,335]],a7=[[110,140,190,260,410,760,1310,1820,2150,2040,1960,1710,1530,1410],[160,180,210,245,300,420,610,780,920,1050,1120,1180,1160,1200],[80,95,130,160,220,300,440,580,690,740,760,730,710,700]],all=range==='24h'?a24:a7,max=range==='24h'?1600:2400,colors=['#1769ff','#10a66a','#f59e0b'];all.forEach((series,si)=>{ctx.beginPath();series.forEach((v,i)=>{const x=p.l+iw*i/(series.length-1),y=p.t+ih-v/max*ih;i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.strokeStyle=colors[si];ctx.lineWidth=selectedIndex===si?3:1.7;ctx.globalAlpha=selectedIndex===si?1:.55;ctx.stroke();ctx.globalAlpha=1})
  }
}
"""


_DASHBOARD = st.components.v2.component(
    "trendscope_decision_dashboard",
    html=_DASHBOARD_HTML,
    css=_DASHBOARD_CSS,
    js=_DASHBOARD_JS,
)


def dashboard(
    data: dict[str, Any],
    *,
    key: str = "trendscope-dashboard",
    on_update_change: Callable[[], None] | None = None,
):
    return _DASHBOARD(
        key=key,
        data=data,
        on_selected_change=lambda: None,
        on_update_change=on_update_change or (lambda: None),
    )
