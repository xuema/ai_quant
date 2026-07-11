#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task1 PDF — quantitative trading Q&A + GitHub page content
Uses fpdf2 (lightweight, no PIL dependency)
"""
import os
from fpdf import FPDF

# ─── Config ────────────────────────────────────────────────────
BASE = "/Users/skyler/workspace/stock_selection/announcement_alpha/data/stock_analysis"
PDF_PATH = os.path.join(BASE, "Task1.pdf")
FONT_TTF = "/System/Library/Fonts/Hiragino Sans GB.ttc"
GITHUB = "https://xuema.github.io/ai_quant/index.html"

# ─── PDF class ─────────────────────────────────────────────────
class PDF(FPDF):
    # All text uses multi_cell only; avoid cell() to prevent x-position issues
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Heiti", "", 9)
        self.set_text_color(130, 130, 130)
        self.multi_cell(0, 8, f"量化交易分析报告 - Task 1 - Page {self.page_no()}", align="C")
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Heiti", "", 8)
        self.set_text_color(150, 150, 150)
        self.multi_cell(0, 10, "免责声明：本报告仅供参考，不构成投资建议。股市有风险，投资需谨慎。", align="C")

    def title_block(self):
        self.set_font("Heiti", "", 26)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 16, "量化交易分析报告", align="C")
        self.set_font("Heiti", "", 12)
        self.set_text_color(100, 100, 100)
        self.multi_cell(0, 10, "Task 1 - 理论问答与项目实践", align="C")
        self.ln(8)
        self.set_draw_color(100, 100, 100)
        self.line(25, self.get_y(), self.w - 25, self.get_y())
        self.ln(10)

    def section_title(self, text):
        self.set_font("Heiti", "", 16)
        self.set_text_color(50, 50, 120)
        self.multi_cell(0, 10, text)
        self.ln(4)

    def sub_title(self, text):
        self.set_font("Heiti", "", 12)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 8, text)
        self.ln(2)

    def body_text(self, text):
        self.set_font("Heiti", "", 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 7, text)
        self.ln(3)

    def bullet_list(self, items):
        self.set_font("Heiti", "", 11)
        self.set_text_color(40, 40, 40)
        for item in items:
            if item.startswith("  "):
                self.multi_cell(0, 7, "    " + item.strip())
            else:
                self.multi_cell(0, 7, "  • " + item)
        self.ln(2)

# ─── Build ────────────────────────────────────────────────────
def build():
    print("Building Task1.pdf...")
    os.makedirs(BASE, exist_ok=True)

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_font("Heiti", "", FONT_TTF, uni=True)
    pdf.add_font("Heiti", "B", FONT_TTF, uni=True)
    pdf.add_page()

    # ── Title ──
    pdf.title_block()

    # ══════════════════════════════════════════════════════════
    #  Question 1
    # ═══════════════════════════════════════════════════════════
    pdf.section_title("问题 1：量化交易的优势")
    pdf.body_text(
        "相较于传统手工操作交易的方法，量化交易具有以下显著优势："
    )

    advantages = [
        ("1. 纪律性与客观性",
         "严格执行预设策略，消除人性弱点（贪婪、恐惧、后悔、犹豫）的干扰。"
         "避免手动交易中的追涨杀跌、频繁止损等情绪化行为，保证每笔交易决策的客观性和稳定性。"),
        ("2. 高效性与执行速度",
         "计算机毫秒级下单执行，能抓住转瞬即逝的市场机会。程序可同时监控数十个品种、"
         "数百只个股、多个市场，覆盖范围远超人工能力。"),
        ("3. 海量数据处理能力",
         "实时分析多年历史数据与实时行情，运用统计模型、机器学习等方法识别复杂市场模式，"
         "手工交易无法处理如此规模的信息维度。"),
        ("4. 精确的风险控制",
         "自动计算仓位大小（如凯利公式）和风险敞口，严格执行止损止盈规则，"
         "将单笔损失控制在预设范围内，实现系统化风险管理。"),
        ("5. 策略回测与验证",
         "可在历史数据上回溯测试策略表现，评估收益率、最大回撤、夏普比率等关键指标，"
         "通过参数优化找到最优配置，降低盲目试错成本。"),
        ("6. 可复制性与可扩展性",
         "策略代码可一键复制部署，支持多账户、多市场并行运行，"
         "实现投资能力的规模化扩展。"),
    ]
    for heading, desc in advantages:
        pdf.sub_title(heading)
        pdf.body_text(desc)

    # ═══════════════════════════════════════════════════════════
    #  Question 2
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("问题 2：基本概念解释")

    pdf.sub_title("K 线（蜡烛图）")
    pdf.body_text(
        "K线起源于日本米市，是记录单根交易周期（通常为一天）内四个关键价格的图表：\n"
        "  • 开盘价：当日交易开始时的价格\n"
        "  • 收盘价：当日交易结束时的价格\n"
        "  • 最高价：当日交易中的最高价格\n"
        "  • 最低价：当日交易中的最低价格\n\n"
        "K线由「实体」和「影线」组成：\n"
        "  • 实体：开盘价与收盘价之间的矩形区域\n"
        "    - 红色（阳线）：收盘价 > 开盘价，表示上涨\n"
        "    - 绿色（阴线）：收盘价 < 开盘价，表示下跌\n"
        "  • 影线：实体上方和下方的细线（上影线连接最高价，下影线连接最低价）\n\n"
        "K线组合形态（十字星、锤子线、吞没形态等）常被用于判断市场趋势反转或延续信号。"
    )

    pdf.sub_title("基本面分析")
    pdf.body_text(
        "基本面分析是通过评估公司内在价值来判断股票投资价值的方法。\n\n"
        "宏观层面关注：GDP增速、通胀率、货币政策、行业政策、资金流向等。\n\n"
        "微观层面（公司分析）关注：\n"
        "  • 财务报表：利润表、资产负债表、现金流量表\n"
        "  • 盈利能力：毛利率、净利率、ROE（净资产收益率）\n"
        "  • 成长性：营收增长率、净利润增长率\n"
        "  • 估值指标：PE（市盈率）、PB（市净率）、PS（市销率）\n"
        "  • 竞争优势：护城河、技术壁垒、品牌价值\n\n"
        "核心逻辑：股票市场价格围绕内在价值波动，低估时买入，高估时卖出。"
    )

    pdf.sub_title("技术面分析")
    pdf.body_text(
        "技术面分析是通过研究历史价格和成交量数据来预测未来价格走势的方法。\n\n"
        "三大基本假设：\n"
        "  ① 市场行为包容消化一切\n"
        "  ② 价格以趋势方式演变\n"
        "  ③ 历史会重演\n\n"
        "主要分析工具：\n"
        "  • 趋势分析：移动平均线 MA5/MA10/MA20/MA60\n"
        "  • 动量指标：MACD（DIF/DEA/柱体）、RSI、KDJ\n"
        "  • 通道指标：布林带（Bollinger Bands）\n"
        "  • 量价分析：成交量变化与价格走势的相互验证\n\n"
        "技术面常用于判断买卖时机和设置止损压力位。但基于历史统计规律，不能保证未来表现，"
        "需结合基本面综合判断。"
    )

    # ═══════════════════════════════════════════════════════════
    #  Question 3
    # ═══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("问题 3：GitHub 项目展示")

    pdf.body_text("项目在线报告地址（GitHub Pages）：")
    pdf.set_font("Heiti", "B", 12)
    pdf.set_text_color(20, 60, 180)
    pdf.multi_cell(0, 8, GITHUB, link=GITHUB)
    pdf.ln(6)

    pdf.set_text_color(40, 40, 40)
    pdf.body_text(
        "该项目是光迅科技（002281.SZ）的技术分析报告，分析周期 2025-07-03 至 2026-07-03，"
        "共计 243 个交易日数据。"
    )

    pdf.sub_title("页面包含以下模块：")
    pdf.bullet_list([
        "K线走势图 + 均线系统（MA5/MA10/MA20/MA60）+ 布林带",
        "MACD 动量指标图表（DIF/DEA/柱体）",
        "RSI 相对强弱指标图表（RSI6/RSI14）",
        "技术信号解读：趋势/MACD/RSI/布林带 四维度研判",
        "基本面分析：公司概况（光通信器件龙头地位）、核心驱动因素",
        "综合研判与操作建议：短期观望，中期分批建仓",
        "风险提示：估值、竞争、技术迭代、市场情绪等六大风险",
        "总结：基本面长期看好，短期估值偏高，需等待技术面企稳信号",
    ])

    pdf.sub_title("技术实现：")
    pdf.bullet_list([
        "数据源：akshare（免费A股数据接口）",
        "图表库：ECharts 5.4.3（交互式图表）",
        "前端：Bootstrap 5.3.0 + 自定义样式",
        "部署：GitHub Pages 静态托管",
    ])

    pdf.ln(4)
    pdf.set_font("Heiti", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 6,
        "注：PDF 为静态格式，无法展示完整交互图表。"
        "请访问上方 GitHub Pages 链接在线查看带有交互式 K线、MACD、RSI 图表的完整报告。"
    )

    pdf.output(PDF_PATH)
    print(f"✓ Task1.pdf 已生成：{PDF_PATH}")
    print(f"  大小：{os.path.getsize(PDF_PATH)/1024:.0f} KB")
    print(f"  总页数：{pdf.pages_count}")

if __name__ == "__main__":
    build()
