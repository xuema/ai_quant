"""
下载同花顺概念/行业板块历史行情数据（断点续跑）
================================================
数据源：同花顺（akshare）
输出：data_cache_sector/concept_*.csv, data_cache_sector/industry_*.csv

用法：
  python3 3_update_sector_data.py              # 下载概念+行业板块（从头开始）
  python3 3_update_sector_data.py --resume     # 从上次断点继续
  python3 3_update_sector_data.py --from=50    # 从第 51 个板块开始
  python3 3_update_sector_data.py --type concept  # 只下载概念板块
  python3 3_update_sector_data.py --type industry # 只下载行业板块
"""

import pandas as pd
import os
import sys
import time
from datetime import datetime, timedelta
import akshare as ak
import warnings

warnings.filterwarnings("ignore")

# ---------------- 配置 ----------------
DATA_DIR = "./data_cache_sector/"
DAYS_HISTORY = 800  # 约 2 年
BATCH_SIZE = 20
BATCH_SLEEP = 3

os.makedirs(DATA_DIR, exist_ok=True)

# ================================================================
#  获取板块名称列表
# ================================================================

def fetch_concept_list():
    """获取同花顺概念板块列表"""
    df = ak.stock_board_concept_name_ths()
    # 排除大盘/全市场类
    return df[['name', 'code']].copy()


def fetch_industry_list():
    """获取同花顺行业板块列表"""
    df = ak.stock_board_industry_name_ths()
    return df[['name', 'code']].copy()


# ================================================================
#  下载单个板块历史数据
# ================================================================

def download_board_history(board_name, board_code, board_type, start_date, end_date):
    """下载单个板块的历史行情，返回 DataFrame"""
    if board_type == "concept":
        df = ak.stock_board_concept_index_ths(
            symbol=board_name, start_date=start_date, end_date=end_date
        )
    else:
        df = ak.stock_board_industry_index_ths(
            symbol=board_name, start_date=start_date, end_date=end_date
        )

    if df is None or df.empty:
        return None

    # 标准化列名
    df = df.rename(columns={
        "日期": "Date",
        "开盘价": "Open",
        "最高价": "High",
        "最低价": "Low",
        "收盘价": "Close",
        "成交量": "Volume",
        "成交额": "Amount"
    })
    df = df.sort_values("Date").reset_index(drop=True)
    return df


# ================================================================
#  读取本地 CSV 最新日期
# ================================================================

