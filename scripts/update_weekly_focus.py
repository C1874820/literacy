#!/usr/bin/env python3
"""生成并写入 FlowUs「本周主力」页（识字计划用）。

数据流: week_roster.json（主力书单） → 生成 markdown → 合并页内手工 [x] 记录 → 整页重写（FlowUs v2 API，stdlib）。

写入策略（幂等，每工作日 cron 重跑安全）:
  1. 读回现有页 markdown，把手工勾选的 [x] 记录并入新周次内容
  2. 与现有内容归一化比对，一致则跳过写入
  3. 不一致时先追加新块、再删旧块（append-then-delete，避免出现空页窗口）

用 flowus v2 HTTP API 而非 flowus CLI：CLI 的 `markdown put` 服务端未实现（404），
且 cron 环境 PATH 不含 ~/.npm-global/bin；纯 stdlib 走 urllib 无此依赖。

用法:
  python3 scripts/update_weekly_focus.py              # 生成+写入当前周
  python3 scripts/update_weekly_focus.py --week 3     # 指定周次
  python3 scripts/update_weekly_focus.py --dry-run    # 只打印 markdown，不写入

依赖:
  - week_roster.json（先跑 week_roster.py --apply）
  - .env 的 FLOWUS_TOKEN
"""
import json, os, re, sys, datetime, urllib.request

BASE = os.environ.get("REX_BASE", "/mnt/d/rex")
BANK_PATH = f"{BASE}/character_bank.json"
LEARNED_PATH = f"{BASE}/progress/learned.json"
ETYMOLOGY_PATH = f"{BASE}/progress/char_etymology.json"
ROSTER_PATH = f"{BASE}/week_roster.json"
ENV = f"{BASE}/.env"
PAGE_ID = "d14aa902-707b-4b1b-b443-0eaa15ed4cd6"  # 本周主力页

WEEK1_START = datetime.date(2026, 9, 1)


def log(msg):
    print(msg)


def load_token():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("FLOWUS_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def current_week(today=None):
    today = today or datetime.date.today()
    days = (today - WEEK1_START).days
    # 第一周只有6天（9/1~9/6），之后每7天一周
    return (days + 1) // 7 + 1


def week_range(week):
    # 第一周 9/1~9/6（6天，周一~周六），之后每7天（周一~周日）
    if week == 1:
        start = WEEK1_START
        end = start + datetime.timedelta(days=5)
    else:
        start = WEEK1_START + datetime.timedelta(days=6 + (week - 2) * 7)
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


# 抽象虚词/结构词：幼儿识字优先具体名物，规避这些
ABSTRACT = set("的了是在有和就都很也把被从为以之者这那又还到么吧啊呢与或而于及其等却但并对要会可上用不中大")
# 具象字：常见幼儿名物/动词（具体可指认，多为象形/会意直观字）
CONCRETE = set("日月山水木火土田鸟虫鱼花草猫狗马牛羊兔熊虎龙风车书门窗床桌饭面米肉瓜果桃梨杏枣树屋家人母女兄弟宝贝爸妈爷奶手脚口耳目身心")


def pick_points(chars, learned, freq):
    """认字点：未学 + 具体名物字优先 + 规避抽象虚词 + 高频排序"""
    unlearned = [c for c in chars if c not in learned]
    concrete = [c for c in unlearned if c in CONCRETE]
    normal = [c for c in unlearned if c not in ABSTRACT and c not in CONCRETE]
    concrete.sort(key=lambda c: -freq.get(c, 0))
    normal.sort(key=lambda c: -freq.get(c, 0))
    return (concrete + normal)[:4]


def build_markdown(week, roster_items, bank, learned, ety, freq):
    start, end = week_range(week)
    lines = []
    lines.append(f"# 本周主力 · 第{week}周（{start.month}/{start.day}~{end.month}/{end.day}）")
    lines.append("")
    lines.append("> 💡 年度目标 300-400 字 · 每晚读 1-2 本，C 位封面朝外摆放，每周日轮换。")
    lines.append("")
    lines.append("## 本周 C 位书单")
    lines.append("")
    for item in roster_items:
        title = item["title"]
        info = bank["books"].get(title, {})
        chars = info.get("characters", [])
        pts = pick_points(chars, learned, freq)
        pts_str = "、".join(pts) if pts else "待提取"
        unread = item.get("unread_weeks", 0)
        tag = f"（顺延第{unread}周）" if unread > 0 else "（新加入）"
        lines.append(f"- [ ] {title}｜认字点：{pts_str} {tag}")
        lines.append("")
    lines.append("## 生活场景认字")
    lines.append("")
    lines.append("- [ ] 生活场景认字：（本周如发生生活场景认字，记录在此行）")
    lines.append("")
    lines.append("## 周记录指南")
    lines.append("")
    lines.append("- 每晚读完：问 Rex 新认识了哪几个字，填入对应书的「认字情况」字段")
    lines.append("- 每周日：更新本页 C 位书单（读完勾选→送回书架→从素材池补新）")
    return "\n".join(lines)


CHECKED_RE = re.compile(r"^-\s*\[x\]\s*(.+?)\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
KEY_SPLIT_RE = re.compile(r"[（(｜|:：]")


def api(token, method, path, body=None, timeout=30):
    """FlowUs v2 API（纯 stdlib，不依赖 flowus CLI → cron 环境 PATH 无关）"""
    req = urllib.request.Request(
        f"https://api.flowus.cn/v2{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw else None


def get_page_markdown(token):
    """读回整页 markdown；返回 None 表示读取失败（与空页区分）"""
    try:
        data = api(token, "GET", f"/pages/{PAGE_ID}/content/markdown")
        return (data or {}).get("markdown", "") or ""
    except Exception as e:
        log(f"ERROR: 读取现有页失败: {e}")
        return None


def list_children(token, max_pages=50):
    """列出页面全部子 block（FlowUs 首页返回空 results，必须跟 next_cursor 翻页）"""
    blocks, cursor, pages = [], None, 0
    while pages < max_pages:
        path = f"/blocks/{PAGE_ID}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        data = api(token, "GET", path) or {}
        blocks += data.get("results") or []
        pages += 1
        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data["next_cursor"]
    return blocks


def md_to_blocks(md):
    """markdown → FlowUs block JSON"""
    blocks = []
    for line in md.split("\n"):
        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": line[4:]}}]}})
        elif line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": line[3:]}}]}})
        elif line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif re.match(r"^-\s*\[x\]\s", line, re.IGNORECASE):
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": line[6:]}}], "checked": True}})
        elif line.startswith("- [ ] "):
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"type": "text", "text": {"content": line[6:]}}], "checked": False}})
        elif line.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif line.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": [{"type": "text", "text": {"content": line[2:]}}]}})
        elif line.strip():
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
    return blocks


