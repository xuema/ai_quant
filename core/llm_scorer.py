"""
LLM Announcement Scorer — 用大模型（OpenRouter）给公告评分。

Input:  公告列表 JSON（每条含 code, title, pdf_text, event_type 等）
Output: 带 score 的公告 JSON（只输出利多项），格式与 run_daily.py 兼容

调用方式：
    通过 OpenRouter API 直连（无需 Oracle CLI）。
"""
import json
import os
import time
import re
import urllib.request
import urllib.error


# ================================================================
# OpenRouter 配置
# ================================================================
# 优先从环境变量取，否则从 OpenClaw auth-profiles 读取
DEFAULT_MODEL = "qwen/qwen3.6-plus"
API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_openrouter_key():
    """获取 OpenRouter API Key。"""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key

    # 从 OpenClaw auth-profiles 读取
    profiles_path = os.path.expanduser(
        "~/.openclaw/agents/main/agent/auth-profiles.json"
    )
    if os.path.exists(profiles_path):
        try:
            with open(profiles_path, "r") as f:
                data = json.load(f)
            key = (data.get("profiles", {})
                   .get("openrouter:default", {})
                   .get("key"))
            if key:
                return key
        except Exception:
            pass

    raise RuntimeError(
        "找不到 OpenRouter API Key。"
        "请设置环境变量 OPENROUTER_API_KEY 或确保 ~/.openclaw/agents/main/agent/auth-profiles.json 存在。"
    )


# ================================================================
# 评分 Prompt（精简版，优化 token 效率）
# ================================================================
SYSTEM_PROMPT = """你是A股量化公告分析器，根据公告PDF全文内容给公告评分。

评分规则：
- score 范围：-2.0 到 +2.0，保留1位小数
- score > 0 利多，score < 0 利空，score ≈ 0 中性
- 利好信号：净利润增长超预期、高比例分红、回购/增持、重大订单、资产重组
- 利空信号：大幅亏损、减值、重要股东减持、重大诉讼/处罚
- confidence：0.0–1.0，信息越明确越高
- reason：用一句话（≤15字）说明为什么利多/利空
- holding_days：基于该公告的影响力，给出建议持仓周期（整数天数），通常 3~30 天

输出要求：
- 每条公告只输出一行 JSON 对象
- 必须含：code、score、label、event_type、confidence、reason、holding_days
- 只输出合法 JSON 数组，不要任何解释文字
- 如果 PDF 内容不包含实质信息，跳过该公告

输出格式：
[
  {
    "code": "000725",
    "score": 1.5,
    "label": "利多",
    "event_type": "分红",
    "confidence": 0.85,
    "reason": "净利润增长40%，超预期",
    "holding_days": 14
  }
]"""


def _build_user_prompt(batch: list) -> str:
    """为一批公告构建 prompt，压缩 PDF 文本以节省 tokens。"""
    lines = [f"请对以下 {len(batch)} 条公告的 PDF 全文内容逐条评分：", ""]
    for i, item in enumerate(batch, 1):
        code = item.get("code", "?")
        title = item.get("title", "")
        event = item.get("event_type", "其他")
        # 截取 PDF 文本前 2000 字（关键信息通常在开头）
        full_text = item.get("pdf_text", "")
        truncated = full_text[:2000] if len(full_text) > 2000 else full_text
        lines.append(f"### {i}. [{code}] {title}")
        lines.append(f"类型: {event}")
        lines.append(f"内容摘要:\n{truncated}")
        lines.append("")
    return "\n".join(lines)


def _call_openrouter(messages: list, model: str = DEFAULT_MODEL,
                     retries: int = 5) -> str:
    """直接调用 OpenRouter API，带指数退避重试。

    捕获所有网络异常（超时、连接重置、IncompleteRead 等），
    每次失败后 2^attempt 秒重试。
    """
    key = _get_openrouter_key()
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 8192,
    }).encode("utf-8")

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                API_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                    "HTTP-Referer": "https://openclaw.ai",
                    "X-Title": "announcement_alpha",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            err_body = ""
            if hasattr(e, "read"):
                try:
                    err_body = e.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    pass
            wait = min(2 ** attempt, 30)
            if attempt < retries:
                print(
                    f"  ⚠️ API [{type(e).__name__}] 第 {attempt}/{retries} 次，"
                    f"{wait}s 后重试: {e}"
                )
                time.sleep(wait)
                continue
            print(
                f"  ❌ API [{type(e).__name__}] 最终失败 "
                f"(第 {attempt}/{retries} 次): {e}"
            )
            raise
    return None


