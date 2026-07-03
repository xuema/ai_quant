"""
run_daily.py — Announcement Alpha Event-Study & Signal Pipeline

Usage:
    # --- 完整模式（回测/评估，需要公告后有足够的价格数据） ---
    python3 run_daily.py                                    # 默认最新日期
    python3 run_daily.py --mode market                      # 使用市值调整 CAR
    python3 run_daily.py --pre 7 --post 5                   # 自定义窗口
    python3 run_daily.py --top-k 30                         # 多空各 30 只
    python3 run_daily.py --date 20260401                    # 指定公告日期

    # --- 信号模式（当日可用，不需要未来价格数据） ---
    python3 run_daily.py --signal-only                      # 当天公告 → 快速出交易信号
    python3 run_daily.py --signal-only --date 20260413      # 指定日期，只看当天信号
    python3 run_daily.py --signal-only --top-k 30           # 信号模式自定义 top-k

Pipeline (完整模式):
  1. Load data (announcements + prices [+ optional market index])
  2. Build raw factor from announcement scores
  3. Apply risk model (filter → winsorize → z-score)
  4. Event-study CAR (pre/post leak detection)
  5. Multi-dimensional IC analysis
  6. Leakage analysis
  7. Generate long/short signals
  8. Save everything and print a summary report

Pipeline (信号模式 --signal-only):
  1. Load announcements for the specified date
  2. Build raw factor from scores
  3. Apply risk model
  4. Generate long/short signals (skip CAR / IC / leakage — no future price needed)
  5. Save signal files and print summary

When to use which:
  --signal-only  → 每天公告出来后，快速获知当天该做多/做空哪些股票
                   （适用于当日交易决策，不需要等未来价格数据）
  (默认模式)      → 回测和因子质量评估，计算 IC、leakage、CAR 等指标
                   （需要公告日之后有足够的价格数据，当天跑会全部跳过）
"""

import argparse
import time
import os
import sys

import pandas as pd

# Add project root to path so imports resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

from config import CONFIG as DEFAULT_CONFIG

from core.loader import load_announcements, load_price_from_local, load_market_from_local
from core.factor_builder import build_factor
from core.strategy import generate_signal
from core.risk_model import apply_risk_model
from core.event_study_extended import calc_event_car


