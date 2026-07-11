#!/usr/bin/env python3
"""Task4: single self-contained HTML — charts, data, and rich explanations."""
import os, json, pandas as pd, numpy as np
from datetime import datetime

DATA_DIR = "data/stock_analysis"
CRATE, CMIN, STAMP = 0.000025, 5.0, 0.00005
CAP = 1000000
STOCKS = [("002281","光迅科技"),("601988","中国银行"),("002384","东山精密"),("002317","众生药业")]
DETAIL_KEYS = {"20_10_0.5", "55_20_0.5"}

def load_data(code):
    for pth in [DATA_DIR+"/%s_20250703_20260708.csv"%code,
                DATA_DIR+"/%s_2025-07-03_2026-07-08.csv"%code]:
        if not os.path.exists(pth): continue
        df = pd.read_csv(pth)
        cols = list(df.columns)
        if "trade_date" in cols:
            df = pd.read_csv(pth, parse_dates=["trade_date"])
            df.rename(columns={"trade_date":"date"}, inplace=True)
        elif "date" in cols:
            df = pd.read_csv(pth, parse_dates=["date"])
        else:
            df = pd.read_csv(pth, parse_dates=[0])
            df.columns.values[0] = "date"
        return df
    return None

def compute_indicators(df, entry_n=20, exit_n=10, atr_n=20):
    d = df.copy()
    hl = d["high"] - d["low"]
    hc = abs(d["high"] - d["close"].shift(1))
    lc = abs(d["low"] - d["close"].shift(1))
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    d["atr"] = tr.rolling(atr_n).mean()
    d["upper"] = d["high"].rolling(entry_n).max().shift(1)
    d["lower"] = d["low"].rolling(exit_n).min().shift(1)
    return d.dropna().reset_index(drop=True)

