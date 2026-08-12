"use client";

import { useEffect, useRef, useState } from "react";

type Hotspot = {
  id: number;
  title: string;
  action: string;
  actionTone: "urgent" | "watch" | "risk";
  discussions: string;
  growth: string;
  platforms: string;
  percentile: string;
  why: string;
  debate: string;
  impact: string;
  advice: string;
  risk: string;
  business: string;
  truth: string;
  cluster: string;
  sources: { name: string; time: string; short: string }[];
  evidence: [string, string][];
};

const hotspots: Hotspot[] = [
  {
    id: 1,
    title: "Cursor 发布新版本，跨平台讨论 4 小时增长 280%",
    action: "立即跟进",
    actionTone: "urgent",
    discussions: "1,284 条",
    growth: "+216%",
    platforms: "4/6 平台",
    percentile: "Top 3%",
    why: "官方发布与开发者实测集中出现",
    debate: "能力提升明显，但成本与代码隐私仍有争议",
    impact: "AI IDE、开发者工具、模型厂商",
    advice: "今日发布竞品快讯，并安排功能拆解",
    risk: "部分传播来自二次转载",
    business: "高 · 直接影响 AI 编程工具竞争格局",
    truth: "较高",
    cluster: "中等",
    sources: [
      { name: "官方博客", time: "08:20", short: "官" },
      { name: "GitHub", time: "10:40", short: "GH" },
      { name: "Hacker News", time: "12:10", short: "HN" },
      { name: "Reddit", time: "13:30", short: "R" },
    ],
    evidence: [
      ["支持证据", "官方 Release 可验证功能变化"],
      ["反方证据", "暂无独立性能评测"],
      ["风险提示", "Reddit 内容存在重复转载"],
    ],
  },
  {
    id: 2,
    title: "GitHub Copilot 企业安全功能升温",
    action: "持续观察",
    actionTone: "watch",
    discussions: "642 条",
    growth: "+88%",
    platforms: "3/6 平台",
    percentile: "Top 12%",
    why: "企业客户集中讨论合规与数据边界",
    debate: "安全控制增强，但配置复杂度可能上升",
    impact: "企业研发团队、安全与合规负责人",
    advice: "追踪企业版实际部署反馈，48 小时后复评",
    risk: "当前讨论集中在少数技术社区",
    business: "中高 · 影响企业采购与工具选型",
    truth: "较高",
    cluster: "较高",
    sources: [
      { name: "GitHub", time: "09:10", short: "GH" },
      { name: "Hacker News", time: "11:25", short: "HN" },
      { name: "技术 RSS", time: "14:10", short: "RSS" },
    ],
    evidence: [
      ["支持证据", "官方文档列出新的策略控制项"],
      ["反方证据", "尚无大规模企业落地案例"],
      ["风险提示", "媒体报道多引用同一官方材料"],
    ],
  },
  {
    id: 3,
    title: "Continue 融资消息扩散，但独立信源不足",
    action: "谨慎验证",
    actionTone: "risk",
    discussions: "318 条",
    growth: "+47%",
    platforms: "2/6 平台",
    percentile: "Top 28%",
    why: "融资数字被多个聚合账号短时间转载",
    debate: "商业关注上升，但关键金额缺少官方确认",
    impact: "投资研究、开发者工具赛道观察者",
    advice: "暂不对外引用，等待公司或投资方确认",
    risk: "疑似同源转载形成虚假跨平台热度",
    business: "中等 · 可能影响赛道融资预期",
    truth: "信息不足",
    cluster: "较低",
    sources: [
      { name: "行业媒体", time: "10:05", short: "媒" },
      { name: "Reddit", time: "12:40", short: "R" },
    ],
    evidence: [
      ["支持证据", "多个账号出现相同融资描述"],
      ["反方证据", "公司与投资方均未发布公告"],
      ["风险提示", "高度疑似单一稿源重复传播"],
    ],
  },
];

const navItems = ["今日决策", "热点监控", "专题分析", "分析报告", "数据源"];