def append_blocks(token, blocks, chunk=100):
    """追加子块（FlowUs 单次上限 100）"""
    created = []
    for i in range(0, len(blocks), chunk):
        res = api(token, "PATCH", f"/blocks/{PAGE_ID}/children",
                  {"children": blocks[i:i + chunk]}, timeout=60)
        created += (res or {}).get("results") or []
    return created


def delete_blocks(token, ids):
    """删除子块（DELETE /v2/blocks/{id} → in_trash）"""
    failed = []
    for bid in ids:
        try:
            api(token, "DELETE", f"/blocks/{bid}")
        except Exception:
            failed.append(bid)
    return failed


def normalize_md(md):
    """比对用归一化：忽略空行与首尾空白差异"""
    return "\n".join(l.rstrip() for l in (md or "").split("\n") if l.strip())


def line_key(text):
    """条目匹配键：截断到第一个括号/书名分隔符/冒号之前，用于把 [x] 记录对回新周次对应行"""
    return KEY_SPLIT_RE.split(text.strip(), 1)[0].strip()


def collect_manual_checked(old_md):
    """从旧页提取手工勾选记录：{所在小节标题(无小节则为 None): [条目文本, ...]}"""
    manual, section = {}, None
    for line in old_md.split("\n"):
        h = HEADING_RE.match(line)
        if h:
            section = h.group(2).strip()
            manual.setdefault(section, [])
            continue
        m = CHECKED_RE.match(line)
        if m:
            manual.setdefault(section, []).append(m.group(1))
    return {k: v for k, v in manual.items() if v}


