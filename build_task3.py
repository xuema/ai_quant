#!/usr/bin/env python3
"""Task3: 双均线策略分析 - 含交易手续费计算"""

import pandas as pd
import numpy as np
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
       (df['MA_short'] > df['MA_long']), 'signal'] = 1  # 金叉
df.loc[(df['MA_short'].shift(1) >= df['MA_long'].shift(1)) & 
       (df['MA_short'] < df['MA_long']), 'signal'] = -1  # 死叉

buy_idx = df.index[df['signal'] == 1].tolist()
sell_idx = df.index[df['signal'] == -1].tolist()

# ============================================================
# 4. 回测（含交易成本）
# ============================================================
# 交易成本参数
COMMISSION_RATE = 0.00025  # 佣金：万2.5
MIN_COMMISSION = 5.0       # 最低佣金：5元/笔
STAMP_TAX_RATE = 0.0005    # 印花税：万5（仅卖出）

INITIAL_CAPITAL = 1_000_000.0
capital = INITIAL_CAPITAL
shares = 0
position = 0
equity_curve = []
trade_log = []

for i, row in df.iterrows():
    price = row['close']
    date = row['trade_date']
    
    if row['signal'] == 1 and position == 0:  # 买入
        shares = int(capital // (price * 100)) * 100
        if shares > 0:
            amount = shares * price
            commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
            total_amount = amount + commission
            
            trade_log.append({
                'date': date,
                'action': 'buy',
                'price': price,
                'shares': shares,
                'amount': amount,
                'commission': commission,
                'stamp_tax': 0,
                'net': total_amount
            })
            capital -= total_amount
            position = 1
            
    elif row['signal'] == -1 and position == 1:  # 卖出
        if shares > 0:
            amount = shares * price
            commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
            stamp_tax = amount * STAMP_TAX_RATE
            net_amount = amount - commission - stamp_tax
            
            trade_log.append({
                'date': date,
                'action': 'sell',
                'price': price,
                'shares': shares,
                'amount': amount,
                'commission': commission,
                'stamp_tax': stamp_tax,
                'net': net_amount
            })
            capital += net_amount
            shares = 0
            position = 0
    
    equity = capital + shares * price
    equity_curve.append({'date': date, 'equity': equity})

eq_df = pd.DataFrame(equity_curve).set_index('date')
trades_df = pd.DataFrame(trade_log)

# ============================================================
# 5. 计算量化指标
# ============================================================
final_equity = eq_df['equity'].iloc[-1]
cum_return = final_equity / INITIAL_CAPITAL - 1
strategy_days = (eq_df.index[-1] - eq_df.index[0]).days

# 最大回撤
eq_df['peak'] = eq_df['equity'].cummax()
eq_df['drawdown'] = (eq_df['equity'] - eq_df['peak']) / eq_df['peak']
mdd = eq_df['drawdown'].min()
mdd_date = eq_df['drawdown'].idxmin()

# 年化收益率
annual_return = (1 + cum_return) ** (365 / strategy_days) - 1

# 夏普比率
eq_df['daily_return'] = eq_df['equity'].pct_change()
sharpe = (eq_df['daily_return'].mean() - 0.02/252) / eq_df['daily_return'].std() * np.sqrt(252)

# 基准累计回报
buy_hold_ret = df['close'].iloc[-1] / df['close'].iloc[0] - 1

# 交易费用统计
total_commission = trades_df['commission'].sum()
total_stamp_tax = trades_df['stamp_tax'].sum()
total_fees = total_commission + total_stamp_tax

metrics = {
    '初始资金': f'¥{INITIAL_CAPITAL:,.0f}',
    '期末权益': f'¥{final_equity:,.2f}',
    '累计回报': f'{cum_return:.2%}',
    '年化收益率': f'{annual_return:.2%}',
    '夏普比率': f'{sharpe:.3f}',
    '最大回撤': f'{mdd:.2%}',
    '最大回撤日期': mdd_date.strftime('%Y-%m-%d'),
    '交易次数(单边)': f'{len(trades_df)}',
}

# ============================================================
# 6. 可视化（使用独立的图表）
# ============================================================

# 图表1: K线图 + 均线 + 买卖信号
fig1 = go.Figure()

# K线
fig1.add_trace(go.Candlestick(
    x=df['trade_date'],
    open=df['open'],
    high=df['high'],
    low=df['low'],
    close=df['close'],
    name='K线',
    increasing_line_color='red',
    increasing_fillcolor='red',
    decreasing_line_color='green',
    decreasing_fillcolor='green',
    showlegend=False
))

# 均线
fig1.add_trace(go.Scatter(x=df['trade_date'], y=df['MA_short'],
                          name=f'MA{SHORT_W}', line=dict(color='orange', width=1.5)))
fig1.add_trace(go.Scatter(x=df['trade_date'], y=df['MA_long'],
                          name=f'MA{LONG_W}', line=dict(color='blue', width=1.5)))

# 买入信号（标注在K线上）
fig1.add_trace(go.Scatter(
    x=df.loc[buy_idx, 'trade_date'],
    y=df.loc[buy_idx, 'close'],
    mode='markers+text',
    name='买入',
    marker=dict(symbol='triangle-up', size=15, color='red', line=dict(width=2, color='darkred')),
    text=[f'¥{p:.2f}' for p in df.loc[buy_idx, 'close']],
    textposition='top center',
    textfont=dict(size=10, color='red'),
    hovertemplate='<b>买入信号</b><br>日期: %{x|%Y-%m-%d}<br>价格: ¥%{y:.2f}<extra></extra>'
))

# 卖出信号（标注在K线上）
fig1.add_trace(go.Scatter(
    x=df.loc[sell_idx, 'trade_date'],
    y=df.loc[sell_idx, 'close'],
    mode='markers+text',
    name='卖出',
    marker=dict(symbol='triangle-down', size=15, color='green', line=dict(width=2, color='darkgreen')),
    text=[f'¥{p:.2f}' for p in df.loc[sell_idx, 'close']],
    textposition='bottom center',
    textfont=dict(size=10, color='green'),
    hovertemplate='<b>卖出信号</b><br>日期: %{x|%Y-%m-%d}<br>价格: ¥%{y:.2f}<extra></extra>'
))

fig1.update_layout(
    title='002281 光迅科技 K线图（含买卖信号）',
    xaxis_title='日期',
    yaxis_title='价格（元）',
    template='plotly_white',
    height=600,
    hovermode='x unified',
    xaxis_rangeslider_visible=False,
)

# 图表2: 策略净值 + 回撤
fig2 = make_subplots(rows=2, cols=1, shared_xaxes=True,
                     subplot_titles=['策略净值', '回撤'],
                     row_heights=[0.7, 0.3])

# 策略净值
fig2.add_trace(go.Scatter(
    x=eq_df.index, y=eq_df['equity'],
    name='策略净值', line=dict(color='blue', width=2)
), row=1, col=1)

fig2.add_trace(go.Scatter(
    x=eq_df.index, y=[INITIAL_CAPITAL] * len(eq_df),
    name='初始资金', line=dict(color='gray', dash='dash', width=1)
), row=1, col=1)

# 回撤曲线
fig2.add_trace(go.Scatter(
    x=eq_df.index, y=eq_df['drawdown'] * 100,
    name='回撤', fill='tozeroy',
    line=dict(color='red', width=1.5),
    fillcolor='rgba(255,0,0,0.2)'
), row=2, col=1)

fig2.update_layout(
    title='策略表现',
    yaxis_title='净值（元）',
    yaxis2_title='回撤（%）',
    template='plotly_white',
    height=500,
    hovermode='x unified',
    showlegend=True,
)

# ============================================================
# 7. 生成HTML
# ============================================================
html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Task3: 双均线策略分析</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .metric {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
        .metric .label {{ font-size: 14px; color: #666; }}
        .metric .value {{ font-size: 20px; font-weight: bold; color: #333; margin-top: 5px; }}
        .section {{ margin: 30px 0; }}
        .section h2 {{ color: #444; border-bottom: 2px solid #007bff; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 8px; text-align: right; border: 1px solid #ddd; }}
        th {{ background: #f8f9fa; }}
        .fee-info {{ background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .fee-info h3 {{ color: #856404; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Task3: 双均线策略分析报告</h1>
        <p>股票: 002281 光迅科技 | 区间: {df['trade_date'].iloc[0].strftime('%Y-%m-%d')} 至 {df['trade_date'].iloc[-1].strftime('%Y-%m-%d')}</p>
        
        <div class="metrics">
            {''.join([
                f'<div class="metric"><div class="label">{k}</div><div class="value">{v}</div></div>'
                for k, v in metrics.items()
            ])}
        </div>
        
        <div class="fee-info">
            <h3>💰 交易手续费</h3>
            <p><b>佣金率:</b> {COMMISSION_RATE*10000:.1f}‱ (万{COMMISSION_RATE*10000:.1f}) | <b>印花税率:</b> {STAMP_TAX_RATE*10000:.0f}‱ (万{STAMP_TAX_RATE*10000:.0f})</p>
            <p><b>累计佣金:</b> ¥{total_commission:,.2f} | <b>累计印花税:</b> ¥{total_stamp_tax:,.2f} | <b>总费用:</b> ¥{total_fees:,.2f}</p>
        </div>
        
        <div class="section">
            <h2>📊 K线图与买卖信号</h2>
            <div id="chart1"></div>
        </div>
        
        <div class="section">
            <h2>📈 策略表现</h2>
            <div id="chart2"></div>
        </div>
        
        <div class="section">
            <h2>📋 交易明细</h2>
            <table>
                <tr>
                    <th>日期</th><th>方向</th><th>价格</th><th>股数</th>
                    <th>金额</th><th>佣金</th><th>印花税</th><th>净额</th>
                </tr>
                {trades_df.apply(lambda x: f'''
                <tr>
                    <td>{x["date"].strftime("%Y-%m-%d")}</td>
                    <td>{"买入" if x["action"]=="buy" else "卖出"}</td>
                    <td>¥{x["price"]:.2f}</td>
                    <td>{x["shares"]}</td>
                    <td>¥{x["amount"]:,.2f}</td>
                    <td>¥{x["commission"]:.2f}</td>
                    <td>{"¥"+f'{x["stamp_tax"]:.2f}' if x["action"]=="sell" else "-"}</td>
                    <td>¥{x["net"]:,.2f}</td>
                </tr>''', axis=1).str.join("")}
            </table>
        </div>
        
        <div class="section">
            <h2> 概念说明</h2>
            <h3>金叉 (Golden Cross)</h3>
            <p>短期均线（MA{SHORT_W}）从下方穿越长期均线（MA{LONG_W}），信号看涨，执行买入。</p>
            
            <h3>死叉 (Death Cross)</h3>
            <p>短期均线从上方穿越长期均线，信号看跌，执行卖出。</p>
            
            <h3>最大回撤 (MDD)</h3>
            <p>策略净值从历史高点回撤的最大幅度。{mdd:.2%}，发生在 {mdd_date.strftime('%Y-%m-%d')}。</p>
            
            <h3>夏普比率 (Sharpe Ratio)</h3>
            <p>风险调整后的收益指标，{sharpe:.3f}（无风险利率2%，年化）。</p>
        </div>
    </div>
    
    <script>
        var chart1_data = {fig1.to_json()};
        Plotly.newPlot('chart1', chart1_data.data, chart1_data.layout);
        
        var chart2_data = {fig2.to_json()};
        Plotly.newPlot('chart2', chart2_data.data, chart2_data.layout);
    </script>
</body>
</html>"""

# 保存HTML
output_path = "/Users/skyler/workspace/stock_selection/ai_quant/Task3_002281_dual_ma.html"
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Task3 报告已生成: {output_path}")