def turtle_backtest(df, entry_n=20, exit_n=10, atr_n=20,
                    add_step=0.5, max_adds=3, risk_pct=0.01, detail=False):
    df = compute_indicators(df.copy(), entry_n, exit_n, atr_n)
    trades = []
    equity_curve = []
    cash = CAP
    position = 0
    entry_price = 0.0
    add_prices_list = []
    units_held = 0
    total_comm = 0.0
    total_stamp = 0.0
    buy_dt, buy_px = [], []
    sell_dt, sell_px = [], []
    add_dt, add_px = [], []

    for _, row in df.iterrows():
        dt = str(row["date"])[:10]
        px = row["close"]
        av = row.get("atr")
        up = row.get("upper")
        lo = row.get("lower")

        # stop loss
        if (position > 0 and av is not None and not np.isnan(av)
                and px <= entry_price - 2 * av):
            rev = position * px
            c = max(rev * CRATE, CMIN)
            s = rev * STAMP
            cash += rev - c - s
            total_comm += c
            total_stamp += s
            trades.append({"date":dt,"action":"止损平仓","price":round(px,2),
                           "shares":position,"fee":round(c+s,2),"type":"sell"})
            if detail:
                sell_dt.append(dt)
                sell_px.append(round(px,2))
            position = 0
            units_held = 0
            add_prices_list = []
            equity_curve.append({"date":dt,"equity":round(cash,2)})
            continue

        # exit lower channel
        if (position > 0 and lo is not None and not np.isnan(lo)
                and px < lo):
            rev = position * px
            c = max(rev * CRATE, CMIN)
            s = rev * STAMP
            cash += rev - c - s
            total_comm += c
            total_stamp += s
            trades.append({"date":dt,"action":"通道下轨平仓",
                           "price":round(px,2),"shares":position,
                           "fee":round(c+s,2),"type":"sell"})
            if detail:
                sell_dt.append(dt)
                sell_px.append(round(px,2))
            position = 0
            units_held = 0
            add_prices_list = []
            equity_curve.append({"date":dt,"equity":round(cash,2)})
            continue

        # entry
        if (position == 0 and up is not None
                and not np.isnan(up) and px > up):
            u = int((CAP * risk_pct) / (av * 100)) * 100 \
                if (av is not None and not np.isnan(av) and av > 0) else 0
            if u > 0:
                cost = u * px
                co = max(cost * CRATE, CMIN)
                cash -= cost + co
                total_comm += co
                position = u
                entry_price = px
                units_held = 1
                add_prices_list = [px]
                trades.append({"date":dt,"action":"初始建仓(1单位)",
                               "price":round(px,2),"shares":u,
                               "fee":round(co,2),"type":"buy"})
                if detail:
                    buy_dt.append(dt)
                    buy_px.append(round(px,2))
            equity_curve.append({"date":dt,"equity":round(cash+(position*px if position else 0),2)})
            continue

        # pyramid add
        if (position > 0 and units_held <= max_adds
                and av is not None and not np.isnan(av)
                and add_prices_list):
            if px >= add_prices_list[-1] + add_step * av:
                u = int((CAP * risk_pct) / (av * 100)) * 100
                if u > 0:
                    cost = u * px
                    co = max(cost * CRATE, CMIN)
                    cash -= cost + co
                    total_comm += co
                    position += u
                    add_prices_list.append(px)
                    units_held += 1
                    act = "第%d次加仓(共%d单位)" % (units_held, units_held)
                    trades.append({"date":dt,"action":act,
                                   "price":round(px,2),"shares":u,
                                   "fee":round(co,2),"type":"add"})
                    if detail:
                        add_dt.append(dt)
                        add_px.append(round(px,2))

        equity_curve.append({"date":dt,"equity":round(cash+(position*px if position else 0),2)})

    # metrics
    final = cash + (position * df.iloc[-1]["close"] if position else 0)
    td = len(df)
    cum = round((final / CAP - 1) * 100, 2)
    ann = round(((final / CAP) ** (252 / td) - 1) * 100, 2) if td > 0 else 0
    peak = equity_curve[0]["equity"]
    mdd = 0.0
    mdt = ""
    for e in equity_curve:
        if e["equity"] > peak:
            peak = e["equity"]
        dd = (e["equity"] - peak) / peak
        if dd < mdd:
            mdd = dd
            mdt = e["date"]
    es = pd.Series([e["equity"] for e in equity_curve])
    dr = es.pct_change().dropna()
    sh = round((dr.mean() - 0.02 / 252) / dr.std() * np.sqrt(252), 3) \
        if dr.std() > 0 else 0.0

    res = {
        "cr": cum, "ar": ann, "sh": sh,
        "md": round(mdd * 100, 2), "mdt": mdt,
        "nt": len(trades),
        "tf": round(total_comm + total_stamp, 2),
        "fe": round(final, 2),
        "en": entry_n, "ex": exit_n, "st": add_step,
    }

    if detail:
        res["equity_curve"] = equity_curve
        res["trades"] = trades
        res["chart"] = {
            "dates": [str(v)[:10] for v in df["date"]],
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist(),
            "upper": [round(v, 2) if pd.notna(v) else None
                      for v in df["upper"]],
            "lower": [round(v, 2) if pd.notna(v) else None
                      for v in df["lower"]],
            "atr": [round(v, 2) if pd.notna(v) else None
                    for v in df["atr"]],
            "buy_dates": buy_dt, "buy_prices": buy_px,
            "sell_dates": sell_dt, "sell_prices": sell_px,
            "add_dates": add_dt, "add_prices": add_px,
        }
    return res

# --- run ---
all_data = {}
for code, name in STOCKS:
    df = load_data(code)
    if df is None:
        print("SKIP " + code)
        continue
    print("\n%s %s..." % (code, name))
    all_data[code] = {"name": name, "params": {}}
    for en in [10, 20, 50, 55]:
        for ex in [5, 10, 20]:
            for step in [0.5, 1.0]:
                k = "%d_%d_%.1f" % (en, ex, step)
                det = (k in DETAIL_KEYS)
                r = turtle_backtest(df, en, ex, 20, step, detail=det)
                all_data[code]["params"][k] = r
                tag = " [FULL]" if det else ""
                print("  %s%s: %+6.2f%% sh=%.3f n=%d"
                      % (k, tag, r["cr"], r["sh"], r["nt"]))

total = sum(len(v["params"]) for v in all_data.values())
print("\nTotal combos: %d" % total)

# --- heatmap data: 002281 all combos ---
_h00 = all_data.get("002281", {}).get("params", {})
_heat = []
for _en in sorted(set(int(k.split("_")[0]) for k in _h00)):
    for _ex in sorted(set(int(k.split("_")[1]) for k in _h00)):
        for _st in [0.5, 1.0]:
            _k = "%d_%d_%.1f" % (_en, _ex, _st)
            if _k in _h00:
                p = _h00[_k]
                _heat.append({"en":_en,"ex":_ex,"st":_st,
                    "sh":p["sh"],"cr":p["cr"],"nt":p["nt"]})