def merge_manual_checked(md, manual):
    """把旧页 [x] 记录并入新 markdown：同小节内按匹配键覆盖对应 [ ] 行；无对应行则追加到该小节末尾"""
    if not manual:
        return md, 0

    lines = md.split("\n")
    # 行索引 → 所属小节标题
    section_of, current = {}, None
    for i, line in enumerate(lines):
        h = HEADING_RE.match(line)
        if h:
            current = h.group(2).strip()
        section_of[i] = current

    # 小节 → 该小节的行号（用于追加）
    idx_by_section = {}
    for i, sec in section_of.items():
        idx_by_section.setdefault(sec, []).append(i)

    merged = 0
    for sec, items in manual.items():
        for text in items:
            key = line_key(text)
            target_idx = None
            if key:
                for i, line in enumerate(lines):
                    if section_of[i] != sec:
                        continue
                    m = re.match(r"^-\s*\[( |x|X)\]\s*(.+?)\s*$", line)
                    if m and line_key(m.group(2)) == key:
                        target_idx = i
                        break
            if target_idx is not None:
                lines[target_idx] = f"- [x] {text}"
            else:
                # 手工新增行（新周次书单里没有）：追加到同小节末尾；小节不存在则追加到文末
                anchor = idx_by_section.get(sec)
                pos = max(anchor) + 1 if anchor else len(lines)
                lines.insert(pos, f"- [x] {text}")
                if pos + 1 < len(lines) and lines[pos + 1].strip():
                    lines.insert(pos + 1, "")
                lines, section_of, idx_by_section = rebuild_sections(lines)
            merged += 1
    return "\n".join(lines), merged


def rebuild_sections(lines):
    section_of, current, idx_by_section = {}, None, {}
    for i, line in enumerate(lines):
        h = HEADING_RE.match(line)
        if h:
            current = h.group(2).strip()
        section_of[i] = current
        idx_by_section.setdefault(current, []).append(i)
    return lines, section_of, idx_by_section


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    week = None
    for i, a in enumerate(args):
        if a.startswith("--week"):
            week = int(a.split("=", 1)[1]) if "=" in a else int(args[i + 1])

    week = week or current_week()
    token = load_token()

    if not os.path.exists(ROSTER_PATH):
        log("ERROR: week_roster.json 不存在，请先跑 week_roster.py --apply")
        return
    roster = json.load(open(ROSTER_PATH, encoding="utf-8"))
    roster_items = roster.get("roster", [])
    if not roster_items:
        log("ERROR: week_roster.json 书单为空")
        return

    bank = load_bank()
    learned = load_learned()
    ety = load_etymology()
    freq = {c: v.get("freq", 0) for c, v in bank["chars"].items()}

    md = build_markdown(week, roster_items, bank, learned, ety, freq)

    if dry:
        log(md)
        log("\n[--dry-run] 未写入 FlowUs")
        return

    if not token:
        log("\nERROR: FLOWUS_TOKEN 未设置，跳过写入")
        return

    # 1) 读回现有页，保留手工勾选记录（重写会覆盖，必须先合并）
    old_md = get_page_markdown(token)
    if old_md is None:
        log("ERROR: 读不到现有页内容，为避免覆盖手工记录，本次不写入")
        return
    manual = collect_manual_checked(old_md)
    if manual:
        md, merged = merge_manual_checked(md, manual)
        log(f"合并手工勾选记录 {merged} 条: " +
            " / ".join(t for items in manual.values() for t in items))
    log(md)

    # 2) 幂等：内容无变化则不碰页面
    if normalize_md(old_md) == normalize_md(md):
        log(f"\n✅ 页面内容已与第{week}周一致，跳过写入")
        return

    # 3) 先追加新块，再删旧块（append-then-delete：任何一步失败都不会留下空页）
    old_ids = [b.get("id") for b in list_children(token) if b.get("id")]
    new_blocks = md_to_blocks(md)
    if not new_blocks:
        log("\nWARN: 无 block 内容可写入")
        return
    try:
        created = append_blocks(token, new_blocks)
    except Exception as e:
        log(f"\nERROR: 追加新块失败，原页未改动: {e}")
        return
    if not created:
        log(f"\nERROR: 追加返回 0 个块，原页未改动: {len(new_blocks)}")
        return
    log(f"已追加新块 {len(created)}/{len(new_blocks)}")

    failed = delete_blocks(token, old_ids)
    if failed:
        log(f"\n⚠ 新内容已写入，但 {len(failed)} 个旧块删除失败（页面会有重复内容），需手动清理: {failed}")
    else:
        log(f"\n✅ 已整页重写本周主力页（第{week}周 {md.splitlines()[0][2:]}），清理旧块 {len(old_ids)} 个")


if __name__ == "__main__":
    main()
