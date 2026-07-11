#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate enhanced dashboard HTML with real data
"""

import json
import os

OUTPUT_DIR = "/Users/skyler/workspace/stock_selection/announcement_alpha/data/stock_analysis"

# Read real data
with open(os.path.join(OUTPUT_DIR, "data.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

records = data["records"]
summary = data["summary"]

# Generate HTML with embedded real data
html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>光迅科技(002281.SZ) 技术分析报告 - 增强版</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    padding: 20px;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  .card {{
    background: rgba(255,255,255,0.95);
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.1);
    margin-bottom: 24px;
    padding: 24px;
  }}
  .header {{
    text-align: center;
    color: white;
    margin-bottom: 24px;
  }}
  .header h1 {{ font-size: 2.5rem; margin-bottom: 8px; }}
  .header p {{ font-size: 1.1rem; opacity: 0.9; }}
  .section-title {{
    font-size: 1.5rem;
    font-weight: 600;
    margin-bottom: 16px;
    color: #333;
    border-left: 4px solid #667eea;
    padding-left: 12px;
  }}
  .chart-container {{ width: 100%; height: 500px; }}
  .subchart {{ width: 100%; height: 320px; }}
  .analysis {{
    background: #f8f9fa;
    border-left: 4px solid #667eea;
    padding: 16px;
    margin-top: 16px;
    border-radius: 6px;
  }}
  .analysis h3 {{
    font-size: 1.1rem;
    color: #667eea;
    margin-bottom: 12px;
  }}
  .analysis ul {{ list-style: none; padding-left: 0; }}
  .analysis li {{
    margin-bottom: 8px;
    line-height: 1.6;
    color: #555;
    padding-left: 20px;
    position: relative;
  }}
  .analysis li::before {{
    content: "•";
    color: #667eea;
    font-weight: bold;
    display: inline-block;
    width: 20px;
    margin-left: -20px;
  }}
  .analysis .indicator {{
    display: inline-block;
    background: #667eea;
    color: white;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
    margin-right: 4px;
  }}
  .signal-badges {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
  .badge {{
    padding: 8px 16px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.9rem;
  }}
  .badge-success {{ background: #d4edda; color: #155724; }}
  .badge-danger {{ background: #f8d7da; color: #721c24; }}
  .badge-warning {{ background: #fff3cd; color: #856404; }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
  .operation-box {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 24px;
  }}
  .operation-box h2 {{ margin-bottom: 16px; }}
  .operation-box ul {{ margin-left: 20px; }}
  .operation-box li {{ margin-bottom: 10px; line-height: 1.6; }}
  .risk-box {{
    background: #fff3cd;
    border: 2px solid #ffc107;
    padding: 20px;
    border-radius: 8px;
  }}
  .risk-box h3 {{ color: #856404; margin-bottom: 12px; }}
  .risk-box ul {{ margin-left: 20px; }}
  .risk-box li {{ margin-bottom: 8px; color: #856404; line-height: 1.6; }}
  .price-range {{
    display: flex;
    justify-content: space-between;
    background: #e9ecef;
    padding: 12px;
    border-radius: 6px;
    margin: 16px 0;
  }}
  .price-item {{ text-align: center; }}
  .price-item .label {{ font-size: 0.85rem; color: #6c757d; }}
  .price-item .value {{ font-size: 1.3rem; font-weight: 600; color: #333; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📈 光迅科技(002281.SZ)</h1>
    <p>光通信器件龙头 | AI算力受益标的 | 技术分析增强版</p>
    <p style="margin-top: 8px; font-size: 0.95rem;">分析数据: {records[0]['date']} 至 {records[-1]['date']}</p>
  </div>

  <!-- 技术信号概览 -->
  <div class="card">
    <div class="section-title">🎯 技术信号概览</div>
    <div class="signal-badges">
      <span class="badge badge-warning">🟡 趋势：均线纠缠，方向不明</span>
      <span class="badge badge-danger">🔴 MACD：死叉形成，短期看空</span>
      <span class="badge badge-warning">🟡 RSI14：{summary['rsi14']:.1f} 中性区间</span>
      <span class="badge badge-danger">🔴 布林：价格位于中轨之下，偏弱整理</span>
    </div>
  </div>

  <!-- K线图 + 技术解读 -->
  <div class="card">
    <div class="section-title">📊 K线走势 + 均线系统 + 布林带</div>
    <div id="chart-kline" class="chart-container"></div>
    
    <div class="analysis">
      <h3>🔍 技术面解读</h3>
      <ul>
        <li><span class="indicator">均线系统</span> 当前价格 <strong>{summary['latest_close']:.2f}</strong> 已跌破 MA5({summary['ma5']:.2f}) 和 MA20({summary['ma20']:.2f})，但仍站在 MA60({summary['ma60']:.2f}) 上方。短期均线（MA5/MA20）拐头向下，与长期均线(MA60)形成压制，显示中期调整压力较大。</li>
        <li><span class="indicator">布林带</span> 价格 <strong>{summary['latest_close']:.2f}</strong> 已跌破布林中轨({summary.get('boll_mid', 0):.2f}或约{summary['boll_mid']:.2f})，当前位于中轨与下轨({summary['boll_dn']:.2f})之间的中下部区域。布林带开口较大，显示波动率较高。下轨 {summary['boll_dn']:.2f} 是重要支撑位。</li>
        <li><span class="indicator">年度表现</span> 年内从最低 <strong>{summary['year_low']:.2f}</strong> 涨至最高 <strong>{summary['year_high']:.2f}</strong>，涨幅达 <strong>{(summary['year_high']-summary['year_low'])/summary['year_low']*100:.0f}%</strong>，属于超强势主升浪。当前从高点 {summary['year_high']:.2f} 回撤至 {summary['latest_close']:.2f}，回撤幅度 <strong>{(summary['year_high']-summary['latest_close'])/summary['year_high']*100:.1f}%</strong>，符合强势股回调特征。</li>
      </ul>
    </div>
  </div>

  <!-- MACD图 + 技术解读 -->
  <div class="card">
    <div class="section-title">📉 MACD 指标</div>
    <div id="chart-macd" class="subchart"></div>
    
    <div class="analysis">
      <h3>🔍 技术面解读</h3>
      <ul>
        <li><span class="indicator">DIF/DEA</span> DIF({summary['dif']:.2f}) 已下穿 DEA({summary['dea']:.2f})，形成<strong>死叉</strong>。MACD 柱体为负值，显示空头力量占优，短期趋势偏弱。</li>
        <li><span class="indicator">位置判断</span> DIF 和 DEA 均处于零轴{"上方" if summary['dif'] > 0 else "下方"}，说明{"中长期趋势仍为多头" if summary['dif'] > 0 else "中长期趋势已转空"}。{"但短期死叉信号明确，需要关注是否能企稳回升。" if summary['dif'] > 0 else "需要等待趋势反转信号。"}若 DIF 继续下行逼近零轴，可能触发进一步调整。</li>
        <li><span class="indicator">操作提示</span> MACD 死叉确认后，短期内反弹空间有限。建议等待 MACD 柱体由负转正（即重新金叉）或 DIF 止跌企稳后再考虑介入。</li>
      </ul>
    </div>
  </div>

  <!-- RSI图 + 技术解读 -->
  <div class="card">
    <div class="section-title">📈 RSI 相对强弱指标</div>
    <div id="chart-rsi" class="subchart"></div>
    
    <div class="analysis">
      <h3>🔍 技术面解读</h3>
      <ul>
        <li><span class="indicator">RSI14</span> 当前 RSI14 为 <strong>{summary['rsi14']:.1f}</strong>，处于{"超买区间(>70)，需警惕回调风险" if summary['rsi14'] > 70 else "超卖区间(<30)，关注反弹机会" if summary['rsi14'] < 30 else "中性区间（30-70之间）"}。{"既未超买也未超卖，显示多空力量相对均衡。" if 30 <= summary['rsi14'] <= 70 else ""}</li>
        <li><span class="indicator">历史区间</span> 从走势图看，RSI 在年前期从超卖区(&lt;30)快速攀升至 80 以上强超买区，随后回落至当前 50 附近。若继续下行至 30 以下，可能形成超卖反弹机会。</li>
        <li><span class="indicator">辅助判断</span> RSI {"中性偏弱" if summary['rsi14'] < 50 else "中性偏强"}，配合 MACD 死叉，短期{"仍有下探风险" if summary['rsi14'] < 50 else "需关注是否企稳"}。{"但若 RSI 快速下探至 30 以下形成超卖，可能触发技术性反弹。" if summary['rsi14'] < 60 else ""}</li>
      </ul>
    </div>
  </div>

  <!-- 基本面分析 -->
  <div class="card">
    <div class="section-title">💼 基本面分析</div>
    
    <div class="grid-2">
      <div>
        <h3 style="color: #667eea; margin-bottom: 12px;">🏢 公司概况</h3>
        <ul style="list-style: none; line-height: 1.8;">
          <li><strong>公司全称：</strong>武汉光迅科技股份有限公司</li>
          <li><strong>所属行业：</strong>光通信器件</li>
          <li><strong>主营业务：</strong>光电子器件、光模块、光传输设备</li>
          <li><strong>行业地位：</strong>国内光通信器件龙头企业，全球前列</li>
          <li><strong>核心客户：</strong>华为、中兴、三大运营商、海外云厂商</li>
        </ul>
      </div>
      
      <div>
        <h3 style="color: #667eea; margin-bottom: 12px;">🚀 核心驱动因素</h3>
        <ul style="list-style: none; line-height: 1.8;">
          <li><strong>AI算力基建：</strong>全球数据中心建设加速，光模块需求爆发</li>
          <li><strong>800G升级：</strong>高速光模块进入放量期，单价和毛利率提升</li>
          <li><strong>国产替代：</strong>光芯片国产化进程加快，公司技术领先</li>
          <li><strong>政策支持：</strong>数字经济、东数西算等政策利好</li>
          <li><strong>订单饱满：</strong>下游需求旺盛，产能利用率维持高位</li>
        </ul>
      </div>
    </div>

    <div class="analysis" style="margin-top: 24px;">
      <h3>📊 基本面判断</h3>
      <ul>
        <li><span class="indicator">行业周期</span> 光通信行业正处于 5G→AI 的升级周期，800G 光模块成为新的增长引擎。公司作为国内龙头，充分受益于行业高景气度。</li>
        <li><span class="indicator">业绩预期</span> 2025-2026 年为公司业绩爆发期，高速光模块出货量大幅增长，叠加产品结构优化（800G 占比提升），毛利率有望持续改善。</li>
        <li><span class="indicator">估值水平</span> 年内从 {summary['year_low']:.0f} 涨至 {summary['year_high']:.0f}（涨幅 {int((summary['year_high']-summary['year_low'])/summary['year_low']*100)}%），当前估值已处于历史高位。需要业绩持续兑现来消化估值，短期存在回调压力。</li>
      </ul>
    </div>
  </div>

  <!-- 综合研判与操作建议 -->
  <div class="card">
    <div class="section-title">🎯 综合研判与操作建议</div>
    
    <div class="price-range">
      <div class="price-item">
        <div class="label">当前价格</div>
        <div class="value">{summary['latest_close']:.2f}</div>
      </div>
      <div class="price-item">
        <div class="label">年内最高</div>
        <div class="value" style="color: #d32f2f;">{summary['year_high']:.2f}</div>
      </div>
      <div class="price-item">
        <div class="label">年内最低</div>
        <div class="value" style="color: #388e3c;">{summary['year_low']:.2f}</div>
      </div>
      <div class="price-item">
        <div class="label">MA60 支撑</div>
        <div class="value">{summary['ma60']:.2f}</div>
      </div>
      <div class="price-item">
        <div class="label">布林下轨</div>
        <div class="value">{summary['boll_dn']:.2f}</div>
      </div>
    </div>

    <div class="operation-box">
      <h2>💡 操作建议</h2>
      <ul>
        <li><strong>短期策略（1-2周）：</strong>技术面信号偏弱（MACD死叉、价格跌破中期均线），建议<strong>观望为主</strong>，不急于抄底。等待 MACD 重新金叉或价格站稳 MA20 后再考虑介入。</li>
        <li><strong>中期策略（1-3月）：</strong>光通信行业景气度仍高，基本面支撑较强。若股价回调至<strong>{summary['boll_dn']:.0f}-{summary['ma60']:.0f} 区间</strong>（接近 MA60 和布林下轨），可考虑分批建仓。中线目标看 240-260 区间。</li>
        <li><strong>持仓建议：</strong>已持仓者可<strong>逢高减仓</strong>，降低仓位至 30% 以下。若跌破 180 元（MA60 下方），需止损离场。若站稳 240 以上，可考虑加仓。</li>
        <li><strong>关键点位：</strong></li>
        <ul style="margin-top: 8px;">
          <li>• <strong>强支撑：</strong>{summary['boll_dn']:.0f}-{summary['ma60']:.0f}（布林下轨 + MA60）</li>
          <li>• <strong>弱支撑：</strong>200-210（心理关口）</li>
          <li>• <strong>压力位：</strong>235（MA5 + MA20）</li>
          <li>• <strong>强压力：</strong>260-280（前高区域）</li>
        </ul>
      </ul>
    </div>
  </div>

  <!-- 风险提示 -->
  <div class="card">
    <div class="risk-box">
      <h3>⚠️ 风险提示</h3>
      <ul>
        <li><strong>估值风险：</strong>年内涨幅已超 500%，估值处于历史高位。若业绩不及预期，可能面临戴维斯双杀（估值 + 业绩双降）。</li>
        <li><strong>行业周期：</strong>光通信行业具有周期性，若 AI 算力投资放缓或 800G 升级不及预期，可能影响公司业绩增长。</li>
        <li><strong>竞争加剧：</strong>国内外光模块厂商扩产，若行业竞争加剧，可能压缩毛利率。</li>
        <li><strong>汇率风险：</strong>公司有一定海外收入，人民币升值可能影响出口竞争力和汇兑收益。</li>
        <li><strong>技术迭代：</strong>光通信技术迭代快（如 1.6T），若研发进度落后，可能被竞争对手超越。</li>
        <li><strong>市场情绪：</strong>A股整体波动较大，若市场风险偏好下降，可能引发系统性回调。</li>
      </ul>
    </div>
  </div>

  <!-- 总结 -->
  <div class="card">
    <div class="section-title">📝 总结</div>
    <div class="analysis">
      <h3>🎯 核心观点</h3>
      <ul>
        <li><strong>基本面：</strong>光通信行业高景气，公司作为国内龙头，充分受益于 AI 算力基建和 800G 升级。中长期看好，但短期估值较高。</li>
        <li><strong>技术面：</strong>短期信号偏弱（MACD 死叉 + 价格跌破中期均线），存在进一步回调压力。但均线仍在零轴上方，中长期趋势未破坏。</li>
        <li><strong>操作建议：</strong>短期观望为主，等待技术面企稳信号。若回调至 {summary['boll_dn']:.0f}-{summary['ma60']:.0f} 区间（强支撑），可考虑分批建仓。持仓者逢高减仓，控制风险。</li>
        <li><strong>关键指标：</strong>MACD 重新金叉、价格站稳 MA20 为短期看多信号。跌破 180 则为止损信号。</li>
      </ul>
    </div>
  </div>

  <div style="text-align: center; color: white; margin-top: 24px; opacity: 0.8;">
    <p>⚠️ 免责声明：本分析仅供参考，不构成投资建议。股市有风险，投资需谨慎。</p>
    <p style="margin-top: 8px; font-size: 0.9rem;">分析日期：{summary['latest_date']} | 数据周期：{records[0]['date']} 至 {records[-1]['date']}</p>
  </div>
</div>

<script>
const rawData = {json.dumps(records)};

const dates = rawData.map(d => d.date);
const closes = rawData.map(d => d.close);
const opens = rawData.map(d => d.open);
const highs = rawData.map(d => d.high);
const lows = rawData.map(d => d.low);
const ma5 = rawData.map(d => d.ma5);
const ma10 = rawData.map(d => d.ma10);
const ma20 = rawData.map(d => d.ma20);
const ma60 = rawData.map(d => d.ma60);
const bollUp = rawData.map(d => d.boll_up);
const bollMid = rawData.map(d => d.boll_mid);
const bollDn = rawData.map(d => d.boll_dn);
const dif = rawData.map(d => d.dif);
const dea = rawData.map(d => d.dea);
const macd = rawData.map(d => d.macd);
const rsi6 = rawData.map(d => d.rsi6);
const rsi14 = rawData.map(d => d.rsi14);

const candleData = rawData.map(d => [d.open, d.close, d.low, d.high]);

// K线图
const chartKline = echarts.init(document.getElementById('chart-kline'));
chartKline.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60', '布林上轨', '布林中轨', '布林下轨'], top: 10 }},
  grid: {{ left: '10%', right: '5%', top: 60, bottom: 60 }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: {{ type: 'value', scale: true, axisLabel: {{ formatter: v => v.toFixed(0) }} }},
  dataZoom: [
    {{ type: 'inside', xAxisIndex: 0, start: 70, end: 100 }},
    {{ type: 'slider', xAxisIndex: 0, bottom: 20, height: 20 }}
  ],
  series: [
    {{ name: 'K线', type: 'candlestick', data: candleData, itemStyle: {{ color: '#d32f2f', color0: '#388e3c', borderColor: '#d32f2f', borderColor0: '#388e3c' }} }},
    {{ name: 'MA5', type: 'line', data: ma5, lineStyle: {{ width: 1.5, color: '#1976d2' }} }},
    {{ name: 'MA10', type: 'line', data: ma10, lineStyle: {{ width: 1.5, color: '#f57c00' }} }},
    {{ name: 'MA20', type: 'line', data: ma20, lineStyle: {{ width: 2, color: '#7b1fa2' }} }},
    {{ name: 'MA60', type: 'line', data: ma60, lineStyle: {{ width: 2, color: '#c62828' }} }},
    {{ name: '布林上轨', type: 'line', data: bollUp, lineStyle: {{ width: 1, type: 'dashed', color: '#90a4ae' }} }},
    {{ name: '布林中轨', type: 'line', data: bollMid, lineStyle: {{ width: 1, type: 'dotted', color: '#90a4ae' }} }},
    {{ name: '布林下轨', type: 'line', data: bollDn, lineStyle: {{ width: 1, type: 'dashed', color: '#90a4ae' }} }},
  ]
}});

// MACD
const chartMacd = echarts.init(document.getElementById('chart-macd'));
chartMacd.setOption({{
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: ['MACD', 'DIF', 'DEA'], top: 10 }},
  grid: {{ left: '10%', right: '5%', top: 50, bottom: 40 }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: {{ type: 'value', scale: true }},
  series: [
    {{ name: 'MACD', type: 'bar', data: macd, itemStyle: {{ color: p => p.value >= 0 ? '#d32f2f' : '#388e3c' }} }},
    {{ name: 'DIF', type: 'line', data: dif, lineStyle: {{ width: 1.5, color: '#1976d2' }} }},
    {{ name: 'DEA', type: 'line', data: dea, lineStyle: {{ width: 1.5, color: '#f57c00' }} }},
  ]
}});

// RSI
const chartRsi = echarts.init(document.getElementById('chart-rsi'));
chartRsi.setOption({{
  tooltip: {{ trigger: 'axis' }},
  legend: {{ data: ['RSI6', 'RSI14'], top: 10 }},
  grid: {{ left: '10%', right: '5%', top: 50, bottom: 40 }},
  xAxis: {{ data: dates, axisLabel: {{ rotate: 45 }} }},
  yAxis: {{ type: 'value', min: 0, max: 100 }},
  series: [
    {{ name: 'RSI6', type: 'line', data: rsi6, lineStyle: {{ width: 1.5, color: '#1976d2' }} }},
    {{ name: 'RSI14', type: 'line', data: rsi14, lineStyle: {{ width: 1.5, color: '#f57c00' }} }},
  ],
  graphic: [
    {{ type: 'line', shape: {{ x1: '10%', y1: '70%', x2: '90%', y2: '70%' }}, style: {{ stroke: '#d32f2f', lineDash: [4, 4] }} }},
    {{ type: 'line', shape: {{ x1: '10%', y1: '30%', x2: '90%', y2: '30%' }}, style: {{ stroke: '#388e3c', lineDash: [4, 4] }} }},
  ]
}});

window.addEventListener('resize', () => {{
  chartKline.resize();
  chartMacd.resize();
  chartRsi.resize();
}});
</script>
</body>
</html>
'''

# Write the HTML file
output_path = os.path.join(OUTPUT_DIR, "dashboard_enhanced.html")
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"✅ Enhanced dashboard generated: {output_path}")
print(f"   File size: {os.path.getsize(output_path):,} bytes")
print(f"   Data points: {len(records)}")
print(f"   Period: {records[0]['date']} to {records[-1]['date']}")
