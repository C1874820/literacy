#!/usr/bin/env python3
"""补齐 FlowUs「Rex阅读记录」缺失元数据：适合年龄/系列/作者/认字字数/存放位置。
用法:
  python3 scripts/fill_book_meta.py            # 完整流程（推断+写入）
  python3 scripts/fill_book_meta.py --infer    # 只做推断，输出到 /tmp/opencode/*.json
  python3 scripts/fill_book_meta.py --apply    # 只用已有推断结果写入
依赖:
  - .env 的 FLOWUS_TOKEN
  - ~/.local/share/opencode/auth.json 的 deepseek.key（无则跳过推断）
字段决策:
  - 只补元数据，不补过程字段（读后感/读完日期/认字情况）——避免伪造阅读数据
  - 作者只填高置信度（DeepSeek 明确返回 + 已知确定作者），未知留空防编造
  - 系列只填 FlowUs 已有选项；新系列需在 UI 手动加选项（API 不支持改 select options）
  - 认字字数从认字情况解析（顿号分隔）
注意:
  - 用 V2 API 写入（V1 的 number 字段 PATCH 有 bug 报 "Invalid rich_text"）
  - FlowUs 空字段被 API 省略，统计时"字段不存在=空"
"""
import json, os, sys, time, urllib.request, urllib.error
from collections import Counter

BASE = "/mnt/d/rex"
DB = "10df60aa-aee0-4727-adab-f4d99e1cc053"
ENV = f"{BASE}/.env"
AUTH = os.path.expanduser("~/.local/share/opencode/auth.json")
WORK = "/tmp/opencode"

def load_token():
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("FLOWUS_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("FLOWUS_TOKEN not found in .env")

def api_v2(token, method, path, data=None):
    url = f"https://api.flowus.cn/v2{path}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http_error": e.code, "body": e.read().decode()[:300]}

def deepseek_key():
    if not os.path.exists(AUTH):
        return None
    try:
        return json.load(open(AUTH)).get("deepseek", {}).get("key")
    except Exception:
        return None

def llm(key, system, user, temp=0.1):
    body = {"model": "deepseek-chat",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temp,
            "response_format": {"type": "json_object"}}
    req = urllib.request.Request("https://api.deepseek.com/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"},
                                 method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                content = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            if isinstance(content, str):
                return json.loads(content)
            return content
        except Exception as e:
            print(f"  [重试{attempt+1}] {e}")
            time.sleep(4)
    return None

EXISTING_SERIES = {"布鲁斯系列","巫婆奶奶系列","建筑师的大创造","青蛙和蟾蜍","大野狼系列",
    "宫西达也恐龙系列","深见春夫系列","吉竹伸介系列","卡尔系列","帮帮机器人","野猫军团",
    "不可思议的旅程","安格斯系列","大灰狼咕噜","有时候我可以","思考世界的孩子",
    "藏在地图里的中国历史","走进艺术","超级乌龟兔子","写给亲爱的","大象巴巴","洛克数学启蒙",
    "卡蜜儿情商社交","小兔汤姆","四季时光","五味太郎启蒙","这里是新疆","探索火山深海",
    "一年四季","西游记绘本","有了...你怎么做","德国精选科学图画书","雷切尔·布莱特系列",
    "郝广才系列","欧尼科夫系列","大卫系列"}

# 书名→已有系列 精确映射（含本次确认的新系列归属）
SERIES_BY_TITLE = {
    "野猫军团吃冰淇淋":"野猫军团","野猫军团吃咖喱饭":"野猫军团","野猫军团吃团子":"野猫军团",
    "野猫军团吃寿司":"野猫军团","野猫军团开火车":"野猫军团","野猫军团烤面包":"野猫军团",
    "野猫军团吃蛋糕":"野猫军团","野猫军团吃面包":"野猫军团",
    "巴巴和猴子们":"大象巴巴","巴巴的故事":"大象巴巴","巴巴的旅行":"大象巴巴",
    "巴巴和孩子们":"大象巴巴",
    "飞吧爸爸":"深见春夫系列","冒险泥巴球":"深见春夫系列","云朵怪兽":"深见春夫系列",
    "10只小猴加油":"五味太郎启蒙","安静的湖":"布鲁斯系列",
}

