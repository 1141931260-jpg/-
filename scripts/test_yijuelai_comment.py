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
