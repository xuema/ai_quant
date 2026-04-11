"""
run_daily.py — Announcement Alpha Event-Study Pipeline

Usage:
    python run_daily.py                          # defaults
    python run_daily.py --mode market             # use market-adjusted CAR
    python run_daily.py --pre 7 --post 5          # custom windows
    python run_daily.py --top-k 30                # top/bottom 30

Pipeline:
  1. Load data (announcements + prices [+ optional market index])
  2. Build raw factor from announcement scores
  3. Apply risk model (filter → winsorize → z-score)
  4. Event-study CAR (pre/post leak detection)
  5. Multi-dimensional IC analysis
  6. Leakage analysis
  7. Generate long/short signals
  8. Save everything and print a summary report
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
    parser = argparse.ArgumentParser(description="Run announcement alpha event study.")
    parser.add_argument("--mode", default=None, choices=["simple", "market"],
                        help="CAR mode (overrides config.py)")
    parser.add_argument("--pre", type=int, default=None,
                        help="Pre-event window (trading days)")
    parser.add_argument("--post", type=int, default=None,
                        help="Post-event window (trading days)")
    parser.add_argument("--top-k", type=int, default=None,
                        help="Number of stocks for long/short signal")
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
    return cfg


# =========================
# Main Pipeline
# =========================
def run(cfg: dict):

    t0 = time.time()
    print("=" * 60)
    print("🚀 Announcement Alpha — Daily Run")
    print(f"   CAR mode   : {cfg['car_mode']}")
    print(f"   Pre window : {cfg['pre_window']}")
    print(f"   Post window: {cfg['post_window']}")
    print(f"   Top K      : {cfg['top_k']}")
    print("=" * 60)

    # -----------------------------------------------
    # 1️⃣ Data
    # -----------------------------------------------
    t1 = time.time()
    print("\n📂 Step 1/7 — Loading data...")

    ann = load_announcements(cfg["announcement_dir"])
    if ann.empty:
        print("❌ No announcement data found. Check the data/raw_json directory.")
        return

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
    # 取最后一个日期作为主日期标签（例如 20260401）
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
    t2 = time.time()
    print("\n📐 Step 2/7 — Building factor...")

    factor = build_factor(ann)
    print(f"  → Raw factor: {len(factor)} rows (post-aggregation)")

    # -----------------------------------------------
    # 3️⃣ Risk Model
    # -----------------------------------------------
    print("\n🛡️  Step 3/7 — Applying risk model...")

    factor = apply_risk_model(factor)
    print(f"  → Post risk model: {len(factor)} rows")

    # -----------------------------------------------
    # 4️⃣ Event-Study CAR
    # -----------------------------------------------
    t3 = time.time()
    print("\n📊 Step 4/7 — Computing CAR (event study)...")

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
            "leakage": res["leakage_ratio"]
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
    # 7️⃣ Signal Generation
    # -----------------------------------------------
    print("\n🎯 Step 7/7 — Generating signals...")

    long, short = generate_signal(factor, top_k=cfg["top_k"])

    # ---- 带日期后缀的文件名 ----
    f_long = f"signal_long_{date_label}.csv"
    f_short = f"signal_short_{date_label}.csv"
    f_car = f"car_results_{date_label}.csv"

    long_path = os.path.join(OUT_DIR, f_long)
    short_path = os.path.join(OUT_DIR, f_short)
    car_path = os.path.join(OUT_DIR, f_car)

    long.to_csv(long_path, index=False)
    short.to_csv(short_path, index=False)
    car_df.to_csv(car_path, index=False)

    print(f"  → Long  signals: {len(long)} rows → {f_long}")
    print(f"  → Short signals: {len(short)} rows → {f_short}")

    # -----------------------------------------------
    # Summary Report
    # -----------------------------------------------
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("✅ Done!")
    print(f"   Time elapsed: {elapsed:.1f}s")
    print(f"   Output directory: {OUT_DIR}")
    print(f"   Output files:")
    print(f"     - {f_car}    ({len(car_df)} rows)")
    print(f"     - {f_long}  ({len(long)} rows)")
    print(f"     - {f_short} ({len(short)} rows)")
    print("=" * 60)


if __name__ == "__main__":
    args = parse_args()
    cfg = merge_config(args)
    run(cfg)