def _extract_json(text: str):
    """从 LLM 输出中提取 JSON 数组。"""
    # 找 markdown 代码块
    m = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 直接找 JSON 数组
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    # 清理前缀
    stripped = re.sub(r'^[^{\[\n]*', '', text).strip()
    m = re.search(r'\[.*\]', stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    print(f"  ⚠️ JSON 提取失败，原文前 200 字: {text[:200]}")
    return None


# ================================================================
# 主函数
# ================================================================
def score_announcements(announcements_path: str, output_path: str,
                        batch_size: int = 10, model: str = DEFAULT_MODEL,
                        retries: int = 5) -> list:
    """
    对一批（或多批）公告进行 LLM 评分。

    支持两种输入格式：
    1. 新格式：每条含 code, title, pdf_text, event_type
    2. 旧格式（兼容）：每条含 code, title — PDF 文本由上层调用方填充

    📌 断点续跑：
    - 自动从 checkpoint 文件恢复（_scoring_checkpoint_*.json）
    - 也检查 output_path 里已保存的结果
    - 每个 batch 完成后立即保存 checkpoint
    - 中断后重新运行会接上中断的地方继续
    """
    with open(announcements_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if not raw_data:
        print("⚠️ 没有公告需要评分")
        return []

    # 生成 checkpoint 文件路径（同目录）
    ckpt_path = os.path.join(
        os.path.dirname(output_path),
        "_scoring_checkpoint_" + os.path.basename(output_path).rsplit(".", 1)[0] + ".json"
    )

    # 恢复已有评分：优先 checkpoint，其次 output 文件，再次已生成的 CSV
    previously_scored = {}
    
    # 1. 检查 checkpoint（最详细的进度）
    if os.path.exists(ckpt_path):
        try:
            with open(ckpt_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict) and "scored" in saved:
                for item in saved["scored"]:
                    code = str(item.get("code", ""))
                    if code:
                        previously_scored[code] = item
                print(f"📂 从 checkpoint 恢复: {len(previously_scored)} 条")
        except Exception as e:
            print(f"  ⚠️ checkpoint 读取失败: {e}")

    # 2. 检查 output 文件（已保存的部分结果）
    if os.path.exists(output_path) and output_path.endswith(".json"):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, list):
                for item in existing:
                    code = str(item.get("code", ""))
                    if code and code not in previously_scored:
                        previously_scored[code] = item
                print(f"📂 从 output 文件额外恢复: "
                       f"{len([c for c in existing if str(c.get('code','')) not in [pc for pc in previously_scored]])} 条（去重后）")
        except Exception:
            pass

    # 3. 检查已生成的 CSV 文件（最终输出）
    csv_path = output_path.replace(".json", ".csv")
    if os.path.exists(csv_path):
        import pandas as pd
        try:
            df = pd.read_csv(csv_path, dtype={"code": str})
            df["code"] = df["code"].str.zfill(6)
            for _, row in df.iterrows():
                code = str(row.get("code", ""))
                if code and code not in previously_scored:
                    previously_scored[code] = row.to_dict()
            print(f"📂 从 CSV 恢复: {len(previously_scored)} 条")
        except Exception:
            pass

    # 过滤掉已评分的
    remaining = [item for item in raw_data
                 if str(item.get("code", "")) not in previously_scored]
    if not remaining:
        print("✅ 所有公告均已评分完毕")
        return list(previously_scored.values())
    print(f"📊 总公告: {len(raw_data)} 条，已评分: {len(previously_scored)} 条，待评分: {len(remaining)} 条")

    # 按 event_type 分组，同类型一起评分（节省 prompt tokens）
    grouped: dict[str, list] = {}
    for item in remaining:
        et = item.get("event_type", "其他")
        grouped.setdefault(et, []).append(item)

    all_scored = list(previously_scored.values())
    total = len(remaining)
    done = 0

    def save_checkpoint():
        """保存 checkpoint（所有已评分的）"""
        saved = {"scored": all_scored}
        try:
            with open(ckpt_path, "w", encoding="utf-8") as f:
                json.dump(saved, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  ⚠️ checkpoint 保存失败: {e}")

    for et, items in grouped.items():
        print(f"\n📦 事件类型 [{et}]: {len(items)} 条公告")

        # 分批处理
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            prompt = _build_user_prompt(batch)

            scored_batch = None
            try:
                resp = _call_openrouter([
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ], model=model, retries=retries)

                scored_batch = _extract_json(resp)

            except Exception as e:
                print(f"  ❌ 该批评分最终失败: {e}，跳过 {len(batch)} 条")

            if scored_batch is not None:
                for s in scored_batch:
                    code = str(s.get("code", ""))
                    orig = next((x for x in batch if str(x.get("code", "")) == code), None)
                    if orig:
                        s.setdefault("name", orig.get("name", ""))
                        s.setdefault("title", orig.get("title", ""))
                        s.setdefault("date", orig.get("date", ""))
                        s.setdefault("event_type", orig.get("event_type", "其他"))
                    s.setdefault("label", "利多" if s.get("score", 0) > 0 else "利空")
                    s.setdefault("reason", "")
                    s.setdefault("name", "")
                    s.setdefault("holding_days", 0)
                all_scored.extend(scored_batch)
                print(f"  ✅ {len(scored_batch)} 条已评分")
            else:
                print(f"  ⚠️ 该批 JSON 解析失败，跳过 {len(batch)} 条")

            done += len(batch)
            print(f"  进度: {done}/{total}")

            # 每个 batch 完成后保存 checkpoint
            if scored_batch is not None:
                save_checkpoint()

    # 最终结果：只保留利多
    bullish = [s for s in all_scored if s.get("score", 0) > 0]
    bullish = sorted(bullish, key=lambda x: x.get("score", 0), reverse=True)
    print(f"\n✅ 总计: {len(all_scored)} 条已评分，利多 {len(bullish)} 条")

    if bullish:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bullish, f, ensure_ascii=False, indent=2)
        print(f"📁 输出: {output_path}")

    # 清理 checkpoint 文件（评分已完成）
    if os.path.exists(ckpt_path):
        os.remove(ckpt_path)

    return all_scored
