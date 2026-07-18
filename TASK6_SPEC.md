# Task6: 机器学习选股策略与回测系统 — 实施方案

## 一、任务目标

基于已有股票基本面数据，构建完整的「数据加载 → 特征工程 → 模型训练 → 选股策略 → 回测评估 → 可视化」pipeline，实现可复用的量化选股系统。

## 二、数据源

| 字段 | 说明 |
|------|------|
| **路径** | `data/stock_analysis/model_data.csv` |
| **行数** | 39,616 条 |
| **列数** | 22 列 (19个基础特征 + Date + Code + Next_Ret) |
| **时间范围** | 2020-03-31 ~ 2022-06-30 (10个季度) |
| **股票数** | 3,627 ~ 4,262 (逐季递增) |
| **应变量** | `Next_Ret` (下期收益率, 连续值) |

### 基础特征

| 类别 | 字段 |
|------|------|
| 估值因子 | 企业倍数(EV/EBITDA), 市净率PB, 市现率PCF(现金/经营), 市盈率PE(含扣非), 市销率PS, 股息率 |
| 规模因子 | MV (市值) |
| 成长因子 | 净利润/净资产/利润总额/基本每股收益/总资产/现金净流量/经营现金流/营业利润/营业总收入/营业收入 同比增长率 |

## 三、特征工程 (19 → 36)

### 衍生特征

| 衍生特征 | 计算方式 | 说明 |
|----------|---------|------|
| `log_MV` | log1p(MV) | 对数市值 |
| `EP` | 1/PE | 盈利收益率 (倒数) |
| `BP` | 1/PB | 账面收益率 |
| `SP` | 1/PS | 销售收益率 |
| `{估值因子}_rank` | groupby(Date).rank(pct) | 横截面分位排名 |
| `{成长因子}_rank` | groupby(Date).rank(pct) | 横截面分位排名 |
| `MV_rank` | groupby(Date).rank(pct) | 规模排名 |
| `股息率_rank` | groupby(Date).rank(pct) | 股息排名 |
| `现金净流量排名` | groupby(Date).rank(pct) | 现金流排名 |
| `EP×净利润增长` | EP × 净利润同比增长率 | 估值-成长交互 |
| `BP×营收增长` | BP × 营业收入同比增长率 | 估值-成长交互 |
| `PE_cross_dispersion` | groupby(Date).std(PE) | 横截面离散度 |
| `PE_pctl` | (PE - median) / std | 标准化偏离 |

### 预处理
- **Winsorize**: 上下 1% 截断极端值
- **缺失值填充**: ffill → 0
- **标准化**: StandardScaler (线性模型需要)

### 应变量设计
- **主模型**: `Next_Ret` (回归预测下期收益率)
- **辅助标签**: `Label_Up = (Next_Ret > 0).astype(int)` (分类方向)

## 四、数据划分 (严格按时间线)

| 集合 | 日期范围 | 季度数 | 样本数 |
|------|---------|--------|--------|
| **训练集** | 2020Q1 ~ 2021Q3 | 7 | 26,953 |
| **测试集** | 2021Q4 ~ 2022Q2 | 3 | 12,663 |

> 70% 时间线训练, 30% 时间线测试, 保持未来不可见原则

## 五、模型 (6种)

| # | 模型 | 类型 | 关键超参数 |
|---|------|------|-----------|
| 1 | Ridge | 线性回归 | alpha=1.0 |
| 2 | Lasso | 线性回归 | alpha=0.01 |
| 3 | DecisionTree | 树 | max_depth=8, min_samples_leaf=50 |
| 4 | **RandomForest** | 集成树 | n_est=200, max_depth=12, min_samples_leaf=30 |
| 5 | GradientBoosting | 集成树 | n_est=200, max_depth=5, lr=0.05 |
| 6 | XGBoost | 梯度提升 | n_est=300, max_depth=6, lr=0.05 |

