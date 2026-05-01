# coding=utf-8
"""关注项结果格式化。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _normalize_watch_time_display(value: str) -> str:
    if not value:
        return ""
    parts = value.split(" ", 1)
    if not parts:
        return value
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ""
    if "-" not in date_part:
        return value
    date_bits = date_part.split("-")
    if len(date_bits) != 2:
        return value
    month = str(int(date_bits[0])) if date_bits[0].isdigit() else date_bits[0]
    day = date_bits[1]
    normalized = f"{month}-{day}"
    return f"{normalized} {time_part}".strip()


def build_watch_report_data(results: List[Dict], rank_threshold: int = 10) -> Dict:
    stats = []
    total_new_count = 0

    for result in results:
        grouped_items = result.get("items") or []
        if grouped_items:
            titles = []
            for index, news in enumerate(grouped_items, start=1):
                source_name = news.get("source_name", result.get("source_name", "topic_news"))
                time_display = _normalize_watch_time_display(news.get("time_display", ""))
                meta_line = "｜".join(part for part in [time_display, source_name] if part)
                titles.append(
                    {
                        "title": news.get("title", ""),
                        "source_name": source_name,
                        "time_display": time_display,
                        "count": 1,
                        "ranks": [index],
                        "rank_threshold": rank_threshold,
                        "url": news.get("url", ""),
                        "mobileUrl": news.get("url", ""),
                        "is_new": False,
                        "compact_watch": True,
                        "meta_line": meta_line,
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
        source_name = result.get("source_name", result.get("watch_type", "watch"))
        time_display = _normalize_watch_time_display(result.get("time_display", ""))
        meta_line = "｜".join(part for part in [time_display, source_name] if part)
        item = {
            "title": result["message"],
            "source_name": source_name,
            "time_display": time_display,
            "count": 1,
            "ranks": [1],
            "rank_threshold": rank_threshold,
            "url": result.get("url", ""),
            "mobileUrl": result.get("url", ""),
            "is_new": False,
            "compact_watch": True,
            "meta_line": meta_line,
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
