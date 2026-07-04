#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Task2 HTML: full 6-indicator dashboard for 002281 with formula docs.
Then save PDF via Chrome headless.
"""
import json, os, subprocess, time

BASE = "/Users/skyler/workspace/stock_selection/announcement_alpha"
DATA_JSON = os.path.join(BASE, "data/stock_analysis/data.json")
OUT_HTML  = os.path.join(BASE, "Task2.html")
OUT_PDF   = os.path.join(BASE, "task2_output/Task2.pdf")

# ─── Load real data ────────────────────────────────────────────
with open(DATA_JSON, "r", encoding="utf-8") as f:
    payload = json.load(f)
records = payload["records"]

# ─── Compute ATR, WR, CR (data.json lacks these) ────────────────
prev_close = None
bull_powers = []
bear_powers = []

for i, r in enumerate(records):
    C = r["close"]; H = r["high"]; L = r["low"]
    # --- ATR (14) ---
    if prev_close is None:
        tr = H - L
    else:
        tr = max(H - L, abs(H - prev_close), abs(L - prev_close))
    r["tr"] = tr
    prev_close = C
    if i >= 13:
        r["atr"] = round(sum(records[j]["tr"] for j in range(i - 13, i + 1)) / 14, 4)
    else:
        r["atr"] = None
    # --- Williams %R (14) ---
    if i >= 13:
        hh = max(records[j]["high"] for j in range(i - 13, i + 1))
        ll = min(records[j]["low"]  for j in range(i - 13, i + 1))
        denom = hh - ll
        r["wr"] = round(-100 * (hh - C) / denom if denom else 0, 2)
    else:
        r["wr"] = None
    # --- CR (Energy Index, N=26) ---
    if i == 0:
        pm_prev = (H + L + C) / 3
    else:
        pm_prev = (records[i - 1]["high"] + records[i - 1]["low"] + records[i - 1]["close"]) / 3
    bp = max(H - pm_prev, 0)
    bp2 = max(pm_prev - L, 0)
    r["bp"] = bp; r["bp2"] = bp2
    bull_powers.append(bp); bear_powers.append(bp2)
    if i >= 25:
        bsum = sum(records[j]["bp"] for j in range(i - 25, i + 1))
        bsum2 = sum(records[j]["bp2"] for j in range(i - 25, i + 1))
        r["cr"] = round(100 * bsum / bsum2 if bsum2 else 100, 2)
    else:
        r["cr"] = None

latest = records[-1]
summary = payload["summary"]

# ─── Build HTML ─────────────────────────────────────────────────
def _j(obj): return json.dumps(obj, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Task 2 — 光迅科技(002281.SZ) 六大技术指标</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(135deg, #1e3a8a 0%, #6366f1 50%, #8b5cf6 100%);
    min-height:100vh; padding:20px;
  }}
  .container {{ max-width:1400px; margin:0 auto; }}
  .card {{
    background: rgba(255,255,255,0.97);
    border-radius:14px; box-shadow:0 8px 30px rgba(0,0,0,0.12);
    margin-bottom:24px; padding:28px;
  }}
  .header {{ text-align:center; color:white; padding:30px 0 10px; }}
  .header h1 {{ font-size:2.4rem; font-weight:800; letter-spacing:1px; }}
  .header h2 {{ font-size:1.2rem; font-weight:400; opacity:0.9; margin-top:6px; }}
  .header small {{ font-size:0.85rem; opacity:0.75; }}
  .section-title {{
    font-size:1.35rem; font-weight:700; color:#1e3a8a;
    margin-bottom:16px; padding-bottom:8px;
    border-bottom:3px solid #818cf8;
    display:flex; align-items:center; gap:10px;
  }}
  .section-title .num {{
    display:inline-flex; align-items:center; justify-content:center;
    width:34px; height:34px; border-radius:50%;
    background:linear-gradient(135deg,#6366f1,#8b5cf6);
    color:white; font-size:0.9rem; font-weight:700;
  }}
  .chart-row {{ width:100%; height:400px; }}
  .formula-box {{
    background:linear-gradient(135deg, #f0f4ff, #e0e7ff);
    border-left:5px solid #6366f1;
    border-radius:8px; padding:16px 20px;
    margin-bottom:16px;
  }}
  .formula-box h4 {{
    color:#3730a3; font-size:1rem; margin-bottom:8px;
  }}
  .formula-box .formula {{
    font-family: "Courier New", monospace; font-size:0.95rem;
    background:white; padding:8px 12px; border-radius:6px;
    margin:6px 0; line-height:1.6; color:#1e293b;
  }}
  .formula-box .desc {{
    color:#475569; font-size:0.92rem; line-height:1.7;
  }}
  .signal-grid {{
    display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
    gap:14px; margin-bottom:20px;
  }}
  .signal-card {{
    background:white; border-radius:10px; padding:16px;
    border:2px solid #e5e7eb; transition:transform 0.2s;
  }}
  .signal-card:hover {{ transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.1); }}
  .signal-card h5 {{ font-size:1rem; margin-bottom:6px; }}
  .signal-card p {{ color:#475569; font-size:0.88rem; line-height:1.5; }}
  .badge-bull {{ background:#dcfce7; color:#166534; border-color:#86efac; }}
  .badge-bear {{ background:#fee2e2; color:#991b1b; border-color:#fca5a5; }}
  .badge-neu  {{ background:#fef3c7; color:#92400e; border-color:#fcd34d; }}
  .stat-bar {{
    display:flex; justify-content:space-around; flex-wrap:wrap;
    background:linear-gradient(135deg,#312e81,#1e3a8a); color:white;
    border-radius:10px; padding:20px; gap:20px;
  }}
  .stat-item {{ text-align:center; }}
  .stat-item .val {{ font-size:1.5rem; font-weight:700; }}
  .stat-item .lbl {{ font-size:0.8rem; opacity:0.85; margin-top:4px; }}
  .disclaimer {{
    text-align:center; color:rgba(255,255,255,0.7);
    font-size:0.82rem; margin-top:30px; padding-bottom:20px;
  }}
  @media (max-width:768px) {{ .chart-row {{ height:300px; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 Task 2 — 六大技术指标深度解析</h1>
    <h2>光迅科技 (002281.SZ)</h2>
    <small>数据区间：{records[0]["date"]} ~ {records[-1]["date"]} | {len(records)} 个交易日</small>
  </div>

  <!-- ===== 统计概览 ===== -->
  <div class="card">
    <div class="section-title"><span class="num">0</span> 实时指标概览</div>
    <div class="stat-bar">
      <div class="stat-item"><div class="val">{latest["close"]}</div><div class="lbl">收盘价 CNY</div></div>
      <div class="stat-item"><div class="val">{summary["year_high"]}</div><div class="lbl">年内最高</div></div>
      <div class="stat-item"><div class="val">{summary["year_low"]}</div><div class="lbl">年内最低</div></div>
      <div class="stat-item"><div class="val">{latest.get("rsi14","0"):.1f}</div><div class="lbl">RSI(14)</div></div>
      <div class="stat-item"><div class="val">{latest.get("atr",0):.2f}</div><div class="lbl">ATR(14)</div></div>
      <div class="stat-item"><div class="val">{latest.get("cr","0"):.1f}</div><div class="lbl">CR(26)</div></div>
    </div>
  </div>

  <!-- ===== 信号卡片 ===== -->
  <div class="card">
    <div class="section-title"><span class="num">1</span> 信号综合判断</div>
    <div class="signal-grid">
"""

