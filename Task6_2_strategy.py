#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task6_2: 002281 ML概率选股策略 — 特征工程复现Task5完整技术指标体系
"""
import pandas as pd
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path
import pickle, json, warnings
warnings.filterwarnings('ignore')

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix)
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier

# ── Config ──
DATA = "/Users/skyler/workspace/stock_selection/ai_quant/data/stock_analysis/002281_202307_202607.csv"
OUT_DIR = Path("/Users/skyler/workspace/stock_selection/ai_quant/data/results/task6_2")
MODEL_DIR = Path("/Users/skyler/workspace/stock_selection/ai_quant/models")
OUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
INIT_CAP = 100_000
FEE = 0.001  # 单边

# ══════════════ 1. LOAD ══════════════
df = pd.read_csv(DATA)
df['trade_date'] = pd.to_datetime(df['trade_date'])
df = df.sort_values('trade_date').reset_index(drop=True)
print(f"数据: {len(df)}行, {df['trade_date'].min().date()} → {df['trade_date'].max().date()}")

# ══════════════ 2. FEATURE ENG (Task5指标) ══════════════
# Label next
df['ret'] = df['pct_chg'] / 100.0
df['next_ret'] = df['ret'].shift(-1)
df['label_up'] = (df['next_ret'] > 0).astype(int)

# MA difference
for n in [5, 10, 20]:
    ma = df['close'].rolling(n).mean()
    df[f'ma_diff_{n}'] = (df['close'] - ma) / ma

# Volatility
for n in [5, 10]:
    df[f'volatility_{n}'] = df['close'].rolling(n).std() / df['close']

# Volume ratio
df['vol_ratio'] = df['vol'] / df['vol'].rolling(20).mean()

# RSI 12 / 56
def rsi(s, p):
    d = s.diff(); g = d.where(d>0,0).rolling(p).mean(); l = (-d.where(d<0,0)).rolling(p).mean()
    return 100 - 100/(1 + g/(l+1e-10))
df['rsi_12'] = rsi(df['close'], 12)
df['rsi_56'] = rsi(df['close'], 56)

# EXPMA + diff
df['expma_5']  = df['close'].ewm(span=5).mean()
df['expma_29'] = df['close'].ewm(span=29).mean()
df['expma_diff_5']  = (df['close'] - df['expma_5'])  / df['expma_5']
df['expma_diff_29'] = (df['close'] - df['expma_29']) / df['expma_29']

# WR (Williams %R, 42)
hh = df['high'].rolling(42).max()
ll = df['low'].rolling(42).min()
df['wr_42'] = (hh - df['close']) / (hh - ll + 1e-10) * (-100)

# CR
pm = (df['high'].shift(1) + df['low'].shift(1) + df['close'].shift(1)) / 3
df['cr'] = ((df['high']-pm).clip(lower=0).rolling(26).sum() /
            ((pm-df['low']).clip(lower=0).rolling(26).sum() + 1e-10) * 100)
for n in [11, 19, 35, 53]:
    df[f'cr_ma_{n}'] = df['cr'].rolling(n).mean()

# vol_ratio_8_89
df['vol_ratio_8_89'] = (df['vol'].rolling(8).mean() /
                        (df['vol'].rolling(89).mean() + 1e-10))

# Feature list: 原始 + 衍生(19个)
FEATS_RAW = ['open','high','low','vol','amount','pct_chg','change','amp','turnover_rate','ret']
FEATS_DERIVED = ([f'ma_diff_{n}' for n in [5,10,20]] +
                 [f'volatility_{n}' for n in [5,10]] +
                 ['vol_ratio','rsi_12','rsi_56',
                  'expma_5','expma_29','expma_diff_5','expma_diff_29',
                  'wr_42','cr','cr_ma_11','cr_ma_19','cr_ma_35','cr_ma_53',
                  'vol_ratio_8_89'])
ALL = FEATS_RAW + FEATS_DERIVED
print(f"特征: {len(ALL)} (原始{len(FEATS_RAW)} + 衍生{len(FEATS_DERIVED)})")

# Drop NaN
df = df.dropna(subset=ALL + ['label_up']).reset_index(drop=True)
print(f"清洗后: {len(df)}样本 | 上涨/下跌 = {df['label_up'].value_counts().to_dict()}")

# ══════════════ 3. SPLIT ══════════════
n = len(df)
split = int(n * 0.8)
X = df[ALL].values
y = df['label_up'].values
Xtr, Xte = X[:split], X[split:]
ytr, yte = y[:split], y[split:]
print(f"训练 {len(Xtr)} | 测试 {len(Xte)}")

sc = StandardScaler()
Xtr_s = sc.fit_transform(Xtr)
Xte_s = sc.transform(Xte)

# ══════════════ 4. MODELS ══════════════
cands = {
    'LogisticRegression': LogisticRegression(max_iter=1000, C=0.5, random_state=42),
    'RandomForest':       RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42, n_jobs=-1),
    'GradientBoosting':   GradientBoostingClassifier(n_estimators=100, learning_rate=0.05, max_depth=3, random_state=42),
    'KNN':                KNeighborsClassifier(n_neighbors=5, weights='distance'),
}

res = {}; best_n, best_m, best_a, best_p = None, None, 0, None
for nm, m in cands.items():
    m.fit(Xtr_s, ytr)
    pp = m.predict_proba(Xte_s)[:,1]
    yp = m.predict(Xte_s)
    auc = roc_auc_score(yte, pp)
    res[nm] = dict(auc=auc, acc=accuracy_score(yte,yp),
                   prec=precision_score(yte,yp,zero_division=0),
                   rec=recall_score(yte,yp,zero_division=0),
                   f1=f1_score(yte,yp,zero_division=0),
                   cm=confusion_matrix(yte,yp).tolist(),
                   prob=pp)
    print(f"  {nm:20s} AUC={auc:.4f} ACC={res[nm]['acc']:.3f} 范围[{pp.min():.3f}–{pp.max():.3f}]")
    if auc > best_a:
        best_a, best_n, best_m, best_p = auc, nm, m, pp

print(f"★ 最优: {best_n} AUC={best_a:.4f}")

# ══════════════ 5. PROB ANALYSIS ══════════════
print(f"\n预测概率范围: [{best_p.min():.4f}, {best_p.max():.4f}] mean={best_p.mean():.4f}")
# If the range is too narrow, try threshold-based strategy with 0.5 as pivot
print(f">0.6: {(best_p>0.6).sum()}  |  0.5-0.6: {((best_p>0.5)&(best_p<=0.6)).sum()}  |  0.4-0.5: {((best_p>0.4)&(best_p<=0.5)).sum()}  |  <0.4: {(best_p<0.4).sum()}")

# Check if we should use a different threshold if prob max < 0.6
if best_p.max() < 0.6:
    print("⚠ 最高概率 < 0.6, 使用概率排序策略:")
    print("  - 按概率排序, top 30% → 满仓, next 30% → 半仓, bottom 40% → 空仓")
    use_rank = True
    ranks = np.argsort(np.argsort(best_p)) / len(best_p)
    position_map = np.where(ranks > 0.7, 1.0,
                   np.where(ranks > 0.4, 0.5, 0.0))
else:
    use_rank = False
    print("✅ 概率范围足够, 使用标准仓位公式")
    position_map = np.clip((best_p - 0.5) * 2, 0, 1)

# ══════════════ 6. BACKTEST ══════════════
test_idx = list(range(split, split + len(best_p)))
positions_full = np.zeros(len(df))
positions_full[split:] = position_map

# Build backtest
cap = INIT_CAP
strat_r, bench_r = [], []
dates_b = []
positions_b = []
for i in range(split, len(df) - 1):
    ret = df.iloc[i+1]['next_ret']  # 次日收益
    if np.isnan(ret): continue
    pos = positions_full[i]
    daily_ret = pos * ret * (1 - FEE * 2)
    cap *= (1 + daily_ret)
    strat_r.append(daily_ret)
    bench_r.append(ret)
    dates_b.append(df.iloc[i+1]['trade_date'])
    positions_b.append(pos)

N = len(strat_r)
tot_s = sum(strat_r)
tot_b = sum(bench_r)
ann_s = (1+tot_s)**(252/N) - 1 if N else 0
sharpe_s = np.mean(strat_r)/np.std(strat_r)*np.sqrt(252) if np.std(strat_r)>0 else 0
excess = tot_s - tot_b

cum = np.cumprod([1+r for r in strat_r])
rmax = np.maximum.accumulate(cum)
dd = (cum - rmax)/rmax
mdd_s = dd.min() if len(dd) else 0

wins = sum(1 for i in range(N) if positions_b[i]>0 and bench_r[i]>0)
trades = sum(1 for i in range(N) if positions_b[i]>0)
wr = wins/trades if trades else 0

print(f"\n{'='*48}\n📊 回测结果:")
print(f"  初始资金: ¥{INIT_CAP:,}  →  ¥{cap:,.2f}")
print(f"  策略收益: {tot_s:.2%}  年化: {ann_s:.2%}")
print(f"  基准收益: {tot_b:.2%}")
print(f"  超额收益: {excess:.2%}")
print(f"  夏普: {sharpe_s:.2f}  最大回撤: {mdd_s:.2%}")
print(f"  胜率: {wr:.2%} ({wins}/{trades})")
print(f"{'='*48}")

# ══════════════ 7. CHART ══════════════
fig, ax = plt.subplots(figsize=(12,5), facecolor='#0d1117')
ax.hist(best_p, bins=30, color='#3b82f6', alpha=0.8, edgecolor='#1e293b')
ax.axvline(0.4, color='#ef4444', ls='--', lw=2)
ax.axvline(0.5, color='#eab308', ls='--', lw=2)
ax.axvline(0.6, color='#22c55e', ls='--', lw=2)
ax.set_title(f'{best_n} — 测试集预测概率分布')
ax.set_xlabel('预测概率(上涨)')
ax.set_ylabel('样本数')
plt.tight_layout()
fp = OUT_DIR / 'prob_distribution.png'
plt.savefig(fp, dpi=150, facecolor='#0d1117')
plt.close()
print(f"📁 已保存: {fp}")

# ══════════════ 8. SAVE MODEL + RESULTS ══════════════
model_path = MODEL_DIR / 'task6_2_best_model.pkl'
with open(model_path, 'wb') as f:
    pickle.dump(dict(model=best_m, scaler=sc, features=ALL, name=best_n,
                     auc=best_a, threshold='rank_based' if use_rank else 'prob_based'), f)

rj = dict(model=best_n, test_period=[str(dates_b[0].date()), str(dates_b[-1].date())],
          trading_days=N, strategy_ret=tot_s, benchmark_ret=tot_b,
          excess=excess, annual=ann_s, sharpe=sharpe_s, max_dd=mdd_s,
          win_rate=wr, win_trades=wins, total_trades=trades,
          final_capital=round(cap,2), use_rank_strategy=use_rank,
          model_metrics={k:{kk:vv for kk,vv in v.items() if kk!='prob'} for k,v in res.items()})
with open(OUT_DIR / 'task6_2_results.json', 'w') as f:
    json.dump(rj, f, indent=2, ensure_ascii=False)

print(f"\n✅ 模型: {model_path}")
print(f"✅ 结果: {OUT_DIR / 'task6_2_results.json'}")
