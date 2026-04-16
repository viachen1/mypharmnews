"""
PharmaPulse - 数据索引生成器
扫描 data/ 目录，生成 data/index.json
前端通过读取 index.json 即可知道所有可用日期及其统计信息
"""

import json
import os
import glob
import re
from datetime import datetime, timezone, timedelta


def build_index(data_dir: str = None) -> dict:
    """
    扫描 data/ 目录中所有 YYYY-MM-DD.json 文件，
    生成一个索引文件供前端使用。
    """
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")

    entries = []
    json_files = glob.glob(os.path.join(data_dir, "*.json"))

    for filepath in json_files:
        filename = os.path.basename(filepath)

        # 跳过 index.json 本身
        if filename == "index.json":
            continue

        match = date_pattern.match(filename)
        if not match:
            continue

        date_str = match.group(1)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            entry = {
                "date": date_str,
                "total": data.get("total", 0),
                "stats": data.get("stats", {}),
                "generated_at": data.get("generated_at", ""),
            }
            entries.append(entry)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  [WARN] 跳过无效文件: {filename} ({e})")
            continue

    # 按日期倒序排列（最新在前）
    entries.sort(key=lambda x: x["date"], reverse=True)

    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)

    index_data = {
        "updated_at": now.isoformat(),
        "total_dates": len(entries),
        "latest_date": entries[0]["date"] if entries else None,
        "dates": entries,
    }

    return index_data


def save_index(data_dir: str = None) -> str:
    """生成并保存索引文件"""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    index_data = build_index(data_dir)
    filepath = os.path.join(data_dir, "index.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"  [INDEX] 索引已生成: {filepath}")
    print(f"  [INDEX] 包含 {index_data['total_dates']} 个日期，最新: {index_data['latest_date']}")

    return filepath


if __name__ == "__main__":
    save_index()
