"""
LLM Announcement Scorer — 用大模型（OpenAI GPT-5.4 Pro via Oracle CLI）给公告评分。

Input:  一个 JSON 文件，包含公告列表（有 title/code/name/date）
Output: 带 score 的公告 JSON（只输出利多项），格式与 run_daily.py 兼容

调用方式：
    通过 Oracle CLI（已配置，无需 API Key）：
        oracle ask -p "<prompt>" -f <公告文件>
"""
import subprocess
import json
import os
import time
import re


# ================================================================
# LLM 评分 Prompt
# ================================================================
SYSTEM_PROMPT = """你是一个A股量化公告分析器。请对以下公告列表逐条评分。

评分规则：
- score 范围：-2.0 到 +2.0
- 利多 = score > 0，利空 = score < 0，中性 = score ≈ 0
- 分红/派息/业绩预告超预期 = 高利多
- 减持/减值/亏损 = 利空
- 事件类型：业绩/分红/增持/回购/股权激励/减持/减值/重组/订单/其他

输出要求：
- 只输出 利多（score > 0） 的公告
- 只输出合法 JSON 数组，不允许任何解释性文字
- 每条必须包含：date, code, title, label, score, event_type, confidence

输出格式：
[
  {
    "date": "2026-04-09",
    "code": "000725",
    "title": "原公告标题",
    "label": "利多",
    "score": 1.5,
    "event_type": "分红",
    "confidence": 0.85
  }
]
"""


def score_announcements(announcements_path: str, output_path: str,
                        retries: int = 2) -> list:
    """
    调用 Oracle CLI 对公告评分。

    Parameters
    ----------
    announcements_path : str
        输入 JSON 文件路径（每条包含 code, name, title, date）
    output_path : str
        输出 JSON 文件路径
    retries : int
        失败重试次数

    Returns
    -------
    list of scored announcements (利多 only)
    """
    with open(announcements_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if not raw_data:
        print("⚠️ 没有公告需要评分")
        return []

    # ---- 构建精简输入（只传 LLM 需要的字段） ----
    prompt_lines = [SYSTEM_PROMPT, "", f"以下是 {len(raw_data)} 条公告，请逐条评分：", ""]
    for i, item in enumerate(raw_data, 1):
        prompt_lines.append(
            f"{i}. [{item.get('code','?')}] {item.get('title','')}"
        )
    prompt_text = "\n".join(prompt_lines)

    # ---- 调用 Oracle CLI ----
    for attempt in range(1, retries + 1):
        print(f"🧠 LLM 评分中 (第 {attempt} 次尝试)...")
        try:
            result = subprocess.run(
                ["oracle", "ask", "-p", prompt_text, "-f", announcements_path],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                print(f"  ⚠️ Oracle CLI 错误: {result.stderr[:200]}")
                if attempt < retries:
                    time.sleep(3)
                    continue
                return []

            # ---- 从输出中提取 JSON ----
            output = result.stdout.strip()
            scored = _extract_json(output)

            if scored is not None:
                # 保存结果
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(scored, f, ensure_ascii=False, indent=2)

                bullish = [s for s in scored if s.get("score", 0) > 0]
                print(f"  ✅ 评分完成：共 {len(scored)} 条，利多 {len(bullish)} 条")
                print(f"  📁 输出: {output_path}")
                return scored
            else:
                print(f"  ⚠️ 无法解析 LLM 输出的 JSON")
                if attempt < retries:
                    print(f"  🔄 3秒后重试...")
                    time.sleep(3)
                    continue
                return []

        except subprocess.TimeoutExpired:
            print(f"  ⚠️ 超时")
            if attempt < retries:
                time.sleep(3)
                continue
            return []
        except Exception as e:
            print(f"  ❌ 评分失败: {e}")
            return []

    return []


def _extract_json(text: str):
    """从 LLM 输出中提取 JSON 数组（容忍各种格式噪声）。"""

    # 策略1: 找 markdown 代码块
    import re
    m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 策略2: 直接找 JSON 数组
    m = re.search(r'\[(.*)\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    # 策略3: 清理常见前缀后重试
    stripped = re.sub(r'^[^{\[\n]*', '', text)
    stripped = re.sub(r'```json\s*', '', stripped)
    stripped = re.sub(r'\s*```\s*$', '', stripped)
    stripped = stripped.strip()

    m = re.search(r'\[.*\]', stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    print(f"  ⚠️ JSON 提取失败，原文前 300 字: {text[:300]}")
    return None
