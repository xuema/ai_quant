"""
Backtest Ranking Signals — 基于历史 ranking 验证选股收益

给定某天（或几天前）的 ranking CSV（兼容旧 JSON），按 score 选前 N 只，
从 data_cache_daily/ 读取这些股票的历史价格，计算从公告日
到当前最新日期的实际收益率（以及每日明细）。

用法：
  # 用 04-08 的 ranking 选 Top 20，看涨幅
  python core/backtest_ranking.py --date 20260408 --top 20

  # 用 04-09 的 ranking，计算到 04-10 的收益
  python core/backtest_ranking.py --date 20260409 --top 20

  # 导出详细 CSV
  python core/backtest_ranking.py --date 20260408 --top 20 --output results.csv

  # 指定持仓天数（从公告日起算 N 个交易日）
  python core/backtest_ranking.py --date 20260408 --top 20 --hold-days 5
"""

import json
import os
import sys
import argparse

import pandas as pd

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(PROJECT_ROOT)  # stock_selection/
sys.path.insert(0, PROJECT_ROOT)

from config import CONFIG


def load_ranking(date_str: str) -> list:
    """加载指定日期的 ranking 文件。优先 CSV，兼容 JSON。"""
    raw_dir = CONFIG.get("announcement_dir")
    path = os.path.join(raw_dir, f"ranking_{date_str}.csv")
    ext = ".csv"
    if not os.path.exists(path):
        path = os.path.join(raw_dir, f"ranking_{date_str}.json")
        ext = ".json"
    if not os.path.exists(path):
        print(f"❌ 找不到 ranking_{date_str} (.csv / .json)")
        files = [f for f in os.listdir(raw_dir) if f.startswith("ranking_")]
        if files:
            print(f"   可用文件: {sorted(files)}")
        return []

    if ext == ".csv":
        df = pd.read_csv(path, dtype={"code": str})
        df["code"] = df["code"].str.zfill(6)
        data = df.to_dict(orient="records")
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            item["code"] = str(item.get("code", "")).zfill(6)

    data.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    return data


