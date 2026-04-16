/**
 * PharmaPulse - 前端主逻辑 v2
 * 数据索引加载、分类筛选、关键词搜索、摘要展开/折叠、日期导航
 */

(function () {
  "use strict";

  // ── 常量 ─────────────────────────────
  const CATEGORY_MAP = {
    regulatory: "政策监管",
    clinical:   "临床研究",
    corporate:  "企业动态",
    market:     "市场动态",
  };

  const CATEGORY_ICON = {
    regulatory: "📋",
    clinical:   "🔬",
    corporate:  "🏢",
    market:     "📈",
  };

  const IMPORTANCE_LABEL = {
    high:   "🔴 高",
    medium: "🟡 中",
    low:    "⚪ 低",
  };

  const REGION_LABEL = {
    domestic:      "🇨🇳 国内",
    international: "🌍 国际",
  };

  const DATA_BASE = "/data/";

  // ── 状态 ─────────────────────────────
  let allArticles = [];
  let indexData = null;          // data/index.json 索引
  let currentCategory = "all";
  let currentImportance = "all";
  let currentRegion = "all";     // all | domestic | international
  let currentDate = "";
  let searchQuery = "";
  let isAllExpanded = false;

  // ── DOM ──────────────────────────────
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const dom = {
    datePicker:         $("#datePicker"),
    prevDay:            $("#prevDay"),
    nextDay:            $("#nextDay"),
    displayDate:        $("#displayDate"),
    statTotal:          $("#statTotal"),
    statDomestic:       $("#statDomestic"),
    statInternational:  $("#statInternational"),
    statRegulatory:     $("#statRegulatory"),
    statClinical:       $("#statClinical"),
    statCorporate:      $("#statCorporate"),
    statMarket:         $("#statMarket"),
    regionTabs:         $("#regionTabs"),
    categoryTabs:       $("#categoryTabs"),
    importanceFilter:   $("#importanceFilter"),
    searchInput:        $("#searchInput"),
    searchClear:        $("#searchClear"),
    expandAllBtn:       $("#expandAllBtn"),
    highlightSection:   $("#highlightSection"),
    highlightList:      $("#highlightList"),
    domesticBlock:      $("#domesticBlock"),
    domesticList:       $("#domesticList"),
    domesticCount:      $("#domesticCount"),
    internationalBlock: $("#internationalBlock"),
    internationalList:  $("#internationalList"),
    internationalCount: $("#internationalCount"),
    emptyState:         $("#emptyState"),
    loadingState:       $("#loadingState"),
    errorState:         $("#errorState"),
    mobileMenuBtn:      $("#mobileMenuBtn"),
    mobileMenu:         $("#mobileMenu"),
    lastUpdated:        $("#lastUpdated"),
    // 刷新数据相关
    refreshBtn:         $("#refreshBtn"),
    refreshModal:       $("#refreshModal"),
    refreshModalClose:  $("#refreshModalClose"),
    startRefreshBtn:    $("#startRefreshBtn"),
    refreshProgress:    $("#refreshProgress"),
    refreshStatus:      $("#refreshStatus"),
    refreshResult:      $("#refreshResult"),
    refreshElapsed:     $("#refreshElapsed"),
    cancelRefreshBtn:   $("#cancelRefreshBtn"),
  };

  // ── 初始化 ───────────────────────────
  async function init() {
    bindEvents();

    // 先加载索引文件，获取最新可用日期
    await loadIndex();

    // 确定要显示的日期
    const params = new URLSearchParams(window.location.search);
    if (params.get("date")) {
      currentDate = params.get("date");
    } else if (indexData && indexData.latest_date) {
      currentDate = indexData.latest_date;
    } else {
      // 兜底: 使用 UTC+8 今天
      const now = new Date();
      const utc8 = new Date(now.getTime() + 8 * 3600 * 1000);
      currentDate = utc8.toISOString().slice(0, 10);
    }

    if (dom.datePicker) {
      dom.datePicker.value = currentDate;
    }

    loadData(currentDate);
  }

  function bindEvents() {
    if (dom.datePicker) {
      dom.datePicker.addEventListener("change", onDateChange);
    }
    if (dom.prevDay) {
      dom.prevDay.addEventListener("click", () => navigateDay(-1));
    }
    if (dom.nextDay) {
      dom.nextDay.addEventListener("click", () => navigateDay(1));
    }
    if (dom.regionTabs) {
      dom.regionTabs.addEventListener("click", onRegionTabClick);
    }
    if (dom.categoryTabs) {
      dom.categoryTabs.addEventListener("click", onTabClick);
    }
    if (dom.importanceFilter) {
      dom.importanceFilter.addEventListener("change", onImportanceChange);
    }
    if (dom.searchInput) {
      dom.searchInput.addEventListener("input", debounce(onSearchInput, 300));
      dom.searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          dom.searchInput.value = "";
          onSearchInput();
        }
      });
    }
    if (dom.searchClear) {
      dom.searchClear.addEventListener("click", () => {
        if (dom.searchInput) dom.searchInput.value = "";
        onSearchInput();
      });
    }
    if (dom.expandAllBtn) {
      dom.expandAllBtn.addEventListener("click", toggleExpandAll);
    }
    if (dom.mobileMenuBtn) {
      dom.mobileMenuBtn.addEventListener("click", toggleMobileMenu);
    }

    // 刷新数据按钮
    if (dom.refreshBtn) {
      dom.refreshBtn.addEventListener("click", openRefreshModal);
    }
    if (dom.refreshModalClose) {
      dom.refreshModalClose.addEventListener("click", closeRefreshModal);
    }
    if (dom.refreshModal) {
      dom.refreshModal.addEventListener("click", function (e) {
        if (e.target === dom.refreshModal) closeRefreshModal();
      });
    }
    if (dom.startRefreshBtn) {
      dom.startRefreshBtn.addEventListener("click", startRefresh);
    }
    if (dom.cancelRefreshBtn) {
      dom.cancelRefreshBtn.addEventListener("click", cancelRefresh);
    }

    // 键盘快捷键
    document.addEventListener("keydown", (e) => {
      // Ctrl+K 聚焦搜索框
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        if (dom.searchInput) dom.searchInput.focus();
      }
      // 左右方向键切换日期 (非输入框状态)
      if (document.activeElement.tagName !== "INPUT" && document.activeElement.tagName !== "TEXTAREA") {
        if (e.key === "ArrowLeft") navigateDay(-1);
        if (e.key === "ArrowRight") navigateDay(1);
      }
    });
  }

  // ── 索引加载 ─────────────────────────
  async function loadIndex() {
    try {
      const resp = await fetch(DATA_BASE + "index.json?t=" + Date.now());
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      indexData = await resp.json();

      // 显示最后更新时间
      if (dom.lastUpdated && indexData.updated_at) {
        const d = new Date(indexData.updated_at);
        dom.lastUpdated.textContent = "最后更新: " + formatDateTime(d);
        dom.lastUpdated.style.display = "inline";
      }
    } catch (err) {
      console.warn("索引文件不可用，将直接尝试加载当日数据:", err.message);
      indexData = null;
    }
  }

  // ── 数据加载 ─────────────────────────
  async function loadData(date) {
    showLoading(true);
    hideEmpty();
    hideError();

    const url = DATA_BASE + date + ".json?t=" + Date.now();

    try {
      const resp = await fetch(url);
      if (!resp.ok) {
        if (resp.status === 404) {
          throw new Error("NOT_FOUND");
        }
        throw new Error("HTTP " + resp.status);
      }

      const data = await resp.json();
      allArticles = data.articles || [];

      updateStats(data);
      updateDateNav();
      renderAll();
    } catch (err) {
      console.warn("加载数据失败:", err);
      allArticles = [];
      updateStats(null);

      if (err.message === "NOT_FOUND") {
        showError(date + " 暂无数据", "该日期没有新闻日报数据，请尝试其他日期。");
      } else {
        showError("数据加载失败", "请检查网络连接或稍后重试。");
      }
    } finally {
      showLoading(false);
    }
  }

  // ── 日期导航 ─────────────────────────
  function navigateDay(offset) {
    if (!currentDate) return;
    const d = new Date(currentDate + "T00:00:00");
    d.setDate(d.getDate() + offset);
    const newDate = d.toISOString().slice(0, 10);
    setDate(newDate);
  }

  function setDate(newDate) {
    if (newDate === currentDate) return;
    currentDate = newDate;
    if (dom.datePicker) dom.datePicker.value = newDate;

    // 更新 URL
    const url = new URL(window.location);
    url.searchParams.set("date", newDate);
    history.pushState(null, "", url);

    loadData(newDate);
  }

  function updateDateNav() {
    // 根据索引禁用/启用前后导航
    if (!indexData || !indexData.dates || indexData.dates.length === 0) return;

    const availDates = indexData.dates.map((d) => d.date);
    const currentIdx = availDates.indexOf(currentDate);

    if (dom.prevDay) {
      // 索引按倒序，所以 "上一天" 是 index + 1
      dom.prevDay.disabled = currentIdx === -1 || currentIdx >= availDates.length - 1;
      if (dom.prevDay.disabled) dom.prevDay.classList.add("disabled");
      else dom.prevDay.classList.remove("disabled");
    }
    if (dom.nextDay) {
      dom.nextDay.disabled = currentIdx <= 0;
      if (dom.nextDay.disabled) dom.nextDay.classList.add("disabled");
      else dom.nextDay.classList.remove("disabled");
    }
  }

  // ── 统计面板 ─────────────────────────
  function updateStats(data) {
    if (!data) {
      if (dom.statTotal)          dom.statTotal.textContent = "0";
      if (dom.statDomestic)       dom.statDomestic.textContent = "0";
      if (dom.statInternational)  dom.statInternational.textContent = "0";
      if (dom.statRegulatory)     dom.statRegulatory.textContent = "0";
      if (dom.statClinical)       dom.statClinical.textContent = "0";
      if (dom.statCorporate)      dom.statCorporate.textContent = "0";
      if (dom.statMarket)         dom.statMarket.textContent = "0";
      if (dom.displayDate)        dom.displayDate.textContent = formatDisplayDate(currentDate);
      return;
    }

    const stats = data.stats || {};
    const byCategory = stats.by_category || {};
    const byRegion = stats.by_region || {};

    // 如果数据中没有 by_region，则从文章中实时统计
    let domestic = byRegion.domestic || 0;
    let international = byRegion.international || 0;
    if (!byRegion.domestic && !byRegion.international && allArticles.length > 0) {
      domestic = allArticles.filter(function (a) { return _guessRegion(a) === "domestic"; }).length;
      international = allArticles.length - domestic;
    }

    if (dom.displayDate)        dom.displayDate.textContent = formatDisplayDate(data.date || currentDate);
    if (dom.statTotal)          animateNumber(dom.statTotal, data.total || 0);
    if (dom.statDomestic)       animateNumber(dom.statDomestic, domestic);
    if (dom.statInternational)  animateNumber(dom.statInternational, international);
    if (dom.statRegulatory)     animateNumber(dom.statRegulatory, byCategory.regulatory || 0);
    if (dom.statClinical)       animateNumber(dom.statClinical, byCategory.clinical || 0);
    if (dom.statCorporate)      animateNumber(dom.statCorporate, byCategory.corporate || 0);
    if (dom.statMarket)         animateNumber(dom.statMarket, byCategory.market || 0);
  }

  /**
   * 前端兜底：当 JSON 没有 region 字段时，根据标题中文字符占比推断地域
   */
  function _guessRegion(article) {
    if (article.region) return article.region;
    var title = article.title || "";
    var cnChars = 0;
    for (var i = 0; i < title.length; i++) {
      var code = title.charCodeAt(i);
      if (code >= 0x4e00 && code <= 0x9fff) cnChars++;
    }
    return (cnChars / Math.max(title.length, 1)) > 0.3 ? "domestic" : "international";
  }

  /** 数字跳动动画 */
  function animateNumber(el, target) {
    const start = parseInt(el.textContent) || 0;
    if (start === target) { el.textContent = target; return; }
    const duration = 500;
    const startTime = performance.now();
    function tick(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out
      el.textContent = Math.round(start + (target - start) * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ── 渲染 ─────────────────────────────
  function renderAll() {
    var filtered = filterArticles();

    // 分高重要度
    var highArticles = filtered.filter(function (a) { return a.importance === "high"; });
    var otherArticles = filtered.filter(function (a) { return a.importance !== "high"; });

    // 按地域拆分（非 high 的部分）
    var domesticArticles = otherArticles.filter(function (a) { return _guessRegion(a) === "domestic"; });
    var internationalArticles = otherArticles.filter(function (a) { return _guessRegion(a) !== "domestic"; });

    // ── 高重要度区域 ──
    if (dom.highlightSection && dom.highlightList) {
      if (highArticles.length > 0 && currentImportance !== "medium" && currentImportance !== "low") {
        dom.highlightSection.style.display = "block";
        dom.highlightList.innerHTML = highArticles.map(function (a, i) { return renderCard(a, i); }).join("");
      } else {
        dom.highlightSection.style.display = "none";
      }
    }

    // ── 国内板块 ──
    var showDomestic = currentRegion === "all" || currentRegion === "domestic";
    if (dom.domesticBlock) {
      if (showDomestic && domesticArticles.length > 0) {
        dom.domesticBlock.style.display = "block";
        dom.domesticList.innerHTML = domesticArticles.map(function (a, i) {
          return renderCard(a, i + highArticles.length);
        }).join("");
        if (dom.domesticCount) dom.domesticCount.textContent = domesticArticles.length + " 条";
      } else {
        dom.domesticBlock.style.display = "none";
      }
    }

    // ── 国际板块 ──
    var showIntl = currentRegion === "all" || currentRegion === "international";
    if (dom.internationalBlock) {
      if (showIntl && internationalArticles.length > 0) {
        dom.internationalBlock.style.display = "block";
        dom.internationalList.innerHTML = internationalArticles.map(function (a, i) {
          return renderCard(a, i + highArticles.length + domesticArticles.length);
        }).join("");
        if (dom.internationalCount) dom.internationalCount.textContent = internationalArticles.length + " 条";
      } else {
        dom.internationalBlock.style.display = "none";
      }
    }

    // 空状态
    if (filtered.length === 0 && allArticles.length > 0) {
      showEmpty("没有找到匹配的新闻", "尝试调整筛选条件或搜索关键词");
    } else if (filtered.length === 0) {
      // 无数据 - 错误状态已处理
    } else {
      hideEmpty();
    }

    // 搜索高亮
    if (searchQuery) {
      highlightSearchTerms();
    }

    // 绑定卡片事件
    bindCardEvents();
  }

  function filterArticles() {
    return allArticles.filter(function (a) {
      if (currentCategory !== "all" && a.category !== currentCategory) return false;
      if (currentImportance !== "all" && a.importance !== currentImportance) return false;
      if (currentRegion !== "all" && _guessRegion(a) !== currentRegion) return false;
      if (searchQuery) {
        var q = searchQuery.toLowerCase();
        var title = (a.title || "").toLowerCase();
        var summary = (a.summary_zh || "").toLowerCase();
        var source = (a.source || "").toLowerCase();
        var tags = (a.tags || []).join(" ").toLowerCase();
        if (!title.includes(q) && !summary.includes(q) && !source.includes(q) && !tags.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }

  function renderCard(article, index) {
    const importanceCls = "importance-" + article.importance;
    const dotCls = article.importance;
    const categoryLabel = CATEGORY_MAP[article.category] || article.category;
    const categoryIcon = CATEGORY_ICON[article.category] || "📄";
    const categoryCls = article.category;
    const importanceLabel = IMPORTANCE_LABEL[article.importance] || "";

    // 清理标题中的 HTML 标签
    let title = article.title || "";
    title = cleanTitle(title);

    // 提取原文链接
    let sourceUrl = article.source_url || "#";
    const hrefMatch = article.title && article.title.match(/href="([^"]+)"/);
    if (hrefMatch) sourceUrl = hrefMatch[1];

    // 时间格式化
    const timeStr = formatTime(article.published_at);

    // 摘要
    const summary = article.summary_zh || "";

    // 动画延迟
    const delay = Math.min(index * 30, 300);

    // 标签
    var regionVal = _guessRegion(article);
    var regionLabel = REGION_LABEL[regionVal] || "";
    let tagsHtml = '<span class="tag tag-region tag-region-' + regionVal + '">' + regionLabel + "</span>";
    tagsHtml += '<span class="tag tag-category ' + categoryCls + '">' + categoryIcon + " " + categoryLabel + "</span>";
    if (article.importance === "high" || article.importance === "medium") {
      tagsHtml += '<span class="tag tag-importance tag-importance-' + article.importance + '">' + importanceLabel + "</span>";
    }
    if (article.tags && article.tags.length > 0) {
      article.tags.slice(0, 3).forEach(function (t) {
        tagsHtml += '<span class="tag">' + escapeHtml(t) + "</span>";
      });
    }

    // 摘要 — 有真实 AI 摘要时默认展开
    const hasSummary = summary && summary.indexOf("(Summary pending)") === -1;
    const summaryCollapsed = hasSummary ? "" : "collapsed";
    const toggleState = hasSummary ? "expanded" : "collapsed";
    const toggleText = hasSummary ? "收起 ▲" : "展开摘要 ▼";
    const aiBadge = hasSummary ? '<span class="ai-badge">🤖 AI 摘要</span>' : '';

    return (
      '<div class="news-card ' + importanceCls + '" style="animation-delay:' + delay + 'ms">' +
        '<div class="card-header">' +
          '<span class="importance-dot ' + dotCls + '" title="' + importanceLabel + '"></span>' +
          '<h3 class="card-title">' +
            '<a href="' + escapeHtml(sourceUrl) + '" target="_blank" rel="noopener">' +
              escapeHtml(title) +
            "</a>" +
          "</h3>" +
          aiBadge +
        "</div>" +
        '<div class="card-meta">' +
          '<span class="card-source">' + escapeHtml(article.source || "") + "</span>" +
          '<span class="card-time">' + timeStr + "</span>" +
        "</div>" +
        '<div class="card-summary ' + summaryCollapsed + '" data-full="' + escapeAttr(summary) + '">' +
          escapeHtml(summary) +
        "</div>" +
        '<div class="card-footer">' +
          '<div class="card-tags">' + tagsHtml + "</div>" +
          '<div class="card-actions">' +
            '<button class="btn-toggle" data-state="' + toggleState + '" title="展开/折叠摘要">' + toggleText + '</button>' +
            '<a class="btn-read" href="' + escapeHtml(sourceUrl) + '" target="_blank" rel="noopener">阅读原文</a>' +
          "</div>" +
        "</div>" +
      "</div>"
    );
  }

  // ── 卡片交互 ─────────────────────────
  function bindCardEvents() {
    $$(".btn-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const card = btn.closest(".news-card");
        const summary = card.querySelector(".card-summary");
        const state = btn.getAttribute("data-state");

        if (state === "collapsed") {
          summary.classList.remove("collapsed");
          btn.setAttribute("data-state", "expanded");
          btn.textContent = "收起 ▲";
        } else {
          summary.classList.add("collapsed");
          btn.setAttribute("data-state", "collapsed");
          btn.textContent = "展开摘要 ▼";
        }
      });
    });
  }

  function toggleExpandAll() {
    isAllExpanded = !isAllExpanded;
    $$(".card-summary").forEach(function (el) {
      if (isAllExpanded) {
        el.classList.remove("collapsed");
      } else {
        el.classList.add("collapsed");
      }
    });
    $$(".btn-toggle").forEach(function (btn) {
      if (isAllExpanded) {
        btn.setAttribute("data-state", "expanded");
        btn.textContent = "收起 ▲";
      } else {
        btn.setAttribute("data-state", "collapsed");
        btn.textContent = "展开摘要 ▼";
      }
    });
    if (dom.expandAllBtn) {
      dom.expandAllBtn.textContent = isAllExpanded ? "全部折叠" : "全部展开";
    }
  }

  /** 搜索高亮 */
  function highlightSearchTerms() {
    if (!searchQuery) return;
    const q = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp("(" + q + ")", "gi");

    $$(".card-title a, .card-summary").forEach(function (el) {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
      const textNodes = [];
      while (walker.nextNode()) textNodes.push(walker.currentNode);

      textNodes.forEach(function (node) {
        if (regex.test(node.textContent)) {
          const span = document.createElement("span");
          span.innerHTML = node.textContent.replace(regex, '<mark class="search-highlight">$1</mark>');
          node.parentNode.replaceChild(span, node);
        }
      });
    });
  }

  // ── 事件处理 ─────────────────────────
  function onRegionTabClick(e) {
    var target = e.target.closest(".region-tab");
    if (!target) return;

    $$(".region-tab").forEach(function (t) { t.classList.remove("active"); });
    target.classList.add("active");

    currentRegion = target.getAttribute("data-region");
    renderAll();
  }

  function onTabClick(e) {
    const target = e.target;
    if (!target.classList.contains("tab")) return;

    $$(".tab").forEach(function (t) { t.classList.remove("active"); });
    target.classList.add("active");

    currentCategory = target.getAttribute("data-category");
    renderAll();
  }

  function onImportanceChange() {
    currentImportance = dom.importanceFilter.value;
    renderAll();
  }

  function onSearchInput() {
    searchQuery = dom.searchInput ? dom.searchInput.value.trim() : "";
    // 显示/隐藏清除按钮
    if (dom.searchClear) {
      dom.searchClear.style.display = searchQuery ? "inline-flex" : "none";
    }
    renderAll();
  }

  function onDateChange() {
    const newDate = dom.datePicker.value;
    if (newDate && newDate !== currentDate) {
      setDate(newDate);
    }
  }

  function toggleMobileMenu() {
    if (dom.mobileMenu) {
      dom.mobileMenu.classList.toggle("show");
    }
  }

  // ── 工具函数 ─────────────────────────
  function cleanTitle(title) {
    return title.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim();
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      const now = new Date();
      const diffMs = now - d;
      const diffH = Math.floor(diffMs / 3600000);
      const diffMin = Math.floor(diffMs / 60000);

      if (diffMin < 5) return "刚刚";
      if (diffMin < 60) return diffMin + "分钟前";
      if (diffH < 24) return diffH + "小时前";
      if (diffH < 48) return "昨天";

      // 超过2天显示具体日期
      const year = d.getFullYear();
      const month = d.getMonth() + 1;
      const day = d.getDate();
      const nowYear = now.getFullYear();
      if (year === nowYear) {
        return month + "月" + day + "日";
      }
      return year + "年" + month + "月" + day + "日";
    } catch (e) {
      return isoStr.slice(0, 10);
    }
  }

  function formatDisplayDate(dateStr) {
    if (!dateStr) return "--";
    try {
      const d = new Date(dateStr + "T00:00:00");
      const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
      const y = d.getFullYear();
      const m = d.getMonth() + 1;
      const day = d.getDate();
      const w = weekdays[d.getDay()];
      return y + "年" + m + "月" + day + "日 " + w;
    } catch (e) {
      return dateStr;
    }
  }

  function formatDateTime(d) {
    try {
      const m = d.getMonth() + 1;
      const day = d.getDate();
      const h = d.getHours().toString().padStart(2, "0");
      const min = d.getMinutes().toString().padStart(2, "0");
      return m + "月" + day + "日 " + h + ":" + min;
    } catch (e) {
      return "";
    }
  }

  function debounce(fn, ms) {
    let timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, arguments), ms);
    };
  }

  function showLoading(show) {
    if (dom.loadingState) {
      dom.loadingState.style.display = show ? "flex" : "none";
    }
  }

  function showEmpty(title, subtitle) {
    if (dom.emptyState) {
      dom.emptyState.style.display = "block";
      const h = dom.emptyState.querySelector(".empty-title");
      const p = dom.emptyState.querySelector(".empty-subtitle");
      if (h) h.textContent = title || "没有找到匹配的新闻";
      if (p) p.textContent = subtitle || "";
    }
  }
  function hideEmpty() {
    if (dom.emptyState) dom.emptyState.style.display = "none";
  }

  function showError(title, msg) {
    if (dom.errorState) {
      dom.errorState.style.display = "block";
      const h = dom.errorState.querySelector(".error-title");
      const p = dom.errorState.querySelector(".error-msg");
      if (h) h.textContent = title;
      if (p) p.textContent = msg;
    }
    // 同时清空列表
    if (dom.domesticList) dom.domesticList.innerHTML = "";
    if (dom.internationalList) dom.internationalList.innerHTML = "";
    if (dom.domesticBlock) dom.domesticBlock.style.display = "none";
    if (dom.internationalBlock) dom.internationalBlock.style.display = "none";
    if (dom.highlightSection) dom.highlightSection.style.display = "none";
  }
  function hideError() {
    if (dom.errorState) dom.errorState.style.display = "none";
  }

  // ── 刷新数据功能 ───────────────────────
  function openRefreshModal() {
    if (dom.refreshModal) {
      dom.refreshModal.style.display = "flex";
      // 重置状态
      if (dom.startRefreshBtn) {
        dom.startRefreshBtn.disabled = false;
        dom.startRefreshBtn.textContent = "开始刷新";
      }
      if (dom.refreshProgress) dom.refreshProgress.style.display = "none";
      if (dom.refreshResult) dom.refreshResult.style.display = "none";
    }
  }

  function closeRefreshModal() {
    if (dom.refreshModal) {
      dom.refreshModal.style.display = "none";
    }
    // 停止按钮旋转
    if (dom.refreshBtn) dom.refreshBtn.classList.remove("spinning");
  }

  let refreshPollTimer = null;
  let refreshElapsedTimer = null;
  let refreshStartTime = null;

  function cancelRefresh() {
    // 停止轮询和计时
    if (refreshPollTimer) { clearInterval(refreshPollTimer); refreshPollTimer = null; }
    if (refreshElapsedTimer) { clearInterval(refreshElapsedTimer); refreshElapsedTimer = null; }
    if (dom.refreshProgress) dom.refreshProgress.style.display = "none";
    showRefreshResult("error", "已取消。后台任务可能仍在运行，关闭弹窗即可。");
    resetRefreshUI();
  }

  function updateElapsed() {
    if (!refreshStartTime || !dom.refreshElapsed) return;
    var secs = Math.floor((Date.now() - refreshStartTime) / 1000);
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    dom.refreshElapsed.textContent = "已用时 " + (m > 0 ? m + " 分 " : "") + s + " 秒";
  }

  function startRefresh() {
    // 获取选择的模式
    const modeRadio = document.querySelector('input[name="refreshMode"]:checked');
    const skipAi = modeRadio && modeRadio.value === "fast";

    // 禁用按钮
    if (dom.startRefreshBtn) {
      dom.startRefreshBtn.disabled = true;
      dom.startRefreshBtn.textContent = "刷新中...";
    }

    // 显示进度
    if (dom.refreshProgress) dom.refreshProgress.style.display = "block";
    if (dom.refreshStatus) dom.refreshStatus.textContent = "正在启动数据流水线...";
    if (dom.refreshResult) dom.refreshResult.style.display = "none";

    // 导航栏按钮旋转动画
    if (dom.refreshBtn) dom.refreshBtn.classList.add("spinning");

    // 启动计时器
    refreshStartTime = Date.now();
    if (dom.refreshElapsed) dom.refreshElapsed.textContent = "";
    if (refreshElapsedTimer) clearInterval(refreshElapsedTimer);
    refreshElapsedTimer = setInterval(updateElapsed, 1000);

    // 调用 API
    fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skip_ai: skipAi }),
    })
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.ok) {
          if (dom.refreshStatus) dom.refreshStatus.textContent = data.message;
          // 开始轮询状态
          startPolling();
        } else {
          showRefreshResult("error", data.message || "启动失败");
          resetRefreshUI();
        }
      })
      .catch(function (err) {
        showRefreshResult("error", "无法连接到服务器。请确保通过 python server.py 启动。");
        resetRefreshUI();
      });
  }

  function startPolling() {
    if (refreshPollTimer) clearInterval(refreshPollTimer);
    refreshPollTimer = setInterval(pollStatus, 2000);
  }

  function pollStatus() {
    fetch("/api/status")
      .then(function (resp) { return resp.json(); })
      .then(function (status) {
        if (dom.refreshStatus) {
          dom.refreshStatus.textContent = translateProgress(status.progress || "Running...");
        }

        if (!status.running) {
          // 流水线结束
          clearInterval(refreshPollTimer);
          refreshPollTimer = null;

          if (dom.refreshProgress) dom.refreshProgress.style.display = "none";

          if (status.last_result === "success") {
            showRefreshResult("success", "\u2705 数据刷新完成！页面将自动重新加载数据。");
            // 重新加载当前日期的数据
            setTimeout(function () {
              loadIndex().then(function () {
                // 更新日期为最新
                if (indexData && indexData.latest_date) {
                  currentDate = indexData.latest_date;
                  if (dom.datePicker) dom.datePicker.value = currentDate;
                }
                loadData(currentDate);
              });
            }, 1000);
          } else if (status.last_result === "error") {
            showRefreshResult("error", translateProgress(status.progress) || "\u274c 刷新失败，请查看服务器日志。");
          }

          resetRefreshUI();
        }
      })
      .catch(function () {
        // 轮询失败时静默处理
      });
  }

  /** 将后端英文进度翻译为中文显示 */
  function translateProgress(msg) {
    if (!msg) return "运行中...";
    return msg
      .replace("Initializing...", "正在初始化...")
      .replace("Fetching international RSS feeds...", "正在抓取国际 RSS 数据源...")
      .replace(/International RSS done \((\d+) items\)\. Fetching Chinese sources\.\.\./, "国际 RSS 完成（$1 条），正在抓取国内数据源...")
      .replace(/CN sources done \((\d+) items\)\. Fetching APIs\.\.\./, "国内数据源完成（$1 条），正在抓取 API 补充数据...")
      .replace(/Fetch complete: (\d+) articles total/, "抓取完成，共 $1 条原始数据")
      .replace(/Processing (\d+) articles \(dedup, filter, classify\)\.\.\./, "正在处理 $1 条数据（去重、过滤、分类）...")
      .replace(/Processing done: (\d+) valid articles/, "处理完成，$1 条有效文章")
      .replace(/Skipping AI summaries \(fast mode\)\.\.\./, "跳过 AI 摘要（快速模式）...")
      .replace(/Generating AI summaries for (\d+) articles\.\.\./, "正在为 $1 篇文章生成 AI 中文摘要...")
      .replace("Summaries done", "AI 摘要生成完成")
      .replace("Generating JSON output...", "正在生成 JSON 数据文件...")
      .replace("Building index...", "正在构建数据索引...")
      .replace(/Done! (\d+) articles processed\./, "完成！共处理 $1 条新闻。")
      .replace("Error: No articles fetched. Check network connection.", "错误：未获取到任何数据，请检查网络连接。")
      .replace("Error: All articles filtered out. Check keyword config.", "错误：所有文章都被过滤，请检查关键词配置。")
      .replace(/^Error: (.+)$/, "错误：$1")
      .replace("Running...", "运行中...");
  }

  function showRefreshResult(type, message) {
    if (dom.refreshResult) {
      dom.refreshResult.style.display = "block";
      dom.refreshResult.className = "refresh-result " + type;
      dom.refreshResult.textContent = message;
    }
  }

  function resetRefreshUI() {
    if (dom.startRefreshBtn) {
      dom.startRefreshBtn.disabled = false;
      dom.startRefreshBtn.textContent = "开始刷新";
    }
    if (dom.refreshBtn) dom.refreshBtn.classList.remove("spinning");
    if (refreshElapsedTimer) { clearInterval(refreshElapsedTimer); refreshElapsedTimer = null; }
  }

  // ── 启动 ─────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
