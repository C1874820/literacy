import os
import json
import urllib.request
import urllib.error

FLOWUS_TOKEN = os.environ.get("FLOWUS_TOKEN")
DATABASE_ID = "10df60aa-aee0-4727-adab-f4d99e1cc053"
OUTPUT_PATH = "/mnt/d/rex-识字系统/books_from_flowus.json"

def fetch_all_books():
    if not FLOWUS_TOKEN:
        print("ERROR: FLOWUS_TOKEN not set")
        return []

    url = f"https://api.flowus.cn/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {FLOWUS_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
        print(e.read().decode())
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []

    books = []
    seen_titles = set()
    for page in data.get("results", []):
        props = page.get("properties", {})
        title_field = props.get("title", {})
        title_parts = title_field.get("title", [])
        if not title_parts:
            continue
        title = "".join(t.get("plain_text", "") for t in title_parts)
        if not title:
            continue

        status_field = props.get("状态", {})
        status = None
        if status_field.get("select"):
            status = status_field["select"].get("name")

        chars_field = props.get("认字情况", {})
        chars_text = "".join(t.get("plain_text", "") for t in chars_field.get("rich_text", []))

        source_field = props.get("书籍来源", {})
        source = None
        if source_field.get("select"):
            source = source_field["select"].get("name")

        if title not in seen_titles:
            seen_titles.add(title)
            books.append({
                "title": title,
                "status": status,
                "learned_chars_raw": chars_text,
                "source": source,
                "page_id": page.get("id")
            })

    return books

if __name__ == "__main__":
    books = fetch_all_books()
    output = {"books": books, "count": len(books)}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Fetched {len(books)} unique books → {OUTPUT_PATH}")
