"""
cninfo_announcement_fetcher.py — 巨潮公告抓取 + PDF提取 + LLM 评分

完整流程：
  1. 从巨潮资讯网抓取 A 股公告
  2. 强信号关键词预筛选
  3. 下载 PDF → 提取文本
  4. 按 event_type 分组 → 调用 OpenRouter API 批量评分
  5. 输出 ranking_YYYYMMDD.json → data/raw_json/
  6. 可选触发 run_daily.py 生成交易信号

用法：
  # 爬取 + PDF提取 + 评分（默认昨天）
  python pipeline/cninfo_fetcher.py

  # 指定日期
  python pipeline/cninfo_fetcher.py 2026-04-09

  # 只抓取不评分
  python pipeline/cninfo_fetcher.py 2026-04-09 --raw-only

  # 强制重新评分
  python pipeline/cninfo_fetcher.py 2026-04-09 --force-score

  # 完整链路：爬取 + 评分 + 跑信号
  python pipeline/cninfo_fetcher.py 2026-04-09 --run-daily

  # 获取 2026-04-09 到 2026-04-11（3天）                                                                                                                                                                                                        
   python pipeline/cninfo_fetcher.py 2026-04-13 --days 3 --force-score
"""

import requests
import os
import sys
import time
import json
import argparse
import io
import logging
from datetime import datetime, timedelta
from collections import Counter

# Suppress pypdf warnings about malformed PDF pointers
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
    print("⚠️ pypdf 未安装，PDF提取不可用。请运行: pip install pypdf")

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
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36"),
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch"
}

# ================================================================
# 强信号关键词（粗筛用，按类型分组）
# ================================================================
STRONG_KEYWORDS = {
    "业绩": [
        "业绩预告", "业绩快报", "净利润", "盈利", "亏损",
        "营业收入", "每股收益", "经营业绩",
        "业绩预增", "业绩预减", "业绩上升", "业绩下降",
        "业绩预告", "年度业绩", "半年度业绩", "季度业绩",
    ],
    "分红": [
        "利润分配", "分红", "派息", "送股", "转增", "现金红利",
    ],
    "增持": [
        "增持", "回购", "员工持股", "管理层增持",
    ],
    "减持": [
        "减持", "股东减持", "大股东减持",
    ],
    "减值": [
        "资产减值", "减值准备", "商誉减值", "计提减值", "核销",
    ],
    "股权激励": [
        "股权激励", "限制性股票", "股票期权",
    ],
    "重组": [
        "收购", "重组", "并购", "重大资产",
    ],
    "订单": [
        "重大合同", "中标", "订单",
    ],
    "其他": [
        "重大诉讼", "仲裁", "处罚", "销售情况", "月报",
        "经营数据", "定增", "非公开发行", "配股", "可转债",
        "复牌", "退市",
    ],
}


def classify_event(title: str) -> str:
    """根据标题分类事件类型，返回最匹配的类型。"""
    t = str(title)
    for event_type, keywords in STRONG_KEYWORDS.items():
        if any(k in t for k in keywords):
            return event_type
    return "其他"


def is_strong_signal(title: str) -> bool:
    """标题是否命中强信号关键词。"""
    return classify_event(title) != "其他" or any(
        k in str(title)
        for kw_list in STRONG_KEYWORDS.values()
        for k in kw_list
    )


