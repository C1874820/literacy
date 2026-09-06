#!/usr/bin/env python3
"""每周主力书单管理：周次计算 + 素材池(认字可行性筛选) + 顺延/剔除逻辑。

维护 week_roster.json（每本书进入主力的日期、未读周数、状态）。

规则（用户定）:
  - 周日人工更新「本周主力」页
  - 读完勾选 → 送回书架
  - 未勾选 → 顺延下一周
  - 连续两周未读 → 第三周剔除，从素材池补新

用法:
  python3 scripts/week_roster.py            # 计算本周 + 输出推荐书单（不写入）
  python3 scripts/week_roster.py --apply    # 更新 week_roster.json 并输出最终书单
  python3 scripts/week_roster.py --week 3   # 指定周次
  python3 scripts/week_roster.py --size 8   # 主力书单本数

周次基准: 德阳 2026-2027 秋季校历，9/1 行课周=第1周（9/1~9/6），其后每7天。
"""
import json, os, sys, datetime, urllib.request, urllib.error

BASE = os.environ.get("REX_BASE", "/mnt/d/rex")
BANK_PATH = f"{BASE}/character_bank.json"
LEARNED_PATH = f"{BASE}/progress/learned.json"
ETYMOLOGY_PATH = f"{BASE}/progress/char_etymology.json"
ROSTER_PATH = f"{BASE}/week_roster.json"
DB = "10df60aa-aee0-4727-adab-f4d99e1cc053"
ENV = f"{BASE}/.env"

WEEK1_START = datetime.date(2026, 9, 1)  # 第1周起点
WEEK_SIZE = 8  # 主力书单本数
MIN_CHARS = 30   # 素材池最低全书字数（太少无字可认）
MAX_CHARS = 200  # 素材池最高全书字数（太长不适合4-5岁）


def log(msg):
    print(msg)


