# coding=utf-8
"""
B站UP主监控模块

通过 bili-cli + yt-dlp + Jina Reader 抓取指定UP主的最新视频文案。
属于 Agent Reach 技能与 GEINEWS Watch 系统的集成。

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
import time
from typing import Any, Dict, List, Optional

import requests


# ──────────────────────────────────────────────
# B站视频搜索
# ──────────────────────────────────────────────

def search_uploader_videos(
    query: str,
    count: int = 5,
    timeout: int = 30,
    retries: int = 2,
    uid: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    搜索B站视频。优先用 UID 直接获取视频列表，回退到搜索。

    Args:
        query: 搜索关键词（如 "橘鸦Juya AI早报"）
        count: 返回结果数量
        timeout: 超时时间
        retries: 重试次数
        uid: UP主 UID，如果提供则直接获取视频列表（更可靠）

    Returns:
        [{"bv": "BVxxx", "title": "...", "uploader": "..."}]
    """
    # 方案1: 通过 UID 直接获取 UP 主视频列表（最可靠，按时间排序）
    if uid:
        for attempt in range(retries + 1):
            try:
                videos = _get_user_videos(uid, count)
                if videos:
                    return videos
            except Exception:
                if attempt < retries:
                    time.sleep(2)
                    continue
                break

    # 方案2: bilibili-api-python 搜索
    for attempt in range(retries + 1):
        try:
            videos = _search_bilibili_api(query, count, timeout)
            if videos:
                return videos
        except Exception:
            if attempt < retries:
                time.sleep(2)
                continue
            break

    # 方案3: bili-cli 子进程（回退）
    last_error = ""
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ["bili", "search", query, "--type", "video", "-n", str(count), "--json"],
                capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            output = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()

            if not output and stderr:
                last_error = f"bili-cli stderr: {stderr[:200]}"
                if attempt < retries:
                    time.sleep(2)
                    continue
            elif not output and result.returncode != 0:
                last_error = f"bili-cli 退出码 {result.returncode}"
                if attempt < retries:
                    time.sleep(2)
                    continue

            if output:
                try:
                    data = json.loads(output)
                    videos_list: List[Dict[str, str]] = []
                    items = data if isinstance(data, list) else data.get("data", [])
                    for entry in items:
                        videos_list.append({
                            "bv": entry.get("bvid") or entry.get("id", ""),
                            "title": entry.get("title", ""),
                            "uploader": entry.get("author") or entry.get("uploader", ""),
                        })
                    if videos_list:
                        return videos_list
                except json.JSONDecodeError:
                    parsed = _parse_bili_yaml(output)
                    if parsed:
                        return parsed
                    last_error = "bili-cli 输出解析失败"
            else:
                last_error = "bili-cli 无输出"

        except FileNotFoundError:
            last_error = "bili-cli 未安装"
            break
        except subprocess.TimeoutExpired:
            last_error = f"bili-cli 搜索超时 ({timeout}s)"
            if attempt < retries:
                time.sleep(2)
                continue

    raise RuntimeError(f"搜索失败: {last_error}")


def _get_user_videos(uid: int, count: int = 5) -> List[Dict[str, str]]:
    """通过 UID 直接获取 UP 主最新视频列表（最可靠）。"""
    import asyncio
    from bilibili_api import user as bili_user

    async def _do_get():
        u = bili_user.User(uid=uid)
        result = await u.get_videos(pn=1, ps=count)
        return result.get("list", {}).get("vlist", []) or []

    vlist = asyncio.run(_do_get())
    videos: List[Dict[str, str]] = []
    for v in vlist[:count]:
        bv = v.get("bvid", "")
        if not bv:
            continue
        videos.append({
            "bv": bv,
            "title": v.get("title", ""),
            "uploader": v.get("author", ""),
        })
    return videos


