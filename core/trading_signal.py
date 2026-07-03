"""
Trading Signal Generator — 直接从 ranking CSV 生成交易清单

不依赖 run_daily.py 的复杂链路（CAR/IC/泄露检测），
仅基于 LLM 评分结果快速生成可执行交易清单。

用法：
  python core/trading_signal.py                        # 加载最新 ranking
  python core/trading_signal.py --date 20260410        # 指定日期
  python core/trading_signal.py --top 20               # 取 Top 20
  python core/trading_signal.py --min-score 1.0        # 最低 score 阈值
  python core/trading_signal.py --types 业绩,分红       # 只选特定类型
  python core/trading_signal.py --output csv            # 输出格式：table/csv/json
  python core/trading_signal.py --top 20 --output csv --o /tmp/signals.csv
"""

import json
import os
import sys
import csv
import argparse
from datetime import datetime, timedelta
from glob import glob

import pandas as pd

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import CONFIG


def _find_latest_ranking_file(ext: str):
    """根据扩展名找最新 ranking 文件。"""
    raw_dir = CONFIG.get("announcement_dir")
    files = [f for f in os.listdir(raw_dir)
             if f.startswith("ranking_") and f.endswith(ext)]
    if not files:
        return None
    files.sort(key=lambda f: f.replace("ranking_", "").replace(ext, ""), reverse=True)
    return os.path.join(raw_dir, files[0])


def find_latest_ranking():
    """找到 data/raw_json/ 下最新的 ranking 文件（优先 CSV，兼容 JSON）。"""
    csv_path = _find_latest_ranking_file(".csv")
    if csv_path:
        return csv_path
    return _find_latest_ranking_file(".json")


def _load_ranking_csv(path: str) -> list:
    """从 ranking CSV 加载，返回 dict 列表。"""
    df = pd.read_csv(path, dtype={"code": str})
    df["code"] = df["code"].str.zfill(6)
    return df.to_dict(orient="records")


