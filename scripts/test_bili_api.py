# coding=utf-8
"""测试 bilibili-api-python 搜索功能"""
import asyncio
import json
import re
from bilibili_api import search

async def test():
    result = await search.search_by_type(
        "橘鸦Juya AI早报",
        search_type=search.SearchObjectType.VIDEO,
        page=1,
    )
    videos = result.get("result", [])
    for v in videos[:3]:
        title = re.sub(r"<[^>]+>", "", v.get("title", ""))
        print(f'{v.get("bvid", "")} | {title} | {v.get("author", "")}')

asyncio.run(test())
