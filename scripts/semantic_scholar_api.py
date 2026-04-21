"""
Semantic Scholar API 封装模块
- 接口文档：https://api.semanticscholar.org/api-docs/graph
- 免费，无需 API Key，国内可直连
- 内存缓存（5 分钟 TTL）+ 频率控制（≤1次/秒，避免 429）
"""

import time
import threading
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
from urllib.error import URLError, HTTPError

# ── 配置 ────────────────────────────────────────────────
BASE = "https://api.semanticscholar.org/graph/v1"
# 可选：申请免费 API Key 后填入，限速从 1次/秒 提升到 10次/秒
# https://www.semanticscholar.org/product/api#api-key
API_KEY = ""
CACHE_TTL = 300        # 缓存有效期（秒）
REQUEST_INTERVAL = 1.5 # 最小请求间隔（秒），无 Key 约 100次/分钟，保守取 1.5s

# 论文列表页需要的字段
LIST_FIELDS = "paperId,title,year,authors,venue,citationCount,openAccessPdf,publicationTypes,abstract"
# 论文详情页需要的字段
DETAIL_FIELDS = "paperId,title,year,authors,venue,citationCount,openAccessPdf,publicationTypes,abstract,references,externalIds,fieldsOfStudy,tldr"

# ── 内存缓存 ─────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()

# ── 频率控制 ─────────────────────────────────────────────
_last_req_time = 0.0
_rate_lock = threading.Lock()


def _get(url: str, _retry: int = 0) -> bytes:
    """带频率控制和自动重试的 GET 请求"""
    global _last_req_time
    with _rate_lock:
        elapsed = time.time() - _last_req_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        _last_req_time = time.time()

    headers = {
        "User-Agent": "PharmaPulse/1.0",
        "Accept": "application/json",
    }
    if API_KEY:
        headers["x-api-key"] = API_KEY

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read()
    except HTTPError as e:
        if e.code == 429 and _retry < 3:
            # 优先读服务器返回的 Retry-After，否则指数退避
            retry_after = e.headers.get("Retry-After", "")
            try:
                wait = float(retry_after) if retry_after else (5 * (2 ** _retry))
            except ValueError:
                wait = 5 * (2 ** _retry)   # 5s → 10s → 20s
            time.sleep(wait)
            return _get(url, _retry + 1)
        if e.code == 429:
            raise RuntimeError("Semantic Scholar 请求频率过高，请等待约 1 分钟后再试")
        raise RuntimeError(f"Semantic Scholar 请求失败 HTTP {e.code}: {e.reason}")
    except URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
    return None


def _cache_set(key: str, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


# ── 搜索文献 ─────────────────────────────────────────────
def search(query: str, page: int = 1, per_page: int = 20,
           year_from: str = "", year_to: str = "",
           fields_of_study: str = "") -> dict:
    """
    关键词搜索，返回文献列表。
    返回: {"total": int, "articles": [...], "page": int, "total_pages": int}
    """
    cache_key = f"search|{query}|{page}|{per_page}|{year_from}|{year_to}|{fields_of_study}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    offset = (page - 1) * per_page
    params = {
        "query": query,
        "limit": per_page,
        "offset": offset,
        "fields": LIST_FIELDS,
    }

    # 年份筛选：格式 "2020-2024" 或 "2020-"
    if year_from or year_to:
        yr_from = year_from or "1900"
        yr_to = year_to or "2100"
        params["year"] = f"{yr_from}-{yr_to}"

    # 领域筛选：如 "Medicine", "Biology"
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study

    url = f"{BASE}/paper/search?{urlencode(params)}"
    raw = _get(url)
    data = json.loads(raw)

    total = data.get("total", 0)
    papers = data.get("data", [])

    articles = [_normalize_paper(p) for p in papers]

    result = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "articles": articles,
    }
    _cache_set(cache_key, result)
    return result


# ── 文献详情 ─────────────────────────────────────────────
def get_paper(paper_id: str) -> dict:
    """
    获取单篇文献完整详情。
    paper_id 可以是 Semantic Scholar paperId 或 DOI:xxx 或 PMID:xxx
    """
    cache_key = f"paper|{paper_id}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"{BASE}/paper/{quote(paper_id)}?fields={DETAIL_FIELDS}"
    raw = _get(url)
    data = json.loads(raw)

    result = _normalize_paper(data, detail=True)
    _cache_set(cache_key, result)
    return result


# ── 发文趋势 ─────────────────────────────────────────────
def get_trends(query: str, years: int = 10) -> dict:
    """
    获取某关键词近 N 年每年的发文量。
    返回: {"2016": 1200, "2017": 1450, ...}
    """
    from datetime import datetime
    current_year = datetime.now().year
    cache_key = f"trends|{query}|{years}|{current_year}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    result = {}
    for y in range(current_year - years + 1, current_year + 1):
        try:
            params = {
                "query": query,
                "limit": 1,
                "offset": 0,
                "fields": "year",
                "year": f"{y}-{y}",
            }
            url = f"{BASE}/paper/search?{urlencode(params)}"
            raw = _get(url)
            data = json.loads(raw)
            result[str(y)] = data.get("total", 0)
        except Exception:
            result[str(y)] = 0
        # 年份间主动等待，避免连续 10 个请求触发 429
        time.sleep(0.3)

    _cache_set(cache_key, result)
    return result


# ── 数据标准化 ────────────────────────────────────────────
def _normalize_paper(p: dict, detail: bool = False) -> dict:
    """将 Semantic Scholar 原始字段转为统一格式"""
    # 作者
    authors = [a.get("name", "") for a in p.get("authors", [])]

    # 期刊/会议
    venue = p.get("venue", "") or ""

    # 开放全文
    pdf = p.get("openAccessPdf") or {}
    pdf_url = pdf.get("url", "") if isinstance(pdf, dict) else ""

    # 外部 ID（DOI、PubMed ID 等）
    ext_ids = p.get("externalIds") or {}
    doi = ext_ids.get("DOI", "")
    pmid = ext_ids.get("PubMed", "")
    arxiv = ext_ids.get("ArXiv", "")

    # 文章类型
    pub_types = p.get("publicationTypes") or []

    # AI 一句话摘要（TLDR）
    tldr_obj = p.get("tldr") or {}
    tldr = tldr_obj.get("text", "") if isinstance(tldr_obj, dict) else ""

    # 研究领域
    fields_of_study = p.get("fieldsOfStudy") or []

    normalized = {
        "paper_id": p.get("paperId", ""),
        "title": p.get("title", "") or "",
        "abstract": p.get("abstract", "") or "",
        "year": p.get("year", ""),
        "authors": authors,
        "venue": venue,
        "citation_count": p.get("citationCount", 0) or 0,
        "pdf_url": pdf_url,
        "doi": doi,
        "pmid": pmid,
        "arxiv": arxiv,
        "pub_types": pub_types,
        "fields_of_study": fields_of_study,
        "tldr": tldr,
    }

    if detail:
        # 参考文献（仅详情页）
        refs = []
        for r in (p.get("references") or [])[:20]:
            refs.append({
                "paper_id": r.get("paperId", ""),
                "title": r.get("title", ""),
                "year": r.get("year", ""),
                "authors": [a.get("name", "") for a in r.get("authors", [])],
            })
        normalized["references"] = refs

    return normalized


# ── 缓存清理 ─────────────────────────────────────────────
def clear_expired_cache():
    with _cache_lock:
        now = time.time()
        expired = [k for k, v in _cache.items() if (now - v["ts"]) >= CACHE_TTL]
        for k in expired:
            del _cache[k]
    return len(expired)