# =========================
# CLI Arguments
# =========================
def parse_args():
    parser = argparse.ArgumentParser(
        description="Run announcement alpha event study or signal generation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Full pipeline (needs post-event price data):
    python3 run_daily.py --date 20260410

  Signal-only mode (same-day trading signals, no CAR needed):
    python3 run_daily.py --signal-only
    python3 run_daily.py --signal-only --date 20260413
        """,
    )
    parser.add_argument("--date", type=str, default=None,
                        help="Specify announcement date YYYYMMDD (default: latest)")
    parser.add_argument("--mode", default=None, choices=["simple", "market"],
                        help="CAR mode (overrides config.py)")
    parser.add_argument("--pre", type=int, default=None,
                        help="Pre-event window (trading days)")
    parser.add_argument("--post", type=int, default=None,
                        help="Post-event window (trading days)")
    parser.add_argument("--top-k", type=int, default=None,
                        help="Number of stocks for long/short signal")
    parser.add_argument("--signal-only", action="store_true", default=False,
                        help="Signal-only mode: skip CAR/IC/leakage, output long/short signals immediately. "
                             "Use this for same-day trading decisions.")
    return parser.parse_args()


def merge_config(args):
    """Merge CLI args into default config."""
    cfg = DEFAULT_CONFIG.copy()
    if args.mode:
        cfg["car_mode"] = args.mode
    if args.pre is not None:
        cfg["pre_window"] = args.pre
    if args.post is not None:
        cfg["post_window"] = args.post
    if args.top_k is not None:
        cfg["top_k"] = args.top_k
    if args.date and len(args.date) == 8:
        cfg["date_filter"] = args.date
    cfg["signal_only"] = args.signal_only
    return cfg


# =========================
# Main Pipeline
# =========================
def run(cfg: dict):

    t0 = time.time()
    is_signal_only = cfg.get("signal_only", False)

    print("=" * 60)
    if is_signal_only:
        print("🎯 Announcement Alpha — Signal-Only Mode")
        print("   (No CAR / IC / leakage — same-day signals only)")
    else:
        print("🚀 Announcement Alpha — Daily Run")
    print(f"   Mode       : {'signal-only' if is_signal_only else 'CAR'}")
    print(f"   CAR mode   : {cfg['car_mode']}")
    print(f"   Pre window : {cfg['pre_window']}")
    print(f"   Post window: {cfg['post_window']}")
    print(f"   Top K      : {cfg['top_k']}")
    print("=" * 60)

    # -----------------------------------------------
    # 1️⃣ Data
    # -----------------------------------------------
    step_label = "1/4" if is_signal_only else "1/7"
    print(f"\n📂 Step {step_label} — Loading data...")

    ann = load_announcements(cfg["announcement_dir"])
    if ann.empty:
        print("❌ No announcement data found. Check the data/raw_json directory.")
        return

    # 日期过滤：如果指定了 --date，只加载对应日期的公告
    if "date_filter" in cfg:
        target = pd.to_datetime(cfg["date_filter"]).date()
        ann["date"] = pd.to_datetime(ann["date"]).dt.date
        before = len(ann)
        ann = ann[ann["date"] == target]
        after = len(ann)
        print(f"  🔍 日期过滤: {cfg['date_filter']} → {before} 条 → {after} 条")
        if ann.empty:
            print(f"  ⚠️ {cfg['date_filter']} 暂无公告数据")
            return

    if is_signal_only:
        # Signal-only: no price data needed
        print(f"  ✅ Announcements: {len(ann)} rows, {ann['code'].nunique()} unique stocks")
        price_data = None
        market_data = None
    else:
        # Full mode: load prices for CAR
        price_data = load_price_from_local(cfg["price_cache_dir"])
        if price_data.empty:
            print("❌ No price data found. Check data_cache_daily.")
            return

        market_data = None
        if cfg["car_mode"] == "market":
            mkt_path = cfg["market_index_file"]
            if os.path.exists(mkt_path):
                market_data = load_market_from_local(mkt_path)
                print(f"  ✅ Market data loaded ({len(market_data)} rows)")
            else:
                print(f"  ⚠️ Market file not found at {mkt_path}, falling back to simple CAR")
                cfg["car_mode"] = "simple"

        print(f"  ✅ Announcements: {len(ann)} rows, {ann['code'].nunique()} unique stocks")
        print(f"  ✅ Price data:    {price_data['code'].nunique()} stocks, {len(price_data)} rows")

    # -----------------------------------------------
    # 📁 自动识别公告日期，作为输出文件的后缀
    # -----------------------------------------------
    unique_dates = sorted(ann["date"].unique())
    date_label = pd.to_datetime(unique_dates[-1]).strftime("%Y%m%d")
    print(f"  📅 公告日期: {date_label}")

    # -----------------------------------------------
    # 📂 创建输出目录 data/results/YYYYMMDD/
    # -----------------------------------------------
    _RESULTS_DIR = os.path.join(os.path.dirname(__file__), "data", "results")
    OUT_DIR = os.path.join(_RESULTS_DIR, date_label)
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"  📁 输出目录: {OUT_DIR}")

    # -----------------------------------------------
    # 2️⃣ Factor Construction
    # -----------------------------------------------
    step_label = "2/4" if is_signal_only else "2/7"
    print(f"\n📐 Step {step_label} — Building factor...")

    factor = build_factor(ann)
    print(f"  → Raw factor: {len(factor)} rows (post-aggregation)")

    # -----------------------------------------------
    # 3️⃣ Risk Model
    # -----------------------------------------------
    step_label = "3/4" if is_signal_only else "3/7"
    print(f"\n🛡️  Step {step_label} — Applying risk model...")

    factor = apply_risk_model(factor)
    print(f"  → Post risk model: {len(factor)} rows")

    # -----------------------------------------------
    # 4️⃣ Event-Study CAR (full mode only)
    # -----------------------------------------------
    car_df = pd.DataFrame()

    if not is_signal_only:
        step_label = "4/7"
        print(f"\n📊 Step {step_label} — Computing CAR (event study)...")

        results = []
        skipped = 0

        for _, row in factor.iterrows():
            stock_df = price_data[price_data["code"] == row["code"]]

            if len(stock_df) < 20:
                skipped += 1
                continue

            res = calc_event_car(
                stock_df=stock_df,
                event_date=row["date"],
                market_df=market_data,
                pre_window=cfg["pre_window"],
                post_window=cfg["post_window"]
            )

            if res is None:
                skipped += 1
                continue

            results.append({
                "code": row["code"],
                "date": row["date"],
                "factor": row["factor"],
                "car_pre": res["car_pre"],
                "car_post": res["car_post"],
                "car_total": res["car_total"],
                "leakage": res["leakage_ratio"],
                "reason": row.get("reason", "") if isinstance(row.get("reason"), str) else "",
            })

        car_df = pd.DataFrame(results)

        if len(car_df) == 0:
            print(f"❌ No valid CAR data ({skipped} events skipped — insufficient price data)")
            return

        print(f"  ✅ Valid CAR results: {len(car_df)} ({skipped} skipped)")

        # -----------------------------------------------
        # 5️⃣ IC Analysis
        # -----------------------------------------------
        print("\n📈 Step 5/7 — IC Analysis:")

        ic_total = car_df["factor"].corr(car_df["car_total"])
        ic_post = car_df["factor"].corr(car_df["car_post"])
        ic_pre = car_df["factor"].corr(car_df["car_pre"])

        print(f"   IC_total: {ic_total:.4f}")
        print(f"   IC_post : {ic_post:.4f}  ⭐ (pure alpha)")
        print(f"   IC_pre  : {ic_pre:.4f}  ⚠️ (possible leakage)")

        # -----------------------------------------------
        # 6️⃣ Leakage Analysis
        # -----------------------------------------------
        print("\n🧠 Step 6/7 — Leakage Analysis:")

        valid_leakage = car_df.dropna(subset=["leakage"])
        if len(valid_leakage) > 0:
            high_leak = valid_leakage[valid_leakage["leakage"] > 0.5]
            print(f"   High-leakage events (leakage > 0.5): {len(high_leak)} / {len(valid_leakage)}  ({len(high_leak)/len(valid_leakage):.2%})")
            print(f"   Mean leakage: {valid_leakage['leakage'].mean():.4f}")
            print(f"   Median leakage: {valid_leakage['leakage'].median():.4f}")
        else:
            print("   No valid leakage ratios computed.")

    # -----------------------------------------------
    # 4️⃣ / 7️⃣ Signal Generation
    # -----------------------------------------------
    step_label = "4/4" if is_signal_only else "7/7"
    print(f"\n🎯 Signal Generation (Step {step_label})...")

    long, short = generate_signal(factor, top_k=cfg["top_k"])

    # ---- 带日期后缀的文件名 ----
    f_long = f"signal_long_{date_label}.csv"
    f_short = f"signal_short_{date_label}.csv"

    # Enrich signals with announcement metadata (event_type, confidence, label, reason)
    long = _enrich_with_ann_info(long, ann)
    short = _enrich_with_ann_info(short, ann)

    long_path = os.path.join(OUT_DIR, f_long)
    short_path = os.path.join(OUT_DIR, f_short)

    # Write CSV with ="" around code so Excel treats it as text
    # = "002078" forces Excel text mode, and the display strips the = and quotes
    import csv as _csv
    for _df, _path in [(long, long_path), (short, short_path)]:
        cols = _df.columns.tolist()
        with open(_path, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.writer(f, quoting=_csv.QUOTE_NONE, escapechar="\\")
            w.writerow(cols)
            for _, row in _df.iterrows():
                vals = []
                for c in cols:
                    if c == "code" and pd.notna(row[c]):
                        vals.append("=" + str(int(row[c])).zfill(6))
                    else:
                        vals.append("" if pd.isna(row[c]) else str(row[c]))
                w.writerow(vals)

    print(f"  → Long  signals: {len(long)} rows → {f_long}")
    print(f"  → Short signals: {len(short)} rows → {f_short}")

    # ---- 打印 Long 信号摘要 ----
    if len(long) > 0:
        print(f"\n📊 Long 信号概览:")
        for i, (_, row) in enumerate(long.iterrows()):
            code = row.get("code", "?")
            name = row.get("name", "")
            score = row.get("score", "")
            reason = row.get("reason", "") if not pd.isna(row.get("reason", "")) else ""
            label = row.get("label", "")
            event_type = row.get("event_type", "")
            note = f" | {name}"
            if label:
                note += f" | {label}"
            if event_type:
                note += f" | {event_type}"
            if reason:
                note += f" | {reason}"
            print(f"  {i+1:>2}. [{code}]{note} score={score}")

    # ---- 打印 Short 信号摘要 ----
    if len(short) > 0:
        print(f"\n📊 Short 信号概览:")
        for i, (_, row) in enumerate(short.iterrows()):
            code = row.get("code", "?")
            name = row.get("name", "")
            score = row.get("score", "")
            reason = row.get("reason", "") if not pd.isna(row.get("reason", "")) else ""
            label = row.get("label", "")
            event_type = row.get("event_type", "")
            note = f" | {name}"
            if label:
                note += f" | {label}"
            if event_type:
                note += f" | {event_type}"
            if reason:
                note += f" | {reason}"
            print(f"  {i+1:>2}. [{code}]{note} score={score}")

    # -----------------------------------------------
    # Summary Report
    # -----------------------------------------------
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("✅ Done!")
    print(f"   Time elapsed: {elapsed:.1f}s")
    print(f"   Output directory: {OUT_DIR}")
    print(f"   Output files:")
    if not is_signal_only:
        f_car = f"car_results_{date_label}.csv"
        car_path = os.path.join(OUT_DIR, f_car)
        car_df.to_csv(car_path, index=False, encoding="utf-8-sig")
        print(f"     - {f_car}    ({len(car_df)} rows)")
    print(f"     - {f_long}  ({len(long)} rows)")
    print(f"     - {f_short} ({len(short)} rows)")
    print("=" * 60)


def _enrich_with_ann_info(signal_df: pd.DataFrame, ann_df: pd.DataFrame) -> pd.DataFrame:
    """Merge announcement metadata into signal DataFrame.

    If the signal dataframe already contains ann metadata columns
    (event_type, confidence, label, reason, name, holding_days),
    this is a no-op. Otherwise, it falls back to merging from
    ann_df on code + date.
    """
    if signal_df.empty or ann_df.empty:
        return signal_df

    # Signal dataframe already has the metadata columns from factor_builder
    meta_cols = ["event_type", "confidence", "label", "reason", "name", "holding_days"]
    already_has = all(c in signal_df.columns for c in meta_cols)
    if already_has:
        return signal_df

    # Fallback: merge from ann
    signal_df = signal_df.copy()
    enrich_cols = [c for c in meta_cols if c in ann_df.columns]
    if not enrich_cols:
        return signal_df

    ann_subset = ann_df[["code", "date"] + enrich_cols]

    # Align date types (signal_df date is datetime, ann date might be date or datetime)
    signal_df["date"] = pd.to_datetime(signal_df["date"])
    ann_subset = ann_subset.copy()
    ann_subset["date"] = pd.to_datetime(ann_subset["date"])

    result = signal_df.merge(
        ann_subset, on=["code", "date"], how="left"
    )
    return result


if __name__ == "__main__":
    args = parse_args()
    cfg = merge_config(args)
    run(cfg)