# Generate signal cards
for s in summary["signals"]:
    tone_map = {"bullish":("badge-bull","🟢"), "bearish":("badge-bear","🔴"), "neutral":("badge-neu","🟡")}
    cls, emo = tone_map.get(s["tone"], ("badge-neu","🟡"))
    html += f"""      <div class="signal-card {cls}">
        <h5>{emo} {s["category"]}</h5>
        <p>{s["description"]}</p>
      </div>
"""

# Add new signals for ATR, WR, CR
attr_val = latest.get("atr")
wr_val = latest.get("wr")
cr_val = latest.get("cr")

if attr_val:
    pct = attr_val / latest["close"] * 100
    tone = "bearish" if pct > 4 else "bullish" if pct < 1.5 else "neutral"
    cls, emo = tone_map[tone]
    html += f"""      <div class="signal-card {cls}">
        <h5>{emo} ATR</h5>
        <p>当前ATR={attr_val:.2f}，占股价{pct:.2f}%。{'波动较大，适合缩小仓位或加大止损' if pct > 3 else '波动温和，可正常操作' if pct > 1.5 else '波动极小，变盘临近'}</p>
      </div>
"""
if wr_val is not None:
    tone = "bearish" if wr_val > -20 else "bullish" if wr_val < -80 else "neutral"
    cls, emo = tone_map[tone]
    html += f"""      <div class="signal-card {cls}">
        <h5>{emo} Williams %R</h5>
        <p>WR(14)={wr_val:.2f}。{'超买区间' if wr_val > -20 else '超卖区间，关注反弹' if wr_val < -80 else '中性区间'}</p>
      </div>
"""
if cr_val:
    tone = "bearish" if cr_val > 200 else "bullish" if cr_val < 40 else "neutral"
    cls, emo = tone_map[tone]
    html += f"""      <div class="signal-card {cls}">
        <h5>{emo} CR 能量指标</h5>
        <p>CR(26)={cr_val:.2f}。{'多方极强，警惕回调' if cr_val > 200 else '多方强势' if cr_val > 100 else '空方占据优势，关注支撑' if cr_val > 60 else '空方极强，关注反弹'}</p>
      </div>
"""

