/**
 * PharmaPulse - 环境配置
 * 本地开发：API 走相对路径（localhost:8080）
 * 线上生产：后端 API 地址（仅作备用，实际优先前端直连 Semantic Scholar）
 */
(function () {
  var isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  // 后端地址（仅在前端直连失败时降级使用）
  window.PHARMA_API_BASE = isLocal
    ? ""
    : "https://pharmapulse-247016-7-1416311162.sh.run.tcloudbase.com";
  // 线上强制走前端直连，避免 Cloud Run IP 被 Semantic Scholar 限速
  window.PHARMA_FORCE_DIRECT = !isLocal;
})();