> 最佳模型: **RandomForest** (用于选股策略)

## 六、选股策略 — Top30 滚动

### 策略逻辑
1. 对测试集每期末, 用训练好的模型预测下期收益率
2. 按预测值排序, 选 Top30
3. 持有到下一期末, 获取实际收益

### 组合方式
- **等权组合 (EW)**: Top30 股票等权持仓
- **预测加权 (PW)**: 基于预测值正权重加权
- **市场基准**: 全市场等权平均

## 七、回测核心指标

| 指标 | 计算公式 |
|------|---------|
| **总收益率** | Π(1+R_i) - 1 |
| **年化收益率** | (1+总收益)^(4/N) - 1 |
| **夏普比率** | (μ_R - Rf) / σ_R × √4 |
| **最大回撤** | max((峰值 - 谷值) / 峰值) |
| **季度胜率** | Top30 中正收益股票占比 |

## 八、输出文件

### 模型文件
```
data/results/task6/models/
├── Ridge.pkl
├── Lasso.pkl
├── DecisionTree.pkl
├── RandomForest.pkl
├── GradientBoosting.pkl
└── XGBoost.pkl
```
每个 pkl 包含: `model`, `scaler`, `features`, `metrics`, `trained_at`

### 策略结果
| 文件 | 内容 |
|------|------|
| `top30_selection_strategy.csv` | 所有入选 Top30 股票 |
| `stock_pick_YYYYMMDD.csv` | 各期选股结果 |
| `task6_backtest_metrics.json` | 回测核心指标 |

### 特征重要性
| 文件 | 内容 |
|------|------|
| `{ModelName}_feature_importance.csv` | 各模型完整特征排名 |

### 可视化图表 (figures/)
| 文件 | 内容 |
|------|------|
| `01_model_performance.png` | 6模型 R²/MAE/RMSE/DirAcc 对比 |
| `02_cumulative_returns.png` | 累计净值曲线 |
| `03_quarterly_returns.png` | 季度收益率柱状图 |
| `04_feature_importance.png` | 最佳模型 Top15 特征重要性 |
| `05_feature_importance_comparison.png` | 多模型 Top10 特征对比 |
| `06_returns_heatmap.png` | 策略×季度收益率热力图 |
| `07_top5_scatter.png` | 各季度 Top5 股票实际收益分布 |

### 汇总报告
| 文件 | 内容 |
|------|------|
| `task6_summary.txt` | 完整文字报告 |

## 九、模型评估结果 (实测)

| 模型 | Test R² | Test MAE | Dir Acc |
|------|---------|----------|---------|
| XGBoost | -0.0704 | 0.198 | 57.56% |
| Ridge | -0.2329 | 0.216 | 50.92% |
| Lasso | -0.2767 | 0.219 | 32.78% |
| GradientBoosting | -0.3717 | 0.227 | 46.56% |
| RandomForest | -0.4278 | 0.231 | 46.89% |
| DecisionTree | -0.4324 | 0.232 | 45.57% |

## 十、回测结果 (实测)

| 策略 | 总收益 | 年化 | 夏普 | 最大回撤 |
|------|--------|------|------|---------|
| Top30 等权 | -2.69% | -3.57% | -0.38 | 10.95% |
| Top30 预测加权 | -2.39% | -3.17% | -0.37 | 10.54% |
| 市场基准 | -16.20% | -20.99% | -2.70 | 16.20% |

> Top30 策略虽录得微亏, 但显著跑赢基准, 超额约 +13.5%

## 十一、Python 依赖

| 包 | 版本 |
|----|------|
| pandas | 2.3.3 |
| numpy | 2.0.2 |
| scikit-learn | 1.6.1 |
| xgboost | 2.1.4 |
| matplotlib | 3.9.4 |
| seaborn | 0.13.2 |

## 十二、运行

```bash
python Task6_ml_strategy_backtest.py
```

输出目录: `data/results/task6/`
