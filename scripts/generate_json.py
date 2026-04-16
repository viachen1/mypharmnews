"""
PharmaPulse - JSON 数据输出模块
将处理后的新闻数据输出为标准 JSON 文件
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import DATA_DIR


def build_output(articles: list[dict], date_str: str = None) -> dict:
    """
    构建标准 JSON 输出格式（符合 PRD 附录 A 规范）
    """
    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)

    if not date_str:
        date_str = now.strftime("%Y-%m-%d")

    # 清理 article 字段，只保留规范字段
    clean_articles = []
    for a in articles:
        clean_articles.append({
            "id": a.get("id", ""),
            "title": a.get("title", ""),
            "summary_zh": a.get("summary_zh", ""),
            "source": a.get("source", "Unknown"),
            "source_url": a.get("source_url", ""),
            "published_at": a.get("published_at", ""),
            "category": a.get("category", "market"),
            "importance": a.get("importance", "low"),
            "region": a.get("region", "international"),
            "tags": a.get("tags", []),
        })

    output = {
        "date": date_str,
        "total": len(clean_articles),
        "generated_at": now.isoformat(),
        "stats": _build_stats(clean_articles),
        "articles": clean_articles,
    }

    return output


def _build_stats(articles: list[dict]) -> dict:
    """构建统计信息"""
    stats = {
        "total": len(articles),
        "by_category": {},
        "by_importance": {},
        "by_region": {},
    }

    for a in articles:
        cat = a["category"]
        imp = a["importance"]
        reg = a.get("region", "international")
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        stats["by_importance"][imp] = stats["by_importance"].get(imp, 0) + 1
        stats["by_region"][reg] = stats["by_region"].get(reg, 0) + 1

    return stats


def save_json(data: dict, date_str: str = None) -> Path:
    """
    保存 JSON 文件到 data/ 目录
    文件名格式：YYYY-MM-DD.json
    """
    if not date_str:
        date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    # 确保目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    filepath = DATA_DIR / f"{date_str}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[SAVE] {filepath}")
    print(f"   Total: {data['total']} articles")

    return filepath
