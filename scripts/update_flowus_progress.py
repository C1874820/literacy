"""
在息流创建「Rex认字进度」页面（一次性创建，后续更新标题+属性）
"""
import json
import os
import urllib.request
import urllib.error

CHAR_BANK_PATH = "/mnt/d/rex-识字系统/character_bank.json"
FLOWUS_TOKEN = os.environ.get("FLOWUS_TOKEN")
STATE_FILE = "/mnt/d/rex-识字系统/.flowus_progress_state"


def load_bank():
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def flowus(method, url, data=None):
    headers = {
        "Authorization": f"Bearer {FLOWUS_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API error {e.code}: {body[:300]}")
        return None


def create_page():
    """Create a top-level page in FlowUs."""
    return flowus("POST", "https://api.flowus.cn/v1/pages", {
        "properties": {
            "title": {
                "type": "title",
                "title": [{"type": "text", "text": {"content": "📊 Rex认字进度"}}]
            }
        }
    })


def add_content(page_id, bank):
    """Append content blocks to the page."""
    p = bank["progress"]
    chars = bank["chars"]

    learned = sum(1 for c in chars.values() if c["status"] == "已学")
    total = p["total_unique_chars"]
    pct = round(learned / max(total, 1) * 100, 1)

    top_untouched = [(c, info) for c, info in chars.items() if info["status"] == "未学"]
    top_untouched.sort(key=lambda x: -x[1]["freq"])
    top10 = top_untouched[:10]

    learned_chars = [(c, info) for c, info in chars.items() if info["status"] == "已学"]
    log_entries = bank.get("log", [])[-5:]

    children = []

    # Stats callout
    stat = "总字库{}字 · 已认识{}字({}%) · 来自{}本书".format(total, learned, pct, p["total_books"])
    children.append({"type": "callout", "data": {"rich_text": [{"type": "text", "text": {"content": stat}}], "icon": "📊"}})

    # Top 10
    top_lines = ["高频未学 TOP 10："]
    for c, info in top10:
        top_lines.append("{}（{}本书）".format(c, info["freq"]))
    children.append({"type": "paragraph", "data": {"rich_text": [{"type": "text", "text": {"content": "\n".join(top_lines)}}]}})

    # Recent log
    if log_entries:
        log_lines = ["最近认字："]
        for entry in reversed(log_entries):
            log_lines.append("{}《{}》→{}".format(entry["date"], entry["book"], "、".join(entry["chars"])))
    else:
        log_lines = ["还没有认字记录"]
    children.append({"type": "paragraph", "data": {"rich_text": [{"type": "text", "text": {"content": "\n".join(log_lines)}}]}})

    # Learned chars
    if learned_chars:
        parts = ["已学识字："]
        for c, info in learned_chars:
            parts.append(c)
        children.append({"type": "paragraph", "data": {"rich_text": [{"type": "text", "text": {"content": " ".join(parts)}}]}})

    # Footer
    last_updated = bank.get("last_updated", "")[:10]
    children.append({"type": "divider", "data": {}})
    children.append({
        "type": "paragraph",
        "data": {"rich_text": [{"type": "text", "text": {"content": "自动更新于 " + last_updated}}]}
    })

    result = flowus("PATCH", "https://api.flowus.cn/v1/blocks/" + page_id + "/children", {"children": children})
    if result:
        print("息流进度页面已更新内容")


def main():
    if not FLOWUS_TOKEN:
        print("FLOWUS_TOKEN not set, skipping")
        return
    if not os.path.exists(CHAR_BANK_PATH):
        print("character_bank.json not found, skipping")
        return

    bank = load_bank()

    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                state = json.load(f)
            except:
                state = {}

    page_id = state.get("page_id")

    if not page_id:
        result = create_page()
        if not result:
            print("创建息流页面失败")
            return
        page_id = result["id"]
        state["page_id"] = page_id
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        print("息流进度页面已创建（首次）")

        # Add initial content
        add_content(page_id, bank)
    else:
        # Update page title icon to reflect latest date
        last_updated = bank.get("last_updated", "")[:10]
        flowus("PATCH", "https://api.flowus.cn/v1/pages/" + page_id, {
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"type": "text", "text": {"content": "📊 Rex认字进度（" + last_updated + "）"}}]
                }
            }
        })
        print("息流进度页面已更新标题")


if __name__ == "__main__":
    main()
