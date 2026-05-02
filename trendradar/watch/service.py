# coding=utf-8
"""关注项监控主服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .bilibili_up import collect_bilibili_up_content
from .changedetection import ChangedetectionClient
from .detectors import detect_feed_update, detect_generic_change, detect_price
from .fetcher import extract_domain, fetch_page
from .github_feed import collect_github_feed, collect_github_projects
from .models import WatchItem
from .resolver import search_candidates
from .state import WatchStateStore
from .topic_news import collect_topic_news


class WatchService:
    def __init__(self, config: Dict[str, Any], proxy_url: Optional[str] = None):
        self.watch_config = config.get("WATCH", {})
        self.proxy_url = proxy_url
        self.timeout = int(self.watch_config.get("FETCH_TIMEOUT", 15))
        self.user_agent = self.watch_config.get("USER_AGENT", "TrendRadar Watch/1.0")
        self.store = WatchStateStore(self.watch_config.get("STATE_FILE", "output/watch_state.json"))
        self.state = self.store.load()
        self.changedetection_config = self.watch_config.get("CHANGEDETECTION", {})

    def _load_items(self) -> List[WatchItem]:
        items: List[WatchItem] = []
        for raw in self.watch_config.get("ITEMS", []):
            watch_id = str(raw.get("id") or raw.get("title") or "").strip()
            title = str(raw.get("title") or watch_id).strip()
            if not watch_id or not title:
                continue
            items.append(
                WatchItem(
                    id=watch_id,
                    title=title,
                    watch_type=str(raw.get("type", "generic_page_change")).strip(),
                    query=str(raw.get("query", raw.get("title", watch_id))).strip(),
                    enabled=bool(raw.get("enabled", True)),
                    backend=str(raw.get("backend", "direct")).strip(),
                    mode=str(raw.get("mode", "manual")).strip(),
                    push_policy=str(raw.get("push_policy", "silent")).strip(),
                    time_window_hours=int(raw.get("time_window_hours", 24) or 24),
                    max_items=int(raw.get("max_items", 10) or 10),
                    source_policy=str(raw.get("source_policy", "official_media_community")).strip(),
                    source_urls=list(raw.get("source_urls", []) or []),
                    resolved_sources=list(raw.get("resolved_sources", []) or []),
                    source_hints=list(raw.get("source_hints", []) or []),
                    selectors=dict(raw.get("selectors", {}) or {}),
                    keywords=list(raw.get("keywords", []) or []),
                    headers=dict(raw.get("headers", {}) or {}),
                    cookies=dict(raw.get("cookies", {}) or {}),
                    backend_options=dict(raw.get("backend_options", {}) or {}),
                )
            )
        return items

    def _discover_candidates(self, item: WatchItem) -> List[Dict[str, str]]:
        query = item.title
        if item.keywords:
            query = " ".join([item.title, *item.keywords])
        return search_candidates(
            query=query,
            max_candidates=int(self.watch_config.get("MAX_CANDIDATES", 3)),
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
        )

    def _resolve_sources(self, item: WatchItem, watch_state: Dict[str, Any]) -> List[str]:
        sources = item.resolved_sources or item.source_urls
        if sources:
            return sources

        if not self.watch_config.get("AUTO_DISCOVERY_ENABLED", True):
            return []

        candidates = self._discover_candidates(item)
        watch_state["candidates"] = candidates
        if candidates and self.watch_config.get("AUTO_ACTIVATE_RESOLVED", False):
            return [candidates[0]["url"]]
        return []

    def _build_pending_result(
        self,
        item: WatchItem,
        candidates: List[Dict[str, str]],
        source_name: str = "pending",
        prefix: str = "待确认监控来源",
    ) -> Dict[str, Any]:
        message = prefix
        if candidates:
            top = candidates[0]
            message = f"{prefix}：{top.get('title', '')} {top.get('url', '')}".strip()
        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": item.watch_type,
            "status": "pending_confirm",
            "message": message,
            "url": candidates[0]["url"] if candidates else "",
            "changed": False,
            "should_push": True,
            "source_name": source_name,
            "time_display": datetime.now().strftime("%H:%M"),
        }

    def _detect(self, item: WatchItem, page: Dict[str, str], last_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if item.watch_type == "price":
            return detect_price(page, last_snapshot)
        if item.watch_type == "feed_update":
            return detect_feed_update(page, last_snapshot)
        return detect_generic_change(page, last_snapshot)

    def _get_changedetection_client(self) -> ChangedetectionClient:
        return ChangedetectionClient(
            base_url=self.changedetection_config.get("BASE_URL", ""),
            api_key=self.changedetection_config.get("API_KEY", ""),
            timeout=int(self.changedetection_config.get("TIMEOUT", 20)),
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
        )

    def _build_changedetection_headers(self, item: WatchItem) -> Dict[str, str]:
        headers = dict(item.headers)
        if item.cookies and "Cookie" not in headers:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in item.cookies.items())
        return headers

    def _run_changedetection_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_changedetection_client()
        sources = self._resolve_sources(item, watch_state)
        if not sources:
            return self._build_pending_result(
                item,
                watch_state.get("candidates", []),
                source_name="changedetection",
                prefix="待确认 changedetection 监控来源",
            )

        url = sources[0]
        options = item.backend_options
        previous_last_checked = str(watch_state.get("remote_last_checked", "") or "")

        watch_info = client.ensure_watch(
            watch_uuid=str(watch_state.get("remote_uuid", "") or ""),
            title=item.title,
            url=url,
            headers=self._build_changedetection_headers(item),
            fetch_backend=options.get("fetch_backend", "html_requests"),
            processor=options.get("processor", "text_json_diff"),
            paused=bool(options.get("paused", False)),
            browser_steps=options.get("browser_steps", ""),
        )

        watch_uuid = str(
            watch_info.get("uuid")
            or watch_info.get("watch_uuid")
            or watch_info.get("id")
            or watch_state.get("remote_uuid", "")
        )
        if not watch_uuid:
            raise ValueError("changedetection 未返回 watch uuid")

        watch_state["remote_uuid"] = watch_uuid

        if options.get("trigger_recheck", False):
            client.trigger_recheck_all()
            watch_info = client.maybe_wait_for_recheck(
                watch_uuid=watch_uuid,
                previous_last_checked=previous_last_checked,
                attempts=int(options.get("wait_attempts", 6)),
                interval_seconds=int(options.get("wait_interval_seconds", 5)),
            )
        else:
            watch_info = client.get_watch(watch_uuid)

        last_checked = str(watch_info.get("last_checked", "") or "")
        last_changed = str(watch_info.get("last_changed", "") or "")
        last_error = str(watch_info.get("last_error", "") or watch_info.get("error", "") or "")
        last_seen_changed = str(watch_state.get("remote_last_changed", "") or "")

        if last_error:
            watch_state["last_error"] = last_error
            return {
                "watch_id": item.id,
                "title": item.title,
                "watch_type": item.watch_type,
                "status": "error",
                "message": f"changedetection 检查失败：{last_error}",
                "url": url,
                "changed": False,
                "should_push": True,
                "source_name": "changedetection",
                "time_display": datetime.now().strftime("%H:%M"),
            }

        summary = ""
        try:
            history = client.get_history(watch_uuid)
            entries = history.get("history") or history.get("entries") or []
            if entries:
                latest_entry = entries[0]
                summary = str(
                    latest_entry.get("title")
                    or latest_entry.get("preview")
                    or latest_entry.get("snapshot")
                    or latest_entry.get("text")
                    or ""
                ).strip()
        except Exception:
            summary = ""

        changed = bool(last_changed and last_changed != last_seen_changed)
        if not last_seen_changed and last_changed:
            changed = True

        if changed:
            message = "检测到页面变化"
            if summary:
                message = f"检测到页面变化：{summary[:120]}"
        else:
            message = "没有检测到新变化"
            if last_checked:
                message = f"没有检测到新变化（最近检查 {last_checked}）"

        watch_state["remote_last_checked"] = last_checked
        if last_changed:
            watch_state["remote_last_changed"] = last_changed
        watch_state["last_snapshot"] = {
            "backend": "changedetection",
            "last_checked": last_checked,
            "last_changed": last_changed,
            "summary": summary[:1000],
        }

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": item.watch_type,
            "status": "ok",
            "message": message,
            "url": url,
            "changed": changed,
            "should_push": changed or item.push_policy == "report_no_change",
            "source_name": "changedetection",
            "time_display": datetime.now().strftime("%H:%M"),
        }

    def _run_topic_news_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        aggregation = collect_topic_news(
            item,
            timeout=self.timeout,
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
        )
        items = aggregation["items"]
        watch_state["last_snapshot"] = {
            "mode": "topic_news",
            "count": aggregation["count"],
            "items": [
                {
                    "title": entry["title"],
                    "url": entry["url"],
                    "source_name": entry["source_name"],
                    "published_at": entry["published_at"].isoformat() if entry.get("published_at") else "",
                }
                for entry in items
            ],
        }
        if items:
            watch_state["last_change_at"] = datetime.now().isoformat()

        if items:
            message = f"近 {item.time_window_hours} 小时找到 {len(items)} 条最新消息"
        else:
            message = f"近 {item.time_window_hours} 小时没有找到最新消息"

        if aggregation["errors"]:
            watch_state["last_error"] = "; ".join(aggregation["errors"][:5])

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": "topic_news",
            "status": "ok",
            "message": message,
            "url": items[0]["url"] if items else "",
            "changed": bool(items),
            "should_push": bool(items),
            "source_name": "topic_news",
            "time_display": datetime.now().strftime("%H:%M"),
            "items": items,
            "time_window_hours": item.time_window_hours,
            "errors": aggregation["errors"],
        }

    def _run_github_feed_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        aggregation = collect_github_feed(
            item,
            timeout=self.timeout,
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
        )
        items = aggregation["items"]
        watch_state["last_snapshot"] = {
            "mode": "github_feed",
            "repo": aggregation.get("repo", ""),
            "count": aggregation["count"],
            "items": [
                {
                    "title": entry["title"],
                    "url": entry["url"],
                    "published_at": entry["published_at"].isoformat() if entry.get("published_at") else "",
                }
                for entry in items
            ],
        }
        if items:
            watch_state["last_change_at"] = datetime.now().isoformat()
        if aggregation["errors"]:
            watch_state["last_error"] = "; ".join(aggregation["errors"][:5])

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": "github_feed",
            "status": "ok",
            "message": f"近 {item.time_window_hours} 小时找到 {len(items)} 条 GitHub 更新" if items else f"近 {item.time_window_hours} 小时没有 GitHub 更新",
            "url": items[0]["url"] if items else "",
            "changed": bool(items),
            "should_push": bool(items),
            "source_name": "github_feed",
            "time_display": datetime.now().strftime("%H:%M"),
            "items": items,
            "time_window_hours": item.time_window_hours,
            "errors": aggregation["errors"],
        }

    def _run_github_projects_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        aggregation = collect_github_projects(
            item,
            timeout=self.timeout,
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
        )
        items = aggregation["items"]
        watch_state["last_snapshot"] = {
            "mode": "github_projects",
            "category": aggregation.get("category", ""),
            "count": aggregation["count"],
            "items": [
                {
                    "title": entry["title"],
                    "url": entry["url"],
                    "published_at": entry["published_at"].isoformat() if entry.get("published_at") else "",
                }
                for entry in items
            ],
        }
        if items:
            watch_state["last_change_at"] = datetime.now().isoformat()

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": "github_projects",
            "status": "ok",
            "message": f"找到 {len(items)} 个 GitHub 项目" if items else "没有找到 GitHub 项目",
            "url": items[0]["url"] if items else "",
            "changed": bool(items),
            "should_push": bool(items),
            "source_name": "github_projects",
            "time_display": datetime.now().strftime("%H:%M"),
            "items": items,
            "errors": aggregation["errors"],
        }

    def _run_bilibili_up_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        """B站UP主监控：抓取最新视频文案。"""
        search_query = item.query or item.title
        title_filter = item.backend_options.get("title_filter", "")
        uid = item.backend_options.get("uid")
        max_items = item.max_items

        aggregation = collect_bilibili_up_content(
            search_query=search_query,
            title_filter=title_filter or None,
            max_items=max_items,
            timeout=self.timeout,
            uid=int(uid) if uid else None,
        )
        raw_items = aggregation["items"]
        errors = aggregation["errors"]

        # 检查是否有新内容（与上次对比 bv_id）
        last_bv_ids = watch_state.get("last_bv_ids", [])
        current_bv_ids = [it["bv_id"] for it in raw_items]
        changed = current_bv_ids != last_bv_ids and bool(raw_items)

        if changed:
            watch_state["last_bv_ids"] = current_bv_ids
            watch_state["last_change_at"] = datetime.now().isoformat()

        # 将 sections 展平为 formatter 可用的 items 格式
        flat_items = []
        for raw in raw_items:
            video_url = raw.get("video_url", "")
            wx_url = raw.get("wx_url", "")
            for sec in raw.get("sections", []):
                flat_items.append({
                    "title": f"{sec['heading']}",
                    "url": sec.get("links", [wx_url or video_url])[0] if sec.get("links") else (wx_url or video_url),
                    "source_name": "bilibili_up",
                    "time_display": raw.get("upload_date", ""),
                })

        watch_state["last_snapshot"] = {
            "mode": "bilibili_up",
            "count": len(raw_items),
            "section_count": len(flat_items),
            "items": [
                {
                    "title": it["title"],
                    "bv_id": it["bv_id"],
                    "section_count": it.get("section_count", 0),
                }
                for it in raw_items
            ],
        }

        message = f"找到 {len(raw_items)} 个视频、{len(flat_items)} 条新闻" if raw_items else "没有找到新视频"
        if errors:
            error_detail = errors[0] if len(errors) == 1 else "; ".join(errors)
            message += f"（{error_detail}）"

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": "bilibili_up",
            "status": "ok",
            "message": message,
            "url": raw_items[0]["video_url"] if raw_items else "",
            "changed": changed,
            "should_push": changed or item.push_policy == "report_no_change",
            "source_name": "bilibili_up",
            "time_display": datetime.now().strftime("%H:%M"),
            "items": flat_items,
            "errors": errors,
        }

    def _run_direct_watch(self, item: WatchItem, watch_state: Dict[str, Any]) -> Dict[str, Any]:
        sources = self._resolve_sources(item, watch_state)
        if not sources:
            return self._build_pending_result(item, watch_state.get("candidates", []))

        url = sources[0]
        page = fetch_page(
            url=url,
            timeout=self.timeout,
            user_agent=self.user_agent,
            proxy_url=self.proxy_url,
            extra_headers=item.headers,
            cookies=item.cookies,
        )
        final_url = page.get("url", "")
        if "passport.weibo.com/visitor" in final_url or "visitor.passport.weibo.cn/visitor" in final_url:
            raise ValueError("需要登录态，当前 Cookie 无效或缺失")

        detection = self._detect(item, page, watch_state.get("last_snapshot"))
        watch_state["last_snapshot"] = detection["snapshot"]
        watch_state["last_url"] = page.get("url", url)
        if detection["changed"]:
            watch_state["last_change_at"] = datetime.now().isoformat()

        return {
            "watch_id": item.id,
            "title": item.title,
            "watch_type": item.watch_type,
            "status": "ok",
            "message": detection["message"],
            "url": page.get("url", url),
            "changed": detection["changed"],
            "should_push": detection["changed"] or item.push_policy == "report_no_change",
            "source_name": extract_domain(page.get("url", url)) or item.watch_type,
            "time_display": datetime.now().strftime("%H:%M"),
        }

    def run(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        watches = self.state.setdefault("watches", {})

        for item in self._load_items():
            if not item.enabled:
                continue

            watch_state = watches.setdefault(item.id, {})
            watch_state["title"] = item.title
            watch_state["watch_type"] = item.watch_type
            watch_state["updated_at"] = datetime.now().isoformat()

            try:
                if item.mode == "topic_news" or item.watch_type == "topic_news":
                    result = self._run_topic_news_watch(item, watch_state)
                elif item.mode == "github_feed" or item.watch_type == "github_feed":
                    result = self._run_github_feed_watch(item, watch_state)
                elif item.mode == "github_projects" or item.watch_type == "github_projects":
                    result = self._run_github_projects_watch(item, watch_state)
                elif item.mode == "bilibili_up" or item.watch_type == "bilibili_up":
                    result = self._run_bilibili_up_watch(item, watch_state)
                elif item.backend == "changedetection":
                    result = self._run_changedetection_watch(item, watch_state)
                else:
                    result = self._run_direct_watch(item, watch_state)
                results.append(result)
            except Exception as exc:
                watch_state["last_error"] = str(exc)
                results.append(
                    {
                        "watch_id": item.id,
                        "title": item.title,
                        "watch_type": item.watch_type,
                        "status": "error",
                        "message": f"检查失败：{exc}",
                        "url": "",
                        "changed": False,
                        "should_push": True,
                        "source_name": "error",
                        "time_display": datetime.now().strftime("%H:%M"),
                    }
                )

        self.store.save(self.state)
        return results