# ================================================================
# 1️⃣ 抓取
# ================================================================
def fetch_day_announcements(date_str: str) -> list:
    """从巨潮资讯网抓取指定日期的全部公告。"""
    all_data = []
    seen_ann_ids = set()  # 检测重复项，防止死循环
    page = 1

    print("  正在抓取...", end="", flush=True)

    while page <= 700:
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
            print(f"\n  ❌ 第 {page} 页请求失败: {e}")
            print(f"  已抓取: {len(all_data)} 条")
            time.sleep(2)
            break

        total = data.get("totalAnnouncement", 0)
        max_page_from_total = max(1, (total + 29) // 30)
        progress_msg = f"\r  正在抓取... 第 {page} 页 / 共 {max_page_from_total} 页 | 已抓取 {len(all_data)} / {total} 条"
        print(progress_msg, end="", flush=True)

        anns = data.get("announcements", [])
        if not anns:
            if page == 1:
                print("\n  ⚠️ 该日无公告")
            break

        # ── 去重：用 title+code+time 作为唯一标识，防止尾部循环重复 ──
        new_count = 0
        for item in anns:
            ann_key = (item.get("announcementTitle", ""), item.get("secCode", ""), item.get("announcementTime", ""))
            if ann_key not in seen_ann_ids:
                seen_ann_ids.add(ann_key)
                new_count += 1

                sec_code = str(item.get("secCode", "")).zfill(6)
                adjunct = item.get("adjunctUrl", "")
                pdf_url = f"https://static.cninfo.com.cn/{adjunct}"

                all_data.append({
                    "code": sec_code,
                    "name": item.get("secName", ""),
                    "title": item.get("announcementTitle", ""),
                    "time": item.get("announcementTime"),
                    "pdf_url": pdf_url,
                })

        # ── 如果 API 已知的 total 小于等于当前已抓取数量，说明到底了 ──
        if total > 0 and len(all_data) >= total:
            break

        # ── 如果 page 已达到 total 算出的总页数，停止 ──
        if total > 0 and page >= max_page_from_total:
            break

        if len(anns) < 30:
            break

        page += 1
        time.sleep(0.3)

    if page > 700:
        print("\n  ⚠️ 达到页数上限（700页），强制停止")

    print()  # 换行
    return all_data


# ================================================================
# 2️⃣ 筛选 + 去重
# ================================================================
def filter_announcements(raw_anns: list) -> list:
    """过滤强信号 + 排除 ST + 去重 + 分类。"""
    seen = set()
    filtered = []
    st_count = 0

    for ann in raw_anns:
        title = str(ann.get("title", ""))
        code = str(ann.get("code", ""))
        name = str(ann.get("name", ""))

        # 排除 ST 公司（名称含 ST 或 *ST）
        if "ST" in name or "*ST" in name or "st " in name.lower():
            st_count += 1
            continue

        if not is_strong_signal(title):
            continue

        key = f"{code}_{title}"
        if key in seen:
            continue
        seen.add(key)

        ann["event_type"] = classify_event(title)
        filtered.append(ann)

    type_counts = Counter(a.get("event_type", "其他") for a in filtered)
    print(f"  📋 全部: {len(raw_anns)} → 排除 ST: {st_count} 条 → 强信号: {len(filtered)}")
    print(f"  📂 类型分布: {dict(type_counts)}")
    return filtered


# ================================================================
# 3️⃣ PDF 下载 & 文本提取
# ================================================================
def download_pdf(url: str, timeout: int = 15) -> bytes:
    """下载 PDF 文件。"""
    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": CNINFO_HEADERS["User-Agent"],
    })
    resp.raise_for_status()
    return resp.content


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 5) -> str:
    """从 PDF 提取文本，最多处理前 max_pages 页。"""
    if not HAS_PYPDF:
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        total = min(len(reader.pages), max_pages)
        for i in range(total):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        return f"[PDF解析失败: {e}]"


def enrich_with_pdf_text(announcements: list, pdf_dir: str = None) -> list:
    """为公告下载 PDF 并提取文本。"""
    if not pdf_dir:
        pdf_dir = os.path.join(PROJECT_ROOT, "data", "pdf_cache")
    os.makedirs(pdf_dir, exist_ok=True)

    enabled_count = 0
    skip_count = 0
    fail_count = 0

    for ann in announcements:
        code = ann.get("code", "")
        title = ann.get("title", "")
        pdf_url = ann.get("pdf_url", "")

        if not pdf_url:
            ann["pdf_text"] = "[无PDF]"
            fail_count += 1
            continue

        # 检查本地缓存
        safe_name = f"{code}_{title[:30].replace('/', '_').replace('\\', '_')}.pdf"
        pdf_path = os.path.join(pdf_dir, safe_name)

        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            # 已有缓存，直接提取
            with open(pdf_path, "rb") as f:
                text = extract_pdf_text(f.read())
            ann["pdf_text"] = text
            skip_count += 1
            continue

        # 下载
        try:
            raw = download_pdf(pdf_url)
            with open(pdf_path, "wb") as f:
                f.write(raw)
            text = extract_pdf_text(raw)
            ann["pdf_text"] = text
            enabled_count += 1
            time.sleep(0.3)  # 防频率
        except Exception as e:
            ann["pdf_text"] = f"[下载失败: {e}]"
            fail_count += 1
            print(f"    ⚠️ {code} PDF 失败: {e}")

    print(f"  📄 PDF: 新下载 {enabled_count}, 缓存 {skip_count}, 失败 {fail_count}")
    return announcements


