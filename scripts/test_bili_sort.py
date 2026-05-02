# coding=utf-8
"""测试按发布时间排序"""
import asyncio
import re
from bilibili_api import search as bili_search

async def test():
    result = await bili_search.search_by_type(
        "橘鸦Juya AI早报",
        search_type=bili_search.SearchObjectType.VIDEO,
        page=1,
        order_type=bili_search.OrderVideo.PUBDATE,
    )
    videos = result.get("result", [])
    for v in videos[:5]:
        title = re.sub(r"<[^>]+>", "", v.get("title", ""))
        print(f'{v.get("bvid", "")} | {title}')

asyncio.run(test())
