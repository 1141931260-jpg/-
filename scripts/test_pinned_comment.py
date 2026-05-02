"""验证UP主视频列表 + 评论区置顶"""
import asyncio
from bilibili_api import user, comment, video

UID = 3546606469123022

async def main():
    # 1. 获取最新视频
    u = user.User(UID)
    vids = await u.get_videos(pn=1, ps=3)
    vlist = vids.get("list", {}).get("vlist", [])
    print(f"=== 最新 {len(vlist)} 个视频 ===")
    for v in vlist:
        print(f"  BV:{v['bvid']}  Title:{v['title']}  Date:{v['created']}")

    if not vlist:
        print("没有视频")
        return

    # 2. 获取最新视频的评论区置顶
    bv = vlist[0]["bvid"]
    print(f"\n=== 获取 {bv} 的置顶评论 ===")
    v = video.Video(bvid=bv)
    vinfo = await v.get_info()
    aid = vinfo["aid"]

    # 获取评论，sort=1 是按时间，sort=2 是按热度
    # 置顶评论通常在最前面
    try:
        comments = await comment.get_comments(
            oid=aid,
            type_=comment.CommentResourceType.VIDEO,
            order=comment.OrderType.TIME,
            page_index=1,
        )
        replies = comments.get("replies") or []
        top_replies = comments.get("top_replies") or []
        
        print(f"  top_replies 数量: {len(top_replies)}")
        print(f"  replies 数量: {len(replies)}")
        
        # 检查置顶
        if top_replies:
            for tr in top_replies:
                msg = tr.get("content", {}).get("message", "")
                print(f"\n  [置顶] {msg[:500]}")
        
        # 也检查 replies 中 rcount > 0 且有 is_top 标记的
        for r in replies[:5]:
            msg = r.get("content", {}).get("message", "")
            is_top = r.get("reply_control", {}).get("is_top", False)
            tag = "[TOP]" if is_top else ""
            print(f"\n  {tag} {msg[:200]}")
    except Exception as e:
        print(f"  评论获取失败: {e}")

asyncio.run(main())
