"""
PharmaPulse - 数据抓取模块
从 RSS 源、新闻 API 和国内医药网站抓取医药行业新闻
"""
from __future__ import annotations

import re
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta

from config import (
    RSS_FEEDS, CN_BAIDU_NEWS_QUERIES, CN_36KR_RSS, CN_SINA_ROLL_API,
    NEWS_API_KEY, GNEWS_API_KEY,
)
from bs4 import BeautifulSoup
from urllib.parse import quote

# 网络超时设置（秒）
REQUEST_TIMEOUT = 15
RSS_FETCH_TIMEOUT = 15

# 通用请求头
HEADERS_EN = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
HEADERS_CN = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _fetch_feed_with_timeout(url: str, timeout: int = RSS_FETCH_TIMEOUT):
    """带超时的 RSS 抓取：先用 requests 下载，再用 feedparser 解析"""
    try:
        resp = requests.get(url, headers=HEADERS_EN, timeout=timeout)
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    except requests.exceptions.Timeout:
        print(f"     [TIMEOUT] {timeout}s exceeded, skipping")
        return None
    except requests.exceptions.RequestException as e:
        print(f"     [NET ERROR] {e}")
        return None


def fetch_rss_feeds() -> list[dict]:
    """从所有国际 RSS 源抓取新闻"""
    articles = []

    for feed_cfg in RSS_FEEDS:
        print(f"  [RSS] Fetching: {feed_cfg['name']}...")
        try:
            feed = _fetch_feed_with_timeout(feed_cfg["url"])
            if feed is None:
                continue
            count = 0
            for entry in feed.entries[:30]:  # 每个源最多取 30 条
                article = _parse_rss_entry(entry, feed_cfg["source"])
                if article:
                    articles.append(article)
                    count += 1
            print(f"     [OK] Got {count} items")
        except Exception as e:
            print(f"     [FAIL] {e}")
        time.sleep(0.5)  # 礼貌性延迟

    return articles


def fetch_cn_rss_feeds() -> list[dict]:
    """从国内可访问的数据源获取中文医药新闻
    三通道：百度资讯搜索 + 36kr RSS + 新浪财经滚动 API
    """
    articles = []

    # ── 通道1：百度资讯搜索（最稳定、数据量最大） ──
    for query_cfg in CN_BAIDU_NEWS_QUERIES:
        print(f"  [CN-Baidu] Fetching: {query_cfg['name']}...")
        try:
            items = _fetch_baidu_news(query_cfg["query"], query_cfg.get("max_items", 20))
            articles.extend(items)
            print(f"     [OK] Got {len(items)} items")
        except Exception as e:
            print(f"     [FAIL] {e}")
        time.sleep(1.5)  # 百度搜索需要更长间隔避免被限

    # ── 通道2：36kr RSS（科技/医疗交叉，过滤医药关键词） ──
    print(f"  [CN-36kr] Fetching: {CN_36KR_RSS['name']}...")
    try:
        feed = _fetch_feed_with_timeout(CN_36KR_RSS["url"])
        if feed and feed.entries:
            med_keywords = [
                "医", "药", "生物", "临床", "健康", "制药", "疫苗",
                "基因", "肿瘤", "集采", "医保", "CDE", "NMPA",
                "biotech", "pharma", "FDA",
            ]
            count = 0
            for entry in feed.entries[:CN_36KR_RSS.get("max_items", 30)]:
                title = getattr(entry, "title", "")
                if any(kw in title.lower() for kw in med_keywords):
                    article = _parse_rss_entry(entry, CN_36KR_RSS["source"])
                    if article:
                        articles.append(article)
                        count += 1
            print(f"     [OK] Got {count} medical items from 36kr")
        else:
            print(f"     [SKIP] RSS 不可用")
    except Exception as e:
        print(f"     [FAIL] {e}")

    # ── 通道3：新浪财经滚动 API（JSON 接口，过滤医药关键词） ──
    print(f"  [CN-Sina] Fetching: {CN_SINA_ROLL_API['name']}...")
    try:
        sina_articles = _fetch_sina_roll_news()
        articles.extend(sina_articles)
        print(f"     [OK] Got {len(sina_articles)} medical items from Sina")
    except Exception as e:
        print(f"     [FAIL] {e}")

    return articles


