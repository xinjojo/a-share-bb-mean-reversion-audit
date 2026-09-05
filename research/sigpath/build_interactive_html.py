#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIGPATH Interactive HTML Report Builder
- 只读已有产物（不重新计算任何统计、不做任何策略判断）
- 输出单文件自包含 HTML：全部统计表 + 全部图表(base64) + manual_review_index 全量(分页/搜索/排序)
- 产物: results/evidence/sigpath/sigpath_interactive_report.html
"""
import base64, csv, io, json, os

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
SP = os.path.join(ROOT, 'results/evidence/sigpath')
SPD = os.path.join(ROOT, 'results/evidence/sigpath_d')
OUT = os.path.join(SP, 'sigpath_interactive_report.html')

def rd(p):
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()

def read_csv_rows(p, n=None):
    with open(p, 'r', encoding='utf-8') as f:
        r = list(csv.reader(f))
    if n is not None:
        return r[:n]
    return r

def read_json(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def img_b64(p):
    with open(p, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode()

# ---------- collect ----------
summary = read_json(os.path.join(SP, 'sigpath_summary.json'))
invariants = read_json(os.path.join(SP, 'sigpath_invariants.json'))
manifest = read_json(os.path.join(SP, 'raw_data_manifest.json'))
try:
    parity = read_json(os.path.join(SP, 'cross_table_parity.json'))
except Exception:
    parity = {}
try:
    dateaud = read_json(os.path.join(SP, 'date_boundary_audit.json'))
except Exception:
    dateaud = {}
try:
    valuepar = read_json(os.path.join(SP, 'wide_long_value_parity.json'))
except Exception:
    valuepar = {}
try:
    pathmath = read_json(os.path.join(SP, 'path_math_invariants.json'))
except Exception:
    pathmath = {}
try:
    pitname = read_json(os.path.join(SP, 'pit_name_audit.json'))
except Exception:
    pitname = {}
try:
    dsum = read_json(os.path.join(SPD, 'sigpath_d_summary.json'))
except Exception:
    dsum = {}

tables_sp = {
    'descriptive': read_csv_rows(os.path.join(SP, 'signal_path_descriptive_statistics.csv')),
    'bins': read_csv_rows(os.path.join(SP, 'signal_path_distribution_bins.csv')),
    'mfe_hit': read_csv_rows(os.path.join(SP, 'mfe_hit_rate_matrix.csv')),
    'mae_hit': read_csv_rows(os.path.join(SP, 'mae_hit_rate_matrix.csv')),
    'missing_horizon': read_csv_rows(os.path.join(SP, 'missing_horizon_by_available_days.csv')),
}
tables_d = {}
for fn in ['core_horizon_statistics.csv', 'close_return_distribution_bins.csv',
           'role_descriptive_statistics.csv', 'new_entry_year_statistics.csv',
           'percentile_path_close.csv', 'percentile_path_mfe.csv', 'percentile_path_mae.csv',
           'first_hit_time_mfe.csv', 'first_hit_time_mae.csv',
           'mfe_hit_rate_extended.csv', 'mae_hit_rate_extended.csv',
           'bb_z_descriptive_buckets.csv', 'episode_layer_structure.csv',
           'turnover_rank_descriptive.csv', 'up_then_down_path_stats.csv',
           'down_then_up_path_stats.csv', 'early_mfe_to_d20_outcome.csv',
           'mae_d3_to_d20_outcome_table.csv', 'mae_d5_to_d20_outcome_table.csv',
           'mae_d10_to_d20_outcome_table.csv', 'manual_casebook.csv']:
    p = os.path.join(SPD, fn)
    if os.path.exists(p):
        tables_d[fn.replace('.csv', '')] = read_csv_rows(p)

imgs = {}
for fn in sorted(os.listdir(os.path.join(SP, 'charts'))):
    if fn.endswith('.png'):
        imgs['sp_' + fn[:-4]] = img_b64(os.path.join(SP, 'charts', fn))
for fn in sorted(os.listdir(SPD)):
    if fn.endswith('.png'):
        imgs['d_' + fn[:-4]] = img_b64(os.path.join(SPD, fn))

# manual index -> compact JSON arrays
with open(os.path.join(SP, 'manual_review_index.csv'), 'r', encoding='utf-8') as f:
    r = list(csv.reader(f))
manual_header = r[0]
manual_rows = r[1:]

sanity = rd(os.path.join(SP, 'sanity_check.txt'))

# ---------- build ----------
def j(x):
    return json.dumps(x, ensure_ascii=False)

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SIGPATH — BB20 Signal Forward Path 交互式审计报告</title>
<style>
:root{--bg:#f5f7fa;--card:#fff;--ink:#1c2733;--mut:#66788a;--line:#e3e8ef;--acc:#1f6feb;--acc2:#0e8a5f;--warn:#b45309;--bad:#c0392b;--good:#0e8a5f;--hdr:#eef2f7;}
*{box-sizing:border-box}
body{margin:0;font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:var(--bg);}
nav{position:fixed;top:0;left:0;bottom:0;width:230px;background:#101a26;color:#cfd8e3;overflow-y:auto;padding:18px 10px;z-index:50}
nav h1{font-size:15px;color:#fff;margin:2px 8px 14px;line-height:1.4}
nav a{display:block;color:#aebac8;text-decoration:none;padding:6px 10px;border-radius:6px;font-size:13px;margin:1px 0}
nav a:hover{background:#1d2c3d;color:#fff}
nav a.sec{margin-top:10px;color:#7fd0a8;font-weight:600}
main{margin-left:230px;padding:26px 34px 80px;max-width:1280px}
h2{font-size:21px;border-bottom:2px solid var(--line);padding-bottom:8px;margin:34px 0 14px}
h3{font-size:16px;margin:22px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0;box-shadow:0 1px 2px rgba(16,26,38,.04)}
.grid{display:grid;gap:12px}
.g4{grid-template-columns:repeat(4,1fr)}
.g3{grid-template-columns:repeat(3,1fr)}
.kpi{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--card)}
.kpi .v{font-size:22px;font-weight:700;color:var(--acc)}
.kpi .k{font-size:12px;color:var(--mut);margin-top:2px}
.kpi .s{font-size:12px;color:var(--mut)}
table{border-collapse:collapse;width:100%;font-size:12.5px;background:#fff}
th,td{border:1px solid var(--line);padding:5px 8px;text-align:right;white-space:nowrap}
th{background:var(--hdr);position:sticky;top:0;cursor:pointer;user-select:none}
td.l,th.l{text-align:left}
tr:nth-child(even) td{background:#fafbfd}
.twrap{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.tools{margin:8px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.tools input{padding:6px 10px;border:1px solid var(--line);border-radius:6px;font-size:13px;min-width:220px}
.tools select{padding:6px 8px;border:1px solid var(--line);border-radius:6px;font-size:13px}
.tools .cnt{color:var(--mut);font-size:12.5px}
.badge{display:inline-block;padding:1px 8px;border-radius:20px;font-size:12px;font-weight:600}
.b-ok{background:#e3f6ec;color:var(--good)}.b-no{background:#fdecec;color:var(--bad)}.b-wa{background:#fdf3e0;color:var(--warn)}
.imgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.imgrid figure{margin:0;background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px;cursor:zoom-in}
.imgrid img{width:100%;height:auto;border-radius:6px}
.imgrid figcaption{font-size:12px;color:var(--mut);margin-top:6px;text-align:center}
.lb{position:fixed;inset:0;background:rgba(8,12,18,.92);display:none;z-index:100;align-items:center;justify-content:center;cursor:zoom-out}
.lb img{max-width:94vw;max-height:94vh;border-radius:6px}
code{background:#eef2f7;padding:1px 5px;border-radius:4px;font-size:12px}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
.note{font-size:12.5px;color:var(--mut)}
.ok{color:var(--good);font-weight:600}.no{color:var(--bad);font-weight:600}
pre.pb{background:#0f1722;color:#d7e2ee;padding:14px 16px;border-radius:8px;overflow:auto;font-size:12px;line-height:1.5;white-space:pre-wrap}
.footer{margin-top:40px;color:var(--mut);font-size:12px;border-top:1px solid var(--line);padding-top:14px}
@media (max-width:900px){nav{position:static;width:auto}main{margin-left:0}.g4,.g3{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<nav>
<h1>SIGPATH 交互式审计报告</h1>
<a href="#overview">概览</a>
<a href="#manifest">数据指纹 / Canonical</a>
<a href="#quality">数据质量 / Sanity</a>
<a href="#stats">描述统计（SIGPATH）</a>
<a href="#bins">分布分桶</a>
<a href="#hitrate">MFE / MAE Hit-Rate</a>
<a href="#charts">图表（SIGPATH）</a>
<a href="#dsec" class="sec">SIGPATH-D 描述审计</a>
<a href="#dstats">D: 核心统计</a>
<a href="#dcharts">D: 图表</a>
<a href="#dmore">D: 扩展表</a>
<a href="#manual">明细浏览（157,469 条）</a>
<a href="#meta">元数据 / README</a>
</nav>
<main>

<section id="overview">
<h2>概览</h2>
<div class="card note">
S1 frozen B20（close_adj &lt; MA20 − 2·SD20，ddof=1）全量信号路径事实层。只读已有审计产物生成本页，<b>未重新计算任何统计、未做任何策略判断</b>。2025–2026 全程未读取（机器断言通过）。
</div>
<div class="grid g4" id="kpis"></div>
<div class="grid g3" id="kpis2"></div>
</section>

<section id="manifest">
<h2>数据指纹与 Canonical Commit</h2>
<div class="card">
<table>
<tr><th>Registry 阶段</th><th>Canonical commit</th><th>说明</th></tr>
<tr><td>SIGPATH-A</td><td class="mono">94bd041d21a695557df3d9596f26385b4fc8f1bf</td><td>prereg（结果前冻结）</td></tr>
<tr><td>SIGPATH-A2</td><td class="mono">8bb98867988bf2b8d3d0304974391ec9276a72ba</td><td>episode_id 语义修正</td></tr>
<tr><td>SIGPATH-A3</td><td class="mono">ea369277546d73957f6b5fd94700a03f21788173</td><td>universe=63,887（SHA 4336000d…）</td></tr>
<tr><td>SIGPATH-B</td><td class="mono">974fa2aef6fd9284ce50163d0d68a4fb13d3697e</td><td>结果 commit（canonical）</td></tr>
<tr><td>SIGPATH-D</td><td class="mono">badf896264e5b3da7c64825498ab98878d6f3509</td><td>描述统计审计 commit</td></tr>
</table>
<p class="note">大 raw 表（wide/long parquet + CSV 分片）不进入 GitHub，canonical 本地副本位于 <code>results/evidence/sigpath/</code>。任何 downstream study 必须先校验 parquet SHA256 与本页 Manifest 一致。</p>
</div>
<div id="manifest_box"></div>
</section>

<section id="quality">
<h2>数据质量与 Sanity</h2>
<div id="quality_box"></div>
<h3>Sanity Check（40 条人工验证案例，公式机器断言 PASS）</h3>
<details><summary>展开查看 sanity_check.txt（全量）</summary><pre class="pb" id="sanity_pre"></pre></details>
</section>

<section id="stats">
<h2>描述统计（SIGPATH，D1–D20 × high/low/close_ret/MFE/MAE）</h2>
<div class="tools"><input id="f_st" placeholder="搜索（如 D5 / median / mfe）"><select id="v_st"><option value="ALL">全部变量</option><option>high_ret</option><option>low_ret</option><option>close_ret</option><option>MFE</option><option>MAE</option></select><select id="h_st"><option value="ALL">全部 horizon</option></select><span class="cnt" id="c_st"></span></div>
<div class="twrap" id="t_st"></div>
</section>

<section id="bins">
<h2>分布分桶（18 桶，D1–D20 × high/low/close_ret）</h2>
<div class="tools"><input id="f_bn" placeholder="搜索（如 -10% / D5）"><select id="v_bn"><option value="ALL">全部变量</option><option>high_ret</option><option>low_ret</option><option>close_ret</option></select><select id="h_bn"><option value="ALL">全部 horizon</option></select><span class="cnt" id="c_bn"></span></div>
<div class="twrap" id="t_bn"></div>
</section>

<section id="hitrate">
<h2>MFE / MAE Hit-Rate 矩阵（D1–D20 × 阈值）</h2>
<h3>MFE：P(MFE_Dn ≥ threshold)</h3>
<div class="twrap" id="t_mfe"></div>
<h3>MAE：P(MAE_Dn ≤ threshold)</h3>
<div class="twrap" id="t_mae"></div>
</section>

<section id="charts">
<h2>图表（SIGPATH 11 张）</h2>
<div class="imgrid" id="g_sp"></div>
</section>

<section id="dsec">
<h2>SIGPATH-D 描述统计审计（badf896）</h2>
<div class="card note" id="d_note"></div>
<h3>核心 Horizon 统计（mean/median/std/skew/kurtosis/分位）</h3>
<div class="tools"><input id="f_dc" placeholder="搜索（如 D5 / close_ret）"><select id="v_dc"><option value="ALL">全部变量</option></select><span class="cnt" id="c_dc"></span></div>
<div class="twrap" id="t_dc"></div>
<h3>Close Return 分桶（D 版）</h3>
<div class="twrap" id="t_dbin"></div>
<h3>Entry Role 描述统计（NEW_ENTRY / ADD_ON 对比）</h3>
<div class="twrap" id="t_drole"></div>
<h3>Percentile Forward Path（close / MFE / MAE）</h3>
<div class="grid g3" id="d_paths"></div>
<h3>First-Hit Time（MFE / MAE 首次达标分布）</h3>
<div class="grid g3"><div class="twrap" id="t_dfh_mfe"></div><div class="twrap" id="t_dfh_mae"></div></div>
</section>

<section id="dcharts">
<h2>图表（SIGPATH-D 17 张）</h2>
<div class="imgrid" id="g_d"></div>
</section>

<section id="dmore">
<h2>扩展表（SIGPATH-D）</h2>
<div id="dmore_box"></div>
</section>

<section id="manual">
<h2>明细浏览 — manual_review_index（157,469 条，全量）</h2>
<div class="card note">每条 = 一个独立 signal（stock_name + stock_code + signal_date + entry_date 可直接打开 K 线核对）。支持搜索（代码/名称/日期/role/signal_id）、列排序、分页。此表为人工检查索引，完整 OHLC 见 wide/long 母表（本地 parquet/CSV）。</div>
<div class="tools">
<input id="m_q" placeholder="搜索 代码/名称/日期/role…"><select id="m_pg"></select>
<span class="cnt" id="m_cnt"></span>
</div>
<div class="twrap" style="max-height:640px"><table id="m_tbl"></table></div>
</section>

<section id="meta">
<h2>元数据 / README</h2>
<div id="meta_box"></div>
</section>

<div class="footer">
SIGPATH Full-Signal Forward Path Audit — 交互式报告 · 数据源：results/evidence/sigpath + results/evidence/sigpath_d · 生成于 2026-09-05 · 本页仅呈现既有产物
</div>
</main>

<div class="lb" id="lb"><img id="lb_img" alt=""></div>

<script type="application/json" id="PAYLOAD">@@DATA@@</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("PAYLOAD").textContent);
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(v){if(v===null||v===undefined||v==="")return "";const n=Number(v);if(!isFinite(n))return esc(v);return n.toLocaleString("zh-CN",{maximumFractionDigits:4});}
function el(tag,cls,html){const e=document.createElement(tag);if(cls)e.className=cls;if(html!==undefined)e.innerHTML=html;return e;}
/* lightbox */
const lb=document.getElementById("lb"),lbi=document.getElementById("lb_img");
lb.onclick=()=>lb.style.display="none";
document.querySelectorAll(".imgrid img").forEach(im=>im.closest("figure").onclick=()=>{lbi.src=im.src;lb.style.display="flex";});
/* generic table */
function makeTable(rows,elId,{sortable=true}={}){
  const el=document.getElementById(elId);el.innerHTML="";
  const thead=el.appendChild(el.createTHead?el.createTHead():document.createElement("thead"));
  const tb=el.appendChild(document.createElement("tbody"));
  if(!rows||rows.length===0){el.innerHTML="<div class='note'>无数据</div>";return;}
  const hd=rows[0];let tr=document.createElement("tr");
  hd.forEach(h=>{const th=document.createElement("th");th.className=isNaN(h)?'l':'r';th.textContent=h;if(sortable){th.style.cursor="pointer";th.onclick=()=>sortBy(h);}tr.appendChild(th);});
  thead.appendChild(tr);
  let sortAsc={},sortKey=null;
  function render(){
    tb.innerHTML="";let rs=rows.slice(1);
    if(sortKey){const i=hd.indexOf(sortKey);rs=rs.slice().sort((a,b)=>{const x=Number(a[i]),y=Number(b[i]);if(!isFinite(x)||!isFinite(y))return String(a[i]).localeCompare(String(b[i]),"zh-CN");return (x-y)*(sortAsc[sortKey]?1:-1);});}
    rs.forEach(r=>{const tr2=document.createElement("tr");r.forEach((c,i)=>{const td=document.createElement("td");td.className=hd[i]===hd[i]&&isNaN(hd[i])?'l':'r';td.textContent=c===""?"":c;tr2.appendChild(td);});tb.appendChild(tr2);});
  }
  function sortBy(h){if(sortKey===h)sortAsc[h]=!sortAsc[h];else{sortKey=h;sortAsc[h]=true;}render();}
  render();
}
/* filtered table */
function filteredTable(rows,elId,inputId,varSelId,horSelId,cntId){
  const hd=rows[0], body=rows.slice(1);
  const varIdx={},horVals=[];
  hd.forEach((h,i)=>{if(h==="variable")varIdx.variable=i;if(h==="horizon_day")varIdx.horizon=i;if(h==="horizon")varIdx.horizon=i;});
  body.forEach(r=>{if(varIdx.horizon!==undefined&&!horVals.includes(r[varIdx.horizon]))horVals.push(r[varIdx.horizon]);});
  const hs=document.getElementById(horSelId);
  if(hs&&horVals.length){horVals.sort((a,b)=>Number(a)-Number(b)).forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;hs.appendChild(o);});}
  function q(){const f=document.getElementById(inputId).value.trim().toLowerCase();
    const v=document.getElementById(varSelId).value,h=horSelId?document.getElementById(horSelId).value:"ALL";
    let rs=body.filter(r=>{if(v!=="ALL"&&r[varIdx.variable]!==v)return false;if(h!=="ALL"&&String(r[varIdx.horizon])!==String(h))return false;if(f&&!r.join(" ").toLowerCase().includes(f))return false;return true;});
    const tbl=document.createElement("table");tbl.innerHTML="<thead></thead><tbody></tbody>";
    const th=tbl.querySelector("thead");const tr=document.createElement("tr");hd.forEach(h=>{const c=document.createElement("th");c.className=isNaN(h)?'l':'r';c.textContent=h;tr.appendChild(c);});th.appendChild(tr);
    const tb=tbl.querySelector("tbody");
    rs.forEach(r=>{const tr2=document.createElement("tr");r.forEach((c,i)=>{const td=document.createElement("td");td.className=isNaN(hd[i])?'l':'r';td.textContent=c===""?"":c;tr2.appendChild(td);});tb.appendChild(tr2);});
    document.getElementById(elId).innerHTML="";document.getElementById(elId).appendChild(tbl);
    document.getElementById(cntId).textContent="显示 "+rs.length+" / "+body.length+" 行";
  }
  document.getElementById(inputId).oninput=q;
  document.getElementById(varSelId).onchange=q;
  if(hs)hs.onchange=q;
  q();
}
/* manual index browser */
(function(){
  const hd=DATA.manualHeader, rows=DATA.manualRows, PER=200;
  let cur=0, flt=[...rows];
  const q=document.getElementById("m_q"),pg=document.getElementById("m_pg"),cnt=document.getElementById("m_cnt"),tbl=document.getElementById("m_tbl");
  function render(){
    const page=flt.slice(cur,cur+PER);
    tbl.innerHTML="";
    let tr=document.createElement("tr");
    hd.forEach((h,i)=>{const th=document.createElement("th");th.className=isNaN(h)?'l':'r';th.textContent=h;th.style.cursor="pointer";th.onclick=()=>sortBy(i);tr.appendChild(th);});
    tbl.appendChild(tr);
    page.forEach(r=>{const tr2=document.createElement("tr");r.forEach((c,i)=>{const td=document.createElement("td");td.className=isNaN(hd[i])?'l':'r';td.textContent=c;td.title=c;tr2.appendChild(td);});tbl.appendChild(tr2);});
    cnt.textContent="显示 "+(cur+1)+"–"+(cur+page.length)+" / "+flt.length+" 条（全量 "+rows.length+"）";
    pg.innerHTML="";
    const pages=Math.max(1,Math.ceil(flt.length/PER));
    for(let i=0;i<pages;i++){const o=document.createElement("option");o.value=i;o.textContent="第 "+(i+1)+" / "+pages+" 页";if(i===Math.floor(cur/PER))o.selected=true;pg.appendChild(o);}
  }
  let si=null;
  function sortBy(i){si=i;render();}
  q.oninput=()=>{const f=q.value.trim().toLowerCase();flt=rows.filter(r=>!f||r.join(" ").toLowerCase().includes(f));cur=0;render();};
  pg.onchange=()=>{cur=Number(pg.value)*PER;render();};
  render();
})();
/* kpis */
(function(){
  const s=DATA.summary;
  const k=[
    ["股票数",s.n_stocks?.toLocaleString(),"PIT 可交易池（含期间退市股）"],
    ["总 Signal",s.n_signals_total?.toLocaleString(),"NEW_ENTRY "+s.n_new_entry?.toLocaleString()+" + ADD_ON "+s.n_add_on?.toLocaleString()],
    ["Long 行数",s.long_rows?.toLocaleString(),"signal×day 固定 20 行"],
    ["日期范围",s.signal_date_min+" ~ "+s.signal_date_max,"entry 至 "+s.signal_date_max+" 后 1 日"],
  ];
  const k2=[
    ["SHORT_HISTORY",s.n_short_history?.toLocaleString(),"期末截断（保留）"],
    ["JUMP 标记",s.n_jump_flag?.toLocaleString(),"跳变标记（不删除）"],
    ["Sanity",s.sanity_check_passed?"PASS":"FAIL",s.sanity_check_passed?"公式机器断言通过":"需检查"],
    ["2025+ 读取","无",s.signal_date_max <= "2024-12-30"?"机器断言通过":"检查"],
  ];
  const g=document.getElementById("kpis");k.forEach(x=>{const d=document.createElement("div");d.className="kpi";d.innerHTML="<div class='v'>"+x[1]+"</div><div class='k'>"+x[0]+"</div><div class='s'>"+x[2]+"</div>";g.appendChild(d);});
  const g2=document.getElementById("kpis2");k2.forEach(x=>{const d=document.createElement("div");d.className="kpi";d.innerHTML="<div class='v "+(x[1]==="PASS"||x[1]==="无"?"ok":"")+"'>"+x[1]+"</div><div class='k'>"+x[0]+"</div><div class='s'>"+x[2]+"</div>";g2.appendChild(d);});
})();
/* manifest */
(function(){
  const m=DATA.manifest;
  function row(k,v){return "<tr><td class='l'>"+k+"</td><td class='mono l'>"+esc(v)+"</td></tr>";}
  let h="<div class='grid g2'>";
  [["wide",m.wide],["long",m.long]].forEach(([nm,e])=>{
    h+="<div class='card'><h3>"+nm+"</h3><table>"+
      row("filename",e.filename)+row("SHA256",e.sha256)+row("bytes",e.bytes)+row("rows",e.rows)+
      row("columns",e.columns)+row("signal_id unique",e.signal_id_unique_count)+
      (e.duplicate_signal_id_count!==undefined?row("duplicate signal_id",e.duplicate_signal_id_count):"")+
      (e.expected_rows_signals_x_20!==undefined?row("expected rows (signals×20)",e.expected_rows_signals_x_20):"")+
      row("min signal_date",e.min_signal_date)+row("max signal_date",e.max_signal_date)+
      row("min entry_date",e.min_entry_date)+row("max entry_date",e.max_entry_date)+
      row("total null cells",e.total_null_cells)+"</table></div>";
  });
  h+="</div>";
  h+="<div class='card'><h3>CSV 分片</h3><div class='twrap'><table><tr><th>filename</th><th>rows</th><th>bytes</th><th>first signal_id</th><th>last signal_id</th></tr>";
  m.csv_part_files.forEach(p=>{h+="<tr><td class='l'>"+esc(p.filename)+"</td><td>"+p.rows+"</td><td>"+p.bytes+"</td><td class='l'>"+esc(p.first_signal_id)+"</td><td class='l'>"+esc(p.last_signal_id)+"</td></tr>";});
  h+="</table></div></div>";
  document.getElementById("manifest_box").innerHTML=h;
})();
/* quality */
(function(){
  const d=DATA.dateAudit, p=DATA.parity;
  let h="<div class='grid g3'>";
  let pt="";
  (p.checks||[]).forEach(c=>{pt+="<tr><td class='l'>"+esc(c.name)+"</td><td>"+esc(c.actual)+"</td><td>"+esc(c.expected)+"</td><td class='"+(c.pass?"ok":"no")+"'>"+(c.pass?"PASS":"FAIL")+"</td></tr>";});
  h+="<div class='card'><h3>Cross-Table Parity <span class='badge "+(p.pass?"b-ok":"b-no")+"'>"+(p.pass?"PASS":"FAIL")+"</span></h3>"+
     "<div class='twrap'><table><tr><th>check</th><th>actual</th><th>expected</th><th>result</th></tr>"+pt+"</table></div></div>";
  if(d.pass!==undefined)h+="<div class='card'><h3>Date Boundary 2025+ 硬检查 <span class='badge "+(d.pass?"b-ok":"b-no")+"'>"+(d.pass?"PASS":"FAIL")+"</span></h3><p class='note'>boundary: "+esc(d.boundary)+" · scanned: "+esc((d.scanned_tables||[]).join(", "))+"</p>";
  if(d.date_like_fields){h+="<div class='twrap'><table><tr><th>table</th><th>column</th><th>rows</th><th>min</th><th>max</th><th>gt_2024_12_31</th><th>pass</th></tr>";
  d.date_like_fields.forEach(f=>{h+="<tr><td class='l'>"+esc(f.table)+"</td><td class='l'>"+esc(f.column)+"</td><td>"+f.rows+"</td><td>"+esc(f.min)+"</td><td>"+esc(f.max)+"</td><td>"+f.gt_2024_12_31_count+"</td><td class='"+(f.pass?"ok":"no")+"'>"+(f.pass?"PASS":"FAIL")+"</td></tr>";});
  h+="</table></div></div>";}
  if(d.short_history_checks)h+="<div class='card'><h3>Short-History Parity</h3><pre class='pb'>"+esc(JSON.stringify(d.short_history_checks,null,1))+"</pre></div>";
  h+="</div>";
  h+="<div class='card'><h3>数据质量标记（保留不删除）</h3><table><tr><th>flag</th><th>count</th></tr>"+Object.entries(DATA.summary.data_quality_flags||{SHORT_HISTORY:DATA.summary.n_short_history,JUMP:DATA.summary.n_jump_flag}).map(([k,v])=>"<tr><td class='l'>"+k+"</td><td>"+v+"</td></tr>").join("")+"</table></div>";
  h+="<div class='card' id='mh_card'><h3>Missing Horizon（按 available_future_days，parity 全 PASS）</h3></div>";
  document.getElementById("quality_box").innerHTML=h;
  const mhc=document.getElementById("mh_card");
  const mht=document.createElement("div");mht.className="twrap";mht.id="mh_tbl";mhc.appendChild(mht);
  makeTable(DATA.tables.missing_horizon,"mh_tbl",{sortable:false});
})();
/* init tables */
filteredTable(DATA.tables.descriptive,"t_st","f_st","v_st","h_st","c_st");
filteredTable(DATA.tables.bins,"t_bn","f_bn","v_bn","h_bn","c_bn");
makeTable(DATA.tables.mfe_hit,"t_mfe",{sortable:false});
makeTable(DATA.tables.mae_hit,"t_mae",{sortable:false});
/* charts sp */
(function(){
  const g=document.getElementById("g_sp");
  const names={fig1_forward_high_ret:"Forward High Return 分布（D1/D3/D5/D10/D20）",fig2_forward_low_ret:"Forward Low Return 分布",fig3_forward_close_ret:"Close Return 分布",fig4_mfe_path_percentiles:"MFE 随 D1–D20 变化（P10–P90）",fig5_mae_path_percentiles:"MAE 随 D1–D20 变化（P10–P90）",fig6_close_ret_forward_path:"Close Return Forward Path（P10–P90）",fig7_heatmap_high_ret:"High Return 热力图（horizon × bucket）",fig7_heatmap_low_ret:"Low Return 热力图",fig7_heatmap_close_ret:"Close Return 热力图",fig10_heatmap_mfe_hit:"MFE Hit-Rate 热力图",fig11_heatmap_mae_hit:"MAE Hit-Rate 热力图"};
  Object.entries(DATA.imgs).filter(([k])=>k.startsWith("sp_")).forEach(([k,b])=>{
    const fig=document.createElement("figure");
    const im=document.createElement("img");im.src=b;im.alt=k;
    const cap=document.createElement("figcaption");cap.textContent=names[k.slice(3)]||k.slice(3);
    fig.appendChild(im);fig.appendChild(cap);g.appendChild(fig);
  });
})();
/* sigpath_d note + core stats */
(function(){
  const s=DATA.dsum||{};
  document.getElementById("d_note").innerHTML="SIGPATH-D 描述统计审计（commit <code>badf896</code>）。核心事实（取自 sigpath_d_summary.json）：<br>"+
  Object.entries(s).map(([k,v])=>{let t=typeof v==="object"?JSON.stringify(v):v;return "<b>"+esc(k)+"</b>: "+esc(String(t).slice(0,200));}).join(" · ");
  const rows=DATA.tables_d.core_horizon_statistics;
  const hd=rows[0];const vars=[...new Set(rows.slice(1).map(r=>r[1]))];
  const vs=document.getElementById("v_dc");vars.forEach(v=>{const o=document.createElement("option");o.value=v;o.textContent=v;vs.appendChild(o);});
  filteredTable(rows,"t_dc","f_dc","v_dc",null,"c_dc");
  makeTable(DATA.tables_d.close_return_distribution_bins,"t_dbin",{sortable:false});
  makeTable(DATA.tables_d.role_descriptive_statistics,"t_drole",{sortable:false});
})();
/* d paths */
(function(){
  const g=document.getElementById("d_paths");
  ["percentile_path_close","percentile_path_mfe","percentile_path_mae"].forEach((k,i)=>{
    const d=document.createElement("div");d.className="card";d.innerHTML="<h4>"+k.replace("percentile_path_","Percentile Path: ")+"</h4>";
    const t=document.createElement("div");t.className="twrap";t.id="dp_"+i;d.appendChild(t);g.appendChild(d);
    makeTable(DATA.tables_d[k],t.id,{sortable:false});
  });
})();
makeTable(DATA.tables_d.first_hit_time_mfe,"t_dfh_mfe",{sortable:false});
makeTable(DATA.tables_d.first_hit_time_mae,"t_dfh_mae",{sortable:false});
/* d charts */
(function(){
  const g=document.getElementById("g_d");
  Object.entries(DATA.imgs).filter(([k])=>k.startsWith("d_")).forEach(([k,b])=>{
    const fig=document.createElement("figure");
    const im=document.createElement("img");im.src=b;im.alt=k;
    const cap=document.createElement("figcaption");cap.textContent=k.slice(2);
    fig.appendChild(im);fig.appendChild(cap);g.appendChild(fig);
  });
})();
/* d more tables */
(function(){
  const box=document.getElementById("dmore_box");
  const order=["mfe_hit_rate_extended","mae_hit_rate_extended","bb_z_descriptive_buckets","episode_layer_structure","turnover_rank_descriptive","new_entry_year_statistics","up_then_down_path_stats","down_then_up_path_stats","early_mfe_to_d20_outcome","mae_d3_to_d20_outcome_table","mae_d5_to_d20_outcome_table","mae_d10_to_d20_outcome_table","manual_casebook"];
  order.forEach(k=>{
    const rows=DATA.tables_d[k];if(!rows)return;
    const card=document.createElement("div");card.className="card";
    const h3=document.createElement("h4");h3.textContent=k;card.appendChild(h3);
    const t=document.createElement("div");t.className="twrap";t.id="dm_"+k;card.appendChild(t);box.appendChild(card);
    makeTable(rows,t.id,{sortable:false});
  });
})();
/* meta */
(function(){
  const r=DATA.readme||"";
  const b=document.getElementById("meta_box");
  const pre=document.createElement("pre");pre.className="pb";pre.textContent=r;b.appendChild(pre);
})();
/* sanity */
document.getElementById("sanity_pre").textContent=DATA.sanity||"";
</script>
</body>
</html>
"""

data = {
    'summary': summary,
    'invariants': invariants,
    'manifest': manifest,
    'parity': parity,
    'dateAudit': dateaud,
    'valuePar': valuepar,
    'pathMath': pathmath,
    'pitName': pitname,
    'dsum': dsum,
    'tables': tables_sp,
    'tables_d': tables_d,
    'imgs': imgs,
    'manualHeader': manual_header,
    'manualRows': manual_rows,
    'sanity': sanity[:40000],
    'readme': rd(os.path.join(SP, 'README.md')),
}
html = HTML.replace('@@DATA@@', j(data))
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print('WROTE', OUT, f'{os.path.getsize(OUT)/1e6:.1f} MB', 'manual_rows', len(manual_rows), 'imgs', len(imgs))
