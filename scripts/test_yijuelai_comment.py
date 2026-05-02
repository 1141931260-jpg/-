"""测试完整推送流程（两个UP主）"""
import sys
sys.path.insert(0, ".")

from trendradar.watch.bilibili_up import collect_bilibili_up_content

# 测试1: 橘鸦Juya
print("=" * 60)
print("📺 橘鸦Juya AI早报")
print("=" * 60)
r1 = collect_bilibili_up_content(
    search_query="橘鸦Juya AI早报",
    title_filter="早报",
    max_items=1,
    uid=285286947,
)
print(f"items: {len(r1['items'])}, errors: {r1['errors']}")
for item in r1["items"]:
    print(f"  Title: {item['title']}")
    print(f"  Sections: {item['section_count']}")
    for sec in item["sections"][:3]:
        print(f"    - {sec['heading'][:60]}")

# 测试2: 一觉醒来发生啥
print("\n" + "=" * 60)
print("📺 一觉醒来发生啥")
print("=" * 60)
r2 = collect_bilibili_up_content(
    search_query="一觉醒来发生啥",
    max_items=1,
    uid=3546606469123022,
    use_pinned_comment=True,
)
print(f"items: {len(r2['items'])}, errors: {r2['errors']}")
for item in r2["items"]:
    print(f"  Title: {item['title']}")
    print(f"  Sections: {item['section_count']}")
    for sec in item["sections"][:3]:
        print(f"    - {sec['heading'][:60]}")

"""检查UP主的所有回复（可能有多条）"""
import requests
import asyncio
import time
from bilibili_api import video

BV = "BV1LLRGBAE9N"
UID = 3546606469123022

async def get_aid():
    v = video.Video(bvid=BV)
    for attempt in range(3):
        try:
            info = await v.get_info()
            return info["aid"]
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
    return None

aid = asyncio.run(get_aid())
print(f"AID: {aid}")

# 获取多页评论
all_up_replies = []
for pn in range(1, 6):
    url = "https://api.bilibili.com/x/v2/reply"
    params = {"oid": aid, "type": 1, "sort": 2, "pn": pn, "ps": 20}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{BV}",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    data = resp.json()
    replies = data.get("data", {}).get("replies") or []
    
    if not replies:
        print(f"  第{pn}页无回复")
        break
    
    print(f"  第{pn}页: {len(replies)} 条回复")
    for r in replies:
        mid = r.get("member", {}).get("mid", 0)
        msg = r.get("content", {}).get("message", "")
        rpid = r.get("rpid", "")
        if str(mid) == str(UID):
            all_up_replies.append({"rpid": rpid, "msg": msg, "page": pn})
            print(f"    [UP主] rpid={rpid} len={len(msg)}")

print(f"\n=== UP主共 {len(all_up_replies)} 条回复 ===")
for i, r in enumerate(all_up_replies):
    print(f"\n--- 回复 {i+1} (page={r['page']}, len={len(r['msg'])}) ---")
    print(r["msg"])

"""检查B站评论是否有展开/全文API"""
import requests
import asyncio
import time
from bilibili_api import video

BV = "BV1LLRGBAE9N"
UID = 3546606469123022
RPID = 300980446512

async def get_aid():
    v = video.Video(bvid=BV)
    for attempt in range(3):
        try:
            info = await v.get_info()
            return info["aid"]
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
    return None

aid = asyncio.run(get_aid())
print(f"AID: {aid}")

# 尝试1: 获取单条评论详情
print("\n=== 尝试1: 单条评论详情 ===")
url1 = "https://api.bilibili.com/x/v2/reply/detail"
params1 = {"oid": aid, "type": 1, "rpid": RPID, "pn": 1}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV}",
}
resp1 = requests.get(url1, params=params1, headers=headers, timeout=15)
data1 = resp1.json()
print(f"  code: {data1.get('code')}")
print(f"  message: {data1.get('message')}")
if data1.get("code") == 0:
    root = data1.get("data", {}).get("root", {})
    if root:
        msg = root.get("content", {}).get("message", "")
        print(f"  root msg len: {len(msg)}")
        print(f"  root msg: {msg[:200]}")

