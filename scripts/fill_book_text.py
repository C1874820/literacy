#!/usr/bin/env python3
"""从 search_texts/*.txt 提取汉字，填充 character_bank.json 对应书籍的 characters。
用法: python3 scripts/fill_book_text.py
规则:
  - 文件名(去.txt) 需匹配 character_bank.json 中的书名（支持模糊包含）
  - 提取所有 CJK 字符（\u4e00-\u9fff）去重排序
  - 与书籍已有 characters 取并集（保留 FlowUs 认字记录）
  - 更新 total_chars，标记 text_source=searched，重算全库字频，写 log
"""
import json, os, glob, datetime

BASE = "/mnt/d/rex-识字系统"
BANK = f"{BASE}/character_bank.json"
TEXT_DIR = f"{BASE}/search_texts"


def extract_cjk(text):
    return sorted(set(c for c in text if '\u4e00' <= c <= '\u9fff'))


def main():
    bank = json.load(open(BANK, encoding="utf-8"))
    books = bank["books"]
    files = sorted(glob.glob(f"{TEXT_DIR}/*.txt"))
    updated = []
    for fp in files:
        title_raw = os.path.basename(fp)[:-4]
        text = open(fp, encoding="utf-8").read()
        chars = extract_cjk(text)
        # 精确匹配（书名/去冒号）
        matched = None
        for t in books:
            if t == title_raw or t.replace("：", "") == title_raw.replace("：", ""):
                matched = t
                break
        # 模糊：互相包含
        if matched is None:
            for t in books:
                if title_raw in t or t in title_raw:
                    matched = t
                    break
        if matched is None:
            print(f"[跳过] 无法匹配书名: {title_raw}")
            continue
        info = books[matched]
        before = len(info.get("characters", []))
        merged = sorted(set(info.get("characters", [])) | set(chars))
        info["characters"] = merged
        info["total_chars"] = len(merged)
        info["text_source"] = "searched"
        updated.append(f"{matched}: {before}→{len(merged)}字(全文{len(chars)}字)")

    if not updated:
        print("未更新任何书")
        return

    # 重建字频
    from collections import Counter
    counter = Counter()
    for info in books.values():
        for c in info.get("characters", []):
            counter[c] += 1

    new_chars = {}
    for c, freq in counter.most_common():
        book_list = [bt for bt, info in books.items() if c in info.get("characters", [])]
        old = bank["chars"].get(c, {})
        new_chars[c] = {"freq": freq, "books": book_list, "learned": old.get("learned", False),
                        "source": old.get("source", "")}
    bank["chars"] = new_chars

    bank["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    bank["log"].append({"ts": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
                        "action": f"填充全文 {len(updated)}本书",
                        "detail": "; ".join(updated)})
    json.dump(bank, open(BANK, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for u in updated:
        print(f"  ✓ {u}")


if __name__ == "__main__":
    main()