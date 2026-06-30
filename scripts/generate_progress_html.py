"""
从 character_bank.json 生成 progress/index.html
由 auto_sync.py 自动调用
"""
import json
import os

CHAR_BANK_PATH = "/mnt/d/rex-识字系统/character_bank.json"
OUTPUT_DIR = "/mnt/d/rex-识字系统/progress"
OUTPUT_HTML = f"{OUTPUT_DIR}/index.html"
OUTPUT_DATA = f"{OUTPUT_DIR}/data.json"


def load_bank():
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html(bank):
    p = bank["progress"]
    chars = bank["chars"]
    books = bank["books"]
    log = bank["log"]

    # Top 15 untouched chars by frequency
    untouched = [(c, info) for c, info in chars.items() if info["status"] == "未学"]
    untouched.sort(key=lambda x: -x[1]["freq"])
    top_untouched = untouched[:15]

    # Books sorted by char count
    books_sorted = sorted(books.items(), key=lambda x: -x[1]["total_chars"])

    # Recent learning (last 10)
    recent_log = log[-10:]

    # Stats
    learned = p["learned"]
    total = p["total_unique_chars"]
    pct = round(learned / max(total, 1) * 100, 1)

    # Build HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Rex 认字进度</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#f8fafc;color:#1e293b;padding:16px;max-width:500px;margin:0 auto}}
h1{{font-size:22px;font-weight:700;margin-bottom:4px}}
.sub{{font-size:13px;color:#64748b;margin-bottom:16px}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
.row{{display:flex;gap:8px}}
.stat{{flex:1;text-align:center;padding:8px 0}}
.stat-num{{font-size:24px;font-weight:700;color:#0891b2}}
.stat-label{{font-size:12px;color:#64748b;margin-top:2px}}
.bar-wrap{{background:#e2e8f0;border-radius:99px;height:10px;margin:12px 0;overflow:hidden}}
.bar-fill{{height:100%;border-radius:99px;background:linear-gradient(90deg,#06b6d4,#0891b2);transition:width .5s}}
.bar-label{{font-size:12px;color:#64748b;text-align:right}}
h2{{font-size:15px;font-weight:600;margin-bottom:10px}}
.rank-item{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:14px}}
.rank-item:last-child{{border:none}}
.rank-char{{font-weight:600;font-size:15px}}
.rank-freq{{color:#64748b;font-size:12px}}
.tag{{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin-left:4px}}
.tag-learned{{background:#d1fae5;color:#065f46}}
.tag-untouched{{background:#f1f5f9;color:#64748b}}
.log-item{{font-size:13px;padding:4px 0;color:#475569}}
.log-date{{color:#94a3b8;margin-right:6px}}
.book-list{{font-size:13px}}
.book-item{{display:flex;justify-content:space-between;padding:3px 0;color:#475569}}
.empty{{text-align:center;color:#94a3b8;padding:20px;font-size:14px}}
.footer{{text-align:center;font-size:11px;color:#94a3b8;padding:16px 0 32px}}
</style>
</head>
<body>
<h1>📊 Rex 认字进度</h1>
<div class="sub">最后更新：{bank.get('last_updated', '')[:10]}</div>

<div class="card">
  <div class="row">
    <div class="stat"><div class="stat-num">{total}</div><div class="stat-label">总字库</div></div>
    <div class="stat"><div class="stat-num" style="color:#059669">{learned}</div><div class="stat-label">已认识</div></div>
    <div class="stat"><div class="stat-num" style="color:#dc2626">{p['untouched']}</div><div class="stat-label">未学</div></div>
    <div class="stat"><div class="stat-num" style="color:#7c3aed">{p['total_books']}</div><div class="stat-label">书籍</div></div>
  </div>
  <div class="bar-wrap"><div class="bar-fill" style="width:{pct}%"></div></div>
  <div class="bar-label">已认 {learned}/{total} 字 ({pct}%)</div>
</div>
"""
    # Recent log
    html += '<div class="card"><h2>📝 最近认字</h2>'
    if recent_log:
        for entry in reversed(recent_log):
            html += f'<div class="log-item"><span class="log-date">{entry["date"]}</span>《{entry["book"]}》→ {"、".join(entry["chars"])}</div>'
    else:
        html += '<div class="empty">还没有认字记录</div>'
    html += '</div>'

    # Top untouched
    html += '<div class="card"><h2>🏆 高频未学</h2>'
    for i, (c, info) in enumerate(top_untouched, 1):
        html += f'<div class="rank-item"><span><span class="rank-char">{c}</span><span class="tag tag-untouched">未学</span></span><span class="rank-freq">{info["freq"]} 本书</span></div>'
    html += '</div>'

    # Learned chars
    learned_chars = [(c, info) for c, info in chars.items() if info["status"] == "已学"]
    html += '<div class="card"><h2>✅ 已学汉字</h2>'
    if learned_chars:
        for c, info in learned_chars:
            date = info.get("learned_date", "-")
            html += f'<div class="rank-item"><span>{c}</span><span class="rank-freq">{date}</span></div>'
    else:
        html += '<div class="empty">还没有已学汉字</div>'
    html += '</div>'

    # Book list
    html += '<div class="card"><h2>📚 书籍字库</h2>'
    for title, info in books_sorted:
        wl = " (无字)" if info.get("wordless") else ""
        html += f'<div class="book-item"><span>{title}{wl}</span><span>{info["total_chars"]} 字</span></div>'
    html += '</div>'

    html += '<div class="footer">每天 10:00 自动更新 · 数据来源于息流阅读记录</div>'
    html += '</body></html>'

    return html


def generate_data_json(bank):
    """Generate a clean JSON data file for potential future use."""
    data = {
        "version": 1,
        "last_updated": bank.get("last_updated", ""),
        "progress": bank["progress"]
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not os.path.exists(CHAR_BANK_PATH):
        print("character_bank.json not found, skipping HTML generation")
        return

    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)

    html = generate_html(bank)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    data_json = generate_data_json(bank)
    with open(OUTPUT_DATA, "w", encoding="utf-8") as f:
        f.write(data_json)

    p = bank["progress"]
    print(f"progress/index.html → {p['total_books']}本 | {p['total_unique_chars']}字 | 已学{p['learned']}")


if __name__ == "__main__":
    main()
