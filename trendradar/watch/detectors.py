# coding=utf-8
"""关注项检测器。"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional


PRICE_META_RE = re.compile(
    r"""(?:product:price:amount|price)["']?\s*[:=]\s*["']?(?P<price>\d+(?:\.\d{1,2})?)""",
    re.I,
)
PRICE_TEXT_RE = re.compile(
    r"""(?:¥|￥|RMB|CNY|\$)\s*(?P<price>\d[\d,]*(?:\.\d{1,2})?)""",
    re.I,
)


def _normalize_lines(text: str) -> List[str]:
    lines = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 4:
            continue
        if line.lower() in seen:
            continue
        seen.add(line.lower())
        lines.append(line)
    return lines


def detect_price(page: Dict[str, str], last_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    html_text = page.get("html", "")
    plain_text = page.get("text", "")

    value = None
    meta_match = PRICE_META_RE.search(html_text)
    if meta_match:
        value = meta_match.group("price")
    else:
        text_match = PRICE_TEXT_RE.search(plain_text)
        if text_match:
            value = text_match.group("price")

    if value is None:
        raise ValueError("未识别到价格")

    current_price = float(value.replace(",", ""))
    last_price = None
    if last_snapshot and last_snapshot.get("price") is not None:
        last_price = float(last_snapshot["price"])

    if last_price is None:
        message = f"当前价格 {current_price:.2f}，已记录为基线"
        changed = True
        event = "baseline"
    elif current_price < last_price:
        message = f"已降价：{last_price:.2f} -> {current_price:.2f}"
        changed = True
        event = "price_drop"
    elif current_price > last_price:
        message = f"未降价，当前价格 {current_price:.2f}（上次 {last_price:.2f}）"
        changed = False
        event = "price_up"
    else:
        message = f"未降价，当前仍为 {current_price:.2f}"
        changed = False
        event = "no_change"

    return {
        "changed": changed,
        "message": message,
        "snapshot": {
            "title": page.get("title", ""),
            "price": current_price,
            "event": event,
        },
    }


def detect_feed_update(page: Dict[str, str], last_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    lines = _normalize_lines(page.get("text", ""))
    if not lines:
        raise ValueError("页面正文为空")

    summary_lines = lines[:3]
    summary = " / ".join(summary_lines)
    identifier = hashlib.sha1(summary.encode("utf-8")).hexdigest()
    last_id = last_snapshot.get("latest_id") if last_snapshot else None

    if not last_id:
        changed = True
        message = f"已记录基线内容：{summary[:120]}"
        event = "baseline"
    elif identifier != last_id:
        changed = True
        message = f"有新更新：{summary[:120]}"
        event = "updated"
    else:
        changed = False
        message = "暂无更新"
        event = "no_change"

    return {
        "changed": changed,
        "message": message,
        "snapshot": {
            "title": page.get("title", ""),
            "latest_id": identifier,
            "summary": summary[:500],
            "event": event,
        },
    }


def detect_generic_change(page: Dict[str, str], last_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    lines = _normalize_lines(page.get("text", ""))
    summary = "\n".join(lines[:20])[:1000]
    if not summary:
        raise ValueError("页面主体内容为空")

    fingerprint = hashlib.sha1(summary.encode("utf-8")).hexdigest()
    last_fp = last_snapshot.get("fingerprint") if last_snapshot else None

    if not last_fp:
        changed = True
        message = "已记录页面基线内容"
        event = "baseline"
    elif fingerprint != last_fp:
        changed = True
        message = f"页面内容有变化：{summary[:120]}"
        event = "changed"
    else:
        changed = False
        message = "页面内容无明显变化"
        event = "no_change"

    return {
        "changed": changed,
        "message": message,
        "snapshot": {
            "title": page.get("title", ""),
            "summary": summary,
            "fingerprint": fingerprint,
            "event": event,
        },
    }
