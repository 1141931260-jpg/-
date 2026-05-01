# coding=utf-8
"""changedetection.io API 客户端。"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests


class ChangedetectionClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: int = 20,
        user_agent: str = "TrendRadar Watch/1.0",
        proxy_url: Optional[str] = None,
    ):
        if not base_url:
            raise ValueError("未配置 changedetection.io base_url")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )
        if api_key:
            self.session.headers["x-api-key"] = api_key
        if proxy_url:
            self.session.proxies.update({"http": proxy_url, "https": proxy_url})

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        if response.content:
            return response.json()
        return None

    def create_watch(
        self,
        *,
        title: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        fetch_backend: str = "html_requests",
        processor: str = "text_json_diff",
        paused: bool = False,
        browser_steps: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "url": url,
            "headers": headers or {},
            "fetch_backend": fetch_backend,
            "processor": processor,
            "paused": paused,
        }
        if browser_steps:
            payload["browser_steps"] = browser_steps
        return self._request("POST", "/api/v1/watch", json=payload)

    def update_watch(self, watch_uuid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/api/v1/watch/{watch_uuid}", json=payload)

    def get_watch(self, watch_uuid: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/watch/{watch_uuid}")

    def list_watches(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/watch")

    def get_history(self, watch_uuid: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/watch/{watch_uuid}/history")

    def trigger_recheck_all(self) -> Any:
        return self._request("GET", "/api/v1/watch?recheck_all=1")

    def ensure_watch(
        self,
        *,
        watch_uuid: str = "",
        title: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        fetch_backend: str = "html_requests",
        processor: str = "text_json_diff",
        paused: bool = False,
        browser_steps: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "url": url,
            "headers": headers or {},
            "fetch_backend": fetch_backend,
            "processor": processor,
            "paused": paused,
        }
        if browser_steps:
            payload["browser_steps"] = browser_steps

        if watch_uuid:
            self.update_watch(watch_uuid, payload)
            return self.get_watch(watch_uuid)

        created = self.create_watch(
            title=title,
            url=url,
            headers=headers,
            fetch_backend=fetch_backend,
            processor=processor,
            paused=paused,
            browser_steps=browser_steps,
        )
        return created

    def maybe_wait_for_recheck(
        self,
        watch_uuid: str,
        previous_last_checked: str = "",
        attempts: int = 6,
        interval_seconds: int = 5,
    ) -> Dict[str, Any]:
        latest = self.get_watch(watch_uuid)
        for _ in range(max(attempts, 1)):
            latest_checked = str(latest.get("last_checked", "") or "")
            if latest_checked and latest_checked != previous_last_checked:
                return latest
            time.sleep(interval_seconds)
            latest = self.get_watch(watch_uuid)
        return latest