def query_all(token):
    records = []
    cursor = None
    while True:
        data = {"page_size": 100}
        if cursor:
            data["start_cursor"] = cursor
        d = api_v2(token, "POST", f"/databases/{DB}/query", data)
        records.extend(d.get("results", []))
        cursor = d.get("next_cursor")
        if not cursor:
            break
    return records

def normalize(records):
    out = []
    for r in records:
        p = r.get("properties", {})
        title = (p.get("书名", {}).get("title") or [{}])[0].get("plain_text", "")
        author = "".join(t.get("plain_text", "") for t in p.get("作者", {}).get("rich_text", [])) if p.get("作者", {}).get("rich_text") else ""
        series = (p.get("系列", {}).get("select") or {}).get("name", "") if p.get("系列", {}).get("select") else ""
        types = [o["name"] for o in p.get("书籍类型", {}).get("multi_select", []) or []]
        source = (p.get("书籍来源", {}).get("select") or {}).get("name", "") if p.get("书籍来源", {}).get("select") else ""
        shelf = (p.get("存放位置", {}).get("select") or {}).get("name", "") if p.get("存放位置", {}).get("select") else ""
        age = [o["name"] for o in p.get("适合年龄", {}).get("multi_select", []) or []]
        rz = "".join(t.get("plain_text", "") for t in p.get("认字情况", {}).get("rich_text", [])) if p.get("认字情况", {}).get("rich_text") else ""
        rz_count = p.get("认字字数", {}).get("number")
        out.append({"id": r["id"], "title": title, "author": author, "series": series,
                    "types": types, "source": source, "shelf": shelf, "age": age,
                    "rz": rz, "rz_count": rz_count})
    return out

def infer_age(key, records):
    """DeepSeek 批量推断适合年龄，返回 {书名: [区间]}"""
    if not key:
        print("[跳过] 无 deepseek key，无法推断适合年龄")
        return {}
    # 字量数据
    bank_path = f"{BASE}/character_bank.json"
    char_count = {}
    if os.path.exists(bank_path):
        bank = json.load(open(bank_path, encoding="utf-8"))
        char_count = {t: i.get("total_chars", 0) for t, i in bank["books"].items()}
    items = [{"书名": r["title"], "作者": r["author"], "类型": ",".join(r["types"]),
              "系列": r["series"], "字量": char_count.get(r["title"], 0)} for r in records]
    system = """你是儿童绘本年龄分级专家。判断每本童书适合的阅读年龄段（亲子共读/独立听读都算）。
规则：1.只从候选年龄段选 1-2 个最合适的区间；2.依据书名/作者/类型/系列/总字数（>500字偏大龄，<200字低幼）；3.只输出 JSON。"""
    user = f"候选年龄段: 3-4, 4-5, 5-6, 6-7, 7-8, 8-9。请分级:\n" + json.dumps(items, ensure_ascii=False)
    results = {}
    batches = [items[i:i+85] for i in range(0, len(items), 85)]
    for bi, batch in enumerate(batches):
        print(f"  年龄批次 {bi+1}/{len(batches)} ({len(batch)} 本)...")
        out = llm(key, system, user)
        if out:
            results.update(out)
        time.sleep(1)
    return results

def infer_series(key, records):
    """DeepSeek 识别缺失系列的归属，返回 {书名: 系列名或None}"""
    if not key:
        print("[跳过] 无 deepseek key，无法识别系列")
        return {}
    miss = [r for r in records if not r["series"]]
    titles = [r["title"] for r in miss
              if r["title"] not in SERIES_BY_TITLE]
    if not titles:
        return {}
    system = """你是儿童绘本分类专家。判断每本童书属于哪个系列。规则：1.只输出确定属于系列的；2.单本绘本/非系列输出 null；3.系列名用候选名。"""
    user = ("已知候选系列: " + json.dumps(sorted(EXISTING_SERIES), ensure_ascii=False) +
            "\n请输出 JSON {\"书名\":系列名或null}:\n" + json.dumps(titles, ensure_ascii=False))
    out = llm(key, system, user)
    if not out:
        return {}
    # 规范化：只保留候选内存在的系列名
    clean = {}
    for t, s in out.items():
        if isinstance(s, str) and s in EXISTING_SERIES:
            clean[t] = s
        else:
            clean[t] = None
    return clean