def _fetch_baidu_news(query: str, max_items: int = 20) -> list[dict]:
    """从百度资讯搜索抓取新闻（按时间排序，近30天内容）"""
    # sort=1 按时间排序（最新优先），gpc=stf=... 限制时间范围为近30天
    now_ts = int(time.time())
    month_ago_ts = now_ts - 30 * 86400
    url = (
        f"https://www.baidu.com/s?wd={quote(query)}&tn=news"
        f"&rn={max_items}&ie=utf-8&sort=1"
        f"&gpc=stf%3D{month_ago_ts}%2C{now_ts}%7Cstftype%3D1"
    )
    resp = requests.get(url, headers=HEADERS_CN, timeout=15)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    # 百度新闻搜索结果容器
    results = soup.select("div.result")
    if not results:
        results = soup.select("div.c-container")

    for item in results:
        try:
            # 标题和链接
            title_el = item.select_one("h3 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")

            # 跳过太短的标题（通常是广告/导航）
            if len(title) < 8:
                continue

            # 内容摘要
            content_el = item.select_one(
                "span.c-font-normal, div.c-span-last, .c-abstract, "
                "div.c-row span"
            )
            content = content_el.get_text(strip=True) if content_el else ""

            # 来源和时间（百度格式："来源名  X小时前" 或 "来源名  YYYY年M月D日"）
            source = "百度资讯"
            published = datetime.now(timezone.utc).isoformat()

            source_el = item.select_one(
                ".c-author, .news-source span, .c-color-author, "
                "span.c-color-gray, .c-gap-left-xsmall"
            )
            if source_el:
                raw = source_el.get_text(strip=True)
                # 尝试解析时间
                parsed_time = _parse_baidu_time(raw)
                if parsed_time:
                    published = parsed_time
                # 来源名（去掉时间部分）
                src = re.sub(r'\d+\s*(秒|分钟|小时|天|年|月|日|前).*', '', raw).strip()
                src = re.sub(r'^\s*\d{4}.*', '', src).strip()  # 去掉以年份开头的情况
                if src and len(src) < 30:
                    source = src

            articles.append({
                "title": title,
                "content": content if content else title,
                "source": source,
                "source_url": link,
                "published_at": published,
            })
        except Exception:
            continue

    return articles


def _parse_baidu_time(raw: str) -> str | None:
    """解析百度新闻的时间字符串，返回 ISO 格式时间，失败返回 None"""
    now = datetime.now(timezone.utc)
    raw = raw.strip()

    # "X秒前" / "X分钟前" / "X小时前"
    m = re.search(r'(\d+)\s*秒前', raw)
    if m:
        return (now - timedelta(seconds=int(m.group(1)))).isoformat()
    m = re.search(r'(\d+)\s*分钟前', raw)
    if m:
        return (now - timedelta(minutes=int(m.group(1)))).isoformat()
    m = re.search(r'(\d+)\s*小时前', raw)
    if m:
        return (now - timedelta(hours=int(m.group(1)))).isoformat()

    # "X天前"
    m = re.search(r'(\d+)\s*天前', raw)
    if m:
        return (now - timedelta(days=int(m.group(1)))).isoformat()

    # "昨天"
    if '昨天' in raw:
        return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()

    # "M月D日" (当年)
    m = re.search(r'(\d{1,2})月(\d{1,2})日', raw)
    if m:
        try:
            # 使用 UTC+8 当前年
            utc8_now = now + timedelta(hours=8)
            dt = datetime(utc8_now.year, int(m.group(1)), int(m.group(2)), 12, 0, 0, tzinfo=timezone.utc)
            # 如果日期在未来，往前一年
            if dt > now:
                dt = dt.replace(year=dt.year - 1)
            return dt.isoformat()
        except ValueError:
            pass

    # "YYYY年M月D日"
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', raw)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, 0, tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass

    return None


def _fetch_sina_roll_news() -> list[dict]:
    """从新浪财经滚动新闻 API 抓取医药相关新闻"""
    med_keywords = [
        "医", "药", "生物", "临床", "健康", "制药", "疫苗",
        "基因", "肿瘤", "集采", "医保", "创新药", "仿制药",
        "CDE", "NMPA", "药监", "药审",
    ]
    articles = []

    for page in range(1, CN_SINA_ROLL_API.get("pages", 3) + 1):
        url = CN_SINA_ROLL_API["url"].format(page=page)
        try:
            resp = requests.get(url, headers=HEADERS_CN, timeout=10)
            data = resp.json()
            items = data.get("result", {}).get("data", [])

            for item in items:
                title = item.get("title", "")
                # 只保留医药相关
                if not any(kw in title for kw in med_keywords):
                    continue

                # 解析时间
                ctime = item.get("ctime", "")
                try:
                    published = datetime.fromtimestamp(
                        int(ctime), tz=timezone.utc
                    ).isoformat() if ctime else datetime.now(timezone.utc).isoformat()
                except (ValueError, OSError):
                    published = datetime.now(timezone.utc).isoformat()

                articles.append({
                    "title": title,
                    "content": item.get("intro", "") or item.get("summary", "") or title,
                    "source": item.get("media_name", CN_SINA_ROLL_API["source"]),
                    "source_url": item.get("url", ""),
                    "published_at": published,
                })
        except Exception:
            continue
        time.sleep(0.5)

    return articles


