"""
PubMed API 封装模块
- 封装 esearch / esummary / efetch 三个 NCBI E-utilities 接口
- XML → JSON 解析（使用标准库 xml.etree.ElementTree，零依赖）
- 内存缓存（5 分钟 TTL）
- 请求频率控制（队列，每秒最多 3 次）
"""

import time
import threading
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError
import json

# ── 配置 ────────────────────────────────────────────────
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# 如有 API Key 可填入，无 Key 限制 3次/秒，有 Key 限制 10次/秒
NCBI_API_KEY = ""  # 可选：填入 NCBI API Key
CACHE_TTL = 300    # 缓存有效期（秒）
REQUEST_MIN_INTERVAL = 0.35  # 最小请求间隔（秒），确保 ≤3 次/秒

# ── 内存缓存 ─────────────────────────────────────────────
_cache: dict = {}           # key -> {"data": ..., "ts": float}
_cache_lock = threading.Lock()

# ── 请求频率控制 ──────────────────────────────────────────
_last_request_time = 0.0
_rate_lock = threading.Lock()


def _rate_limited_get(url: str) -> bytes:
    """带频率控制的 HTTP GET，返回响应字节"""
    global _last_request_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < REQUEST_MIN_INTERVAL:
            time.sleep(REQUEST_MIN_INTERVAL - elapsed)
        _last_request_time = time.time()

    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read()
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"NCBI 请求失败: {e} | URL: {url}")


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < CACHE_TTL:
            return entry["data"]
    return None


def _cache_set(key: str, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _build_url(endpoint: str, params: dict) -> str:
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params["tool"] = "PharmaPulse"
    params["email"] = "contact@pharma"
    return f"{NCBI_BASE}/{endpoint}?{urlencode(params)}"


# ── esearch ──────────────────────────────────────────────
def esearch(term: str, retmax: int = 20, retstart: int = 0,
            sort: str = "relevance", date_from: str = "", date_to: str = "",
            article_type: str = "") -> dict:
    """
    关键词搜索，返回 PMID 列表和总数。
    返回: {"count": int, "idlist": [str], "query": str}
    """
    cache_key = f"esearch|{term}|{retmax}|{retstart}|{sort}|{date_from}|{date_to}|{article_type}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retstart": retstart,
        "sort": sort,
        "retmode": "json",
        "usehistory": "n",
    }
    if date_from or date_to:
        params["datetype"] = "pdat"
        if date_from:
            params["mindate"] = date_from.replace("-", "/")
        if date_to:
            params["maxdate"] = date_to.replace("-", "/")
    if article_type:
        # 如 "review", "clinical_trial"
        params["term"] = f"{term} AND {article_type}[pt]"

    url = _build_url("esearch.fcgi", params)
    raw = _rate_limited_get(url)
    if raw.lstrip()[:1] == b"<":
        raise RuntimeError("NCBI 返回了 HTML 错误页，可能被风控拦截。请稍后重试，或配置 NCBI_API_KEY。")
    data = json.loads(raw)
    result_set = data.get("esearchresult", {})

    result = {
        "count": int(result_set.get("count", 0)),
        "idlist": result_set.get("idlist", []),
        "query": term,
    }
    _cache_set(cache_key, result)
    return result


# ── esummary ─────────────────────────────────────────────
def esummary(pmids: list) -> list:
    """
    批量获取文章摘要信息（轻量，用于列表页）。
    返回: list of article summary dicts
    """
    if not pmids:
        return []

    cache_key = f"esummary|{'_'.join(sorted(pmids))}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    }
    url = _build_url("esummary.fcgi", params)
    raw = _rate_limited_get(url)
    if raw.lstrip()[:1] == b"<":
        raise RuntimeError("NCBI esummary 返回了 HTML 错误页，请稍后重试。")
    data = json.loads(raw)
    result_data = data.get("result", {})

    articles = []
    for pmid in pmids:
        doc = result_data.get(pmid, {})
        if not doc or pmid == "uids":
            continue

        # 作者列表
        authors = []
        for a in doc.get("authors", []):
            if a.get("authtype") == "Author":
                authors.append(a.get("name", ""))

        articles.append({
            "pmid": pmid,
            "title": doc.get("title", "").rstrip("."),
            "authors": authors,
            "journal": doc.get("fulljournalname", "") or doc.get("source", ""),
            "pub_date": doc.get("pubdate", ""),
            "volume": doc.get("volume", ""),
            "issue": doc.get("issue", ""),
            "pages": doc.get("pages", ""),
            "doi": _extract_doi(doc.get("articleids", [])),
            "pub_types": [t.get("value", "") for t in doc.get("pubtype", [])],
        })

    _cache_set(cache_key, articles)
    return articles


