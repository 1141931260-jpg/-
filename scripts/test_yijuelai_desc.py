"""测试视频描述内容"""
import asyncio
import time
from bilibili_api import video

BV = "BV1LLRGBAE9N"

async def main():
    v = video.Video(bvid=BV)
    for attempt in range(3):
        try:
            info = await v.get_info()
            print(f"Title: {info.get('title', '')}")
            print(f"Desc: {info.get('desc', '')}")
            print(f"Desc length: {len(info.get('desc', ''))}")
            break
        except Exception as e:
            print(f"  失败 (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(3)

asyncio.run(main())
