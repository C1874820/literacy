#!/usr/bin/env python3
"""补全 FlowUs「Rex阅读记录」手动新加书籍的元数据。
用户手动在 FlowUs 加书名 → 本脚本扫描缺元数据的书 → 豆瓣补作者/年份 →
本地模型分类(10类) → 填系列 + 书架 → 写回 FlowUs。

用法:
  python3 scripts/enrich_books.py              # 扫描+补全（分类走本地 Ollama）
  python3 scripts/enrich_books.py --dry-run    # 只预览，不写入
  python3 scripts/enrich_books.py --model qwen2.5:7b   # 指定分类模型

依赖:
  - .env 的 FLOWUS_TOKEN
  - 本地 Ollama（分类用，缺省 qwen2.5:7b，可降档）
"""
import json, os, sys, time, urllib.request, urllib.error, urllib.parse
from collections import Counter

BASE = os.environ.get("REX_BASE", "/mnt/d/rex")
DB = "10df60aa-aee0-4727-adab-f4d99e1cc053"
ENV = f"{BASE}/.env"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DOUBAN_SUGGEST = "https://book.douban.com/j/subject_suggest"

# 类型定义（10类，严格约束）
EXISTING_TYPES = ["地域", "传统", "文学", "科普", "无字书", "神话故事", "桥梁书", "艺术", "情绪习惯", "思维社会"]

# 书架映射：按类型优先序 → 具名书架（文学为主归流动层，非文学按类型）
SHELF_MAP = {
    "无字书": "6#艺术+神话/无字书/桥梁",
    "桥梁书": "6#艺术+神话/无字书/桥梁",
    "艺术": "6#艺术+神话/无字书/桥梁",
    "神话故事": "6#艺术+神话/无字书/桥梁",
    "科普": "4#科普+思维社会",
    "思维社会": "4#科普+思维社会",
    "情绪习惯": "5#情绪习惯+传统",
    "传统": "5#情绪习惯+传统",
}
SHELF_LITERATURE = "7#流动层（未读文学常住）"

