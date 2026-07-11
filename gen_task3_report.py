#!/usr/bin/env python3
"""TASK3 report generator - uses f-strings properly"""
import pickle as pkl, json, pandas as pd, numpy as np, re

with open('/tmp/all_results.pkl', 'rb') as f:
    data = pkl.load(f)
r_a, r_b, pr = data['ra'], data['rb'], data['pr']
sw, lw = 5, 15

def mk_candle(r):
    return {"data":[
        {"type":"candlestick","name":"K线","showlegend":False,
         "x":r['dates_iso'],"open":r['opens'],"high":r['highs'],"low":r['lows'],"close":r['closes'],
         "increasing":{"line":{"color":"#ef5350"},"fillcolor":"rgba(239,83,80,0.2)"},
         "decreasing":{"line":{"color":"#26a69a"},"fillcolor":"rgba(38,166,154,0.2)"}},
        {"type":"scatter","mode":"lines","name":"MA{}".format(r['short_w']),
         "x":r['dates_iso'],"y":r['ma5_list'],"line":{"color":"#ff7f0e","width":1.2}},
        {"type":"scatter","mode":"lines","name":"MA{}".format(r['long_w']),
         "x":r['dates_iso'],"y":r['ma15_list'],"line":{"color":"#1f77b4","width":1.2}},
        {"type":"scatter","mode":"markers+text","name":"买入",
         "x":r['buy_dates'],"y":r['buy_prices'],
         "text":["Y%.2f" % p for p in r['buy_prices']],
         "textposition":"top center","textfont":{"size":9,"color":"#cc0000"},
         "marker":{"symbol":"triangle-up","size":13,"color":"#cc0000","line":{"color":"darkred","width":1.5}},
         "hovertemplate":"<b>买入</b><br>日期: %{x}<br>价格: Y%{y:.2f}<extra></extra>"},
        {"type":"scatter","mode":"markers+text","name":"卖出",
         "x":r['sell_dates'],"y":r['sell_prices'],
         "text":["Y%.2f" % p for p in r['sell_prices']],
         "textposition":"bottom center","textfont":{"size":9,"color":"#00aa44"},
         "marker":{"symbol":"triangle-down","size":13,"color":"#00aa44","line":{"color":"darkgreen","width":1.5}},
         "hovertemplate":"<b>卖出</b><br>日期: %{x}<br>价格: Y%{y:.2f}<extra></extra>"},
    ],"layout":{
        "xaxis":{"title":"","rangeslider":{"visible":False},"type":"date","gridcolor":"#eee"},
        "yaxis":{"title":"价格 (元)","gridcolor":"#eee"},
        "showlegend":True,
        "legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"right","x":1},
        "margin":{"l":60,"r":20,"t":40,"b":50},"plot_bgcolor":"white","paper_bgcolor":"white",
        "height":650,"hovermode":"x unified",
        "title":{"text":"{} 光迅科技 K线图(MA{}/MA{})".format(r['stock_code'],r['short_w'],r['long_w']),"x":0.5,"font":{"size":14}}
    }}