# ================================================================
# 4️⃣ LLM 评分 (由 llm_scorer.py 处理)
# ================================================================


# ================================================================
# 5️⃣ 格式化为 ranking
# ================================================================
def format_ranking(scored: list, date_str: str) -> list:
    """转换为 run_daily.py 需要的格式，按 score 从高到低排序。"""
    bullish = [s for s in scored if s.get("score", 0) > 0]
    bullish.sort(key=lambda x: x.get("score", 0), reverse=True)
    ranking = []
    for item in bullish:
        entry = {
            "code": str(item.get("code", "")).zfill(6),
            "name": item.get("name", ""),
            "date": date_str,
            "score": round(float(item.get("score", 0)), 2),
            "title": item.get("title", ""),
            "event_type": item.get("event_type", "其他"),
            "confidence": round(float(item.get("confidence", 0)), 2),
            "label": item.get("label", "利多"),
        }
        for field in ("reason", "holding_days"):
            if item.get(field):
                entry[field] = item[field]
        ranking.append(entry)
    return ranking


# ================================================================
# 6️⃣ 触发 run_daily.py
# ================================================================
def trigger_daily_run():
    """调用 run_daily.py 生成交易信号并运行 CAR 分析。"""
    run_daily = os.path.join(PROJECT_ROOT, "run_daily.py")
    if not os.path.exists(run_daily):
        print("⚠️ run_daily.py 不存在，跳过")
        return

    print("\n🔄 触发 run_daily.py ...")
    import subprocess
    result = subprocess.run([sys.executable, run_daily], cwd=PROJECT_ROOT)
    if result.returncode == 0:
        print("✅ run_daily.py 完成")
    else:
        print(f"❌ run_daily.py 失败 (exit {result.returncode})")


