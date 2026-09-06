#!/usr/bin/env python3
"""生成 progress/char_etymology.json —— 每个字的字源（象形/会意/形声 + 中文造字提示）。

数据源: Make Me a Hanzi 的 dictionary.txt（MIT 许可，9000+ 常用字）
  https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt

用法:
  python3 scripts/build_etymology.py               # 下载(如缺) + 解析 + 翻译 hint + 写 JSON
  python3 scripts/build_etymology.py --no-translate # 只解析，不翻译（hint 保留英文）
  python3 scripts/build_etymology.py --model qwen2.5:7b

输出: progress/char_etymology.json
  每字: { type(pictographic/ideographic/pictophonetic), type_cn, hint_cn, hint_en,
          pinyin, definition, radical }
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("REX_BASE", "/mnt/d/rex")
BANK_PATH = f"{BASE}/character_bank.json"
DATA_DIR = f"{BASE}/data/makemeahanzi"
DICT_PATH = f"{DATA_DIR}/dictionary.txt"
DICT_URL = "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt"
OUT_PATH = f"{BASE}/progress/char_etymology.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
AUTH_FILE = os.path.expanduser("~/.local/share/opencode/auth.json")

TYPE_CN = {"pictographic": "象形字", "ideographic": "会意字", "pictophonetic": "形声字"}
# 翻译优先级：象形+会意优先（有确定 hint），形声其次
PRIORITY = {"pictographic": 0, "ideographic": 0, "pictophonetic": 1}


def deepseek_key():
    try:
        return json.load(open(AUTH_FILE, encoding="utf-8")).get("deepseek", {}).get("key")
    except Exception:
        return None


def log(msg):
    print(msg)


def download_dict():
    if os.path.exists(DICT_PATH) and os.path.getsize(DICT_PATH) > 1000000:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    log("下载 dictionary.txt ...")
    req = urllib.request.Request(DICT_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    open(DICT_PATH, "wb").write(data)
    log(f"  已保存 {len(data)} bytes")


def load_bank_chars():
    bank = json.load(open(BANK_PATH, encoding="utf-8"))
    return bank["chars"]


def parse_dict(bank_chars):
    rows = {}
    for ln in open(DICT_PATH, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        d = json.loads(ln)
        c = d.get("character", "")
        if len(c) != 1 or c not in bank_chars:
            continue
        e = d.get("etymology")
        entry = {
            "type": None, "type_cn": None,
            "hint_en": None, "hint_cn": None,
            "pinyin": d.get("pinyin", []),
            "definition": d.get("definition", ""),
            "radical": d.get("radical", ""),
        }
        if e:
            t = e.get("type")
            entry["type"] = t
            entry["type_cn"] = TYPE_CN.get(t, t)
            entry["hint_en"] = e.get("hint")
            if t == "pictophonetic":
                # 形声：声旁+形旁拼说明
                sem = e.get("semantic")
                pho = e.get("phonetic")
                if not entry["hint_en"] and (sem or pho):
                    entry["hint_en"] = ("meaning from " + sem if sem else "") + \
                        (" (sound from " + pho + ")" if pho else "")
        rows[c] = entry
    return rows


def translate_hints(rows, model):
    """批量翻译 hint_en → hint_cn。优先 DeepSeek（快准），无 key 回退本地 Ollama。"""
    todo = [(c, r) for c, r in rows.items()
            if r.get("hint_en") and not r.get("hint_cn")]
    todo.sort(key=lambda x: (PRIORITY.get(x[1]["type"], 2), x[0]))
    if not todo:
        return 0
    log(f"待翻译 {len(todo)} 字（hint 英文→中文）...")
    key = deepseek_key()
    backend = "deepseek" if key else model
    batch_size = 60
    done = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        items = {c: r["hint_en"] for c, r in batch}
        prompt = ("把下列每个汉字对应的英文造字提示翻译成简短、形象的中文短语，"
                  "用来说明这个字的来源（它本来像什么/怎么造出来的），适合讲给幼儿听。"
                  "键（汉字）保持不变，只翻译值。只输出 JSON 对象，不要解释、不要保留英文。\n"
                  + json.dumps(items, ensure_ascii=False))
        result = _call_translate(backend, key, prompt)
        if result:
            for c, hint in result.items():
                if c in rows and isinstance(hint, str) and hint.strip():
                    rows[c]["hint_cn"] = hint.strip()
                    done += 1
        log(f"  [{min(i + batch_size, len(todo))}/{len(todo)}] 已译 {done} 字")
        time.sleep(0.3)
    return done


def _call_translate(backend, key, prompt):
    if backend == "deepseek":
        body = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "你是汉字字源翻译器，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        try:
            req = urllib.request.Request(
                DEEPSEEK_URL, data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=300) as r:
                content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            return _parse_json(content)
        except Exception as e:
            log(f"  ⚠ DeepSeek 翻译失败: {e}")
            return None
    else:
        body = {
            "model": backend,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as r:
                content = json.loads(r.read().decode()).get("message", {}).get("content", "")
            return _parse_json(content)
        except Exception as e:
            log(f"  ⚠ 本地翻译失败: {e}")
            return None


def _parse_json(content):
    if not isinstance(content, str):
        return None
    content = content.strip()
    # 去掉可能的 ```json 包裹
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        return json.loads(content)
    except Exception:
        # 尝试截取第一个 { 到最后一个 }
        a, b = content.find("{"), content.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(content[a:b + 1])
            except Exception:
                return None
    return None


def main():
    args = sys.argv[1:]
    translate = "--no-translate" not in args
    model = OLLAMA_MODEL
    for a in args:
        if a.startswith("--model"):
            model = a.split("=", 1)[1] if "=" in a else OLLAMA_MODEL

    download_dict()
    bank_chars = load_bank_chars()
    rows = parse_dict(bank_chars)
    log(f"字库 ∩ 字源库: {len(rows)} 字")

    n_hint = sum(1 for r in rows.values() if r.get("hint_en"))
    log(f"  含字源提示: {n_hint} 字")

    if translate and n_hint:
        done = translate_hints(rows, model)
        log(f"翻译完成: {done} 字")

    out = {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Make Me a Hanzi (MIT)",
        "total": len(rows),
        "chars": rows,
    }
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 统计
    from collections import Counter
    c = Counter(r.get("type") for r in rows.values() if r.get("type"))
    log(f"已写 {OUT_PATH}: {len(rows)} 字 | 类型分布 {dict(c)}")


if __name__ == "__main__":
    main()