html += """    </div>
  </div>

<!-- ===================================================================== -->
<!--  INDICATOR PAGES                                                     -->
<!-- ===================================================================== -->

"""

# ===================  1. RSI  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">2</span> RSI 相对强弱指标（Relative Strength Index）</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      Δ = Close[t] − Close[t−1]<br>
      Gain = max(Δ, 0) &nbsp;&nbsp; Loss = −min(Δ, 0)<br>
      AvgGain = EMA(Gain, 14) &nbsp;&nbsp; AvgLoss = EMA(Loss, 14)<br>
      <b>RS = AvgGain / AvgLoss</b><br>
      <b>RSI = 100 − 100 / (1 + RS)</b>
    </div>
    <div class="desc">
      使用 Wilder 指数平滑（EMA 乘数 α = 1/14），初始种子取前 14 期 SMA。RSI 值域 [0, 100]。
    </div>
  </div>

  <div class="formula-box">
    <h4>🎯 作用与判读</h4>
    <div class="formula">
      RSI &gt; 70 → 超买（overbought）→ 关注回调风险<br>
      RSI &lt; 30 → 超卖（oversold）→ 关注反弹机会<br>
      RSI = 50  → 多空均衡线
    </div>
    <div class="desc">
      RSI 是动量震荡器，衡量近期涨跌强弱。RSI 与价格顶背离常预示顶部反转；
      底背离则预示底部反转。常用于短线交易择时与仓位管理。
    </div>
  </div>

  <div id="chart-rsi" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>最新 RSI(14) = {latest.get("rsi14", 0):.2f}</b>
    {"→ 超卖区间，关注反弹信号" if latest.get("rsi14", 50) < 30 else
      "→ 超买区间，警惕回调" if latest.get("rsi14", 50) > 70 else
      "→ 中性区间，多空力量均衡"}
  </div>
</div>

"""

# ===================  2. MACD  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">3</span> MACD 指数平滑异同移动平均线</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      EMA_fast = EMA(Close, 12) &nbsp;&nbsp; EMA_slow = EMA(Close, 26)<br>
      <b>DIF  = EMA_fast − EMA_slow</b><br>
      <b>DEA  = EMA(DIF, 9)</b><br>
      <b>MACD = 2 × (DIF − DEA)</b> &nbsp;（中国 A 股惯例乘以 2）<br>
      其中 EMA 乘数 α = 2/(N+1)
    </div>
  </div>

  <div class="formula-box">
    <h4>🎯 作用与判读</h4>
    <div class="formula">
      DIF &gt; DEA（金叉）→ 看多信号<br>
      DIF &lt; DEA（死叉）→ 看空信号<br>
      MACD 柱 &gt; 0 → 多头动能增强<br>
      MACD 柱 &lt; 0 → 空头动能增强<br>
      DIF/DEA 位于零轴上方 → 中长期趋势偏多
    </div>
    <div class="desc">
      MACD 兼具趋势与动量双重特性。DIF 从下方上穿零轴是中线入场点；
      MACD 柱由缩小转为放大常标志趋势加速；与价格顶/底背离为高可靠信号。
    </div>
  </div>

  <div id="chart-macd" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>最新 DIF={latest["dif"]:.4f} / DEA={latest["dea"]:.4f} / MACD={latest["macd"]:.4f}</b><br>
    {"→ DIF 在 DEA 上方，金叉状态" if latest["dif"] > latest["dea"] else "→ DIF 跌破 DEA，死叉状态"}
    {"，DIF 位于零轴上方" if latest["dif"] > 0 else "，DIF 已跌破零轴"}
  </div>
</div>

"""