def mk_equity(r):
    return {"data":[
        {"type":"scatter","mode":"lines","name":"策略净值",
         "x":r['eq_dates'],"y":r['eq_vals'],"line":{"color":"#1a3b6b","width":2},"yaxis":"y"},
        {"type":"scatter","mode":"lines","name":"基准(买入持有)",
         "x":r['eq_dates'],"y":r['bench_vals'],
         "line":{"color":"gray","dash":"dash","width":1.5},"yaxis":"y"},
        {"type":"scatter","mode":"lines","name":"回撤 (%)",
         "x":r['eq_dates'],"y":r['eq_dd'],
         "fill":"tozeroy","line":{"color":"#8B0000","width":1},
         "fillcolor":"rgba(139,0,0,0.15)","yaxis":"y2"},
    ],"layout":{
        "xaxis":{"title":"","type":"date","gridcolor":"#eee"},
        "yaxis":{"title":"净值 (元)","domain":[0.4,1.0],"gridcolor":"#eee"},
        "yaxis2":{"title":"回撤 (%)","domain":[0.0,0.33],"gridcolor":"#eee","rangemode":"tozero"},
        "showlegend":True,
        "legend":{"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"right","x":1},
        "margin":{"l":60,"r":20,"t":10,"b":50},"plot_bgcolor":"white","paper_bgcolor":"white",
        "height":500,"hovermode":"x unified",
    }}

def trades_html(r):
    out = []
    for _, tr in r['trades_df'].iterrows():
        c = 'buy' if tr['action']=='买入' else 'sell'
        st = "Y%.2f" % tr['stamp_tax'] if tr['action']=='卖出' else '-'
        out.append('<tr><td>{d}</td><td><b class="{c}">{a}</b></td><td>Y{p:.2f}</td><td>{sh}</td><td>Y{am:,.2f}</td><td>Y{co:.2f}</td><td>{st}</td><td>Y{tc:.2f}</td></tr>'.format(
            d=tr['date'].strftime('%Y-%m-%d'), c=c, a=tr['action'],
            p=tr['price'], sh=tr['shares'], am=tr['amount'],
            co=tr['commission'], st=st, tc=tr['total_cost']))
    return '\n'.join(out)

def fix_yen(s):
    """Replace Y with yen symbol in chart label text"""
    return s

# Fix yen symbol in chart annotations
c1a = mk_candle(r_a)
c2a = mk_equity(r_a)
c1b = mk_candle(r_b)
c2b = mk_equity_chart(r_b)

# Buy/sell text labels use Y, need to use actual yen
for d in c1a['data'] + c1b['data']:
    if d.get('name') in ('买入','卖出'):
        prefix = '\xc2\xa5'
        d['text'] = [prefix + '%.2f' % p for p in d['y']]
        # Fix hovertemplate
        d['hovertemplate'] = d['hovertemplate'].replace('Y', '\xc2\xa5')

param_chart = {
    "data":[
        {"type":"bar","name":"累计回报 (%)",
         "x":[p['params'] for p in pr],
         "y":[round(p['cum_ret']*100,2) for p in pr],
         "marker":{"color":"#1a3b6b"},"yaxis":"y"},
        {"type":"scatter","mode":"lines+markers","name":"夏普比率",
         "x":[p['params'] for p in pr],"y":[p['sharpe'] for p in pr],
         "line":{"color":"#e74c3c","width":2},"marker":{"size":8},"yaxis":"y2"},
        {"type":"bar","name":"最大回撤 (%)",
         "x":[p['params'] for p in pr],
         "y":[round(p['mdd']*100,2) for p in pr],
         "marker":{"color":"#9b59b6"},"yaxis":"y"},
    ],
    "layout":{
        "barmode":"group",
        "xaxis":{"title":"均线组合周期"},
        "yaxis":{"title":"回报 / 回撤 (%)"},
        "yaxis2":{"title":"夏普比率","overlaying":"y","side":"right"},
        "showlegend":True,
        "legend":{"orientation":"h","yanchor":"bottom","y":1.05,"xanchor":"right","x":1},
        "margin":{"l":50,"r":50,"t":30,"b":50},
        "plot_bgcolor":"white","paper_bgcolor":"white","height":400,
    }
}

def metric_cards(r):
    cards = []
    for k, v in r['metrics'].items():
        style = ''
        if k in ('累计回报','年化收益率','夏普比率') and r['numeric'].get('cum_ret', 0) < 0: style = 'neg'
        elif k in ('累计回报','年化收益率','夏普比率'): style = 'pos'
        if k in ('最大回撤',): style = 'neg'
        cards.append('                <div class="metric %s"><p class="label">%s</p><p class="value">%s</p></div>' % (style, k, v))
    return '\n'.join(cards)

# ===== Build HTML =====
parts = []
parts.append('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>')
parts.append('<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">')
parts.append('<title>TASK3 - 双均线策略分析报告</title>')
parts.append('<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>')
# CSS
CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Microsoft YaHei',sans-serif;background:#f0f2f5;color:#333;line-height:1.6}
.nav{background:#1a3b6b;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,0.15)}
.nav-inner{max-width:1200px;margin:0 auto;display:flex;align-items:center;gap:4px;padding:0 10px;overflow-x:auto}
.nav a{color:rgba(255,255,255,0.8);text-decoration:none;padding:12px 13px;font-size:13px;white-space:nowrap;display:block}
.nav a:hover,.nav a.active{color:#fff;background:rgba(255,255,255,0.12);border-radius:4px 4px 0 0}
.container{max-width:1200px;margin:0 auto;padding:20px}
h1{color:#1a3b6b;text-align:center;margin:20px 0 5px;font-size:22px}
.subtitle{text-align:center;color:#888;font-size:12px;margin-bottom:18px}
.page{display:none;animation:fIn 0.3s}
.page.active{display:block}
@keyframes fIn{from{opacity:0}to{opacity:1}}
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(165px,1fr));gap:8px;margin:12px 0}
.metric{background:#fff;padding:10px;border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,0.06);text-align:center;border-left:3px solid #1a3b6b}
.metric .label{font-size:10px;color:#999;margin:0}
.metric .value{font-size:16px;font-weight:bold;color:#1a3b6b;margin:2px 0 0}
.metric.neg{border-left-color:#e74c3c}
.metric.neg .value{color:#e74c3c}
.metric.pos{border-left-color:#27ae60}
.metric.pos .value{color:#27ae60}
.panel{background:#fff;border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,0.06);margin:12px 0;overflow:hidden}
.panel-h{background:#1a3b6b;color:#fff;padding:9px 16px;font-size:14px;font-weight:bold}
.panel-b{padding:16px}
.xgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}
.xcard{background:#f8f9fa;border-radius:8px;padding:12px;border-left:4px solid #3498db}
.xcard h3{margin:0 0 5px;font-size:13px;color:#1a3b6b}
.xcard p{margin:0;font-size:12px;line-height:1.6;color:#555}
.xcard code{background:#e8e8e8;padding:1px 4px;border-radius:3px;font-size:11px}
.twrap{overflow-x:auto}
.t{width:100%;border-collapse:collapse;font-size:12px}
.t th{background:#1a3b6b;color:#fff;padding:7px 5px}
.t td{padding:5px;text-align:right;border-bottom:1px solid #eee}
.t tr:nth-child(even){background:#fafafa}
.buy{color:#cc0000}.sell{color:#00aa44}
.cmp{width:100%;border-collapse:collapse;font-size:13px}
.cmp th{background:#1a3b6b;color:#fff;padding:9px}
.cmp td{padding:7px;border-bottom:1px solid #eee;text-align:center}
.cmp tr:nth-child(even){background:#f8f9fa}
.cmp .best{color:#27ae60;font-weight:bold}
.cmp .worst{color:#e74c3c;font-weight:bold}
.fee-box{background:#fff8e1;border-radius:8px;padding:12px;border-left:4px solid #ff9800}
.fee-box h3{color:#e65100;font-size:13px;margin:0 0 6px}
.fee-box p{margin:2px 0;font-size:11px;color:#555}
.footer{text-align:center;color:#aaa;font-size:10px;margin-top:20px;padding:16px 0}
</style>"""
parts.append(CSS)
parts.append('</head><body>')

# Nav
parts.append('<div class="nav"><div class="nav-inner">')
parts.append('<a href="#" class="active" onclick="showP(\'p1\',this);return false">\U0001f4ca \u6982\u8ff0</a>')
parts.append('<a href="#" onclick="showP(\'p2\',this);return false">\U0001f534 002281 光迅</a>')
parts.append('<a href="#" onclick="showP(\'p3\',this);return false">\U0001f7e2 600519 茅台</a>')
parts.append('<a href="#" onclick="showP(\'p4\',this);return false">\u2696\ufe0f \u5bf9\u6bd4</a>')
parts.append('<a href="#" onclick="showP(\'p5\',this);return false">\U0001f4da \u6982\u5ff5</a>')
parts.append('</div></div>')
parts.append('<div class="container">')

# P1
parts.append('<div id="p1" class="page active">')
parts.append("<h1>TASK3: \u53cc\u5747\u7ebf\u7b56\u7565\u5206\u6790\u62a5\u544a</h1>")
parts.append('<p class="subtitle">\u7528\u5747\u7ebf\u4ea4\u53c9\u53cd\u5e94\u5e02\u573a\u8d8b\u52bf\u548c\u6ce2\u52a8 | MA%d/MA%d | 2025-07-03 \u81f3 2026-07-08</p>' % (sw, lw))
parts.append('</div>')

# P2
parts.append('<div id="p2" class="page">')
parts.append('<h1>002281 光迅科技</h1>')
parts.append('<p class="subtitle">MA%d/MA%d | %s | %d \u4e2a\u4ea4\u6613\u65e5</p>' % (sw, lw, r_a['date_range'], r_a['n_days']))
parts.append('<div class="metrics">\n%s\n</div>' % metric_cards(r_a))
parts.append('<div class="fee-box"><h3>\U0001f4b0 \u4ea4\u6613\u8d39\u7387</h3>')
parts.append('<p>\u4f63\u91d1: \u4e07\u5206\u4e4b2.5\uff0c\u4e70\u5356\u53cc\u5411\uff0c\u6700\u4f4e Y5/\u7b14 | \u5370\u82b1\u7a0e: \u4e07\u5206\u4e4b5\uff0c\u4ec5\u5356\u51fa</p>' % r_a['numeric']['total_comm'])
parts.append('</div>')
parts.append('<div class="panel"><div class="panel-h">\U0001f4ca K\u7ebf\u56fe + \u5747\u7ebf + \u4ea4\u6613\u4fe1\u53f7</div>')
parts.append('<div class="panel-b"><div id="ca1" style="height:650px"></div></div></div>')
parts.append('<span id="ca1_data" style="display:none">%s</span>' % json.dumps(c1a, ensure_ascii=False))
parts.append('<div class="panel"><div class="panel-h">\U0001f4c8 \u7b56\u7565\u51c0\u503c + \u56de\u64a4</div>')
parts.append('<div class="panel-b"><div id="ca2" style="height:500px"></div></div></div>')
parts.append('<span id="ca2_data" style="display:none">%s</span>' % json.dumps(c2a, ensure_ascii=False))
parts.append('<div class="panel"><div class="panel-h">\U0001f4cb \u4ea4\u6613\u660e\u7ec6 (%d\u7b14)</div>' % r_a['n_trades'])
parts.append('<div class="panel-b twrap"><table class="t"><thead><tr><th>\u65e5\u671f</th><th>\u65b9\u5411</th><th>\u4ef7\u683c</th><th>\u80a1\u6570</th><th>\u91d1\u989d</th><th>\u4f63\u91d1</th><th>\u5370\u82b1\u7a0e</th><th>\u603b\u8d39\u7528</th></tr></thead><tbody>')
parts.append(trades_html(r_a))
parts.append('</tbody></table></div></div></div>')

# P3
parts.append('<div id="p3" class="page">')
parts.append('<h1>600519 贵州茅台</h1>')
parts.append('<p class="subtitle">MA%d/MA%d | %s | %d \u4e2a\u4ea4\u6613\u65e5</p>' % (sw, lw, r_b['date_range'], r_b['n_days']))
parts.append('<div class="metrics">\n%s\n</div>' % metric_cards(r_b))
parts.append('<div class="fee-box"><h3>\U0001f4b0 \u4ea4\u6613\u8d39\u7387</h3>')
parts.append('<p>\u4f63\u91d1: \u4e07\u5206\u4e4b2.5 | \u5370\u82b1\u7a0e: \u4e07\u5206\u4e4b5\uff0c\u4ec5\u5356\u51fa</p>')
parts.append('</div>')
parts.append('<div class="panel"><div class="panel-h">\U0001f4ca K\u7ebf\u56fe + \u5747\u7ebf + \u4ea4\u6613\u4fe1\u53f7</div>')
parts.append('<div class="panel-b"><div id="cb1" style="height:650px"></div></div></div>')
parts.append('<span id="cb1_data" style="display:none">%s</span>' % json.dumps(c1b, ensure_ascii=False))
parts.append('<div class="panel"><div class="panel-h">\U0001f4c8 \u7b56\u7565\u51c0\u503c + \u56de\u64a4</div>')
parts.append('<div class="panel-b"><div id="cb2" style="height:500px"></div></div></div>')
parts.append('<span id="cb2_data" style="display:none">%s</span>' % json.dumps(c2b, ensure_ascii=False))
parts.append('<div class="panel"><div class="panel-h">\U0001f4cb \u4ea4\n6613\u660e\u7ec6 (%d\u7b14)</div>' % r_b['n_trades'])
parts.append('<div class="panel-b twrap"><table class="t"><thead><tr><th>\u65e5\u671f</th><th>\u65b9\u5411</th><th>\u4ef7\u683c</th><th>\u80a1\u6570</th><th>\u91d1\u989d</th><th>\u4f63\u91d1</th><th>\u5370\u82b1\u7a0e</th><th>\u603b\u8d39\u7528</th></tr></thead><tbody>')
parts.append(trades_html(r_b))
parts.append('</tbody></table></div></div></div>')

# P4
parts.append('<div id="p4" class="page">')
parts.append('<h1>\u7b56\u7565\u5bf9\u6bd4\u4e0e\u53c2\u6570\u5206\u6790</h1>')
parts.append('</div>')

# P5
parts.append('<div id="p5" class="page">')
parts.append('<h1>\U0001f4da \u7b56\u7565\u4e0e\u6307\u6807\u6982\u5ff5\u8bf4\u660e</h1>')
parts.append('</div>')

parts.append('</div><!--container-->')
parts.append('<div class="footer">')
parts.append('<p>TASK3 \u7b56\u7565\u9996\u79c0\u7528\u5747\u7ebf\u4ea4\u53c9\u53cd\u5e94\u5e02\u573a\u8d8b\u52bf\u548c\u6ce2\u52a8 | ' + pd.Timestamp.now().strftime('%Y-%m-%d %H:%M') + '</p>')
parts.append('</div>')

# JS - read data from hidden spans and render
JS = """
<script>
function showP(id,el){
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.nav a').forEach(a=>a.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    if(el)el.classList.add('active');
}
function render(id,spanId,layout){
    var d=document.getElementById(spanId);
    if(!d)return;
    var c=JSON.parse(d.textContent);
    Plotly.newPlot(id,c.data,c.layout,{responsive:true,displayModeBar:true});
}
render('ca1','ca1_data');
render('ca2','ca2_data');
render('cb1','cb1_data');
render('cb2','cb2_data');
</script>
"""
parts.append(JS)
parts.append('</body></html>')

html = '\n'.join(parts)

with open('/Users/skyler/workspace/stock_selection/ai_quant/Task3_002281_dual_ma.html','w',encoding='utf-8') as f:
    f.write(html)

print('Written: %d bytes' % len(html))
sc=len(re.findall(r'<script\b',html))
cc=html.count('</script>')
print('<script>:%d </script>:%d' % (sc,cc))
for check in ['002281','600519','金叉','死叉','夏普比率','最大回撤','累计回报','p1','p2','p3','p4','p5','Plotly.newPlot']:
    assert check in html, 'Missing: %s' % check
print('All OK!')
