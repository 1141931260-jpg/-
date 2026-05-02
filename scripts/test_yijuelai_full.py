"""测试完整推送流程（两个UP主）"""
import sys
sys.path.insert(0, ".")

from trendradar.watch.bilibili_up import collect_bilibili_up_content

# 测试1: 橘鸦Juya
print("=" * 60)
print("📺 橘鸦Juya AI早报")
print("=" * 60)
result1 = collect_bilibili_up_content(
    search_query="橘鸦Juya AI早报",
    uid=285286947,
    max_items=1,
    title_filter="早报",
)
items1 = result1.get("items", [])
errors1 = result1.get("errors", [])
print(f"items: {len(items1)}, errors: {errors1}")
for item in items1:
    print(f"  Title: {item['title']}")
    print(f"  Sections: {len(item.get('sections', []))}")
    for s in item.get("sections", [])[:3]:
        print(f"    - {s['heading'][:60]}")

# 测试2: 一觉醒来发生啥
print("\n" + "=" * 60)
print("📺 一觉醒来发生啥")
print("=" * 60)
result2 = collect_bilibili_up_content(
    search_query="一觉醒来发生啥",
    uid=3546606469123022,
    max_items=1,
    use_pinned_comment=True,
)
items2 = result2.get("items", [])
errors2 = result2.get("errors", [])
print(f"items: {len(items2)}, errors: {errors2}")
for item in items2:
    print(f"  Title: {item['title']}")
    sections = item.get("sections", [])
    print(f"  Sections: {len(sections)}")
    for s in sections[:5]:
        print(f"    - {s['heading'][:80]}")
    if len(sections) > 5:
        print(f"    ... 还有 {len(sections) - 5} 条")
