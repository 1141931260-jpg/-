# coding=utf-8
"""
橘鸦Juya AI 早报抓取 & 企业微信推送

流程：
1. 通过 bili-cli 搜索橘鸦Juya最新AI早报视频
2. 从视频描述中提取微信公众号文章链接
3. 通过 Jina Reader 获取文章全文
4. 格式化后推送到企业微信 Webhook

用法：
    python scripts/juya_briefing.py
    python scripts/juya_briefing.py --webhook "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
    python scripts/juya_briefing.py --dry-run   # 只打印不推送
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests


# ──────────────────────────────────────────────
# 1. B站搜索：获取最新视频信息
# ──────────────────────────────────────────────

def search_latest_juya_video(query: str = "橘鸦Juya AI早报", count: int = 3) -> Optional[Dict]:
    """
    通过 bili-cli 搜索橘鸦Juya最新视频，返回视频信息。

    Returns:
        {"bv": "BVxxx", "title": "...", "uploader": "...", "views": "...", "duration": "..."}
    """
    try:
        result = subprocess.run(
            ["bili", "search", query, "--type", "video", "-n", str(count)],
            capture_output=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        print("[错误] bili-cli 未安装，请运行: pip install bilibili-cli")
        return None
    except subprocess.TimeoutExpired:
        print("[错误] bili-cli 搜索超时")
        return None

    # 解析 bili-cli 的表格输出
    # 格式: | 1    | BV1m7RLBtE4f   | 标题... | 橘鸦Juya | 1.6万 | 3:11 |
    videos = []
    lines = output.split("\n")
    current_bv = None
    current_title_parts = []
    current_uploader = None

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 4:
            # 新的一行数据开始
            if current_bv and current_title_parts:
                videos.append({
                    "bv": current_bv,
                    "title": " ".join(current_title_parts),
                    "uploader": current_uploader or "",
                })
            # 第一个 cell 可能是序号或 BV 号
            if cells[0].startswith("BV"):
                current_bv = cells[0]
                current_title_parts = [cells[1]] if len(cells) > 1 else []
                current_uploader = cells[2] if len(cells) > 2 else ""
            elif cells[0].isdigit():
                current_bv = cells[1] if len(cells) > 1 else None
                current_title_parts = [cells[2]] if len(cells) > 2 else []
                current_uploader = cells[3] if len(cells) > 3 else ""
            else:
                # 续行（标题换行）
                if current_title_parts:
                    current_title_parts.append(cells[0])

    # 别忘了最后一个
    if current_bv and current_title_parts:
        videos.append({
            "bv": current_bv,
            "title": " ".join(current_title_parts),
            "uploader": current_uploader or "",
        })

    # 找到包含 "AI" 和 "早报" 的最新视频
    for v in videos:
        title = v["title"]
        if "早报" in title and ("AI" in title or "ai" in title.lower()):
            return v

    # 如果没找到精确匹配，返回第一个
    return videos[0] if videos else None


# ──────────────────────────────────────────────
# 2. 获取视频描述（含微信文章链接）
# ──────────────────────────────────────────────

def get_video_description(bv_id: str) -> Tuple[str, str]:
    """
    通过 yt-dlp 获取视频描述和标题。

    Returns:
        (title, description)
    """
    url = f"https://www.bilibili.com/video/{bv_id}"
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--skip-download", url],
            capture_output=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        data = json.loads(result.stdout)
        return data.get("title", ""), data.get("description", "")
    except Exception as e:
        print(f"[警告] yt-dlp 获取视频信息失败: {e}")
        return "", ""


def extract_wechat_url(description: str) -> Optional[str]:
    """从视频描述中提取微信公众号文章链接"""
    match = re.search(r'https?://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+', description)
    return match.group(0) if match else None


# ──────────────────────────────────────────────
# 3. 获取微信文章全文（Jina Reader）
# ──────────────────────────────────────────────

def fetch_article_via_jina(url: str) -> str:
    """通过 Jina Reader 获取文章全文"""
    jina_url = f"https://r.jina.ai/{url}"
    try:
        resp = requests.get(
            jina_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[警告] Jina Reader 获取失败: {e}")
        return ""


def fetch_article_via_exa(url: str) -> str:
    """备选方案：通过 Exa 获取文章（需要 mcporter）"""
    try:
        result = subprocess.run(
            ["mcporter", "call", f'exa.crawling_exa(urls: ["{url}"], maxCharacters: 15000)'],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
        )
        return result.stdout
    except Exception:
        return ""


# ──────────────────────────────────────────────
# 4. 格式化为企微 Markdown
# ──────────────────────────────────────────────

def format_for_wework_markdown(title: str, date_str: str, articles: List[Dict]) -> str:
    """
    将早报内容格式化为企业微信 markdown。

    Args:
        title: 标题
        date_str: 日期字符串
        articles: [{"heading": "...", "summary": "...", "links": ["..."]}]

    Returns:
        企业微信 markdown 文本
    """
    lines = []
    lines.append(f"# {title}")
    lines.append(f"> 来源：橘鸦Juya | {date_str}")
    lines.append("")

    for i, art in enumerate(articles, 1):
        heading = art.get("heading", "")
        summary = art.get("summary", "")
        links = art.get("links", [])

        if heading:
            lines.append(f"**{heading}**")
        if summary:
            lines.append(summary)
        if links:
            link_text = " | ".join(f"[链接{idx}]({lnk})" for idx, lnk in enumerate(links, 1))
            lines.append(f"> {link_text}")
        lines.append("---")

    lines.append("")
    lines.append("> [视频版](https://www.bilibili.com/video/{bv}) | [公众号原文]({wx})".format(
        bv=articles[0].get("bv", "") if articles else "",
        wx=articles[0].get("wx_url", "") if articles else "",
    ))

    return "\n".join(lines)


def parse_article_to_sections(raw_text: str, bv_id: str = "", wx_url: str = "") -> List[Dict]:
    """
    将 Jina Reader 返回的原始文本解析为结构化段落。

    Returns:
        [{"heading": "标题 #N", "summary": "摘要文本", "links": [...], "bv": ..., "wx_url": ...}]
    """
    sections = []
    current = None

    for line in raw_text.split("\n"):
        line = line.strip()

        # 匹配 ## 标题行（如 "## OpenAI Codex 新增... #1"）
        heading_match = re.match(r'^#{1,3}\s+(.+?)(?:\s*`#\d+`)?$', line)
        if heading_match and "早报" not in line and "概览" not in line and "要闻" not in line \
                and "开发生态" not in line and "产品应用" not in line and "技术与洞察" not in line \
                and "行业动态" not in line:
            if current and current.get("summary"):
                sections.append(current)
            current = {
                "heading": heading_match.group(1).strip(),
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

        # 跳过 blockquote 标记
        if line == ">":
            continue

        # 收集链接
        url_match = re.match(r'^`?(https?://[^\s`]+)`?$', line)
        if url_match:
            current["links"].append(url_match.group(1))
            continue

        # 收集正文摘要（去掉 > 前缀）
        clean = line.lstrip("> ").strip()
        if clean and len(clean) > 10:
            if current["summary"]:
                current["summary"] += "\n"
            current["summary"] += clean

    # 最后一个
    if current and current.get("summary"):
        sections.append(current)

    return sections


def build_wework_payload(title: str, date_str: str, sections: List[Dict],
                         bv_id: str, wx_url: str) -> Dict:
    """构建企业微信 webhook 请求体（markdown 格式）"""
    # 企微 markdown 限制 4096 字节，需要截断
    MAX_BYTES = 3800  # 留一些余量

    md_lines = []
    md_lines.append(f"# 🤖 {title}")
    md_lines.append(f"> 来源：[橘鸦Juya](https://space.bilibili.com/) | {date_str}")
    md_lines.append("")

    for sec in sections:
        heading = sec["heading"]
        summary = sec["summary"]
        links = sec.get("links", [])

        # 截断过长的摘要
        if len(summary.encode("utf-8")) > 300:
            summary = summary[:120] + "..."

        md_lines.append(f"**📌 {heading}**")
        md_lines.append(summary)
        if links:
            md_lines.append(f"> 🔗 [参考链接]({links[0]})")
        md_lines.append("---")

    md_lines.append("")
    md_lines.append(f"> 📺 [B站视频](https://www.bilibili.com/video/{bv_id})")
    if wx_url:
        md_lines.append(f"> 📄 [公众号原文]({wx_url})")

    content = "\n".join(md_lines)

    # 检查长度，如果超限就逐条删减
    while len(content.encode("utf-8")) > MAX_BYTES and len(sections) > 3:
        sections.pop()
        # 重新构建
        md_lines = []
        md_lines.append(f"# 🤖 {title}")
        md_lines.append(f"> 来源：[橘鸦Juya](https://space.bilibili.com/) | {date_str}")
        md_lines.append("")
        for sec in sections:
            heading = sec["heading"]
            summary = sec["summary"][:100] + "..." if len(sec["summary"]) > 100 else sec["summary"]
            links = sec.get("links", [])
            md_lines.append(f"**📌 {heading}**")
            md_lines.append(summary)
            if links:
                md_lines.append(f"> 🔗 [参考链接]({links[0]})")
            md_lines.append("---")
        md_lines.append("")
        md_lines.append(f"> 📺 [B站视频](https://www.bilibili.com/video/{bv_id})")
        if wx_url:
            md_lines.append(f"> 📄 [公众号原文]({wx_url})")
        content = "\n".join(md_lines)

    return {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        }
    }


# ──────────────────────────────────────────────
# 5. 推送到企业微信
# ──────────────────────────────────────────────

def send_to_wework(webhook_url: str, payload: Dict) -> bool:
    """发送到企业微信 webhook"""
    try:
        resp = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        result = resp.json()
        if result.get("errcode") == 0:
            print("[成功] 已推送到企业微信")
            return True
        else:
            print(f"[失败] 企业微信返回错误: {result}")
            return False
    except Exception as e:
        print(f"[失败] 推送异常: {e}")
        return False


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="橘鸦Juya AI早报 → 企业微信推送")
    parser.add_argument("--webhook", type=str, default="", help="企业微信 Webhook URL")
    parser.add_argument("--dry-run", action="store_true", help="只打印不推送")
    parser.add_argument("--query", type=str, default="橘鸦Juya AI早报", help="搜索关键词")
    parser.add_argument("--text-mode", action="store_true", help="使用 text 格式（个人微信模式）")
    args = parser.parse_args()

    print("=" * 50)
    print("🍊 橘鸦Juya AI 早报抓取器")
    print("=" * 50)

    # Step 1: 搜索最新视频
    print("\n[1/4] 搜索最新 AI 早报视频...")
    video = search_latest_juya_video(args.query)
    if not video:
        print("[错误] 未找到视频")
        sys.exit(1)

    bv_id = video["bv"]
    title = video["title"]
    print(f"  找到: {title} ({bv_id})")

    # Step 2: 获取视频描述，提取微信链接
    print("\n[2/4] 获取视频信息...")
    _, description = get_video_description(bv_id)
    wx_url = extract_wechat_url(description)
    if wx_url:
        print(f"  微信文章: {wx_url}")
    else:
        print("  [提示] 未找到微信文章链接，将使用视频描述")

    # Step 3: 获取文章全文
    print("\n[3/4] 获取文章全文...")
    article_text = ""
    if wx_url:
        article_text = fetch_article_via_jina(wx_url)
        if not article_text:
            print("  Jina 失败，尝试 Exa...")
            article_text = fetch_article_via_exa(wx_url)

    if not article_text:
        print("  [回退] 使用视频描述作为内容")
        article_text = description

    # 解析文章结构
    sections = parse_article_to_sections(article_text, bv_id, wx_url)
    print(f"  解析到 {len(sections)} 条新闻")

    # 提取日期
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
    date_str = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")

    # Step 4: 推送
    print("\n[4/4] 构建推送内容...")
    payload = build_wework_payload(title, date_str, sections, bv_id, wx_url)

    # 预览
    md_content = payload["markdown"]["content"]
    print(f"\n{'─' * 50}")
    print("📋 推送预览：")
    print(f"{'─' * 50}")
    print(md_content)
    print(f"{'─' * 50}")
    print(f"字节数: {len(md_content.encode('utf-8'))} / 4096")

    if args.dry_run:
        print("\n[DRY RUN] 跳过推送")
        return

    webhook = args.webhook
    if not webhook:
        # 尝试从环境变量读取
        import os
        webhook = os.environ.get("WECOM_WEBHOOK_URL", "")

    if not webhook:
        print("\n[提示] 未配置企业微信 Webhook URL")
        print("  方式1: python scripts/juya_briefing.py --webhook 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx'")
        print("  方式2: 设置环境变量 WECOM_WEBHOOK_URL")
        print("  方式3: 在 config/config.yaml 的 notification.channels.wework.webhook_url 中配置")
        return

    print("推送到企业微信...")
    send_to_wework(webhook, payload)


if __name__ == "__main__":
    main()
