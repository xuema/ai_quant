"""
Intersection Signal — 取 Ranking Top-N 和 Signal Long Top-N 的交集

双重筛选逻辑：
  - 在 ranking CSV 中 score 排名前 N
  - 同时在 signal_long CSV 中 factor 排名前 M
  - 取交集 → 只买两边都认可的股票

用法：
  # 默认：加载最新 ranking + 最新 signal，取交集
  python core/intersection_signal.py

  # 指定日期
  python core/intersection_signal.py --date 20260408

  # 调整两边 Top 数量
  python core/intersection_signal.py --date 20260408 --top-ranking 20 --top-signal 20

  # 回测持仓 3 天
  python core/intersection_signal.py --date 20260408 --backtest --hold-days 3

  # 导出
  python core/intersection_signal.py --date 20260408 --output csv
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


def find_latest_ranking():
    """找最新 ranking 文件（优先 CSV，兼容 JSON）。"""
    raw_dir = CONFIG.get("announcement_dir")
    files = []
    for ext in (".csv", ".json"):
        files.extend(
            [f for f in os.listdir(raw_dir)
             if f.startswith("ranking_") and f.endswith(ext)]
        )
    if not files:
        return None, None
    # 排序：ranking_YYYYMMDD.ext → 按日期倒序
    files.sort(key=lambda f: f.replace("ranking_", "").replace(".csv", "").replace(".json", ""), reverse=True)
    return os.path.join(raw_dir, files[0]), files[0]


def load_ranking(path: str, top_n: int) -> dict:
    """加载 ranking 文件（CSV/JSON），返回 {code: info} 字典。"""
    if path.endswith(".csv"):
        df = pd.read_csv(path, dtype={"code": str})
        data = df.to_dict(orient="records")
        for item in data:
            item["code"] = str(item.get("code", "")).zfill(6)
    else:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            item["code"] = str(item.get("code", "")).zfill(6)

    data.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    top = data[:top_n]
    return {item["code"]: item for item in top}


def find_latest_signal():
    results_dir = os.path.join(PROJECT_ROOT, "data", "results")
    pattern = os.path.join(results_dir, "**", "signal_long_*.csv")
    files = glob(pattern, recursive=True)
    if not files:
        return None, None
    files.sort(reverse=True)
    return files[0], os.path.basename(os.path.dirname(files[0]))


def load_signal(path: str, top_n: int) -> dict:
    """加载 signal_long CSV，返回 {code: info} 字典。"""
    df = pd.read_csv(path)
    if len(df) > top_n:
        df = df.sort_values("factor", ascending=False).head(top_n)
    return {str(row["code"]).zfill(6): row for _, row in df.iterrows()}


def backtest_intersection(codes: list, price_dir: str,
                          ann_date: str, hold_days: int = None) -> pd.DataFrame:
    """回测交集股票的收益。"""
    results = []
    missing = []
    ann_date_dt = pd.to_datetime(ann_date)

    for code in codes:
        fpath = os.path.join(price_dir, f"{code}.csv")
        if not os.path.exists(fpath):
            missing.append(code)
            continue

        df = pd.read_csv(fpath)
        df["Date"] = pd.to_datetime(df["Date"])
        for col in ["Close", "Open"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("Date").reset_index(drop=True)

        match = df[df["Date"] >= ann_date_dt]
        if len(match) == 0:
            missing.append(code)
            continue

        entry_row = match.iloc[0]
        if "Open" in df.columns and pd.notna(entry_row.get("Open")):
            entry_price = float(entry_row["Open"])
        else:
            entry_price = float(entry_row["Close"])

        entry_idx = entry_row.name
        if hold_days is not None:
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(df):
                exit_idx = len(df) - 1
        else:
            exit_idx = len(df) - 1

        exit_row = df.iloc[exit_idx]
        exit_price = float(exit_row["Close"])
        ret = (exit_price - entry_price) / entry_price * 100

        results.append({
            "code": code,
            "entry_date": entry_row["Date"].strftime("%Y-%m-%d"),
            "entry_open": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round(ret, 2),
        })

    return pd.DataFrame(results), missing


def main():
    parser = argparse.ArgumentParser(description="Ranking + Signal 交集选股")
    parser.add_argument("--date", type=str, default=None,
                        help="信号日期 YYYYMMDD（默认最新）")
    parser.add_argument("--top-ranking", type=int, default=20,
                        help="Ranking 取 Top N（默认 20）")
    parser.add_argument("--top-signal", type=int, default=20,
                        help="Signal 取 Top N（默认 20）")
    parser.add_argument("--backtest", action="store_true",
                        help="开启回测")
    parser.add_argument("--hold-days", type=int, default=None,
                        help="持仓交易日天数")
    parser.add_argument("--output", type=str, choices=["table", "csv", "json"],
                        default="table", help="输出格式")
    args = parser.parse_args()

    price_dir = CONFIG.get("price_cache_dir")
    raw_dir = CONFIG.get("announcement_dir")
    results_base = os.path.join(PROJECT_ROOT, "data", "results")

    # ---- 找文件 ----
    if args.date:
        ranking_path = os.path.join(raw_dir, f"ranking_{args.date}.csv")
        if not os.path.exists(ranking_path):
            ranking_path = os.path.join(raw_dir, f"ranking_{args.date}.json")
        signal_path = os.path.join(results_base, args.date, f"signal_long_{args.date}.csv")
        date_label = args.date
    else:
        ranking_path, ranking_name = find_latest_ranking()
        signal_path, signal_date = find_latest_signal()
        date_label = signal_date  # 用 signal 的日期

        if not ranking_path or not signal_path:
            print("❌ 找不到 ranking 或 signal 文件")
            sys.exit(1)

    if not os.path.exists(ranking_path):
        print(f"❌ 找不到 {ranking_path}")
        sys.exit(1)
    if not os.path.exists(signal_path):
        print(f"❌ 找不到 {signal_path}")
        sys.exit(1)

    # ---- 加载 ----
    ranking_top = load_ranking(ranking_path, args.top_ranking)
    signal_top = load_signal(signal_path, args.top_signal)

    rank_codes = set(ranking_top.keys())
    sig_codes = set(signal_top.keys())

    # 交集
    intersection = sorted(rank_codes & sig_codes)
    only_in_ranking = sorted(rank_codes - sig_codes)
    only_in_signal = sorted(sig_codes - rank_codes)

    print("=" * 60)
    print("🎯 双重筛选：Ranking + Signal 交集")
    print(f"   日期: {date_label}")
    print(f"   Ranking Top {args.top_ranking}: {len(ranking_top)} 只")
    print(f"   Signal  Top {args.top_signal}: {len(signal_top)} 只")
    print(f"   ✅ 交集: {len(intersection)} 只")
    print(f"   ⚪ 仅 Ranking: {len(only_in_ranking)} 只")
    print(f"   ⚪ 仅 Signal:  {len(only_in_signal)} 只")
    print("=" * 60)

    # ---- 交集详情 ----
    if intersection:
        print(f"\n📊 交集股票明细:")
        print(f"{'─' * 90}")
        print(f"{'序号':>3s}  {'代码':>6s}  {'名称':<10s}  {'Ranking Score':>13s}  {'Signal Factor':>13s}  {'事件类型':<6s}  {'建议持仓':>4s}  {'理由'}")
        print(f"{'─' * 90}")

        rows = []
        for i, code in enumerate(intersection, 1):
            r = ranking_top.get(code, {})
            s = signal_top.get(code, {})
            name = str(r.get("name", ""))[:10]
            score = float(r.get("score", 0))
            factor = round(float(s.get("factor", 0)), 3)
            etype = str(r.get("event_type", ""))[:6]
            reason = str(r.get("reason", ""))[:20]
            holding = str(r.get("holding_days", ""))

            rows.append({
                "code": code,
                "name": name,
                "ranking_score": score,
                "signal_factor": factor,
                "event_type": etype,
                "holding_days": holding,
                "reason": reason,
            })

            parts = [name] if name else []
            if reason:
                parts.append(f"| {reason}")
            note = " ".join(parts)
            h_note = f"  持{holding}d" if holding else ""
            if not note:
                note = f"code={code}"
            print(f"{i:>3d}  {code:>6s}  {name:<10s}  {score:>13.1f}  {factor:>13.3f}  {etype:<6s}  {holding:>4s}{h_note}  {reason}")
        print(f"{'─' * 90}")

    # ---- 回测 ----
    if args.backtest:
        print(f"\n📈 回测结果（持仓 {args.hold_days or '到最新'} 个交易日）:")
        bt_results, missing = backtest_intersection(
            intersection, price_dir, date_label, hold_days=args.hold_days
        )

        if not bt_results.empty:
            print(f"\n  股票数: {len(bt_results)}")
            print(f"  平均收益: {bt_results['return_pct'].mean():+.2f}%")
            print(f"  中位数:   {bt_results['return_pct'].median():+.2f}%")
            print(f"  盈利比例: {(bt_results['return_pct'] > 0).sum()}/{len(bt_results)} ({(bt_results['return_pct'] > 0).mean():.0%})")

            print(f"\n  明细:")
            for i, (_, row) in enumerate(bt_results.iterrows(), 1):
                ret_str = f"{row['return_pct']:+.1f}%"
                print(f"    {i:>2d}. [{row['code']}]  {row['entry_open']:>8.2f} → {row['exit_price']:>8.2f}  {ret_str:>6s}")

            if missing:
                print(f"\n  ⚠️ 缺失: {', '.join(missing[:5])}")

    # ---- 导出 ----
    if args.output == "csv":
        fpath = f"/tmp/intersection_{date_label}.csv"
        with open(fpath, "w", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["code", "name", "ranking_score", "signal_factor",
                                               "event_type", "holding_days", "reason"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n💾 已导出: {fpath}")
    elif args.output == "json":
        fpath = f"/tmp/intersection_{date_label}.json"
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已导出: {fpath}")


if __name__ == "__main__":
    main()
