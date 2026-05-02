# coding=utf-8
"""
B站UP主监控模块

通过 bili-cli + yt-dlp + Jina Reader 抓取指定UP主的最新视频文案。
属于 Agent Reach 技能与 TrendRadar Watch 系统的集成。

支持：
- 按UP主名称搜索最新视频
- 从视频描述中提取微信公众号文章链接
- 通过 Jina Reader 获取文章全文
- 解析文章为结构化段落
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional

import requests


# ──────────────────────────────────────────────
# B站视频搜索
# ──────────────────────────────────────────────

def search_uploader_videos(
    query: str,
    count: int = 5,
    timeout: int = 30,
) -> List[Dict[str, str]]:
    """
    通过 bili-cli 搜索视频。

    Args:
        query: 搜索关键词（如 "橘鸦Juya AI早报"）
        count: 返回结果数量

    Returns:
        [{"bv": "BVxxx", "title": "...", "uploader": "..."}]
    """
    try:
        result = subprocess.run(
            ["bili", "search", query, "--type", "video", "-n", str(count), "--json"],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "").strip()
    except FileNotFoundError:
        raise RuntimeError("bili-cli 未安装，请运行: pip install bilibili-cli")
    except subprocess.TimeoutExpired:
        raise RuntimeError("bili-cli 搜索超时")

    if not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        # 回退：尝试 YAML 格式（bili-cli 默认输出）
        return _parse_bili_yaml(output)

    videos: List[Dict[str, str]] = []
    items = data if isinstance(data, list) else data.get("data", [])
    for entry in items:
        videos.append({
            "bv": entry.get("bvid") or entry.get("id", ""),
            "title": entry.get("title", ""),
            "uploader": entry.get("author") or entry.get("uploader", ""),
        })
    return videos


def _parse_bili_yaml(output: str) -> List[Dict[str, str]]:
    """解析 bili-cli YAML 格式输出（回退方案）。"""
    videos: List[Dict[str, str]] = []
    current: Dict[str, str] = {}

    for line in output.split("\n"):
        line = line.rstrip()
        if line.startswith("- id: "):
            if current.get("bv"):
                videos.append(current)
            current = {"bv": line[6:].strip()}
        elif line.startswith("  bvid: "):
            current["bv"] = line[8:].strip()
        elif line.startswith("  title: "):
            current["title"] = line[9:].strip()
        elif line.startswith("  author: "):
            current["uploader"] = line[10:].strip()

    if current.get("bv"):
        videos.append(current)
    return videos


# ──────────────────────────────────────────────
# 视频元数据
# ──────────────────────────────────────────────

def get_video_info(bv_id: str, timeout: int = 30) -> Dict[str, Any]:
    """
    通过 yt-dlp 获取视频元数据。

    Returns:
        {"title": "...", "description": "...", "upload_date": "...", "uploader": "..."}
    """
    url = f"https://www.bilibili.com/video/{bv_id}"
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", url],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        data = json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "upload_date": data.get("upload_date", ""),
            "uploader": data.get("uploader", ""),
            "webpage_url": data.get("webpage_url", url),
        }
    except Exception as e:
        raise RuntimeError(f"yt-dlp 获取视频信息失败: {e}")


def extract_wechat_url(description: str) -> Optional[str]:
    """从视频描述中提取微信公众号文章链接。"""
    match = re.search(r'https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+', description)
    return match.group(0) if match else None


# ──────────────────────────────────────────────
# 文章获取（Agent Reach: Jina Reader）
# ──────────────────────────────────────────────

def fetch_article_jina(url: str, timeout: int = 30) -> str:
    """通过 Jina Reader 获取文章全文（Agent Reach 零配置通道）。"""
    jina_url = f"https://r.jina.ai/{url}"
    try:
        resp = requests.get(
            jina_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        raise RuntimeError(f"Jina Reader 获取失败: {e}")


def _is_captcha_page(text: str) -> bool:
    """检测返回内容是否为验证码/拦截页面。"""
    captcha_markers = ["环境异常", "完成验证", "captcha", "verify", "访问验证"]
    text_lower = text.lower()[:500]
    return any(marker in text_lower for marker in captcha_markers)


# ──────────────────────────────────────────────
# 文章解析
# ──────────────────────────────────────────────

def parse_article_sections(
    raw_text: str,
    bv_id: str = "",
    wx_url: str = "",
    skip_headings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    将文章原始文本解析为结构化段落。

    Returns:
        [{"heading": "...", "summary": "...", "links": [...], "bv": ..., "wx_url": ...}]
    """
    if skip_headings is None:
        skip_headings = ["早报", "概览", "要闻", "开发生态", "产品应用", "技术与洞察", "行业动态"]

    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for line in raw_text.split("\n"):
        line = line.strip()

        # 匹配 ## 标题行
        heading_match = re.match(r'^#{1,3}\s+(.+?)(?:\s*`#\d+`)?$', line)
        if heading_match:
            heading_text = heading_match.group(1).strip()
            if any(skip in heading_text for skip in skip_headings):
                continue
            if current and current.get("summary"):
                sections.append(current)
            current = {
                "heading": heading_text,
                "summary": "",
                "links": [],
                "bv": bv_id,
                "wx_url": wx_url,
            }
            continue

        if current is None:
            continue

        # 跳过图片和空行
        if not line or line.startswith("![") or line.startswith("http"):
            continue
        if line == ">":
            continue

        # 收集链接
        url_match = re.match(r'^`?(https?://[^\s`]+)`?$', line)
        if url_match:
            current["links"].append(url_match.group(1))
            continue

        # 收集正文摘要
        clean = line.lstrip("> ").strip()
        if clean and len(clean) > 10:
            if current["summary"]:
                current["summary"] += "\n"
            current["summary"] += clean

    if current and current.get("summary"):
        sections.append(current)

    return sections


