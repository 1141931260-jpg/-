# coding=utf-8
"""模拟运行 bilibili_up watch，展示推送结果。"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trendradar.watch.service import WatchService
from trendradar.watch.formatter import build_watch_report_data
from trendradar.core import load_config


def main():
    config = load_config()
    service = WatchService(config)

    # 1. 运行 bilibili_up watch
    results = []
    watches = service.state.setdefault("watches", {})
    for item in service._load_items():
        if not item.enabled:
            continue
        if item.mode != "bilibili_up" and item.watch_type != "bilibili_up":
            continue
        watch_state = watches.setdefault(item.id, {})
        watch_state["title"] = item.title
        watch_state["watch_type"] = item.watch_type
        try:
            result = service._run_bilibili_up_watch(item, watch_state)
            results.append(result)
        except Exception as exc:
            print(f"Error: {exc}")
            continue

    if not results:
        print("没有找到 bilibili_up 类型的 watch")
        return

    # 2. 格式化为报告
    report = build_watch_report_data(results)

    # 3. 生成企业微信 markdown 推送内容
    print("=" * 60)
    print("📺 模拟推送内容（企业微信 Markdown）")
    print("=" * 60)
    print()

    for stat in report.get("stats", []):
        print(f"### 📰 {stat['word']}")
        print()
        for t in stat.get("titles", []):
            title = t.get("title", "")
            url = t.get("url", "")
            meta = t.get("meta_line", "")
            if url:
                print(f"- [{title}]({url})")
            else:
                print(f"- {title}")
            if meta:
                print(f"  > {meta}")
        print()

    total = report.get("total_new_count", 0)
    print(f"共 **{total}** 条内容")
    print()

    # 4. 展示原始结果
    print("=" * 60)
    print("📊 原始结果 JSON（调试用）")
    print("=" * 60)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
