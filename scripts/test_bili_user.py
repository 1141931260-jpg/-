# coding=utf-8
"""查找橘鸦Juya的UID并获取最新视频"""
import asyncio
import re
from bilibili_api import user, search

async def test():
    # 搜索用户
    result = await search.search_by_type(
        "橘鸦Juya",
        search_type=search.SearchObjectType.USER,
        page=1,
    )
    users = result.get("result", [])
    for u in users[:3]:
        mid = u.get("mid", "")
        uname = u.get("uname", "")
        print(f"UID: {mid} | {uname}")

    if users:
        mid = users[0].get("mid", "")
        print(f"\n--- 获取 UID={mid} 的最新视频 ---")
        u = user.User(uid=mid)
        videos = await u.get_videos(pn=1, ps=5)
        vlist = videos.get("list", {}).get("vlist", [])
        for v in vlist[:5]:
            print(f'{v.get("bvid", "")} | {v.get("title", "")} | {v.get("created", "")}')

asyncio.run(test())