def parse_description_timestamps(description: str, bv_id: str = "") -> List[Dict[str, Any]]:
    """
    从视频描述的时间戳列表中解析新闻条目。

    B站视频描述常见格式：
        00:09 OpenAI Codex 新增导入其他Agent配置功能和宠物功能
        00:29 OpenAI Codex 登录策略调整，大概率触发手机验证

    Returns:
        [{"heading": "...", "summary": "", "links": [], "bv": ...}]
    """
    sections: List[Dict[str, Any]] = []
    # 匹配 MM:SS 或 HH:MM:SS 开头的行
    ts_pattern = re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?\s+(.+)')

    for line in description.split("\n"):
        line = line.strip()
        m = ts_pattern.match(line)
        if m:
            heading = m.group(1).strip()
            if heading:
                sections.append({
                    "heading": heading,
                    "summary": "",
                    "links": [],
                    "bv": bv_id,
                    "wx_url": "",
                })

    return sections


# ──────────────────────────────────────────────
# 主入口：收集UP主最新内容
# ──────────────────────────────────────────────

def collect_bilibili_up_content(
    search_query: str,
    title_filter: Optional[str] = None,
    max_items: int = 1,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    抓取指定B站UP主的最新视频文案。

    Args:
        search_query: 搜索关键词（如 "橘鸦Juya AI早报"）
        title_filter: 标题过滤关键词（如 "早报"），只保留匹配的视频
        max_items: 最多处理几个视频
        timeout: 超时时间

    Returns:
        {
            "items": [{"title", "bv_id", "sections", "wx_url", "video_url", "upload_date"}],
            "errors": [],
        }
    """
    items: List[Dict[str, Any]] = []
    errors: List[str] = []

    # 1. 搜索视频
    try:
        videos = search_uploader_videos(search_query, count=max_items + 3, timeout=timeout)
    except RuntimeError as e:
        errors.append(str(e))
        return {"items": items, "errors": errors}

    if not videos:
        errors.append(f"未搜索到视频: {search_query}")
        return {"items": items, "errors": errors}

    # 2. 过滤
    if title_filter:
        filtered = [v for v in videos if title_filter.lower() in v["title"].lower()]
        if not filtered:
            filtered = videos[:1]  # 回退到第一个
        videos = filtered

    # 3. 逐个处理
    for video in videos[:max_items]:
        bv_id = video["bv"]
        try:
            info = get_video_info(bv_id, timeout=timeout)
            title = info["title"]
            description = info["description"]
            wx_url = extract_wechat_url(description)

            # 获取文章全文
            article_text = ""
            if wx_url:
                try:
                    article_text = fetch_article_jina(wx_url, timeout=timeout)
                except RuntimeError:
                    article_text = ""

            # 解析段落：优先用文章全文，回退到视频描述时间戳
            sections = []
            if article_text and not _is_captcha_page(article_text):
                sections = parse_article_sections(article_text, bv_id, wx_url or "")

            # 如果文章解析不到有效内容（如被 CAPTCHA 拦截），用视频描述的时间戳
            if not sections and description:
                sections = parse_description_timestamps(description, bv_id)

            # 最后兜底：用视频描述本身
            if not sections and description:
                sections = [{
                    "heading": title,
                    "summary": description[:500],
                    "links": [f"https://www.bilibili.com/video/{bv_id}"],
                    "bv": bv_id,
                    "wx_url": wx_url or "",
                }]

            items.append({
                "title": title,
                "bv_id": bv_id,
                "video_url": f"https://www.bilibili.com/video/{bv_id}",
                "wx_url": wx_url or "",
                "upload_date": info.get("upload_date", ""),
                "sections": sections,
                "section_count": len(sections),
            })
        except Exception as e:
            errors.append(f"处理 {bv_id} 失败: {e}")

    return {"items": items, "errors": errors}
