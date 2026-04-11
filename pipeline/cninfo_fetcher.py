"""
cninfo_announcement_fetcher.py — 巨潮公告抓取 + LLM 评分

完整流程：
  1. 从巨潮资讯网抓取 A 股公告
  2. 强信号关键词预筛选
  3. 调用 LLM（Oracle CLI）逐条评分
  4. 输出 ranking_YYYYMMDD.json → data/raw_json/
  5. 直接触发 run_daily.py 生成交易信号

用法：
  # 爬取并评分（默认昨天）
  python pipeline/cninfo_fetcher.py

  # 指定日期
  python pipeline/cninfo_fetcher.py 2026-04-09

  # 只抓取不评分
  python pipeline/cninfo_fetcher.py 2026-04-09 --raw-only

  # 强制重新评分
  python pipeline/cninfo_fetcher.py 2026-04-09 --force-score

  # 完整链路：爬取 + 评分 + 跑信号
  python pipeline/cninfo_fetcher.py 2026-04-09 --run-daily
"""

import requests
import os
import sys
import time
import json
import argparse
from datetime import datetime, timedelta

# ── 模块路径 ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import CONFIG
from core.llm_scorer import score_announcements

# ================================================================
# 巨潮 API
# ================================================================
CNINFO_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"

CNINFO_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch"
}

# ================================================================
# 强信号关键词（粗筛用）
# ================================================================
STRONG_KEYWORDS = [
    # 业绩类
    "业绩预告", "业绩快报", "净利润", "盈利", "亏损",
    # 分红类
    "利润分配", "分红", "派息", "送股", "转增", "现金红利",
    # 资产/减值
    "资产减值", "减值准备", "商誉减值", "计提减值", "核销",
    # 股权/激励
    "减持", "增持", "回购", "股权激励", "限制性股票", "员工持股",
    # 重大事项
    "收购", "重组", "并购", "重大合同", "中标", "订单",
    "重大诉讼", "仲裁", "处罚",
    # 经营/销售
    "销售情况", "月报", "经营数据",
    # 融资类
    "定增", "非公开发行", "配股", "可转债",
    # 停复牌
    "复牌", "退市",
]


def is_strong_signal(title: str) -> bool:
    """标题是否命中强信号关键词。"""
    t = str(title)
    return any(k in t for k in STRONG_KEYWORDS)


# ================================================================
# 1️⃣ 抓取
# ================================================================
def fetch_day_announcements(date_str: str) -> list:
    """
    从巨潮资讯网抓取指定日期的全部公告。
    返回: [{"code", "name", "title", "pdf_url", "time"}, ...]
    """
    all_data = []
    page = 1

    while True:
        payload = {
            "pageNum": page,
            "pageSize": 30,
            "column": "",
            "tabName": "fulltext",
            "plate": "sz;sh",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{date_str}~{date_str}",
            "sortName": "announcementTime",
            "sortType": "desc"
        }

        try:
            res = requests.post(
                CNINFO_URL, headers=CNINFO_HEADERS, data=payload, timeout=15
            )
            res.raise_for_status()
            data = res.json()
        except Exception as e:
            print(f"  ❌ 第 {page} 页请求失败: {e}")
            time.sleep(2)
            break

        anns = data.get("announcements", [])
        if not anns:
            if page == 1:
                print("  ⚠️ 该日无公告")
            break

        for item in anns:
            sec_code = str(item.get("secCode", "")).zfill(6)
            adjunct = item.get("adjunctUrl", "")
            # cninfo 的 PDF URL 使用 static.cninfo.com.cn
            pdf_url = f"https://static.cninfo.com.cn/{adjunct}"

            all_data.append({
                "code": sec_code,
                "name": item.get("secName", ""),
                "title": item.get("announcementTitle", ""),
                "time": item.get("announcementTime"),
                "pdf_url": pdf_url,
            })

        if len(anns) < 30:
            break

        page += 1
        time.sleep(0.5)  # 防频率限制

    return all_data


# ================================================================
# 2️⃣ 筛选 + 去重
# ================================================================
def filter_announcements(raw_anns: list) -> list:
    """过滤强信号 + 去重（code+title 相同视为重复）。"""
    seen = set()
    filtered = []

    for ann in raw_anns:
        title = str(ann.get("title", ""))
        code = str(ann.get("code", ""))

        if not is_strong_signal(title):
            continue

        key = f"{code}_{title}"
        if key in seen:
            continue
        seen.add(key)

        filtered.append(ann)

    print(f"  📋 全部: {len(raw_anns)} → 强信号: {len(filtered)}")
    return filtered


# ================================================================
# 3️⃣ LLM 评分
# ================================================================
def run_scoring(input_path: str, output_path: str) -> list:
    """调用 LLM 评分，返回评分结果。"""
    results = score_announcements(input_path, output_path)
    return results or []


