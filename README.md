# Announcement Alpha — 公告事件驱动选股系统

> 基于上市公司公告（分红、回购、业绩预告等）的 NLP 评分因子，通过事件研究法（CAR）验证因子有效性，生成每日做多/做空信号。

---

## 📁 项目结构

```
announcement_alpha/
├── config.py                  # 统一配置中心（路径、参数、风控阈值）
├── run_daily.py               # 每日运行入口（7 步流水线）
├── backtest.py                # 回测模块（尚未启用）
│
├── core/
│   ├── loader.py              # 数据加载层：公告 JSON + 日线价格 + 沪深300 指数
│   ├── factor_builder.py      # 因子构建：score 聚合 → 波动率调整
│   ├── risk_model.py          # 风控模型：极值过滤 → Winsorize → 截面 Z-Score
│   ├── strategy.py            # 信号生成：每日截面 Top-K 做多 / Bottom-K 做空
│   ├── event_study_extended.py # 事件研究：CAR_pre / CAR_post / 泄露检测
│   └── event_study.py         # 事件研究（简化版，仅计算 post-window CAR）
│
└── data/
    ├── raw_json/              # 当日公告数据（ranking_YYYYMMDD.json）
    ├── history_json/          # 历史公告数据
    └── market/                # 市场指数（000300 沪深300）
```

---

## 🔄 核心运行流程（7 步流水线）

### Step 1: 数据加载

| 数据源 | 来源 | 说明 |
|--------|------|------|
| **公告数据** | `data/raw_json/ranking_YYYYMMDD.json` | 每日公告评分，字段：`code`, `date`, `score`, `title` |
| **日线价格** | `data_cache_daily/`（CSV 文件） | 由 `2_update_a_stock_data.py` 维护，4300+ 只股票 |
| **市场指数** | `data/market/000300.csv`（可选） | 沪深 300 收盘价，用于计算超额收益（CAR） |

### Step 2: 因子构建

```
原始 score（NLP 评分）
    │
    ▼
按 (code, date) 聚合：同一股票当天多条公告 → score 求和
    │
    ▼
波动率调整：factor_raw = score / std(score_by_stock)
    防止大盘股/频繁公告的公司权重过高
    │
    ▼
（不做标准化，留给 risk_model）
```

**关键设计**：`factor_builder.py` 只做聚合和波动率调整，不做截面标准化，避免与 risk_model 的 Z-Score 重复。

### Step 3: 风控模型

```
Raw Factor
    │
    ▼
1. 极值过滤：factor ∈ (-10, 10)，剔除极端异常的公告
    │
    ▼
2. Winsorize：截面 5%/95% 分位数截断
   防止少数极端分数污染标准化后的分布
    │
    ▼
3. 截面 Z-Score：每日因子标准化为均值为 0、标准差为 1
    保证不同日期的因子具有可比性
```

### Step 4: 事件研究（CAR 分析）

核心：对每只股票计算公告日前后的累计（超额）收益。

```
时间线（交易日）：

  |---pre_window---|--事件日--|--post_window--|
   -5   -4   -3   -2   -1      0       +1  +2  +3
  ────────────────────────────────────────────────
   CAR_pre（泄露检测）   │    CAR_post（纯净 Alpha）
```

| 指标 | 定义 | 含义 |
|------|------|------|
| **CAR_pre** | 事件日前 N 天累计（超额）收益 | 信息泄露度量 |
| **CAR_post** | 事件日后 N 天累计（超额）收益 | 真正的 Alpha |
| **CAR_total** | CAR_pre + CAR_post | 整体预测能力 |
| **Leakage** | CAR_pre / CAR_total | > 0.5 表示泄露严重 |

### Step 5: IC 分析

计算因子与 CAR 的相关性：

| IC 指标 | 计算公式 | 解读 |
|---------|---------|------|
| **IC_total** | corr(factor, CAR_total) | 因子整体预测能力 |
| **IC_post** | corr(factor, CAR_post) | ⭐ 真正的 Alpha 能力 |
| **IC_pre** | corr(factor, CAR_pre) | ⚠️ 因子泄露程度 |

### Step 6: 泄露分析

统计有多少事件表现出信息泄露（leakage > 0.5）:

```
高泄露事件占比 = count(leakage > 0.5) / count(all_events)
```

**2026-04-01 测试结果**：62.50% 的事件存在泄露，中位数 leakage = 0.80

