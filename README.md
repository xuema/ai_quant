# Announcement Alpha — 公告事件驱动选股系统

> 基于 LLM 评分的 A 股公告事件驱动策略。从巨潮资讯网抓取 → 大模型评分 → 因子构建 → 事件研究（CAR） → 生成多空交易信号

---

## 完整流程图

```
巨潮资讯网 (cninfo.com.cn)
    │
    ▼
┌─────────────────────────────────────────────┐
│  pipeline/cninfo_fetcher.py                  │
│                                              │
│  1. 爬取当天全部公告（~2000 条）              │
│  2. 强信号关键词预筛选 → ~200 条              │
│     （按事件类型分类：业绩/分红/增持等）         │
│  3. 下载公告 PDF → 提取文本（pypdf）          │
│     （本地缓存，不重复下载）                     │
│  4. 按 event_type 分组 + 每批 ≤10 条           │
│  5. 调用 OpenRouter API 批量评分               │
│     基于 PDF 全文内容（截取前 2000 字）           │
│     只保留利多（score > 0）                    │
│  6. 按 score 降序输出                          │
└─────────────────────────────────────────────┘
    │
    ▼
  data/raw_json/ranking_YYYYMMDD.json
    │
    ▼
┌─────────────────────────────────────────────┐
│  run_daily.py                                │
│                                              │
│  1. 加载公告 JSON + 日线价格                  │
│  2. 构建因子（聚合 + 波动调整）                │
│  3. 风控（极值过滤 → Winsorize → Z-Score）    │
│  4. 事件研究 CAR（前5日/后3日/泄露检测）        │
│  5. IC 分析（IC_total / IC_post / IC_pre）    │
│  6. 泄露分析                                  │
│  7. Top-K 做多/做空信号                       │
└─────────────────────────────────────────────┘
    │
    ▼
  data/results/YYYYMMDD/
  ├── car_results_YYYYMMDD.csv
  ├── signal_long_YYYYMMDD.csv
  └── signal_short_YYYYMMDD.csv
```

---

## 快速开始

### 一键运行

```bash
cd /Users/skyler/workspace/stock_selection/announcement_alpha

# 昨天的公告 + LLM 评分 + 信号生成
python pipeline/cninfo_fetcher.py --run-daily

# 指定日期
python pipeline/cninfo_fetcher.py 2026-04-09 --run-daily
```

### 分步运行

```bash
# 只抓取不评分（调试用）
python pipeline/cninfo_fetcher.py 2026-04-09 --raw-only

# 只评分 + 跑信号（已有 raw 文件时）
python pipeline/cninfo_fetcher.py 2026-04-09 --force-score --run-daily

# 仅生成信号（已有 ranking JSON）
python run_daily.py

# 市场模式（需沪深300指数数据）
python run_daily.py --mode market --pre 7 --post 5 --top-k 30
```

### 环境要求

```bash
# 激活虚拟环境（必须）
cd /Users/skyler/workspace/stock_selection
source venv/bin/activate

# 依赖已安装：requests, pandas, yfinance, pypdf, openai
# 如需重新安装：
pip install requests pandas yfinance pypdf
```

### OpenRouter 配置

评分使用 OpenRouter API（`qwen/qwen3.5`），Key 从 `~/.openclaw/agents/main/agent/auth-profiles.json` 自动读取。

也可手动指定：

```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxx"
```

---

## 项目结构

```
announcement_alpha/
├── config.py                        # 统一配置（路径、参数、阈值）
├── run_daily.py                     # 信号生成入口（7步流水线）
├── backtest.py                      # 回测模块
│
├── pipeline/
│   ├── __init__.py
│   └── cninfo_fetcher.py            # ║ 巨潮爬取 + LLM 评分（数据入口）║
│
├── core/
│   ├── loader.py                    # 数据加载（公告JSON + 价格 + 指数）
│   ├── factor_builder.py            # 因子构建（聚合 + 波动调整）
│   ├── risk_model.py                # 风控（极值 + Winsorize + Z-Score）
│   ├── strategy.py                  # 信号生成（动态Top-K）
│   ├── llm_scorer.py                # ║ LLM 评分引擎 ║
│   ├── event_study_extended.py      # 事件研究（CAR pre/post/leakage）
│   └── event_study.py               # 简化版CAR
│
└── data/
    ├── raw_json/                    # ║ 公告评分 JSON ║ ranking_YYYYMMDD.json
    ├── market/                      # 市场指数（000300.csv）
    └── results/                     # 输出结果（按日期分目录）
        └── YYYYMMDD/
            ├── car_results_YYYYMMDD.csv
            ├── signal_long_YYYYMMDD.csv
            └── signal_short_YYYYMMDD.csv
```

