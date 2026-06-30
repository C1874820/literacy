"""
学习记录解析器
用法：
  python3 process_log.py "6/28 大卫不可以 不、可"
  python3 process_log.py --batch  # 从文件读取多条记录

支持格式：
  6/28 大卫不可以 不、可
  6-28 猜猜我有多爱你 大、小、多
  2026-6-28 好饿的毛毛虫 好、饿、虫
"""
import json
import re
import sys
import os
from datetime import datetime

CHAR_BANK_PATH = "/mnt/d/rex-识字系统/character_bank.json"


def load_bank():
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_bank(bank):
    with open(CHAR_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)


def parse_date(text):
    """Parse various date formats. Returns YYYY-MM-DD or None."""
    # 6/28 → 2026-06-28
    m = re.search(r'(\d{1,2})/(\d{1,2})', text)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # 6-28
    m = re.search(r'(\d{1,2})-(\d{1,2})', text)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # 2026-6-28
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 6月28日
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        return f"2026-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def extract_chinese(text):
    return [c for c in text if '\u4e00' <= c <= '\u9fff']


def fuzzy_find_book(title, bank):
    """Find a book in the bank by exact match or substring match."""
    if title in bank["books"]:
        return title
    # Try substring match
    for bt in bank["books"]:
        if title in bt or bt in title:
            return bt
    return None


def parse_entry(text, bank):
    """Parse a single entry text. Returns (date, book, [chars]) or None."""
    text = text.strip()
    if not text or text.startswith("#") or text.startswith("//"):
        return None

    date = parse_date(text)
    if not date:
        return None

    # Remove the date part
    remainder = re.sub(r'\d{1,4}[-/]\d{1,2}[-/]?\d{0,4}|\d{1,2}月\d{1,2}日', '', text).strip()

    # Try to find which book name is mentioned (known from character bank)
    chars = []
    matched_book = None
    matched_book_len = 0

    # Sort book titles by length descending to match longest first
    book_titles = sorted(bank["books"].keys(), key=len, reverse=True)
    for bt in book_titles:
        if bt in remainder:
            matched_book = bt
            matched_book_len = len(bt)
            break

    if matched_book:
        # Remove the book name from remainder to get the chars part
        chars_remainder = remainder.replace(matched_book, "", 1).strip()
        # Extract Chinese chars, splitting by common delimiters
        # First try to find delimited lists (、，, etc)
        # Just extract all Chinese chars - the book name is already removed
        raw_chars = extract_chinese(chars_remainder)
        # Remove duplicates while preserving order
        seen = set()
        chars = []
        for c in raw_chars:
            if c not in seen:
                seen.add(c)
                chars.append(c)

    if not matched_book or not chars:
        return None

    return date, matched_book, chars


def process_single(text):
    bank = load_bank()
    result = parse_entry(text, bank)

    if not result:
        print("❌ 无法解析。支持格式：6/28 书名 字、字、字")
        return

    date, book_title, chars = result
    matched_book = fuzzy_find_book(book_title, bank)

    if not matched_book:
        print(f"⚠️  未在字库中找到书名「{book_title}」")
        print(f"   字库中已有：{', '.join(bank['books'].keys())}")
        return

    if not chars:
        print("⚠️  未提取到汉字，请确认格式：日期 书名 字、字、字")
        return

    # Update learning log
    entry = {
        "date": date,
        "book": matched_book,
        "chars": chars
    }
    bank["log"].append(entry)

    # Update character status
    for c in chars:
        if c in bank["chars"] and bank["chars"][c]["status"] == "未学":
            bank["chars"][c]["status"] = "已学"
            bank["chars"][c]["learned_date"] = date

    # Update progress
    learned = sum(1 for c in bank["chars"].values() if c["status"] == "已学")
    bank["progress"]["learned"] = learned
    bank["progress"]["untouched"] = bank["progress"]["total_unique_chars"] - learned

    save_bank(bank)

    print(f"✅ 已记录：{date} 读了《{matched_book}》")
    print(f"   认字：{'、'.join(chars)}")
    print(f"   累计已学：{learned} / {bank['progress']['total_unique_chars']} 字")


def process_batch(file_path):
    """Process multiple entries from a file."""
    bank = load_bank()
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    count = 0
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            print(f"\n── {line}")
            process_single(line)
            count += 1

    print(f"\n共处理 {count} 条记录")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--batch":
        process_batch(sys.argv[2])
    elif len(sys.argv) >= 2:
        process_single(" ".join(sys.argv[1:]))
    else:
        print("用法:")
        print("  python3 process_log.py \"6/28 大卫不可以 不、可\"")
        print("  python3 process_log.py --batch log.txt")
