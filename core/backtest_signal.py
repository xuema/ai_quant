"""
Backtest Signal Long — 基于 run_daily.py 生成的 signal_long CSV 回测收益

signal_long CSV 只有 code/date/score/factor, 没有 name/reason。
从 data_cache_daily 读取 Open 价作为买入价，计算持仓收益。

用法：
  # 默认：加载最新 signal_long 文件
  python core/backtest_signal.py

  # 指定日期
  python core/backtest_signal.py --date 20260410

  # 持仓 N 个交易日（默认算到最新可用数据）
  python core/backtest_signal.py --date 20260410 --hold-days 3

  # 导出 CSV
  python core/backtest_signal.py --date 20260410 --output /tmp/signal_bt.csv
"""

import json
import os
import sys
import csv
import argparse
from glob import glob

import pandas as pd

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, PARENT_DIR)

from config import CONFIG


def find_latest_signal():
    """找到 data/results/ 下最新的 signal_long 文件。"""
    results_dir = os.path.join(PROJECT_ROOT, "data", "results")
    pattern = os.path.join(results_dir, "**", "signal_long_*.csv")
    files = glob(pattern, recursive=True)
    if not files:
        return None
    files.sort(reverse=True)
    return files[0]


def get_price_data(code: str, price_dir: str) -> pd.DataFrame:
    """读取股票日线数据。"""
    file_path = os.path.join(price_dir, f"{code}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame()
    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])
    for col in ["Close", "Open"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)
    return df.dropna(subset=["Close"])


def calculate_returns(signals_df: pd.DataFrame, price_dir: str,
                      hold_days: int = None) -> tuple:
    """
    计算每只信号股的实际收益。
    买入价 = 公告日当天的 Open 价（开盘买入）
    """
    results = []
    missing = []

    for _, row in signals_df.iterrows():
        code = str(row["code"]).zfill(6)
        ann_date = pd.to_datetime(row["date"])
        score = float(row.get("score", 0))
        factor = float(row.get("factor", 0))

        df = get_price_data(code, price_dir)
        if df.empty:
            missing.append(code)
            continue

        match = df[df["Date"] >= ann_date]
        if len(match) == 0:
            missing.append(f"{code}(无公告日后数据)")
            continue

        # 📌 买入价 = Open（开盘即买）
        entry_row = match.iloc[0]
        if "Open" in df.columns and pd.notna(entry_row.get("Open")):
            entry_price = float(entry_row["Open"])
        else:
            entry_price = float(entry_row["Close"])

        entry_date = entry_row["Date"]
        entry_idx = entry_row.name

        # 退出
        if hold_days is not None:
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(df):
                exit_idx = len(df) - 1
        else:
            exit_idx = len(df) - 1

        exit_row = df.iloc[exit_idx]
        exit_price = float(exit_row["Close"])
        exit_date = exit_row["Date"]

        ret = (exit_price - entry_price) / entry_price * 100
        hold_trading = exit_idx - entry_idx

        results.append({
            "code": code,
            "score": round(score, 2),
            "factor": round(factor, 3),
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price_open": round(entry_price, 2),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "exit_price": round(exit_price, 2),
            "hold_trading_days": hold_trading,
            "return_pct": round(ret, 2),
        })

    return pd.DataFrame(results), missing


def main():
    parser = argparse.ArgumentParser(description="基于 signal_long CSV 回测收益")
    parser.add_argument("--date", type=str, default=None,
                        help="信号日期 YYYYMMDD（默认最新）")
    parser.add_argument("--hold-days", type=int, default=None,
                        help="持仓交易日天数（默认算到最新）")
    parser.add_argument("--output", type=str, default=None,
                        help="导出 CSV 路径")
    args = parser.parse_args()

    price_dir = CONFIG.get("price_cache_dir")

    # 找 signal_long 文件
    if args.date:
        results_dir = os.path.join(PROJECT_ROOT, "data", "results")
        pattern = os.path.join(results_dir, args.date, f"signal_long_{args.date}.csv")
    else:
        pattern = find_latest_signal()
        if pattern is None:
            print("❌ 找不到任何 signal_long 文件")
            sys.exit(1)

    if not os.path.exists(pattern):
        print(f"❌ 找不到 {pattern}")
        # 列出可用文件
        results_dir = os.path.join(PROJECT_ROOT, "data", "results")
        for root, dirs, files in os.walk(results_dir):
            for f in files:
                if f.startswith("signal_long_"):
                    print(f"  可用: {os.path.join(root, f)}")
        sys.exit(1)

    # 加载
    signals_df = pd.read_csv(pattern)
    signal_date = os.path.basename(os.path.dirname(pattern))

    print("=" * 60)
    print("📊 回测 Signal Long 选股收益")
    print(f"   信号日期: {signal_date}")
    print(f"   信号文件: {os.path.basename(pattern)}")
    print(f"   信号数量: {len(signals_df)}")
    if args.hold_days:
        print(f"   持仓: {args.hold_days} 个交易日")
    else:
        print(f"   持仓: 到最新可用数据")
    print("=" * 60)

    results, missing = calculate_returns(signals_df, price_dir, hold_days=args.hold_days)

    if results.empty:
        print("\n❌ 没有获取到任何股票的价格数据")
        if missing:
            print(f"   缺失股票: {missing}")
        return

    # 汇总
    print(f"\n📈 结果汇总 ({len(results)} 只有价格数据)")
    print(f"   平均收益: {results['return_pct'].mean():.2f}%")
    print(f"   中位数:   {results['return_pct'].median():.2f}%")
    print(f"   最高:     {results['return_pct'].max():+.2f}%  [{results.loc[results['return_pct'].idxmax(), 'code']}]")
    print(f"   最低:     {results['return_pct'].min():+.2f}%  [{results.loc[results['return_pct'].idxmin(), 'code']}]")
    print(f"   盈利比例: {(results['return_pct'] > 0).sum()}/{len(results)} ({(results['return_pct'] > 0).mean():.0%})")

    if missing:
        print(f"\n⚠️ 缺失 {len(missing)} 只股票: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")

    # 明细
    print(f"\n{'─' * 90}")
    print(f"{'序号':>3s}  {'代码':>6s}  {'Score':>5s}  {'Factor':>7s}  {'买入开盘':>8s}  {'现价':>8s}  {'持仓(d)':>6s}  {'收益率':>6s}")
    print(f"{'─' * 90}")

    for i, (_, row) in enumerate(results.iterrows(), 1):
        ret_str = f"{row['return_pct']:+.1f}%"
        print(f"{i:>3d}  {row['code']:>6s}  {row['score']:>5.1f}  {row['factor']:>7.3f}  {row['entry_price_open']:>8.2f}  {row['exit_price']:>8.2f}  {row['hold_trading_days']:>6d}  {ret_str:>6s}")

    print(f"{'─' * 90}")

    if args.output:
        results.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"\n💾 已导出: {args.output}")


if __name__ == "__main__":
    main()
