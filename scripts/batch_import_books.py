#!/usr/bin/env python3
"""
批量导入书名+作者到 FlowUs
读取输入文件 → 去重 → LLM 分类 → 批量创建 FlowUs 页面

用法：
  python batch_import_books.py                    # 读默认 books.txt（电脑端录入）
  python batch_import_books.py <输入文件路径>      # 读指定文件（如手机端 OB 的录书.md）

输入文件格式（每行）：
  书名, 作者
  书名（无作者可省略逗号和作者）
"""

import json
import os
import sys
import urllib.request
import urllib.error

BASE_DIR = "/mnt/d/rex-识字系统"
DATABASE_ID = "10df60aa-aee0-4727-adab-f4d99e1cc053"
FLOWUS_TOKEN = os.environ.get("FLOWUS_TOKEN")
BOOKS_FILE = os.path.join(BASE_DIR, "books.txt")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

# 已有的类型选项（LLM 可新增）
EXISTING_TYPES = ["地域", "传统", "文学", "科普", "无字书", "神话故事", "桥梁书", "艺术", "情绪习惯", "思维社会"]


def log(msg):
    print(msg)


def flowus_api(method, path, data=None):
    url = f"https://api.flowus.cn/v1{path}"
    headers = {
        "Authorization": f"Bearer {FLOWUS_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_existing_books():
    """拉取 FlowUs 现有书单（翻页拉全量，防止去重失效）"""
    books = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = flowus_api("POST", f"/databases/{DATABASE_ID}/query", body)
        for page in data.get("results", []):
            props = page.get("properties", {})
            # title 字段的 key 可能是 "title" 或 "书名"
            title_raw = props.get("title") or props.get("书名") or {}
            title_parts = title_raw.get(title_raw.get("type", "title"), [])
            title = "".join(t.get("plain_text", "") for t in title_parts)
            if title:
                books[title] = page.get("id")
        if data.get("has_more") and data.get("next_cursor"):
            cursor = data["next_cursor"]
        else:
            break
    return books


def ensure_type_exists(type_name):
    """确保类型选项存在于数据库，不存在则自动添加"""
    db = flowus_api("GET", f"/databases/{DATABASE_ID}")
    type_prop = db.get("properties", {}).get("书籍类型", {})
    type_id = type_prop.get("id", "")
    options = type_prop.get("multi_select", {}).get("options", [])
    existing_names = [o.get("name") for o in options]

    if type_name in existing_names:
        return True

    new_options = [{"name": n} for n in existing_names] + [{"name": type_name}]
    try:
        flowus_api("PATCH", f"/databases/{DATABASE_ID}", {
            "properties": {
                "书籍类型": {
                    "type": "multi_select",
                    "multi_select": {"options": new_options},
                }
            }
        })
        log(f"  + 新增类型「{type_name}」到数据库")
        return True
    except Exception as e:
        log(f"  ⚠ 添加类型「{type_name}」失败: {e}")
        return False


def read_books_file(path):
    """解析 books.txt"""
    books = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # 支持中英文逗号
            sep = "," if "," in line else "，" if "，" in line else None
            if sep:
                parts = line.split(sep, 1)
                title = parts[0].strip()
                author = parts[1].strip()
            else:
                title = line.strip()
                author = ""
            if title:
                books.append({"title": title, "author": author})
    return books


def classify_book(title, author, retries=2):
    """调用 Ollama 分类单本书"""
    prompt = f"""你是儿童绘本分类专家。根据书名和作者，为这本书选择最合适的类型。可返回多个类型，用逗号分隔。

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
5. 不要创造新类型（如"军事科技""历史""季节"），科普类一律归入"科普"。
6. 帽子迷弗雷德、卡尔的大大惊喜 这类虚构故事书 → 文学。
7. 野兽国（经典情绪类绘本）→ 文学,情绪习惯。老鼠娶新娘 → 传统（民间婚俗故事，不是神话故事）。
8. 四季时光（找图观察书）→ 文学,科普。不要发明"季节"等新类型。

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
- 老鼠娶新娘 → 传统
- 四季时光 → 文学,科普

书名：{title}
作者：{author}

请只返回类型名称，多个用逗号分隔，不要解释。例如：地域 或 文学,科普"""

    data = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    for attempt in range(retries + 1):
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                OLLAMA_URL, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
                content = result.get("message", {}).get("content", "").strip()
                # 解析返回的类型
                types = []
                for t in content.replace("、", ",").replace("，", ",").split(","):
                    t = t.strip().strip("\"'""''")
                    if t:
                        types.append(t)
                return types if types else ["文学"]
        except Exception as e:
            if attempt < retries:
                log(f"  ⚠ Ollama 调用失败，重试... ({e})")
            else:
                log(f"  ✗ 分类失败: {e}")
                return ["文学"]


def create_flowus_page(title, author, types):
    """创建 FlowUs 页面"""
    properties = {
        "title": {
            "type": "title",
            "title": [{"type": "text", "text": {"content": title}}],
        },
        "状态": {
            "type": "select",
            "select": {"name": "未读"},
        },
        "书籍来源": {
            "type": "select",
            "select": {"name": "纸质书"},
        },
    }
    if author:
        properties["作者"] = {
            "type": "rich_text",
            "rich_text": [{"type": "text", "text": {"content": author}}],
        }
    if types:
        properties["书籍类型"] = {
            "type": "multi_select",
            "multi_select": [{"name": t} for t in types],
        }

    result = flowus_api("POST", "/pages", {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
    })
    return result.get("id", "")


def main():
    if not FLOWUS_TOKEN:
        log("ERROR: FLOWUS_TOKEN 未设置")
        return

    # 可选位置参数指定输入文件；缺省用 books.txt
    input_file = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            input_file = arg
            break
    books_file = input_file or BOOKS_FILE

    if not os.path.exists(books_file):
        log(f"ERROR: {books_file} 不存在")
        log(f"请创建 {books_file}，每行格式：书名, 作者")
        return

    log("=" * 50)
    log("批量导入书单到 FlowUs")
    log("=" * 50)

    # 1. 读取书单
    books = read_books_file(books_file)
    log(f"\n📖 读取 {books_file}: {len(books)} 本书")

    if not books:
        log(f"{books_file} 为空，无书可导入")
        return

    # 2. 拉取 FlowUs 现有书单
    log("\n🔍 拉取 FlowUs 现有书单...")
    existing = fetch_existing_books()
    log(f"   FlowUs 已有 {len(existing)} 本书")

    # 3. 去重
    new_books = [b for b in books if b["title"] not in existing]
    skipped = len(books) - len(new_books)
    if skipped:
        log(f"   跳过已存在: {skipped} 本")
    log(f"   新增: {len(new_books)} 本")

    if not new_books:
        log("\n✅ 所有书都已存在于 FlowUs，无新增")
        return

    # 4. LLM 分类
    log(f"\n🤖 调用 Ollama ({OLLAMA_MODEL}) 分类中...")
    categorized = []
    for i, book in enumerate(new_books):
        title = book["title"]
        author = book["author"]
        log(f"   [{i+1}/{len(new_books)}] {title}" + (f" ({author})" if author else ""))
        types = classify_book(title, author)
        categorized.append({"title": title, "author": author, "types": types})
        log(f"           → {', '.join(types or [])}")

    # 5. 展示预览
    log("\n" + "=" * 50)
    log("📋 导入预览（共 {} 本）：".format(len(categorized)))
    log("=" * 50)
    for i, b in enumerate(categorized):
        log(f"  {i+1:2d}. {b['title']}" + (f"  | {b['author']}" if b['author'] else "") + f"  | {', '.join(b['types'])}")

    # 6. 自动确认
    log("")
    log("自动确认模式，直接导入")

    # 7. 批量创建
    log("\n📝 开始创建 FlowUs 页面...")

    # 收集所有需要的类型，确保它们存在于数据库
    all_types = set()
    for b in categorized:
        all_types.update(b["types"])
    log(f"   检查类型选项: {', '.join(sorted(all_types))}")
    for t in sorted(all_types):
        ensure_type_exists(t)

    success = 0
    fail = 0
    for i, b in enumerate(categorized):
        try:
            page_id = create_flowus_page(b["title"], b["author"], b["types"])
            success += 1
            log(f"   ✓ [{i+1}/{len(categorized)}] {b['title']} → {page_id[:8]}...")
        except Exception as e:
            fail += 1
            log(f"   ✗ [{i+1}/{len(categorized)}] {b['title']} - 失败: {e}")

    log(f"\n{'=' * 50}")
    log(f"✅ 完成！新增 {success} 本，失败 {fail} 本")
    log(f"{'=' * 50}")

    # 8. 按类型分组输出（方便摆书架）
    type_groups = {}
    for b in categorized:
        for t in b["types"]:
            type_groups.setdefault(t, []).append(b)

    if type_groups:
        log(f"\n{'=' * 50}")
        log("📚 按类型分组（摆书架参考）：")
        log("=" * 50)
        for t in sorted(type_groups.keys()):
            log(f"\n【{t}】({len(type_groups[t])}本)")
            for b in type_groups[t]:
                author_str = f", {b['author']}" if b['author'] else ""
                log(f"  - {b['title']}{author_str}")


if __name__ == "__main__":
    main()
