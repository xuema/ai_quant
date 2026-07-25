# -*- coding: utf-8 -*-
"""
聚宽平台 - 超级顶底策略 V4 (Debug版)
"""
from jqdata import *
import numpy as np, pandas as pd

# === 参数 ===
g.BUY_TH        = 11
g.SELL_TH       = 89
g.MIN_MCAP      = 80
g.FIXED_POS     = 5
g.BAR_COUNT     = 80
g.VOL_WINDOW    = 10
g.VOL_MIN       = 1.2
g.PARAM_N       = 27
g.ATR_WINDOW    = 14
g.ATR_MULT      = 2.0
g.WR_WINDOW     = 42
g.WR_TH         = 45


def initialize(context):
    log.info('=== V4 初始化 ===')
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(
        OrderCost(close_tax=0.001, open_commission=0.0003,
                  close_commission=0.0003, min_commission=5),
        type='stock'
    )
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG')
    run_daily(market_open,        time='open',       reference_security='000300.XSHG')
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')
    g.stock_pool = []
    g.high_peak  = {}
    g.buy_costs  = {}
    g.day_count  = 0
    log.info('初始化完成，等待每日调度...')


def _sma_td(s, n, m):
    x = s.values.astype(np.float64)
    out = np.full(len(x), np.nan)
    a = m / n
    first = next((i for i, v in enumerate(x) if np.isfinite(v)), None)
    if first is None:
        return pd.Series(out, index=s.index)
    out[first] = x[first]
    for i in range(first + 1, len(x)):
        if np.isfinite(x[i]):
            p = out[i-1] if np.isfinite(out[i-1]) else x[i]
            out[i] = a * x[i] + (1 - a) * p
    return pd.Series(out, index=s.index)


def _trend(hi, lo, cl):
    n = g.PARAM_N
    den = (hi.rolling(n).max() - lo.rolling(n).min()).replace(0, np.nan)
    rsv = (cl - lo.rolling(n).min()) / den * 100
    s1 = _sma_td(rsv, 5, 1)
    s2 = _sma_td(s1, 3, 1)
    return 3 * s1 - 2 * s2