# 系列匹配：书名 → 系列（精确）
SERIES_BY_TITLE = {
    "四季时光 五本": "四季时光",
    "建筑师的大创造巧妙地改造方案": "建筑师的大创造",
    "建筑师的大创造看不见的空间": "建筑师的大创造",
    "建筑师的大创造错位的建筑结构": "建筑师的大创造",
    "建筑师的大创造变化的设计图": "建筑师的大创造",
    "建筑师的大创造老房子的记忆": "建筑师的大创造",
    "小兔汤姆系列图画书旅行版26册": "小兔汤姆",
    "卡蜜儿情商社交游戏绘本共5辑": "卡蜜儿情商社交",
    "洛克数学启蒙 趣味启蒙图画书共40册": "洛克数学启蒙",
    "帮帮机器人分清事实和观点": "帮帮机器人",
    "帮帮机器人分清想要和需要": "帮帮机器人",
    "野猫军团吃蛋糕": "野猫军团",
    "野猫军团吃面包": "野猫军团",
    "野猫军团吃冰淇淋": "野猫军团",
    "野猫军团吃咖喱饭": "野猫军团",
    "野猫军团吃团子": "野猫军团",
    "野猫军团吃寿司": "野猫军团",
    "野猫军团开火车": "野猫军团",
    "野猫军团烤面包": "野猫军团",
    "青蛙和蟾蜍 好朋友": "青蛙和蟾蜍",
    "青蛙和蟾蜍 快乐时光": "青蛙和蟾蜍",
    "青蛙和蟾蜍 快乐年年": "青蛙和蟾蜍",
    "藏在地图里的中国历史史前文明-西晋": "藏在地图里的中国历史",
    "藏在地图里的中国历史东晋-清": "藏在地图里的中国历史",
    "走进艺术故事": "走进艺术",
    "走进艺术人物": "走进艺术",
    "思考世界的孩子想个不停": "思考世界的孩子",
    "思考世界的孩子问个不停": "思考世界的孩子",
    "有时候我可以拒绝": "有时候我可以",
    "有时候我可以生气": "有时候我可以",
    "写给亲爱的儿子": "写给亲爱的",
    "写给亲爱的女儿": "写给亲爱的",
    "超级乌龟": "超级乌龟兔子",
    "超级兔子": "超级乌龟兔子",
    "探索火山岛": "探索火山深海",
    "走去深海": "探索火山深海",
    "城堡的一年": "一年四季",
    "建筑工地的一年": "一年四季",
    "山间的一年": "一年四季",
    "城市中的一年": "一年四季",
    "森林里的一年": "一年四季",
    "有了问题你怎么做": "有了...你怎么做",
    "有了机会你怎么做": "有了...你怎么做",
    "有了想法你怎么做": "有了...你怎么做",
    "西游记绘本": "西游记绘本",
    "大灰狼咕噜羞耻的秘密": "大灰狼咕噜",
    "大灰狼咕噜怀念的秘密": "大灰狼咕噜",
    "巫婆奶奶去度假": "巫婆奶奶系列",
    "巫婆奶奶的魔戒": "巫婆奶奶系列",
    "巫婆奶奶棋逢对手": "巫婆奶奶系列",
    "巫婆奶奶的魔法课": "巫婆奶奶系列",
    "巫婆奶奶": "巫婆奶奶系列",
    "巫婆奶奶的故事": "巫婆奶奶系列",
    "不可思议的旅程 彩虹国度": "不可思议的旅程",
    "不可思议的旅程 回归之夜": "不可思议的旅程",
    "不可思议的旅程": "不可思议的旅程",
    "安格斯迷路了": "安格斯系列",
    "安格斯和鸭子": "安格斯系列",
    "安格斯和猫": "安格斯系列",
    "巴巴和孩子们": "大象巴巴",
    "巴巴的故事": "大象巴巴",
    "巴巴的旅行": "大象巴巴",
    "巴巴和猴子们": "大象巴巴",
    "大象巴巴": "大象巴巴",
    "最聪明的大野狼": "大野狼系列",
    "我是最厉害的大野狼": "大野狼系列",
    "我是最帅的大野狼": "大野狼系列",
    "狼狼你来了吗": "大野狼系列",
    "卡尔玩游戏": "卡尔系列",
    "卡尔的大大惊喜": "卡尔系列",
    "卡尔的第一次体验": "卡尔系列",
    "圣诞老人布鲁斯": "布鲁斯系列",
    "嘿布鲁斯": "布鲁斯系列",
    "布鲁斯遇上大暴雨": "布鲁斯系列",
    "布鲁斯大搬家": "布鲁斯系列",
    "鹅妈妈布鲁斯": "布鲁斯系列",
    "冒牌布鲁斯": "布鲁斯系列",
    "安静": "布鲁斯系列",
    "安静的湖": "布鲁斯系列",
    "去沙爷爷小院升国旗": "这里是新疆",
    "喀什寻喵迹": "这里是新疆",
    "驼背上的梦想": "这里是新疆",
    "龟兹奇妙之旅": "这里是新疆",
    "我和爸爸逛巴扎": "这里是新疆",
    "艾德莱斯绸布谷鸟的翅膀花": "这里是新疆",
    "我还想去博物馆": "这里是新疆",
    "更高的地面": "这里是新疆",
    "图瓦人的木房子": "这里是新疆",
    "我和野马王子": "这里是新疆",
    "举世无双的地毯": "这里是新疆",
    '"地下长城"坎儿井': "这里是新疆",
    "阿丽亚找爸爸": "这里是新疆",
    "飞吧爸爸": "深见春夫系列",
    "冒险泥巴球": "深见春夫系列",
    "云朵怪兽": "深见春夫系列",
    "10只小猴加油": "五味太郎启蒙",
}

# 系列匹配：作者包含匹配
SERIES_BY_AUTHOR = [
    ("宫西达也", "宫西达也恐龙系列"),
    ("深见春夫", "深见春夫系列"),
    ("吉竹伸介", "吉竹伸介系列"),
    ("五味太郎", "五味太郎启蒙"),
    ("瑞安·T·希金斯", "布鲁斯系列"),
    ("马里奥·哈默斯", "大野狼系列"),
    ("安娜·鲁斯曼", "德国精选科学图画书"),
    ("雷切尔布莱特", "雷切尔·布莱特系列"),
    ("雷切尔·布莱特", "雷切尔·布莱特系列"),
    ("郝广才", "郝广才系列"),
    ("伊戈尔·欧尼科夫", "欧尼科夫系列"),
    ("大卫·香农", "大卫系列"),
]

