# PharmaPulse · 医药行业全球动向每日新闻推送

面向医药行业从业者的新闻聚合 + 学术文献检索平台。

## 线上访问

| 地址 | 说明 |
|------|------|
| **前端** | https://biweekly-report-6gpmft9d61d581e6-1416311162.tcloudbaseapp.com/web/index.html |
| **文献检索** | https://biweekly-report-6gpmft9d61d581e6-1416311162.tcloudbaseapp.com/web/literature.html |
| **后端 API** | https://pharmapulse-247016-7-1416311162.sh.run.tcloudbase.com |

## 本地开发

```bash
# 启动本地服务器
python server.py

# 访问
http://localhost:8080/web/index.html
```

## 部署架构（CloudBase）

| 资源 | 说明 |
|------|------|
| **Cloud Run** | 服务名 `pharmapulse`，Python 容器，1C2G，最小 1 实例 |
| **静态托管** | `web/` 目录，CDN 加速 |
| **环境 ID** | `biweekly-report-6gpmft9d61d581e6` |

## 更新部署

```bash
# 1. 同步文件到 cloudrun 目录
cp -r web/ cloudrun/pharmapulse/web/
cp -r scripts/ cloudrun/pharmapulse/scripts/
cp server.py cloudrun/pharmapulse/

# 2. 推送到 GitHub（触发记录）
git add -A && git commit -m "update" && git push

# 3. 在 CodeBuddy 中用 CloudBase 集成重新部署
```

## 功能模块

- 📰 **今日日报** — 自动聚合全球医药资讯，AI 生成中文摘要
- 🔍 **文献检索** — 基于 Semantic Scholar，覆盖 2 亿+ 论文
- 📚 **历史归档** — 按日期查看历史新闻
- 🌓 **暗色模式** — 全站支持，护眼阅读
