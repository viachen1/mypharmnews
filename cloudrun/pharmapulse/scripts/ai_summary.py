"""
PharmaPulse - AI 中文摘要生成模块
使用 DeepSeek API（兼容 OpenAI SDK）
"""
from __future__ import annotations

import time
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, SUMMARY_PROMPT


def create_client() -> OpenAI | None:
    """创建 DeepSeek API 客户端"""
    if not DEEPSEEK_API_KEY:
        print("  [SKIP] DEEPSEEK_API_KEY 未配置，跳过 AI 摘要生成")
        return None

    return OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
    )


def generate_summary(client: OpenAI, title: str, content: str) -> str:
    """为单条新闻生成中文摘要"""
    # 截断内容，避免 token 过多
    content_truncated = content[:1500] if content else "无详细内容"

    prompt = SUMMARY_PROMPT.format(title=title, content=content_truncated)

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "你是一位专业的医药行业新闻编辑，擅长将英文医药新闻翻译并概括为简洁准确的中文摘要。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
        return summary
    except Exception as e:
        print(f"     [FAIL] AI summary error: {e}")
        return _fallback_summary(title)


def _fallback_summary(title: str) -> str:
    """当 AI 不可用时，生成简单的回退摘要"""
    return f"(Summary pending) {title}"


def batch_generate_summaries(articles: list[dict], batch_delay: float = 0.5) -> list[dict]:
    """
    批量为文章生成 AI 中文摘要
    - 有 API Key 时调用 DeepSeek 生成
    - 无 Key 时使用回退方案
    """
    print("[AI] 开始生成中文摘要...\n")

    client = create_client()

    total = len(articles)
    success_count = 0

    for i, article in enumerate(articles):
        title = article["title"]
        content = article.get("content", "")

        print(f"   [{i + 1}/{total}] {title[:50]}...")

        if client:
            summary = generate_summary(client, title, content)
            time.sleep(batch_delay)  # 请求间隔，避免限速
        else:
            summary = _fallback_summary(title)

        article["summary_zh"] = summary
        success_count += 1

    print(f"\n[DONE] 摘要生成完成: {success_count}/{total}\n")
    return articles
