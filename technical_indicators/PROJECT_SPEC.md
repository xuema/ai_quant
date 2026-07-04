# Project Spec — 光迅科技(002281.SZ) 技术分析系统

## 1. Project Overview

A self-contained quantitative analysis project for 光迅科技. The system loads one year of daily OHLCV data, runs data quality diagnostics, implements six core technical indicators (RSI, MACD, Bollinger Bands, Williams %R, ATR, CR / 能量指标) with full formula documentation, and walks through every calculation step in a single comprehensive Jupyter notebook.

---

## 2. Codebase Layout

```
technical_analysis_project/
│
├── Project_Spec.md          # ← this document
├── README.md                # Quick start & repo overview
├── requirements.txt         # Python deps
├── .gitignore               # Ignore cache/data artifacts
│
├── data/
│   └── 002281_daily.csv     # Raw CSV, 243 trading days (2025-07-03 ~ 2026-07-03)
│
├── notebooks/
│   └── 002281_technical_analysis.ipynb
│       # THE notebook. Contains:
│       #   Cell  1-2 : Setup & imports
│       #   Cell  3-7 : Data loading & diagnostics
│       #   Cell  8-10: RSI   (explain → formula → step-by-step → plot)
│       #   Cell 11-13: MACD  (explain → formula → step-by-step → plot)
│       #   Cell 14-16: Bollinger Bands
│       #   Cell 17-19: Williams %R
│       #   Cell 20-22: ATR
│       #   Cell 23-25: CR (Energy Index)
│       #   Cell 26-28: Dashboard & cross-indicator summary
│
└── src/
    ├── __init__.py
    └── indicators.py          # Reusable indicator functions (no pandas dep)
```

---

## 3. Notebook Cell Design

The notebook follows a **three-phase structure** for each indicator:

| Phase | Cell Type | Content |
|-------|-----------|---------|
| **Theory** | Markdown | Indicator name, origin, intuition, mathematical formula, standard parameters, interpretation rules |
| **Implementation** | Code | Python function with full formula implementation, vectorized |
| **Demonstration** | Code | Step-by-step calculation shown for the first 30 rows: intermediate variables printed as DataFrame, then a chart over the full dataset |

---

## 4. Technical Indicators — Formula Reference

### 4.1 RSI — Relative Strength Index (Wilder, 1978)

```
Δ = Close[t] - Close[t-1]
Gain = max(Δ, 0)        Loss = -min(Δ, 0)
AvgGain = EMA(Gain, N)  AvgLoss = EMA(Loss, N)     N=14
RS = AvgGain / AvgLoss
RSI = 100 - 100/(1 + RS)

Interpretation:
  RSI > 70 → 超买 (overbought)
  RSI < 30 → 超卖 (oversold)
  RSI = 50 → 多空均衡
```

### 4.2 MACD — Moving Average Convergence Divergence (Appel, 1979)

```
EMA_fast = EMA(Close, 12)
EMA_slow = EMA(Close, 26)
DIF  = EMA_fast - EMA_slow
DEA  = EMA(DIF, 9)
MACD = 2 × (DIF - DEA)        ← Chinese convention doubles histogram

Interpretation:
  DIF > DEA (金叉)  → 看多信号
  DIF < DEA (死叉)  → 看空信号
  MACD > 0 → 多头动能
  DIF/DEA 位于零轴上方 → 中长期偏多
```

### 4.3 BOLL — Bollinger Bands (Bollinger, 1983)

```
MID  = SMA(Close, N)              N=20
STD  = StdDev(Close, N)
UP   = MID + k*STD                k=2
LOW  = MID - k*STD

Interpretation:
  价格触及上轨 → 短期强势但超买
  价格触及下轨 → 短期弱势但超卖
  带宽 (UP-LOW)/MID ↓ → 波动率收缩 → 即将变盘
  价格在中轨上方运行 → 偏多, 下方 → 偏空
```

### 4.4 WR — Williams %R (Williams, 1973)

```
H_N = Highest(High, N)           N=14
L_N = Lowest(Low,  N)
WR = (H_N - Close) / (H_N - L_N) × (-100)

Interpretation:
  WR ∈ [-100, 0]
  WR > -20 → 超买
  WR < -80 → 超卖
  与 RSI 镜像 (WR = RSI - 100 的近似)
```

### 4.5 ATR — Average True Range (Wilder, 1978)

```
TR = max(
    High - Low,
    |High - Close_prev|,
    |Low  - Close_prev|
)
ATR = SMA(TR, N)        N=14

Interpretation:
  ATR 越大 → 日波动越大 → 仓位应该越小
  常用止损距离: 1.5~2 × ATR
  ATR 飙升 → 行情加速 (趋势中/恐慌中)
  ATR 持续走低 → 行情收敛 → 即将选择方向
```

### 4.6 CR — Energy Index / 能量指标

```
PM[t-1] = (High[t-1] + Low[t-1] + Close[t-1]) / 3          中间价

BullPower = max(High[t] - PM[t-1], 0)
BearPower = max(PM[t-1] - Low[t], 0)

CR = 100 × Σ BulPower / Σ BearPower       (滚动N日, N=26)

Interpretation:
  CR > 100 → 多方占优
  CR < 100 → 空方占优
  CR > 200/300 → 超强, 注意回调
  CR < 40 → 超卖, 关注反弹
  常见参考线: 40, 60, 160, 200
  MA_CR(5/10/20/60) 四线系统: 多头排列看多, 空头排列看空
```

---

## 5. Data Diagnostic Protocol

The notebook runs the following diagnostics before any indicator:

1. `df.shape` — row & column count
2. `df.dtypes` — type check (prices must be float; dates must be datetime)
3. `df.isnull().sum()` — missing value matrix
4. `df.describe()` — mean/std/min/max/quartiles
5. Distribution plots for price, volume, return
6. Duplicate row check (`df.duplicated().sum()`)
7. Date gap analysis (detect missing sessions)

---

## 6. Quality Gate

Before pushing to GitHub, verify:
- [ ] Notebook runs top-to-bottom with no error
- [ ] All six indicator outputs match TradingView reference values (tolerance ±0.5%)
- [ ] `src/indicators.py` functions are pure: no side effects, pandas not required
- [ ] No hardcoded paths; use `pathlib.Path(__file__).parent`
- [ ] `.gitignore` covers: `__pycache__/`, `*.pyc`, `.ipynb_checkpoints/`, `.env`
- [ ] README documents setup, run, expected output

---

## 7. Development Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1. Spec & layout | This document + directory structure | **DONE** |
| 2. Data download | akshare CSV in `data/` | **DONE** |
| 3. Indicator library | `src/indicators.py` | **DONE** |
| 4. Notebook | `notebooks/` with step-by-step cells | Building now |
| 5. Verification | Compare against reference values | Pending |
| 6. GitHub push | Clean initial commit | Pending |

---

## 8. Future Extensions

- Add KDJ / Stochastic oscillator
- Add Volume Profile & OBV
- Strategy backtest: RSI+MACD combo, dual-MA crossover
- Live data pipeline: scheduled cron → akshare → auto-rebuild notebook
- PDF export pipeline (weasyprint → weekly report)