# ===================  3. Bollinger Bands  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">4</span> 布林带（Bollinger Bands）</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      MID  = SMA(Close, 20) &nbsp;（20日简单均线）<br>
      σ    = StdDev(Close, 20)<br>
      <b>UP   = MID + 2σ</b><br>
      <b>LOW  = MID − 2σ</b><br>
      带宽 = (UP − LOW) / MID
    </div>
  </div>

  <div class="formula-box">
    <h4>🎯 作用与判读</h4>
    <div class="formula">
      价格触及上轨 → 超买，趋势极强或见顶<br>
      价格触及下轨 → 超卖，趋势极弱或见底<br>
      带宽收窄（Squeeze）→ 波动收缩，预示即将爆发<br>
      价格持续在上轨上方 → 超强趋势<br>
      上下轨开口扩大 → 趋势加速
    </div>
    <div class="desc">
      布林带是衡量波动率最常用的通道工具。95% 的价格落在 ±2σ 范围内；
      价格突破上/下轨时约 5% 概率——属极端事件。
      常配合 RSI 等确认顶底。
    </div>
  </div>

  <div id="chart-boll" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>上轨={latest["boll_up"]:.2f} / 中轨={latest["boll_mid"]:.2f} / 下轨={latest["boll_dn"]:.2f}</b><br>
    {"→ 价格在下轨附近，超卖" if latest["close"] <= latest["boll_dn"] * 1.02 else
       "→ 价格在中轨上方，偏强" if latest["close"] > latest["boll_mid"] else
       "→ 价格在中轨与下轨之间，弱势整理"}
  </div>
</div>

"""

# ===================  4. ATR  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">5</span> ATR 真实波幅（Average True Range）</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      前一收盘价 = Close[t−1]<br>
      <b>TR = max( H−L,<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|H − Close_prev|,<br>
      &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|L − Close_prev|)</b><br>
      <b>ATR = SMA(TR, 14)</b><br>
      （亦可用 Wilder EMA 平滑）
    </div>
    <div class="desc">
      TR 能捕捉跳空缺口，比单纯 H−L 更全面反映每日真实风险。
    </div>
  </div>

  <div class="formula-box">
    <h4> 作用与判读</h4>
    <div class="formula">
      止损位 = 入场价 ± 1.5~2 × ATR<br>
      仓位 = 风险金额 / (N × ATR)<br>
      ATR 走高 → 波动扩张，趋势进行中或恐慌蔓延<br>
      ATR 走低 → 波动收敛，变盘临近
    </div>
    <div class="desc">
      ATR 不以方向为判读，是量化仓位与止损的首选工具。
      海龟交易系统即使用 2×ATR 作为止损距离；
      Van Tharp 建议单笔风险不超过 1% 本金。
    </div>
  </div>

  <div id="chart-atr" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>最新 ATR(14) = {latest.get("atr",0):.2f} &nbsp;|&nbsp; 占股价 {(latest.get("atr",0)/latest["close"]*100):.2f}%</b><br>
    {"→ 高波动，需缩仓或放大止损" if latest.get("atr",0)/latest["close"] > 0.03 else
       "→ 低波动，等待变盘信号" if latest.get("atr",0)/latest["close"] < 0.01 else
       "→ 波动适中，可正常交易"}
  </div>
</div>

"""