### Step 7: 信号生成

```
因子 DataFrame
    │
    ▼
每日排序（从大到小）
    │
    ├─ 前 Top-K → signal_long.csv（做多）
    └─ 后 Top-K → signal_short.csv（做空）
```

- `top_k` 默认 20
- 当股票池不足 `2 * top_k` 时自动减半，防止 long/short 重叠

---

## 📊 最新运行结果（2026-04-01 数据）

```
CAR 模式     : simple
前窗口       : 5 个交易日
后窗口       : 3 个交易日
有效事件数   : 16

IC_total : 0.2927  — 因子有一定预测能力
IC_post  : 0.4270  ⭐ 纯 Alpha 预测能力强
IC_pre   : 0.1758  ⚠️ 泄露信号也存在

泄露分析:
  高泄露占比  : 62.50%
  中位泄露值  : 0.8026
```

**核心发现**：因子在事件后的预测能力（0.43）远强于事前（0.18），说明**即使存在信息泄露，因子仍然有可利用的 Alpha**。

---

## 🛠️ 当前已知问题

### 严重

| 问题 | 状态 | 说明 |
|------|------|------|
| 单日数据 | ⚠️ 待解 | 只有 1 天公告数据（2026-04-01），IC 分析样本量太少 |
| 缺失市场指数 | ⚠️ 待解 | `000300.csv` 不存在，无法计算超额 CAR |

### 轻微

| 问题 | 状态 | 说明 |
|------|------|------|
| backtest.py | 🟡 部分可用 | 回测逻辑已修复但未集成到 run_daily |
| 无命令行参数 | ✅ 已解 | 已支持 `--mode`、`--pre`、`--post`、`--top-k` |
| 泄露无统计检验 | 🟡 待解 | 没有对泄露显著性做 t 检验或 bootstrap |

---

## 🚀 下一步优化方向

### 1. 数据层

- [ ] **收集每日公告数据**：每天运行公告爬取脚本，生成 `ranking_YYYYMMDD.json`
- [ ] **补全历史数据**：至少需要 30-60 天的公告数据才能做可靠的 IC 分析
- [ ] **添加沪深 300 指数**：下载 000300 日线数据，支持 `market` 模式的 CAR
- [ ] **添加行业分类**：用于中性化、行业轮动分析
- [ ] **考虑停牌/涨跌停**：剔除无法交易的信号

### 2. 信号层优化

- [ ] **市值中性化**：剔除大小市值偏置
- [ ] **行业中性化**：每个行业内部分位数排名
- [ ] **动态 Top-K**：根据每日信号数量自动调整持仓数
- [ ] **组合持仓权重**：按因子分档或 IC 加权，非等权

### 3. 回测模块

- [ ] **将 backtest.py 集成到 run_daily**：自动跑 PnL 曲线
- [ ] **交易成本**：滑点、佣金、印花税
- [ ] **基准对比**：vs 沪深 300、中证 500
- [ ] **多日持有**：支持 1 日/3 日/5 日持有期回测

### 4. 统计严谨性

- [ ] **泄露显著性检验**：bootstrap 置信区间
- [ ] **IC 时序分析**：滚动 IC、ICIR
- [ ] **分组回测**：按因子分 5 组，观察单调性

---

## 📋 每日运行清单

```
# 1. 获取当日公告（外部脚本）
#    → 生成 ranking_YYYYMMDD.json → 放入 data/raw_json/

# 2. 更新日线价格（外部脚本）
/Users/skyler/workspace/stock_selection/2_update_a_stock_data.py

# 3. 运行公告因子信号
cd /Users/skyler/workspace/stock_selection/announcement_alpha
python run_daily.py

# 可选：市场模式
python run_daily.py --mode market

# 查看结果
cat signal_long.csv
cat car_results_extended.csv
```

---

## 📝 开发日志

### 2026-04-11 — 项目重构

- ✅ 修复 `factor_builder.py` 和 `risk_model.py` 的重复标准化 bug
- ✅ 修复 `event_study_extended.py` 事件窗口边界（包含事件日）
- ✅ 修复 `event_study.py` 简化版 CAR
- ✅ 完全重写 `backtest.py`（原版跑不通）
- ✅ `config.py` 统一配置，支持项目相对路径
- ✅ `run_daily.py` 增加 CLI 参数和详细日志
- ✅ `strategy.py` 修复 Top-K 重叠问题