def infer_author(key, records):
    """DeepSeek 识别缺作者书名，返回 {书名: 作者}（高置信度）"""
    if not key:
        return {}
    miss = [r["title"] for r in records if not r["author"]]
    if not miss:
        return {}
    system = """你是童书目录专家。根据书名判断作者。规则：1.只输出你确信的作者名（中文译本用中文作者名）；2.不确定写"未知"；3.只输出 JSON {"书名":"作者名"}。"""
    user = json.dumps(miss, ensure_ascii=False)
    out = llm(key, system, user)
    if not out:
        return {}
    return {t: a for t, a in out.items() if a and a != "未知"}

def build_props(fields):
    props = {}
    for f, v in fields.items():
        if f == "适合年龄":
            props[f] = {"type": "multi_select", "multi_select": [{"name": a} for a in v]}
        elif f in ("系列", "存放位置"):
            props[f] = {"type": "select", "select": {"name": v}}
        elif f == "作者":
            props[f] = {"type": "rich_text", "rich_text": [{"type": "text", "text": {"content": v}}]}
        elif f == "认字字数":
            props[f] = {"type": "number", "number": v}
    return props

def build_plan(records, age, series, author):
    """生成写入计划 [(id, title, fields)]，跳过已填字段"""
    plan = []
    for r in records:
        fields = {}
        a = age.get(r["title"]) if age else None
        if a and not r["age"]:
            fields["适合年龄"] = [x for x in a if x in ("3-4","4-5","5-6","6-7","7-8","8-9")]
        s = series.get(r["title"]) if series else None
        if s and s in EXISTING_SERIES and not r["series"]:
            fields["系列"] = s
        s2 = SERIES_BY_TITLE.get(r["title"])
        if s2 and not r["series"]:
            fields["系列"] = s2
        au = author.get(r["title"]) if author else None
        if au and not r["author"]:
            fields["作者"] = au
        if r["rz"] and not r["rz_count"]:
            n = len([c for c in r["rz"].replace(" ", "").split("、") if c])
            if n > 0:
                fields["认字字数"] = n
        if not r["shelf"] and "桥梁书" in r["types"]:
            fields["存放位置"] = "6#艺术+神话/无字书/桥梁"
        if fields:
            plan.append({"id": r["id"], "title": r["title"], "fields": fields})
    return plan

def apply(token, plan):
    """V2 API 批量 PATCH，带进度断点续传"""
    progress = f"{WORK}/fill_progress.json"
    done = set(json.load(open(progress))) if os.path.exists(progress) else set()
    for p in plan:
        if p["id"] in done:
            continue
        r = api_v2(token, "PATCH", f"/pages/{p['id']}", {"properties": build_props(p["fields"])})
        if "http_error" in r:
            print(f"  FAIL {p['title']}: {r['http_error']} {r['body']}")
        else:
            done.add(p["id"])
        json.dump(list(done), open(progress, "w"))
    print(f"写入完成 {len(done)}/{len(plan)}")

def main():
    args = sys.argv[1:]
    mode_infer = "--infer" in args
    mode_apply = "--apply" in args

    token = load_token()
    print("拉取全库...")
    records = normalize(query_all(token))
    print(f"共 {len(records)} 本")

    key = deepseek_key()
    if mode_apply:
        age = json.load(open(f"{WORK}/age_result.json", encoding="utf-8"))
        series = json.load(open(f"{WORK}/series_clean.json", encoding="utf-8"))
        author = json.load(open(f"{WORK}/author_final.json", encoding="utf-8"))
    else:
        age = infer_age(key, records)
        if age:
            json.dump(age, open(f"{WORK}/age_result.json", "w", encoding="utf-8"), ensure_ascii=False)
        series = infer_series(key, records)
        if series:
            json.dump(series, open(f"{WORK}/series_clean.json", "w", encoding="utf-8"), ensure_ascii=False)
        author = infer_author(key, records)
        if author:
            json.dump(author, open(f"{WORK}/author_final.json", "w", encoding="utf-8"), ensure_ascii=False)
        if mode_infer:
            print("[--infer] 推断完成，未写入")
            return

    plan = build_plan(records, age, series, author)
    print(f"待写入 {len(plan)} 本")
    field_cnt = Counter()
    for p in plan:
        for f in p["fields"]:
            field_cnt[f] += 1
    print("字段统计:", dict(field_cnt))
    json.dump(plan, open(f"{WORK}/fill_plan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if mode_infer:
        print("[--infer] 计划已保存，未写入")
        return
    apply(token, plan)

if __name__ == "__main__":
    main()