---

## LLM 评分机制

### 工作原理（2026-04-12 重构）

评分基于 **PDF 全文内容**，而不是仅看标题。流程：

```
巨潮 API 返回标题列表（~2000条/天）
    ↓
STRONG_KEYWORDS 粗筛 → ~200条 + 按类型分类
    ↓
下载 PDF → pypdf 提取文本（前5页，截取2000字）
（本地缓存 data/pdf_cache/，不重复下载）
    ↓
按 event_type 分组，每批 ≤10 条
    ↓
OpenRouter API (qwen/qwen3.5) 批量评分 → 只保留利多项
    ↓
ranking_YYYYMMDD.json（score 降序排列）
```

### Token 优化策略

- 同类型公告分批发送（同一段 system prompt 复用）
- 每条公告 PDF 文本截取前 2000 字（关键信息在开头）
- 每批最多 10 条（max_tokens=4096）

### 评分 Prompt

```
你是A股量化公告分析器，根据公告PDF全文内容给公告评分。

评分规则：
- score 范围：-2.0 到 +2.0
- 利好信号：净利润增长超预期、高比例分红、回购/增持、重大订单、资产重组
- 利空信号：大幅亏损、减值、重要股东减持、重大诉讼/处罚
- 如果 PDF 内容不包含实质信息，跳过该公告
```

### OpenRouter 配置

Key 自动从 `~/.openclaw/agents/main/agent/auth-profiles.json` 读取，也可手动指定：

```bash
export OPENROUTER_API_KEY="sk-or-v1-xxxxx"
```

### 输出格式

```json
[
  {
    "code": "603869",
    "date": "2026-04-09",
    "title": "关于申请撤销其他风险警示的公告",
    "score": 2.0,
    "event_type": "其他",
    "confidence": 0.95,
    "label": "利多"
  }
]
```

### 自定义评分规则

修改提示词：`core/llm_scorer.py` → `SYSTEM_PROMPT`
修改粗筛词：`pipeline/cninfo_fetcher.py` → `STRONG_KEYWORDS`
修改模型：`core/llm_scorer.py` → `DEFAULT_MODEL`

---

## 策略逻辑

### 因子构建

```
score（LLM 评分）
    → 同日同股多条公告 → score 求和
    → 波动调整：factor = score / std(score_by_stock)
    → （Z-Score标准化留给风控模型）
```

### 风控模型

```
Raw Factor
    → 极值过滤：factor ∈ (-10, 10)
    → Winsorize：截面 5%/95% 分位数截断
    → Z-Score 标准化
```

### 事件研究 CAR

```
|---pre_window(5)---| EVENT |--post_window(3)--|
 CAR_pre（泄露检测）       │   CAR_post（纯净Alpha）
```

| 指标 | 含义 |
|------|------|
| IC_total | 因子整体预测能力 |
| IC_post | ⭐ 真正的 Alpha 能力 |
| IC_pre | ⚠️ 因子泄露程度 |
| Leakage | 事件前收益占总收益的比例 |

---

## 配置说明

所有参数集中于 `config.py`，运行时可通过 CLI 覆盖：

```bash
python run_daily.py --mode market     # 市场调整模式
python run_daily.py --pre 7 --post 5  # 更宽的事件窗口
python run_daily.py --top-k 30        # Top30做多/做空
```

---

## 每日自动运行

```bash
# crontab（周一至周五 15:30 CST 收盘后）
# 注意：需激活虚拟环境，或在脚本中指定完整 python 路径
30 15 * * 1-5 cd /Users/skyler/workspace/stock_selection && source venv/bin/activate && cd announcement_alpha && python pipeline/cninfo_fetcher.py --run-daily >> /tmp/alpha.log 2>&1
```
