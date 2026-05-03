# coding=utf-8
"""网页抓取与基础提取。"""

from __future__ import annotations

import html
import re
from typing import Dict, Optional
from urllib.parse import urlparse

import requests


SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"[ \t]+")
LINE_RE = re.compile(r"\n+")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def extract_text(raw_html: str) -> str:
    cleaned = SCRIPT_RE.sub(" ", raw_html)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"</(p|div|li|section|article|h\d)>", "\n", cleaned, flags=re.I)
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\r", "\n")
    cleaned = SPACE_RE.sub(" ", cleaned)
    cleaned = LINE_RE.sub("\n", cleaned)
    return cleaned.strip()


def extract_title(raw_html: str) -> str:
    match = TITLE_RE.search(raw_html)
    if not match:
        return ""
    return html.unescape(TAG_RE.sub("", match.group(1))).strip()


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def fetch_page(
    url: str,
    timeout: int = 15,
    user_agent: str = "GEINEWS Watch/1.0",
    proxy_url: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if extra_headers:
        headers.update({k: str(v) for k, v in extra_headers.items()})
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    response = requests.get(
        url,
        headers=headers,
        timeout=timeout,
        proxies=proxies,
        cookies=cookies or None,
    )
    response.raise_for_status()

    # Some official sites incorrectly default to ISO-8859-1 in requests.
    # Prefer the apparent encoding in that case to avoid mojibake in summaries.
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1", "latin1"}:
        apparent = getattr(response, "apparent_encoding", None)
        if apparent:
            response.encoding = apparent

    raw_html = response.text
    return {
        "url": response.url,
        "domain": extract_domain(response.url),
        "title": extract_title(raw_html),
        "html": raw_html,
        "text": extract_text(raw_html),
    }
