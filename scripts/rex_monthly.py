#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rex 月度观察报告生成。每月初聚合 rex观察记录/ 中上一月的所有周观察记录，
调用本地 Ollama 生成月度报告，写入 `YY年-幼儿园-M月-月度报告.md`。
无上月记录则跳过。生成后打印"是否移动脚本"提示。

用法:
  rex_monthly.py          按当前日期生成上月报告（手动/定时）
  rex_monthly.py 2026 8   指定年月生成（2026-08 的报告）
"""
import os, re, sys, json, urllib.request, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ollama_host import generate_url as ollama_url  # noqa: E402

OBS_DIR = "/mnt/d/Onedrive/个人仓库/01_Areas/孩子成长/rex观察记录"
SCRIPTS_DIR = "/mnt/d/rex-识字系统/scripts"
MODEL = "qwen3:0.6b"

REPORT_SYSTEM = (
    "你是幼儿教育观察的月度总结助手。给你指定月份（学年/校历）内多条对儿童（Rex，4岁）"
    "的观察记录，请综合提炼成一份月度报告，包含四个部分：\n"
    "1. 本月闪光点（做得好的、值得表扬的成长）\n"
    "2. 解决方法值得优化的（处理问题的做法哪里可以改进）\n"
    "3. 性格特性（本月观察到的性格/行为特点，中性描述不评判）\n"
    "4. 下月要做的（可执行的建议）\n"
    "用中文、条目式（每条用 - 开头）。客观、具体、引用事件，不虚构。"
)


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def ollama(prompt, system):
    payload = {
        "model": MODEL,
        "prompt": f"{system}\n\n{'-'*20}\n{prompt}",
        "stream": False,
        "options": {"temperature": 0.3},
    }
    req = urllib.request.Request(
        ollama_url(), data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["response"].strip()


def current_target():
    """返回要生成报告的年月（默认上月）。"""
    today = datetime.date.today()
    first_this = today.replace(day=1)
    last_month = first_this - datetime.timedelta(days=1)
    return last_month.year, last_month.month


# 德阳市2026-2027秋季学期校历：第1周从2026-09-01(周二)起，连续20周
SEMESTER_START = datetime.date(2026, 9, 1)
SEMESTER_WEEKS = 20


def week_dates(week_no):
    """返回第X周对应的起止日期区间 [start, end]。
    week_no 从1开始；按德阳2026-2027秋季校历：第1周=2026-09-01(周二)~09-06(周日)，
    其后每周周一~周日，共20周。"""
    if week_no == 1:
        start = SEMESTER_START
        end = SEMESTER_START + datetime.timedelta(days=5)
    else:
        start = SEMESTER_START + datetime.timedelta(days=(week_no - 1) * 7 - 1)
        end = start + datetime.timedelta(days=6)
    return start, end


def collect_month_records(year, month):
    """收集指定年月所有观察记录文本。按文件名周次→校历日期→与目标月交集过滤。"""
    pattern = re.compile(r"^(\d{2})年-幼儿园-第(\d+)周-观察记录\.md$")
    records = []
    if not os.path.isdir(OBS_DIR):
        return records
    for fn in sorted(os.listdir(OBS_DIR)):
        m = pattern.match(fn)
        if not m:
            continue
        week_no = int(m.group(2))
        s, e = week_dates(week_no)
        # 该周与目标月(int year/month)是否有交集
        sm = datetime.date(s.year, s.month, 1)
        em = datetime.date(e.year, e.month, 1)
        in_s = (s.year == year and s.month == month)
        in_e = (e.year == year and e.month == month)
        if not (in_s or in_e):
            continue
        path = os.path.join(OBS_DIR, fn)
        try:
            text = read_file(path)
        except Exception:
            continue
        records.append((fn, text))
    return records


def report_name(year, month):
    yy = f"{year:02d}" if year < 100 else str(year)[-2:]
    return f"{yy}年-幼儿园-{month}月-月度报告.md"


def main():
    args = sys.argv[1:]
    if len(args) >= 2:
        year, month = int(args[0]), int(args[1])
    else:
        year, month = current_target()

    records = collect_month_records(year, month)
    if not records:
        print(f"[{year}-{month:02d}] 无观察记录，跳过报告生成")
        return

    body = "\n\n".join(f"【{fn}】\n{text}" for fn, text in records)
    print(f"[{year}-{month:02d}] 聚合 {len(records)} 个文件，生成报告…")
    report_text = ollama(f"月份：{year}年{month}月\n\n{body}", REPORT_SYSTEM)

    out = os.path.join(OBS_DIR, report_name(year, month))
    header = f"""---
type: rex-monthly
学段: 幼儿园
月份: {year}-{month:02d}
学年: {year}年
---

# 月度报告 · {year}年-幼儿园-{month}月

"""
    with open(out, "w", encoding="utf-8") as f:
        f.write(header + report_text + "\n")
    print(f"报告已生成: {out}")
    print()
    print("== 是否移动脚本？ ==")
    print(f"当前观察记录脚本位于识字系统目录 {SCRIPTS_DIR}/，与识字/FlowUs 业务耦合。")
    print("若观察记录系统独立成长（模板/监听/报告自成一体），建议移至独立目录管理；")
    print("若暂共用识字系统基础设施（如 cron/systemd 习惯），可保持现状。请按需决定。")


if __name__ == "__main__":
    main()
