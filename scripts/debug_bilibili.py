# coding=utf-8
"""诊断 bilibili_up watch 调用链。"""
import json, sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from trendradar.watch.service import WatchService
from trendradar.core import load_config

config = load_config()
service = WatchService(config)

watches = service.state.setdefault("watches", {})
for item in service._load_items():
    if item.mode != "bilibili_up" and item.watch_type != "bilibili_up":
        continue
    watch_state = watches.setdefault(item.id, {})
    print(f"query: {item.query}")
    print(f"title_filter: {item.backend_options.get('title_filter', '')}")
    print(f"max_items: {item.max_items}")
    print(f"timeout: {service.timeout}")
    try:
        result = service._run_bilibili_up_watch(item, watch_state)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(f"EXCEPTION: {exc}")
        traceback.print_exc()
    break
