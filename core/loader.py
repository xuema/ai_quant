import pandas as pd
import glob
import os
import json

# =========================
# 1️⃣ 公告数据加载
# =========================
def load_announcements(folder_path="data/raw_json"):

    files = glob.glob(os.path.join(folder_path, "ranking_*.json"))

    all_data = []

    for file in files:

        # 提取日期
        filename = os.path.basename(file)
        date_str = filename.replace("ranking_", "").replace(".json", "")

        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)

        df = pd.DataFrame(data)

        # ✔ 标准字段
        # 你当前JSON里是 name / title 混用 → 统一
        if "title" not in df.columns and "name" in df.columns:
            df["title"] = df["name"]

        # ✔ code统一
        df["code"] = df["code"].astype(str).str.zfill(6)

        # ✔ 日期
        df["date"] = pd.to_datetime(date_str)

        # ✔ score（确保是float）
        df["score"] = pd.to_numeric(df["score"], errors="coerce")

        df = df.dropna(subset=["code", "date", "score"])

        all_data.append(df[["code", "date", "score", "title"]])

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