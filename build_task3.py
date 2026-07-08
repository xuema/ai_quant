#!/usr/bin/env python3
"""Task3: 双均线策略分析 - 002281 光迅科技"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# ============================================================
# 1. 加载数据
# ============================================================
DATA_PATH = "/Users/skyler/workspace/stock_selection/ai_quant/data/stock_analysis/002281_20250703_20260708.csv"
df = pd.read_csv(DATA_PATH, parse_dates=['trade_date'])
df = df.sort_values('trade_date').reset_index(drop=True)

# ============================================================
# 2. 计算均线
# ============================================================
SHORT_W = 5
LONG_W = 15
df['MA_short'] = df['close'].rolling(window=SHORT_W, min_periods=1).mean()
df['MA_long'] = df['close'].rolling(window=LONG_W, min_periods=1).mean()

# ============================================================
# 3. 计算交易信号（金叉买入，死叉卖出）
# ============================================================
df['signal'] = 0
df.loc[(df['MA_short'].shift(1) <= df['MA_long'].shift(1)) & 
       (df['MA_short'] > df['MA_long']), 'signal'] = 1
df.loc[(df['MA_short'].shift(1) >= df['MA_long'].shift(1)) & 
       (df['MA_short'] < df['MA_long']), 'signal'] = -1

buy_idx = df.index[df['signal'] == 1].tolist()
sell_idx = df.index[df['signal'] == -1].tolist()

# ============================================================
# 4. 回测（含交易成本）
# ============================================================
# 交易成本参数（A股）
COMMISSION_RATE = 0.0003   # 佣金率：万3（双边收取）
MIN_COMMISSION = 5.0       # 最低佣金：5元/笔
STAMP_TAX_RATE = 0.0005    # 印花税率：万5（仅卖出）

INITIAL_CAPITAL = 1_000_000.0
CAPITAL = INITIAL_CAPITAL
SHARES = 0
POSITION = 0
EQUITY_CURVE = []
TRADE_LOG = []
TOTAL_COST = 0.0  # 累计交易成本

for i, row in df.iterrows():
    price = row['close']
    date = row['trade_date']

    if row['signal'] == 1 and POSITION == 0:   # 买入
        SHARES = int(CAPITAL // (price * 100)) * 100     # A股整手 100 股
        if SHARES > 0:
            amount = SHARES * price
            commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)  # 买入佣金
            total_cost = amount + commission
            TRADE_LOG.append({
                '日期': date, '方向': '买入', '价格': price,
                '股数': SHARES, '金额': amount, '佣金': commission
            })
            CAPITAL -= total_cost
            TOTAL_COST += commission
            POSITION = 1

    elif row['signal'] == -1 and POSITION == 1:  # 卖出
        if SHARES > 0:
            amount = SHARES * price
            commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)  # 卖出佣金
            stamp_tax = amount * STAMP_TAX_RATE  # 印花税
            total_fee = commission + stamp_tax
            NET_REVENUE = amount - total_fee
            TRADE_LOG.append({
                '日期': date, '方向': '卖出', '价格': price,
                '股数': SHARES, '金额': amount, '佣金': commission,
                '印花税': stamp_tax, '总费用': total_fee
            })
            CAPITAL += NET_REVENUE
            SHARES = 0
            POSITION = 0
            TOTAL_COST += total_fee

    equity = CAPITAL + SHARES * price
    EQUITY_CURVE.append({'日期': date, 'equity': equity, 'price': price})

eq_df = pd.DataFrame(EQUITY_CURVE).set_index('日期')
trades_df = pd.DataFrame(TRADE_LOG)

# 交易成本统计
avg_cost_per_trade = TOTAL_COST / (len(trades_df) / 2) if len(trades_df) > 0 else 0
cost_ratio = TOTAL_COST / INITIAL_CAPITAL * 100

# 每日收益率
eq_df['daily_ret'] = eq_df['equity'].pct_change().fillna(0)
eq_df['cum_ret'] = eq_df['equity'] / INITIAL_CAPITAL - 1

# --- 量化指标 ---
final_equity = eq_df['equity'].iloc[-1]
cum_return = final_equity / INITIAL_CAPITAL - 1

# 最大回撤 MDD
running_max = eq_df['equity'].cummax()
drawdown = (eq_df['equity'] - running_max) / running_max
mdd = drawdown.min()
mdd_date = drawdown.idxmin()

# 夏普比率 Sharpe (年化,无风险 r_f=2%)
rf = 0.02
mean_ret = eq_df['daily_ret'].mean()
std_ret = eq_df['daily_ret'].std(ddof=1)
sharpe = (mean_ret - rf/252) / std_ret * (252 ** 0.5)

# 策略基准对比 (买入持有)
buy_hold_ret = eq_df['price'].iloc[-1] / eq_df['price'].iloc[0] - 1
strategy_days = (eq_df.index[-1] - eq_df.index[0]).days
strategy_years = strategy_days / 365.25
annual_ret = (1 + cum_return) ** (1 / strategy_years) - 1

metrics = {
    "初始资金": f"¥{INITIAL_CAPITAL:,.2f}",
    "期末权益": f"¥{final_equity:,.2f}",
    "累计回报": f"{cum_return*100:.2f}%",
    "年化收益率": f"{annual_ret*100:.2f}%",
    "基准累计回报(买入持有)": f"{buy_hold_ret*100:.2f}%",
    "最大回撤(MDD)": f"{mdd*100:.2f}%",
    "最大回撤发生日期": mdd_date.strftime("%Y-%m-%d"),
    "夏普比率(Sharpe)": f"{sharpe:.3f}",
    "交易次数(单边)": f"{len(trades_df)//2}",
    "交易总费用": f"¥{TOTAL_COST:,.2f}",
    "费用占初始资金比": f"{cost_ratio:.2f}%",
    "策略周期": f"{strategy_days} 天",
}

fee_info = {
    "佣金费率": f"{COMMISSION_RATE*10000:.1f}‱ (万{int(COMMISSION_RATE*10000)}), 双边收取, 最低¥{MIN_COMMISSION:.0f}/笔",
    "印花税率": f"{STAMP_TAX_RATE*10000:.1f}‱ (万{int(STAMP_TAX_RATE*10000)}), 仅卖出收取",
    "累计佣金": f"¥{sum(t['佣金'] for t in TRADE_LOG):,.2f}",
    "累计印花税": f"¥{sum(t.get('印花税', 0) for t in TRADE_LOG):,.2f}",
    "交易总费用": f"¥{TOTAL_COST:,.2f}",
}

# ============================================================
# 5. 绘图 + 生成 Task3 页面
# ============================================================
fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                    vertical_spacing=0.06,
                    row_heights=[0.65, 0.35],
                    subplot_titles=["股价 + 均线 + 交易信号",
                                    "策略净值曲线 vs 买入持有"])

# K线图
fig.add_trace(go.Candlestick(
    x=df['trade_date'],
    open=df['open'], high=df['high'], low=df['low'], close=df['close'],
    name="K线",
    increasing_line_color="#ef5350", increasing_fillcolor="#ef5350",
    decreasing_line_color="#26a69a", decreasing_fillcolor="#26a69a",
), row=1, col=1)

# 均线
fig.add_trace(go.Scatter(x=df['trade_date'], y=df['MA_short'],
                         name=f"MA{SHORT_W} (短均线)", line=dict(color="#ff7f0e", width=1.2)), row=1, col=1)
fig.add_trace(go.Scatter(x=df['trade_date'], y=df['MA_long'],
                         name=f"MA{LONG_W} (长均线)", line=dict(color="#2ca02c", width=1.2)), row=1, col=1)

# 买入信号
fig.add_trace(go.Scatter(x=df.loc[buy_idx, 'trade_date'], y=df.loc[buy_idx, 'close'],
                         mode="markers", name="买入信号",
                         marker=dict(symbol="triangle-up", size=12, color="red",
                                   line=dict(width=1.5, color="black")),
                         hovertemplate="买入<br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>"), row=1, col=1)

# 卖出信号
fig.add_trace(go.Scatter(x=df.loc[sell_idx, 'trade_date'], y=df.loc[sell_idx, 'close'],
                         mode="markers", name="卖出信号",
                         marker=dict(symbol="triangle-down", size=12, color="green",
                                   line=dict(width=1.5, color="black")),
                         hovertemplate="卖出<br>日期: %{x}<br>价格: ¥%{y:.2f}<extra></extra>"), row=1, col=1)

# 策略净值曲线
fig.add_trace(go.Scatter(x=eq_df.index, y=eq_df['equity'] / INITIAL_CAPITAL,
                         name="策略净值", line=dict(color="#1f77b4", width=2)), row=2, col=1)

# 基准曲线（买入持有）
buy_hold_norm = eq_df['price'] / eq_df['price'].iloc[0]
fig.add_trace(go.Scatter(x=eq_df.index, y=buy_hold_norm, name="基准(买入持有)",
                         line=dict(color="#7f7f7f", width=2, dash="dash")), row=2, col=1)

# 回撤曲线
underwater = drawdown * 100
fig.add_trace(go.Scatter(x=drawdown.index, y=underwater, fill="tozeroy",
                         name="回撤 (%)", line=dict(color="#9467bd", width=0.5),
                         fillcolor="rgba(148,103,185,0.3)"), row=2, col=1)

fig.update_layout(
    title=f"002281 光迅科技 - 双均线策略分析 (MA{SHORT_W}/{LONG_W})<br>区间: {df['trade_date'].iloc[0].date()} 至 {df['trade_date'].iloc[-1].date()}",
    title_x=0.5,
    xaxis_title="日期",
    yaxis_title="价格 (元)",
    xaxis2_title="日期",
    yaxis2_title="净值 / 回撤 (%)",
    height=900,
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
    template="plotly_white"
)
fig.update_xaxes(rangeslider_visible=False)

# 交易明细表格
if len(trades_df) > 0:
    trade_table = trades_df.to_html(
        index=False, border=1, justify='center', float_format=lambda x: f"{x:.2f}",
        classes="trades"
    )
else:
    trade_table = "<p>无交易记录</p>"

# 生成HTML
HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Task3: 双均线策略分析 - 002281 光迅科技</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a3b6b; text-align: center; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin: 20px 0; }}
        .metric {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .metric h3 {{ margin: 0 0 10px 0; color: #666; font-size: 14px; }}
        .metric p {{ margin: 0; font-size: 24px; font-weight: bold; color: #1a3b6b; }}
        .explanation {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0; }}
        .explanation h2 {{ color: #1a3b6b; margin-top: 0; }}
        .explanation ul {{ line-height: 1.8; }}
        .fee-info {{ background: #fff9e6; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0; }}
        .fee-info h2 {{ color: #e67e22; margin-top: 0; }}
        table.trades {{ width: 100%; border-collapse: collapse; background: white; }}
        table.trades th, table.trades td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        table.trades th {{ background: #1a3b6b; color: white; }}
        table.trades tr:nth-child(even) {{ background: #f9f9f9; }}
        .chart {{ height: 900px; }}
    </style>
</head>
<body>
    <h1>Task3: 双均线策略分析报告</h1>
    <p style="text-align: center; color: #666;">002281 光迅科技 | MA{SHORT_W}/{LONG_W} | {df['trade_date'].iloc[0].date()} 至 {df['trade_date'].iloc[-1].date()}</p>

    <div id="chart" class="chart"></div>

    <div class="metrics">
        <div class="metric"><h3>初始资金</h3><p>{metrics['初始资金']}</p></div>
        <div class="metric"><h3>期末权益</h3><p>{metrics['期末权益']}</p></div>
        <div class="metric"><h3>累计回报</h3><p>{metrics['累计回报']}</p></div>
        <div class="metric"><h3>年化收益率</h3><p>{metrics['年化收益率']}</p></div>
        <div class="metric"><h3>基准累计回报</h3><p>{metrics['基准累计回报(买入持有)']}</p></div>
        <div class="metric"><h3>最大回撤</h3><p>{metrics['最大回撤(MDD)']}</p></div>
        <div class="metric"><h3>最大回撤日期</h3><p>{metrics['最大回撤发生日期']}</p></div>
        <div class="metric"><h3>夏普比率</h3><p>{metrics['夏普比率(Sharpe)']}</p></div>
        <div class="metric"><h3>交易次数</h3><p>{metrics['交易次数(单边)']}</p></div>
        <div class="metric"><h3>交易总费用</h3><p>{metrics['交易总费用']}</p></div>
        <div class="metric"><h3>费用占比</h3><p>{metrics['费用占初始资金比']}</p></div>
        <div class="metric"><h3>策略周期</h3><p>{metrics['策略周期']}</p></div>
    </div>

    <div class="explanation">
        <h2>📊 策略与信号说明</h2>
        <p><strong>双均线策略</strong>是经典的趋势跟踪策略，通过短期均线（MA{SHORT_W}）和长期均线（MA{LONG_W}）的相对位置变化判断趋势方向。</p>
        
        <h3>🔵 金叉（Golden Cross）— 买入信号</h3>
        <p><strong>定义：</strong>短期均线从下方<b>上穿</b>长期均线</p>
        <p><strong>含义：</strong>短期价格动能开始强于长期趋势，市场由弱转强，通常视为上涨趋势启动，策略执行<b>买入</b>。</p>
        
        <h3>🔴 死叉（Death Cross）— 卖出信号</h3>
        <p><strong>定义：</strong>短期均线从上方<b>下穿</b>长期均线</p>
        <p><strong>含义：</strong>短期动能转弱并跌破长期趋势线，市场由强转弱，通常视为下跌趋势开始，策略执行<b>卖出</b>。</p>
        
        <p><strong>本区间信号：</strong>金叉 {len(buy_idx)} 次，死叉 {len(sell_idx)} 次</p>
    </div>

    <div class="explanation">
        <h2>📈 回测指标详解</h2>
        
        <h3>最大回撤（MDD）</h3>
        <p><strong>定义：</strong>从历史最高净值跌至之后最低净值的最大跌幅</p>
        <p><strong>公式：</strong>MDD = (谷值 − 峰值) / 峰值</p>
        <p><strong>意义：</strong>衡量策略在极端不利情况下的<b>最大亏损幅度</b>，是风险控制的核心指标。</p>
        <p><strong>本期数据：</strong>{metrics['最大回撤(MDD)']}，出现在 {metrics['最大回撤发生日期']}</p>
        
        <h3>夏普比率（Sharpe Ratio）</h3>
        <p><strong>定义：</strong>每承担一单位总风险所获得的超额回报</p>
        <p><strong>公式：</strong>Sharpe = (Rp − Rf) / σp × √252</p>
        <p>其中 Rp = 策略年化收益，Rf = 无风险利率（2%），σp = 年化波动率</p>
        <p><strong>评判标准：</strong>&lt;1 一般，1~2 良好，&gt;2 优秀</p>
        <p><strong>本期数据：</strong>{metrics['夏普比率(Sharpe)']}（{('优秀' if float(metrics['夏普比率(Sharpe)']) > 2 else '良好') if float(metrics['夏普比率(Sharpe)']) > 1 else '一般'}）</p>
        
        <h3>累计回报（Cumulative Return）</h3>
        <p><strong>定义：</strong>策略从运行起点到终点的总收益率</p>
        <p><strong>公式：</strong>CR = 期末权益 / 期初资金 − 1</p>
        <p><strong>意义：</strong>直接反映策略的总体盈利能力，是收益端的综合体现。</p>
        <p><strong>本期数据：</strong>{metrics['累计回报']}（基准: {metrics['基准累计回报(买入持有)']}）</p>
    </div>

    <div class="fee-info">
        <h2>💰 交易费率说明</h2>
        <p><strong>A股交易成本构成：</strong></p>
        <p><strong>• 印花税：</strong>成交金额的 {STAMP_TAX_RATE*10000:.0f}‱（万分之{int(STAMP_TAX_RATE*10000)}），<strong>仅卖出时收取</strong></p>
        <p><strong>• 佣金：</strong>成交金额的 {COMMISSION_RATE*10000:.0f}‱（万分之{int(COMMISSION_RATE*10000)}），<strong>买卖双向收取</strong>，最低 {MIN_COMMISSION:.0f} 元/笔</p>
        
        <h3 style="margin-top: 20px;">本策略累计费用：</h3>
        <table class="trades" style="width: auto; margin: 10px 0;">
            <tr><th>费用项目</th><th>累计金额</th></tr>
            <tr><td>累计佣金</td><td>{fee_info['累计佣金']}</td></tr>
            <tr><td>累计印花税</td><td>{fee_info['累计印花税']}</td></tr>
            <tr style="font-weight: bold; background: #ffe6b3;"><td>交易总费用</td><td>{fee_info['交易总费用']}</td></tr>
            <tr><td>占初始资金</td><td>{metrics['费用占初始资金比']}</td></tr>
        </table>
    </div>

    <div class="explanation">
        <h2>📋 交易明细</h2>
        {trade_table}
    </div>

    <script>
        var plotData = {fig.to_json()};
        var config = {{responsive: true, displayModeBar: true}};
        Plotly.newPlot('chart', plotData.data, plotData.layout, config);
    </script>

    <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>数据来源: 002281_20250703_20260708.csv</p>
    </div>
</body>
</html>"""

# 保存HTML
out_path = "/Users/skyler/workspace/stock_selection/ai_quant/Task3_002281_dual_ma.html"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(HTML)

print("=" * 60)
print(f"[✓] Task3 已生成: {out_path}")
print("=" * 60)
print("\n【回测摘要】")
for k, v in metrics.items():
    print(f"  {k}: {v}")
print(f"\n【交易费用明细】")
print(f"  累计佣金: {fee_info['累计佣金']}")
print(f"  累计印花税: {fee_info['累计印花税']}")
print(f"\n【信号统计】金叉(买入) {len(buy_idx)} 次, 死叉(卖出) {len(sell_idx)} 次")
print(f"【交易笔数】{len(trades_df)} 笔(单边)")