CLASSIFY_PROMPT = """你是儿童绘本分类专家。根据书名和作者，为这本书选择最合适的类型。可返回多个类型，用逗号分隔。

## 类型定义（严格遵循）

- 地域：书名明确含地名（如新疆、喀什、龟兹、胡同、巴扎、坎儿井），且内容围绕当地生活/文化。仅含"城堡/城市/森林"等泛称不是地域。含"小院/邻居"等具体场景但无地名的，不是地域。
- 传统：民间故事、成语、节气节日、传统艺术题材（如老鼠娶新娘）。注意：书名含地名 ≠ 传统；普通生活故事 ≠ 传统。
- 文学：虚构故事、情感故事、生活故事、童话。故事书一般都要标 文学。
- 科普：百科、数学、科学、实验、动物、人体、自然、non-fiction、生命科学。包括：肚子里有个火车站/牙齿大街的新鲜事（人体消化）、生命的故事/走去深海（自然生命）、好饿的毛毛虫（昆虫成长）、新武器驾到（军事科技）、青少年军事大百科。
- 无字书：纯图画无文字。**只有这些已知无字书才标**：小香蕉去看海、午夜游乐场、逃跑吧寻找吧、我来帮你打开吧。其他书不确定时**不要**标 无字书。
- 神话故事：中国古典神话/民间传说（哪吒、龙、神仙、西游记、马良、猴子捞月）。可叠加 传统。
- 桥梁书：章节式、文字量介于绘本和纯文字之间（如青蛙和蟾蜍系列）。
- 艺术：美术、音乐、建筑、设计、艺术启蒙。书名含"艺术""颜色""色彩""建筑师/建筑""走进艺术" = 艺术。建筑师系列 = 艺术（+科普）。
- 情绪习惯：情绪管理、生活习惯、社交礼仪、性格培养。书名含"生气""发火""情绪""哭""尿裤子""刷牙""睡觉/数羊""橡皮筋""脾气"等行为/情绪词 = 情绪习惯。如：我的情绪小怪兽、大卫不可以、发火、尿湿了裤子、尿裤子男孩、刷牙先生来了、谁说睡前要数羊、我的橡皮筋不给你。
- 思维社会：哲学启蒙、权利义务、社会认知、思考方法。帮帮机器人系列、思考世界的孩子系列、唤醒会思考的你 = 思维社会（+科普）。

## 分类规则（最重要，按优先级）

1. **书名含明确信号词的，必须标对应类型**：
   - 含"情绪/生气/发火/脾气/哭/尿裤子/刷牙/习惯/社交/礼貌/心愿/情绪小怪兽" → 情绪习惯
   - 含"艺术/颜色/色彩/建筑师/建筑/走进艺术/绘画/音乐" → 艺术
   - 含"科学/数学/实验/百科/动物/恐龙/海洋/深海/生命/人体/大脑/肚子/牙齿/自然" → 科普
   - 含"哲学/思考/权利/义务/事实/观点/想要/需要/规则" → 思维社会
   - 含"神话/哪吒/龙王/神仙/西游记/马良/捞月/传说" → 神话故事
   - 含明确地名（新疆/喀什/龟兹/巴扎/坎儿井/胡同/地图里的中国历史）→ 地域
   - 含"青蛙和蟾蜍" → 桥梁书
2. **故事书默认标 文学**，再叠加上面的信号类型。不要只给 情绪习惯/思维社会 而不给 文学（除非书名明确是行为教育功能书，如"尿湿了裤子"→情绪习惯）。
3. 如果书名同时含多个信号词，返回多个类型。
4. 无字书只限已知四本，其他一律不标。
5. 不要创造新类型，科普类一律归入"科普"。
6. 帽子迷弗雷德、卡尔的大大惊喜 这类虚构故事书 → 文学。
7. 野兽国（经典情绪类绘本）→ 文学,情绪习惯。老鼠娶新娘 → 传统（民间婚俗故事，不是神话故事）。
8. 四季时光（找图观察书）→ 文学,科普。不要发明"季节"等新类型。

## 输出约束（必须严格遵守）

- **只能从这 10 个类型中选择**：地域、传统、文学、科普、无字书、神话故事、桥梁书、艺术、情绪习惯、思维社会
- 绝不输出这 10 个以外的任何词
- 若不确定，选最接近的，并给故事书补上"文学"

## 示例（权威标准，学这个）

- 喀什寻喵迹 → 地域,文学
- 神笔马良 → 传统,神话故事,文学
- 老鼠娶新娘 → 传统
- 帮帮机器人分清事实和观点 → 科普,思维社会
- 思考世界的孩子问个不停 → 思维社会
- 好饿的毛毛虫 → 科普,文学
- 大卫不可以 → 文学,情绪习惯
- 小香蕉去看海 → 文学,无字书
- 建筑师的大创造错位的建筑结构 → 艺术,科普
- 藏在地图里的中国历史 → 地域,科普,传统
- 青蛙和蟾蜍 好朋友 → 桥梁书
- 我的情绪小怪兽 → 情绪习惯
- 牙齿大街的新鲜事 → 科普
- 尿湿了裤子 → 情绪习惯
- 权力和义务 → 思维社会
- 生命的故事 → 科普
- 走进艺术故事 → 艺术
- 颜色的战争 → 艺术
- 走去深海 → 科普
- 新武器驾到 → 科普
- 去沙爷爷小院升国旗 → 地域,文学
- 帽子迷弗雷德 → 文学
- 卡尔的大大惊喜 → 文学
- 野兽国 → 文学,情绪习惯
- 四季时光 → 文学,科普

书名：{title}
作者：{author}

请只返回类型名称，多个用逗号分隔，不要解释。例如：地域 或 文学,科普"""