def load_token():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("FLOWUS_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def api_v2(token, method, path, data=None):
    url = f"https://api.flowus.cn/v2{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def current_week(today=None):
    today = today or datetime.date.today()
    return (today - WEEK1_START).days // 7 + 1


def week_range(week):
    start = WEEK1_START + datetime.timedelta(days=(week - 1) * 7)
    end = start + datetime.timedelta(days=6)
    return start, end


def load_bank():
    return json.load(open(BANK_PATH, encoding="utf-8"))


def load_learned():
    ld = json.load(open(LEARNED_PATH, encoding="utf-8"))
    return {it["char"] for it in ld.get("learned", [])}


def load_etymology():
    if os.path.exists(ETYMOLOGY_PATH):
        return json.load(open(ETYMOLOGY_PATH, encoding="utf-8")).get("chars", {})
    return {}


def fetch_flowus_meta(token):
    """拉 FlowUs 书单：书名 → {状态, 类型, 书架}"""
    meta = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        d = api_v2(token, "POST", f"/databases/{DB}/query", body)
        for p in d.get("results", []):
            pr = p.get("properties", {})
            title = (pr.get("书名", {}).get("title") or [{}])[0].get("plain_text", "")
            status = (pr.get("状态", {}).get("select") or {}).get("name", "") if pr.get("状态", {}).get("select") else ""
            types = [o["name"] for o in pr.get("书籍类型", {}).get("multi_select", []) or []]
            shelf = (pr.get("存放位置", {}).get("select") or {}).get("name", "") if pr.get("存放位置", {}).get("select") else ""
            if title:
                meta[title] = {"status": status, "types": types, "shelf": shelf}
        if d.get("has_more") and d.get("next_cursor"):
            cursor = d["next_cursor"]
        else:
            break
    return meta


def build_material_pool(bank, learned, ety, fmeta):
    """认字可行性筛选 → 素材池（未读、非桥梁/无字、字量适中、字源可溯优先）"""
    pool = []
    for title, info in bank["books"].items():
        chars = info.get("characters", [])
        total = len(chars)
        if total < MIN_CHARS or total > MAX_CHARS:
            continue
        fm = fmeta.get(title, {})
        if fm.get("status") != "未读":
            continue
        types = fm.get("types", [])
        if "桥梁书" in types or "无字书" in types:
            continue
        unique = set(chars)
        unlearned = [c for c in unique if c not in learned]
        if not unlearned:
            continue
        # 字源可溯性：未学字中含象形/会意字（优先，配合小象汉字范式）
        ety_chars = [c for c in unlearned if ety.get(c, {}).get("type") in ("pictographic", "ideographic")]
        new_ratio = len(unlearned) / len(unique)
        pool.append({
            "title": title,
            "total": total,
            "new_ratio": round(new_ratio, 2),
            "etymo_count": len(ety_chars),
            "etymo_points": ety_chars[:5],
            "shelf": fm.get("shelf", ""),
        })
    # 排序：字源可溯优先 > 字量小（低幼优先）
    pool.sort(key=lambda r: (-r["etymo_count"], r["total"]))
    return pool


def load_roster():
    if os.path.exists(ROSTER_PATH):
        return json.load(open(ROSTER_PATH, encoding="utf-8"))
    return {"roster": [], "history": [], "last_week": 0, "last_updated": ""}


def main():
    args = sys.argv[1:]
    do_apply = "--apply" in args
    week = None
    size = WEEK_SIZE
    for a in args:
        if a.startswith("--week"):
            week = int(a.split("=", 1)[1]) if "=" in a else int(args[args.index(a) + 1])
        if a.startswith("--size"):
            size = int(a.split("=", 1)[1]) if "=" in a else WEEK_SIZE

    today = datetime.date.today()
    week = week or current_week(today)
    start, end = week_range(week)
    log(f"当前周次: 第 {week} 周（{start} ~ {end}）")

    token = load_token()
    bank = load_bank()
    learned = load_learned()
    ety = load_etymology()
    fmeta = fetch_flowus_meta(token) if token else {}
    log(f"字库 {len(bank['books'])} 本 | 已学 {len(learned)} 字 | FlowUs 元数据 {len(fmeta)} 本")

    pool = build_material_pool(bank, learned, ety, fmeta)
    log(f"素材池(认字可行性筛选后): {len(pool)} 本")

    roster = load_roster()
    roster_list = list(roster.get("roster", []))
    history = list(roster.get("history", []))

    # 1. 处理上周主力书的顺延/剔除
    next_roster = []
    removed = []
    for item in roster_list:
        title = item.get("title", "")
        fm = fmeta.get(title, {})
        status = fm.get("status", "")
        unread_weeks = item.get("unread_weeks", 0)
        if status in ("已读", "在读"):
            # 读完 → 送回书架，记录历史
            history.append({"title": title, "week_out": week, "result": "读完"})
            log(f"  ✓ 读完送回书架: {title}")
            continue
        unread_weeks += 1
        if unread_weeks >= 2:
            # 连续两周未读 → 第三周剔除
            history.append({"title": title, "week_out": week, "result": "连续两周未读剔除"})
            removed.append(title)
            log(f"  ✗ 连续两周未读，剔除: {title}")
            continue
        next_roster.append({"title": title, "entered_week": item.get("entered_week", week - unread_weeks),
                            "unread_weeks": unread_weeks})
        log(f"  → 顺延: {title}（未读 {unread_weeks} 周）")

    # 2. 从素材池补新，补满 size
    existing_titles = {i["title"] for i in next_roster}
    for p in pool:
        if len(next_roster) >= size:
            break
        if p["title"] in existing_titles:
            continue
        next_roster.append({"title": p["title"], "entered_week": week, "unread_weeks": 0})
        log(f"  + 补新: {p['title']}")

    # 3. 输出结果
    log(f"\n本周主力书单（{len(next_roster)} 本）:")
    for i, item in enumerate(next_roster):
        title = item["title"]
        info = bank["books"].get(title, {})
        pts = ety.get(title) or {}
        log(f"  {i+1}. {title}（进入第{item['entered_week']}周，未读{item['unread_weeks']}周）")

    if do_apply:
        roster = {"roster": next_roster, "history": history,
                  "last_week": week,
                  "last_updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")}
        json.dump(roster, open(ROSTER_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"\n已写 week_roster.json（第{week}周）")
    else:
        log("\n（未 --apply，未写入）")


if __name__ == "__main__":
    main()
