# coding=utf-8
"""关注项结果格式化。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List


def build_watch_report_data(results: List[Dict], rank_threshold: int = 10) -> Dict:
    stats = []
    total_new_count = 0

    for result in results:
        grouped_items = result.get("items") or []
        if grouped_items:
            titles = []
            for index, news in enumerate(grouped_items, start=1):
                titles.append(
                    {
                        "title": f"{news.get('title', '')}\n来源：{news.get('source_name', '')}",
                        "source_name": news.get("source_name", result.get("source_name", "topic_news")),
                        "time_display": news.get("time_display", ""),
                        "count": 1,
                        "ranks": [index],
                        "rank_threshold": rank_threshold,
                        "url": news.get("url", ""),
                        "mobileUrl": news.get("url", ""),
                        "is_new": True,
                    }
                )
            total_new_count += len(titles)
            stats.append(
                {
                    "word": result["title"],
                    "count": len(titles),
                    "titles": titles,
                }
            )
            continue

        total_new_count += 1
        item = {
            "title": result["message"],
            "source_name": result.get("source_name", result.get("watch_type", "watch")),
            "time_display": result.get("time_display", ""),
            "count": 1,
            "ranks": [1],
            "rank_threshold": rank_threshold,
            "url": result.get("url", ""),
            "mobileUrl": result.get("url", ""),
            "is_new": result.get("changed", False),
        }
        stats.append(
            {
                "word": result["title"],
                "count": 1,
                "titles": [item],
            }
        )

    return {
        "stats": stats,
        "new_titles": [],
        "failed_ids": [],
        "total_new_count": total_new_count,
    }


def generate_watch_html(report_data: Dict, output_dir: str, date_folder: str, time_filename: str) -> str:
    html_dir = Path(output_dir) / "html" / date_folder
    html_dir.mkdir(parents=True, exist_ok=True)
    html_file = html_dir / f"{time_filename}.html"

    lines = [
        "<!DOCTYPE html>",
        "<html lang=\"zh-CN\">",
        "<head><meta charset=\"UTF-8\"><title>关注项最新消息</title></head>",
        "<body>",
        "<h1>关注项最新消息</h1>",
        f"<p>生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        "<ul>",
    ]
    for stat in report_data.get("stats", []):
        lines.append(f"<li><strong>{stat['word']}</strong><ul>")
        for title_line in stat.get("titles", []):
            url = title_line.get("url", "")
            message = title_line.get("title", "")
            if url:
                lines.append(f"<li><a href=\"{url}\">{message}</a></li>")
            else:
                lines.append(f"<li>{message}</li>")
        lines.append("</ul></li>")
    lines.extend(["</ul>", "</body>", "</html>"])
    html_file.write_text("\n".join(lines), encoding="utf-8")
    return str(html_file)