def _parse_rss_entry(entry: dict, source: str) -> dict | None:
    """解析单条 RSS entry 为统一格式"""
    title = getattr(entry, "title", "").strip()
    if not title:
        return None

    # 提取发布时间
    published = None
    for time_field in ("published_parsed", "updated_parsed"):
        tp = getattr(entry, time_field, None)
        if tp:
            try:
                published = datetime(*tp[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
            break

    if not published:
        published = datetime.now(timezone.utc).isoformat()

    # 提取内容/描述
    content = ""
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        content = entry.summary or ""

    # 简单清理 HTML 标签
    content = re.sub(r"<[^>]+>", "", content).strip()
    content = content[:2000]  # 截断过长内容

    return {
        "title": title,
        "content": content,
        "source": source,
        "source_url": getattr(entry, "link", ""),
        "published_at": published,
    }



# ── 国际 API ──────────────────────────────────────────────

def fetch_newsapi(query: str = "pharma OR pharmaceutical OR FDA OR biotech") -> list[dict]:
    """从 NewsAPI 抓取新闻"""
    if not NEWS_API_KEY:
        print("  [SKIP] NewsAPI Key 未配置，跳过")
        return []

    print("  [API] 抓取 NewsAPI...")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 50,
        "apiKey": NEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        articles = []
        for item in data.get("articles", []):
            articles.append({
                "title": item.get("title", "").strip(),
                "content": (item.get("description", "") or "") + " " + (item.get("content", "") or ""),
                "source": item.get("source", {}).get("name", "Unknown"),
                "source_url": item.get("url", ""),
                "published_at": item.get("publishedAt", datetime.now(timezone.utc).isoformat()),
            })
        print(f"     [OK] 获取 {len(articles)} 条")
        return articles
    except Exception as e:
        print(f"     [FAIL] NewsAPI: {e}")
        return []


def fetch_gnews(query: str = "pharmaceutical", lang: str = "en") -> list[dict]:
    """从 GNews API 抓取新闻"""
    if not GNEWS_API_KEY:
        print(f"  [SKIP] GNews API Key 未配置，跳过 ({lang})")
        return []

    print(f"  [API] 抓取 GNews ({lang}: {query})...")
    url = "https://gnews.io/api/v4/search"
    params = {
        "q": query,
        "lang": lang,
        "max": 50,
        "token": GNEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        articles = []
        for item in data.get("articles", []):
            articles.append({
                "title": item.get("title", "").strip(),
                "content": item.get("description", "") or item.get("content", "") or "",
                "source": item.get("source", {}).get("name", "Unknown"),
                "source_url": item.get("url", ""),
                "published_at": item.get("publishedAt", datetime.now(timezone.utc).isoformat()),
            })
        print(f"     [OK] 获取 {len(articles)} 条")
        return articles
    except Exception as e:
        print(f"     [FAIL] GNews ({lang}): {e}")
        return []


def fetch_all() -> list[dict]:
    """抓取所有数据源，返回原始文章列表"""
    print("\n[START] 开始抓取数据...\n")
    all_articles = []

    # 1. 国际 RSS 源（主力，无限量）
    print("── 国际数据源 ──")
    rss_articles = fetch_rss_feeds()
    all_articles.extend(rss_articles)

    # 2. 国内数据源（百度资讯搜索 + 36kr RSS + 新浪滚动 API）
    print("\n── 国内数据源（百度+36kr+新浪） ──")
    cn_articles = fetch_cn_rss_feeds()
    all_articles.extend(cn_articles)

    # 3. NewsAPI（补充，英文）
    print("\n── API 补充数据源 ──")
    newsapi_articles = fetch_newsapi()
    all_articles.extend(newsapi_articles)

    # 4. GNews 英文（补充）
    gnews_articles = fetch_gnews()
    all_articles.extend(gnews_articles)

    print(f"\n[STAT] 抓取完成，共获取 {len(all_articles)} 条原始数据")
    print(f"   国际RSS: {len(rss_articles)}, 国内(百度+36kr+新浪): {len(cn_articles)}")
    print(f"   NewsAPI: {len(newsapi_articles)}, GNews: {len(gnews_articles)}\n")
    return all_articles


if __name__ == "__main__":
    articles = fetch_all()
    for a in articles[:10]:
        print(f"  - [{a['source']}] {a['title'][:60]}")
