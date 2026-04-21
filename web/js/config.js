/**
 * PharmaPulse - 环境配置
 * 本地开发：API 走相对路径（localhost:8080）
 * 线上生产：API 走 Cloud Run 地址
 */
(function () {
  var isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  window.PHARMA_API_BASE = isLocal
    ? ""   // 本地：相对路径
    : "https://pharmapulse-247016-7-1416311162.sh.run.tcloudbase.com"; // 线上 Cloud Run
})();
