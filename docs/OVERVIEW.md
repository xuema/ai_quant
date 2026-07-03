# Announcement Alpha — 公告事件驱动选股系统

> 基于 LLM 评分的 A 股公告事件驱动策略，从巨潮资讯网抓取 -> 大模型评分 -> 因子构建 -> 事件研究（CAR） -> 交易信号生成

---

## 完整流程图

```
巨潮资讯网 (cninfo.com.cn)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  pipeline/cninfo_fetcher.py                      │
│  1. 爬取公告（巨潮 API）                          │
│  2. 强信号关键词预筛选                            │
│  3. LLM 评分（Oracle CLI / GPT-5.4 Pro）          │
│  4. 输出 ranking_YYYYMMDD.json                    │
└─────────────────────────────────────────────────┘
    │
    ▼
  data/raw_json/ranking_YYYYMMDD.json
    │
    ▼
┌─────────────────────────────────────────────────┐
│  run_daily.py                                    │
│  1. 加载公告 + 价格数据                           │
│  2. 构建因子（score 聚合 + 波动调整）               │
│  3. 风控模型（极值过滤 + Winsorize + Z-Score）     │
│  4. 事件研究 CAR（pre/post/泄露检测）               │
│  5. IC 分析                                     │
│  6. 泄露分析                                     │
│  7. Top-K 信号生成                                │
└─────────────────────────────────────────────────┘
    │
    ▼
  data/results/YYYYMMDD/
  ├── car_results_YYYYMMDD.csv     (CAR 分析)
  ├── signal_long_YYYYMMDD.csv     (做多信号)
  └── signal_short_YYYYMMDD.csv    (做空信号)
```

---

## 快速开始

### 单步运行（推荐）

```bash
cd /Users/skyler/workspace/stock_selection/announcement_alpha

# 昨天公告 + 评分 + 信号（一步到位）
python pipeline/cninfo_fetcher.py --run-daily

# 指定日期
python pipeline/cninfo_fetcher.py 2026-04-09 --run-daily
```

### 分步运行

```bash
# 只爬取（不评分）
python pipeline/cninfo_fetcher.py 2026-04-09 --raw-only

# 只评分（已有 raw 数据）
python pipeline/cninfo_fetcher.py 2026-04-09

# 从已有 ranking 生成信号
python run_daily.py

# 市场模式（需 000300.csv）
python run_daily.py --mode market
```

---

## 项目结构

```
announcement_alpha/
├── config.py                        # 统一配置中心
├── run_daily.py                     # 信号生成入口（7 步流水线）
├── backtest.py                      # 回测模块
│
├── pipeline/
│   ├── __init__.py
│   └── cninfo_fetcher.py            # 巨潮爬取 + LLM 评分
│
├── core/
│   ├── loader.py                    # 数据加载层
│   ├── factor_builder.py            # 因子构建（聚合 + 波动调整）
│   ├── risk_model.py                # 风控（极值 + Winsorize + Z-Score）
│   ├── strategy.py                  # 信号生成（Top-K）
│   ├── llm_scorer.py                # LLM 评分（Oracle CLI）
│   ├── event_study_extended.py      # 事件研究（CAR pre/post/leakage）
│   └── event_study.py               # 事件研究简化版
│
└── data/
    ├── raw_json/                    # 公告评分数据 (ranking_YYYYMMDD.json)
    ├── history_json/                # 历史原始公告
    ├── market/                      # 市场指数 (000300.csv)
    └── results/                     # 运行结果 (按日期分目录)
        └── YYYYMMDD/
            ├── car_results_YYYYMMDD.csv
            ├── signal_long_YYYYMMDD.csv
            └── signal_short_YYYYMMDD.csv
```

---

## LLM 评分

系统通过 **Oracle CLI**（本地已安装）调用 GPT-5.4 Pro 对每条公告评分，无需额外配置 API Key。

### 评分维度

