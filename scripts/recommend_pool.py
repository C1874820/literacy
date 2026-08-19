#!/usr/bin/env python3
"""
素材池推荐 + 月度统计（双池：巩固池/初学池，每本输出认字点 3-5 字）

用法:
  python3 scripts/recommend_pool.py            # 输出到控制台
  python3 scripts/recommend_pool.py --write    # 额外写 progress/素材池推荐.md
  python3 scripts/recommend_pool.py --json     # 额外输出 JSON（供其他脚本消费）

数据源:
  - character_bank.json  : 字库（books/chars）
  - progress/learned.json: 已学字（权威）
  - FlowUs 阅读记录库    : 状态(在读/已读/未读)、存放位置
目标: 月均 25-35 字 / 周均 6-8 字
"""
import json, os, sys, datetime, urllib.request, urllib.error

BASE = "/mnt/d/rex-识字系统"
BANK = f"{BASE}/character_bank.json"
LEARNED = f"{BASE}/progress/learned.json"
OUT = f"{BASE}/progress/素材池推荐.md"
DB = "10df60aa-aee0-4727-adab-f4d99e1cc053"
TOKEN = os.environ.get("FLOWUS_TOKEN")
MONTH_TARGET = (25, 35)
WEEK_TARGET = (6, 8)
SUGGEST_N = 15

learned = set()
learned_dates = {}
if os.path.exists(LEARNED):
    ld = json.load(open(LEARNED, encoding="utf-8"))
    for it in ld.get("learned", []):
        learned.add(it["char"])
        if it.get("date"):
            learned_dates.setdefault(it["char"], it["date"])


def flowus_books():
    if not TOKEN:
        return {}
    def api(method, path, data=None):
        url = f"https://api.flowus.cn/v1{path}"
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
                   "Notion-Version": "2022-06-28"}
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    out = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        d = api("POST", f"/databases/{DB}/query", body)
        for p in d.get("results", []):
            props = p.get("properties", {})
            tr = props.get("title") or {}
            t = "".join(x.get("plain_text", "") for x in tr.get(tr.get("type", "title"), []))
            status = (props.get("状态", {}).get("select") or {}).get("name", "")
            shelf = (props.get("存放位置", {}).get("select") or {}).get("name", "")
            out[t] = {"status": status, "shelf": shelf}
        if d.get("has_more") and d.get("next_cursor"):
            cursor = d["next_cursor"]
        else:
            break
    return out


def monthly_stats():
    """按月统计新增识字量"""
    months = {}
    for ch, dt in learned_dates.items():
        m = dt[:7]
        months.setdefault(m, []).append(ch)
    rows = sorted(months.items())
    if not rows:
        return "暂无已学字日期记录"
    lines = ["| 月份 | 新增字数 | 目标(25-35) | 达标 |", "|---|---|---|---|"]
    for m, chs in rows:
        n = len(chs)
        hit = "✅" if MONTH_TARGET[0] <= n <= MONTH_TARGET[1] else ("⬆️超" if n > MONTH_TARGET[1] else "⬇️不足")
        lines.append(f"| {m} | {n} | {MONTH_TARGET[0]}-{MONTH_TARGET[1]} | {hit} |")
    lines.append(f"\n累计已学: **{len(learned)}** 字 / 年度目标 300-400 字")
    return "\n".join(lines)


# 抽象虚词/结构词：幼儿识字优先具体名物，规避这些
ABSTRACT = set("的了是在有和就都很也把被从为以之者这那又还到么吧啊呢与或而于及其等却但并对要会可上用不中大")
# 具象字加分：常见幼儿名物/动词（具体可指认）
CONCRETE = set("日月山水木火土田鸟虫鱼花草猫狗马牛羊兔熊虎龙风车书门窗床桌饭面米肉瓜果桃梨杏枣桃树屋家人母女兄弟宝贝宝宝猫猫狗狗")


