"""
PharmaPulse - 主入口脚本
串联完整数据流：抓取 -> 处理 -> AI摘要 -> 输出 JSON
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# 确保可以导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_news import fetch_all
from process import process_articles
from ai_summary import batch_generate_summaries
from generate_json import build_output, save_json


def run(skip_ai: bool = False):
    """
    运行完整的数据处理流水线

    参数:
        skip_ai: 是否跳过 AI 摘要生成（用于测试时节省 API 调用）
    """
    tz_cn = timezone(timedelta(hours=8))
    today = datetime.now(tz_cn).strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"  PharmaPulse Data Pipeline - {today}")
    print("=" * 60)

    # -- Step 1: 数据抓取 --
    raw_articles = fetch_all()

    if not raw_articles:
        print("\n[ERROR] 未获取到任何数据，请检查网络连接和数据源配置")
        return

    # -- Step 2: 数据处理（去重、过滤、分类、评分）--
    processed_articles = process_articles(raw_articles)

    if not processed_articles:
        print("\n[ERROR] 过滤后无有效数据，请检查关键词配置")
        return

    # -- Step 3: AI 中文摘要生成 --
    if skip_ai:
        print("\n[SKIP] 跳过 AI 摘要生成 (--skip-ai 模式)")
        for a in processed_articles:
            a["summary_zh"] = f"(待生成摘要) {a['title'][:80]}"
    else:
        processed_articles = batch_generate_summaries(processed_articles)

    # -- Step 4: 输出 JSON --
    output_data = build_output(processed_articles, today)
    filepath = save_json(output_data, today)

    # -- Step 5: 生成数据索引 --
    try:
        from build_index import save_index
        print("\n[Step 5] 生成数据索引...")
        save_index()
    except ImportError:
        print("\n[WARN] build_index 模块不可用，跳过索引生成")
    except Exception as e:
        print(f"\n[WARN] 索引生成失败: {e}")

    # -- 完成 --
    print("\n" + "=" * 60)
    print(f"  [DONE] 共处理 {output_data['total']} 条新闻")
    print(f"  [FILE] {filepath}")
    print(f"  [CATEGORY] {output_data['stats']['by_category']}")
    print(f"  [IMPORTANCE] {output_data['stats']['by_importance']}")
    print(f"  [REGION] {output_data['stats'].get('by_region', {})}")
    print("=" * 60)


if __name__ == "__main__":
    # 支持命令行参数
    skip = "--skip-ai" in sys.argv
    run(skip_ai=skip)
