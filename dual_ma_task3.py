#!/usr/bin/env python3
"""
Task 3: 双均线策略对比 — 002281 光迅科技 vs 601988 中国银行
"""
import os, json
import pandas as pd
import numpy as np
from datetime import datetime

DATA_DIR = "/Users/skyler/workspace/stock_selection/ai_quant/data/stock_analysis"
OUTPUT_HTML = "/Users/skyler/workspace/stock_selection/ai_quant/Task3_dual_ma_comparison.html"
INITIAL_CAPITAL = 1_000_000
COMMISSION_RATE = 0.000025
COMMISSION_MIN = 5.0
STAMP_RATE = 0.00005


def load_002281():
    csv_path = os.path.join(DATA_DIR, "002281_20250703_20260708.csv")
    df = pd.read_csv(csv_path, parse_dates=['trade_date'])
    df = df.rename(columns={'trade_date': 'date'})
    if 'date' not in df.columns:
        raise ValueError(f"No date column in 002281 CSV. Columns: {df.columns.tolist()}")
    return df


def download_boc():
    csv_path = os.path.join(DATA_DIR, "601988_2025-07-03_2026-07-08.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=['date'])
        if 'date' not in df.columns:
            df = pd.read_csv(csv_path, parse_dates=['trade_date'])
            df = df.rename(columns={'trade_date': 'date'})
        return df
    try:
        import yfinance as yf
        ticker = yf.Ticker("601988.SS")
        df = ticker.history(start="2025-07-03", end="2026-07-08")
        if not df.empty:
            df = df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume"})
            df = df[["open","high","low","close","volume"]].copy()
            df.index = pd.to_datetime(df.index)
            df.index.name = "date"
            df.reset_index().to_csv(csv_path, index=False)
            return csv_path, df.reset_index()
    except Exception as e:
        print(f"yfinance failed for 601988: {e}")
    return None


def calc_ma(df, short=5, long_=15):
    df = df.copy()
    df['ma_short'] = df['close'].rolling(window=short).mean()
    df['ma_long'] = df['close'].rolling(window=long_).mean()
    return df


def calc_signals(df):
    df = df.copy()
    df['signal'] = 0
    df.loc[df['ma_short'] > df['ma_long'], 'signal'] = 1
    df.loc[df['ma_short'] < df['ma_long'], 'signal'] = -1
    df['position'] = df['signal'].diff()
    return df


def backtest(df, symbol=""):
    trades = []
    cash = INITIAL_CAPITAL
    position = 0
    total_commission = 0.0
    total_stamp = 0.0
    equity_curve = []

    for i, row in df.iterrows():
        dt = row['date']
        price = row['close']
        sig = row.get('position', 0)

        if sig == 2 and position == 0:
            max_shares = int(cash / price / 100) * 100
            if max_shares > 0:
                cost = max_shares * price
                commission = max(cost * COMMISSION_RATE, COMMISSION_MIN)
                cash -= cost + commission
                position = max_shares
                total_commission += commission
                trades.append({'date': dt, 'direction': '买入', 'price': price,
                    'shares': max_shares, 'amount': cost,
                    'commission': commission, 'stamp': 0, 'fee': commission})
        elif sig == -2 and position > 0:
            revenue = position * price
            commission = max(revenue * COMMISSION_RATE, COMMISSION_MIN)
            stamp = revenue * STAMP_RATE
            cash += revenue - commission - stamp
            total_commission += commission
            total_stamp += stamp
            trades.append({'date': dt, 'direction': '卖出', 'price': price,
                'shares': position, 'amount': revenue,
                'commission': commission, 'stamp': stamp, 'fee': commission + stamp})
            position = 0

        equity_curve.append({'date': dt, 'equity': cash + (position * price if position > 0 else 0)})

    end_equity = cash + (position * df.iloc[-1]['close'] if position > 0 else 0)
    trading_days = len(df)
    cum_return = end_equity / INITIAL_CAPITAL - 1.0
    ann_return = (1 + cum_return) ** (252 / trading_days) - 1 if trading_days > 0 else 0

    # 最大回撤
    peak = equity_curve[0]['equity']
    max_dd, max_dd_date = 0.0, ''
    for e in equity_curve:
        if e['equity'] > peak: peak = e['equity']
        dd = (e['equity'] - peak) / peak
        if dd < max_dd:
            max_dd, max_dd_date = dd, e['date']

    # 夏普
    eq_ser = pd.Series([e['equity'] for e in equity_curve])
    daily_ret = eq_ser.pct_change().dropna()
    rf_daily = 0.02 / 252
    sharpe = (daily_ret.mean() - rf_daily) / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0.0

    bench_return = df.iloc[-1]['close'] / df.iloc[0]['close'] - 1.0

    return {
        'symbol': symbol, 'end_equity': end_equity,
        'cum_return': cum_return, 'ann_return': ann_return,
        'bench_return': bench_return,
        'max_dd': max_dd, 'max_dd_date': str(max_dd_date)[:10],
        'sharpe': sharpe, 'n_trades': len(trades),
        'total_commission': total_commission, 'total_stamp': total_stamp,
        'total_fee': total_commission + total_stamp,
        'fee_pct': (total_commission + total_stamp) / INITIAL_CAPITAL * 100,
        'trades': trades, 'equity_curve': equity_curve,
    }


def chart_json(df):
    data = [
        {"type":"candlestick","name":"K线","showlegend":False,
         "x":[str(d)[:10] for d in df['date']],
         "open":df['open'].tolist(),"high":df['high'].tolist(),
         "low":df['low'].tolist(),"close":df['close'].tolist(),
         "increasing":{"line":{"color":"#ef5350"},"fillcolor":"rgba(239,83,80,0.2)"},
         "decreasing":{"line":{"color":"#26a69a"},"fillcolor":"rgba(38,166,154,0.2)"}},
        {"type":"scatter","mode":"lines","name":"MA5",
         "x":[str(d)[:10] for d in df['date']],
         "y":[round(v,2) if pd.notna(v) else None for v in df['ma_short']],
         "line":{"color":"#ff7f0e","width":1.2}},
        {"type":"scatter","mode":"lines","name":"MA15",
         "x":[str(d)[:10] for d in df['date']],
         "y":[round(v,2) if pd.notna(v) else None for v in df['ma_long']],
         "line":{"color":"#1f77b4","width":1.2}}
    ]
    buys = df[df['position']==2]
    sells = df[df['position']==-2]
    if not buys.empty:
        data.append({"type":"scatter","mode":"markers+text","name":"买入信号",
            "x":[str(d)[:10] for d in buys['date']],"y":buys['close'].tolist(),
            "text":[f"¥{v:.2f}" for v in buys['close']],"textposition":"top center",
            "textfont":{"size":9,"color":"#cc0000"},
            "marker":{"symbol":"triangle-up","size":13,"color":"#cc0000","line":{"color":"darkred","width":1.5}}})
    if not sells.empty:
        data.append({"type":"scatter","mode":"markers+text","name":"卖出信号",
            "x":[str(d)[:10] for d in sells['date']],"y":sells['close'].tolist(),
            "text":[f"¥{v:.2f}" for v in sells['close']],"textposition":"bottom center",
            "textfont":{"size":9,"color":"#00aa44"},
            "marker":{"symbol":"triangle-down","size":13,"color":"#00aa44","line":{"color":"darkgreen","width":1.5}}})
    layout = {
        "xaxis":{"type":"date","gridcolor":"#eee","rangeslider":{"visible":False}},
        "yaxis":{"title":"价格 (元)","gridcolor":"#eee"},
        "showlegend":True,"legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"right","x":1},
        "margin":{"l":60,"r":20,"t":40,"b":50},
        "plot_bgcolor":"white","paper_bgcolor":"white","height":550,"hovermode":"x unified"}
    return json.dumps({"data":data,"layout":layout})


def equity_json(r1, r2):
    def dd_curve(eq_list):
        peak = eq_list[0]['equity']
        dds = []
        for e in eq_list:
            if e['equity'] > peak: peak = e['equity']
            dds.append({'date': e['date'], 'dd': (e['equity'] - peak) / peak * 100})
        return dds
    dd1, dd2 = dd_curve(r1['equity_curve']), dd_curve(r2['equity_curve'])
    data = [
        {"type":"scatter","mode":"lines","name":"002281 策略净值",
         "x":[str(e['date'])[:10] for e in r1['equity_curve']],
         "y":[e['equity'] for e in r1['equity_curve']],
         "line":{"color":"#ef5350","width":2},"yaxis":"y"},
        {"type":"scatter","mode":"lines","name":"601988 策略净值",
         "x":[str(e['date'])[:10] for e in r2['equity_curve']],
         "y":[e['equity'] for e in r2['equity_curve']],
         "line":{"color":"#2196f3","width":2},"yaxis":"y"},
        {"type":"scatter","mode":"lines","name":"002281 回撤",
         "x":[str(d['date'])[:10] for d in dd1],
         "y":[d['dd'] for d in dd1],
         "line":{"color":"#ef5350","width":1},"yaxis":"y2",
         "fill":"tozeroy","fillcolor":"rgba(239,83,80,0.15)"},
        {"type":"scatter","mode":"lines","name":"601988 回撤",
         "x":[str(d['date'])[:10] for d in dd2],
         "y":[d['dd'] for d in dd2],
         "line":{"color":"#2196f3","width":1},"yaxis":"y2",
         "fill":"tozeroy","fillcolor":"rgba(33,150,243,0.15)"}
    ]
    layout = {
        "yaxis":{"title":"策略净值 (元)","gridcolor":"#eee"},
        "yaxis2":{"title":"回撤 (%)","overlaying":"y","side":"right","gridcolor":"#eee"},
        "xaxis":{"type":"date","gridcolor":"#eee"},
        "showlegend":True,"legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"right","x":1},
        "margin":{"l":60,"r":60,"t":40,"b":50},
        "plot_bgcolor":"white","paper_bgcolor":"white","height":450,"hovermode":"x unified"}
    return json.dumps({"data":data,"layout":layout})


def trade_rows(trades):
    rows = ""
    for t in trades:
        cls = "buy" if t['direction']=='买入' else "sell"
        stamp_str = f"¥{t['stamp']:.2f}" if t['stamp'] > 0 else "-"
        rows += f"""<tr>
            <td>{str(t['date'])[:10]}</td><td><b class="{cls}">{t['direction']}</b></td>
            <td>¥{t['price']:.2f}</td><td>{t['shares']}</td>
            <td>¥{t['amount']:,.2f}</td><td>¥{t['commission']:.2f}</td>
            <td>{stamp_str}</td><td>¥{t['fee']:.2f}</td></tr>"""
    return rows


def generate_html(r1, r2, j1, j2, j3):
    eq_cls1 = "color:#27ae60" if r1['end_equity'] >= INITIAL_CAPITAL else "color:#e74c3c"
    eq_cls2 = "color:#27ae60" if r2['end_equity'] >= INITIAL_CAPITAL else "color:#e74c3c"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Task3 双均线策略对比分析</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:0;padding:20px;background:#f0f2f5;color:#333}}
h1{{color:#1a3b6b;text-align:center;margin:0 0 5px;font-size:24px}}
.subtitle{{text-align:center;color:#888;font-size:14px;margin:0 0 20px}}
.panel{{background:white;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);margin:16px 0;overflow:hidden}}
.panel-header{{background:#1a3b6b;color:white;padding:12px 20px;font-size:16px;font-weight:bold}}
.panel-body{{padding:20px}}
.chart{{width:100%}}
.buy{{color:#cc0000}}.sell{{color:#00aa44}}
.trade-table{{width:100%;border-collapse:collapse;font-size:13px}}
.trade-table th{{background:#1a3b6b;color:white;padding:10px 8px}}
.trade-table td{{padding:8px;text-align:right;border-bottom:1px solid #eee}}
.trade-table tr:nth-child(even){{background:#fafafa}}
.explain-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}}
.explain-card{{background:#f8f9fa;border-radius:8px;padding:16px;border-left:4px solid #3498db}}
.explain-card h3{{margin:0 0 8px;font-size:15px;color:#1a3b6b}}
.explain-card p{{margin:0;font-size:13px;line-height:1.7;color:#555}}
.explain-card code{{background:#e8e8e8;padding:1px 5px;border-radius:3px;font-size:12px}}
.conclusion{{background:#e8f5e9;border-radius:8px;padding:20px;border-left:4px solid #4caf50;font-size:14px;line-height:2}}
.conclusion h3{{color:#2e7d32;margin:0 0 10px;font-size:16px}}
.conclusion ul{{margin:8px 0;padding-left:20px}}
.footer{{text-align:center;color:#aaa;font-size:12px;margin-top:20px}}
</style></head><body>
<h1>Task3 双均线策略 · 对比分析报告</h1>
<p class="subtitle">MA5/MA15 | 2025-07-03 至 2026-07-08 | 初始资金 ¥1,000,000</p>

<div class="panel"><div class="panel-header">📊 两只股票策略指标对比</div><div class="panel-body">
<table style="width:100%;border-collapse:collapse;font-size:14px">
<tr><th style="padding:10px;background:#1a3b6b;color:white;text-align:left">指标</th>
<th style="padding:10px;background:#e74c3c;color:white;text-align:center">002281 光迅科技 (MA5/15)</th>
<th style="padding:10px;background:#2196f3;color:white;text-align:center">601988 中国银行 (MA5/15)</th></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">累计回报</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;color:#e74c3c;font-weight:bold">+{r1['cum_return']*100:.2f}%</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r2['cum_return']:+.2f}%</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">年化收益率</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r1['ann_return']*100:+.2f}%</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r2['ann_return']*100:+.2f}%</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">基准回报(买入持有)</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r1['bench_return']*100:+.2f}%</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r2['bench_return']*100:+.2f}%</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">最大回撤 (MDD)</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;color:#e74c3c;font-weight:bold">{r1['max_dd']*100:.2f}%</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r2['max_dd']*100:.2f}%</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">最大回撤日期</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r1['max_dd_date']}</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r2['max_dd_date']}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">夏普比率</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r1['sharpe']:.3f}</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;font-weight:bold">{r2['sharpe']:.3f}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">交易次数</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r1['n_trades']}</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center">{r2['n_trades']}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee">期末权益</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;{eq_cls1};font-weight:bold">¥{r1['end_equity']:,.2f}</td>
<td style="padding:8px;border-bottom:1px solid #eee;text-align:center;{eq_cls2};font-weight:bold">¥{r2['end_equity']:,.2f}</td></tr>
</table></div></div>

<div class="panel"><div class="panel-header">📈 策略净值 + 回撤对比</div><div class="panel-body"><div id="chart_equity" style="height:450px"></div></div></div>

<div class="panel"><div class="panel-header">📊 002281 光迅科技 — K线 + 均线 + 交易信号</div><div class="panel-body"><div id="chart_002281" style="height:550px"></div></div></div>

<div class="panel"><div class="panel-header">📊 601988 中国银行 — K线 + 均线 + 交易信号</div><div class="panel-body"><div id="chart_601988" style="height:550px"></div></div></div>

<div class="panel"><div class="panel-header">📋 002281 光迅科技 — 交易明细</div><div class="panel-body" style="overflow-x:auto"><table class="trade-table">
<thead><tr><th>日期</th><th>方向</th><th>价格</th><th>股数</th><th>金额</th><th>佣金</th><th>印花税</th><th>总费用</th></tr></thead>
<tbody>{trade_rows(r1['trades'])}</tbody></table></div></div>

<div class="panel"><div class="panel-header">📋 601988 中国银行 — 交易明细</div><div class="panel-body" style="overflow-x:auto"><table class="trade-table">
<thead><tr><th>日期</th><th>方向</th><th>价格</th><th>股数</th><th>金额</th><th>佣金</th><th>印花税</th><th>总费用</th></tr></thead>
<tbody>{trade_rows(r2['trades'])}</tbody></table></div></div>

<div class="panel"><div class="panel-header">📚 策略与指标说明</div><div class="panel-body">
<h3 style="color:#1a3b6b;margin:0 0 12px">双均线策略</h3>
<p style="font-size:14px;line-height:1.8;color:#555;margin:0 0 20px">
双均线策略通过两条不同周期的移动平均线交叉信号来捕捉趋势。短期均线 MA5 上穿长期均线 MA15 产生金叉（买入），下穿产生死叉（卖出）。</p>
<div class="explain-grid">
<div class="explain-card"><h3>🔵 金叉（Golden Cross）— 买入</h3>
<p><b>定义:</b> 短期均线 MA5 从下方上穿长期均线 MA15</p><p><b>含义:</b> 短期价格动能开始强于长期趋势，通常意味着上涨趋势启动。</p></div>
<div class="explain-card" style="border-left-color:#e74c3c"><h3>🔴 死叉（Death Cross）— 卖出</h3>
<p><b>定义:</b> 短期均线 MA5 从上方下穿长期均线 MA15</p><p><b>含义:</b> 短期动能转弱跌破长期趋势，通常意味着下跌趋势开始。</p></div>
<div class="explain-card" style="border-left-color:#27ae60"><h3>📊 最大回撤（MDD）</h3>
<p><b>公式:</b> <code>MDD = (谷值 - 峰值) / 峰值</code></p><p>历史最高净值跌至之后最低净值的最大跌幅，衡量策略最坏情况下的最大亏损。</p></div>
<div class="explain-card" style="border-left-color:#9b59b6"><h3>📈 夏普比率（Sharpe Ratio）</h3>
<p><b>公式:</b> <code>Sharpe = (Rp - Rf) / σp × √252</code></p><p>Rp=策略年化收益, Rf=无风险利率(2%), σp=年化波动率。&lt;1 一般 | 1~2 良好 | &gt;2 优秀</p></div>
<div class="explain-card" style="border-left-color:#2ecc71"><h3>💰 累计回报（Cumulative Return）</h3>
<p><b>公式:</b> <code>CR = 期末权益 / 期初资金 - 1</code></p><p>策略总体盈利能力，直接反映收益端综合表现。</p></div>
</div></div></div>

<div class="panel"><div class="panel-header">💡 双均线策略适用场景与应用心得</div><div class="panel-body"><div class="conclusion">
<h3>📌 双均线核心特性</h3>
<ul>
<li><b>趋势跟随型策略：</b>在单边趋势行情中表现优异，但在震荡市中频繁产生假信号</li>
<li><b>延迟性：</b>均线天然滞后于价格，信号出现时趋势已走了一段</li>
<li><b>参数敏感度：</b>短周期(MA5)更敏感但噪音多，长周期(MA15/20/30)更稳但反应慢</li>
</ul>
<h3>📌 对比发现</h3>
<ul>
<li><b>002281 光迅科技：</b>高弹性科技股，价格波动大趋势强，双均线策略收益显著但波动剧烈（最大回撤 {r1['max_dd']*100:.1f}%）</li>
<li><b>601988 中国银行：</b>银行股波动小走势平稳，均线系统易产生频繁假信号，收益偏低</li>
<li><b>关键发现：</b>高波动/强趋势股 → 双均线效果好；低波动/盘整股 → 双均线效果差</li>
</ul>
<h3>📌 适用场景</h3>
<ul>
<li>✅ 单边趋势行情（牛市主升浪/熊市主跌浪）</li>
<li>✅ 高波动成长股（科技、新能源、AI等）</li>
<li>❌ 震荡盘整行情（横盘区间震荡时反复止损）</li>
<li>❌ 低波动大盘股（银行、公用事业，信号噪音大）</li>
</ul>
<h3>📌 实践心得</h3>
<ul>
<li><b>周期参数：</b>MA5/MA15 适合短线交易，中线可改为 MA10/MA30 或 MA20/MA60</li>
<li><b>费用影响：</b>频繁交易时手续费和印花税会显著侵蚀收益</li>
<li><b>仓位管理：</b>全仓进出是极端情况，实际应配合资金管理（如每次不超过 30% 资金）</li>
<li><b>止损配合：</b>建议增设固定止损（如 -5%）弥补均线策略滞后缺陷</li>
<li><b>多指标共振：</b>可结合 RSI/MACD/成交量 做确认，降低假信号率</li>
</ul>
</div></div></div>

<br/>
<div class="footer">
<p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据: yfinance | 佣金 万2.5 | 印花税 万5</p>
</div>

<script>
Plotly.newPlot('chart_002281', {j1}.data, {j1}.layout, {{responsive:true,displayModeBar:true}});
Plotly.newPlot('chart_601988', {j2}.data, {j2}.layout, {{responsive:true,displayModeBar:true}});
Plotly.newPlot('chart_equity', {j3}.data, {j3}.layout, {{responsive:true,displayModeBar:true}});
</script>
</body></html>"""


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("加载 002281 数据...")
    df1 = load_002281()
    print(f"  {len(df1)} 条记录, columns: {df1.columns.tolist()}")
    df1 = calc_ma(df1)
    df1 = calc_signals(df1)

    print("下载 601988 数据...")
    result = download_boc()
    if result is None:
        print("❌ 中国银行数据下载失败")
        return
    csv_path, df2 = result
    df2 = df2.rename(columns={'trade_date':'date', 'Date':'date'}) if 'trade_date' in df2.columns or 'Date' in df2.columns else df2
    print(f"  {len(df2)} 条记录, columns: {df2.columns.tolist()}")
    df2 = calc_ma(df2)
    df2 = calc_signals(df2)

    print("回测 002281...")
    r1 = backtest(df1, "002281")
    print(f"  累计回报: {r1['cum_return']*100:+.2f}% | 夏普: {r1['sharpe']:.3f} | MDD: {r1['max_dd']*100:.2f}% | 交易: {r1['n_trades']}次")

    print("回测 601988...")
    r2 = backtest(df2, "601988")
    print(f"  累计回报: {r2['cum_return']*100:+.2f}% | 夏普: {r2['sharpe']:.3f} | MDD: {r2['max_dd']*100:.2f}% | 交易: {r2['n_trades']}次")

    j1 = chart_json(df1)
    j2 = chart_json(df2)
    j3 = equity_json(r1, r2)

    html = generate_html(r1, r2, j1, j2, j3)
    with open(OUTPUT_HTML, 'w') as f:
        f.write(html)

    print(f"\n✅ HTML 报告已生成: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