function TrendChart({ range, selected }: { range: "24h" | "7d"; selected: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * ratio;
    canvas.height = rect.height * ratio;
    ctx.scale(ratio, ratio);
    const w = rect.width;
    const h = rect.height;
    const pad = { l: 42, r: 18, t: 28, b: 32 };
    const iw = w - pad.l - pad.r;
    const ih = h - pad.t - pad.b;

    ctx.clearRect(0, 0, w, h);
    ctx.font = "11px Arial";
    ctx.strokeStyle = "#e7ebf2";
    ctx.fillStyle = "#7b8599";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (ih * i) / 4;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      const value = range === "24h" ? 1600 - i * 400 : 2400 - i * 600;
      ctx.fillText(i === 4 ? "0" : `${value / 1000}k`, 8, y + 4);
    }
    const labels = range === "24h" ? ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"] : ["8/06", "8/07", "8/08", "8/09", "8/10", "8/11", "8/12"];
    labels.forEach((label, i) => ctx.fillText(label, pad.l + (iw * i) / (labels.length - 1) - 14, h - 9));

    const series24 = [
      [25,35,48,46,55,58,60,72,85,120,160,230,305,420,550,710,760,820,900,970,1030,1150,1210,1340,1410,1450,1390,1300,1240,1190,1080,1120,1040],
      [20,28,32,36,40,44,52,60,72,90,120,170,220,290,340,390,420,440,470,490,500,540,570,585,610,620,590,600,610,615,620,618,620],
      [12,16,20,25,28,30,36,42,50,65,85,110,145,190,230,270,300,320,330,340,350,360,365,370,380,385,370,365,355,350,345,340,335],
    ];
    const series7 = [
      [110,140,190,260,410,760,1310,1820,2150,2040,1960,1710,1530,1410],
      [160,180,210,245,300,420,610,780,920,1050,1120,1180,1160,1200],
      [80,95,130,160,220,300,440,580,690,740,760,730,710,700],
    ];
    const all = range === "24h" ? series24 : series7;
    const max = range === "24h" ? 1600 : 2400;
    const colors = ["#1769ff", "#10a66a", "#f59e0b"];
    all.forEach((series, si) => {
      ctx.beginPath();
      series.forEach((v, i) => {
        const x = pad.l + (iw * i) / (series.length - 1);
        const y = pad.t + ih - (v / max) * ih;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.strokeStyle = colors[si];
      ctx.lineWidth = selected === si + 1 ? 3 : 1.7;
      ctx.globalAlpha = selected === si + 1 ? 1 : .55;
      ctx.stroke();
      ctx.globalAlpha = 1;
    });

    if (range === "24h") {
      const marks = [[11,"08:20","官方发布"],[15,"10:40","GitHub Release"],[18,"12:10","HN 讨论爆发"]];
      marks.forEach(([index,time,label]) => {
        const x = pad.l + (iw * Number(index)) / 32;
        ctx.setLineDash([3,3]); ctx.strokeStyle = "#8691a5";
        ctx.beginPath(); ctx.moveTo(x, pad.t + 30); ctx.lineTo(x, h - pad.b); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = "#263247"; ctx.font = "600 10px Arial";
        ctx.fillText(String(time), x - 15, pad.t + 9); ctx.font = "10px Arial";
        ctx.fillText(String(label), x - 22, pad.t + 22);
      });
    }
  }, [range, selected]);

  return <canvas ref={canvasRef} className="trend-canvas" aria-label="热点讨论量趋势图" />;
}