def get_csv_latest_date(file_path: str):
    """快速读取 CSV 最后一行日期"""
    try:
        with open(file_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return None
            read_size = min(2000, size)
            f.seek(-read_size, 2)
            tail = f.read().decode("utf-8-sig")
            lines = tail.splitlines()
            if not lines:
                return None
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                date_part = parts[0].strip()
                if not date_part:
                    continue
                dt = pd.to_datetime(date_part, errors="coerce")
                if pd.isna(dt):
                    continue
                return dt.date()
    except Exception:
        return None
    return None


# ================================================================
#  更新单个板块 CSV（增量模式）
# ================================================================

def update_board_csv(board_name, board_code, board_type):
    """下载板块数据，增量更新"""
    file_path = os.path.join(DATA_DIR, f"{board_type}_{board_code}_{board_name}.csv")

    today = datetime.now().date()
    start_date_full = (today - timedelta(days=DAYS_HISTORY)).strftime("%Y%m%d")
    end_date_full = today.strftime("%Y%m%d")

    # 检查本地是否有数据
    csv_date = None
    if os.path.exists(file_path):
        csv_date = get_csv_latest_date(file_path)
        if csv_date is None:
            print(f"   ⚠️ 本地数据异常，全量下载...")
            csv_date = None

    if csv_date is None:
        # 全量下载
        try:
            print(f"   📥 全量下载（{start_date_full} ~ {end_date_full}）...")
            df = download_board_history(board_name, board_code, board_type,
                                        start_date_full, end_date_full)
            if df is None or df.empty:
                print(f"   ❌ 下载无数据")
                return False
            df.to_csv(file_path, index=False, encoding="utf-8-sig")
            print(f"   ✅ 全量保存 {len(df)} 行")
            return True
        except Exception as e:
            print(f"   ❌ 全量下载失败: {e}")
            return False

    # 增量更新
    if csv_date >= today:
        print(f"   ⏭️ 已同步 {csv_date}")
        return True

    start_date = csv_date.strftime("%Y%m%d")
    try:
        print(f"   🔄 增量更新（{start_date} ~ {end_date_full}）...")
        df = download_board_history(board_name, board_code, board_type,
                                    start_date, end_date_full)
        if df is None or df.empty:
            return True  # 周末/节假日，正常

        old_df = pd.read_csv(file_path)
        combined = pd.concat([old_df, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        combined.to_csv(file_path, index=False, encoding="utf-8-sig")
        print(f"   ✅ 更新完成 → 最新: {combined['Date'].values[-1][:10]} ({len(combined)} 行)")
        return True
    except Exception as e:
        print(f"   ⚠️ 增量更新失败: {e}，尝试全量下载...")
        try:
            df = download_board_history(board_name, board_code, board_type,
                                        start_date_full, end_date_full)
            if df is None or df.empty:
                print(f"   ❌ 回退全量下载也无数据")
                return False
            df.to_csv(file_path, index=False, encoding="utf-8-sig")
            print(f"   ✅ 回退全量保存 {len(df)} 行")
            return True
        except Exception as e2:
            print(f"   ❌ 全量下载也失败: {e2}")
            return False


# ================================================================
#  主程序
# ================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="同花顺板块历史行情下载器")
    parser.add_argument("--type", choices=["concept", "industry", "both"],
                        default="both", help="板块类型")
    parser.add_argument("--resume", action="store_true", help="从断点继续")
    parser.add_argument("--from", dest="from_idx", type=int, default=0,
                        help="起始索引")
    args = parser.parse_args()

    # ---- 断点续跑 ----
    RESUME_DIR = "./"
    RESUME_FILE = os.path.join(RESUME_DIR, "_sector_resume.txt")

    def save_resume(index: int):
        with open(RESUME_FILE, "w") as f:
            f.write(str(index))

    def load_resume() -> int:
        if os.path.exists(RESUME_FILE):
            try:
                return int(open(RESUME_FILE).read().strip())
            except Exception:
                pass
        return 0

    resume_from = load_resume() if args.resume else 0
    if args.from_idx > 0:
        resume_from = args.from_idx

    # 构建板块列表
    all_boards = []

    if args.type in ("concept", "both"):
        print("📡 获取概念板块列表...")
        concept_df = fetch_concept_list()
        for _, row in concept_df.iterrows():
            all_boards.append({
                "name": row["name"],
                "code": str(row["code"]),
                "type": "concept"
            })
        print(f"   概念板块: {len(concept_df)} 个")

    if args.type in ("industry", "both"):
        print("📡 获取行业板块列表...")
        industry_df = fetch_industry_list()
        for _, row in industry_df.iterrows():
            all_boards.append({
                "name": row["name"],
                "code": str(row["code"]),
                "type": "industry"
            })
        print(f"   行业板块: {len(industry_df)} 个")

    total = len(all_boards)
    print(f"\n📋 总计: {total} 个板块")

    if resume_from > 0:
        if resume_from >= total:
            print("✅ 所有板块已处理完成！")
            sys.exit(0)
        print(f"🔄 从断点 {resume_from+1}/{total} 继续...")
        start = resume_from
    else:
        start = 0

    success = 0
    failed = 0
    skipped = 0

    for idx in range(start, total):
        board = all_boards[idx]
        label = f"{board['name']} [{board['code']}]"
        type_label = "概念" if board["type"] == "concept" else "行业"
        print(f"\n[{idx+1}/{total}] {type_label}: {label}")

        result = update_board_csv(board["name"], board["code"], board["type"])
        if result is True:
            success += 1
        elif result is False:
            failed += 1

        # 每处理一批休息一下
        if (idx + 1) % BATCH_SIZE == 0:
            print(f"  💤 休息 {BATCH_SLEEP}s …")
            time.sleep(BATCH_SLEEP)

        # 保存进度
        save_resume(idx + 1)

    # 统计
    print(f"\n{'='*50}")
    print(f"📊 下载完成总结:")
    print(f"   ✅ 成功: {success}")
    print(f"   ❌ 失败: {failed}")
    print(f"   总计处理: {total - start}/{total - (args.from_idx if args.from_idx else 0)}")
    print(f"{'='*50}")

    # 完成清除断点
    if os.path.exists(RESUME_FILE):
        os.remove(RESUME_FILE)
    print("\n🎉 全部完成！")
