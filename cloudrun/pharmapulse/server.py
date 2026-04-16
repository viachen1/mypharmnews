"""
PharmaPulse - CloudRun 容器版服务器
提供静态文件服务 + 数据刷新 API
端口: 8080
"""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
WEB_DIR = os.path.join(ROOT_DIR, "web")
DATA_DIR = os.path.join(ROOT_DIR, "data")

# 运行状态
pipeline_status = {
    "running": False,
    "last_run": None,
    "last_result": None,
    "progress": "",
}


def run_pipeline(skip_ai=False):
    """在后台线程中运行数据流水线（带细粒度进度更新）"""
    global pipeline_status

    pipeline_status["running"] = True
    pipeline_status["progress"] = "Initializing..."
    pipeline_status["last_result"] = None

    try:
        # 将 scripts 目录加入 sys.path
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)

        # 重新加载模块以获取最新代码（避免缓存问题）
        import importlib
        mods_to_reload = [
            "config", "fetch_news", "process",
            "ai_summary", "generate_json", "build_index", "main",
        ]
        for mod_name in mods_to_reload:
            if mod_name in sys.modules:
                importlib.reload(sys.modules[mod_name])

        from datetime import datetime as dt, timezone as tz, timedelta as td
        tz_cn = tz(td(hours=8))
        today = dt.now(tz_cn).strftime("%Y-%m-%d")

        # ── Step 1: Fetch ──
        pipeline_status["progress"] = "[1/4] Fetching international RSS feeds..."
        from fetch_news import fetch_rss_feeds, fetch_cn_rss_feeds, fetch_newsapi, fetch_gnews

        all_articles = []

        rss_articles = fetch_rss_feeds()
        all_articles.extend(rss_articles)
        pipeline_status["progress"] = f"[1/4] International RSS done ({len(rss_articles)} items). Fetching Chinese sources..."

        cn_articles = fetch_cn_rss_feeds()
        all_articles.extend(cn_articles)
        pipeline_status["progress"] = f"[1/4] CN sources done ({len(cn_articles)} items). Fetching APIs..."

        api_articles = fetch_newsapi()
        all_articles.extend(api_articles)

        gnews_articles = fetch_gnews()
        all_articles.extend(gnews_articles)

        total_fetched = len(all_articles)
        pipeline_status["progress"] = f"[1/4] Fetch complete: {total_fetched} articles total"

        if not all_articles:
            pipeline_status["last_result"] = "error"
            pipeline_status["progress"] = "Error: No articles fetched. Check network connection."
            return

        # ── Step 2: Process ──
        pipeline_status["progress"] = f"[2/4] Processing {total_fetched} articles (dedup, filter, classify)..."
        from process import process_articles
        processed = process_articles(all_articles)

        if not processed:
            pipeline_status["last_result"] = "error"
            pipeline_status["progress"] = "Error: All articles filtered out. Check keyword config."
            return

        pipeline_status["progress"] = f"[2/4] Processing done: {len(processed)} valid articles"

        # ── Step 3: AI Summary ──
        if skip_ai:
            pipeline_status["progress"] = "[3/4] Skipping AI summaries (fast mode)..."
            for a in processed:
                a["summary_zh"] = f"(Summary pending) {a['title'][:80]}"
        else:
            pipeline_status["progress"] = f"[3/4] Generating AI summaries for {len(processed)} articles..."
            from ai_summary import batch_generate_summaries
            processed = batch_generate_summaries(processed)

        pipeline_status["progress"] = "[3/4] Summaries done"

        # ── Step 4: Output JSON + Index ──
        pipeline_status["progress"] = "[4/4] Generating JSON output..."
        from generate_json import build_output, save_json
        output_data = build_output(processed, today)
        save_json(output_data, today)

        pipeline_status["progress"] = "[4/4] Building index..."
        from build_index import save_index
        save_index()

        pipeline_status["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
        pipeline_status["last_result"] = "success"
        pipeline_status["progress"] = f"Done! {output_data['total']} articles processed."

    except Exception as e:
        pipeline_status["last_result"] = "error"
        pipeline_status["progress"] = f"Error: {str(e)}"
        print(f"[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        pipeline_status["running"] = False


class PharmaPulseHandler(SimpleHTTPRequestHandler):
    """自定义请求处理器：静态文件 + API
    
    容器部署版本：
    - /data/* → 从 data/ 目录提供 JSON 数据
    - /api/*  → API 接口
    - /*      → 从 web/ 目录提供前端静态文件
    """

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: 获取流水线状态
        if path == "/api/status":
            self._json_response(pipeline_status)
            return

        # /data/* → 从 data/ 目录提供文件
        if path.startswith("/data/"):
            rel = path[len("/data/"):]
            file_path = os.path.join(DATA_DIR, rel.split("?")[0])
            self._serve_file(file_path, "application/json")
            return

        # 根路径 → index.html
        if path == "/" or path == "":
            file_path = os.path.join(WEB_DIR, "index.html")
            self._serve_file(file_path, "text/html; charset=utf-8")
            return

        # 尝试从 web/ 目录提供静态文件
        # 去掉开头的 /
        rel_path = path.lstrip("/")
        file_path = os.path.join(WEB_DIR, rel_path)

        if os.path.isfile(file_path):
            content_type = self._guess_type(file_path)
            self._serve_file(file_path, content_type)
            return

        # 404
        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # API: 触发数据刷新
        if path == "/api/refresh":
            if pipeline_status["running"]:
                self._json_response({
                    "ok": False,
                    "message": "数据流水线正在运行中，请稍候...",
                })
                return

            # 读取请求体
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                params = json.loads(body)
            except json.JSONDecodeError:
                params = {}

            skip_ai = params.get("skip_ai", False)

            # 在后台线程中运行
            t = threading.Thread(target=run_pipeline, args=(skip_ai,), daemon=True)
            t.start()

            self._json_response({
                "ok": True,
                "message": "数据刷新已启动！" + ("（跳过 AI 摘要）" if skip_ai else "（含 AI 摘要生成）"),
            })
            return

        self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, file_path, content_type):
        """提供文件内容"""
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404, "File not found")

    def _json_response(self, data, status=200):
        """返回 JSON 响应"""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _guess_type(self, path):
        """根据扩展名猜测 Content-Type"""
        ext = os.path.splitext(path)[1].lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".xml": "application/xml; charset=utf-8",
            ".txt": "text/plain; charset=utf-8",
        }
        return types.get(ext, "application/octet-stream")

    def log_message(self, format, *args):
        """自定义日志格式"""
        msg = format % args
        if "/api/" in msg or "404" in msg or "500" in msg:
            print(f"[SERVER] {msg}")


def main():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PharmaPulseHandler)

    print("=" * 50)
    print("  PharmaPulse Server (CloudRun)")
    print("=" * 50)
    print(f"  Port: {port}")
    print(f"  Root: {ROOT_DIR}")
    print(f"  Web:  {WEB_DIR}")
    print(f"  Data: {DATA_DIR}")
    print(f"  API:  POST /api/refresh")
    print(f"  API:  GET  /api/status")
    print("=" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped")
        server.server_close()


if __name__ == "__main__":
    main()
