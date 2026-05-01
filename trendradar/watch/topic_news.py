# coding=utf-8
"""主题最新消息聚合。"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests

from .fetcher import extract_domain


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
GOOGLE_NEWS_SOURCE_SUFFIX_RE = re.compile(r"\s*-\s*([^-\n]{2,60})$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _clean_text(value: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", value or ""))
    return SPACE_RE.sub(" ", text).strip()


def _parse_dt(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if ISO_RE.match(raw):
            normalized = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _source_from_title(title: str) -> str:
    match = GOOGLE_NEWS_SOURCE_SUFFIX_RE.search(title or "")
    if not match:
        return ""
    return match.group(1).strip()


def _title_without_source_suffix(title: str) -> str:
    if not title:
        return ""
    match = GOOGLE_NEWS_SOURCE_SUFFIX_RE.search(title)
    if not match:
        return title.strip()
    return title[: match.start()].strip()


def _normalize_key(value: str) -> str:
    cleaned = re.sub(r"https?://", "", (value or "").strip().lower())
    cleaned = re.sub(r"[\W_]+", "", cleaned)
    return cleaned


def _build_keywords(item) -> List[str]:
    raw_keywords = list(item.keywords or [])
    if raw_keywords:
        return [keyword.strip() for keyword in raw_keywords if keyword and keyword.strip()]
    return [part.strip() for part in re.split(r"\s+", item.query or item.title) if len(part.strip()) >= 2]


def _build_exclude_keywords(item) -> List[str]:
    raw_keywords = list(item.backend_options.get("exclude_keywords", []) or [])
    return [keyword.strip() for keyword in raw_keywords if keyword and keyword.strip()]


def _relevance_score(text: str, keywords: List[str]) -> int:
    haystack = (text or "").lower()
    score = 0
    for keyword in keywords:
        if keyword.lower() in haystack:
            score += 1
    return score


def _contains_any(text: str, keywords: List[str]) -> bool:
    haystack = (text or "").lower()
    for keyword in keywords:
        if keyword.lower() in haystack:
            return True
    return False


def _google_news_feed_url(query: str, hours: int) -> str:
    hours = max(1, hours)
    q = quote(f"{query} when:{hours}h")
    return f"https://news.google.com/rss/search?q={q}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def _parse_github_repo_hint(hint: str) -> Optional[str]:
    parsed = urlparse(hint)
    if "github.com" not in parsed.netloc.lower():
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _build_feed_specs(item) -> List[Dict[str, str]]:
    specs: List[Dict[str, str]] = []
    seen = set()

    def add(url: str, source_type: str, source_name: str) -> None:
        key = url.strip()
        if not key or key in seen:
            return
        seen.add(key)
        specs.append(
            {
                "url": key,
                "source_type": source_type,
                "source_name": source_name,
            }
        )

    query = item.query or item.title
    official_only = str(getattr(item, "source_policy", "") or "").strip().lower() == "official_only"
    if item.backend_options.get("general_search", True):
        add(_google_news_feed_url(query, item.time_window_hours), "media", "Google News")

    for hint in item.source_hints:
        repo = _parse_github_repo_hint(hint)
        if repo:
            add(f"https://github.com/{repo}/releases.atom", "community", f"GitHub {repo}")
            continue

        domain = hint.replace("https://", "").replace("http://", "").strip().strip("/")
        if not domain:
            continue
        if official_only:
            continue
        add(
            _google_news_feed_url(f"{query} site:{domain}", item.time_window_hours),
            "official" if domain.endswith(".gov.cn") or "deepseek.com" in domain else "media",
            domain,
        )

    for url in item.source_urls:
        repo = _parse_github_repo_hint(url)
        if repo:
            add(f"https://github.com/{repo}/releases.atom", "community", f"GitHub {repo}")
            continue
        add(url, "official", extract_domain(url) or "feed")

    return specs


def _fetch_xml(url: str, timeout: int, user_agent: str, proxy_url: Optional[str]) -> str:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() in {"iso-8859-1", "latin-1", "latin1"}:
        apparent = getattr(response, "apparent_encoding", None)
        if apparent:
            response.encoding = apparent
    return response.text


def _parse_rss_items(xml_text: str, default_type: str, default_name: str) -> List[Dict]:
    root = ET.fromstring(xml_text)
    items: List[Dict] = []
    for node in root.findall(".//item"):
        title = _clean_text(node.findtext("title", ""))
        if not title:
            continue
        link = (node.findtext("link", "") or "").strip()
        published_at = _parse_dt(node.findtext("pubDate", "") or node.findtext("published", ""))
        source_name = _clean_text(node.findtext("source", "")) or _source_from_title(title) or default_name
        summary = _clean_text(node.findtext("description", "")) or title
        items.append(
            {
                "title": _title_without_source_suffix(title),
                "summary": summary[:280],
                "url": link,
                "source_name": source_name,
                "source_type": default_type,
                "published_at": published_at,
            }
        )
    return items


def _parse_atom_items(xml_text: str, default_type: str, default_name: str) -> List[Dict]:
    root = ET.fromstring(xml_text)
    items: List[Dict] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = _clean_text(entry.findtext("atom:title", "", ATOM_NS))
        if not title:
            continue
        link = ""
        for link_node in entry.findall("atom:link", ATOM_NS):
            href = (link_node.attrib.get("href") or "").strip()
            rel = (link_node.attrib.get("rel") or "alternate").strip()
            if href and rel == "alternate":
                link = href
                break
        published_at = _parse_dt(
            entry.findtext("atom:updated", "", ATOM_NS) or entry.findtext("atom:published", "", ATOM_NS)
        )
        summary = _clean_text(
            entry.findtext("atom:summary", "", ATOM_NS) or entry.findtext("atom:content", "", ATOM_NS)
        )
        items.append(
            {
                "title": title,
                "summary": (summary or title)[:280],
                "url": link,
                "source_name": default_name,
                "source_type": default_type,
                "published_at": published_at,
            }
        )
    return items


def _parse_sitemap_items(xml_text: str, default_type: str, default_name: str) -> List[Dict]:
    root = ET.fromstring(xml_text)
    items: List[Dict] = []
    for node in root.findall("sm:url", SITEMAP_NS):
        loc = (node.findtext("sm:loc", "", SITEMAP_NS) or "").strip()
        if not loc:
            continue
        lastmod = _parse_dt(node.findtext("sm:lastmod", "", SITEMAP_NS))
        slug = loc.rstrip("/").split("/")[-1]
        title = slug.replace("-", " ").replace("_", " ").strip() or loc
        # Heuristic for DeepSeek-style slugs like news260424 -> 2026-04-24
        date_match = re.search(r"news(\d{2})(\d{2})(\d{2})$", slug)
        if date_match and not lastmod:
            yy, mm, dd = date_match.groups()
            year = 2000 + int(yy)
            try:
                lastmod = datetime(year, int(mm), int(dd), tzinfo=timezone.utc)
            except ValueError:
                lastmod = None
        items.append(
            {
                "title": title,
                "summary": title,
                "url": loc,
                "source_name": default_name,
                "source_type": default_type,
                "published_at": lastmod,
            }
        )
    return items


def _fetch_feed_items(spec: Dict[str, str], timeout: int, user_agent: str, proxy_url: Optional[str]) -> List[Dict]:
    xml_text = _fetch_xml(spec["url"], timeout=timeout, user_agent=user_agent, proxy_url=proxy_url)
    if "<urlset" in xml_text:
        return _parse_sitemap_items(xml_text, spec["source_type"], spec["source_name"])
    try:
        return _parse_rss_items(xml_text, spec["source_type"], spec["source_name"])
    except Exception:
        return _parse_atom_items(xml_text, spec["source_type"], spec["source_name"])


def collect_topic_news(item, timeout: int, user_agent: str, proxy_url: Optional[str] = None) -> Dict[str, object]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(item.time_window_hours)))
    keywords = _build_keywords(item)
    exclude_keywords = _build_exclude_keywords(item)
    all_items: List[Dict] = []
    errors: List[str] = []

    for spec in _build_feed_specs(item):
        try:
            fetched = _fetch_feed_items(spec, timeout=timeout, user_agent=user_agent, proxy_url=proxy_url)
            for entry in fetched:
                entry["matched_query"] = item.query or item.title
                entry["feed_url"] = spec["url"]
                all_items.append(entry)
        except Exception as exc:
            errors.append(f"{spec['source_name']}: {exc}")

    filtered: List[Dict] = []
    seen_urls = set()
    seen_titles = set()
    for entry in all_items:
        published_at = entry.get("published_at")
        if not published_at or published_at < cutoff:
            continue
        text = " ".join([entry.get("title", ""), entry.get("summary", ""), entry.get("source_name", "")])
        if exclude_keywords and _contains_any(text, exclude_keywords):
            continue
        score = _relevance_score(text, keywords)
        if keywords and score <= 0:
            continue
        url = (entry.get("url") or "").strip()
        title_key = _normalize_key(entry.get("title", ""))
        url_key = _normalize_key(url)
        if url_key and url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if url_key:
            seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        entry["relevance_score"] = score
        filtered.append(entry)

    source_priority = {"official": 0, "media": 1, "community": 2}
    filtered.sort(
        key=lambda item_data: (
            -(item_data["published_at"].timestamp() if item_data.get("published_at") else 0),
            source_priority.get(str(item_data.get("source_type", "media")), 9),
            -int(item_data.get("relevance_score", 0)),
        )
    )
    filtered = filtered[: max(1, int(item.max_items))]

    for entry in filtered:
        published_at = entry.get("published_at")
        if published_at:
            entry["time_display"] = published_at.astimezone().strftime("%m-%d %H:%M")
        else:
            entry["time_display"] = ""

    return {
        "items": filtered,
        "errors": errors,
        "count": len(filtered),
    }
