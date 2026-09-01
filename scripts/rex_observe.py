#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rex 观察记录本地整理工具。
检测 rex观察记录/ 目录中周观察记录文件里带"待本地模型整理"占位的原始记录，
调用本地 Ollama 模型整理（通顺、删口语），在原文件内追加"整理"区并保留原始稿。

用法:
  rex_observe.py once         单次扫描当前未整理的记录
  rex_observe.py watch [秒]   轮询监听（配合 systemd long-running）
  rex_observe.py show         查看所有未整理记录
"""
import os, re, sys, time, json, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ollama_host import generate_url as ollama_url  # noqa: E402

OBS_DIR = "/mnt/d/Onedrive/个人仓库/01_Areas/孩子成长/rex观察记录"
MODEL = "qwen3:0.6b"
PLACEHOLDER = "（待本地模型整理）"

SYSTEM_PROMPT = (
    "你是一名幼儿观察记录整理助手。用户会给你一段由家长手机语音转文字得到的、"
    "记录儿童（Rex，4岁）日常行为的原始口语稿。请将它整理成通顺、客观、"
    "保留关键细节的书面观察记录：理顺语序、去掉口头禅和重复、保留时间地点人物事件、"
    "对儿童行为做中性描述（不评判、不贴标签）。"
    "直接输出整理后的正文，不要加标题、不要加解释、不要加问候语。"
)


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def ollama(prompt, system=SYSTEM_PROMPT):
    payload = {
        "model": MODEL,
        "prompt": f"{system}\n\n{'-'*20}\n{prompt}",
        "stream": False,
        "options": {"temperature": 0.3},
    }
    req = urllib.request.Request(
        ollama_url(),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["response"].strip()


def find_unprocessed():
    """返回 [(path, [(header, raw)])]，找出所有待整理的记录段。"""
    results = []
    if not os.path.isdir(OBS_DIR):
        return results
    for fn in sorted(os.listdir(OBS_DIR)):
        if not fn.endswith("观察记录.md") and not ("观察记录" in fn and fn.endswith(".md")):
            continue
        path = os.path.join(OBS_DIR, fn)
        text = read_file(path)
        # 每个 #### 段；找含占位符的
        blocks = re.split(r"(?m)^(?=#### )", text)
        for blk in blocks:
            if PLACEHOLDER in blk:
                title = blk.split("\n", 1)[0].strip() if blk.strip().startswith("####") else fn
                raw_m = re.search(r"\*\*原始记录\*\*：(.+?)(?=\n\*\*整理\*\*|\Z)", blk, re.S)
                if raw_m and raw_m.group(1).strip():
                    results.append((path, title, raw_m.group(1).strip()))
    return results


def process_one(path, title, raw):
    digested = ollama(raw)
    text = read_file(path)
    if PLACEHOLDER not in text:
        return
    # 替换 `-？（待本地模型整理）` 或 `（待本地模型整理）`，保留去除破折号
    pat = re.compile(r"[\-－]?\s*" + re.escape(PLACEHOLDER))
    new_text, n = pat.subn(digested, text, count=1)
    if n == 0:
        new_text = text.replace(PLACEHOLDER, digested, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return digested


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "once"
    interval = float(args[1]) if len(args) > 1 and mode == "watch" else 30.0

    if mode == "show":
        items = find_unprocessed()
        if not items:
            print("无未整理记录")
        for path, title, raw in items:
            print(f"== {os.path.basename(path)} | {title}")
            print(raw[:120], "...")
        return

    if mode == "once":
        items = find_unprocessed()
        for path, title, raw in items:
            d = process_one(path, title, raw)
            if d:
                print(f"整理完成: {os.path.basename(path)} | {title}\n  {d[:80]}...")
        return

    if mode == "watch":
        print(f"[watch] 监听 {OBS_DIR}，每 {interval}s 扫描")
        while True:
            try:
                items = find_unprocessed()
                for path, title, raw in items:
                    try:
                        d = process_one(path, title, raw)
                        if d:
                            print(f"整理完成: {os.path.basename(path)} | {title}\n  {d[:80]}...")
                    except Exception as e:
                        print(f"整理失败 {os.path.basename(path)} {title}: {e}")
            except Exception as e:
                print(f"扫描异常: {e}")
            time.sleep(interval)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
