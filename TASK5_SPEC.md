# Task5 机器学习分类模型实战 — 实施方案

## 一、任务目标

使用多种机器学习分类算法对股票数据进行涨跌预测，构建完整的「数据加载 → 特征工程 → 模型训练 → 评估对比 → 可视化」pipeline，并输出交互式 HTML 报告。

## 二、数据源（可切换）

### 2.1 本地股票数据（默认）
| 字段 | 说明 |
|------|------|
| **路径** | `data/stock_analysis/002281_20250703_20260708.csv` |
| **行数** | ~247 条 |
| **字段** | trade_date, 股票代码, open, close, high, low, vol, amount, amp, pct_chg, change, turnover_rate |

### 2.2 sklearn 乳腺癌数据集（对照选项）
- `sklearn.datasets.load_breast_cancer()`
- 569 样本 × 30 特征，二分类标签 0/1

### 2.3 标签构造（股票数据专用）

| 方案 | 规则 | 说明 |
|------|------|------|
| **次日涨跌** | label = 1 if 次日 pct_chg > 0 else 0 | 最常用，预测次日涨跌方向 |
| **阈值涨跌** | label = 1 if 次日 pct_chg > threshold else 0 | 忽略小幅波动，threshold 默认 1% |
| **多日收益** | label = 1 if N日后收益率 > threshold else 0 | 预测中期方向 |

默认采用 **次日涨跌** 方案，可配置。

## 三、特征工程

### 3.1 原始特征
- open, close, high, low, vol, amount, amp, pct_chg, change, turnover_rate

### 3.2 技术指标衍生特征
| 指标 | 计算方式 | 用途 |
|------|---------|------|
| 移动均价差 | (close - MA_n) / MA_n | n∈{5, 10, 20} |
| 波动率 | rolling std(close, window=n) | n∈{5, 10} |
| 量比 | vol / MA_vol_20 | 相对放量 |
| RSI | 14日相对强弱指标 | 超买超卖 |
| MACD | 12/26日EMA差值 | 趋势动量 |
| 涨跌幅 | pct_chg（已有） | 原始涨跌 |
| 振幅 | amp（已有） | 波动强度 |

### 3.3 预处理
- 缺失值处理：前向填充（ffill）+ 剔除首段
- 标准化：StandardScaler（树模型可跳过）
- 特征选择：可选，使用 RandomForest feature_importances 筛选 Top-K

## 四、数据划分

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **test_size** | 0.2 | 20% 测试集 |
| **random_state** | 42 | 可复现 |
| **stratify** | True | 保持正负样本比例 |

股票数据时序特性可选方案：
| 方案 | 说明 |
|------|------|
| **随机划分**（默认） | train_test_split(stratify=y)，与对照组一致 |
| **时序划分** | 按时间先后切分，前80%训练，后20%测试 |

报告需展示两种划分方式的对比结果。

## 五、分类模型（至少 5 种）

| 模型 | 类 | 关键超参数 |
|------|-----|-----------|
| **逻辑回归** | LogisticRegression | C, penalty, max_iter |
| **决策树** | DecisionTreeClassifier | max_depth, min_samples_split, criterion |
| **随机森林** | RandomForestClassifier | n_estimators, max_depth, min_samples_split |
| **梯度提升** | GradientBoostingClassifier | n_estimators, learning_rate, max_depth |
| **XGBoost** | xgb.XGBClassifier（可选） | n_estimators, learning_rate, max_depth |
| **SVM** | SVC（可选） | C, kernel, gamma |
| **K近邻** | KNeighborsClassifier | n_neighbors, weights |

所有模型使用默认参数作为基线，随机森林和梯度提升需展示 GridSearchCV 超参数调优过程。

## 六、模型评估

### 6.1 评估指标
| 指标 | 说明 |
|------|------|
| **Accuracy** | 整体分类准确率 |
| **Precision** | 正类预测准确率 |
| **Recall** | 正类召回率 |
| **F1-Score** | Precision 与 Recall 调和平均 |
| **AUC-ROC** | ROC 曲线下面积，核心指标 |
| **Confusion Matrix** | 混淆矩阵 |

### 6.2 评估输出方式
- 各模型分类报告（sklearn `classification_report`）
- 各模型混淆矩阵
- 各模型 AUC 值横向对比
- ROC 曲线叠加图

## 七、可视化输出

### 7.1 ROC 曲线图
- 所有模型 ROC 曲线绘制在同一张图上
- 标注各模型 AUC 值（图例）
- 对角线参考线（AUC=0.5 随机猜测基准）
- 子图：每个模型单独的 ROC 图

### 7.2 其他可视化
| 图表 | 内容 |
|------|------|
| 混淆矩阵热力图 | 每个模型的 2×2 混淆矩阵 |
| 指标对比柱状图 | Accuracy/Precision/Recall/F1/AUC 横向对比 |
| 特征重要性 | RandomForest/GradientBoosting 的 feature_importances 排序图 |
| 决策树可视化 | DecisionTree 的树结构图（限制 max_depth≤4） |

## 八、交互式 HTML 报告

### 8.1 页面布局
- **顶部控制面板**：选择数据源 / 标签方案 / 数据划分方式 / 测试集比例
- **模型选择器**：复选框选择参与对比的模型
- **ROC 曲线面板**：叠加 ROC 图 + 各模型 AUC 值
- **指标对比面板**：柱状图/表格对比所有评估指标
- **混淆矩阵面板**：热力图展示
- **特征重要性面板**：Feature importance bar chart
- **结论区**：模型对比总结与实用建议

### 8.2 前端技术
- Plotly.js（交互式图表）
- 纯 HTML/CSS/JS 单文件输出

## 九、输出文件

| 文件 | 路径 | 内容 |
|------|------|------|
| 主脚本 | `ml_classification_task5.py` | 完整 pipeline：数据加载 → 特征 → 训练 → 评估 → HTML 生成 |
| HTML 报告 | `Task5_ml_classification.html` | 交互式可视化报告 |
| 模型结果 JSON | `data/results/task5_models_metrics.json` | 各模型评估指标（可复用的结构化结果） |
| 特征重要性 CSV | `data/results/task5_feature_importance.csv` | 各模型特征重要性排行 |

## 十、Python 依赖

| 包 | 版本要求 |
|----|---------|
| pandas | ≥1.5 |
| numpy | ≥1.23 |
| scikit-learn | ≥1.2 |
| matplotlib | ≥3.6 |
| seaborn | ≥0.12 |
| plotly | ≥5.0 |
| xgboost | 可选 |

## 十一、预期结论（参考）

- **随机森林 / 梯度提升** 通常表现最佳，AUC 约 0.6–0.8
- **逻辑回归** 作为基线，AUC 约 0.5–0.65
- 短期股票波动预测本身信噪比低，AUC 很难突破 0.8
- 乳腺癌数据集作为对照：各模型 AUC 可达 0.95+
- 特征重要性可揭示哪些技术指标对涨跌预测最有信号价值
