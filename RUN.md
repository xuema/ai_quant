# Announcement Alpha — 日更完整流程

一键运行（爬取 + LLM 评分 + 信号生成 + CAR 分析）：

```bash
cd /Users/skyler/workspace/stock_selection/announcement_alpha

# 默认昨天的公告
python pipeline/cninfo_fetcher.py --run-daily

# 指定日期
python pipeline/cninfo_fetcher.py 2026-04-09 --run-daily

# 分步执行
python pipeline/cninfo_fetcher.py 2026-04-09      # 爬取 + 评分
python run_daily.py                                 # 跑信号
```

## 完整链路

```
巨潮资讯网 (cninfo.com.cn)
    ↓ 爬取
pipeline/cninfo_fetcher.py
    ↓ LLM 评分（Oracle CLI）
data/raw_json/ranking_YYYYMMDD.json
    ↓ run_daily.py 因子 + CAR + 信号
data/results/YYYYMMDD/
  ├── car_results_YYYYMMDD.csv
  ├── signal_long_YYYYMMDD.csv
  └── signal_short_YYYYMMDD.csv
```
