# coding=utf-8
"""关注项监控数据模型。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WatchItem:
    id: str
    title: str
    watch_type: str
    query: str = ""
    enabled: bool = True
    backend: str = "direct"
    mode: str = "manual"
    push_policy: str = "silent"
    time_window_hours: int = 24
    max_items: int = 10
    source_policy: str = "official_media_community"
    source_urls: List[str] = field(default_factory=list)
    resolved_sources: List[str] = field(default_factory=list)
    source_hints: List[str] = field(default_factory=list)
    selectors: Dict[str, str] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    backend_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchResult:
    watch_id: str
    title: str
    watch_type: str
    status: str
    message: str
    url: str = ""
    changed: bool = False
    should_push: bool = False
    snapshot: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Dict[str, str]] = field(default_factory=list)
    error: str = ""
