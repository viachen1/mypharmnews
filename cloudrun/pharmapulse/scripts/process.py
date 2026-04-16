"""
PharmaPulse - 数据处理模块
去重、关键词过滤、自动分类、重要度评分
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from config import INCLUDE_KEYWORDS, EXCLUDE_KEYWORDS, CATEGORY_RULES, IMPORTANCE_RULES

# ── 国内来源白名单（来源名命中即判定为国内） ──────────
_DOMESTIC_SOURCES = {
    "东方财富", "新浪财经", "新浪医药", "智慧芽", "摩熵医药", "新华网", "华尔街见闻",
    "21财经", "财联社", "证券之星", "医药网", "经济日报", "人民日报",
    "财经号", "观点网", "每日经济新闻", "ByDrug", "客观日本",
    "Jiemian.com", "thepaper.cn", "china.caixin.com", "phirda.com",
    "丁香园", "生物谷", "医药魔方", "药明康德", "米内网", "赛柏蓝",
    "健康界", "中国医药报", "药智网", "医谷", "动脉网", "亿欧健谈",
    "36氪", "界面新闻", "澎湃新闻", "财新", "中国证券报", "上海证券报",
    "证券时报", "第一财经", "经济观察报", "南方都市报", "央视新闻",
    "光明网", "中国新闻网", "环球网", "搜狐健康", "腾讯健康",
    "网易健康", "凤凰网健康", "中文媒体",
}

# 国际来源白名单
_INTERNATIONAL_SOURCES = {
    "FDA", "STAT News", "BioPharma Dive", "FiercePharma", "Reuters",
    "EMA", "WHO", "NIH", "Bloomberg", "CNBC", "The Wall Street Journal",
    "Endpoints News", "Evaluate", "Scrip", "Pink Sheet", "Pharmalot",
    "BioSpace", "GEN", "Nature", "Science", "The Lancet", "NEJM",
    "BMJ", "JAMA", "Medscape", "Healio",
}


def _classify_region(article: dict) -> str:
    """
    判断新闻属于 domestic（国内）还是 international（国际）。
    策略：
    1. 来源名精确匹配白名单
    2. 标题中含中文字符占比 > 30% → 国内
    3. 默认国际
    """
    source = article.get("source", "")

    # 1. 来源白名单匹配
    if source in _DOMESTIC_SOURCES:
        return "domestic"
    if source in _INTERNATIONAL_SOURCES:
        return "international"

    # 2. 来源名包含中文 → 国内
    if any('\u4e00' <= c <= '\u9fff' for c in source):
        return "domestic"

    # 3. 标题中文字符占比
    title = article.get("title", "")
    if title:
        cn_chars = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
        if cn_chars / max(len(title), 1) > 0.3:
            return "domestic"

    return "international"


def generate_id(title: str) -> str:
    """根据标题生成唯一 ID"""
    return hashlib.md5(title.strip().lower().encode("utf-8")).hexdigest()[:12]


def deduplicate(articles: list[dict], threshold: float = 0.80) -> list[dict]:
    """
    去重逻辑：
    1. 标题完全相同 -> 去重
    2. 标题相似度 > threshold -> 保留最早来源
    """
    print("[DEDUP] 去重处理...")
    seen_hashes: set[str] = set()
    seen_titles: list[str] = []
    unique = []

    for article in articles:
        title = article["title"].strip()
        if not title:
            continue

        # 精确去重：标题哈希
        title_hash = hashlib.md5(title.lower().encode("utf-8")).hexdigest()
        if title_hash in seen_hashes:
            continue
        seen_hashes.add(title_hash)

        # 模糊去重：相似度检查
        is_dup = False
        for existing_title in seen_titles:
            similarity = SequenceMatcher(None, title.lower(), existing_title.lower()).ratio()
            if similarity > threshold:
                is_dup = True
                break

        if not is_dup:
            seen_titles.append(title)
            unique.append(article)

    removed = len(articles) - len(unique)
    print(f"   {len(articles)} -> {len(unique)} (removed {removed} duplicates)")
    return unique


def filter_by_keywords(articles: list[dict]) -> list[dict]:
    """
    关键词过滤：
    - 必须包含至少一个医药相关词
    - 不能包含排除词
    """
    print("[FILTER] 关键词过滤...")
    filtered = []

    for article in articles:
        text = (article["title"] + " " + article.get("content", "")).lower()

        # 检查排除词
        if any(kw in text for kw in EXCLUDE_KEYWORDS):
            continue

        # 检查包含词（至少命中一个）
        if any(kw in text for kw in INCLUDE_KEYWORDS):
            filtered.append(article)

    removed = len(articles) - len(filtered)
    print(f"   {len(articles)} -> {len(filtered)} (filtered {removed} irrelevant)")
    return filtered


def classify(article: dict) -> str:
    """
    自动分类：基于关键词规则匹配
    返回: regulatory | clinical | corporate | market
    """
    text = (article["title"] + " " + article.get("content", "")).lower()

    scores = {}
    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for kw in keywords if kw in text)
        scores[category] = score

    # 返回得分最高的分类；如果都没命中，默认 "market"
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "market"
    return best


def rate_importance(article: dict) -> str:
    """
    重要度评分：基于关键词规则
    返回: high | medium | low
    """
    text = (article["title"] + " " + article.get("content", "")).lower()

    # 先检查高重要度
    for kw in IMPORTANCE_RULES["high"]:
        if kw in text:
            return "high"

    # 再检查中重要度
    for kw in IMPORTANCE_RULES["medium"]:
        if kw in text:
            return "medium"

    return "low"


def process_articles(raw_articles: list[dict]) -> list[dict]:
    """
    完整处理流水线：去重 -> 过滤 -> 分类 -> 评分 -> 生成ID
    """
    print("\n[PROCESS] 开始处理数据...\n")

    # Step 1: 去重
    articles = deduplicate(raw_articles)

    # Step 2: 关键词过滤
    articles = filter_by_keywords(articles)

    # Step 3: 分类 + 评分 + 地域判断 + 生成 ID
    print("[CLASSIFY] 分类 & 评分 & 地域判断...")
    for article in articles:
        article["id"] = generate_id(article["title"])
        article["category"] = classify(article)
        article["importance"] = rate_importance(article)
        article["region"] = _classify_region(article)
        article["summary_zh"] = ""  # 占位，后续 AI 生成
        article["tags"] = _extract_tags(article)

    # 按重要度排序：high -> medium -> low
    importance_order = {"high": 0, "medium": 1, "low": 2}
    articles.sort(key=lambda a: importance_order.get(a["importance"], 2))

    # 统计
    cats = {}
    imps = {}
    regions = {}
    for a in articles:
        cats[a["category"]] = cats.get(a["category"], 0) + 1
        imps[a["importance"]] = imps.get(a["importance"], 0) + 1
        regions[a["region"]] = regions.get(a["region"], 0) + 1

    print(f"\n[RESULT] 处理完成，共 {len(articles)} 条")
    print(f"   Category: {cats}")
    print(f"   Importance: {imps}")
    print(f"   Region: {regions}\n")

    return articles


def _extract_tags(article: dict) -> list[str]:
    """从标题和内容中提取标签（公司名、药物名等常见实体）"""
    text = article["title"] + " " + article.get("content", "")

    # 常见医药公司名
    companies = [
        # 国际药企
        "Pfizer", "Moderna", "Johnson & Johnson", "AstraZeneca", "Novartis",
        "Roche", "Merck", "AbbVie", "Eli Lilly", "Sanofi", "GSK",
        "Bristol Myers Squibb", "Amgen", "Gilead", "Regeneron", "BioNTech",
        "Novo Nordisk", "Takeda", "Bayer", "Biogen",
        # 中国药企
        "恒瑞医药", "百济神州", "信达生物", "君实生物", "药明康德",
        "药明生物", "复星医药", "石药集团", "中国生物制药", "翰森制药",
        "科伦药业", "华东医药", "正大天晴", "齐鲁制药", "扬子江药业",
        "先声药业", "荣昌生物", "康方生物", "和黄医药", "再鼎医药",
        "贝达药业", "亚盛医药", "诺诚健华", "基石药业", "传奇生物",
    ]

    # 常见监管机构
    agencies = [
        "FDA", "EMA", "NMPA", "WHO", "CDC", "NIH",
        "国家药监局", "CDE", "药审中心", "国家医保局",
    ]

    tags = []
    for name in companies + agencies:
        if name.lower() in text.lower():
            tags.append(name)

    return tags[:5]  # 最多 5 个标签
