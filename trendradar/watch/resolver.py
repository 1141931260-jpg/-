# coding=utf-8
"""关注项来源发现。"""

from __future__ import annotations

import html
import re
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

import requests


RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.I | re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


def search_candidates(
    query: str,
    max_candidates: int = 3,
    user_agent: str = "TrendRadar Watch/1.0",
    proxy_url: Optional[str] = None,
) -> List[Dict[str, str]]:
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    url = f"https://duckduckgo.com/html/?q={quote(query)}"
    response = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=15,
        proxies=proxies,
    )
    response.raise_for_status()

    candidates: List[Dict[str, str]] = []
    for match in RESULT_LINK_RE.finditer(response.text):
        href = html.unescape(match.group("href")).strip()
        title = html.unescape(TAG_RE.sub("", match.group("title"))).strip()
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin("https://duckduckgo.com", href)
        candidates.append({"url": href, "title": title})
        if len(candidates) >= max_candidates:
            break
    return candidates