# ================================================================
# 4️⃣ 格式化为 ranking（与 run_daily.py 兼容）
# ================================================================
def format_ranking(scored: list, date_str: str) -> list:
    """
    转换为 run_daily.py 需要的格式:
    [{"code":"000001", "date":"2026-04-09", "score":1.5, "title":"..."}]
    """
    bullish = [s for s in scored if s.get("score", 0) > 0]
    bullish = sorted(bullish, key=lambda x: x.get("score", 0), reverse=True)

    ranking = []
    for item in bullish:
        ranking.append({
            "code": str(item.get("code", "")).zfill(6),
            "date": date_str,
            "score": round(float(item.get("score", 0)), 2),
            "title": item.get("title", ""),
            "event_type": item.get("event_type", "其他"),
            "confidence": round(float(item.get("confidence", 0)), 2),
            "label": item.get("label", "利多"),
        })

    return ranking


# ================================================================
# 5️⃣ 触发 run_daily.py
# ================================================================
def trigger_daily_run():
    """
    调用 run_daily.py 生成交易信号并运行 CAR 分析。
    """
    run_daily = os.path.join(PROJECT_ROOT, "run_daily.py")
    if not os.path.exists(run_daily):
        print("⚠️ run_daily.py 不存在，跳过")
        return

    print("\n🔄 触发 run_daily.py ...")
    import subprocess
    result = subprocess.run(
        [sys.executable, run_daily],
        cwd=PROJECT_ROOT,
        capture_output=False
    )
    if result.returncode == 0:
        print("✅ run_daily.py 完成")
    else:
        print(f"❌ run_daily.py 失败 (exit {result.returncode})")


# ================================================================
# 主流程
# ================================================================
def main(target_date: str = None, raw_only: bool = False,
         force_score: bool = False, run_daily: bool = False):

    # 默认：昨天
    if target_date is None:
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    date_label = target_date.replace("-", "")

    # 输出路径
    raw_dir = CONFIG.get("announcement_dir")
    os.makedirs(raw_dir, exist_ok=True)
    ranking_path = os.path.join(raw_dir, f"ranking_{date_label}.json")

    # 检查是否已有结果
    if os.path.exists(ranking_path) and not force_score and not raw_only:
        try:
            with open(ranking_path, "r", encoding="utf-8") as f:
                exist = json.load(f)
            if exist and isinstance(exist, list) and len(exist) > 0:
                print(f"⏭️ {target_date} 已有评级文件 ({len(exist)} 条)")
                if run_daily:
                    trigger_daily_run()
                return
        except Exception:
            pass

    print("=" * 60)
    print("🚀 公告爬取 + LLM 评分")
    print(f"   日期: {target_date}")
    print("=" * 60)

    # ── Step 1: 爬取 ──
    print("\n📡 Step 1/3 — 巨潮公告爬取...")
    raw_anns = fetch_day_announcements(target_date)
    if not raw_anns:
        print("❌ 无公告数据，结束")
        return
    print(f"  ✅ 原始公告: {len(raw_anns)} 条")

    # ── Step 2: 预筛 ──
    print("\n📋 Step 2/3 — 强信号筛选...")
    filtered = filter_announcements(raw_anns)
    if not filtered:
        print("⚠️ 无强信号公告，结束")
        return

    # 保存原始（LLM 用的输入）
    raw_input = os.path.join(raw_dir, f"_raw_{date_label}.json")
    with open(raw_input, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)
    print(f"  📁 Raw: {raw_input} ({len(filtered)} 条)")

    if raw_only:
        print("\n🔍 Raw-only 模式，跳过评分")
        return

    # ── Step 3: LLM 评分 ──
    print("\n🧠 Step 3/3 — LLM 评分...")
    scored = run_scoring(raw_input, ranking_path)

    if not scored:
        print("⚠️ LLM 评分失败")
        return

    # 格式化输出
    ranking = format_ranking(scored, target_date)
    with open(ranking_path, "w", encoding="utf-8") as f:
        json.dump(ranking, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ 评分完成!")
    print(f"   利多: {len(ranking)} 条")
    if ranking:
        print(f"   文件: {ranking_path}")
        print(f"\n🏆 Top 10:")
        for i, item in enumerate(ranking[:10], 1):
            print(f"  {i:>2}. [{item['code']}] {item['title'][:50]}  score={item['score']}")
    print("=" * 60)

    # ── 可选：直接跑信号 ──
    if run_daily:
        trigger_daily_run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="公告爬取 + LLM 评分")
    parser.add_argument("date", nargs="?", default=None,
                        help="目标日期 YYYY-MM-DD（默认昨天）")
    parser.add_argument("--raw-only", action="store_true", help="只爬不评分")
    parser.add_argument("--force-score", action="store_true", help="强制重新评分")
    parser.add_argument("--run-daily", action="store_true", help="评分后自动跑信号")
    args = parser.parse_args()

    main(target_date=args.date, raw_only=args.raw_only,
         force_score=args.force_score, run_daily=args.run_daily)