# ===================  5. WR  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">6</span> WR 威廉指标（Williams %R）</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      HH = RollingMax(High, 14) &nbsp;&nbsp; LL = RollingMin(Low, 14)<br>
      <b>WR = (HH − Close) / (HH − LL) × (−100)</b><br>
      值域：[−100, 0]
    </div>
    <div class="desc">
      与 RSI 镜像互补（RSI ≈ 100 + WR），但 WR 更敏感。
    </div>
  </div>

  <div class="formula-box">
    <h4>🎯 作用与判读</h4>
    <div class="formula">
      WR &gt; −20 → 超买，高位滞涨风险<br>
      WR &lt; −80 → 超卖，低位超跌反弹<br>
      WR 在 −20 ~ −80 之间为中性震荡
    </div>
    <div class="desc">
      适合做短线超买超卖判断；连续多日 WR 高于 −20，常表示高位盘坚（强趋势）；
      连续 WR 低于 −80 且价格不再创新低，预示底部形成。
    </div>
  </div>

  <div id="chart-wr" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>最新 WR(14) = {latest.get("wr",0):.2f}</b><br>
    {"→ 超买区间，警惕回调" if latest.get("wr",0) > -20 else
       "→ 超卖区间，关注反弹" if latest.get("wr",0) < -80 else
       "→ 中性区间"}
  </div>
</div>

"""

# ===================  6. CR  =========================
html += f"""
<div class="card">
  <div class="section-title"><span class="num">7</span> CR 能量指标</div>

  <div class="formula-box">
    <h4>📐 计算方法</h4>
    <div class="formula">
      PM[t−1] = (High[t−1] + Low[t−1] + Close[t−1]) / 3 &nbsp; 中间价<br>
      Bull = max(High[t] − PM[t−1], 0) &nbsp;&nbsp; bear = max(PM[t−1] − Low[t], 0)<br>
      <b>CR = 100 × ΣBull / Σbear</b> &nbsp;（滚动26日）
    </div>
  </div>

  <div class="formula-box">
    <h4>🎯 作用与判读</h4>
    <div class="formula">
      CR &gt; 100 → 多方占优<br>
      CR &lt; 100 → 空方占优<br>
      CR &gt; 200/300 → 超强（注意回调）<br>
      CR &lt; 40 → 超卖，关注反弹<br>
      常用参考线：40 / 60 / 160 / 200
    </div>
    <div class="desc">
      CR 衡量多头能量 vs 空头能量的比值；
      常用于中期趋势判断。多线系统（5/10/20/60 日均线）多头排列则中期偏多。
    </div>
  </div>

  <div id="chart-cr" class="chart-row"></div>
  <div style="background:#f1f5f9;padding:14px;border-radius:8px;margin-top:14px;">
    <b>最新 CR(26) = {latest.get("cr",0):.2f}</b><br>
    {"→ 多方极强，但警惕高位回调" if latest.get("cr",0) > 200 else
       "→ 多方强势" if latest.get("cr",0) > 100 else
       "→ 空方占优，关注 40 支撑线"}
  </div>
</div>

"""

# ==========================================================
#  JAVASCRIPT  (charts)
# ==========================================================
html += """
<script>
const data = """ + _j(records) + """;

const dates = data.map(d => d.date);
const closes = data.map(d => d.close);
const opens = data.map(d => d.open);
const highs = data.map(d => d.high);
const lows = data.map(d => d.low);
const volumes = data.map(d => d.vol/1e4);

const rsi6 = data.map(d => d.rsi6);
const rsi14 = data.map(d => d.rsi14);

const ma5 = data.map(d => d.ma5);
const ma10 = data.map(d => d.ma10);
const ma20 = data.map(d => d.ma20);
const ma60 = data.map(d => d.ma60);
const bollUp = data.map(d => d.boll_up);
const bollMid = data.map(d => d.boll_mid);
const bollDn = data.map(d => d.boll_dn);

const dif = data.map(d => d.dif);
const dea = data.map(d => d.dea);
const macd = data.map(d => d.macd);

const atr = data.map(d => d.atr);
const wr = data.map(d => d.wr);
const cr = data.map(d => d.cr);

const candleData = data.map(d => [d.open, d.close, d.low, d.high]);

const ZOOM_CFG = [
  { type: 'inside', xAxisIndex: 0, start: 60, end: 100 },
  { type: 'slider', xAxisIndex: 0, bottom: 15, height: 18 }
];

