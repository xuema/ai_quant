# 光迅科技(002281.SZ) 技术分析系统

## 📊 项目概述

完整的技术分析系统，包含数据质量诊断、6大核心技术指标计算、详细的公式推导与可视化展示。

##  快速开始

### 1. 环境要求

```bash
Python >= 3.8
pip install pandas numpy matplotlib jupyter
```

### 2. 项目结构

```
technical_analysis_project/
├── README.md                          # 本项目说明
├── Project_Spec.md                    # 项目规范文档
├── requirements.txt                   # 依赖包
├── .gitignore
│
├── data/
│   └── 002281_daily.csv              # 原始数据 (243天)
│
├── notebooks/
│   └── 002281_technical_analysis.ipynb  # 主分析笔记本
│
└── src/
    └── indicators.py                  # 可复用指标函数库
```

### 3. 运行笔记本

```bash
cd technical_analysis_project
jupyter notebook notebooks/002281_technical_analysis.ipynb
```

或者使用 Jupyter Lab:

```bash
jupyter lab notebooks/002281_technical_analysis.ipynb
```

## 📈 技术指标说明

### 包含的指标

1. **RSI** (相对强弱指标) - 动量震荡器，识别超买超卖
2. **MACD** (指数平滑异同移动平均线) - 趋势跟踪动量指标
3. **Bollinger Bands** (布林带) - 波动率通道，识别价格边界
4. **Williams %R** (威廉指标) - 超买超卖震荡器
5. **ATR** (真实波幅) - 波动性度量，用于仓位管理
6. **CR** (能量指标) - 多空力量对比

## 🎯 分析产出

执行 `002281_technical_analysis.ipynb` 后，你将获得:

- ✅ 数据质量诊断报告
- ✅ 6大指标的完整计算过程
- ✅ 交互式可视化图表
- ✅ 综合研判与投资建议

## 📝 注意事项

- 所有指标函数在 `src/indicators.py` 中提供，可在其他项目复用
- 笔记本中的公式说明与业界标准一致
- 建议结合基本面分析进行综合判断

##  扩展开发

后续可添加的指标:
- KD/KDJ (随机指标)
- OBV (能量潮)
- CMF (资金流量)
- 策略回测框架

---

**免责声明**: 本项目仅供学习与研究，不构成任何投资建议。