def log(msg):
    print(msg)


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
        shelf = (p.get("存放位置", {}).get("select") or {}).get("name", "") if p.get("存放位置", {}).get("select") else ""
        out.append({"id": r["id"], "title": title, "author": author,
                    "series": series, "types": types, "shelf": shelf})
    return out


def douban_author(title):
    """豆瓣 subject_suggest 查询，返回精确匹配的 (作者, 年份)"""
    url = DOUBAN_SUGGEST + "?q=" + urllib.parse.quote(title)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            items = json.loads(r.read().decode())
    except Exception as e:
        log(f"    ⚠ 豆瓣查询失败: {e}")
        return "", ""
    if not isinstance(items, list):
        return "", ""
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("title", "").strip() == title.strip():
            return it.get("author_name", ""), it.get("year", "")
    # 无精确匹配，取第一个候选（书名含标题）
    for it in items:
        if isinstance(it, dict) and title.strip() in it.get("title", ""):
            return it.get("author_name", ""), it.get("year", "")
    return "", ""


def classify(title, author, retries=1):
    """本地 Ollama 分类，返回合法类型列表"""
    def _clean(content):
        raw = []
        for t in content.replace("、", ",").replace("，", ",").split(","):
            t = t.strip().strip("\"'‘’“”")
            if t:
                raw.append(t)
        valid = [t for t in raw if t in EXISTING_TYPES]
        return valid if valid else (raw[:1] if raw else [])

    body = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": CLASSIFY_PROMPT.format(title=title, author=author)}],
        "stream": False,
        "options": {"temperature": 0},
    }
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                content = json.loads(r.read().decode()).get("message", {}).get("content", "").strip()
            types = _clean(content)
            if types:
                return types
            return ["文学"]
        except Exception as e:
            if attempt < retries:
                log(f"    ⚠ 分类重试 ({e})")
                time.sleep(2)
            else:
                log(f"    ✗ 分类失败: {e}")
                return ["文学"]