// ── RSI ──
echarts.init(document.getElementById('chart-rsi')).setOption({
  title: { text: 'RSI(6) / RSI(14)', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  legend: { data: ['RSI6', 'RSI14'], top: 30 },
  grid: { left: '8%', right: '5%', top: 70, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { min: 0, max: 100 },
  dataZoom: ZOOM_CFG,
  graphic: [
    { type: 'line', shape: { x1: '8%', y1: '30%',  x2: '95%', y2: '30%' },  style: { stroke: '#e11d48', lineDash: [4,4] } },
    { type: 'line', shape: { x1: '8%', y1: '70%',  x2: '95%', y2: '70%' },  style: { stroke: '#059669', lineDash: [4,4] } },
    { type: 'text', z: 100, left: '92%', top: '28%',  style: { text: '70 超买', fill: '#e11d48', fontSize: 11 } },
    { type: 'text', z: 100, left: '92%', top: '68%',  style: { text: '30 超卖', fill: '#059669', fontSize: 11 } },
  ],
  series: [
    { name: 'RSI6',  type: 'line', data: rsi6,  lineStyle: { width: 1.5, color: '#6366f1' }, symbol: 'none' },
    { name: 'RSI14', type: 'line', data: rsi14, lineStyle: { width: 1.8, color: '#f59e0b' }, symbol: 'none' },
  ]
});

// ── MACD ──
echarts.init(document.getElementById('chart-macd')).setOption({
  title: { text: 'MACD(12,26,9)', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  legend: { data: ['MACD柱', 'DIF', 'DEA'], top: 30 },
  grid: { left: '8%', right: '5%', top: 70, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { type: 'value', scale: true },
  dataZoom: ZOOM_CFG,
  graphic: [
    { type: 'line', shape: { x1: '8%', y1: '50%', x2: '95%', y2: '50%' }, style: { stroke: '#64748b', lineDash: [4,4] } },
  ],
  series: [
    { name: 'MACD柱', type: 'bar', data: macd,
      itemStyle: { color: p => p.value >= 0 ? '#ef4444' : '#22c55e' } },
    { name: 'DIF', type: 'line', data: dif, lineStyle: { width: 1.8, color: '#3b82f6' }, symbol: 'none' },
    { name: 'DEA', type: 'line', data: dea, lineStyle: { width: 1.8, color: '#f59e0b' }, symbol: 'none' },
  ]
});

// ── BOLL ─
echarts.init(document.getElementById('chart-boll')).setOption({
  title: { text: 'K线 + 布林带 (MA20 ± 2σ)', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  legend: { data: ['K线', 'MA5', 'MA20', 'MA60', '上轨', '中轨', '下轨'], top: 30 },
  grid: { left: '8%', right: '5%', top: 70, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { scale: true },
  dataZoom: ZOOM_CFG,
  series: [
    { name: 'K线', type: 'candlestick', data: candleData,
      itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' } },
    { name: 'MA5',  type: 'line', data: ma5,  lineStyle: { width: 1.2, color: '#6366f1' }, symbol: 'none' },
    { name: 'MA20', type: 'line', data: ma20, lineStyle: { width: 1.5, color: '#ec4899' }, symbol: 'none' },
    { name: 'MA60', type: 'line', data: ma60, lineStyle: { width: 1.5, color: '#ef4444' }, symbol: 'none' },
    { name: '上轨', type: 'line', data: bollUp,  lineStyle: { width: 1, type: 'dashed', color: '#475569' }, symbol: 'none' },
    { name: '中轨', type: 'line', data: bollMid, lineStyle: { width: 1, type: 'dotted', color: '#64748b' }, symbol: 'none' },
    { name: '下轨', type: 'line', data: bollDn,  lineStyle: { width: 1, type: 'dashed', color: '#475569' }, symbol: 'none' },
  ]
});

// ── ATR ──
echarts.init(document.getElementById('chart-atr')).setOption({
  title: { text: 'ATR(14) 真实波幅', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  grid: { left: '8%', right: '5%', top: 60, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { scale: true, name: 'ATR 值' },
  dataZoom: ZOOM_CFG,
  series: [
    { type: 'line', data: atr, symbol: 'none',
      lineStyle: { width: 2, color: '#dc2626' },
      areaStyle: {
        color: { type: 'linear', x:0,y:0,x2:0,y2:1,
                 colorStops: [{offset:0,color:'rgba(220,38,38,0.35)'},{offset:1,color:'rgba(220,38,38,0.05)'}] }
      } }
  ]
});

// ── WR ──
echarts.init(document.getElementById('chart-wr')).setOption({
  title: { text: 'Williams %R (14)', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  grid: { left: '8%', right: '5%', top: 60, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { min: -100, max: 0, name: 'WR' },
  dataZoom: ZOOM_CFG,
  graphic: [
    { type: 'line', shape: { x1: '8%', y1: '20%',  x2: '95%', y2: '20%' },  style: { stroke: '#e11d48', lineDash: [4,4] } },
    { type: 'line', shape: { x1: '8%', y1: '80%',  x2: '95%', y2: '80%' },  style: { stroke: '#059669', lineDash: [4,4] } },
    { type: 'text', z: 100, left: '92%', top: '18%',  style: { text: '−20 超买', fill: '#e11d48', fontSize: 11 } },
    { type: 'text', z: 100, left: '92%', top: '78%',  style: { text: '−80 超卖', fill: '#059669', fontSize: 11 } },
  ],
  series: [
    { type: 'line', data: wr, symbol: 'none',
      lineStyle: { width: 1.8, color: '#8b5cf6' },
      areaStyle: { color: 'rgba(139,92,246,0.1)' } }
  ]
});

// ── CR ──
echarts.init(document.getElementById('chart-cr')).setOption({
  title: { text: 'CR 能量指标 (26)', textStyle: { fontSize: 13 } },
  tooltip: { trigger: 'axis' },
  grid: { left: '8%', right: '5%', top: 60, bottom: 70 },
  xAxis: { data: dates },
  yAxis: { name: 'CR 值' },
  dataZoom: ZOOM_CFG,
  graphic: [
    { type: 'line', shape: { x1: '8%', y1: '33%',  x2: '95%', y2: '33%' },  style: { stroke: '#ef4444', lineDash: [4,4] } },
    { type: 'line', shape: { x1: '8%', y1: '50%',  x2: '95%', y2: '50%' },  style: { stroke: '#64748b', lineDash: [4,4] } },
    { type: 'line', shape: { x1: '8%', y1: '80%',  x2: '95%', y2: '80%' },  style: { stroke: '#22c55e', lineDash: [4,4] } },
    { type: 'text', z: 100, left: '92%', top: '31%',  style: { text: '200', fill: '#ef4444', fontSize: 11 } },
    { type: 'text', z: 100, left: '92%', top: '49%',  style: { text: '100', fill: '#64748b', fontSize: 11 } },
    { type: 'text', z: 100, left: '92%', top: '79%',  style: { text: '40',  fill: '#22c55e', fontSize: 11 } },
  ],
  series: [
    { type: 'line', data: cr, symbol: 'none',
      lineStyle: { width: 1.8, color: '#d97706' },
      areaStyle: { color: 'rgba(217,119,6,0.12)' } }
  ]
});

// Resize all
window.addEventListener('resize', () => {
  document.querySelectorAll('.chart-row').forEach(el => {
    const ech = echarts.getInstanceByDom(el);
    if (ech) ech.resize();
  });
});
</script>

<div class="disclaimer">
  ⚠️ 以上分析仅供学习参考，不构成投资建议。股市有风险，投资需谨慎。<br>
  Source Code → <a href="https://github.com/xuema/ai_quant" style="color:white;">github.com/xuema/ai_quant</a>
</div>
</div>
</body>
</html>
"""

# ─── Write ──────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PDF), exist_ok=True)

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
size_kb = os.path.getsize(OUT_HTML) // 1024
print(f"[OK] HTML written  -> {OUT_HTML}  ({size_kb} KB)")

# ─── Print to PDF ───────────────────────────────────────────────
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
cmd = (
    f'"{CHROME}" --headless --no-sandbox --disable-gpu '
    + '--run-all-compositor-stages-before-draw '
    + f'--print-to-pdf="{OUT_PDF}" '
    + f'--no-margins "file://{OUT_HTML}"'
)
print(f"[CMD] Generating PDF...")
subprocess.run(cmd, shell=True, timeout=60, capture_output=True)
if os.path.exists(OUT_PDF):
    print(f"[OK] PDF written    -> {OUT_PDF}  ({os.path.getsize(OUT_PDF)//1024} KB)")
else:
    print("[!] PDF generation failed")