def get_price_data(code: str, price_dir: str) -> pd.DataFrame:
    """从 data_cache_daily 读取单只股票的日线数据。"""
    file_path = os.path.join(price_dir, f"{code}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame()
    df = pd.read_csv(file_path)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    for col in ["Close", "Open", "High", "Low"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["Close"])


def calculate_returns(signals: list, price_dir: str,
                      hold_days: int = None) -> pd.DataFrame:
    """
    计算每只信号股票从公告日到最新可用日的收益率。

    📌 核心逻辑：
       盘前出公告 → 开盘即买入 → 买入价 = 公告日当天的 Open 价
    """
    results = []
    missing_stocks = []

    for signal in signals:
        code = str(signal.get("code", "")).zfill(6)
        ann_date = pd.to_datetime(signal.get("date", ""))
        score = float(signal.get("score", 0))
        name = signal.get("name", "")
        reason = signal.get("reason", "")
        event_type = signal.get("event_type", "")

        df = get_price_data(code, price_dir)
        if df.empty:
            missing_stocks.append(code)
            continue

        # 找到公告日当天（或之后的第一个交易日）
        match = df[df["Date"] >= ann_date]
        if len(match) == 0:
            # 所有数据都在公告日之前
            missing_stocks.append(code)
            continue

        entry_row = match.iloc[0]
        entry_date = entry_row["Date"]
        entry_idx = entry_row.name

        # 📌 买入价 = 公告日当天的 Open 价（开盘即买入）
        if "Open" in df.columns and pd.notna(entry_row.get("Open")):
            entry_price = float(entry_row["Open"])
        else:
            # fallback: 用前一日 Close
            fallback_idx = entry_idx - 1
            if fallback_idx < 0:
                missing_stocks.append(code)
                continue
            entry_price = float(df.iloc[fallback_idx]["Close"])

        # 📌 退出：从公告日当天起，持有 N 个交易日
        if hold_days is not None:
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(df):
                exit_idx = len(df) - 1
        else:
            exit_idx = len(df) - 1

        exit_row = df.iloc[exit_idx]
        exit_price = exit_row["Close"]
        exit_date = exit_row["Date"]

        # 收益率
        ret = (exit_price - entry_price) / entry_price * 100

        # 持有天数
        actual_hold_days = (exit_date - entry_date).days if hasattr(exit_date, 'date') else 0

        results.append({
            "code": code,
            "name": name,
            "score": round(score, 2),
            "event_type": event_type,
            "reason": reason,
            "entry_date": entry_date.strftime("%Y-%m-%d"),
            "entry_price": round(entry_price, 3),
            "exit_date": exit_date.strftime("%Y-%m-%d"),
            "exit_price": round(exit_price, 3),
            "return_pct": round(ret, 2),
        })

    df_result = pd.DataFrame(results)
    return df_result, missing_stocks


def main():
    parser = argparse.ArgumentParser(description="基于历史 ranking 验证选股收益")
    parser.add_argument("--date", type=str, required=True,
                        help="ranking 文件日期 YYYYMMDD")
    parser.add_argument("--top", type=int, default=20,
                        help="选取 Top N 只（默认 20）")
    parser.add_argument("--min-score", type=float, default=0,
                        help="最低 score 阈值")
    parser.add_argument("--hold-days", type=int, default=None,
                        help="持仓交易日天数（默认算到最新可用数据）")
    parser.add_argument("--output", type=str, default=None,
                        help="导出 CSV 路径")
    args = parser.parse_args()

    price_dir = CONFIG.get("price_cache_dir", os.path.join(PARENT_DIR, "data_cache_daily"))

    # 加载 ranking
    data = load_ranking(args.date)
    if not data:
        sys.exit(1)

    # 过滤 + 排序
    data = [s for s in data if float(s.get("score", 0)) >= args.min_score]
    data = data[:args.top]

    print("=" * 60)
    print("📊 回测 Ranking 选股信号")
    print(f"   Ranking 日期: {args.date}")
    print(f"   选取: Top {args.top}")
    if args.hold_days:
        print(f"   持仓: {args.hold_days} 个交易日")
    else:
        print(f"   持仓: 到最新可用数据")
    print("=" * 60)

    # 计算收益
    results, missing = calculate_returns(data, price_dir, hold_days=args.hold_days)

    if results.empty:
        print("\n❌ 没有获取到任何股票的价格数据")
        if missing:
            print(f"   缺失股票: {missing}")
        return

    # 汇总统计
    print(f"\n📈 结果汇总 ({len(results)} 只有价格数据)")
    print(f"   平均收益: {results['return_pct'].mean():.2f}%")
    print(f"   中位数:   {results['return_pct'].median():.2f}%")
    print(f"   最高:     {results['return_pct'].max():.2f}%  [{results.loc[results['return_pct'].idxmax(), 'code']}]")
    print(f"   最低:     {results['return_pct'].min():.2f}%  [{results.loc[results['return_pct'].idxmin(), 'code']}]")
    print(f"   盈利比例: {(results['return_pct'] > 0).sum()}/{len(results)} ({(results['return_pct'] > 0).mean():.0%})")

    if missing:
        print(f"\n⚠️ 缺失 {len(missing)} 只股票: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")

    # 明细表格
    print(f"\n{'─' * 80}")
    print(f"{'序号':>3s}  {'代码':>6s}  {'名称':<10s}  {'Score':>5s}  {'类型':<4s}  {'买入日':>10s}  {'买入价':>8s}  {'现价':>8s}  {'收益率':>6s}  {'理由'}")
    print(f"{'─' * 80}")

    for i, (_, row) in enumerate(results.iterrows(), 1):
        reason_short = str(row.get("reason", ""))[:15]
        event_short = str(row.get("event_type", ""))[:4]
        name_short = str(row.get("name", ""))[:10]
        ret_str = f"{row['return_pct']:+.1f}%"
        print(f"{i:>3d}  {row['code']:>6s}  {name_short:<10s}  {row['score']:>5.1f}  {event_short:<4s}  {row['entry_date']:>10s}  {row['entry_price']:>8.2f}  {row['exit_price']:>8.2f}  {ret_str:>6s}  {reason_short}")

    print(f"{'─' * 80}")

    # 导出
    if args.output:
        results.to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"\n💾 已导出: {args.output}")


if __name__ == "__main__":
    main()