def pick_points(chars, n=4):
    """认字点：未学 + 优先具体形象字，其次全局高频，规避抽象虚词"""
    bank = json.load(open(BANK, encoding="utf-8"))
    freq = {c: v.get("freq", 0) for c, v in bank["chars"].items()}
    cands = [c for c in chars if c not in learned and c in freq]
    concrete = [c for c in cands if c in CONCRETE]
    normal = [c for c in cands if c not in ABSTRACT and c not in CONCRETE]
    concrete.sort(key=lambda c: -freq[c])
    normal.sort(key=lambda c: -freq[c])
    return (concrete + normal)[:n]


def recommend():
    bank = json.load(open(BANK, encoding="utf-8"))
    books = bank["books"]
    fb = flowus_books()
    # 合并 FlowUs 状态（无则视作未读）
    rows = []
    for t, info in books.items():
        chars = info.get("characters", [])
        st = fb.get(t, {}).get("status", "未读")
        shelf = fb.get(t, {}).get("shelf", "")
        rows.append({"title": t, "chars": chars, "total": len(chars),
                     "status": st, "shelf": shelf})

    # 巩固池：已学字覆盖度最高（在读/已读优先）
    def cov(r):
        hit = len(set(r["chars"]) & learned)
        return hit
    consol = sorted(rows, key=lambda r: (-cov(r), -r["total"]))
    consol = [r for r in consol if cov(r) > 0][:SUGGEST_N]

    # 初学池：未学 + 总字数少 + 高频密度高
    freq = {c: v.get("freq", 0) for c, v in bank["chars"].items()}
    def density(r):
        new_chars = [c for c in r["chars"] if c not in learned]
        if not new_chars:
            return 0
        avg_freq = sum(freq.get(c, 0) for c in new_chars) / len(new_chars)
        return avg_freq / max(r["total"], 1)
    fresh = [r for r in rows if r["status"] == "未读" and r["total"] > 0]
    fresh.sort(key=lambda r: (-density(r), r["total"]))
    fresh = fresh[:SUGGEST_N]

    return consol, fresh, rows


def render(consol, fresh, rows, n_books):
    bank = json.load(open(BANK, encoding="utf-8"))
    L = [f"# 素材池推荐 · {datetime.date.today()}"]
    L.append(f"\n当前已学 **{len(learned)}** 字，库内 **{n_books}** 本书有字库数据。\n")
    L.append("## 📊 月度统计（目标 25-35 字/月）\n")
    L.append(monthly_stats())
    L.append("\n---\n")
    L.append(f"## 🔁 巩固池（已学字覆盖 Top {len(consol)}，复习推荐）\n")
    L.append("| 书名 | 状态 | 书架 | 已学字覆盖 | 认字点(复习) |")
    L.append("|---|---|---|---|---|")
    for r in consol:
        hits = sorted(set(r["chars"]) & learned)
        L.append(f"| {r['title']} | {r['status']} | {r['shelf']} | {'、'.join(hits)} | — |")
    L.append(f"\n## 🌱 初学池（高频密度高、字数少，未读 Top {len(fresh)}，新学推荐）\n")
    L.append("| 书名 | 总字数 | 书架 | 认字点(建议先学) |")
    L.append("|---|---|---|---|")
    for r in fresh:
        pts = pick_points(r["chars"])
        L.append(f"| {r['title']} | {r['total']} | {r['shelf']} | {'、'.join(pts)} |")
    L.append("\n---\n*每周日轮换：读完勾选 → 送回书架 → 从本池补新。认字点由全局高频统计自动生成。*")
    return "\n".join(L)


def main():
    consol, fresh, rows = recommend()
    n_books = len([r for r in rows if r["total"] > 0])
    md = render(consol, fresh, rows, n_books)
    print(md)
    if "--write" in sys.argv:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n[已写入] {OUT}")
    if "--json" in sys.argv:
        out = {"learned": sorted(learned),
               "consolidation": [{"title": r["title"], "learned_hits": sorted(set(r["chars"]) & learned),
                                  "status": r["status"], "shelf": r["shelf"]} for r in consol],
               "fresh": [{"title": r["title"], "total": r["total"], "shelf": r["shelf"],
                          "points": pick_points(r["chars"])} for r in fresh]}
        print("\n" + json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()