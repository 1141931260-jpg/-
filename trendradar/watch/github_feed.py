# coding=utf-8
"""GitHub 更新聚合。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests


ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
REPO_IN_TITLE_RE = re.compile(r"^(?P<repo>[^ ]+/[^ ]+)")


def _clean_text(value: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", value or ""))
    return SPACE_RE.sub(" ", text).strip()


def _shorten_cn(text: str, max_len: int = 10) -> str:
    value = (text or "").strip()
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _brief_from_text(title: str, summary: str) -> str:
    haystack = f"{title} {summary}".lower()
    rules = [
        (["trading", "trade", "quant"], "量化交易"),
        (["agent", "agents"], "智能体框架"),
        (["ai coding", "coding"], "AI编程工具"),
        (["cli", "terminal", "shell"], "命令行工具"),
        (["browser"], "浏览器工具"),
        (["dictionary", "glossary"], "术语词典"),
        (["prompt"], "提示词工具"),
        (["workflow", "automation"], "自动化工具"),
        (["api"], "API工具"),
        (["sdk"], "开发SDK"),
        (["ui", "design"], "界面设计"),
        (["finance", "defi"], "金融工具"),
        (["security"], "安全工具"),
        (["search"], "搜索工具"),
        (["chat"], "聊天工具"),
        (["warp"], "终端工具"),
        (["cable"], "线缆识别"),
    ]
    for keywords, brief in rules:
        for keyword in keywords:
            if keyword in haystack:
                return brief
    return "开源项目"


def _parse_dt(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
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


def _parse_repo(value: str) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if "github.com" not in parsed.netloc.lower():
            return None
        parts = [part for part in parsed.path.split("/") if part]
    else:
        parts = [part for part in raw.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def _fetch_text(url: str, timeout: int, user_agent: str, proxy_url: Optional[str]) -> str:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
    response.raise_for_status()
    return response.text


def _parse_atom_entries(xml_text: str, source_name: str, source_type: str) -> List[Dict]:
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
        summary = _clean_text(
            entry.findtext("atom:summary", "", ATOM_NS) or entry.findtext("atom:content", "", ATOM_NS)
        )
        published_at = _parse_dt(
            entry.findtext("atom:updated", "", ATOM_NS) or entry.findtext("atom:published", "", ATOM_NS)
        )
        items.append(
            {
                "title": title,
                "summary": (summary or title)[:280],
                "url": link,
                "source_name": source_name,
                "source_type": source_type,
                "published_at": published_at,
            }
        )
    return items


def _fetch_json(url: str, timeout: int, user_agent: str, proxy_url: Optional[str]) -> Dict:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/vnd.github+json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}
    response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
    response.raise_for_status()
    return json.loads(response.text)


def _parse_trending_rss(xml_text: str) -> List[Dict]:
    root = ET.fromstring(xml_text)
    items: List[Dict] = []
    for node in root.findall(".//item"):
        raw_title = _clean_text(node.findtext("title", ""))
        title = raw_title
        link = (node.findtext("link", "") or "").strip()
        pub_date = _parse_dt(node.findtext("pubDate", ""))
        description = _clean_text(node.findtext("description", ""))
        repo_name = ""
        match = REPO_IN_TITLE_RE.match(raw_title)
        if match:
            repo_name = match.group("repo")
        brief = _shorten_cn(_brief_from_text(raw_title, description))
        if repo_name:
            title = f"{repo_name}｜{brief}"
        items.append(
            {
                "title": title,
                "summary": description[:280] or title,
                "brief": brief,
                "url": link,
                "source_name": "GitHub Trending",
                "source_type": "community",
                "published_at": pub_date,
                "repo_name": repo_name,
            }
        )
    return items


def collect_github_feed(item, timeout: int, user_agent: str, proxy_url: Optional[str] = None) -> Dict[str, object]:
    repo = None
    repo = _parse_repo(item.backend_options.get("repo", ""))
    if not repo:
        for source in list(item.source_urls or []) + list(item.source_hints or []):
            repo = _parse_repo(source)
            if repo:
                break
    if not repo:
        raise ValueError("未配置有效的 GitHub repo")

    branch = str(item.backend_options.get("branch", "main") or "main").strip()
    include_releases = bool(item.backend_options.get("include_releases", True))
    include_commits = bool(item.backend_options.get("include_commits", True))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(item.time_window_hours)))

    specs = []
    if include_releases:
        specs.append((f"https://github.com/{repo}/releases.atom", f"GitHub {repo}", "community"))
    if include_commits:
        specs.append((f"https://github.com/{repo}/commits/{branch}.atom", f"GitHub {repo}", "community"))

    all_items: List[Dict] = []
    errors: List[str] = []
    for url, source_name, source_type in specs:
        try:
            text = _fetch_text(url, timeout=timeout, user_agent=user_agent, proxy_url=proxy_url)
            all_items.extend(_parse_atom_entries(text, source_name, source_type))
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    seen_urls = set()
    filtered: List[Dict] = []
    for entry in all_items:
        published_at = entry.get("published_at")
        if not published_at or published_at < cutoff:
            continue
        url = (entry.get("url") or "").strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)
        entry["time_display"] = published_at.astimezone().strftime("%m-%d %H:%M")
        filtered.append(entry)

    filtered.sort(key=lambda x: -(x["published_at"].timestamp() if x.get("published_at") else 0))
    filtered = filtered[: max(1, int(item.max_items))]
    return {"items": filtered, "errors": errors, "count": len(filtered), "repo": repo}


def collect_github_projects(item, timeout: int, user_agent: str, proxy_url: Optional[str] = None) -> Dict[str, object]:
    category = str(item.backend_options.get("category", "trending") or "trending").strip().lower()
    max_items = max(1, int(item.max_items))

    if category == "trending":
        url = str(item.backend_options.get("feed_url", "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"))
        text = _fetch_text(url, timeout=timeout, user_agent=user_agent, proxy_url=proxy_url)
        items = _parse_trending_rss(text)[:max_items]
        for entry in items:
            if entry.get("published_at"):
                entry["time_display"] = entry["published_at"].astimezone().strftime("%m-%d %H:%M")
            else:
                entry["time_display"] = ""
        return {"items": items, "errors": [], "count": len(items), "category": category}

    if category == "rising":
        since = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(item.time_window_hours)))).date().isoformat()
        query = f"created:>{since}"
        url = (
            "https://api.github.com/search/repositories"
            f"?q={query}&sort=stars&order=desc&per_page={max_items}"
        )
        payload = _fetch_json(url, timeout=timeout, user_agent=user_agent, proxy_url=proxy_url)
        items: List[Dict] = []
        for repo in payload.get("items", [])[:max_items]:
            created_at = _parse_dt(repo.get("created_at", ""))
            base_name = repo.get("full_name", "")
            summary = _clean_text(repo.get("description", "") or "")[:280] or base_name
            brief = _shorten_cn(_brief_from_text(repo.get("full_name", ""), summary))
            title = f"{base_name} | ★ {repo.get('stargazers_count', 0)}｜{brief}"
            items.append(
                {
                    "title": title,
                    "summary": summary,
                    "brief": brief,
                    "url": repo.get("html_url", ""),
                    "source_name": "GitHub Search",
                    "source_type": "community",
                    "published_at": created_at,
                    "time_display": created_at.astimezone().strftime("%m-%d %H:%M") if created_at else "",
                }
            )
        return {"items": items, "errors": [], "count": len(items), "category": category}

    raise ValueError(f"不支持的 GitHub 项目类别: {category}")
