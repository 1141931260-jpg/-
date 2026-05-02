"""搜索B站UP主获取UID"""
import asyncio
from bilibili_api import search

async def main():
    r = await search.search_by_type(
        "一觉醒来发生啥",
        search_type=search.SearchObjectType.USER,
        order_type=search.OrderUser.FANS,
    )
    for u in r.get("result", [])[:5]:
        print(f"UID:{u['mid']}  Name:{u['uname']}")

asyncio.run(main())
