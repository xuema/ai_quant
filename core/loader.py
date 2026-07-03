import pandas as pd
import glob
import os
import json

# =========================
# 1️⃣ 公告数据加载
# =========================
def _load_ranking_csv(path: str) -> pd.DataFrame:
    """从 ranking CSV 加载公告数据。"""
    df = pd.read_csv(path, dtype={"code": str})
    # 确保 code 6 位
    df["code"] = df["code"].str.zfill(6)
    # 兼容：如果 CSV 没有 title 列但有 title
    col_map = {}
    if "title" not in df.columns and "name" in df.columns:
        df = df.rename(columns={"name": "title"})
    if "name" not in df.columns and "title" in df.columns:
        df.loc[:, "name"] = df["title"]
    return df


def _load_ranking_json(path: str, date_str: str) -> pd.DataFrame:
    """从 ranking JSON 加载公告数据 (旧格式兼容)。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    if "title" not in df.columns and "name" in df.columns:
        df["title"] = df["name"]
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(date_str)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df = df.dropna(subset=["code", "date", "score"])
    return df


def load_announcements(folder_path="data/raw_json"):
    """
    加载所有 ranking 文件（优先 .csv，兼容 .json 旧格式）。
    返回 DataFrame：[code, date, score, title, name, event_type, confidence, label, reason, holding_days]
    """

    csv_files = glob.glob(os.path.join(folder_path, "ranking_*.csv"))
    json_files = glob.glob(os.path.join(folder_path, "ranking_*.json"))

    all_data = []

    # 优先处理 CSV 文件
    for file in sorted(csv_files):
        basename = os.path.basename(file)
        date_str = basename.replace("ranking_", "").replace(".csv", "")
        df = _load_ranking_csv(file)
        if df.empty:
            continue
        if "date" not in df.columns:
            df["date"] = pd.to_datetime(date_str)
        elif pd.to_datetime(df["date"]).dt.year.max() < 2000:
            # date 列可能是 score 值而非日期
            df["date"] = pd.to_datetime(date_str)
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
        df = df.dropna(subset=["code", "score"])

        meta_cols = ["code", "date", "score"]
        extra_cols = [c for c in ["title", "name", "event_type", "confidence", "label", "reason", "holding_days"]
                       if c in df.columns]
        all_data.append(df[meta_cols + extra_cols])

    # 处理 JSON 文件（旧格式兼容），但跳过已有 CSV 的日期
    csv_dates = {os.path.basename(f).replace("ranking_", "").replace(".csv", "") for f in csv_files}
    for file in sorted(json_files):
        basename = os.path.basename(file)
        date_str = basename.replace("ranking_", "").replace(".json", "")
        if date_str in csv_dates:
            continue  # CSV 已覆盖此日期，跳过
        df = _load_ranking_json(file, date_str)
        if df.empty:
            continue

        meta_cols = ["code", "date", "score", "title"]
        extra_cols = [c for c in ["name", "event_type", "confidence", "label", "reason", "holding_days"]
                       if c in df.columns]
        all_data.append(df[meta_cols + extra_cols])

    if len(all_data) == 0:
        return pd.DataFrame(columns=["code", "date", "score", "title"])

    return pd.concat(all_data, ignore_index=True)


# =========================
# 2️⃣ 本地价格数据加载（你已有）
# =========================
def load_price_from_local(folder_path):

    files = glob.glob(os.path.join(folder_path, "*.csv"))

    all_data = []

    for file in files:

        code = os.path.basename(file).replace(".csv", "")

        try:
            df = pd.read_csv(file)

            # =========================
            # ✔ 处理异常首行
            # =========================
            try:
                if len(df) == 0:
                    print(f"⚠️ 空文件跳过: {code}")
                    continue

                if "000" in str(df.iloc[0].values):
                    df = df.iloc[1:]

            except Exception as e:
                print(f"⚠️ 首行处理异常 | code={code} | error={e}")
                continue

            # =========================
            # ✔ 列名统一
            # =========================
            if df.shape[1] < 6:
                print(f"⚠️ 列数不足 | code={code} | shape={df.shape}")
                continue

            df = df.iloc[:, :6]
            df.columns = ["date", "close", "high", "low", "open", "volume"]

            # =========================
            # ✔ 类型转换
            # =========================
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

            for col in ["close", "high", "low", "open", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # =========================
            # ✔ 删除异常数据
            # =========================
            before = len(df)

            df = df.dropna(subset=["date", "close"])

            after = len(df)

            if after == 0:
                print(f"⚠️ 全部为空 | code={code}")
                continue

            if before - after > 0:
                print(f"⚠️ 清理脏数据 | code={code} | drop={before-after}")

            df["code"] = code

            all_data.append(df[["code", "date", "close"]])

        except Exception as e:
            # =========================
            # ❌ 全局异常捕获
            # =========================
            print(f"❌ 读取失败 | code={code} | error={e}")
            continue

    if len(all_data) == 0:
        print("❌ 没有有效数据")
        return pd.DataFrame()

    price_data = pd.concat(all_data, ignore_index=True)

    price_data = price_data.sort_values(["code", "date"])

    print(f"✅ 成功加载股票数量: {price_data['code'].nunique()}")

    return price_data


def load_market_from_local(file_path):

    df = pd.read_csv(file_path)

    # 兼容常见指数格式
    df.columns = [c.lower() for c in df.columns]

    # 统一字段
    rename_map = {}

    if "close" in df.columns:
        rename_map["close"] = "mkt_close"

    df = df.rename(columns=rename_map)

    # 日期处理（兼容不同格式）
    if "date" not in df.columns:
        raise ValueError("market data must contain date column")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df = df.dropna(subset=["date"])

    # 只保留必要列
    if "mkt_close" in df.columns:
        df = df[["date", "mkt_close"]]
    else:
        raise ValueError("market data missing close column")

    df = df.sort_values("date")

    return df