def calc_shelf(types):
    """类型 → 书架。文学为主→流动层；非文学按类型优先映射。"""
    has_lit = "文学" in types
    for t in ["无字书", "桥梁书", "艺术", "神话故事"]:
        if t in types and t not in ("神话故事",) and t in types:
            pass
    # 非文学主导 → 类型书架
    nonlit = [t for t in types if t != "文学"]
    if nonlit:
        # 按优先级：无字书/桥梁/艺术/神话 → 6#；科普/思维 → 4#；情绪/传统 → 5#
        if any(t in ("无字书", "桥梁书", "艺术", "神话故事") for t in nonlit):
            return SHELF_MAP["无字书"]
        if any(t in ("科普", "思维社会") for t in nonlit):
            return SHELF_MAP["科普"]
        if any(t in ("情绪习惯", "传统") for t in nonlit):
            return SHELF_MAP["情绪习惯"]
        if "地域" in nonlit:
            return SHELF_LITERATURE
    return SHELF_LITERATURE


def calc_series(title, author):
    if title in SERIES_BY_TITLE:
        return SERIES_BY_TITLE[title]
    if author:
        for auth, series in SERIES_BY_AUTHOR:
            if auth in author:
                return series
    return ""


def build_props(fields):
    props = {}
    for f, v in fields.items():
        if f == "作者":
            props[f] = {"type": "rich_text", "rich_text": [{"type": "text", "text": {"content": v}}]}
        elif f == "书籍类型":
            props[f] = {"type": "multi_select", "multi_select": [{"name": t} for t in v]}
        elif f in ("系列", "存放位置"):
            props[f] = {"type": "select", "select": {"name": v}}
    return props


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    for a in args:
        if a.startswith("--model"):
            global OLLAMA_MODEL
            OLLAMA_MODEL = a.split("=", 1)[1] if "=" in a else OLLAMA_MODEL

    token = load_token()
    log("拉取全库...")
    records = normalize(query_all(token))
    log(f"共 {len(records)} 本")

    # 去重检测
    by_title = Counter(r["title"] for r in records if r["title"])
    dups = {t: n for t, n in by_title.items() if n > 1}
    if dups:
        log(f"⚠ 发现 {len(dups)} 个重名书（需手动核对）：")
        for t, n in dups.items():
            log(f"   {t} ×{n}")

    # 找缺元数据的书
    need = [r for r in records if r["title"] and (not r["author"] or not r["types"] or not r["shelf"])]
    log(f"缺元数据待补全: {len(need)} 本")
    if not need:
        log("无需补全")
        return

    log(f"\n分类模型: {OLLAMA_MODEL} | 豆瓣补作者 + 本地分类\n")
    plan = []
    for i, r in enumerate(need):
        log(f"[{i+1}/{len(need)}] {r['title']}" + (f"（{r['author']}）" if r["author"] else ""))
        fields = {}
        author = r["author"]
        year = ""
        if not author:
            author, year = douban_author(r["title"])
            if author:
                fields["作者"] = author
                log(f"    豆瓣 → 作者 {author}" + (f" ({year})" if year else ""))
            else:
                log(f"    豆瓣 → 未找到作者")
        types = r["types"] or []
        if not types:
            t0 = time.time()
            types = classify(r["title"], author or r["author"]) or ["文学"]
            fields["书籍类型"] = types
            log(f"    分类 → {', '.join(types)} ({time.time()-t0:.1f}s)")
        if not r["shelf"]:
            shelf = calc_shelf(types)
            fields["存放位置"] = shelf
            log(f"    书架 → {shelf}")
        if not r["series"]:
            series = calc_series(r["title"], author or r["author"])
            if series:
                fields["系列"] = series
                log(f"    系列 → {series}")
        if fields:
            plan.append({"id": r["id"], "title": r["title"], "fields": fields})

    log(f"\n待写入 {len(plan)} 本")
    if dry:
        log("--dry-run 模式，未写入")
        return
    for p in plan:
        r = api_v2(token, "PATCH", f"/pages/{p['id']}", {"properties": build_props(p["fields"])})
        if "http_error" in r:
            log(f"  FAIL {p['title']}: {r['http_error']} {r['body']}")
        else:
            log(f"  ✓ {p['title']}")
    log("完成")


if __name__ == "__main__":
    main()
