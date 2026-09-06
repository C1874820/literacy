#!/usr/bin/env python3
"""生成并写入 FlowUs「本周主力」页（识字计划用）。

数据流: week_roster.json（主力书单） → 生成 markdown → flowus markdown put 写入。

用法:
  python3 scripts/update_weekly_focus.py              # 生成+写入当前周
  python3 scripts/update_weekly_focus.py --week 3     # 指定周次
  python3 scripts/update_weekly_focus.py --dry-run    # 只打印 markdown，不写入

依赖:
  - week_roster.json（先跑 week_roster.py --apply）
  - .env 的 FLOWUS_TOKEN
  - flowus CLI（flowus markdown put）
"""
import json, os, sys, subprocess, datetime, urllib.request

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
    return (today - WEEK1_START).days // 7 + 1


def week_range(week):
    start = WEEK1_START + datetime.timedelta(days=(week - 1) * 7)
    return start, start + datetime.timedelta(days=6)


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
    lines.append(f"# 本周主力 · {start} 起（第 {week} 周）")
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
    log(md)

    if dry:
        log("\n[--dry-run] 未写入 FlowUs")
        return

    if not token:
        log("\nERROR: FLOWUS_TOKEN 未设置，跳过写入")
        return

    # 写临时 markdown 文件，用 flowus CLI markdown put 写入
    tmp = f"{BASE}/_weekly_focus_tmp.md"
    open(tmp, "w", encoding="utf-8").write(md)
    try:
        r = subprocess.run(["flowus", "markdown", "put", "--file", tmp, PAGE_ID],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            log(f"\n✅ 已写入本周主力页（第{week}周）")
        else:
            log(f"\n⚠ 写入可能失败: {r.stderr.strip() or r.stdout.strip()}")
    except FileNotFoundError:
        log("\nERROR: flowus CLI 未找到，请确认已安装")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == "__main__":
    main()
