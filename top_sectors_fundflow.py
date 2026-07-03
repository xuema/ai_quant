"""
A股市场行业/概念板块综合排名
=============================
综合维度：资金净流入排名（权重 60%）+ 涨幅排名（权重 40%）

数据源：东方财富（akshare）
用法：
  python3 top_sectors_fundflow.py                  # 行业板块 Top10
  python3 top_sectors_fundflow.py -t concept        # 概念板块 Top10
  python3 top_sectors_fundflow.py -t industry 20     # 行业板块 Top20
  python3 top_sectors_fundflow.py -t concept 50      # 概念板块 Top50
"""

import sys
import datetime
import warnings
import argparse
import pandas as pd
import akshare as ak

warnings.filterwarnings("ignore")

# ================================================================
#  配置
# ================================================================
WEIGHT_FUND_FLOW = 0.6  # 资金流权重
WEIGHT_CHANGE    = 0.4  # 涨幅权重
TOP_N            = 10   # 默认输出前 N 名

# ================================================================
#  获取数据
# ================================================================
def fetch_industry_fund_flow():
    """获取实时行业板块资金流数据"""
    print("📡 正在获取行业板块资金流数据...")
    df = ak.stock_fund_flow_industry(symbol="即时")
    df.columns = [c.replace("\u200b", "").strip() for c in df.columns]
    print(f"   共获取 {len(df)} 个行业板块")
    return df


def fetch_concept_fund_flow():
    """获取实时概念板块资金流数据"""
    print("📡 正在获取概念板块资金流数据...")
    df = ak.stock_fund_flow_concept(symbol="即时")
    df.columns = [c.replace("\u200b", "").strip() for c in df.columns]
    print(f"   共获取 {len(df)} 个概念板块")
    return df


# ================================================================
#  综合排名计算
# ================================================================
def rank_sectors(df: pd.DataFrame, top_n: int = TOP_N):
    """按资金流 + 涨幅综合排名"""

    col_flow = "净额"
    col_change = "行业-涨跌幅"

    df = df.copy()

    # 清洗数值列
    for c in [col_flow, col_change, "领涨股-涨跌幅"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 按每列做百分位排名（降序，越前越好）
    df["rank_fund_flow"] = df[col_flow].rank(pct=True, method="min")
    df["rank_change"]    = df[col_change].rank(pct=True, method="min")

    # 综合分
    df["综合得分"] = (df["rank_fund_flow"] * WEIGHT_FUND_FLOW +
                    df["rank_change"] * WEIGHT_CHANGE)

    df["资金流排名"] = df[col_flow].rank(method="min", ascending=False).astype(int)
    df["涨幅排名"]   = df[col_change].rank(method="min", ascending=False).astype(int)
    df["综合排名"]   = df["综合得分"].rank(method="min", ascending=False).astype(int)

    # 排序 + 取 TopN
    df = df.sort_values("综合排名").reset_index(drop=True)
    result = df.head(top_n)[[
        "综合排名", "行业", "行业-涨跌幅", "资金流排名", "涨幅排名",
        "综合得分", "净额", "行业指数", "公司家数", "领涨股", "领涨股-涨跌幅", "当前价"
    ]].copy()

    return result


# ================================================================
#  输出
# ================================================================
def save_result(result: pd.DataFrame, board_type: str):
    """保存结果到输出目录"""
    import os
    today = datetime.date.today().strftime("%Y%m%d")
    out_dir = f"data/top_{board_type}_fundflow"
    os.makedirs(out_dir, exist_ok=True)

    board_label = "sector" if board_type == "industry" else "concept"
    csv_path = os.path.join(out_dir, f"top_{board_label}_{today}.csv")
    xlsx_path = csv_path.replace(".csv", ".xlsx")

    result.to_csv(csv_path, index=False, encoding="utf-8-sig")
    result.to_excel(xlsx_path, index=False)
    print(f"\n💾 CSV:  {csv_path}")
    print(f"💾 XLSX: {xlsx_path}")


def print_table(result: pd.DataFrame, board_type: str):
    """美观打印"""
    label_map = {"industry": "行业板块", "concept": "概念板块"}
    label = label_map.get(board_type, board_type)

    print(f"\n{'='*90}")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"📊 {label}综合排名 Top-{len(result)}  |  {now}")
    print(f"   权重：资金流 {WEIGHT_FUND_FLOW*100:.0f}%  + 涨幅 {WEIGHT_CHANGE*100:.0f}%")
    print(f"{'='*90}")

    for _, row in result.iterrows():
        rank = int(row["综合排名"])
        flow_rank = int(row["资金流排名"])
        change_rank = int(row["涨幅排名"])
        name = row["行业"]
        change_pct = row["行业-涨跌幅"]
        net = row["净额"]
        leader = row["领涨股"]
        leader_chg = row["领涨股-涨跌幅"]

        bar_len = int(row["综合得分"] * 50)
        bar = "█" * bar_len + "░" * (50 - bar_len)

        change_display = f"+{change_pct:.2f}" if change_pct >= 0 else f"{change_pct:.2f}"
        leader_chg_disp = f"+{leader_chg:.2f}" if leader_chg >= 0 else f"{leader_chg:.2f}"
        print(f"  #{rank:>2}  {name:<10} | 资金流#{flow_rank:>2} 涨幅#{change_rank:>2} | "
              f"涨跌 {change_display:>7}% | 净额 {net:>8.2f}亿 | "
              f"领涨 {leader} ({leader_chg_disp}%)")
        print(f"        {bar} {row['综合得分']:.4f}")
    print(f"{'='*90}")


# ================================================================
#  主程序
# ================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A股板块综合排名（资金流+涨幅）")
    parser.add_argument("-t", "--type", choices=["industry", "concept"],
                        default="industry", help="板块类型：industry=行业, concept=概念")
    parser.add_argument("top_n", nargs="?", default=TOP_N, type=int, help="显示数量（默认10）")
    args = parser.parse_args()

    board_type = args.type
    top_n = args.top_n

    # 获取数据
    if board_type == "concept":
        df = fetch_concept_fund_flow()
    else:
        df = fetch_industry_fund_flow()

    result = rank_sectors(df, top_n=top_n)
    print_table(result, board_type)
    save_result(result, board_type)