def _load_ranking_json(path: str) -> list:
    """从 ranking JSON 加载（旧格式兼容）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 确保 code 6 位
    for item in data:
        item["code"] = str(item.get("code", "")).zfill(6)
    return data


def load_ranking(date_str: str = None) -> tuple:
    """加载 ranking 文件，返回 (元信息, 公告列表)。
    优先 .csv，不存在则 fallback 到 .json。"""
    raw_dir = CONFIG.get("announcement_dir")

    if date_str:
        # 优先找 CSV
        path = os.path.join(raw_dir, f"ranking_{date_str}.csv")
        if not os.path.exists(path):
            path = os.path.join(raw_dir, f"ranking_{date_str}.json")
        if not os.path.exists(path):
            files = sorted(
                [f for f in os.listdir(raw_dir) if f.startswith("ranking_")]
            )
            print(f"❌ 找不到 ranking_{date_str} (.csv / .json)")
            print(f"   可用文件: {files}")
            return None, []
    else:
        path = find_latest_ranking()
        if not path:
            print("❌ 找不到任何 ranking 文件")
            return None, []

    if path.endswith(".csv"):
        data = _load_ranking_csv(path)
    else:
        data = _load_ranking_json(path)

    meta = {
        "file": os.path.basename(path),
        "count": len(data),
    }
    return meta, data


def generate_signal(
    items: list,
    top: int = None,
    min_score: float = 0,
    max_score: float = None,
    event_types: list = None,
    exclude_types: list = None,
    min_confidence: float = 0,
    sort_by: str = "score",
):
    """过滤并排序交易信号。"""
    result = []

    for item in items:
        # 过滤
        score = float(item.get("score", 0))
        if score < min_score:
            continue
        if max_score is not None and score > max_score:
            continue

        confidence = float(item.get("confidence", 0))
        if confidence < min_confidence:
            continue

        event_type = item.get("event_type", "")
        if event_types and event_type not in event_types:
            continue
        if exclude_types and event_type in exclude_types:
            continue

        result.append(item)

    # 排序
    if sort_by == "score":
        result.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    elif sort_by == "confidence":
        result.sort(key=lambda x: float(x.get("confidence", 0)), reverse=True)

    # Top N
    if top:
        result = result[:top]

    return result


def format_table(signals: list) -> str:
    """格式化为对齐表格（终端友好）。"""
    if not signals:
        return "（无符合条件的信号）"

    # 表头
    header = f"{'序号':>4s}  {'代码':>6s}  {'名称':<12s}  {'类型':<6s}  {'Score':>5s}  {'信度':>4s}  {'持仓':>4s}  {'理由'}"
    sep = "─" * len(header)

    lines = [sep, header, sep]
    for i, s in enumerate(signals, 1):
        code = str(s.get("code", "?")).zfill(6)
        name = str(s.get("name", "?"))[:12]
        event_type = str(s.get("event_type", "?"))[:6]
        score = str(s.get("score", ""))
        confidence = str(s.get("confidence", ""))[:4]
        holding = str(s.get("holding_days", ""))
        reason = str(s.get("reason", ""))[:30]

        line = f"{i:>4d}  {code:>6s}  {name:<12s}  {event_type:<6s}  {score:>5s}  {confidence:>4s}  {holding:>4s}  {reason}"
        lines.append(line)
    lines.append(sep)

    return "\n".join(lines)


def format_csv(signals: list) -> str:
    """格式化为 CSV（BOM 编码由调用方处理，这里返回文本）。"""
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["code", "name", "date", "event_type", "score",
                     "confidence", "holding_days", "reason", "title"],
    )
    writer.writeheader()
    for s in signals:
        writer.writerow({
            "code": str(s.get("code", "")).zfill(6),
            "name": str(s.get("name", "")),
            "date": str(s.get("date", "")),
            "event_type": str(s.get("event_type", "")),
            "score": s.get("score", ""),
            "confidence": s.get("confidence", ""),
            "holding_days": s.get("holding_days", ""),
            "reason": str(s.get("reason", "")),
            "title": str(s.get("title", "")),
        })
    return buf.getvalue().rstrip()


def main():
    parser = argparse.ArgumentParser(description="从 ranking JSON 生成交易清单")
    parser.add_argument("--date", type=str, default=None,
                        help="ranking 文件日期 YYYYMMDD（默认最新）")
    parser.add_argument("--top", type=int, default=None,
                        help="只取 Top N 条")
    parser.add_argument("--min-score", type=float, default=0,
                        help="最低 score 阈值（默认 0）")
    parser.add_argument("--max-score", type=float, default=None,
                        help="最大 score 阈值")
    parser.add_argument("--min-confidence", type=float, default=0,
                        help="最低置信度阈值（0-1）")
    parser.add_argument("--types", type=str, default=None,
                        help="只选特定事件类型（逗号分隔）")
    parser.add_argument("--exclude-types", type=str, default=None,
                        help="排除特定事件类型（逗号分隔）")
    parser.add_argument("--sort", type=str, default="score",
                        choices=["score", "confidence"],
                        help="排序字段（默认 score）")
    parser.add_argument("--output", type=str, default="table",
                        choices=["table", "csv", "json"],
                        help="输出格式")
    parser.add_argument("--o", type=str, default=None,
                        help="输出到文件路径")
    args = parser.parse_args()

    # 加载
    meta, data = load_ranking(args.date)
    if not data:
        sys.exit(1)

    print(f"📂 加载: {meta['file']} ({meta['count']} 条)")
    print()

    # 解析类型
    event_types = args.types.split(",") if args.types else None
    exclude_types = args.exclude_types.split(",") if args.exclude_types else None

    # 生成信号
    signals = generate_signal(
        data,
        top=args.top,
        min_score=args.min_score,
        max_score=args.max_score,
        event_types=event_types,
        exclude_types=exclude_types,
        min_confidence=args.min_confidence,
        sort_by=args.sort,
    )

    # 统计
    if event_types:
        print(f"🔍 过滤: 类型={','.join(event_types)}, min_score={args.min_score}")
    else:
        print(f"🔍 过滤: min_score={args.min_score}, top={args.top or '全部'}")

    print(f"📊 结果: {len(signals)} 条信号\n")

    # 输出
    if args.output == "table":
        output = format_table(signals)
    elif args.output == "csv":
        output = format_csv(signals)
    else:
        output = json.dumps(signals, ensure_ascii=False, indent=2)

    if args.o:
        with open(args.o, "w", encoding="utf-8-sig", newline="") as f:
            f.write(output)
        print(f"💾 已保存: {args.o}")
    else:
        print(output)


if __name__ == "__main__":
    main()
