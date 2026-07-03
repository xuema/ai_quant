#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成光迅科技技术分析网页面板
"""

import json
import os

OUTPUT_DIR = "/Users/skyler/workspace/stock_selection/announcement_alpha/data/stock_analysis"

# 读取数据
with open(os.path.join(OUTPUT_DIR, "summary.json"), "r", encoding="utf-8") as f:
    summary = json.load(f)

with open(os.path.join(OUTPUT_DIR, "data.json"), "r", encoding="utf-8") as f:
    payload = json.load(f)
    records = payload["records"]

# 生成信号卡片 HTML
def make_signal_cards(signals):
    cards = []
    for s in signals:
        colors = {
            "bullish": ("success", "🟢", "rgba(46, 204, 113, 0.15)", "#2ecc71"),
            "bearish": ("danger", "🔴", "rgba(231, 76, 60, 0.15)", "#e74c3c"),
            "neutral": ("warning", "🟡", "rgba(241, 196, 15, 0.15)", "#f1c40f"),
        }
        variant = colors[s["tone"]][0]
        emoji = colors[s["tone"]][1]
        bg = colors[s["tone"]][2]
        border = colors[s["tone"]][3]
        cards.append(f"""
        <div class="card signal-card" style="background:{bg};border-color:{border}">
          <div class="card-body p-3">
            <h6 class="card-title mb-2"><strong>{emoji} {s['category']}</strong></h6>
            <p class="card-text small mb-0">{s['description']}</p>
          </div>
        </div>
        """)
    return "\n".join(cards)

signal_cards_html = make_signal_cards(summary.get("signals", []))

# 生成HTML
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>光迅科技(002281) 技术分析报告</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
  body {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px 0; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .container-fluid {{ max-width: 1600px; }}
  .card {{ border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.1); margin-bottom: 20px; }}
  .signal-card {{ border-width: 2px; }}
  .stat-card {{ background: rgba(255,255,255,0.95); }}
  .stat-value {{ font-size: 1.8rem; font-weight: 700; margin: 10px 0; }}
  .stat-label {{ font-size: 0.85rem; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; }}
  .positive {{ color: #d32f2f; }}
  .negative {{ color: #388e3c; }}
  .neutral {{ color: #757575; }}
  .chart-container {{ width: 100%; height: 500px; background: white; border-radius: 8px; }}
  .subchart {{ width: 100%; height: 320px; background: white; border-radius: 8px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; }}
  .badge-lg {{ font-size: 0.9rem; padding: 8px 16px; font-weight: 500; }}
  #loading {{ position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(255,255,255,0.95); display: flex; align-items: center; justify-content: center; z-index: 9999; }}
  .spinner-border {{ width: 3rem; height: 3rem; }}
</style>
</head>
<body>
<div id="loading">
  <div class="text-center">
    <div class="spinner-border text-primary" role="status"></div>
    <p class="mt-3 text-muted">正在加载技术数据...</p>
  </div>
</div>

<div class="container-fluid">
  <div class="row mb-4">
    <div class="col-12">
      <div class="card">
        <div class="card-body text-center py-4">
          <h1 class="mb-2">📈 光迅科技(002281.SZ)</h1>
          <h4 class="text-muted">技术分析报告</h4>
          <p class="text-muted mb-0">数据区间：{records[0]['date']} 至 {summary['latest_date']} | 共 {len(records)} 个交易日</p>
        </div>
      </div>
    </div>
  </div>

  <!-- 核心指标卡片 -->
  <div class="row mb-4">
    <div class="col-md-3 col-sm-6">
      <div class="card stat-card">
        <div class="card-body text-center">
          <div class="stat-label">最新收盘价</div>
          <div class="stat-value {'positive' if summary['latest_chg']>=0 else 'negative'}">{summary['latest_close']:.2f}</div>
          <span class="badge {'text-bg-danger' if summary['latest_chg']>=0 else 'text-bg-success'} badge-lg">{summary['latest_chg']:+.2f}%</span>
        </div>
      </div>
    </div>
    <div class="col-md-3 col-sm-6">
      <div class="card stat-card">
        <div class="card-body text-center">
          <div class="stat-label">年度最高/最低</div>
          <div class="stat-value text-danger">{summary['year_high']:.2f}</div>
          <div class="text-success fs-5">{summary['year_low']:.2f}</div>
        </div>
      </div>
    </div>
    <div class="col-md-3 col-sm-6">
      <div class="card stat-card">
        <div class="card-body text-center">
          <div class="stat-label">RSI14</div>
          <div class="stat-value {'positive' if summary['rsi14']>55 else 'negative' if summary['rsi14']<45 else 'neutral'}">{summary['rsi14']:.1f}</div>
          <div class="text-muted small">{'偏强' if summary['rsi14']>55 else '偏弱' if summary['rsi14']<45 else '中性'}</div>
        </div>
      </div>
    </div>
    <div class="col-md-3 col-sm-6">
      <div class="card stat-card">
        <div class="card-body text-center">
          <div class="stat-label">成交量(万手)</div>
          <div class="stat-value">{summary['latest_vol_wan']:.2f}</div>
          <div class="text-muted small">均量: {summary['year_avg_vol']:.0f}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- 主图：K线+布林带+均线 -->
  <div class="row mb-4">
    <div class="col-12">
      <div class="p-3 bg-white rounded">
        <div id="chart-kline" class="chart-container"></div>
      </div>
    </div>
  </div>

  <!-- 副图：MACD -->
  <div class="row mb-4">
    <div class="col-12">
      <div class="p-3 bg-white rounded">
        <div id="chart-macd" class="subchart"></div>
      </div>
    </div>
  </div>

  <!-- 副图：RSI -->
  <div class="row mb-4">
    <div class="col-12">
      <div class="p-3 bg-white rounded">
        <div id="chart-rsi" class="subchart"></div>
      </div>
    </div>
  </div>

  <!-- 技术指标信号解读 -->
  <div class="row mb-4">
    <div class="col-12">
      <div class="card">
        <div class="card-header bg-dark text-white">
          <h5 class="mb-0">🎯 技术信号解读</h5>
        </div>
        <div class="card-body">
          <div class="row">
            {signal_cards_html if signal_cards_html else '<div class="col-12 text-center text-muted">暂无信号数据</div>'}
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 详细指标表 -->
  <div class="row mb-4">
    <div class="col-12">
      <div class="card">
        <div class="card-header">
          <h5 class="mb-0">📊 关键技术指标</h5>
        </div>
        <div class="card-body">
          <table class="table table-hover">
            <thead>
              <tr><th>指标</th><th>数值</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr><td><strong>MA5</strong></td><td>{summary['ma5']:.2f}</td><td>5日均线（短期趋势）</td></tr>
              <tr><td><strong>MA20</strong></td><td>{summary['ma20']:.2f}</td><td>20日均线（中期趋势）</td></tr>
              <tr><td><strong>MA60</strong></td><td>{summary['ma60']:.2f}</td><td>60日均线（长期趋势）</td></tr>
              <tr><td><strong>DIF</strong></td><td>{summary['dif']:.4f}</td><td>MACD指标DIF线</td></tr>
              <tr><td><strong>DEA</strong></td><td>{summary['dea']:.4f}</td><td>MACD指标DEA线</td></tr>
              <tr><td><strong>布林上轨</strong></td><td>{summary['boll_up']:.2f}</td><td>Bollinger Bands上轨</td></tr>
              <tr><td><strong>布林下轨</strong></td><td>{summary['boll_dn']:.2f}</td><td>Bollinger Bands下轨</td></tr>
              <tr><td><strong>换手率</strong></td><td>{summary['latest_turnover']:.2f}%</td><td>最新交易日换手率</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div class="text-center text-white mb-5">
    <p class="small opacity-75">⚠️ 本报告仅供参考，不构成投资建议。股市有风险，投资需谨慎。</p>
  </div>
</div>

<script>
const data = {json.dumps(records)};

// 提取数据数组
const dates = data.map(d => d.date);
const closes = data.map(d => d.close);
const opens  = data.map(d => d.open);
const highs  = data.map(d => d.high);
const lows   = data.map(d => d.low);
const vols   = data.map(d => d.vol / 10000);
const ma5    = data.map(d => d.ma5);
const ma10   = data.map(d => d.ma10);
const ma20   = data.map(d => d.ma20);
const ma60   = data.map(d => d.ma60);
const dif    = data.map(d => d.dif);
const dea    = data.map(d => d.dea);
const macd   = data.map(d => d.macd);
const rsi6   = data.map(d => d.rsi6);
const rsi14  = data.map(d => d.rsi14);
const bollUp = data.map(d => d.boll_up);
const bollMid= data.map(d => d.boll_mid);
const bollDn = data.map(d => d.boll_dn);

// 生成K线数据 [open, close, low, high]
const candleData = data.map(d => [d.open, d.close, d.low, d.high]);

// 成交量颜色（红涨绿跌）
const volColors = data.map(d => d.close >= d.open ? '#d32f2f' : '#388e3c');

// ─── K线图 ───
const chartKline = echarts.init(document.getElementById('chart-kline'));
chartKline.setOption({{
  title: {{ text: 'K线走势 + 布林带 + 均线', textStyle: {{ fontSize: 14 }} }},
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60', '布林上轨', '布林中轨', '布林下轨'], top: 30 }},
  grid: {{ left: '8%', right: '3%', bottom: '10%' }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: [
    {{ type: 'value', scale: true, axisLabel: {{ formatter: v => v.toFixed(2) }} }},
  ],
  dataZoom: [
    {{ type: 'inside', xAxisIndex: 0, start: 70, end: 100 }},
    {{ type: 'slider', xAxisIndex: 0, bottom: 20, height: 20 }}
  ],
  series: [
    {{
      name: 'K线', type: 'candlestick', data: candleData,
      itemStyle: {{
        color: '#d32f2f', color0: '#388e3c',
        borderColor: '#d32f2f', borderColor0: '#388e3c'
      }}
    }},
    {{ name: 'MA5', type: 'line', data: ma5, lineStyle: {{ width: 1 }}, symbol: 'none' }},
    {{ name: 'MA10', type: 'line', data: ma10, lineStyle: {{ width: 1 }}, symbol: 'none' }},
    {{ name: 'MA20', type: 'line', data: ma20, lineStyle: {{ width: 1.5 }}, symbol: 'none' }},
    {{ name: 'MA60', type: 'line', data: ma60, lineStyle: {{ width: 1.5 }}, symbol: 'none' }},
    {{ name: '布林上轨', type: 'line', data: bollUp, lineStyle: {{ width: 1, type: 'dashed', color: '#3498db' }}, symbol: 'none' }},
    {{ name: '布林中轨', type: 'line', data: bollMid, lineStyle: {{ width: 1, type: 'dotted', color: '#9b59b6' }}, symbol: 'none' }},
    {{ name: '布林下轨', type: 'line', data: bollDn, lineStyle: {{ width: 1, type: 'dashed', color: '#3498db' }}, symbol: 'none' }},
  ]
}});

// ─── MACD图 ───
const chartMacd = echarts.init(document.getElementById('chart-macd'));
chartMacd.setOption({{
  title: {{ text: 'MACD (12, 26, 9)', textStyle: {{ fontSize: 13 }} }},
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: ['MACD', 'DIF', 'DEA'], top: 25 }},
  grid: {{ left: '10%', right: '3%', bottom: '15%' }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: {{ type: 'value', scale: true }},
  dataZoom: [
    {{ type: 'inside', xAxisIndex: 0, start: 70, end: 100 }}
  ],
  series: [
    {{
      name: 'MACD', type: 'bar', data: macd,
      itemStyle: {{ color: p => p.value >= 0 ? '#d32f2f' : '#388e3c' }}
    }},
    {{ name: 'DIF', type: 'line', data: dif, lineStyle: {{ width: 1.2 }}, symbol: 'none' }},
    {{ name: 'DEA', type: 'line', data: dea, lineStyle: {{ width: 1.2 }}, symbol: 'none' }},
  ]
}});

// ─── RSI图 ───
const chartRsi = echarts.init(document.getElementById('chart-rsi'));
chartRsi.setOption({{
  title: {{ text: 'RSI (6, 14)', textStyle: {{ fontSize: 13 }} }},
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: ['RSI6', 'RSI14'], top: 25 }},
  grid: {{ left: '10%', right: '3%', bottom: '15%' }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: {{ type: 'value', min: 0, max: 100 }},
  dataZoom: [
    {{ type: 'inside', xAxisIndex: 0, start: 70, end: 100 }}
  ],
  visualMap: {{
    show: false, seriesIndex: 1, pieces: [
      {{ lte: 30, color: '#27ae60' }},
      {{ gt: 30, lte: 70, color: '#f39c12' }},
      {{ gt: 70, color: '#c0392b' }}
    ]
  }},
  series: [
    {{ name: 'RSI6', type: 'line', data: rsi6, lineStyle: {{ width: 1.2 }}, symbol: 'none' }},
    {{ name: 'RSI14', type: 'line', data: rsi14, lineStyle: {{ width: 1.2 }}, symbol: 'none' }},
  ],
  graphic: [
    {{ type: 'line', shape: {{ x1: '10%', y1: '70%', x2: '97%', y2: '70%' }}, style: {{ stroke: '#c0392b', lineDash: [4,4] }} }},
    {{ type: 'line', shape: {{ x1: '10%', y1: '30%', x2: '97%', y2: '30%' }}, style: {{ stroke: '#27ae60', lineDash: [4,4] }} }},
  ]
}});

window.addEventListener('resize', () => {{
  chartKline.resize();
  chartMacd.resize();
  chartRsi.resize();
}});

document.getElementById('loading').style.display = 'none';
</script>
</body>
</html>
"""

html_path = os.path.join(OUTPUT_DIR, f"dashboard_{summary['latest_date'].replace('-','')}.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✓ Dashboard generated: {html_path}")
print(f"\\n📊 Summary:")
print(f"   Latest close: {summary['latest_close']:.2f} ({summary['latest_chg']:+.2f}%)")
print(f"   Year high: {summary['year_high']:.2f}  |  Year low: {summary['year_low']:.2f}")
print(f"   RSI14: {summary['rsi14']:.1f}")
print(f"\\n🎯 Technical signals:")
for s in summary['signals']:
    print(f"   {s['category']}: {s['description']}")
print(f"\\n🌐 Open the dashboard in your browser:")
print(f"   file://{html_path}")