| 维度 | 范围 | 说明 |
|------|------|------|
| **score** | -2.0 ~ +2.0 | 利多程度 |
| **label** | 利多/利空/中性 | 定性标签 |
| **event_type** | 业绩/分红/增持/回购/股权激励/等 | 事件分类 |
| **confidence** | 0.0 ~ 1.0 | LLM 置信度 |

### 评分 Prompt

系统会自动构建如下 Prompt 发送给 LLM：

```
你是一个A股量化公告分析器。请对以下公告列表逐条评分。

评分规则：
- score 范围：-2.0 到 +2.0
- 利多 = score > 0，利空 = score < 0
- 分红/派息/业绩预告超预期 = 高利多
- 减持/减值/亏损 = 利空
- 事件类型：业绩/分红/增持/回购/股权激励/减持/减值/重组/订单/其他
```

### 输出

```json
[
  {
    "code": "000725",
    "date": "2026-04-09",
    "score": 1.5,
    "title": "京东方科技2025年度利润分配预案",
    "event_type": "分红",
    "confidence": 0.92,
    "label": "利多"
  }
]
```

### 自定义

如果要更换 LLM 或评分规则，修改：
- `core/llm_scorer.py` 中的 `SYSTEM_PROMPT`
- `pipeline/cninfo_fetcher.py` 中的 `STRONG_KEYWORDS` 粗筛词

---

## 策略逻辑

### 因子构建

```
原始 score（LLM 评分）
    │
    ├─ 同股票同日多条公告 → score 求和
    │
    ├─ 波动调整：factor = score / std(score_by_stock)
    │  （防止频繁公告的公司权重过高）
    │
    └─ （不做标准化，留给风控模型）
```

### 风控模型

```
Raw Factor
    │
    ├─ 极值过滤：factor ∈ (-10, 10)
    │
    ├─ Winsorize：截面 5%/95% 分位数截断
    │
    └─ 截面 Z-Score：标准化为均值 0、标准差 1
```

### 事件研究（CAR）

```
|---pre_window(5天)---|--事件日--|--post_window(3天)---|
  -5  -4  -3  -2  -1     0       +1    +2    +3
 ───────────────────────────────────────────────────────
  CAR_pre                │        CAR_post
  (泄露检测)              │       (纯净 Alpha)
```

### 信号生成

| 信号 | 规则 |
|------|------|
| **做多** | Top-K（默认 20 只最高 factor） |
| **做空** | Bottom-K（默认 20 只最低 factor） |
| 自动调整 | 不足 2× Top-K 时自动减半，避免重叠 |

---

## 配置说明

所有参数在 `config.py` 集中管理：

```python
CONFIG = {
    # 数据路径
    "announcement_dir": "data/raw_json",
    "price_cache_dir": "data_cache_daily",
    "market_index_file": "data/market/000300.csv",

    # CAR 参数
    "car_mode": "simple",        # "simple" | "market"
    "pre_window": 5,             # 事件前交易日
    "post_window": 3,            # 事件后交易日

    # 信号
    "top_k": 20,

    # 风控
    "factor_floor": -10,
    "factor_cap": 10,
    "winsor_lower": 0.05,
    "winsor_upper": 0.95,
}
```

CLI 覆盖参数：
```bash
python run_daily.py --mode market --pre 7 --post 5 --top-k 30
```

---

## 每日自动运行

可以添加到 crontab 或 openclaw cron：

```bash
# 每个交易日收盘后（15:30 CST）自动运行
0 15 * * 1-5 cd /Users/skyler/workspace/stock_selection/announcement_alpha && python pipeline/cninfo_fetcher.py --run-daily >> /tmp/announcement_daily.log 2>&1
```

---

## 已知问题 & TODO

- [ ] 补充市场指数（000300.csv）以支持 market 模式 CAR
- [ ] 增加回测集成（将 backtest.py 接入 run_daily）
- [ ] 增加行业/市值中性化
- [ ] LLM 评分结果缓存机制
- [ ] 多日历史数据分析（IC 时序、滚动 IC）
- [ ] PDF 内容提取（用 NLP 而非仅标题）