def _atr_val(df):
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift(1)).abs(),
        (df['low']  - df['close'].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(g.ATR_WINDOW).mean()


def _wr_val(df):
    w = g.WR_WINDOW
    hh = df['high'].rolling(w).max()
    ll = df['low'].rolling(w).min()
    den = (hh - ll).replace(0, np.nan)
    return (hh - df['close']) / den * 100


def _score(tv, vr):
    return round(max(0, 100 * (1 - (tv - g.BUY_TH) / 25)) + min(30, (vr - g.VOL_MIN) * 30), 1)


def before_market_open(context):
    g.day_count += 1
    dt = context.current_dt.date()
    log.info('=== Day %d: %s ===' % (g.day_count, dt))

    try:
        sec = get_all_securities(types=['stock'], date=dt)
        log.info('全A股: %d 只' % len(sec))
    except Exception as e:
        log.error('get_all_securities 异常: %s' % str(e))
        g.stock_pool = []
        return

    if sec is None or len(sec) == 0:
        log.error('全A股为空')
        g.stock_pool = []
        return

    try:
        mask = (~sec['display_name'].str.contains('ST')) & (~sec['name'].str.contains('ST'))
        codes = sec[mask].index.tolist()
        log.info('去ST后: %d 只' % len(codes))
    except Exception as e:
        log.error('去ST异常: %s' % str(e))
        codes = sec.index.tolist()

    try:
        q = query(valuation.code, valuation.market_cap).filter(
            valuation.code.in_(codes[:500]),  # 分批查询避免超时
            valuation.market_cap >= g.MIN_MCAP
        )
        df = get_fundamentals(q, date=dt)
        if df is not None and len(df) > 0:
            g.stock_pool = df['code'].tolist()
        else:
            g.stock_pool = codes[:200]  # 回退方案
        log.info('市值过滤后: %d 只' % len(g.stock_pool))
    except Exception as e:
        log.warn('市值过滤异常: %s, 使用回退池' % str(e))
        g.stock_pool = codes[:200]


def market_open(context):
    try:
        _trade_logic(context)
    except Exception as e:
        log.error('market_open 异常: %s' % str(e))
        import traceback
        log.error(traceback.format_exc())


def _trade_logic(context):
    dt = context.current_dt.date()
    pool = g.stock_pool
    log.info('持仓: %d 只, 候选池: %d 只' % (
        sum(1 for c, p in context.portfolio.positions.items() if p.total_amount > 0),
        len(pool)
    ))

    # === 1. ATR + WR 检查 ===
    atr_sells, wr_sells = [], []
    for code, pos in context.portfolio.positions.items():
        if pos.total_amount <= 0:
            continue
        try:
            bars = get_bars(code, count=g.BAR_COUNT, unit='1d',
                fields=['close','high','low','volume'],
                include_now=False, df=True, end_dt=dt)
            if bars is None or len(bars) < 50:
                continue

            cur = pos.price
            # ATR
            atr = _atr_val(bars[['high','low','close']]).iloc[-1]
            if np.isfinite(atr) and atr > 0:
                peak = g.high_peak.get(code, cur)
                g.high_peak[code] = max(peak, cur)
                stop = g.high_peak[code] - g.ATR_MULT * atr
                if cur < stop:
                    log.info('ATR止损 %s: peak=%.2f ATR=%.2f stop=%.2f now=%.2f' % (
                        code, g.high_peak[code], atr, stop, cur))
                    atr_sells.append(code)
                    continue

            # WR
            wr = _wr_val(bars).iloc[-1]
            if np.isfinite(wr) and wr > g.WR_TH:
                t = _trend(bars['high'], bars['low'], bars['close'])
                v = t.dropna()
                if len(v) >= 1 and v.iloc[-1] > 50:
                    log.info('WR止盈 %s: WR=%.1f trend=%.1f' % (code, wr, v.iloc[-1]))
                    wr_sells.append(code)
        except Exception as e:
            log.warn('检查 %s 异常: %s' % (code, str(e)))

    # 执行卖出
    for code in atr_sells + wr_sells:
        order_target(code, 0)
        g.high_peak.pop(code, None)
        g.buy_costs.pop(code, None)

    # === 2. 信号扫描 ===
    buys, sells = [], []
    checked, sig_count, vol_fail = 0, 0, 0

    for code in pool:
        try:
            bars = get_bars(code, count=g.BAR_COUNT, unit='1d',
                fields=['close','high','low','volume'],
                include_now=False, df=True, end_dt=dt)
        except:
            continue
        if bars is None or len(bars) < g.PARAM_N + 5:
            continue

        t = _trend(bars['high'], bars['low'], bars['close'])
        v = t.dropna()
        if len(v) < 2:
            continue
        tn, tp = v.iloc[-1], v.iloc[-2]
        if not np.isfinite(tn) or not np.isfinite(tp):
            continue
        checked += 1

        # 卖出
        if tp >= g.SELL_TH and tn < g.SELL_TH:
            sells.append(code)
            sig_count += 1
            continue

        # 买入
        if tp <= g.BUY_TH and tn > g.BUY_TH:
            sig_count += 1
            va = bars['volume'].iloc[-g.VOL_WINDOW:-1].mean()
            vr = bars['volume'].iloc[-1] / va if va > 0 else 1.0
            if vr < g.VOL_MIN:
                vol_fail += 1
                continue
            sc = _score(tn, vr)
            buys.append({'code': code, 'score': sc, 'close': bars['close'].iloc[-1]})

    log.info('扫描: 检查%d 信号%d 量比过滤%d 买入%d 信号卖出%d' % (
        checked, sig_count, vol_fail, len(buys), len(sells)))

    # 执行信号卖出
    for code in sells:
        pos = context.portfolio.positions.get(code)
        if pos and pos.total_amount > 0:
            order_target(code, 0)
            log.info('信号卖出 %s' % code)
            g.high_peak.pop(code, None)
            g.buy_costs.pop(code, None)

    # === 3. 补仓 ===
    exist = set(c for c, p in context.portfolio.positions.items() if p.total_amount > 0)
    n_open = g.FIXED_POS - len(exist)
    log.info('空位: %d (持仓%d/%d)' % (n_open, len(exist), g.FIXED_POS))

    if n_open <= 0 or not buys:
        return

    exist_codes = set(context.portfolio.positions.keys())
    to_buy = [s for s in buys if s['code'] not in exist_codes][:n_open]
    buys.sort(key=lambda x: x['score'], reverse=True)

    if not to_buy:
        return

    per = context.portfolio.available_cash / len(to_buy)
    for sig in to_buy:
        order_value(sig['code'], per)
        g.buy_costs[sig['code']] = sig['close']
        g.high_peak[sig['code']] = sig['close']
        log.info('买入 %s 金额%.0f 评分%.1f' % (sig['code'], per, sig['score']))


def after_market_close(context):
    n = sum(1 for c, p in context.portfolio.positions.items() if p.total_amount > 0)
    log.info('收盘: 持仓%d 净值%.0f 现金%.0f' % (
        n, context.portfolio.total_value, context.portfolio.available_cash))
