/**
 * PharmaPulse - 文献检索模块 v2 (Semantic Scholar)
 */

(function () {
  "use strict";

  // ── 状态 ─────────────────────────────────────────────
  let currentPage = 1;
  let currentQuery = "";
  let currentDateFrom = "";
  let currentDateTo = "";
  let currentArticleType = "";
  let totalCount = 0;
  let totalPages = 1;
  const PER_PAGE = 20;
  let isAllExpanded = false;
  let trendsChart = null;
  let trendsFetched = false;

  // ── DOM ──────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    searchInput:      $("#litSearchInput"),
    searchBtn:        $("#litSearchBtn"),
    advancedToggleBtn:$("#advancedToggleBtn"),
    advancedPanel:    $("#advancedPanel"),
    dateFrom:         $("#dateFrom"),
    dateTo:           $("#dateTo"),
    articleType:      $("#articleType"),
    sortOrder:        $("#sortOrder"),
    resultsSection:   $("#litResultsSection"),
    resultsCount:     $("#litResultsCount"),
    expandAllBtn:     $("#litExpandAllBtn"),
    litList:          $("#litList"),
    pagination:       $("#litPagination"),
    trendsSection:    $("#litTrendsSection"),
    trendsTitle:      $("#litTrendsTitle"),
    emptyState:       $("#litEmptyState"),
    loadingState:     $("#litLoadingState"),
    errorState:       $("#litErrorState"),
    errorMsg:         $("#litErrorMsg"),
    intro:            $("#litIntro"),
    modal:            $("#articleModal"),
    modalTitle:       $("#modalTitle"),
    modalBody:        $("#modalBody"),
    modalClose:       $("#modalClose"),
    themeToggle:      $("#themeToggle"),
    mobileMenuBtn:    $("#mobileMenuBtn"),
    mobileMenu:       $("#mobileMenu"),
  };

  // ── 暗色模式 ─────────────────────────────────────────
  function initTheme() {
    const saved = localStorage.getItem("pp-theme") || "light";
    document.documentElement.setAttribute("data-theme", saved);
    updateThemeIcon(saved);
  }
  function updateThemeIcon(theme) {
    if (dom.themeToggle) dom.themeToggle.textContent = theme === "dark" ? "☀️" : "🌓";
  }
  if (dom.themeToggle) {
    dom.themeToggle.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") || "light";
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("pp-theme", next);
      updateThemeIcon(next);
      // 趋势图颜色随主题刷新
      if (trendsChart) { trendsChart.destroy(); trendsChart = null; fetchTrends(true); }
    });
  }
  initTheme();

  // ── 移动端菜单 ─────────────────────────────────────
  if (dom.mobileMenuBtn && dom.mobileMenu) {
    dom.mobileMenuBtn.addEventListener("click", () => dom.mobileMenu.classList.toggle("open"));
  }

  // ── 高级筛选折叠 ──────────────────────────────────
  if (dom.advancedToggleBtn) {
    dom.advancedToggleBtn.addEventListener("click", () => {
      const isOpen = dom.advancedPanel.style.display !== "none";
      dom.advancedPanel.style.display = isOpen ? "none" : "block";
      dom.advancedToggleBtn.textContent = isOpen ? "⚙ 高级筛选" : "⚙ 收起筛选";
    });
  }

  // ── 快速时间范围预设 ──────────────────────────────
  $$(".btn-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".btn-preset").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const years = parseInt(btn.dataset.years, 10);
      const now = new Date();
      dom.dateFrom.value = (now.getFullYear() - years) + "-01-01";
      dom.dateTo.value   = now.toISOString().split("T")[0];
    });
  });

  // ── 热门主题标签 ─────────────────────────────────
  $$(".hot-tag").forEach((tag) => {
    tag.addEventListener("click", () => {
      dom.searchInput.value = tag.dataset.q;
      triggerSearch();
    });
  });

  // ── 搜索触发 ─────────────────────────────────────
  function triggerSearch(page = 1) {
    const q = dom.searchInput.value.trim();
    if (!q) return;
    currentQuery    = q;
    currentPage     = page;
    currentDateFrom = dom.dateFrom  ? dom.dateFrom.value.slice(0, 4)  : "";
    currentDateTo   = dom.dateTo    ? dom.dateTo.value.slice(0, 4)    : "";
    currentArticleType = dom.articleType ? dom.articleType.value : "";
    trendsFetched   = false;
    fetchArticles();
  }

  dom.searchBtn.addEventListener("click", () => triggerSearch(1));
  dom.searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") triggerSearch(1); });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); dom.searchInput.focus(); dom.searchInput.select(); }
    if (e.key === "Escape") closeModal();
  });

  // ── 全部展开/折叠 ─────────────────────────────────
  if (dom.expandAllBtn) {
    dom.expandAllBtn.addEventListener("click", () => {
      isAllExpanded = !isAllExpanded;
      $$(".lit-abstract-body").forEach((el) => { el.style.display = isAllExpanded ? "block" : "none"; });
      $$(".lit-abstract-toggle").forEach((btn) => { btn.textContent = isAllExpanded ? "收起 ▲" : "展开摘要 ▼"; });
      dom.expandAllBtn.textContent = isAllExpanded ? "全部折叠" : "全部展开";
    });
  }

  // ── 获取文献列表 ─────────────────────────────────
  async function fetchArticles() {
    showState("loading");

    // 线上强制前端直连 / 本地优先前端直连
    try {
      await fetchArticlesDirect();
      return;
    } catch (directErr) {
      // 前端直连失败，若是线上强制模式直接报错；本地降级走后端
      if (window.PHARMA_FORCE_DIRECT) {
        showState("error", "文献检索暂时不可用，请稍后重试（" + directErr.message + "）");
        return;
      }
    }

    // 本地降级：后端代理
    const params = new URLSearchParams({
      q: currentQuery, page: currentPage, per_page: PER_PAGE,
    });
    if (currentDateFrom)    params.set("date_from", currentDateFrom);
    if (currentDateTo)      params.set("date_to",   currentDateTo);
    if (currentArticleType) params.set("article_type", currentArticleType);

    try {
      const resp = await fetch((window.PHARMA_API_BASE || "") + `/api/pubmed/search?${params}`);
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "搜索失败");
      totalCount = data.total;
      totalPages = data.total_pages;
      if (totalCount === 0) { showState("empty"); return; }
      renderResults(data.articles);
      renderPagination();
      showState("results");
      if (!trendsFetched) { trendsFetched = true; fetchTrends(); }
    } catch (err) {
      showState("error", err.message);
    }
  }

  async function fetchArticlesDirect() {
    const S2_BASE = "https://api.semanticscholar.org/graph/v1";
    const fields = "paperId,title,year,authors,venue,citationCount,openAccessPdf,publicationTypes,abstract";
    const offset = (currentPage - 1) * PER_PAGE;
    const qp = new URLSearchParams({
      query: currentQuery, limit: PER_PAGE, offset, fields,
    });
    if (currentDateFrom && currentDateTo) qp.set("year", `${currentDateFrom}-${currentDateTo}`);

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    const resp = await fetch(`${S2_BASE}/paper/search?${qp}`, { signal: ctrl.signal });
    clearTimeout(timer);

    if (!resp.ok) throw new Error(`Semantic Scholar 请求失败 (${resp.status})`);
    const data = await resp.json();

    totalCount = data.total || 0;
    totalPages = Math.max(1, Math.ceil(totalCount / PER_PAGE));
    if (totalCount === 0) { showState("empty"); return; }

    const articles = (data.data || []).map(p => normalizePaper(p));
    renderResults(articles);
    renderPagination();
    showState("results");
    if (!trendsFetched) { trendsFetched = true; fetchTrendsDirect(); }
  }

  // ── 渲染文献卡片 ─────────────────────────────────
  function renderResults(articles) {
    dom.resultsCount.textContent =
      `共找到 ${totalCount.toLocaleString()} 篇文献，当前显示第 ${(currentPage-1)*PER_PAGE+1}–${Math.min(currentPage*PER_PAGE, totalCount)} 篇`;

    dom.litList.innerHTML = articles.map(renderCard).join("");

    // 摘要折叠
    dom.litList.querySelectorAll(".lit-abstract-toggle").forEach((btn) => {
      btn.addEventListener("click", function () {
        const body = this.closest(".lit-abstract").querySelector(".lit-abstract-body");
        const isOpen = body.style.display !== "none";
        body.style.display = isOpen ? "none" : "block";
        this.textContent = isOpen ? "展开摘要 ▼" : "收起 ▲";
      });
    });

    // 详情点击
    dom.litList.querySelectorAll(".lit-card-title").forEach((el) => {
      el.addEventListener("click", function () { openDetail(this.dataset.pid, this.textContent); });
    });

    // 快速引用
    dom.litList.querySelectorAll(".btn-cite-quick").forEach((btn) => {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        copyText(buildQuickCite(this.closest(".lit-card")), this);
      });
    });
  }

  function renderCard(a) {
    const authors = a.authors && a.authors.length
      ? (a.authors.length > 3 ? a.authors.slice(0, 3).join(", ") + " 等" : a.authors.join(", "))
      : "作者不详";

    const types = (a.pub_types || []).slice(0, 2)
      .map((t) => `<span class="lit-badge">${esc(t)}</span>`).join("");

    const fields = (a.fields_of_study || []).slice(0, 2)
      .map((f) => `<span class="lit-badge lit-badge-field">${esc(f)}</span>`).join("");

    const pdfBtn = a.pdf_url
      ? `<a class="btn-link" href="${esc(a.pdf_url)}" target="_blank" rel="noopener">📄 全文 ↗</a>`
      : "";

    const doiBtn = a.doi
      ? `<a class="btn-link" href="https://doi.org/${esc(a.doi)}" target="_blank" rel="noopener">DOI ↗</a>`
      : "";

    const s2Btn = a.paper_id
      ? `<a class="btn-link" href="https://www.semanticscholar.org/paper/${esc(a.paper_id)}" target="_blank" rel="noopener">S2 ↗</a>`
      : "";

    const tldr = a.tldr
      ? `<div class="lit-tldr"><span class="tldr-label">TLDR</span>${esc(a.tldr)}</div>`
      : "";

    const abstractPreview = a.abstract
      ? `<div class="lit-abstract-body" style="display:none;">${esc(a.abstract)}</div>`
      : `<div class="lit-abstract-body" style="display:none;"><span class="text-muted">暂无摘要</span></div>`;

    return `
<div class="lit-card"
     data-pid="${esc(a.paper_id)}"
     data-authors="${esc(JSON.stringify(a.authors||[]))}"
     data-year="${esc(String(a.year||""))}"
     data-venue="${esc(a.venue||"")}"
     data-doi="${esc(a.doi||"")}"
     data-pmid="${esc(a.pmid||"")}">
  <div class="lit-card-meta">
    <span class="lit-card-date">${esc(String(a.year||""))}</span>
    ${types}${fields}
    ${a.citation_count ? `<span class="lit-cite-count" title="被引次数">🔗 ${a.citation_count.toLocaleString()}</span>` : ""}
    ${a.pdf_url ? `<span class="lit-oa-badge">Open Access</span>` : ""}
  </div>
  <h3 class="lit-card-title" data-pid="${esc(a.paper_id)}" title="点击查看完整详情">${esc(a.title||"（无标题）")}</h3>
  <p class="lit-card-authors">${esc(authors)}</p>
  ${a.venue ? `<p class="lit-card-journal">${esc(a.venue)}</p>` : ""}
  ${tldr}
  <div class="lit-card-actions">
    ${doiBtn}${pdfBtn}${s2Btn}
    <button class="btn-link btn-cite-quick" title="复制 Vancouver 引用">📋 引用</button>
    ${a.abstract ? `<button class="btn-link lit-abstract-toggle">展开摘要 ▼</button>` : ""}
  </div>
  <div class="lit-abstract">${abstractPreview}</div>
</div>`;
  }

  function buildQuickCite(card) {
    const authors = JSON.parse(card.dataset.authors || "[]");
    const year = card.dataset.year || "";
    const venue = card.dataset.venue || "";
    const doi = card.dataset.doi || "";
    const title = card.querySelector(".lit-card-title")?.textContent || "";
    const authorStr = authors.slice(0, 6).join(", ") + (authors.length > 6 ? " et al" : "");
    let cite = `${authorStr}. ${title}. ${venue}. ${year}`;
    if (doi) cite += `. doi:${doi}`;
    return cite;
  }

  // ── 分页 ─────────────────────────────────────────
  function renderPagination() {
    if (totalPages <= 1) { dom.pagination.innerHTML = ""; return; }
    const maxV = 5;
    let start = Math.max(1, currentPage - Math.floor(maxV / 2));
    let end = Math.min(totalPages, start + maxV - 1);
    if (end - start < maxV - 1) start = Math.max(1, end - maxV + 1);

    let html = `<button class="page-btn" ${currentPage<=1?"disabled":""} data-page="${currentPage-1}">‹ 上一页</button>`;
    if (start > 1) html += `<button class="page-btn" data-page="1">1</button>${start>2?'<span class="page-ellipsis">…</span>':""}`;
    for (let i = start; i <= end; i++) html += `<button class="page-btn${i===currentPage?" active":""}" data-page="${i}">${i}</button>`;
    if (end < totalPages) html += `${end<totalPages-1?'<span class="page-ellipsis">…</span>':""}` + `<button class="page-btn" data-page="${totalPages}">${totalPages}</button>`;
    html += `<button class="page-btn" ${currentPage>=totalPages?"disabled":""} data-page="${currentPage+1}">下一页 ›</button>`;

    dom.pagination.innerHTML = html;
    dom.pagination.querySelectorAll(".page-btn:not([disabled])").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pg = parseInt(btn.dataset.page, 10);
        if (pg !== currentPage) { triggerSearch(pg); window.scrollTo({ top: 0, behavior: "smooth" }); }
      });
    });
  }

  // ── 文献详情弹窗 ─────────────────────────────────
  async function openDetail(paperId, titleHint) {
    dom.modalTitle.textContent = titleHint || "加载中…";
    dom.modalBody.innerHTML = '<div class="loading"><div class="spinner"></div><p>正在加载详情…</p></div>';
    dom.modal.style.display = "flex";
    document.body.style.overflow = "hidden";

    const S2_BASE = "https://api.semanticscholar.org/graph/v1";
    const fields = "paperId,title,year,authors,venue,citationCount,openAccessPdf,publicationTypes,abstract,references,externalIds,fieldsOfStudy,tldr";

    // 优先前端直连（浏览器 IP 不受后端限速影响），5 秒超时
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5000);
      const resp = await fetch(
        `${S2_BASE}/paper/${encodeURIComponent(paperId)}?fields=${fields}`,
        { signal: ctrl.signal }
      );
      clearTimeout(timer);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const raw = await resp.json();
      renderModal(normalizePaper(raw, true));
      return;
    } catch (directErr) {
      if (window.PHARMA_FORCE_DIRECT) {
        dom.modalBody.innerHTML = `<div class="error-state"><div class="error-icon">⚠️</div><p class="error-title">加载失败</p><p class="error-msg">${esc(directErr.message)}</p><p style="margin-top:8px;font-size:0.8rem;color:var(--text-muted)">可直接在 <a href="https://www.semanticscholar.org/paper/${esc(paperId)}" target="_blank">Semantic Scholar</a> 查看</p></div>`;
        return;
      }
    }

    // 本地降级：后端代理
    try {
      const resp = await fetch((window.PHARMA_API_BASE || "") + `/api/pubmed/article/${encodeURIComponent(paperId)}`);
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "加载失败");
      renderModal(data.article);
    } catch (err) {
      dom.modalBody.innerHTML = `<div class="error-state"><div class="error-icon">⚠️</div><p class="error-title">加载失败</p><p class="error-msg">${esc(err.message)}</p><p style="margin-top:8px;font-size:0.8rem;color:var(--text-muted)">可直接在 <a href="https://www.semanticscholar.org/paper/${esc(paperId)}" target="_blank">Semantic Scholar</a> 查看</p></div>`;
    }
  }

  // ── 前端直连趋势图 ────────────────────────────────
  async function fetchTrendsDirect() {
    const S2_BASE = "https://api.semanticscholar.org/graph/v1";
    const curYear = new Date().getFullYear();
    const result = {};
    for (let y = curYear - 9; y <= curYear; y++) {
      try {
        const qp = new URLSearchParams({ query: currentQuery, limit: 1, offset: 0, fields: "year", year: `${y}-${y}` });
        const r = await fetch(`${S2_BASE}/paper/search?${qp}`);
        if (!r.ok) { result[y] = 0; continue; }
        const d = await r.json();
        result[y] = d.total || 0;
      } catch (_) { result[y] = 0; }
      await new Promise(res => setTimeout(res, 500));  // 年份间隔
    }
    if (Object.keys(result).length) renderTrends(result);
  }

  // ── 数据格式统一（前端直连时使用） ─────────────────
  function normalizePaper(p, detail = false) {
    const ext = p.externalIds || {};
    const pdf = p.openAccessPdf || {};
    const tldrObj = p.tldr || {};
    const normalized = {
      paper_id:      p.paperId || "",
      title:         p.title || "",
      abstract:      p.abstract || "",
      year:          p.year || "",
      authors:       (p.authors || []).map(a => a.name || ""),
      venue:         p.venue || "",
      citation_count: p.citationCount || 0,
      pdf_url:       typeof pdf === "object" ? (pdf.url || "") : "",
      doi:           ext.DOI || "",
      pmid:          ext.PubMed || "",
      arxiv:         ext.ArXiv || "",
      pub_types:     p.publicationTypes || [],
      fields_of_study: p.fieldsOfStudy || [],
      tldr:          typeof tldrObj === "object" ? (tldrObj.text || "") : "",
    };
    if (detail) {
      normalized.references = (p.references || []).slice(0, 20).map(r => ({
        paper_id: r.paperId || "",
        title:    r.title || "",
        year:     r.year || "",
        authors:  (r.authors || []).map(a => a.name || ""),
      }));
    }
    return normalized;
  }

  function renderModal(a) {
    dom.modalTitle.textContent = a.title || "（无标题）";

    const authorsHtml = (a.authors || [])
      .map((name) => `<span class="modal-author">${esc(name)}</span>`).join(", ") || "作者不详";

    const types = (a.pub_types || []).map((t) => `<span class="lit-badge">${esc(t)}</span>`).join(" ");
    const fields = (a.fields_of_study || []).map((f) => `<span class="lit-badge lit-badge-field">${esc(f)}</span>`).join(" ");

    const doiLink = a.doi ? `<a href="https://doi.org/${esc(a.doi)}" target="_blank" rel="noopener">${esc(a.doi)} ↗</a>` : "—";
    const pmidLink = a.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(a.pmid)}/" target="_blank" rel="noopener">${esc(a.pmid)} ↗</a>` : "—";
    const pdfLink = a.pdf_url ? `<a href="${esc(a.pdf_url)}" target="_blank" rel="noopener">下载 PDF ↗</a>` : "—";
    const s2Link = a.paper_id ? `<a href="https://www.semanticscholar.org/paper/${esc(a.paper_id)}" target="_blank" rel="noopener">查看 ↗</a>` : "—";

    const apa = buildAPA(a);
    const van = buildVancouver(a);

    // 参考文献
    const refsHtml = (a.references || []).length
      ? `<div class="modal-section"><h4 class="modal-section-title">参考文献（前 ${a.references.length} 篇）</h4><div class="modal-refs">${
          a.references.map((r) => `<div class="modal-ref-item">${r.year ? `<span class="ref-year">${esc(String(r.year))}</span>` : ""}${r.authors&&r.authors.length?`<span class="ref-authors">${esc(r.authors.slice(0,3).join(", "))}${r.authors.length>3?" et al":""}</span>`:""}${r.title?`<span class="ref-title">${esc(r.title)}</span>`:""}</div>`).join("")
        }</div></div>`
      : "";

    dom.modalBody.innerHTML = `
<div class="modal-meta-row">
  <span class="modal-journal">${esc(a.venue || "")}</span>
  <span class="modal-date">${esc(String(a.year || ""))}</span>
  ${types}${fields}
  ${a.citation_count ? `<span class="lit-cite-count" title="被引次数">🔗 ${a.citation_count.toLocaleString()} 引用</span>` : ""}
</div>
<div class="modal-authors">${authorsHtml}</div>

${a.tldr ? `<div class="modal-tldr"><span class="tldr-label">TLDR</span>${esc(a.tldr)}</div>` : ""}

<div class="modal-section">
  <h4 class="modal-section-title">摘要</h4>
  <div class="modal-abstract">${a.abstract ? formatAbstract(a.abstract) : '<span class="text-muted">暂无摘要</span>'}</div>
</div>

<div class="modal-section modal-ids">
  <div class="modal-id-row"><span class="modal-id-label">Semantic Scholar</span>${s2Link}</div>
  <div class="modal-id-row"><span class="modal-id-label">DOI</span>${doiLink}</div>
  <div class="modal-id-row"><span class="modal-id-label">PubMed ID</span>${pmidLink}</div>
  <div class="modal-id-row"><span class="modal-id-label">全文 PDF</span>${pdfLink}</div>
</div>

<div class="modal-section modal-citation-section">
  <h4 class="modal-section-title">引用格式</h4>
  <div class="modal-citation-item">
    <span class="citation-format-label">APA</span>
    <span class="citation-text" id="citAPA">${esc(apa)}</span>
    <button class="btn-copy-cite" data-target="citAPA">复制</button>
  </div>
  <div class="modal-citation-item">
    <span class="citation-format-label">Vancouver</span>
    <span class="citation-text" id="citVancouver">${esc(van)}</span>
    <button class="btn-copy-cite" data-target="citVancouver">复制</button>
  </div>
</div>

${refsHtml}`;

    dom.modalBody.querySelectorAll(".btn-copy-cite").forEach((btn) => {
      btn.addEventListener("click", function () {
        copyText(document.getElementById(this.dataset.target)?.textContent || "", this);
      });
    });
  }

  function formatAbstract(text) {
    return text.split(/\n+/).map((p) => p.trim()).filter(Boolean)
      .map((p) => `<p>${esc(p)}</p>`).join("");
  }

  function buildAPA(a) {
    const authorStr = (a.authors || []).slice(0, 7).map((name) => {
      const parts = name.split(" ");
      return parts.length < 2 ? name : `${parts[parts.length-1]}, ${parts.slice(0,-1).map(p=>p[0]+".").join(" ")}`;
    }).join(", ");
    let cite = `${authorStr} (${a.year || "n.d."}). ${a.title}. ${a.venue || ""}`;
    if (a.doi) cite += `. https://doi.org/${a.doi}`;
    return cite;
  }

  function buildVancouver(a) {
    const authorStr = (a.authors || []).slice(0, 6).map((name) => {
      const parts = name.split(" ");
      return parts.length < 2 ? name : `${parts[parts.length-1]} ${parts.slice(0,-1).map(p=>p[0]).join("")}`;
    }).join(", ") + ((a.authors||[]).length > 6 ? " et al" : "");
    let cite = `${authorStr}. ${a.title}. ${a.venue || ""}. ${a.year || ""}`;
    if (a.doi) cite += `. doi:${a.doi}`;
    return cite;
  }

  function closeModal() {
    dom.modal.style.display = "none";
    document.body.style.overflow = "";
  }
  dom.modalClose.addEventListener("click", closeModal);
  dom.modal.addEventListener("click", (e) => { if (e.target === dom.modal) closeModal(); });

  // ── 趋势图 ───────────────────────────────────────
  async function fetchTrends(forceRedraw = false, attempt = 0) {
    try {
      const resp = await fetch((window.PHARMA_API_BASE || "") + `/api/pubmed/trends?q=${encodeURIComponent(currentQuery)}`);
      const data = await resp.json();
      if (!data.ok) return;

      if (data.pending && attempt < 8) {
        // 后台还在计算，4 秒后重试
        setTimeout(() => fetchTrends(forceRedraw, attempt + 1), 4000);
        return;
      }

      if (data.trends) renderTrends(data.trends);
    } catch (_) {}
  }

  function renderTrends(trends) {
    const years = Object.keys(trends).sort();
    const counts = years.map((y) => trends[y]);
    if (!years.length) return;

    dom.trendsTitle.textContent = `"${currentQuery}" 发文趋势`;
    dom.trendsSection.style.display = "block";

    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";
    const textColor = isDark ? "#a0aec0" : "#4a5568";

    if (trendsChart) trendsChart.destroy();
    trendsChart = new Chart($("#trendsChart"), {
      type: "line",
      data: {
        labels: years,
        datasets: [{
          label: "发文量",
          data: counts,
          borderColor: "#2563EB",
          backgroundColor: "rgba(37,99,235,0.10)",
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: "#2563EB",
          fill: true,
          tension: 0.35,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.y.toLocaleString()} 篇` } },
        },
        scales: {
          x: { grid: { color: gridColor }, ticks: { color: textColor } },
          y: { grid: { color: gridColor }, ticks: { color: textColor, callback: (v) => v.toLocaleString() }, beginAtZero: true },
        },
      },
    });
  }

  // ── 工具 ─────────────────────────────────────────
  function showState(state, errMsg = "") {
    dom.loadingState.style.display = "none";
    dom.emptyState.style.display   = "none";
    dom.errorState.style.display   = "none";
    dom.resultsSection.style.display = "none";
    dom.intro.style.display        = "none";

    if (state === "loading")  dom.loadingState.style.display = "flex";
    else if (state === "empty")   dom.emptyState.style.display = "block";
    else if (state === "error")   { dom.errorState.style.display = "block"; dom.errorMsg.textContent = errMsg || "请稍后重试"; }
    else if (state === "results") dom.resultsSection.style.display = "block";
    else if (state === "intro")   dom.intro.style.display = "block";
  }

  function esc(str) {
    if (str == null) return "";
    return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }

  async function copyText(text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
    }
    const orig = btn.textContent;
    btn.textContent = "✓ 已复制"; btn.classList.add("copied");
    setTimeout(() => { btn.textContent = orig; btn.classList.remove("copied"); }, 1800);
  }

  // ── 初始化 ───────────────────────────────────────
  showState("intro");

  const urlQ = new URLSearchParams(location.search).get("q");
  if (urlQ) { dom.searchInput.value = urlQ; triggerSearch(1); }

})();
