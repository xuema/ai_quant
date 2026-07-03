#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
光迅科技(002281) 技术面分析 & 网页面板生成 (akshare 版本)
"""

import akshare as ak
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import os
import json
import warnings
warnings.filterwarnings('ignore')

# ─── 设置 ────────────────────────────────────────────────────────────────────
TS_CODE = "002281"  # 光迅科技
TODAY = datetime.now().strftime("%Y%m%d")
ONE_YEAR_AGO = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
OUTPUT_DIR = "/Users/skyler/workspace/stock_selection/announcement_alpha/data/stock_analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── 下载数据 ─────────────────────────────────────────────────────────────────
print(f"Downloading {TS_CODE} daily data: {ONE_YEAR_AGO} -> {TODAY}")
df = ak.stock_zh_a_hist(symbol=TS_CODE, period="daily",
                        start_date=ONE_YEAR_AGO, end_date=TODAY, adjust="qfq")

if df.empty:
    raise RuntimeError("No data returned")

df = df.sort_values("日期").reset_index(drop=True)
df = df.rename(columns={
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "vol",
    "成交额": "amount",
    "振幅": "amp",
    "涨跌幅": "pct_chg",
    "涨跌额": "change",
    "换手率": "turnover_rate",
})

df["trade_date"] = pd.to_datetime(df["trade_date"])
csv_path = os.path.join(OUTPUT_DIR, f"002281_{ONE_YEAR_AGO}_{TODAY}.csv")
df.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"Saved {len(df)} rows to {csv_path}")
print(f"Date range: {df['trade_date'].min().date()} -> {df['trade_date'].max().date()}")

# ─── 技术指标计算 ──────────────────────────────────────────────────────────────
df["MA5"]  = df["close"].rolling(5).mean()
df["MA10"] = df["close"].rolling(10).mean()
df["MA20"] = df["close"].rolling(20).mean()
df["MA60"] = df["close"].rolling(60).mean()

# MACD
def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()

ema12 = calc_ema(df["close"], 12)
ema26 = calc_ema(df["close"], 26)
df["DIF"] = ema12 - ema26
df["DEA"] = calc_ema(df["DIF"], 9)
df["MACD"] = (df["DIF"] - df["DEA"]) * 2

# RSI
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

df["RSI6"]  = calc_rsi(df["close"], 6)
df["RSI14"] = calc_rsi(df["close"], 14)

# Bollinger Bands
df["BOLL_MID"] = df["close"].rolling(20).mean()
df["BOLL_STD"] = df["close"].rolling(20).std()
df["BOLL_UP"]  = df["BOLL_MID"] + 2 * df["BOLL_STD"]
df["BOLL_DN"]  = df["BOLL_MID"] - 2 * df["BOLL_STD"]

# Volume MA
df["VOL_MA5"]  = df["vol"].rolling(5).mean()
df["VOL_MA20"] = df["vol"].rolling(20).mean()

print(f"\nLatest close: {df['close'].iloc[-1]:.2f}")
print(f"Year high:    {df['high'].max():.2f}  Year low: {df['low'].min():.2f}")
print(f"Mean vol:     {df['vol'].mean()/1e4:.0f} 万手")

# ─── 静态图表 ───────────────────────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

fig, axes = plt.subplots(4, 1, figsize=(14, 15),
                          gridspec_kw={"height_ratios": [5, 1.5, 1.2, 1.2]},
                          sharex=True)
fig.suptitle(f"光迅科技(002281) 技术分析 — {df['trade_date'].iloc[0].date()} → {df['trade_date'].iloc[-1].date()}",
             fontsize=15, fontweight="bold")

# Price + Bollinger + MA
ax = axes[0]
ax.plot(df["trade_date"], df["close"], color="#222", linewidth=1.2, label="Close")
ax.plot(df["trade_date"], df["MA5"],  color="#1f77b4", linewidth=0.9, label="MA5")
ax.plot(df["trade_date"], df["MA10"], color="#ff7f0e", linewidth=0.9, label="MA10")
ax.plot(df["trade_date"], df["MA20"], color="#2ca02c", linewidth=0.9, label="MA20")
ax.plot(df["trade_date"], df["MA60"], color="#d62728", linewidth=0.9, label="MA60")
ax.fill_between(df["trade_date"], df["BOLL_UP"], df["BOLL_DN"], alpha=0.12, color="skyblue", label="Bollinger")
ax.plot(df["trade_date"], df["BOLL_UP"], color="steelblue", linewidth=0.7, linestyle="--")
ax.plot(df["trade_date"], df["BOLL_DN"], color="steelblue", linewidth=0.7, linestyle="--")
hi_idx = df["high"].idxmax(); lo_idx = df["low"].idxmin()
ax.annotate(f"H {df.loc[hi_idx,'high']:.2f}", xy=(df.loc[hi_idx,"trade_date"], df.loc[hi_idx,"high"]),
            xytext=(0,10), textcoords="offset points", color="red", fontsize=9, ha="center")
ax.annotate(f"L {df.loc[lo_idx,'low']:.2f}", xy=(df.loc[lo_idx,"trade_date"], df.loc[lo_idx,"low"]),
            xytext=(0,-14), textcoords="offset points", color="green", fontsize=9, ha="center")
ax.set_ylabel("Price (CNY)"); ax.grid(alpha=0.3); ax.legend(loc="upper left", fontsize=8)

# Volume
ax = axes[1]
colors = ["#d32f2f" if c >= o else "#388e3c" for c, o in zip(df["close"], df["open"])]
ax.bar(df["trade_date"], df["vol"]/1e4, color=colors, width=0.8, alpha=0.85)
ax.plot(df["trade_date"], df["VOL_MA5"]/1e4, color="orange", linewidth=0.8)
ax.plot(df["trade_date"], df["VOL_MA20"]/1e4, color="blue", linewidth=0.8)
ax.set_ylabel("Vol (万手)"); ax.grid(alpha=0.3)

# MACD
ax = axes[2]
macd_colors = ["#d32f2f" if v >= 0 else "#388e3c" for v in df["MACD"]]
ax.bar(df["trade_date"], df["MACD"], color=macd_colors, width=0.8, alpha=0.85)
ax.plot(df["trade_date"], df["DIF"], color="blue", linewidth=0.9, label="DIF")
ax.plot(df["trade_date"], df["DEA"], color="orange", linewidth=0.9, label="DEA")
ax.axhline(0, color="grey", linewidth=0.5)
ax.set_ylabel("MACD"); ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=0.3)

# RSI
ax = axes[3]
ax.plot(df["trade_date"], df["RSI6"],  color="#1f77b4", linewidth=0.9, label="RSI6")
ax.plot(df["trade_date"], df["RSI14"], color="#ff7f0e", linewidth=0.9, label="RSI14")
ax.axhline(70, color="red", linestyle="--", linewidth=0.6, alpha=0.7)
ax.axhline(30, color="green", linestyle="--", linewidth=0.6, alpha=0.7)
ax.fill_between(df["trade_date"], 30, df["RSI14"], where=df["RSI14"]<=30, color="green", alpha=0.2)
ax.fill_between(df["trade_date"], 70, df["RSI14"], where=df["RSI14"]>=70, color="red", alpha=0.2)
ax.set_ylim(10, 90); ax.set_ylabel("RSI"); ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=0.3)

axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
plt.xticks(rotation=30)
plt.tight_layout(rect=[0, 0, 1, 0.97])
png_path = os.path.join(OUTPUT_DIR, f"002281_tech_analysis_{TODAY}.png")
plt.savefig(png_path, dpi=140, bbox_inches="tight")
plt.close()
print(f"\nChart saved: {png_path}")

# ─── 生成 JSON ──────────────────────────────────────────────────────────────
df_clean = df.fillna(value=np.nan).replace({np.nan: None})
records = []
for _, r in df_clean.iterrows():
    records.append({
        "date": r["trade_date"].strftime("%Y-%m-%d"),
        "open":  round(r["open"],  2),
        "high":  round(r["high"],  2),
        "low":   round(r["low"],   2),
        "close": round(r["close"], 2),
        "vol":   r["vol"],
        "ma5":   round(r["MA5"],  2) if r["MA5"]  is not None else None,
        "ma10":  round(r["MA10"], 2) if r["MA10"] is not None else None,
        "ma20":  round(r["MA20"], 2) if r["MA20"] is not None else None,
        "ma60":  round(r["MA60"], 2) if r["MA60"] is not None else None,
        "dif":   round(r["DIF"],  4) if r["DIF"]  is not None else None,
        "dea":   round(r["DEA"],  4) if r["DEA"]  is not None else None,
        "macd":  round(r["MACD"], 4) if r["MACD"] is not None else None,
        "rsi6":  round(r["RSI6"], 2) if r["RSI6"] is not None else None,
        "rsi14": round(r["RSI14"],2) if r["RSI14"] is not None else None,
        "boll_up": round(r["BOLL_UP"], 2) if r["BOLL_UP"] is not None else None,
        "boll_mid": round(r["BOLL_MID"],2) if r["BOLL_MID"] is not None else None,
        "boll_dn":  round(r["BOLL_DN"],  2) if r["BOLL_DN"] is not None else None,
        "vol_ma5":  round(r["VOL_MA5"]/1e4, 2)  if r["VOL_MA5"] is not None else None,
        "vol_ma20": round(r["VOL_MA20"]/1e4, 2) if r["VOL_MA20"] is not None else None,
        "amp":   round(r.get("amp", 0), 2),
        "pct_chg": round(r.get("pct_chg", 0), 2),
        "turnover_rate": round(r.get("turnover_rate", 0), 2),
    })

latest = records[-1]
summary = {
    "latest_date": latest["date"],
    "latest_close": latest["close"],
    "latest_open": latest["open"],
    "latest_chg": latest["pct_chg"],
    "latest_vol_wan": round(latest["vol"]/1e4, 2),
    "latest_turnover": latest["turnover_rate"],
    "year_high": round(df["high"].max(), 2),
    "year_low":  round(df["low"].min(), 2),
    "year_avg_vol": round(df["vol"].mean()/1e4, 2),
    "ma5":  latest["ma5"],
    "ma20": latest["ma20"],
    "ma60": latest["ma60"],
    "rsi14": latest["rsi14"],
    "dif":  latest["dif"],
    "dea":  latest["dea"],
    "boll_up": latest["boll_up"],
    "boll_dn": latest["boll_dn"],
    "boll_mid": latest["boll_mid"] if latest["boll_mid"] else (latest["boll_up"]+latest["boll_dn"])/2 if latest["boll_up"] and latest["boll_dn"] else None,
}

signals = []
c = latest["close"]
if c and latest["ma5"] and latest["ma20"] and latest["ma60"]:
    if c > latest["ma5"] > latest["ma20"] > latest["ma60"]:
        signals.append(("趋势", "多头排列 ⬆️（价格 > MA5 > MA20 > MA60）", "bullish"))
    elif c < latest["ma5"] < latest["ma20"] < latest["ma60"]:
        signals.append(("趋势", "空头排列 ⬇️（价格 < MA5 < MA20 < MA60）", "bearish"))
    else:
        signals.append(("趋势", "均线纠缠，方向不明", "neutral"))

if latest["dif"] is not None and latest["dea"] is not None:
    if latest["dif"] > latest["dea"] and latest["dif"] > 0:
        signals.append(("MACD", "DIF/DEA均>0且DIF>DEA，强势上升", "bullish"))
    elif latest["dif"] > latest["dea"]:
        signals.append(("MACD", "金叉形成，短期看多", "bullish"))
    elif latest["dif"] < latest["dea"] and latest["dif"] < 0:
        signals.append(("MACD", "DIF/DEA均<0且DIF<DEA，弱势下跌", "bearish"))
    else:
        signals.append(("MACD", "死叉形成，短期看空", "bearish"))

if latest["rsi14"] is not None:
    if latest["rsi14"] > 70:
        signals.append(("RSI14", f"{latest['rsi14']:.1f} 超买区间，注意回调风险", "bearish"))
    elif latest["rsi14"] < 30:
        signals.append(("RSI14", f"{latest['rsi14']:.1f} 超卖区间，关注反弹机会", "bullish"))
    elif latest["rsi14"] >= 55:
        signals.append(("RSI14", f"{latest['rsi14']:.1f} 偏强", "bullish"))
    elif latest["rsi14"] <= 45:
        signals.append(("RSI14", f"{latest['rsi14']:.1f} 偏弱", "bearish"))
    else:
        signals.append(("RSI14", f"{latest['rsi14']:.1f} 中性区间", "neutral"))

if (latest["boll_up"] is not None and latest["boll_dn"] is not None):
    if c >= latest["boll_up"]:
        signals.append(("布林", f"价格触及/超越上轨，短期强势但回调压力增大", "bearish"))
    elif c <= latest["boll_dn"]:
        signals.append(("布林", f"价格触及/跌破下轨，短期弱势但反弹潜力增大", "bullish"))
    elif latest["boll_mid"] is not None and c > latest["boll_mid"]:
        signals.append(("布林", "价格站上中轨，偏强势运行", "bullish"))
    else:
        signals.append(("布林", "价格位于中轨之下，偏弱整理", "bearish"))

summary["signals"] = [{"category": s[0], "description": s[1], "tone": s[2]} for s in signals]

json_payload = {"records": records, "summary": summary}
json_path = os.path.join(OUTPUT_DIR, "data.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(json_payload, f, ensure_ascii=False)
print(f"JSON data saved: {json_path} ({len(records)} records)")

with open(os.path.join(OUTPUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("\n✓ Data pipeline complete. Running dashboard generator next...")
