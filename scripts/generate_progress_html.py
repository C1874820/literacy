"""
从 character_bank.json 生成 progress/index.html（儿童识字 app 风格）
"""
import json
import os
from datetime import datetime

CHAR_BANK_PATH = "/mnt/d/rex-识字系统/character_bank.json"
OUTPUT_DIR = "/mnt/d/rex-识字系统/progress"
OUTPUT_DATA = f"{OUTPUT_DIR}/data.json"


def load_bank():
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html(bank):
    p = bank["progress"]
    chars = bank["chars"]
    books = bank["books"]
    log = bank["log"]
    learned = sum(1 for c in chars.values() if c["status"] == "已学")
    total = p["total_unique_chars"]
    pct = round(learned / max(total, 1) * 100, 1)

    top_untouched = [(c, info) for c, info in chars.items() if info["status"] == "未学"]
    top_untouched.sort(key=lambda x: -x[1]["freq"])
    top20_raw = top_untouched[:20]
    learned_chars = [c for c, info in chars.items() if info["status"] == "已学"]
    recent_log = log[-10:]

    last_up = bank.get("last_updated", "")[:10]
    # Character cloud HTML
    max_freq = max((info["freq"] for _, info in top20_raw), default=1)
    cloud_items = []
    for c, info in top20_raw:
        size = 14 + int(info["freq"] / max_freq * 18)
        color = COLORS[hash(c) % len(COLORS)]
        cloud_items.append(f'<span class="cloud-char" style="font-size:{size}px;color:{color}">{c}</span>')

    cloud_html = "\n".join(cloud_items)

    # Learned wall
    wall_items = []
    for c in learned_chars:
        wall_items.append(f'<span class="wall-char">{c}</span>')
    wall_html = "\n".join(wall_items) if wall_items else '<div class="empty-state">还没有已学汉字<br>读完绘本后在息流记录吧 📖</div>'

    # Recent log
    log_items = []
    for entry in reversed(recent_log):
        log_items.append(f'<div class="log-row"><span class="log-date">{entry["date"]}</span><span class="log-book">《{entry["book"]}》</span><span class="log-chars">{",".join(entry["chars"])}</span></div>')
    log_html = "\n".join(log_items) if log_items else '<div class="empty-state">还没有学习记录</div>'

    # Book stats
    books_sorted = sorted(books.items(), key=lambda x: -x[1]["total_chars"])
    book_rows = []
    for title, info in books_sorted:
        wl = " 📄" if info.get("wordless") else ""
        book_rows.append(f'<div class="book-row"><span>{title}{wl}</span><span class="book-count">{info["total_chars"]}</span></div>')
    book_html = "\n".join(book_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Rex 认字进度</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:linear-gradient(135deg,#f0f9ff 0%,#ecfeff 50%,#fefce8 100%);min-height:100vh;padding:0 0 48px}}
.header{{padding:32px 20px 0;text-align:center}}
.header h1{{font-size:28px;font-weight:800;background:linear-gradient(135deg,#06b6d4,#059669);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.header .sub{{font-size:13px;color:#94a3b8;margin-top:4px}}
.ring-wrap{{display:flex;justify-content:center;margin:16px 0 8px}}
.ring-text{{font-size:12px;fill:#64748b}}
.ring-pct{{font-size:32px;font-weight:800;fill:#0f172a}}
.ring-label{{font-size:13px;fill:#94a3b8}}
.stats{{display:flex;gap:8px;padding:0 16px;margin-bottom:16px}}
.stat-card{{flex:1;background:#fff;border-radius:14px;padding:12px 8px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.04)}}
.stat-num{{font-size:20px;font-weight:700;color:#0f172a}}
.stat-label{{font-size:11px;color:#94a3b8;margin-top:2px}}
.section{{padding:0 16px;margin-bottom:16px}}
.section-title{{font-size:15px;font-weight:600;color:#0f172a;margin-bottom:10px;padding-left:4px}}
.card{{background:#fff;border-radius:16px;padding:16px;box-shadow:0 2px 12px rgba(0,0,0,.04)}}
.cloud{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;padding:8px 0}}
.cloud-char{{font-weight:600;padding:4px 10px;border-radius:99px;background:#f8fafc;transition:transform .2s}}
.cloud-char:active{{transform:scale(1.15)}}
.wall{{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}}
.wall-char{{display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,#a7f3d0,#6ee7b7);color:#065f46;font-size:18px;font-weight:700;box-shadow:0 2px 6px rgba(16,185,129,.2)}}
.log-row{{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px}}
.log-row:last-child{{border:none}}
.log-date{{color:#94a3b8;white-space:nowrap}}
.log-book{{color:#475569;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.log-chars{{color:#0891b2;font-weight:600}}
.book-row{{display:flex;justify-content:space-between;padding:5px 0;font-size:13px;color:#475569;border-bottom:1px solid #f8fafc}}
.book-count{{color:#94a3b8;font-size:12px}}
.empty-state{{text-align:center;color:#94a3b8;padding:24px 0;font-size:14px;line-height:1.8}}
.footer{{text-align:center;font-size:11px;color:#cbd5e1;padding:16px}}
</style>
</head>
<body>
<div class="header">
  <h1>📖 Rex 认字</h1>
  <div class="sub">更新于 {last_up} · {p['total_books']} 本书</div>
</div>

<div class="ring-wrap">
<svg width="160" height="160" viewBox="0 0 160 160">
  <circle cx="80" cy="80" r="68" fill="none" stroke="#e2e8f0" stroke-width="10"/>
  <circle cx="80" cy="80" r="68" fill="none" stroke="#06b6d4" stroke-width="10" stroke-linecap="round"
    stroke-dasharray="{pct*4.27} {427-pct*4.27}" transform="rotate(-90 80 80)"/>
  <text x="80" y="68" text-anchor="middle" class="ring-pct">{pct}%</text>
  <text x="80" y="88" text-anchor="middle" class="ring-label">已认识</text>
  <text x="80" y="104" text-anchor="middle" class="ring-text">{learned}/{total}</text>
</svg>
</div>

<div class="stats">
  <div class="stat-card"><div class="stat-num">{total}</div><div class="stat-label">总字库</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#059669">{learned}</div><div class="stat-label">已认识</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#dc2626">{p['untouched']}</div><div class="stat-label">未学</div></div>
  <div class="stat-card"><div class="stat-num" style="color:#7c3aed">{p['total_books']}</div><div class="stat-label">书籍</div></div>
</div>

<div class="section">
  <div class="section-title">🏆 高频未学</div>
  <div class="card"><div class="cloud">{cloud_html}</div></div>
</div>

<div class="section">
  <div class="section-title">✅ 已认识 ({len(learned_chars)})</div>
  <div class="card"><div class="wall">{wall_html}</div></div>
</div>

<div class="section">
  <div class="section-title">📝 最近学习</div>
  <div class="card">{log_html}</div>
</div>

<div class="section">
  <div class="section-title">📚 绘本书库 ({p['total_books']})</div>
  <div class="card">{book_html}</div>
</div>

<div class="footer">每天 10:00 自动更新 · 数据来自息流</div>
</body></html>"""
    return html


def generate_data_json(bank):
    data = {"version": 1, "last_updated": bank.get("last_updated", ""), "progress": bank["progress"]}
    return json.dumps(data, ensure_ascii=False, indent=2)


def generate_learned_json(bank):
    chars = bank["chars"]
    learned = [{"char": c, "date": info.get("learned_date", "")}
               for c, info in sorted(chars.items()) if info["status"] == "已学"]
    return json.dumps({"last_updated": bank.get("last_updated", ""), "learned": learned},
                      ensure_ascii=False, indent=2)


def generate_char_meta_json(bank):
    return json.dumps({
        "last_updated": bank.get("last_updated", ""),
        "total_chars": len(bank["chars"]),
        "chars": bank["chars"]
    }, ensure_ascii=False, indent=2)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CHAR_BANK_PATH):
        print("character_bank.json not found")
        return
    with open(CHAR_BANK_PATH, "r", encoding="utf-8") as f:
        bank = json.load(f)

    with open(OUTPUT_DATA, "w", encoding="utf-8") as f:
        f.write(generate_data_json(bank))

    with open(f"{OUTPUT_DIR}/learned.json", "w", encoding="utf-8") as f:
        f.write(generate_learned_json(bank))

    with open(f"{OUTPUT_DIR}/char_meta.json", "w", encoding="utf-8") as f:
        f.write(generate_char_meta_json(bank))

    p = bank["progress"]
    print(f"data.json + learned.json + char_meta.json → {p['total_books']}本 | {p['total_unique_chars']}字 | 已学{p['learned']}")


if __name__ == "__main__":
    main()
