"""
PharmaPulse - 一键构建脚本
完整流程: 抓取数据 -> 处理 -> AI摘要 -> 输出JSON -> 生成索引
可用于 GitHub Actions 或本地手动运行
"""

import sys
import os

# 确保可以导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import run
from build_index import save_index


def build(skip_ai: bool = False):
    """运行完整构建流程"""

    print("\n" + "=" * 60)
    print("  PharmaPulse Build Pipeline")
    print("=" * 60)

    # Step 1: 运行数据抓取 + 处理 + AI摘要 + JSON输出
    print("\n📡 [1/2] 运行数据流...")
    run(skip_ai=skip_ai)

    # Step 2: 生成索引文件
    print("\n📋 [2/2] 生成数据索引...")
    save_index()

    print("\n" + "=" * 60)
    print("  ✅ 构建完成！")
    print("  前端页面: web/index.html")
    print("  数据目录: data/")
    print("  索引文件: data/index.json")
    print("=" * 60)


if __name__ == "__main__":
    skip = "--skip-ai" in sys.argv
    build(skip_ai=skip)