# 尝试2: 用 sort=0 (时间排序) 获取更多评论
print("\n=== 尝试2: 时间排序获取更多 ===")
url2 = "https://api.bilibili.com/x/v2/reply"
params2 = {"oid": aid, "type": 1, "sort": 0, "pn": 1, "ps": 49}
resp2 = requests.get(url2, params=params2, headers=headers, timeout=15)
data2 = resp2.json()
replies2 = data2.get("data", {}).get("replies") or []
print(f"  replies count: {len(replies2)}")
for r in replies2:
    mid = r.get("member", {}).get("mid", 0)
    msg = r.get("content", {}).get("message", "")
    rpid = r.get("rpid", "")
    if str(mid) == str(UID):
        print(f"  [UP主] rpid={rpid} len={len(msg)}")
        print(f"  msg: {msg[:100]}...")

# 尝试3: 检查评论是否有子评论（续楼）
print("\n=== 尝试3: 检查子评论 ===")
for r in replies2:
    mid = r.get("member", {}).get("mid", 0)
    rpid = r.get("rpid", "")
    rcount = r.get("rcount", 0)
    if str(mid) == str(UID) and rcount > 0:
        print(f"  UP主评论 rpid={rpid} 有 {rcount} 条子评论")
        # 获取子评论
        url3 = "https://api.bilibili.com/x/v2/reply/reply"
        params3 = {"oid": aid, "type": 1, "root": rpid, "pn": 1, "ps": 20}
        resp3 = requests.get(url3, params=params3, headers=headers, timeout=15)
        data3 = resp3.json()
        sub_replies = data3.get("data", {}).get("replies") or []
        print(f"  子评论数: {len(sub_replies)}")
        for sr in sub_replies:
            sr_mid = sr.get("member", {}).get("mid", 0)
            sr_msg = sr.get("content", {}).get("message", "")
            print(f"    [mid={sr_mid}] len={len(sr_msg)} msg={sr_msg[:100]}")

"""尝试从B站网页获取完整评论"""
import requests
import re
import asyncio
import time
from bilibili_api import video

BV = "BV1LLRGBAE9N"
UID = 3546606469123022

async def get_aid():
    v = video.Video(bvid=BV)
    for attempt in range(3):
        try:
            info = await v.get_info()
            return info["aid"]
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
    return None

aid = asyncio.run(get_aid())

# 尝试用 wbi 签名的 API 获取完整评论
# B站评论有 "展开全文" 功能，对应的API可能是 reply/reply 或者有 extra_reply 参数
print("=== 尝试 extra_reply 参数 ===")
url = "https://api.bilibili.com/x/v2/reply"
params = {"oid": aid, "type": 1, "sort": 2, "pn": 1, "ps": 20, "extra_reply": 1}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"https://www.bilibili.com/video/{BV}",
}
resp = requests.get(url, params=params, headers=headers, timeout=15)
data = resp.json()
replies = data.get("data", {}).get("replies") or []
for r in replies:
    mid = r.get("member", {}).get("mid", 0)
    msg = r.get("content", {}).get("message", "")
    if str(mid) == str(UID):
        print(f"  len={len(msg)}")
        print(f"  msg: {msg}")

# 尝试 reply/main
print("\n=== 尝试 reply/main ===")
url2 = "https://api.bilibili.com/x/v2/reply/main"
params2 = {"oid": aid, "type": 1, "mode": 3, "next": 0}
resp2 = requests.get(url2, params=params2, headers=headers, timeout=15)
data2 = resp2.json()
print(f"  code: {data2.get('code')}")
if data2.get("code") == 0:
    replies2 = data2.get("data", {}).get("replies") or []
    print(f"  replies: {len(replies2)}")
    for r in replies2:
        mid = r.get("member", {}).get("mid", 0)
        msg = r.get("content", {}).get("message", "")
        if str(mid) == str(UID):
            print(f"  [UP主] len={len(msg)}")
            print(f"  msg: {msg}")

# 尝试 reply/wbi/main (wbi签名版本)
print("\n=== 尝试 reply/hot ===")
url3 = "https://api.bilibili.com/x/v2/reply/hot"
params3 = {"oid": aid, "type": 1, "pn": 1, "ps": 20}
resp3 = requests.get(url3, params=params3, headers=headers, timeout=15)
data3 = resp3.json()
print(f"  code: {data3.get('code')}")
if data3.get("code") == 0:
    replies3 = data3.get("data", {}).get("replies") or []
    print(f"  replies: {len(replies3)}")
    for r in replies3:
        mid = r.get("member", {}).get("mid", 0)
        msg = r.get("content", {}).get("message", "")
        if str(mid) == str(UID):
            print(f"  [UP主] len={len(msg)}")
            print(f"  msg: {msg}")
