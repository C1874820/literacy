"""
全自动同步脚本 | cron 触发 | 周一到五 10:00

全自动部分（100%可靠）：
  1. 拉息流书单 + 认字情况
  2. 同步已学汉字状态
  3. 检测新增书籍
  4. 更新字库 JSON

半自动部分（新书文字提取）：
  新增的书标记 text_source: "pending"
  当我活跃时，自动处理待搜书单
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime

BASE_DIR = "/mnt/d/rex-识字系统"
CHAR_BANK_PATH = f"{BASE_DIR}/character_bank.json"
SYNC_LOG_PATH = f"{BASE_DIR}/sync_log.txt"
DATABASE_ID = "10df60aa-aee0-4727-adab-f4d99e1cc053"
FLOWUS_TOKEN = os.environ.get("FLOWUS_TOKEN")

NEW_BOOKS_FOUND = []
PENDING_FILE = f"{BASE_DIR}/pending_books.json"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(SYNC_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_flowus_books():
    if not FLOWUS_TOKEN:
        log("ERROR: FLOWUS_TOKEN 未设置")
        return []
    url = f"https://api.flowus.cn/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {FLOWUS_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        log(f"ERROR: FlowUs API 请求失败 - {e}")
        return []
    books, seen = [], set()
    for page in data.get("results", []):
        props = page.get("properties", {})
        title = "".join(t.get("plain_text", "") for t in props.get("title", {}).get("title", []))
        if not title or title in seen:
            continue
        seen.add(title)
        author = "".join(t.get("plain_text", "") for t in ((props.get("作者") or {}).get("rich_text") or [])) if props.get("作者") else ""
        st_prop = props.get("状态") or {}
        status = (st_prop.get("select") or {}).get("name") if isinstance(st_prop.get("select"), dict) else None
        chars_raw = "".join(t.get("plain_text", "") for t in ((props.get("认字情况") or {}).get("rich_text") or [])) if props.get("认字情况") else ""
        src_prop = props.get("书籍来源") or {}
        source = (src_prop.get("select") or {}).get("name") if isinstance(src_prop.get("select"), dict) else None
        books.append({"title": title, "author": author, "status": status, "learned_chars_raw": chars_raw, "source": source, "page_id": page.get("id")})
    log(f"FlowUs 拉取 {len(books)} 本书")
    return books


def extract_chinese(text):
    return [c for c in text if '\u4e00' <= c <= '\u9fff']


def merge_supabase_entries(bank):
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        log("WARN: SUPABASE_URL/KEY 未设置，跳过 Supabase 合并")
        return bank
    try:
        req = urllib.request.Request(
            f"{url}/rest/v1/words?select=new_words,date,recorder,book_name",
            headers={"apikey": key, "Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode())
    except Exception as e:
        log(f"WARN: Supabase 合并失败（网络/项目不可达）- {e}")
        return bank
    sync_count = 0
    for row in rows:
        c = (row.get("new_words") or "").strip()
        if not c or c not in bank["chars"]:
            continue
        if bank["chars"][c]["status"] == "未学":
            bank["chars"][c]["status"] = "已学"
            bank["chars"][c]["learned_date"] = row.get("date") or datetime.now().strftime("%Y-%m-%d")
            sync_count += 1
            bank["log"].append({
                "date": row.get("date") or datetime.now().strftime("%Y-%m-%d"),
                "book": row.get("book_name") or "网页录入",
                "chars": [c],
                "source": "web"
            })
    if sync_count:
        log(f"Supabase 合并: {sync_count} 字从网页录入汇入字库")
    return bank


def sync():
    log("=" * 40)
    log("自动同步开始")

    flowus = fetch_flowus_books()
    if not flowus:
        log("同步失败：无数据")
        return

    bank = {"version": 1, "books": {}, "chars": {}, "log": [], "progress": {}, "last_updated": ""}
    if os.path.exists(CHAR_BANK_PATH):
        with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
            bank = json.load(f)

    existing = set(bank["books"].keys())
    current_titles = {b["title"] for b in flowus}

    # 移除已删除的书
    for t in existing - current_titles:
        log(f"  息流已移除: {t}")
        del bank["books"][t]

    # 处理每本书
    new_books = []
    for fb in flowus:
        t = fb["title"]
        if t not in bank["books"]:
            bank["books"][t] = {
                "characters": [], "total_chars": 0,
                "status": fb.get("status", "未读"), "source": fb.get("source", "纸质书"),
                "wordless": False, "text_source": "pending"
            }
            new_books.append(t)
            log(f"  新增书籍: {t}" + (f" ({fb['author']})" if fb.get("author") else ""))
        bank["books"][t]["status"] = fb.get("status") or bank["books"][t].get("status")

    # 重建字频
    char_counter = Counter()
    for info in bank["books"].values():
        for c in info.get("characters", []):
            char_counter[c] += 1

    # 更新字库
    chars_dict = {}
    for c, freq in char_counter.most_common():
        books_with = [bt for bt, info in bank["books"].items() if c in info.get("characters", [])]
        old = bank["chars"].get(c, {})
        chars_dict[c] = {
            "freq": freq, "books": books_with,
            "status": old.get("status", "未学"),
            "learned_date": old.get("learned_date")
        }

    # 同步认字情况 → 已学状态
    sync_count = 0
    for fb in flowus:
        raw = fb.get("learned_chars_raw", "")
        if not raw:
            continue
        chars_logged = extract_chinese(raw.replace("、", "，").replace(",", "，"))
        for c in chars_logged:
            if c in chars_dict and chars_dict[c]["status"] == "未学":
                chars_dict[c]["status"] = "已学"
                chars_dict[c]["learned_date"] = datetime.now().strftime("%Y-%m-%d")
                sync_count += 1

    # 合并 Supabase 网页录入（best-effort，网络不通跳过）
    merged = merge_supabase_entries({"chars": chars_dict, "log": bank.get("log", [])})
    chars_dict = merged["chars"]
    bank["log"] = merged["log"]

    learned = sum(1 for c in chars_dict.values() if c["status"] == "已学")
    bank["chars"] = chars_dict
    bank["progress"] = {
        "total_books": len(bank["books"]),
        "total_unique_chars": len(chars_dict),
        "learned": learned, "learning": 0,
        "untouched": len(chars_dict) - learned
    }
    bank["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(CHAR_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    p = bank["progress"]
    log(f"字库更新完成 | {p['total_books']}本 | {p['total_unique_chars']}字 | 已学{learned}(+{sync_count})")

    # 自动提交 + 推送到 GitHub
    try:
        r = subprocess.run(["git", "-C", BASE_DIR, "add", "-A"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            log(f"WARN: git add 失败 - {r.stderr.strip()}")
    except Exception as e:
        log(f"WARN: git add 异常 - {e}")

    try:
        r = subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", "auto-sync " + datetime.now().strftime("%Y-%m-%d")],
                          capture_output=True, text=True, timeout=10)
        if r.returncode != 0 and "nothing to commit" not in r.stderr and "nothing to commit" not in r.stdout:
            log(f"WARN: git commit 可能失败 - rc={r.returncode} {r.stderr.strip()}")
    except Exception as e:
        log(f"WARN: git commit 异常 - {e}")

    try:
        r = subprocess.run(["git", "-C", BASE_DIR, "push", "origin", "main"],
                          capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            log("Git push 成功")
        else:
            log(f"WARN: git push 失败 - {r.stderr.strip()}")
    except Exception as e:
        log(f"WARN: git push 异常 - {e}")

    # 生成网页进度 + 息流页面
    for script in ["generate_progress_html.py", "update_flowus_progress.py"]:
        try:
            result = subprocess.run(
                [sys.executable, f"{BASE_DIR}/scripts/{script}"],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout.strip():
                log(f"  {script}: {result.stdout.strip()}")
            if result.stderr.strip():
                log(f"  {script} stderr: {result.stderr.strip()}")
        except Exception as e:
            log(f"WARN: {script} 执行失败 - {e}")

    # 待搜书记录
    if new_books:
        NEW_BOOKS_FOUND.extend(new_books)
        pending = []
        if os.path.exists(PENDING_FILE):
            with open(PENDING_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
        existing_pending = {b["title"] for b in pending}
        for nb in new_books:
            author = ""
            for fb in flowus:
                if fb["title"] == nb:
                    author = fb.get("author", "")
                    break
            if nb not in existing_pending:
                pending.append({"title": nb, "author": author, "added": datetime.now().strftime("%Y-%m-%d")})
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        log(f"待搜字书: {', '.join(new_books)}")

    log("自动同步结束")


if __name__ == "__main__":
    sync()