# ================================================================
# 主流程
# ================================================================
def main(target_date: str = None, raw_only: bool = False,
         force_score: bool = False, run_daily_flag: bool = False,
         days: int = 1, max_items: int = 700):
    """
    支持多天公告爬取。

    - target_date 为结束日期（最新日），向前推 days-1 天
    - 文件以最新日期为后缀
    - max_items 为筛选后的公告数量上限
    """
    if target_date is None:
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    # 计算日期范围
    end_dt = datetime.strptime(target_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=days - 1)

    latest_label = end_dt.strftime("%Y%m%d")
    date_label = latest_label  # 用最新日期命名
    raw_dir = CONFIG.get("announcement_dir")
    os.makedirs(raw_dir, exist_ok=True)
    ranking_path = os.path.join(raw_dir, f"ranking_{date_label}.json")

    # 检查已有结果
    if os.path.exists(ranking_path) and not force_score and not raw_only:
        try:
            with open(ranking_path, "r", encoding="utf-8") as f:
                exist = json.load(f)
            if exist and isinstance(exist, list) and len(exist) > 0:
                print(f"⏭️ {target_date} 已有评级文件 ({len(exist)} 条)")
                if run_daily_flag:
                    trigger_daily_run()
                return
        except Exception:
            pass

    # 生成日期列表
    date_list = []
    d = start_dt
    while d <= end_dt:
        date_list.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    print("=" * 60)
    print("🚀 公告爬取 + PDF提取 + LLM 评分")
    if len(date_list) == 1:
        print(f"   日期: {date_list[0]}")
    else:
        print(f"   日期范围: {date_list[0]} ~ {date_list[-1]} ({len(date_list)} 天)")
    print(f"   公告上限: {max_items} 条")
    print("=" * 60)

    # ── Step 1: 爬取（多天） ──
    print("\n📡 Step 1/4 — 巨潮公告爬取...")
    all_raw = []
    for date_str in date_list:
        print(f"\n  📅 {date_str}:")
        raw = fetch_day_announcements(date_str)
        if raw:
            all_raw.extend(raw)
        else:
            print(f"    ⚠️ 无公告")

    if not all_raw:
        print("\n❌ 所有日期均无公告数据，结束")
        return

    # 去重（多天可能有重复公告）
    seen = set()
    deduped = []
    for ann in all_raw:
        key = f"{ann['code']}|{ann['title']}|{ann['time']}"
        if key not in seen:
            seen.add(key)
            deduped.append(ann)
    if len(all_raw) != len(deduped):
        print(f"\n  去重: {len(all_raw)} → {len(deduped)} (去除 {len(all_raw) - len(deduped)} 条重复)")

    print(f"\n  ✅ 原始公告总计: {len(deduped)} 条")

    # ── Step 2: 预筛 + 分类 ──
    print("\n📋 Step 2/4 — 强信号筛选...")
    filtered = filter_announcements(deduped)

    # 限制数量（按强信号排序后取 top N）
    if len(filtered) > max_items:
        print(f"  ✂️ 超过上限 {max_items} 条，截取 Top {max_items}（按标题匹配强度）")
        # 优先保留业绩/分红类
        priority_order = ["业绩", "分红", "增持", "重组", "订单", "股权激励", "减持", "减值", "其他"]
        priority = {t: i for i, t in enumerate(priority_order)}
        filtered = sorted(filtered, key=lambda x: priority.get(x.get("event_type", "其他"), 99))
        filtered = filtered[:max_items]
        # 按原始顺序重新排序
        filtered = sorted(filtered, key=lambda x: all_raw.index(next(a for a in all_raw if a.get("title") == x.get("title") and a.get("code") == x.get("code"))))

    if not filtered:
        print("⚠️ 无强信号公告，结束")
        return
    print(f"  ✅ 筛选后: {len(filtered)} 条")

    raw_input = os.path.join(raw_dir, f"_raw_{date_label}.json")
    with open(raw_input, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)
    print(f"  📁 Raw: {raw_input} ({len(filtered)} 条)")

    if raw_only:
        print("\n🔍 Raw-only 模式，跳过 PDF 提取和评分")
        return

    # ── Step 3: PDF 下载 & 文本提取 ──
    print("\n📄 Step 3/4 — PDF 下载 & 文本提取...")
    enriched = enrich_with_pdf_text(filtered)

    # 保存带 PDF 文本的数据供 LLM 用
    llm_input_path = os.path.join(raw_dir, f"_llm_input_{date_label}.json")
    with open(llm_input_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"  📁 LLM Input: {llm_input_path}")

    # ── Step 4: LLM 评分 ──
    print("\n🧠 Step 4/4 — LLM 评分 (OpenRouter)...")
    scored = score_announcements(llm_input_path, ranking_path)

    if not scored:
        print("⚠️ LLM 评分无结果")
        return

    ranking = format_ranking(scored, target_date)
    if ranking:
        with open(ranking_path, "w", encoding="utf-8") as f:
            json.dump(ranking, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ 评分完成!")
    print(f"   利多: {len(ranking)} 条")
    if ranking:
        print(f"   文件: {ranking_path}")
        print(f"\n🏆 Top 20:")
        for i, item in enumerate(ranking[:20], 1):
            code = item.get('code', '?')
            name = item.get('name', '')
            reason = item.get('reason', '')
            holding = item.get('holding_days', '')
            score_val = item.get('score', '?')
            parts = [name]
            if reason:
                parts.append(f"| {reason}")
            note = " ".join(parts)
            print(f"  {i:>2}. [{code}] {note}  score={score_val}")
            holding_note = f" | 建议持仓 {holding} 天" if holding else ""
            print(f"      {item.get('title', '')[:50]}{holding_note}")
    print("=" * 60)

    if run_daily_flag:
        trigger_daily_run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="公告爬取 + PDF提取 + LLM 评分")
    parser.add_argument("date", nargs="?", default=None,
                        help="结束日期 YYYY-MM-DD（默认昨天）")
    parser.add_argument("--days", type=int, default=1,
                        help="爬取天数（从结束日期往前算），默认 1 天")
    parser.add_argument("--raw-only", action="store_true",
                        help="只爬不评分")
    parser.add_argument("--force-score", action="store_true",
                        help="强制重新评分")
    parser.add_argument("--run-daily", action="store_true",
                        help="评分后自动跑信号")
    args = parser.parse_args()

    main(target_date=args.date, raw_only=args.raw_only,
         force_score=args.force_score, run_daily_flag=args.run_daily,
         days=args.days)