def _search_bilibili_api(query: str, count: int = 5, timeout: int = 30) -> List[Dict[str, str]]:
    """通过 bilibili-api-python 搜索视频（自带 wbi 签名，不会被 412）。"""
    import asyncio
    from bilibili_api import search as bili_search

    async def _do_search():
        result = await bili_search.search_by_type(
            query,
            search_type=bili_search.SearchObjectType.VIDEO,
            page=1,
            order_type=bili_search.OrderVideo.PUBDATE,  # 按发布时间排序，优先取最新
        )
        return result.get("result", []) or []

    entries = asyncio.run(_do_search())
    videos: List[Dict[str, str]] = []
    for entry in entries[:count]:
        bv = entry.get("bvid", "")
        if not bv:
            continue
        title = re.sub(r"<[^>]+>", "", entry.get("title", ""))
        videos.append({
            "bv": bv,
            "title": title,
            "uploader": entry.get("author", ""),
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

def get_video_info(bv_id: str, timeout: int = 30, retries: int = 2) -> Dict[str, Any]:
    """
    获取视频元数据。优先用 bilibili-api-python，回退到 yt-dlp。

    Returns:
        {"title": "...", "description": "...", "upload_date": "...", "uploader": "..."}
    """
    # 方案1: bilibili-api-python（可靠，不会被 412）
    for attempt in range(retries + 1):
        try:
            info = _get_video_info_api(bv_id)
            if info:
                return info
        except Exception:
            if attempt < retries:
                time.sleep(2)
                continue
            break

    # 方案2: yt-dlp 子进程（回退）
    url = f"https://www.bilibili.com/video/{bv_id}"
    last_error = ""
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                ["yt-dlp", "--dump-json", "--skip-download", url],
                capture_output=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
            if not result.stdout.strip():
                stderr = (result.stderr or "").strip()
                last_error = f"yt-dlp 无输出, stderr: {stderr[:200]}"
                if attempt < retries:
                    time.sleep(2)
                    continue
                raise RuntimeError(last_error)
            data = json.loads(result.stdout)
            return {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "upload_date": data.get("upload_date", ""),
                "uploader": data.get("uploader", ""),
                "webpage_url": data.get("webpage_url", url),
            }
        except json.JSONDecodeError as e:
            last_error = f"yt-dlp JSON 解析失败: {e}"
            if attempt < retries:
                time.sleep(2)
                continue
        except subprocess.TimeoutExpired:
            last_error = f"yt-dlp 超时 ({timeout}s)"
            if attempt < retries:
                time.sleep(2)
                continue
        except RuntimeError:
            raise
        except Exception as e:
            last_error = f"yt-dlp 异常: {e}"
            if attempt < retries:
                time.sleep(2)
                continue

    raise RuntimeError(f"yt-dlp 获取视频信息失败: {last_error}")


def _get_video_info_api(bv_id: str) -> Optional[Dict[str, Any]]:
    """通过 bilibili-api-python 获取视频元数据。"""
    import asyncio
    from bilibili_api import video as bili_video
    from datetime import datetime

    async def _do_get():
        v = bili_video.Video(bvid=bv_id)
        return await v.get_info()

    info = asyncio.run(_do_get())
    if not info:
        return None

    # pubdate 是时间戳，转为 YYYYMMDD 格式
    pubdate = info.get("pubdate", 0)
    upload_date = datetime.fromtimestamp(pubdate).strftime("%Y%m%d") if pubdate else ""

    return {
        "title": info.get("title", ""),
        "description": info.get("desc", ""),
        "upload_date": upload_date,
        "uploader": info.get("owner", {}).get("name", ""),
        "webpage_url": f"https://www.bilibili.com/video/{bv_id}",
    }


def extract_wechat_url(description: str) -> Optional[str]:
    """从视频描述中提取微信公众号文章链接。"""
    match = re.search(r'https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+', description)
    return match.group(0) if match else None


# ──────────────────────────────────────────────
# 评论区内容
# ──────────────────────────────────────────────

def get_pinned_comment(bv_id: str, uid: Optional[int] = None, retries: int = 2) -> Optional[str]:
    """
    获取视频评论区的UP主回复内容。

    某些UP主（如"一觉醒来发生啥"）会把视频内容总结放在评论区回复中，
    且由于B站单条评论798字符限制，UP主会通过子评论"续楼"发布剩余内容。
    本函数会自动扫描置顶和前几页普通评论，优先返回可解析为编号新闻列表的
    UP主评论，并拼接所有UP主子评论为完整文本。

    Args:
        bv_id: 视频 BV 号
        uid: UP主 UID，用于匹配UP主的回复
        retries: 重试次数

    Returns:
        UP主回复文本（含续楼），无则返回 None
    """
    import asyncio
    from bilibili_api import video as bili_video

    async def _do_get():
        v = bili_video.Video(bvid=bv_id)
        info = await v.get_info()
        aid = info.get("aid")
        if not aid:
            return None
        return aid

    # 获取 AID
    aid = None
    for attempt in range(retries + 1):
        try:
            aid = asyncio.run(_do_get())
            if aid:
                break
        except Exception:
            if attempt < retries:
                time.sleep(2)
                continue

    if not aid:
        return None

    # 使用HTTP API获取评论（更可靠）
    url = "https://api.bilibili.com/x/v2/reply"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{bv_id}",
    }

    def _numbered_item_count(text: str) -> int:
        return sum(1 for line in text.splitlines() if re.match(r'^\s*\d{1,3}[、.．]\s*.+', line))

    def _join_up_sub_comments(main_msg: str, main_rpid: Any) -> str:
        if not main_msg or not main_rpid:
            return main_msg

        sub_url = "https://api.bilibili.com/x/v2/reply/reply"
        up_subs = []
        for pn in range(1, 10):
            params = {"oid": aid, "type": 1, "root": main_rpid, "pn": pn, "ps": 20}
            try:
                resp = requests.get(sub_url, params=params, headers=headers, timeout=15)
                data = resp.json()
            except Exception:
                break
            if data.get("code") != 0:
                break

            replies = data.get("data", {}).get("replies") or []
            if not replies:
                break

            for sr in replies:
                sr_mid = sr.get("member", {}).get("mid", 0)
                sr_msg = sr.get("content", {}).get("message", "")
                if uid and str(sr_mid) == str(uid) and sr_msg:
                    up_subs.append(sr)
                elif not uid and sr_msg and len(sr_msg) > 50:
                    up_subs.append(sr)

        if not up_subs:
            return main_msg

        up_subs.sort(key=lambda x: x.get("rpid", 0))
        parts = [main_msg]
        for sr in up_subs:
            sub_msg = sr["content"]["message"]
            if parts and sub_msg:
                last_part = parts[-1]
                if last_part.endswith(("、", "，", "。", "；")) and sub_msg[0] == last_part[-1]:
                    sub_msg = sub_msg[1:]
                parts[-1] = last_part + sub_msg
                continue
            parts.append(sub_msg)
        return "\n".join(parts)

    fallback_text = None
    best_text = None
    best_count = 0

    for pn in range(1, 6):
        params = {"oid": aid, "type": 1, "sort": 2, "pn": pn, "ps": 20}
        reply_data = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                data = resp.json()
                if data.get("code") != 0:
                    if attempt < retries:
                        time.sleep(2)
                        continue
                    return best_text or fallback_text
                reply_data = data.get("data", {})
                break
            except Exception:
                if attempt < retries:
                    time.sleep(2)
                    continue

        if not reply_data:
            continue

        candidates = []
        if pn == 1:
            upper = reply_data.get("upper", {})
            top = upper.get("top")
            if top:
                candidates.append(top)

        candidates.extend(reply_data.get("replies") or [])
        if not candidates:
            break

        for reply in candidates:
            mid = reply.get("member", {}).get("mid", "")
            msg = reply.get("content", {}).get("message", "")
            rpid = reply.get("rpid")
            if not msg:
                continue
            if uid and str(mid) != str(uid):
                continue
            if not uid and len(msg) <= 50:
                continue

            full_text = _join_up_sub_comments(msg, rpid)
            if fallback_text is None and len(full_text) > 50:
                fallback_text = full_text

            count = _numbered_item_count(full_text)
            if count > best_count:
                best_count = count
                best_text = full_text

    if best_text:
        return best_text

    return fallback_text


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


def parse_numbered_list(text: str, bv_id: str = "") -> List[Dict[str, Any]]:
    """
    解析编号列表格式的评论内容。

    常见格式（如"一觉醒来发生啥"UP主的评论区）：
        2026年5月2日信息差，
        1、xxx
        2、xxx
        3、xxx

    Returns:
        [{"heading": "...", "summary": "", "links": [], "bv": ...}]
    """
    sections: List[Dict[str, Any]] = []
    # 匹配 "数字、" 或 "数字." 或 "数字、" 开头的行
    num_pattern = re.compile(r'^\d{1,3}[、.．]\s*(.+)')

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = num_pattern.match(line)
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
    uid: Optional[int] = None,
    use_pinned_comment: bool = False,
) -> Dict[str, Any]:
    """
    抓取指定B站UP主的最新视频文案。

    Args:
        search_query: 搜索关键词（如 "橘鸦Juya AI早报"）
        title_filter: 标题过滤关键词（如 "早报"），只保留匹配的视频
        max_items: 最多处理几个视频
        timeout: 超时时间
        uid: UP主 UID（推荐，直接获取视频列表更可靠）
        use_pinned_comment: 是否从评论区置顶获取内容（适用于"一觉醒来发生啥"等UP主）

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
        videos = search_uploader_videos(search_query, count=max_items + 3, timeout=timeout, uid=uid)
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

            # 如果开启了评论区置顶模式，优先从置顶评论获取内容
            pinned_text = ""
            if use_pinned_comment:
                try:
                    pinned_text = get_pinned_comment(bv_id, uid=uid) or ""
                except Exception:
                    pinned_text = ""

            # 解析段落：优先用评论区置顶 > 文章全文 > 视频描述时间戳
            sections = []
            if pinned_text and not _is_captcha_page(pinned_text):
                sections = parse_article_sections(pinned_text, bv_id, wx_url or "")
                # 评论区内容通常是编号列表格式，不是markdown标题
                if not sections:
                    sections = parse_numbered_list(pinned_text, bv_id)
            if not sections and article_text and not _is_captcha_page(article_text):
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
