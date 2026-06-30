"""
进度报告生成器
用法：
  python3 report.py          # 完整报告
  python3 report.py --top 30 # 高频字TOP 30
  python3 report.py --book "书名"  # 某本书详情
"""
import json
import sys

CHAR_BANK_PATH = "/mnt/d/rex-识字系统/character_bank.json"


def load_bank():
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def full_report():
    bank = load_bank()
    p = bank["progress"]
    chars = bank["chars"]
    log = bank["log"]

    print("=" * 50)
    print("  Rex 识字系统 · 进度报告")
    print("=" * 50)
    print(f"  字库书籍: {p['total_books']} 本")
    print(f"  字库总字数: {p['total_unique_chars']} 个")
    print(f"  已认识: {p['learned']} 字 ({p['learned']/max(p['total_unique_chars'],1)*100:.1f}%)")
    print(f"  学习中: {p['learning']} 字")
    print(f"  未学: {p['untouched']} 字")
    print()

    # 学习记录
    print(f"  最近学习记录 ({len(log)} 条):")
    for entry in log[-5:]:
        print(f"    {entry['date']} 《{entry['book']}》 → {'、'.join(entry['chars'])}")
    print()

    # 高频未学 TOP 10
    untouched = [(c, info) for c, info in chars.items() if info["status"] == "未学"]
    untouched.sort(key=lambda x: -x[1]["freq"])
    print(f"  高频未学字 TOP 10:")
    for c, info in untouched[:10]:
        books_str = "、".join(info["books"][:3])
        print(f"    {c}: 出现在 {info['freq']} 本书 ({books_str}...)")

    print()
    # 已学字
    learned = [(c, info) for c, info in chars.items() if info["status"] == "已学"]
    learned.sort(key=lambda x: x[1].get("learned_date", "") or "")
    print(f"  已学汉字 ({len(learned)} 个):")
    for c, info in learned:
        date = info.get("learned_date") or "-"
        print(f"    {c} (学于 {date})")

    print()
    # 按书统计
    print(f"  各书字数排行:")
    books_sorted = sorted(bank["books"].items(),
                          key=lambda x: -x[1]["total_chars"])
    for title, info in books_sorted:
        wl = " (无字)" if info.get("wordless") else ""
        print(f"    {title}: {info['total_chars']} 字{wl}")


def top_chars(n=20):
    bank = load_bank()
    chars = bank["chars"]
    sorted_chars = sorted(chars.items(), key=lambda x: -x[1]["freq"])
    print(f"高频字 TOP {n}:")
    for i, (c, info) in enumerate(sorted_chars[:n], 1):
        status = "✓" if info["status"] == "已学" else "○"
        print(f"  {i:2d}. {c} ({status}) - {info['freq']} 本书")


def book_detail(title):
    bank = load_bank()
    if title not in bank["books"]:
        print(f"❌ 未找到「{title}」")
        return
    info = bank["books"][title]
    chars = info["characters"]
    # Find which chars are learned
    learned = [c for c in chars if c in bank["chars"] and bank["chars"][c]["status"] == "已学"]
    print(f"《{title}》")
    print(f"  总字数: {info['total_chars']}")
    print(f"  已学: {len(learned)} 字")
    print(f"  未学: {info['total_chars'] - len(learned)} 字")
    print(f"  所有字: {'、'.join(chars)}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        full_report()
    elif sys.argv[1] == "--top" and len(sys.argv) >= 3:
        top_chars(int(sys.argv[2]))
    elif sys.argv[1] == "--book" and len(sys.argv) >= 3:
        book_detail(sys.argv[2])
    else:
        print("用法: python3 report.py [--top N] [--book 书名]")