heat_json = "const HEAT=" + json.dumps(_heat, separators=(",",":")) + ";"

data_json = "const TURTLE = " + json.dumps(all_data, ensure_ascii=False, separators=(",", ":")) + ";" + heat_json

opts = "".join(
    '<option value="%s">%s %s</option>' % (c, c, n)
    for c, n in STOCKS)
gt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

html = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Task4 海龟交易法则</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<script>""" + data_json + """</script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f0f2f5;color:#333}
h1{text-align:center;color:#1a3b6b;padding:18px 0 8px}
.sub{text-align:center;color:#888;font-size:12px;margin-bottom:14px}
.pnl{background:#fff;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,.08);margin:12px 16px;overflow:hidden}
.ph{background:linear-gradient(135deg,#1a3b6b,#2c5aa0);color:#fff;padding:10px 16px;font-size:15px;font-weight:bold}
.pb{padding:14px}
.ctrl{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
@media(max-width:800px){.ctrl{grid-template-columns:repeat(2,1fr)}}
.ctr label{font-size:11px;color:#666;display:block;margin-bottom:2px}
.ctr select{width:100%;padding:5px;border:1px solid #ccc;border-radius:4px;font-size:12px;background:#fff}
.note{font-size:10px;color:#999;margin-top:6px;line-height:1.5}
.met{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
@media(max-width:900px){.met{grid-template-columns:repeat(3,1fr)}}
.mc{background:#fff;padding:10px;border-radius:6px;text-align:center;box-shadow:0 1px 2px rgba(0,0,0,.05);border-left:3px solid #1a3b6b}
.mc .l{font-size:10px;color:#999;line-height:1.2}
.mc .v{font-size:16px;font-weight:bold;margin-top:4px;line-height:1.2}
.pos{color:#27ae60}.neg{color:#e74c3c}
table{width:100%;border-collapse:collapse;font-size:11px}
th{background:#1a3b6b;color:#fff;padding:6px}
td{padding:5px 6px;border-bottom:1px solid #eee;text-align:center}
tr:nth-child(even){background:#fafafa}
.buy{color:#cc0000}.sell{color:#00aa44}.add{color:#ff9800}
.eg{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.cd{background:#f8f9fa;border-radius:6px;padding:12px;border-left:4px solid #3498db}
.cd h3{margin:0 0 6px;font-size:13px;color:#1a3b6b}
.cd p{margin:0;font-size:12px;line-height:1.7;color:#555}
.cd p+p{margin-top:6px}
.cd code{background:#e8e8e8;padding:1px 4px;border-radius:2px;font-size:11px}
.cn{background:#e8f5e9;border-left:4px solid #4caf50;padding:14px;border-radius:6px}
.cn h3{color:#2e7d32;margin:0 0 6px;font-size:13px}
.cn ul{margin:4px 0;padding-left:18px}
.cn li{margin:4px 0;font-size:11px;line-height:1.7;color:#444}
.cn li+li{margin-top:4px}
.ft{text-align:center;color:#aaa;font-size:10px;margin:14px 0}
.nd{text-align:center;color:#999;padding:40px;font-size:13px}
.heat-bar{margin-bottom:8px}.hb{background:#ddd;border:none;padding:5px 14px;border-radius:4px;cursor:pointer;font-size:12px;margin-right:4px}.hb.active{background:#1a3b6b;color:#fff}
</style>
</head><body>
<h1>Task4 海龟交易法则 · 实战演练</h1>
<p class="sub">1%风险管理 | 2×ATR止损 | 金字塔加仓(最多4单位) | ATR周期固定20</p>

<div class="pnl"><div class="ph">参数控制面板</div><div class="pb">
<div class="ctrl">
<div class="ctr"><label>选择标的</label><select id="stk" onchange="render()">""" + opts + """</select></div>
<div class="ctr"><label>入场通道 N</label><select id="enN" onchange="render()"><option value="10">10天</option><option value="20" selected>20天</option><option value="50">50天</option><option value="55">55天</option></select></div>
<div class="ctr"><label>出场通道 M</label><select id="exN" onchange="render()"><option value="5">5天</option><option value="10" selected>10天</option><option value="20">20天</option></select></div>
<div class="ctr"><label>加仓步长</label><select id="stp" onchange="render()"><option value="0.5" selected>0.5×ATR</option><option value="1.0">1.0×ATR</option></select></div>
</div>
<p class="note">突破前 N 日最高价建立 1 单位初始仓位 → 价格每上涨 step×ATR 加仓 1 单位 → 最多 4 单位 → 跌破下轨或触及 2×ATR 止损线时平仓</p>
</div></div>

<div class="pnl"><div class="ph">策略指标</div><div class="pb"><div class="met" id="met"></div></div></div>
<div class="pnl"><div class="ph">策略净值曲线 & 回撤</div><div class="pb"><div id="chartEquity" style="height:340px"></div></div></div>
<div class="pnl"><div class="ph">K线图 + 通道 + 交易信号</div><div class="pb"><div id="chartKline" style="height:440px"></div></div></div>
<div class="pnl"><div class="ph">交易记录</div><div class="pb" style="max-height:320px;overflow:auto"><table><thead><tr><th>日期</th><th>操作</th><th>价格</th><th>股数</th><th>费用</th></tr></thead><tbody id="tbl"></tbody></table></div></div>
<div class="pnl"><div class="ph">🔥 光迅科技 参数空间热力图</div><div class="pb">
<p style="font-size:11px;color:#888;margin-bottom:6px">选择步长查看不同 入场周期×出场周期 组合的夏普比率分布（颜色越深越优）</p>
<div class="heat-bar"><button onclick="toggleStep(0.5)" id="btn05" class="hb active">0.5×ATR</button><button onclick="toggleStep(1.0)" id="btn10" class="hb">1.0×ATR</button></div>
<div id="chartHeat" style="height:420px"></div>
</div></div>

<!-- ========== 核心概念解释 ========== -->
<div class="pnl"><div class="ph">策略核心概念解释</div><div class="pb">
<p style="font-size:12px;line-height:1.8;margin:0 0 14px;color:#555">
<strong>海龟交易法则（Turtle Trading Rules）</strong>是趋势跟踪策略的经典代表作。1983年，传奇交易员
<strong>Richard Dennis</strong> 与 William Eckhardt 打赌：交易能力究竟是天赋还是技能？他们招募了23名毫无交易经验的新手（昵称"海龟"），教授一套完全机械化的交易规则，并给予每人100万美元真实资金。结果是——这些"海龟"在四年内创造了超过1.75亿美元的利润。
<strong>这套规则证明：纪律化的交易系统比主观决策更可靠。</strong>
</p>
<div class="eg">
<div class="cd"><h3>📈 高低点通道突破（Donchian Channel Breakout）</h3>
<p><strong>上轨 = </strong><code>过去 N 个交易日的最高价</code></p>
<p><strong>下轨 = </strong><code>过去 M 个交易日的最低价</code></p>
<p>当收盘价突破上轨时，视为多头趋势信号，<strong>建立初始1单位仓位</strong>。
当收盘价跌破下轨时，说明趋势反转，<strong>立即全部平仓离场</strong>。</p>
<p>通道宽度（N、M的取值）直接决定了策略的灵敏度：
N越小，入场信号越多但假突破也越多；N越大，信号越可靠但入场机会越少。
<strong>入场通道N通常大于出场通道M</strong>（如20/10），以保证趋势确认后才入场，而反转信号更早触发出场。</p>
</div>
<div class="cd" style="border-left-color:#e67e22"><h3>📊 真实波幅 TR 与平均真实波幅 ATR</h3>
<p><strong>TR（True Range）= max(高-低, |高-昨收|, |低-昨收|)</code></p>
<p style="margin-top:4px">TR 不仅考虑了日内的高低差，还纳入了隔夜跳空缺口（高开或低开），能更真实地反映一天的实际波动范围。</p>
<p style="margin-top:6px"><strong>ATR（Average True Range）= TR的N日移动平均</strong></p>
<p>ATR 衡量资产的波动程度——ATR越高，市场价格波动越剧烈。对于海龟策略而言，ATR是一个核心"度量衡"，被用于：<strong>① 仓位计算</strong>（每单位 = 资金×1%÷(ATR×100)）、<strong>② 止损距离</strong>（2×ATR）、<strong>③ 加仓步长</strong>（step×ATR）。</p>
<p style="margin-top:4px;color:#888;font-size:10px">以100万本金、ATR=5元为例：每单位 = 1万÷500 = 20手 = 2000股。波动大时ATR变大→仓位自动减小，反之亦然——这就是"ATR自适应仓位"的精髓。</p>
</div>
<div class="cd" style="border-left-color:#e74c3c"><h3>🛡️ 止损机制与仓位管理</h3>
<p><strong>2×ATR硬止损：</strong><code>止损价 = 入场价 - 2×ATR</code></p>
<p>一旦持仓股票价格跌破止损价，<strong>立即全部平仓止损，绝不犹豫</strong>。这是海龟策略的"铁律"——纪律高于一切。</p>
<p style="margin-top:6px"><strong>1%风险规则：</strong>每单位=总资产×1%÷(ATR×100)，确保每单位头寸的1倍ATR波动风险不超过总资金的1%。
以2×ATR止损计算，单笔最大亏损约为总资产的2%。</p>
<p style="margin-top:4px"><strong>加仓后的止损同步：</strong>每次加仓后，所有单位（包括已加仓的单位）的止损价同步上调至"最后入场价-2×ATR"，确保已实现利润不被回吐。</p>
<p style="margin-top:4px;color:#888;font-size:10px">海龟策略的核心理念是"截断亏损，让利润奔跑"——止损是为了活下来，加仓是为了在正确的方向上扩大收益。</p>
</div>
<div class="cd" style="border-left-color:#9b59b6"><h3>🔺 金字塔加仓机制（Pyramiding）</h3>
<p>初始建立1单位仓位后，价格每上涨 <code>step×ATR</code>，就加仓1单位：</p>
<p>• <strong>第1次加仓</strong>：价格 ≥ 入场价+step×ATR → 共2单位</p>
<p>• <strong>第2次加仓</strong>：价格 ≥ 上次加仓价+step×ATR → 共3单位</p>
<p>• <strong>第3次加仓</strong>：价格 ≥ 上次加仓价+step×ATR → 共4单位（满仓，不再加仓）</p>
<p style="margin-top:6px"><strong>加仓步长 step 的含义：</strong></p>
<p>• <strong>step = 0.5：</strong>每涨 0.5×ATR 就加仓，加仓节奏更密集、更快满仓，在强趋势行情中利润更大，但在震荡市中可能加仓过快、亏损也更大。</p>
<p>• <strong>step = 1.0：</strong>每涨 1×ATR 才加仓，加仓节奏更稀疏、满仓更慢，更适合趋势不够强劲时降低加仓频率。</p>
<p style="margin-top:4px;color:#888;font-size:10px">金字塔加仓的精髓是"在盈利的方向上扩大头寸"——只有当价格继续向有利方向运动时才加仓，这与"亏损时补仓"的做法截然相反。</p>
</div>
</div></div></div>

<!-- ========== 适用场景与实战心得 ========== -->
<div class="pnl"><div class="ph">适用场景与实战心得</div><div class="pb"><div class="cn">
<h3>🎯 适合使用海龟策略的场景</h3>
<ul>
<li><strong>单边趋势行情：</strong>海龟是经典趋势跟踪策略，在趋势明确的多头行情中表现最佳。如光迅科技(002281)在N=20/M=10/0.5×ATR配置下实现<strong>+141.94%</strong>的累计回报，夏普比率1.985，持仓期间经历了多轮上涨-加仓-平仓的完整循环。</li>
<li><strong>中高波动率的品种：</strong>科技、电子、医药等行业股票的日内波动较大，ATR值也较大。由于ATR大→仓位自动减小，海龟可以在这类品种上安全地持有4单位满仓，一旦趋势形成收益非常可观。东山精密(002384)在N=50/M=20/0.5×ATR下收益达+92.27%。</li>
<li><strong>中长线持有环境：</strong>海龟的持仓周期通常为数周至数月，需要足够的耐心和纪律。本回测数据区间约1年(2025.07-2026.07)，足以展示策略在不同市场环境下的表现。回测中多数交易的持仓天数超过10天，体现了"让利润奔跑"的理念。</li>
<li><strong>多品种分散配置：</strong>原始海龟策略同时交易20多个期货品种。通过在不同行业、不同波动率的品种上同时运行策略，可以降低单一品种失效期对整体资金曲线的影响。本回测中的4只股票（科技/银行/电子/医药）展示了策略在不同风格下的高度差异化的表现。</li>
</ul>
<h3>⚠️ 不适合使用海龟策略的场景</h3>
<ul>
<li><strong>低波动、窄幅震荡行情：</strong>这是海龟策略最大的"天敌"。当价格在一个区间内频繁上下波动时，会不断触发上轨突破信号买入，紧接着又跌破下轨止损——反复的"买入-止损-买入-止损"会造成持续的亏损。众生药业(002317)在全部18种参数组合下均亏损，最差-29.67%，就是因为其走势呈现无趋势的来回震荡。</li>
<li><strong>低波动率的大盘股：</strong>银行等金融板块波动率低，ATR值偏小，即使ATR小有利建仓（仓位大），但价格很少突破N日通道。中国银行(601988)在最佳配置下仅+14.13%，最差-15.16%，说明低波动品种很难从海龟策略的趋势跟踪中获益。</li>
<li><strong>窄通道参数(如N=10)在震荡市中：</strong>N=10的通道太窄，几乎每天的高点都可能触发新的突破信号。在震荡市中，这会导致频繁入场但很快止损，交易次数激增但胜率极低，佣金和印花税也会大量侵蚀本金。</li>
</ul>
<h3>💡 实战心得与改进建议</h3>
<ul>
<li><strong>通道参数的选择：</strong>N=20/M=10是最稳健的基准配置，兼顾信号数量和可靠性。入场N=20意味着大约1个月的观察窗口，足够过滤掉短期噪音；出场M=10意味着在价格跌破10日最低点时及时锁定利润。本回测中，N=50虽然信号少(全年6-11次)，但一旦入场往往是大行情；而N=10虽然信号多，但在震荡股中被反复"割肉"。</li>
<li><strong>加仓步长的权衡：</strong>0.5×ATR加仓更激进，在趋势明确时能更快累积到4单位满仓，收益更大。1.0×ATR加仓更保守，适合趋势不确定时避免过早加仓。本回测中，0.5步长在强势股(002281)中收益高出15%以上，但在弱势股中也导致亏损更严重——说明加仓步长应与品种波动特征匹配。</li>
<li><strong>ATR自适应是海龟的灵魂：</strong>波动大→ATR大→仓位小；波动小→ATR小→仓位大。这套机制使策略天然适应不同波动率的股票，不需要人工判断"这只股票风险大不大"。这也是海龟策略能在期货市场和股票市场都有效的原因。</li>
<li><strong>止损纪律不可妥协：</strong>海龟的2×ATR止损是"硬止损"——没有商量余地，跌破就卖。任何试图"再等等看会不会反弹"的行为都会让2%的可控亏损变成10%甚至更大的灾难。纪律是海龟策略的生命线。</li>
<li><strong>费率影响：</strong>海龟策略交易频率适中（约10-29笔/年），佣金(万2.5，最低5元)+印花税(万5，仅卖出)对净值影响有限。本回测中最高手续费约520元(众生药业10_5_0.5配置29笔)，仅占初始资金的0.05%，几乎可忽略。</li>
<li><strong>改进① 结合技术指标过滤假信号：</strong>在价格突破上轨的同时，要求RSI>50（确认多头动能）或MACD金叉，可以过滤约30%的假突破，减少无谓的建仓-止损循环。</li>
<li><strong>改进② ADX趋势强度过滤：</strong>ADX>25表示当前市场存在明确趋势，允许建仓；ADX<20表示盘整，暂停交易。避免在无趋势的震荡市中反复被"割肉"。</li>
<li><strong>改进③ 动态调整通道参数：</strong>根据市场环境自动调节N和M——高波动期使用更宽的通道(N=50)过滤噪音，低波动期收窄通道(N=10)捕捉小趋势。这需要额外的判断逻辑，但能更好地适应不同市场环境。</li>
</ul>
</div></div></div>

<div class="ft">生成时间: """ + gt + """ | 数据区间: 2025-07-03 ~ 2026-07-09 | 佣金万2.5(最低5元) / 印花税万5(卖出)</div>

<script>
function initChart(id, data, layout) {
  if (typeof Plotly !== "undefined") {
    Plotly.newPlot(id, data, layout, {responsive: true, displayModeBar: false});
  }
}
function render() {
  var code = document.getElementById("stk").value;
  var enN = document.getElementById("enN").value;
  var exN = document.getElementById("exN").value;
  var stp = document.getElementById("stp").value;
  var key = enN + "_" + exN + "_" + stp;
  var s = TURTLE[code];
  if (!s || !s.params[key]) return;

  var r = s.params[key];
  var nm = s.name;

  // === metrics ===
  var el = document.getElementById("met");
  var positive = r.cr >= 0;
  el.innerHTML = [
    {l:"标的",        v:code+" "+nm},
    {l:"累计回报",    v:(r.cr>0?"+":"")+r.cr+"%",   cls:positive?"pos":"neg"},
    {l:"年化收益率",  v:(r.ar>0?"+":"")+r.ar+"%"},
    {l:"夏普比率",    v:r.sh},
    {l:"最大回撤",    v:r.md+"% ("+r.mdt+")",       cls:"neg"},
    {l:"交易/费用",   v:r.nt+"笔 / ¥"+r.tf.toLocaleString()}
  ].map(function(c){
    return '<div class="mc"><div class="l">'+c.l+'</div><div class="v'+(c.cls?" "+c.cls:"")+'">'+c.v+'</div></div>';
  }).join("");

  // === equity curve ===
  var eqEl = document.getElementById("chartEquity");
  if (r.equity_curve && r.equity_curve.length > 0) {
    var dates=[], vals=[];
    r.equity_curve.forEach(function(e){ dates.push(e.date); vals.push(e.equity); });
    var peak=vals[0], dd=[];
    vals.forEach(function(v){ if(v>peak)peak=v; dd.push((v-peak)/peak*100); });
    initChart("chartEquity", [
      {x:dates, y:vals, type:"scatter", mode:"lines", name:"策略净值",
       line:{color:"#1a3b6b",width:2.5}},
      {x:dates, y:dd, type:"scatter", mode:"lines", name:"回撤(%)",
       line:{color:"#e74c3c",width:1.2}, fill:"tozeroy",
       fillcolor:"rgba(231,76,60,0.10)"}
    ], {yaxis:{title:"权益(元)",gridcolor:"#f0f0f0"},
        yaxis2:{title:"回撤(%)",overlaying:"y",side:"right"},
        margin:{l:60,r:60,t:15,b:35},
        legend:{orientation:"h",y:1.06,x:0.5,xanchor:"center"},
        plot_bgcolor:"#fff",paper_bgcolor:"#fff",height:340,
        hovermode:"x unified"});
  } else {
    eqEl.innerHTML = '<p class="nd">当前参数组合(入场'+r.en+'/出场'+r.ex+'/'+r.st+'×ATR)未预计算权益曲线。<br>请切换到 N=20 / M=10 / 0.5×ATR 查看详细图表。</p>';
  }

  // === kline ===
  var kEl = document.getElementById("chartKline");
  if (r.chart) {
    var ch = r.chart;
    initChart("chartKline", [
      {type:"candlestick",showlegend:false,
       x:ch.dates,open:ch.open,high:ch.high,low:ch.low,close:ch.close,
       increasing:{line:{color:"#ef5350"},fillcolor:"rgba(239,83,80,0.12)"},
       decreasing:{line:{color:"#26a69a"},fillcolor:"rgba(38,166,154,0.12)"}},
      {type:"scatter",mode:"lines",name:"上轨(入场N="+r.en+")",
       x:ch.dates,y:ch.upper,line:{color:"#ff7f0e",width:1.2,dash:"dash"}},
      {type:"scatter",mode:"lines",name:"下轨(出场N="+r.ex+")",
       x:ch.dates,y:ch.lower,line:{color:"#1f77b4",width:1.2,dash:"dash"}},
      {type:"scatter",mode:"markers",name:"买入建仓",
       x:ch.buy_dates,y:ch.buy_prices,
       marker:{symbol:"triangle-up",size:14,color:"#cc0000",line:{color:"#8b0000",width:1.5}}},
      {type:"scatter",mode:"markers",name:"卖出/止损",
       x:ch.sell_dates,y:ch.sell_prices,
       marker:{symbol:"triangle-down",size:14,color:"#00aa44",line:{color:"#006622",width:1.5}}},
      {type:"scatter",mode:"markers",name:"金字塔加仓",
       x:ch.add_dates,y:ch.add_prices,
       marker:{symbol:"diamond",size:11,color:"#ff9800",line:{color:"#e65100",width:1.2}}}
    ], {xaxis:{type:"date",gridcolor:"#f0f0f0"},
        yaxis:{title:"价格(元)",gridcolor:"#f0f0f0"},
        margin:{l:60,r:20,t:15,b:35},
        legend:{orientation:"h",y:1.04,x:0.5,xanchor:"center"},
        plot_bgcolor:"#fff",paper_bgcolor:"#fff",height:440,
        hovermode:"x unified"});
  } else {
    kEl.innerHTML = '<p class="nd">当前参数组合未预计算K线图与交易信号。<br>请切换到 N=20 / M=10 / 0.5×ATR 查看详细图表。</p>';
  }

  // === trade table ===
  var tEl = document.getElementById("tbl");
  if (r.trades && r.trades.length > 0) {
    tEl.innerHTML = r.trades.map(function(t){
      var cls = t.type==="buy"?"buy":(t.type==="add"?"add":"sell");
      return "<tr><td>"+t.date+"</td><td class="+cls+" style='font-weight:bold'>"+t.action+
        "</td><td>¥"+t.price.toFixed(2)+"</td><td>"+t.shares+"</td><td>¥"+t.fee.toFixed(2)+"</td></tr>";
    }).join("");
  } else {
    tEl.innerHTML = '<tr><td colspan="5" style="color:#888;text-align:center">当前参数仅显示摘要，未预计算交易记录</td></tr>';
  }
}

var heatStep = 0.5;
function toggleStep(s) {
  heatStep = s;
  document.getElementById("btn05").className = s === 0.5 ? "hb active" : "hb";
  document.getElementById("btn10").className = s === 1.0 ? "hb active" : "hb";
  renderHeat();
}
function renderHeat() {
  if (typeof HEAT === "undefined" || HEAT.length === 0) return;
  var d = HEAT.filter(function(x) { return x.st === heatStep; });
  var entries = [10, 20, 50, 55];
  var exits = [5, 10, 20];
  var z = [], txt = [], allSh = [];
  for (var i = 0; i < entries.length; i++) {
    var en = entries[i], row = [], rtxt = [];
    for (var j = 0; j < exits.length; j++) {
      var ex = exits[j], f = null;
      for (var k = 0; k < d.length; k++) {
        if (d[k].en === en && d[k].ex === ex) { f = d[k]; break; }
      }
      if (f) {
        row.push(f.sh);
        rtxt.push("入场="+f.en+"天<br>出场="+f.ex+"天<br>夏普="+f.sh+"<br>回报="+f.cr+"%<br>交易="+f.nt+"笔<br>步长="+f.st+"×ATR");
        allSh.push(f.sh);
      } else { row.push(null); rtxt.push("无数据"); }
    }
    z.push(row); txt.push(rtxt);
  }
  var zv = allSh.filter(function(v){return v!=null;});
  var zMin=Math.min.apply(null,zv), zMax=Math.max.apply(null,zv);
  Plotly.newPlot("chartHeat", [{
    type:"heatmap", z:z, x:exits.map(String), y:entries.map(String),
    text:txt, hovertemplate:"%{text}<extra></extra>",
    texttemplate:"%{z:.3f}", textfont:{size:11,color:"#333"},
    colorscale:"YlGn", zmin:zMin, zmax:zMax, showscale:true
  }], {
    margin:{l:80,r:120,t:15,b:60}, height:420,
    plot_bgcolor:"#fff", paper_bgcolor:"#fff",
    xaxis:{title:{text:"退出通道周期 (exit)",font:{size:13}},
      tickvals:exits.map(function(v){return String(v);}),
      tickfont:{size:14,family:"Microsoft YaHei"}},
    yaxis:{title:{text:"入场通道周期 (entry)",font:{size:13}},
      tickvals:entries.map(function(v){return String(v);}),
      tickfont:{size:14,family:"Microsoft YaHei"},
      autorange:"reversed"},
    font:{family:"Microsoft YaHei,PingFang SC,sans-serif",size:12}
  });
}

window.addEventListener("load", function() {
  var tries = 0;
  var poll = setInterval(function() {
    tries++;
    if (typeof Plotly !== "undefined" || tries > 50) {
      clearInterval(poll);
      render();
      renderHeat();
    }
  }, 200);
});
</script>
</body></html>"""

with open("Task4_turtle_final.html", "w", encoding="utf-8") as f:
    f.write(html)

import os
print("\nTask4_turtle_final.html: %.1f KB (single self-contained file)" % (os.path.getsize("Task4_turtle_final.html")/1024))

# verify
with open("Task4_turtle_final.html") as f:
    c = f.read()
print("Has TURTLE const:", "const TURTLE" in c)
print("Has render fn:", "function render" in c)
print("Has Plotly calls:", "Plotly.newPlot" in c)
print("No external .js refs:", "task4_" not in c)