export default function Home() {
  const [selectedId, setSelectedId] = useState(1);
  const [range, setRange] = useState<"24h" | "7d">("24h");
  const [question, setQuestion] = useState("");
  const [toast, setToast] = useState("");
  const [updatedAt, setUpdatedAt] = useState("2026-08-12 10:30");
  const selected = hotspots.find((item) => item.id === selectedId) ?? hotspots[0];

  const notify = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  };

  const updateAnalysis = () => {
    setUpdatedAt(new Date().toLocaleString("zh-CN", { hour12: false }).replaceAll("/", "-"));
    notify("分析已更新：样板数据保持不变");
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">◎</span><span><strong>TrendScope</strong><small>热点雷达</small></span></div>
        <nav aria-label="主导航">
          {navItems.map((item, index) => <button key={item} className={index === 0 ? "active" : ""} onClick={() => notify(`${item}模块为演示入口`)}><span>{["⌖","◉","▣","▥","◫"][index]}</span>{item}</button>)}
        </nav>
        <button className="collapse" onClick={() => notify("侧边栏已保持展开，便于演示")}>‹ <span>收起菜单</span></button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><h1>AI 编程工具 <i /> 热点决策台</h1><p>持续监控　·　数据截至 {updatedAt}　·　最近 7 天　<span className="info-dot">i</span></p></div>
          <div className="top-actions"><span className="role-chip">♙　AI 产品与竞争情报</span><button className="ghost" onClick={() => notify("本次分析：126 条信息，完成去重、聚类与信源核验")}>▤　查看执行日志</button><button className="primary" onClick={updateAnalysis}>↻　更新分析</button><button className="icon-btn" aria-label="更多操作">⋮</button></div>
        </header>

        <section className="decision-banner">
          <span className="alert-icon">!</span>
          <div className="decision-copy"><h2>今天有 3 个热点值得立即关注，2 个正在快速升温，1 个疑似虚假热度。</h2><p>Cursor 新版本在 4 小时内跨平台扩散，建议产品与内容团队立即跟进。</p></div>
          <div className="decision-actions"><button className="urgent" onClick={() => setSelectedId(1)}>立即跟进　<b>3</b></button><button className="watch" onClick={() => setSelectedId(2)}>持续观察　<b>2</b></button><button onClick={() => setSelectedId(3)}>暂不处理　<b>1</b></button></div>
        </section>

        <section className="funnel" aria-label="信息处理漏斗">
          {[
            ["▤","原始信息","126 条","去重 56"],
            ["▽","相关信息","42 条","低相关 19"],
            ["⌁","独立事件","18 个","低可信 9"],
            ["☆","高价值热点","6 个",""]
          ].map((stage, index) => <div className="funnel-stage" key={stage[1]} onClick={() => notify(`查看${stage[1]}明细`)}><span className={`stage-icon c${index}`}>{stage[0]}</span><div><small>{stage[1]}</small><strong>{stage[2]}</strong><em>{stage[3]}</em></div>{index < 3 && <b className="arrow">→</b>}</div>)}
          <div className="coverage"><p>覆盖 6 个来源　·　<strong>1 个来源异常</strong></p><button onClick={() => notify("筛选原因：重复 56、低相关 19、低可信 9")}>查看筛选原因　›</button></div>
        </section>

        <div className="analysis-grid">
          <div className="left-column">
            <section className="panel trend-panel">
              <div className="panel-head"><div className="title-tabs"><h2>趋势与爆发信号</h2><button className={range === "24h" ? "selected" : ""} onClick={() => setRange("24h")}>24 小时</button><button className={range === "7d" ? "selected" : ""} onClick={() => setRange("7d")}>7 天</button></div><p>生命周期：萌芽　→　爆发　→　<b>扩散</b>　→　衰退</p></div>
              <div className="legend"><span><i className="blue" />Cursor 新版本</span><span><i className="green" />Copilot 安全功能</span><span><i className="amber" />Continue 融资</span><em>虚线为同类基线</em></div>
              <TrendChart range={range} selected={selectedId} />
            </section>

            <section className="hotspots-section">
              <div className="section-head"><h2>值得关注的热点 <span>（共 6 个）</span></h2><button onClick={() => notify("已按行动优先级排序")}>按行动优先级　⌄</button></div>
              {hotspots.map((item) => (
                <article key={item.id} className={`hotspot-card ${selectedId === item.id ? "selected" : ""}`} onClick={() => setSelectedId(item.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelectedId(item.id)}>
                  <span className="rank">{item.id}</span>
                  <div className="hotspot-main">
                    <div className="hotspot-title"><h3>{item.title}</h3><span className={`action-badge ${item.actionTone}`}>{item.action}</span></div>
                    <div className="signal-chips"><span>24h 讨论　<b>{item.discussions}</b></span><span>环比　<b className="up">{item.growth}</b></span><span>覆盖　<b>{item.platforms}</b></span><span>同类增速　<b>{item.percentile}</b></span></div>
                    {selectedId === item.id && <><div className="insight-grid"><p><b>为何上榜：</b>{item.why}</p><p><b>建议动作：</b>{item.advice}</p><p><b>争议焦点：</b>{item.debate}</p><p><b>风险：</b>{item.risk}</p><p><b>影响对象：</b>{item.impact}</p></div><div className="source-links">{item.sources.slice(0,3).map((s) => <button key={s.name} onClick={(e) => {e.stopPropagation(); notify(`${s.name}：演示证据入口`);}}><i>{s.short}</i>{s.name}　↗</button>)}<span>{item.sources.length - 1 || item.sources.length} 个独立信源</span></div></>}
                  </div>
                </article>
              ))}
              <button className="view-all" onClick={() => notify("其余 3 个热点已在完整报告中")}>查看其余 3 个热点　↓</button>
            </section>
          </div>

          <aside className="right-column">
            <section className="panel evidence-panel">
              <div className="panel-head"><h2>选中热点 <span>｜判断依据</span></h2></div>
              <div className="signal-composition"><div className="donut"><span>信号<br/><b>构成</b></span></div><div className="breakdown"><p><i className="blue" />增速 <b>35%</b></p><p><i className="green" />跨平台 <b>25%</b></p><p><i className="purple" />核心信源 <b>20%</b></p><p><i className="amber" />商业相关性 <b>20%</b></p></div><div className="confidence"><p><b>商业相关性：高</b><small>{selected.business}</small></p><p><b>事件真实性：{selected.truth}</b></p><p><b>聚类置信度：{selected.cluster}</b></p></div></div>
            </section>

            <section className="panel propagation">
              <div className="panel-head"><h2>传播路径</h2></div>
              <div className="source-path">{selected.sources.map((source, index) => <div className="source-node" key={source.name}><i>{source.short}</i><b>{source.name}</b><small>{source.time}</small>{index < selected.sources.length - 1 && <span>→</span>}</div>)}</div>
              <p>首发信源：<b>{selected.sources[0].name}</b></p>
            </section>

            <section className="panel key-evidence">
              <div className="panel-head"><h2>关键证据与反方观点</h2></div>
              {selected.evidence.map(([label, text], index) => <div className={`evidence-row e${index}`} key={label}><i>{index === 0 ? "✓" : index === 1 ? "−" : "!"}</i><b>{label}</b><span>{text}</span><button onClick={() => notify(`${label}详情为演示入口`)}>查看{index === 1 ? "讨论" : index === 2 ? "详情" : "证据"}　›</button></div>)}
            </section>

            <section className="agent-box">
              <div className="ask-row"><span>✦</span><input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => {if (e.key === "Enter" && question.trim()) { notify(`已提交追问：${question}`); setQuestion(""); }}} placeholder="追问：为什么继续扩散？还有哪些反对证据？"/><button aria-label="发送追问" onClick={() => { if (question.trim()) { notify(`已提交追问：${question}`); setQuestion(""); }}}>➤</button></div>
              <div className="quick-actions"><button onClick={() => notify("竞品简报已生成（演示）")}>▤　生成竞品简报</button><button onClick={() => notify("选题建议已生成（演示）")}>✎　生成选题</button><button onClick={() => notify("预警已设置（演示）")}>♧　设置预警</button></div>
            </section>
          </aside>
        </div>
      </section>
      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  );
}