def _extract_doi(articleids: list) -> str:
    for item in articleids:
        if item.get("idtype") == "doi":
            return item.get("value", "")
    return ""


# ── efetch ───────────────────────────────────────────────
def efetch(pmid: str) -> dict:
    """
    获取单篇文章完整详情（含摘要全文、MeSH 词、作者机构）。
    返回: article detail dict
    """
    cache_key = f"efetch|{pmid}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "rettype": "abstract",
    }
    url = _build_url("efetch.fcgi", params)
    raw = _rate_limited_get(url)

    result = _parse_efetch_xml(pmid, raw)
    _cache_set(cache_key, result)
    return result


def _parse_efetch_xml(pmid: str, xml_bytes: bytes) -> dict:
    """解析 efetch 返回的 PubMed XML"""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return {"pmid": pmid, "error": f"XML 解析失败: {e}"}

    article_node = root.find(".//PubmedArticle")
    if article_node is None:
        return {"pmid": pmid, "error": "未找到文章数据"}

    # 标题
    title_node = article_node.find(".//ArticleTitle")
    title = "".join(title_node.itertext()).strip() if title_node is not None else ""

    # 摘要（可能分段）
    abstract_parts = []
    for ab in article_node.findall(".//AbstractText"):
        label = ab.get("Label", "")
        text = "".join(ab.itertext()).strip()
        if label and label.upper() != "UNLABELLED":
            abstract_parts.append(f"{label}: {text}")
        else:
            abstract_parts.append(text)
    abstract = "\n\n".join(p for p in abstract_parts if p)

    # 作者 + 机构
    authors = []
    for author in article_node.findall(".//Author"):
        last = author.findtext("LastName", "")
        fore = author.findtext("ForeName", "")
        name = f"{last} {fore}".strip() if last else author.findtext("CollectiveName", "")
        affil = author.findtext(".//AffiliationInfo/Affiliation", "")
        authors.append({"name": name, "affiliation": affil})

    # 期刊信息
    journal_node = article_node.find(".//Journal")
    journal = ""
    volume = issue = pages = pub_date = ""
    if journal_node is not None:
        journal = journal_node.findtext("Title", "") or journal_node.findtext("ISOAbbreviation", "")
        volume = journal_node.findtext(".//JournalIssue/Volume", "")
        issue = journal_node.findtext(".//JournalIssue/Issue", "")
        # 发表日期
        pub_date_node = journal_node.find(".//JournalIssue/PubDate")
        if pub_date_node is not None:
            year = pub_date_node.findtext("Year", "")
            month = pub_date_node.findtext("Month", "")
            day = pub_date_node.findtext("Day", "")
            med_date = pub_date_node.findtext("MedlineDate", "")
            pub_date = " ".join(p for p in [year, month, day] if p) or med_date

    pages = article_node.findtext(".//Pagination/MedlinePgn", "")

    # DOI
    doi = ""
    for eid in article_node.findall(".//ELocationID"):
        if eid.get("EIdType") == "doi":
            doi = eid.text or ""
            break

    # MeSH 词
    mesh_terms = []
    for mesh in article_node.findall(".//MeshHeading"):
        desc = mesh.find("DescriptorName")
        if desc is not None:
            mesh_terms.append(desc.text or "")

    # 文章类型
    pub_types = [pt.text for pt in article_node.findall(".//PublicationTypeList/PublicationType") if pt.text]

    # PMCID
    pmcid = ""
    for aid in article_node.findall(".//ArticleId"):
        if aid.get("IdType") == "pmc":
            pmcid = aid.text or ""
            break

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "pub_date": pub_date,
        "doi": doi,
        "pmcid": pmcid,
        "mesh_terms": mesh_terms,
        "pub_types": pub_types,
    }


# ── 趋势数据 ─────────────────────────────────────────────
def get_trends(term: str, years: int = 10) -> dict:
    """
    获取某关键词近 N 年每年的发文量。
    返回: {"2016": 1200, "2017": 1450, ...}
    """
    from datetime import datetime
    current_year = datetime.now().year
    cache_key = f"trends|{term}|{years}|{current_year}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    result = {}
    for y in range(current_year - years + 1, current_year + 1):
        try:
            data = esearch(
                term=term,
                retmax=0,
                date_from=f"{y}/01/01",
                date_to=f"{y}/12/31",
            )
            result[str(y)] = data["count"]
        except Exception:
            result[str(y)] = 0

    _cache_set(cache_key, result)
    return result


# ── 缓存管理 ─────────────────────────────────────────────
def clear_expired_cache():
    """清除过期缓存条目"""
    with _cache_lock:
        now = time.time()
        expired = [k for k, v in _cache.items() if (now - v["ts"]) >= CACHE_TTL]
        for k in expired:
            del _cache[k]
    return len(expired)
