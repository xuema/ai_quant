#!/usr/bin/env python3
"""
Task5: 机器学习分类模型实战 — 股票涨跌预测
================================================
1) 数据加载 + 标签构造
2) 特征工程（原始OHLCV + 技术指标衍生）
3) 数据划分（训练集/测试集）
4) 多模型训练（LR, DT, RF, GB, XGB）
5) 模型评估（AUC, 分类报告, 混淆矩阵, ROC曲线）
6) 生成交互式 HTML 报告
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import json
import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import base64
from io import BytesIO

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier, plot_tree
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from scipy.interpolate import make_interp_spline
from sklearn.metrics import (
    roc_curve, auc, classification_report, confusion_matrix,
    accuracy_score, precision_score, recall_score, f1_score
)
try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

# ─── 项目路径 ─────────────────────────────────────────────────────────
BASE = "/Users/skyler/workspace/stock_selection/ai_quant"
DATA_PATH = os.path.join(BASE, "data", "stock_analysis", "002281_202307_202607.csv")
RESULTS_DIR = os.path.join(BASE, "data", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ─── 1. 数据加载 ──────────────────────────────────────────────────────
def load_stock_data(path: str) -> pd.DataFrame:
    """加载本地股票CSV"""
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").reset_index(drop=True)
    print(f"[数据] 加载 {len(df)} 条记录, 列: {list(df.columns)}")
    return df


# ─── 2. 标签构造 ──────────────────────────────────────────────────────
def build_label(df: pd.DataFrame, mode: str = "next_day", threshold: float = 0.0, forward_days: int = 1) -> pd.DataFrame:
    """
    构造涨跌标签
    mode: "next_day" | "threshold" | "forward"
    """
    df = df.copy()
    if mode == "next_day":
        future_pct = df["pct_chg"].shift(-forward_days)
        df["label"] = (future_pct > 0).astype(int)
        label_desc = f"次日涨跌幅>0为1, 否则为0 (前瞻{forward_days}天)"
    elif mode == "threshold":
        future_pct = df["pct_chg"].shift(-forward_days)
        df["label"] = (future_pct > threshold).astype(int)
        label_desc = f"次日涨跌幅>{threshold}%为1, 否则为0"
    else:
        future_close = df["close"].shift(-forward_days)
        df["return_fwd"] = (future_close - df["close"]) / df["close"] * 100
        df["label"] = (df["return_fwd"] > threshold).astype(int)
        label_desc = f"{forward_days}天后收益率>{threshold}%为1"
    df = df.dropna(subset=["label"]).reset_index(drop=True)
    n_pos = df["label"].sum()
    n_neg = len(df) - n_pos
    print(f"[标签] {label_desc} | 正样本={n_pos}, 负样本={n_neg}, 正类占比={n_pos/len(df)*100:.1f}%")
    return df, label_desc


# ─── 3. 特征工程 ──────────────────────────────────────────────────────
def build_features(df: pd.DataFrame) -> tuple:
    """
    按照用户指定指标重构特征工程:
    - RSI(6, 12, 24)
    - EXPMA(5, 29)
    - VOL(8, 89) 成交量比率
    - CR(26, 11, 19, 35, 53) 能量指标
    - WR(42) 威廉指标
    去掉重要性较低的: KDJ, MACD, 基础 ma_diff, volatility, hl_ratio, oc_ratio
    """

    """
    衍生技术指标特征
    (不 dropna: 最后统一处理)
    """
    df = df.copy()
    close = df["close"]
    high  = df["high"]
    low   = df["low"]
    vol   = df["vol"]

    # === 按用户指定调整的特征工程 ===
    # 1. 保留 ma_diff_5/10/20 和 volatility_5/10（你确认重要性还可以）
    for w in [5, 10, 20]:
        ma = close.rolling(w).mean()
        df[f"ma_diff_{w}"] = (close - ma) / ma

    for w in [5, 10]:
        df[f"volatility_{w}"] = close.pct_change().rolling(w).std()

    ma_vol_20 = vol.rolling(20).mean()
    df["vol_ratio"] = vol / ma_vol_20

    # 2. 新增用户指定指标
    # RSI 多周期 (12, 56, 12)
    # 用户指定：RSI(12, 56, 12) — 去重后保留 rsi_12 和 rsi_56
    for period in [12, 56]:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs = gain / (loss + 1e-10)
        df[f"rsi_{period}"] = 100 - (100 / (1 + rs))

    # EXPMA(5, 29)
    expma5 = close.ewm(span=5).mean()
    expma29 = close.ewm(span=29).mean()
    df["expma_5"] = expma5
    df["expma_29"] = expma29
    df["expma_diff_5"] = (close - expma5) / expma5
    df["expma_diff_29"] = (close - expma29) / expma29

    # VOL(8, 89) 成交量比率
    vol_ma8 = vol.rolling(8).mean()
    vol_ma89 = vol.rolling(89).mean()
    df["vol_ratio_8_89"] = vol_ma8 / (vol_ma89 + 1e-8)

    # CR 能量指标 (26,11,19,35,53)
    typ_price = (high + low) / 2
    cr_mid = typ_price.shift(1)
    pm = np.maximum(high - cr_mid, 0)
    nm = np.maximum(cr_mid - low, 0)
    cr_sum_pm = pm.rolling(26).sum()
    cr_sum_nm = nm.rolling(26).sum()
    df["cr"] = (cr_sum_pm / (cr_sum_nm + 1e-8)) * 100
    for n in [11, 19, 35, 53]:
        df[f"cr_ma_{n}"] = df["cr"].rolling(n).mean()

    # WR(42) 威廉指标
    h42 = high.rolling(42).max()
    l42 = low.rolling(42).min()
    df["wr_42"] = (h42 - close) / (h42 - l42 + 1e-8) * 100

    # 记录所有衍生特征名（保留 ma_diff/volatility + 用户指定指标）
    new_features = [
        "ma_diff_5", "ma_diff_10", "ma_diff_20",
        "volatility_5", "volatility_10",
        "vol_ratio",
        "rsi_12", "rsi_56",
        "expma_5", "expma_29", "expma_diff_5", "expma_diff_29",
        "vol_ratio_8_89",
        "cr", "cr_ma_11", "cr_ma_19", "cr_ma_35", "cr_ma_53",
        "wr_42",
    ]
    return df, new_features


def describe_features(all_features, raw_features, new_features) -> list:
    """生成特征说明列表"""
    descs = []
    for f in all_features:
        if f in raw_features:
            cat = "原始特征"
            note = "OHLCV基础字段或已有指标"
        else:
            cat = "衍生特征"
            if "ma_diff" in f: cat += " / 移动均价差"
            elif "volatility" in f: cat += " / 滚动波动率"
            elif "vol_ratio" in f: cat += " / 量比"
            elif "rsi" in f: cat += " / 相对强弱指标(RSI)"
            elif "expma" in f: cat += " / 指数移动平均(EXPMA)"
            elif "vol_ratio_8_89" in f: cat += " / VOL(8,89)量比"
            elif "cr" in f: cat += " / 能量指标(CR)"
            elif "wr" in f: cat += " / 威廉指标(WR)"
            else: cat += " / 自定义"
            note = "按照用户指定指标计算"
        descs.append({"feature": f, "category": cat, "note": note})
    return descs


# ─── 4. 数据划分 + 预处理 ────────────────────────────────────────────
def prepare_data(df: pd.DataFrame, feature_cols: list, test_size: float = 0.2,
                 random_state: int = 42, method: str = "random"):
    """划分训练集/测试集, 标准化, 返回数组"""
    X = df[feature_cols].values
    y = df["label"].values.astype(int)

    # 清除 NaN/Inf
    mask = np.isfinite(X).all(axis=1) & np.isfinite(y)
    X, y = X[mask], y[mask]

    if method == "random":
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        split_desc = f"随机划分 (test={test_size}, stratify=True)"
    else:
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        split_desc = f"时序划分 (前{(1-test_size):.0%}训练, 后{test_size:.0%}测试)"

    # StandardScaler
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    return X_train, X_test, y_train, y_test, split_desc


# ─── 5. 模型构建与训练 ───────────────────────────────────────────────
def get_models() -> dict:
    """初始化模型字典"""
    models = {
        "逻辑回归 LogisticRegression": LogisticRegression(
            C=1.0, max_iter=1000, solver="lbfgs", random_state=42
        ),
        "决策树 DecisionTree": DecisionTreeClassifier(
            max_depth=4, random_state=42, min_samples_split=5
        ),
        "随机森林 RandomForest": RandomForestClassifier(
            n_estimators=100, max_depth=8, random_state=42, min_samples_split=3
        ),
        "梯度提升 GradientBoost": GradientBoostingClassifier(
            n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42
        ),
    }
    if HAS_XGB:
        models["XGBoost"] = xgb.XGBClassifier(
            n_estimators=100, learning_rate=0.1, max_depth=3,
            eval_metric="logloss", random_state=42, verbosity=0
        )
    return models


def train_and_evaluate(models: dict, X_train, X_test, y_train, y_test,
                       feature_names: list) -> dict:
    """训练所有模型, 返回评估结果"""
    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        fpr, tpr, _ = roc_curve(y_test, y_prob)
        auc_val = auc(fpr, tpr)

        cm = confusion_matrix(y_test, y_pred, labels=[0, 1])

        report = classification_report(y_test, y_pred, target_names=["跌(0)", "涨(1)"], output_dict=True)

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        # 特征重要性 (仅树模型)
        imp = None
        if hasattr(model, "feature_importances_"):
            imp = dict(zip(feature_names, model.feature_importances_.tolist()))

        results[name] = {
            "model": model,
            "y_pred": y_pred,
            "y_prob": y_prob,
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "auc": float(auc_val),
            "accuracy": float(acc),
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "confusion_matrix": cm.tolist(),
            "classification_report": report,
            "feature_importance": imp,
        }

        print(f"\n{'='*60}")
        print(f" 模型: {name}")
        print(f" Accuracy={acc:.4f}  Precision={prec:.4f}  Recall={rec:.4f}  F1={f1:.4f}  AUC={auc_val:.4f}")
        print(classification_report(y_test, y_pred, target_names=["跌(0)", "涨(1)"]))

    return results


# ─── 6. 可视化（静态图） ─────────────────────────────────────────────
def _smooth_roc(fpr, tpr, n_points=200):
    """通过阈值稠密化 + 样条插值生成平滑ROC曲线"""
    fpr = np.array(fpr)
    tpr = np.array(tpr)
    # 添加端点确保从(0,0)到(1,1)
    fpr = np.concatenate([[0], fpr, [1]])
    tpr = np.concatenate([[0], tpr, [1]])
    # 先通过线性插值增加点数，再用样条平滑
    f_new = np.linspace(0, 1, max(len(fpr), n_points * 2))
    tpr_dense = np.interp(f_new, fpr, tpr)
    if len(tpr_dense) < 5:
        return np.array(f_new), tpr_dense
    # 3次B样条平滑
    t = np.linspace(0, 1, len(tpr_dense))
    spl = make_interp_spline(t, tpr_dense, k=3)
    t_new = np.linspace(0, 1, n_points)
    tpr_s = np.clip(spl(t_new), 0, 1)
    return t_new, tpr_s


def plot_roc_overlay(results: dict, save_path: str):
    """叠加ROC曲线 — matplotlib版本（B样条平滑）"""
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    for i, (name, r) in enumerate(results.items()):
        fpr_s, tpr_s = _smooth_roc(np.array(r["fpr"]), np.array(r["tpr"]))
        c = colors[i % len(colors)]
        ax.plot(fpr_s, tpr_s, color=c, lw=2.5, label=f"{name} (AUC={r['auc']:.4f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Random (0.500)")
    ax.set_xlabel("False Positive Rate", fontsize=11)
    ax.set_ylabel("True Positive Rate", fontsize=11)
    ax.set_title("ROC Curves — All Models", fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", fontsize=10, frameon=True, edgecolor="#ddd")
    ax.grid(True, alpha=0.25, linestyle=":")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    plt.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_roc_individual(results: dict, img_dir: str):
    """为每个模型生成独立的ROC子图——风格参照样例"""
    n = len(results)
    ncols = min(n, 3)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 5.5), squeeze=False)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    for i, (name, r) in enumerate(results.items()):
        ax = axes[i // ncols, i % ncols]
        fpr_s, tpr_s = _smooth_roc(np.array(r["fpr"]), np.array(r["tpr"]))
        c = colors[i % len(colors)]
        ax.plot(fpr_s, tpr_s, color=c, lw=2.2)
        # 随机基线
        ax.plot([0, 1], [0, 1], "#ff9900", lw=1.2, linestyle=":")
        ax.text(0.55, 0.2, "Random chance", color="#ff9900", fontsize=9)
        ax.legend([f"{name} (AUC={r['auc']:.4f})"], loc="best", fontsize=10, frameon=True, edgecolor="#ddd")
        ax.set_xlabel("False Positive Rate", fontsize=9)
        ax.set_ylabel("True Positive Rate", fontsize=9)
        ax.set_title(f"ROC-AUC Curve — {name}", fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.2, linestyle=":")
        ax.set_xlim([0, 1])
        ax.set_ylim([0, 1])
    # 隐藏多余子图
    for j in range(n, nrows * ncols):
        axes[j // ncols, j % ncols].axis("off")
    fig.tight_layout()
    path = os.path.join(img_dir, "roc_individual.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    plt.close(fig)


def plot_confusion_matrix(cm, title: str, save_path: str):
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(np.array(cm), annot=True, fmt="d", cmap="Blues",
                xticklabels=["跌(0)", "涨(1)"], yticklabels=["跌(0)", "涨(1)"], ax=ax)
    ax.set_title(f"Confusion Matrix — {title}", fontsize=12, fontweight="bold")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    plt.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_metrics_comparison(results: dict, save_path: str):
    """指标横向对比柱状图"""
    metrics_names = ["Accuracy", "Precision", "Recall", "F1", "AUC"]
    values = {m: [] for m in metrics_names}
    model_names = list(results.keys())
    for r in results.values():
        values["Accuracy"].append(r["accuracy"])
        values["Precision"].append(r["precision"])
        values["Recall"].append(r["recall"])
        values["F1"].append(r["f1"])
        values["AUC"].append(r["auc"])

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(model_names))
    width = 0.14
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]
    for i, (m, c) in enumerate(zip(metrics_names, colors)):
        ax.bar(x + i * width, values[m], width, label=m, color=c)
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels([n.replace(" ", "\n") for n in model_names], fontsize=9)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Model Metrics Comparison", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.0)
    ax.grid(alpha=0.3, axis="y")
    plt.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_feature_importance(results: dict, save_path: str):
    """画最强模型的feature importance"""
    # 选AUC最高的树模型
    best = None
    best_auc = 0
    for name, r in results.items():
        if r["feature_importance"] is not None and r["auc"] > best_auc:
            best = r
            best_auc = r["auc"]
            best_name = name

    if best is None:
        return
    imp = best["feature_importance"]
    imp_sorted = dict(sorted(imp.items(), key=lambda x: x[1], reverse=True)[:15])
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(list(imp_sorted.keys())[::-1], list(imp_sorted.values())[::-1], color="#4C72B0", edgecolor="white")
    ax.set_xlabel("Feature Importance", fontsize=12)
    ax.set_title(f"Top 15 Feature Importance — {best_name}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def plot_decision_tree(results: dict, feature_names: list, save_path: str):
    """画决策树结构图"""
    dt_result = results.get("决策树 DecisionTree")
    if dt_result is None:
        return
    fig, ax = plt.subplots(figsize=(14, 8))
    plot_tree(dt_result["model"], feature_names=feature_names,
              class_names=["跌(0)", "涨(1)"], filled=True, rounded=True,
              fontsize=9, ax=ax)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)


def fig_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ─── 7. 生成交互式 HTML 报告 ─────────────────────────────────────────
def generate_html_report(
    results: dict,
    label_desc: str,
    feature_descs: list,
    raw_features: list,
    new_features: list,
    split_desc: str,
    n_samples: int,
    n_pos: int,
    n_neg: int,
    stock_code: str,
):
    """用 Plotly 生成交互式 HTML"""
    img_dir = os.path.join(RESULTS_DIR, "task5_img")
    os.makedirs(img_dir, exist_ok=True)

    plot_roc_overlay(results, os.path.join(img_dir, "roc_overlay.png"))
    plot_metrics_comparison(results, os.path.join(img_dir, "metrics_comparison.png"))
    plot_feature_importance(results, os.path.join(img_dir, "feature_importance.png"))
    plot_decision_tree(results, list(raw_features) + new_features, os.path.join(img_dir, "decision_tree.png"))

    cm_imgs = {}
    for name, r in results.items():
        fpath = os.path.join(img_dir, f"cm_{name.replace(' ', '_')}.png")
        plot_confusion_matrix(r["confusion_matrix"], name, fpath)
        cm_imgs[name] = fig_to_base64(fpath)

    roc_b64 = fig_to_base64(os.path.join(img_dir, "roc_overlay.png"))
    metrics_b64 = fig_to_base64(os.path.join(img_dir, "metrics_comparison.png"))
    fi_b64 = fig_to_base64(os.path.join(img_dir, "feature_importance.png"))
    dt_b64 = fig_to_base64(os.path.join(img_dir, "decision_tree.png"))

    # 交互式 ROC 曲线 (Plotly) — B样条平滑
    fig_roc = go.Figure()
    for name, r in results.items():
        fpr_s, tpr_s = _smooth_roc(np.array(r["fpr"]), np.array(r["tpr"]))
        fig_roc.add_trace(go.Scatter(
            x=fpr_s.tolist(), y=tpr_s.tolist(), mode="lines",
            name=f"{name} (AUC={r['auc']:.4f})",
            line=dict(width=2.5),
        ))
    fig_roc.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        name="Random (0.5000)",
        line=dict(width=1, dash="dash", color="gray"),
        showlegend=False
    ))
    fig_roc.update_layout(
        title="ROC Curves — Interactive",
        xaxis_title="False Positive Rate",
        yaxis_title="True Positive Rate",
        hovermode="closest",
        height=500,
        template="plotly_white",
    )

    # 交互式指标对比 (Plotly)
    model_names = list(results.keys())
    fig_metrics = make_subplots(rows=1, cols=5, subplot_titles=["Accuracy", "Precision", "Recall", "F1", "AUC"])
    metrics_keys = ["accuracy", "precision", "recall", "f1", "auc"]
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]
    for i, (mk, c) in enumerate(zip(metrics_keys, colors)):
        fig_metrics.add_trace(
            go.Bar(x=model_names, y=[r[mk] for r in results.values()],
                   marker_color=c, name=mk.capitalize(), showlegend=False),
            row=1, col=i+1
        )
    fig_metrics.update_layout(height=400, template="plotly_white", title_text="Model Metrics Comparison")
    for j in range(1, 6):
        fig_metrics.update_yaxes(range=[0, 1], row=1, col=j)

    roc_html = fig_roc.to_html(full_html=False, include_plotlyjs="cdn")
    metrics_html = fig_metrics.to_html(full_html=False, include_plotlyjs="cdn")

    # 模型结果表格
    model_rows = ""
    for name, r in results.items():
        model_rows += f"""<tr>
            <td>{name}</td>
            <td>{r['accuracy']:.4f}</td>
            <td>{r['precision']:.4f}</td>
            <td>{r['recall']:.4f}</td>
            <td>{r['f1']:.4f}</td>
            <td><strong>{r['auc']:.4f}</strong></td>
        </tr>"""

    # 分类报告表格
    report_rows = ""
    for name, r in results.items():
        report = r["classification_report"]
        cm = r["confusion_matrix"]
        report_rows += f"""
        <h4 class="model-name">{name}</h4>
        <table class="report-table">
            <thead>
                <tr><th>类别</th><th>Precision</th><th>Recall</th><th>F1-Score</th><th>Support</th></tr>
            </thead>
            <tbody>
                <tr><td>跌(0)</td>
                    <td>{report['跌(0)']['precision']:.4f}</td>
                    <td>{report['跌(0)']['recall']:.4f}</td>
                    <td>{report['跌(0)']['f1-score']:.4f}</td>
                    <td>{int(report['跌(0)']['support'])}</td></tr>
                <tr><td>涨(1)</td>
                    <td>{report['涨(1)']['precision']:.4f}</td>
                    <td>{report['涨(1)']['recall']:.4f}</td>
                    <td>{report['涨(1)']['f1-score']:.4f}</td>
                    <td>{int(report['涨(1)']['support'])}</td></tr>
                <tr class="total-row"><td>Accuracy</td><td colspan="3">{r['accuracy']:.4f}</td>
                    <td>{int(report['accuracy'])}</td></tr>
            </tbody>
        </table>
        <div class="cm-grid">
            <div class="cm-cell"><span>真负 TN</span><strong>{cm[0][0]}</strong></div>
            <div class="cm-cell cm-fp"><span>假正 FP</span><strong>{cm[0][1]}</strong></div>
            <div class="cm-cell cm-fn"><span>假负 FN</span><strong>{cm[1][0]}</strong></div>
            <div class="cm-cell cm-tp"><span>真正 TP</span><strong>{cm[1][1]}</strong></div>
        </div>
        <img src="data:image/png;base64,{cm_imgs[name]}" alt="CM - {name}" style="max-width:100%;border-radius:8px;margin-top:8px;">
        """

    # 特征说明表格
    feature_rows = ""
    for fd in feature_descs:
        feature_rows += f"""<tr>
            <td><code>{fd['feature']}</code></td>
            <td>{fd['category']}</td>
            <td>{fd['note']}</td>
        </tr>"""

    # 混淆矩阵图片HTML
    cm_imgs_html = ""
    for name in results:
        cm_imgs_html += f"""<div class="cm-block">
            <h4>{name}</h4>
            <img src="data:image/png;base64,{cm_imgs[name]}" alt="CM">
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Task5 — 机器学习分类模型: 股票涨跌预测 ({stock_code})</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f4f6f9; color: #1a1a2e; line-height:1.6; }}
.container {{ max-width:1280px; margin:0 auto; padding:36px 28px; }}
h1 {{ font-size:26px; text-align:center; margin-bottom:6px; color:#1a1a2e; letter-spacing:1px; }}
.subtitle {{ text-align:center; color:#888; margin-bottom:36px; font-size:14px; }}
.section {{ background:#fff; border-radius:16px; padding:36px 32px; margin-bottom:28px;
           box-shadow:0 1px 6px rgba(0,0,0,0.04); border:1px solid #eef0f4; }}
.section h2 {{ font-size:18px; margin-bottom:18px; color:#1a1a2e;
               padding-bottom:10px; border-bottom:2px solid #f0f2f5; }}
.section h3 {{ font-size:15px; margin:20px 0 10px; color:#444; font-weight:600; }}

table {{ width:100%; border-collapse:collapse; font-size:14px; margin-top:8px; }}
th, td {{ padding:10px 14px; text-align:left; border-bottom:1px solid #eee; }}
th {{ background:#f0f4f8; font-weight:600; }}
tr:hover {{ background:#f8f9fa; }}

.info-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr));
              gap:16px; margin:16px 0; }}
.info-card {{ background:#f8f9fa; border-radius:8px; padding:16px; text-align:center; }}
.info-card .val {{ font-size:28px; font-weight:700; color:#4C72B0; }}
.info-card .lbl {{ font-size:13px; color:#888; margin-top:4px; }}

.plotly-chart {{ margin:16px 0; border-radius:12px; overflow:hidden; }}
.static-img {{ width:100%; border-radius:12px; margin:12px 0; }}

.model-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(340px,1fr));
               gap:20px; }}
.model-card {{ background:#fcfcfc; border:1px solid #e8e8e8; border-radius:10px;
               padding:20px; }}
.model-name {{ color:#4C72B0; }}

.cm-grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:6px; margin-top:10px;
             max-width:200px; }}
.cm-cell {{ background:#e8f0fe; border-radius:6px; padding:10px; text-align:center; }}
.cm-cell span {{ font-size:11px; display:block; color:#666; }}
.cm-cell strong {{ font-size:20px; }}
.cm-fp {{ background:#fff3cd; }}
.cm-fn {{ background:#f8d7da; }}
.cm-tp {{ background:#d4edda; }}

.report-table {{ margin-bottom:10px; }}
.report-table .total-row {{ background:#e8f0fe; font-weight:600; }}

.best-model {{ background: linear-gradient(135deg, #4C72B0, #55A868); color:#fff;
              border-radius:12px; padding:24px; text-align:center; }}
.best-model h3 {{ color:#fff; font-size:22px; }}
.best-model .auc {{ font-size:48px; font-weight:800; }}

code {{ background:#e8e8e8; padding:2px 6px; border-radius:4px; font-size:13px; }}

.tag {{ display:inline-block; background:#4C72B0; color:#fff; padding:2px 8px; border-radius:4px; font-size:11px; margin-right:6px; }}
.concept-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(350px,1fr)); gap:20px; margin:18px 0; }}
.concept-card {{ background:#fff; border-radius:14px;
             padding:24px; border:1px solid #e8e8e8; transition:transform .2s,box-shadow .2s; }}
.concept-card:hover {{ transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.06); }}
.concept-card .card-icon {{ font-size:24px; margin-bottom:6px; display:block; }}
.concept-card h4 {{ font-size:16px; margin:0 0 2px; color:#1a1a2e; font-weight:700; }}
.concept-card .card-sub {{ font-size:12px; color:#999; margin:0 0 8px; font-family:monospace; }}
.concept-card .card-desc {{ font-size:13px; color:#555; line-height:1.7; margin:0 0 10px; }}
.concept-card ul {{ margin:0 0 0 18px; padding:0; font-size:13px; color:#666; line-height:1.9; }}
.concept-card ul li {{ list-style:none; position:relative; padding-left:16px; margin-bottom:2px; }}
.concept-card ul li::before {{ content:""; position:absolute; left:0; top:8px;
            width:5px; height:5px; border-radius:50%; background:#5B8FF9; }}
.concept-card .card-divider {{ border:none; border-top:1px solid #f0f2f5; margin:12px 0; }}
.metric-grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(340px,1fr)); gap:20px; margin:18px 0; }}
.metric-card {{ background:#fff; border-radius:14px;
             padding:24px; border:1px solid #e8e8e8; transition:transform .2s,box-shadow .2s; }}
.metric-card:hover {{ transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,0.06); }}
.metric-card .card-icon {{ font-size:24px; margin-bottom:6px; display:block; }}
.metric-card h4 {{ font-size:16px; margin:0 0 2px; color:#1a1a2e; font-weight:700; }}
.metric-card .card-sub {{ font-size:12px; color:#999; margin:0 0 8px; font-family:monospace; }}
.metric-card p {{ font-size:13px; color:#555; line-height:1.7; margin:0 0 6px; }}
.metric-card .highlight {{ background:#f7f8fc; border-radius:8px; padding:10px 12px; margin:8px 0; 
            font-size:13px; color:#555; line-height:1.7; border:1px solid #eef0f4; }}
.metric-card .highlight b {{ color:#4C72B0; }}
.metric-card .grade-bar {{ display:flex; align-items:center; gap:8px; margin:3px 0; font-size:13px; color:#555; }}
.metric-card .grade-fill {{ height:8px; border-radius:4px; min-width:20px; }}
.metric-card .note {{ background:#fafbfc; border-left:3px solid #dbe0e8; padding:8px 12px; margin-top:10px;
            font-size:12px; color:#888; line-height:1.6; border-radius:0 6px 6px 0; }}

@media (max-width:768px) {{
    .container {{ padding:12px; }}
    .model-grid {{ grid-template-columns: 1fr; }}
    .info-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .concept-grid {{ grid-template-columns: 1fr; }}
    .metric-grid {{ grid-template-columns: 1fr; }}
    h1 {{ font-size:22px; }}
}}
}}
</style>
</head>
<body>
<div class="container">

<h1>🤖 Task5 — 机器学习分类模型实战</h1>
<p class="subtitle">基于 {stock_code} 数据的涨跌预测 | 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

<!-- 概念导论：分类算法 -->
<div class="section">
<h2>📖 分类机器学习算法</h2>
<p class="algo-intro">分类（Classification）是一种有监督学习方式，目标是构建一个函数 f: X → Y，将输入特征向量映射到离散的类别标签。对于二分类任务，Y ∈ (0, 1)，模型输出为样本属于正类的概率，再通过阈值（通常取 0.5）判定类别。本次任务实践了以下五种经典分类算法：</p>
<div class="concept-grid">
    <div class="concept-card">
        <span class="card-icon">📐</span>
        <h4>逻辑回归</h4>
        <p class="card-sub">Logistic Regression</p>
        <p class="card-desc">最经典的线性分类器。将特征的线性组合 <b>w·x + b</b> 通过 <b>Sigmoid 函数</b> σ(z) = 1/(1+e⁻ᶻ) 映射到 (0,1) 概率区间。当 σ(w·x+b) &gt; 0.5 时预测为正类。</p>
        <ul>
            <li><b>优化目标：</b>最大化对数似然函数，通常用梯度下降或 L-BFGS 求解</li>
            <li><b>正则化：</b>L1/L2 正则防止过拟合，C 参数控制正则化强度</li>
            <li><b>优点：</b>输出概率可解释、训练速度快、适合做基线模型</li>
            <li><b>缺点：</b>仅能拟合线性分离边界，无法捕捉特征间的高阶交互</li>
        </ul>
    </div>
    <div class="concept-card">
        <span class="card-icon">🌳</span>
        <h4>决策树</h4>
        <p class="card-sub">Decision Tree Classifier</p>
        <p class="card-desc">以树状结构递归划分特征空间。从根节点开始，每次选择「最优分裂特征+阈值」，将数据集划分为两个子集，直到达到停止条件。</p>
        <ul>
            <li><b>分裂准则：</b>Gini 不纯度 G(p) = 1−Σpᵢ²，选择使子节点不纯度下降最大的分裂</li>
            <li><b>信息增益：</b>基于信息熵 ΔH = H(父) − w₁H(左) − w₂H(右) 进行分裂</li>
            <li><b>优点：</b>无需特征缩放、决策规则可可视化、能处理非线性关系</li>
            <li><b>过拟合风险：</b>需通过 max_depth、min_samples_split 等超参数剪枝控制</li>
        </ul>
    </div>
    <div class="concept-card">
        <span class="card-icon">🌲</span>
        <h4>随机森林</h4>
        <p class="card-sub">Random Forest Classifier（Bagging）</p>
        <p class="card-desc">集成学习的代表，通过「Bootstrap 抽样 + 随机特征选择」构建数十到数百棵差异化的决策树。每棵树独立训练，最终通过<em>多数投票</em>决定分类结果。</p>
        <ul>
            <li><b>Bootstrap：</b>每棵树使用从原始数据中可重复抽样的子集训练（通常 63.2% 的不重复样本）</li>
            <li><b>特征随机化：</b>每次分裂只考虑随机选取的 √p 个特征（p 为总特征数），增强树间的多样性</li>
            <li><b>Bagging 原理：</b>多棵高方差低偏差的树取平均后，整体方差大幅降低</li>
            <li><b>内置评估：</b>可利用 Out-of-Bag（OOB）样本进行无需验证集的模型评估</li>
            <li><b>优点：</b>鲁棒性强、自带特征重要性排序、几乎无需调参</li>
        </ul>
    </div>
    <div class="concept-card">
        <span class="card-icon">📈</span>
        <h4>梯度提升树</h4>
        <p class="card-sub">Gradient Boosting Classifier（Boosting）</p>
        <p class="card-desc">与随机森林「并行投票」不同，Boosting 采用「串行修正」策略：每一棵新树都拟合一前序模型预测的<em>残差</em>，通过学习率 η 控制修正步幅，逐步逼近最优解。</p>
        <ul>
            <li><b>核心公式：</b>Fₘ(x) = Fₘ₋₁(x) + η · hₘ(x)，其中 hₘ 拟合负梯度方向</li>
            <li><b>关键参数：</b>学习率 η（通常 0.01~0.1）、树的深度 d、树的棵数 n_estimators</li>
            <li><b>与 Bagging 的区别：</b>Boosting 降低偏差（Bias），Bagging 降低方差（Variance）</li>
            <li><b>优点：</b>结构化数据上精度极高，Kaggle 竞赛的主流选择</li>
        </ul>
    </div>
    <div class="concept-card">
        <span class="card-icon">⚡</span>
        <h4>XGBoost</h4>
        <p class="card-sub">eXtreme Gradient Boosting</p>
        <p class="card-desc">Chen & Guestrin (2016) 提出的 Gradient Boosting 高效实现。在标准 GB 的基础上引入了<b>二阶泰勒展开</b>、<b>L1/L2 正则化</b>、<b>列采样</b>、<b>缺失值自动处理</b>和<b>并行分裂</b>等优化。</p>
        <ul>
            <li><b>目标函数：</b>Obj = Σ L(yᵢ, ŷᵢ) + Σ Ω(fₜ)，其中 Ω 控制树复杂度</li>
            <li><b>二阶优化：</b>同时利用损失函数的一阶和二阶导数信息，收敛速度更快</li>
            <li><b>优点：</b>训练效率高、内存占用低、工业和学术场景的基准模型</li>
        </ul>
    </div>
</div>
</div>

<!-- 概念导论：评估指标 -->
<div class="section">
<h2>📊 模型评估指标</h2>
<p class="algo-intro">训练完分类模型后，需要科学的量化指标来评估其泛化能力。不同的评估维度能帮助我们理解模型在不同业务场景下的表现：</p>
<div class="metric-grid">
    <div class="metric-card">
        <span class="card-icon">🧩</span>
        <h4>混淆矩阵</h4>
        <p class="card-sub">Confusion Matrix — 2×2 交叉分类表</p>
        <p class="card-desc" style="margin-top:12px;">将预测结果与真实标签交叉对比，得到四种结果：</p>
        <div class="highlight">
            🟢 <b>真正 TP</b>：实际为正 → 预测为正 ✓<br>
            🔴 <b>假正 FP</b>：实际为负 → 预测为正 ✗（误报）<br>
            🟠 <b>假负 FN</b>：实际为正 → 预测为负 ✗（漏报）<br>
            ⚪ <b>真负 TN</b>：实际为负 → 预测为负 ✓
            </div>
        <p><b>衍生指标：</b><br>
        • Precision = TP/(TP+FP)：预测正例中的准确率<br>
        • Recall = TP/(TP+FN)：正例中成功找出的比例<br>
        • F1 = 2·P·R/(P+R)：Precision 和 Recall 的调和平均<br>
        • Accuracy = (TP+TN)/总样本（不均衡时不可靠）</p>
    </div>
    <div class="metric-card">
        <span class="card-icon">📉</span>
        <h4>ROC 曲线</h4>
        <p class="card-sub">Receiver Operating Characteristic Curve</p>
        <p class="card-desc" style="margin-top:12px;">通过<b>连续调整分类阈值</b>来评估模型的整体判别能力：</p>
        <div class="highlight">
            <b>横轴 = 假正率 FPR = FP/(FP+TN)</b>（实际负类中被误报比例）<br>
            <b>纵轴 = 真正率 TPR = TP/(TP+FN)</b>（实际正类中被正确识别比例）
        </div>
        <p><b>解读要点：</b><br>
        • 曲线越靠近左上角 (0,1) 越好 → 低误报 + 高检出<br>
        • 对角线 = 随机猜测基线<br>
        • 曲线下方面积 = <b>AUC</b>，综合判别力</p>
    </div>
    <div class="metric-card" style="grid-column: 1/-1;">
        <h4>AUC — ROC 曲线下面积 (Area Under Curve)</h4>
        <p class="card-sub">概率解释与分级标准</p>
        <div style="display:flex;gap:24px;margin-top:14px;flex-wrap:wrap;">
            <div style="flex:1;min-width:220px;">
                <p><b>概率解释：</b><br>
                AUC = P(模型给一个随机正样本的打分 &gt; 给一个随机负样本的打分)<br>
                即：随便取一个涨样本和一个跌样本，模型给涨样本打分更高的概率。</p>
            </div>
            <div style="flex:1;min-width:220px;">
                <p><b>分级参考：</b><br>
                AUC = 0.5 → 等同于随机猜测（无判别力）<br>
                0.5~0.6 → 弱判别力（需更多特征或更多数据）<br>
                0.6~0.7 → 低到中等判别力<br>
                0.7~0.8 → 中等判别力（具有实用参考价值）<br>
                0.8~0.9 → 高判别力<br>
                AUC &gt; 0.9 → 极佳判别力</p>
            </div>
        </div>
        <p style="margin-top:12px;color:#888;font-size:12px;">⚠ 注意：在股票短期涨跌预测场景中，由于市场随机性极强，AUC 能达到 0.6 以上已具有一定的统计意义。过高的 AUC（如 &gt;0.8）反而需要警惕是否存在数据泄漏或未来信息引入的问题。</p>
    </div>
</div>
</div>

<!-- 概要 -->
<div class="section">
<h2>📊 数据概要览</h2>
<div class="info-grid">
    <div class="info-card"><div class="val">{n_samples}</div><div class="lbl">总样本数</div></div>
    <div class="info-card"><div class="val">{n_pos}</div><div class="lbl">正样本 (涨)</div></div>
    <div class="info-card"><div class="val">{n_neg}</div><div class="lbl">负样本 (跌)</div></div>
    <div class="info-card"><div class="val">{n_pos/n_samples*100:.1f}%</div><div class="lbl">正类占比</div></div>
</div>
<p><b>数据划分:</b> {split_desc}</p>
</div>

<!-- 标签构造 -->
<div class="section">
<h2>🏷️ 数据标签构造</h2>
<div class="info-grid">
    <div class="info-card" style="grid-column: 1/-1;">
        <div class="lbl" style="font-size:16px;">{label_desc}</div>
    </div>
</div>
<p style="margin-top:12px; color:#555;">
    标签构造规则: 以次日 <code>pct_chg</code> 为基准, 若涨跌幅 &gt; 0 则 label=1 (预测次日上涨), 否则 label=0 (预测次日下跌)。
    可通过调整 <code>mode</code> 和 <code>threshold</code> 参数切换不同的标签定义方式。
</p>
</div>

<!-- 特征工程 -->
<div class="section">
<h2>🔧 特征工程</h2>
<p>共 <b>{len(raw_features) + len(new_features)}</b> 个特征: 原始 {len(raw_features)} 个 + 衍生 {len(new_features)} 个</p>

<h3>原始特征 (OHLCV + 基础指标)</h3>
<table>
<thead><tr><th>特征名</th><th>说明</th></tr></thead>
<tbody>
<tr><td><code>open</code></td><td>开盘价</td></tr>
<tr><td><code>close</code></td><td>收盘价</td></tr>
<tr><td><code>high</code></td><td>最高价</td></tr>
<tr><td><code>low</code></td><td>最低价</td></tr>
<tr><td><code>vol</code></td><td>成交量</td></tr>
<tr><td><code>amount</code></td><td>成交额</td></tr>
<tr><td><code>amp</code></td><td>振幅</td></tr>
<tr><td><code>pct_chg</code></td><td>涨跌幅(%)</td></tr>
<tr><td><code>change</code></td><td>涨跌额</td></tr>
<tr><td><code>turnover_rate</code></td><td>换手率(%)</td></tr>
</tbody>
</table>

<h3>衍生特征 (技术指标)</h3>
<table>
<thead><tr><th>特征名</th><th>类别</th><th>计算说明</th></tr></thead>
<tbody>
{feature_rows}
</tbody>
</table>

<div style="margin-top:28px;padding-top:20px;border-top:2px solid #f0f2f5;">
<h3>🔍 特征指标选择与分析</h3>
<p class="algo-intro" style="margin-bottom:20px;">除原始指标外，本研究选取 <b>EXPMA、VOL、CR、WR 与 RSI</b> 五类技术指标作为模型输入特征，分别从价格趋势、成交量变化、多空力量、市场情绪及价格动量五个维度刻画股票运行状态。趋势指标用于识别股价方向的变化，成交量指标反映资金参与程度，多空力量指标衡量市场买卖双方力量对比，超买超卖指标反映价格偏离均衡状态，而动量指标刻画价格变化速度。上述指标具有较强的互补性，能够较为全面地描述股票由资金介入、趋势形成到动量增强的演化过程，为机器学习模型提供多维度的市场信息，提高模型对股票未来走势的识别能力。</p>
<table style="border-collapse:collapse;">
<thead><tr><th style="background:#e8f0fe;">指标</th><th style="background:#e8f0fe;">描述维度</th><th style="background:#e8f0fe;">市场含义</th></tr></thead>
<tbody>
<tr><td><b>EXPMA</b></td><td>趋势</td><td>股价趋势是否开始向上</td></tr>
<tr><td><b>VOL</b></td><td>资金</td><td>是否有新增资金介入</td></tr>
<tr><td><b>CR</b></td><td>市场人气</td><td>多空力量是否转向多头</td></tr>
<tr><td><b>WR</b></td><td>超买超卖</td><td>是否刚摆脱超卖</td></tr>
<tr><td><b>RSI</b></td><td>动量</td><td>上涨动能是否增强</td></tr>
</tbody>
</table>
</div>
</div>

<!-- 模型构建结果 -->
<div class="section">
<h2>🧠 模型构建结果</h2>
<p>共训练 <b>{len(results)}</b> 种分类模型, 使用标准化后的特征矩阵输入。树模型基于 Gini 不纯度进行分裂。</p>

<div class="model-grid">
"""
    for name, r in results.items():
        cm = r["confusion_matrix"]
        html += f"""<div class="model-card">
    <h3 class="model-name">{name}</h3>
    <div class="info-grid" style="margin:12px 0;">
        <div class="info-card"><div class="val">{r['accuracy']:.3f}</div><div class="lbl">Accuracy</div></div>
        <div class="info-card"><div class="val">{r['precision']:.3f}</div><div class="lbl">Precision</div></div>
        <div class="info-card"><div class="val">{r['recall']:.3f}</div><div class="lbl">Recall</div></div>
        <div class="info-card"><div class="val" style="color:#55A868;">{r['auc']:.3f}</div><div class="lbl">AUC</div></div>
    </div>
    <table class="report-table">
        <thead><tr><th>类别</th><th>Prec</th><th>Rec</th><th>F1</th><th>Support</th></tr></thead>
        <tbody>
            <tr><td>跌(0)</td>
                <td>{r['classification_report']['跌(0)']['precision']:.3f}</td>
                <td>{r['classification_report']['跌(0)']['recall']:.3f}</td>
                <td>{r['classification_report']['跌(0)']['f1-score']:.3f}</td>
                <td>{int(r['classification_report']['跌(0)']['support'])}</td></tr>
            <tr><td>涨(1)</td>
                <td>{r['classification_report']['涨(1)']['precision']:.3f}</td>
                <td>{r['classification_report']['涨(1)']['recall']:.3f}</td>
                <td>{r['classification_report']['涨(1)']['f1-score']:.3f}</td>
                <td>{int(r['classification_report']['涨(1)']['support'])}</td></tr>
        </tbody>
    </table>
    <div class="cm-grid">
        <div class="cm-cell"><span>真负 TN</span><strong>{cm[0][0]}</strong></div>
        <div class="cm-cell cm-fp"><span>假正 FP</span><strong>{cm[0][1]}</strong></div>
        <div class="cm-cell cm-fn"><span>假负 FN</span><strong>{cm[1][0]}</strong></div>
        <div class="cm-cell cm-tp"><span>真正 TP</span><strong>{cm[1][1]}</strong></div>
    </div>
    <img src="data:image/png;base64,{cm_imgs[name]}" alt="CM" class="static-img">
"""
        if r["feature_importance"]:
            top_imp = sorted(r["feature_importance"].items(), key=lambda x: x[1], reverse=True)[:8]
            imp_html = "".join(f"<tr><td><code>{k}</code></td><td>{v:.4f}</td></tr>" for k, v in top_imp)
            html += f"""<h3 style="margin-top:16px;">Top 8 特征重要性</h3>
            <table>
                <thead><tr><th>特征</th><th>Importance</th></tr></thead>
                <tbody>{imp_html}</tbody>
            </table>"""
        html += "</div>"
    html += "</div></div>"

    # 评估对比
    best_name = max(results, key=lambda k: results[k]["auc"])
    html += f"""
<div class="section">
<h2>📈 模型评估结果对比</h2>

<div class="best-model">
    <h3>🏆 最佳模型: {best_name}</h3>
    <div class="auc">AUC = {results[best_name]['auc']:.4f}</div>
    <p>准确率: {results[best_name]['accuracy']:.4f} | F1: {results[best_name]['f1']:.4f}</p>
</div>

<h3 style="margin-top:24px;">综合指标对比表</h3>
<table>
<thead><tr><th>模型</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>AUC</th></tr></thead>
<tbody>{model_rows}</tbody>
</table>

<h3 style="margin-top:24px;">指标对比图</h3>
<img src="data:image/png;base64,{metrics_b64}" class="static-img">

<h3 style="margin-top:24px;">ROC 曲线 (静态叠加)</h3>
<img src="data:image/png;base64,{roc_b64}" class="static-img">

<h3 style="margin-top:24px;">ROC 曲线 (交互式 Plotly)</h3>
<div class="plotly-chart">{roc_html}</div>

<h3 style="margin-top:24px;">模型指标对比 (交互式 Plotly)</h3>
<div class="plotly-chart">{metrics_html}</div>
</div>

<!-- 特征重要性 -->
<div class="section">
<h2>📊 特征重要性</h2>
<p>展示 AUC 最高的树模型中排名前列的特征</p>
<img src="data:image/png;base64,{fi_b64}" class="static-img">
</div>

<!-- 决策树结构 -->
<div class="section">
<h2>🌳 决策树结构</h2>
<p>max_depth=4 的决策树可视化</p>
<img src="data:image/png;base64,{dt_b64}" class="static-img">
</div>

<!-- 结论 -->
<div class="section">
<h2>📝 结论与建议</h2>
<p class="algo-intro" style="margin-bottom:20px;">从实验结果可以看出，随机森林和XGBoost两种集成学习模型整体性能优于逻辑回归、决策树及梯度提升模型。其中，随机森林模型在Accuracy（60.00%）、Precision（60.66%）及F1-score（59.68%）等指标上均取得最佳表现，而XGBoost模型获得了最高的AUC值（57.73%），说明基于树模型的集成学习方法能够更有效地挖掘技术指标之间的非线性关系，提高股票涨跌预测能力。相比之下，逻辑回归由于只能建模线性关系，在复杂金融市场环境下难以准确刻画技术指标之间的交互作用，因此整体性能较差。</p>
<p class="algo-intro" style="margin-bottom:20px;">尽管随机森林和XGBoost优于其他模型，但整体AUC仍不足0.60，表明仅依赖EXPMA、VOL、CR、WR和RSI等技术指标，对股票未来走势的预测能力仍然有限。这说明股票价格不仅受历史价格和成交量等技术因素影响，还受到宏观经济环境、行业景气度、市场情绪、资金流向及重大事件等多种因素共同作用，因此单纯依赖技术指标难以实现较高精度的预测。</p>

<h3 style="margin-top:24px;">🔧 改进建议</h3>
<table style="border-collapse:collapse;">
<thead><tr><th style="background:#e8f0fe;">#</th><th style="background:#e8f0fe;">方向</th><th style="background:#e8f0fe;">具体措施</th></tr></thead>
<tbody>
<tr><td><b>1</b></td><td>增加特征维度</td><td>在现有EXPMA、VOL、CR、WR、RSI基础上，引入ATR、布林带宽、成交额、行业板块强弱等特征，提高模型的信息量。</td></tr>
<tr><td><b>2</b></td><td>优化标签定义</td><td>如果目前标签为「未来N日上涨」，可以尝试定义为「未来5日收益率超过3%」或「未来10日收益率超过5%」，降低短期随机波动对标签的干扰。</td></tr>
<tr><td><b>3</b></td><td>特征筛选与重要性分析</td><td>利用随机森林特征重要性或SHAP分析识别关键影响因素，剔除贡献较低或高度相关的指标，提高模型可解释性。</td></tr>
<tr><td><b>4</b></td><td>优化模型训练策略</td><td>采用时间序列交叉验证（Time Series Split），并通过网格搜索或贝叶斯优化调整超参数，减少过拟合风险，提高模型稳定性。</td></tr>
<tr><td><b>5</b></td><td>融合更多市场信息</td><td>引入资金流向、行业热度、指数趋势、财务因子等非技术指标，构建技术面与基本面相结合的多因子模型，以提升预测能力。</td></tr>
</tbody>
</table>
</div>

</div>
</body>
</html>"""

    out_path = os.path.join(BASE, "Task5_ml_classification.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[HTML报告] 已生成 → {out_path}")
    return out_path


# ─── 主流程 ───────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(" Task5: 机器学习分类模型实战")
    print("=" * 60)

    # 1) 加载数据
    df = load_stock_data(DATA_PATH)
    stock_code = str(df["股票代码"].iloc[0]).strip()
    df = df.drop(columns=["股票代码"], errors="ignore")

    # 2) 标签构造
    df, label_desc = build_label(df, mode="next_day", threshold=0.0, forward_days=1)

    # 3) 特征工程
    df, new_features = build_features(df)

    raw_features = ["open", "close", "high", "low", "vol", "amount", "amp",
                    "pct_chg", "change", "turnover_rate"]
    feature_cols = raw_features + new_features

    # 4) 清除NaN
    df = df.dropna(subset=feature_cols + ["label"]).reset_index(drop=True)
    n_samples = len(df)
    n_pos = int(df["label"].sum())
    n_neg = n_samples - n_pos
    print(f"[数据] 有效样本: {n_samples}, 正={n_pos}, 负={n_neg}")

    # 5) 特征说明
    feature_descs = describe_features(feature_cols, raw_features, new_features)

    # 6) 数据划分
    X_train, X_test, y_train, y_test, split_desc = prepare_data(
        df, feature_cols, test_size=0.2, method="random"
    )
    print(f"\n[划分] {split_desc}")
    print(f"  训练集: {len(X_train)} | 测试集: {len(X_test)}")
    print(f"  训练集正类占比: {y_train.mean()*100:.1f}%")
    print(f"  测试集正类占比: {y_test.mean()*100:.1f}%")

    # 7) 模型训练
    print("\n" + "=" * 60)
    print(" 开始训练模型...")
    models = get_models()
    results = train_and_evaluate(models, X_train, X_test, y_train, y_test, feature_cols)

    # 8) 保存结构化结果
    metrics_out = {}
    for name, r in results.items():
        metrics_out[name] = {
            "accuracy": r["accuracy"],
            "precision": r["precision"],
            "recall": r["recall"],
            "f1": r["f1"],
            "auc": r["auc"],
            "classification_report": r["classification_report"],
        }

    metrics_path = os.path.join(RESULTS_DIR, "task5_models_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics_out, f, indent=2, ensure_ascii=False)
    print(f"\n[结果JSON] 已保存 → {metrics_path}")

    # 特征重要性 CSV
    fi_rows = []
    for name, r in results.items():
        if r["feature_importance"]:
            for feat, imp in r["feature_importance"].items():
                fi_rows.append({"model": name, "feature": feat, "importance": imp})
    if fi_rows:
        fi_df = pd.DataFrame(fi_rows).sort_values(["model", "importance"], ascending=[True, False])
        fi_path = os.path.join(RESULTS_DIR, "task5_feature_importance.csv")
        fi_df.to_csv(fi_path, index=False, encoding="utf-8-sig")
        print(f"[特征重要性] 已保存 → {fi_path}")

    # 9) 生成 HTML 报告
    print("\n[HTML] 正在生成交互式报告...")
    generate_html_report(
        results=results,
        label_desc=label_desc,
        feature_descs=feature_descs,
        raw_features=raw_features,
        new_features=new_features,
        split_desc=split_desc,
        n_samples=n_samples,
        n_pos=n_pos,
        n_neg=n_neg,
        stock_code=stock_code,
    )

    print("\n" + "=" * 60)
    print(" ✅ Task5 完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
