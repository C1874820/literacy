# Rex 识字系统

Track Rex's Chinese character literacy progress. Data flows: FlowUs (book list + learning records) → `character_bank.json` → HTML progress page + GitHub Pages.

## Architecture

- **Data source**: FlowUs database (`DATABASE_ID` in scripts) — 唯一数据源（书单 + 认字情况），已删 Supabase
- **Central data file**: `character_bank.json` — books, chars, freq, learning status, log
- **Sync pipeline**: `scripts/run_sync.sh` → `auto_sync.py` (cron weekdays 10:00)
- **Web app**: `progress/index.html` — 纯静态 SPA（进度/认字字源卡片/复习），无后端，复习进度存 localStorage
- **Generated files**: `progress/data.json`, `progress/learned.json`, `progress/char_meta.json`（`generate_progress_html.py`）、`progress/char_etymology.json`（`build_etymology.py`，字源数据）
- **字源数据**: Make Me a Hanzi `dictionary.txt`（MIT，存 `data/makemeahanzi/`，gitignore）→ 每字 type(象形/会意/形声) + hint_cn(造字提示，DeepSeek 翻译)
- **每周主力**: `week_roster.json`（周次书单状态）+ `update_weekly_focus.py` 写 FlowUs 本周主力页
- **Deployment**: GitHub Pages via `auto_sync.py` 内建 `git push origin main`

## Commands

```bash
# Full sync (runs via cron Mon-Fri 10:00)
scripts/run_sync.sh

# Manual sync (needs .env)
source .env && python3 scripts/auto_sync.py

# 补全手动新加书的元数据（豆瓣作者/年份 + 本地模型分类10类 + 书架/系列）
python3 scripts/enrich_books.py            # 扫描+补全
python3 scripts/enrich_books.py --dry-run  # 只预览

# 生成字源数据 char_etymology.json（下载 dictionary.txt + DeepSeek 翻译 hint）
python3 scripts/build_etymology.py

# 每周主力书单（周次计算 + 素材池 + 顺延/剔除）
python3 scripts/week_roster.py --apply

# 写 FlowUs 本周主力页（读 week_roster.json）
python3 scripts/update_weekly_focus.py

# Generate progress HTML + JSON files
python3 scripts/generate_progress_html.py

# Update FlowUs progress page
python3 scripts/update_flowus_progress.py
```

### 识字系统脚本（`scripts/`）

| 脚本 | 功能 |
|------|------|
| `auto_sync.py` | 全自动同步（cron）：FlowUs 书单 → 字库 → 字源/进度 JSON → git push |
| `enrich_books.py` | 补全手动新加书元数据：豆瓣补作者/年份 + 本地 qwen2.5:7b 分类10类 + 填书架/系列 |
| `build_etymology.py` | 生成 `char_etymology.json`（字源：象形/会意/形声 + 中文造字提示，DeepSeek 翻译） |
| `week_roster.py` | 每周主力书单：周次计算 + 素材池筛选 + 顺延/连续两周未读剔除 |
| `update_weekly_focus.py` | 读 week_roster.json → 生成 markdown → flowus markdown put 写本周主力页 |
| `generate_progress_html.py` | 生成 data/learned/char_meta JSON |
| `update_flowus_progress.py` | 更新息流识字进度页 |
| `fill_book_meta.py` / `fill_book_text.py` | 补全书元数据 / 提取正文文字 |
| `recommend_pool.py` | 推荐书单素材池（旧，可被 week_roster 取代） |

## Rex 观察记录系统（v2.0 回退，2026-09-05）

**文字类观察回 OB**，FlowUs **只存图片**（学校图片+教师简短说明）。OB `rex观察记录/` 周文件为文字观察主载体。
周次沿用德阳 2026-2027 秋季校历：9/1 行课周=第1周（9/1~9/6，共20周），其后每7天；「本周主力」与观察记录共用此周次。

### 红线（观察内容绝不公开发布）

- 观察内容只存两处：**OB**（→Gitee **私有**仓库 `yulei890/C1874820.git`，obsidian-git 自动 commit）+ **FlowUs 云端**（私有）
- 公开仓库（GitHub Pages `C1874820/literacy`）**零观察内容**——`observe/`、`.observe/` 已 gitignore 永不提交
- 整理/移动观察内容后必须推进到 Gitee 私库；**绝不**经任何公开发布流程

### 录入与整理（v2.0）

| 流 | 落点 | 说明 |
|----|------|------|
| 家庭瞬时观察 | OB `rex观察记录/YY年-幼儿园-第X周-观察记录.md` | 行格式 `日期 \| 一句话/观察点`，按周文件分节 |
| 阅读随手记 | 同上 | 格式 `日期 \| 书名 \| Rex状态/提问/值得记录` |
| 学校/教师成长 | FlowUs 学期容器周页（**仅图片+简短说明**） | 手动操作，文字不进 OB |
| OB → Gitee 版本控制 | obsidian-git 每 5 分钟自动 commit + 手动 `git push` | **Rollback 利用 git 历史** |

整理 = opencode 手动触发（说"整理观察"）：只用 OB 周文件内容，只规范标题/格式/位置，**不改写内容**。

### FlowUs 结构（图片容器）

| 位置 | ID | 类型 |
|------|----|------|
| `26年秋期-观察记录` 学期容器 | `38a442f6-73a6-455c-8761-70f50992fc94` | child_database：每行=周页（放学校图片+说明） |
| 本周主力页 | `d14aa902-707b-4b1b-b443-0eaa15ed4cd6` | 页面（Rex阅读成长系统下，识字计划用） |

> `家庭观察`页（`d05e88bc...`）已于 2026-09-05 **手动删除**（当时为空页）。观察文字已全部移至 OB。

### 已停用脚本（`/mnt/d/rex/observe/`，后续重新设计）

以下脚本仍保留（gitignore 不进公开仓库），**已停用**，待后续重新设计：

- `flowus_observe.py` detect/show/watch/rollup/mark-done/fix-block
- `rex_monthly.py` / `ollama_host.py`
- `观察整理-playbook.md`

### systemd（user，已 disable）

- `rex-observe-watch.service`、`rex-observe-rollup.timer`、`rex-observe-monthly.timer/.service`：全部 `systemctl --user disable --now`（2026-09-05）

## 文档录入规则（双轨，2026-09-01 定）

改动内容、规划、规则的落笔记方式按系统分轨，互不混写：
- **识字系统**（书单/识字/字库/FlowUs/字源/进度页）→ 只在 `孩子成长/识字系统-项目文档.md` 录入
- **观察记录**（周观察/月报/情绪行为等）→ 只在 `孩子成长/Rex观察记录-项目文档.md` 录入（单独笔记，不写入识字系统文档）

## Environment

- **Python 3** — no requirements, stdlib only (no pip packages)
- `.env` contains: `FLOWUS_TOKEN`, `GITHUB_TOKEN`
- `.env` is gitignored — never commit it
- `books_from_flowus.json` is also gitignored (contains FlowUs page UUIDs)

## Conventions

- All paths are absolute (`/mnt/d/rex/...`) in Python scripts（支持 `REX_BASE` 环境变量覆盖，Windows 端测试用 `REX_BASE=D:/rex`）
- Character extraction: `'\u4e00' <= c <= '\u9fff'` (CJK Unified Ideographs)
- Book status flow: FlowUs select field → `character_bank.json` `status`
- New books get `text_source: "pending"` until character text is extracted
- `auto_sync.py` auto-commits and pushes after sync (`auto-sync YYYY-MM-DD`)
- 书单录入（`enrich_books.py`，2026-09 起）：
  - 手动在 FlowUs「Rex阅读记录」加书名 → 跑 `python3 scripts/enrich_books.py`
  - 脚本自动：去重检测 → 豆瓣 `subject_suggest` 补作者/年份 → 本地 qwen2.5:7b 分类10类 → 填书架/系列
  - 分类模型本地 Ollama（`qwen2.5:7b`，热态 ~1.5s/本）；本机无 qwen3.5，qwen3:0.6b 分类质量差勿用
  - 书架已重构为具名层（见下 FlowUs Schema）；系列精确映射 + 作者包含映射
  - 已删 `batch_import_books.py`（手动录入替代）

## FlowUs Database Schema

### Rex阅读记录 (ID: `10df60aa-aee0-4727-adab-f4d99e1cc053`)

| Field | Type | Notes |
|-------|------|-------|
| 书名 | title | Book name (API key 用 `title`) |
| 作者 | rich_text | Author |
| 状态 | select | 未读 / 在读 / 已读 |
| 书籍类型 | multi_select | 地域/传统/文学/科普/无字书/神话故事/桥梁书/艺术/情绪习惯/思维社会 |
| 书籍来源 | select | 纸质书 / 电子书 |
| 电子书籍格式 | select | PDF / EPUB |
| 认字情况 | rich_text | Learned chars (e.g. 大、小、上、下) |
| 认字字数 | number | 认字情况 字符数（--count-chars 统计） |
| 读后感 | rich_text | Reading notes |
| 存放位置 | select | 具名书架层：1#文学A·低字量启蒙 / 2#文学B·中篇系列 / 3#文学C·普通绘本 / 4#科普+思维社会 / 5#情绪习惯+传统 / 6#艺术+神话·无字书·桥梁 / 7#流动层（未读文学常住）/ 未上架 |
| 适合年龄 | multi_select | 3-4, 4-5, 5-6, 6-7, 7-8, 8-9 |
| 系列 | select | 36 个系列选项（布鲁斯/巫婆奶奶/吉竹伸介/宫西达也恐龙/这里是新疆/德国精选科学图画书 等） |
| 读完日期 | date | 阅读完成日期 |

### 每周推荐 (ID: `2f45cfb4-a4f2-4271-b1e3-e0a2d94892ab`)

| Field | Type | Notes |
|-------|------|-------|
| title | title | Book name |
| 作者 | rich_text | Author |
| 适合年龄 | multi_select | 3-4, 4-5, 5-6, 6-7, 7-8, 8-9 |
| 推荐理由 | rich_text | Why it suits Rex |
| 精读技巧 | rich_text | How to guide reading |
| 认字点 | rich_text | What chars to learn |
| 书籍来源 | multi_select | 已有 / 需下载 / 需购买 |

## Supabase Schema

已删除（2026-09-06）。原 `words`（网页录入）+ `reviews`（间隔复习）表随 Supabase 一并移除，认字记录统一走 FlowUs `认字情况` 字段，复习进度存网页 localStorage。

## Gotchas

- 识字录入统一走 FlowUs「认字情况」字段（网页只读展示，不再有 Supabase 录入入口）
- 字源数据 `char_etymology.json` 由 `build_etymology.py` 生成（Make Me a Hanzi，MIT）；`data/makemeahanzi/dictionary.txt` 已 gitignore
- GitHub Pages: `auto_sync.py` 内建 `git push origin main`（分支为 `main`，旧 `deploy_github.sh` 已删除）
- FlowUs API: every property must include `type` field in requests
- 本地 Ollama 分类用 `qwen2.5:7b`（翻译/复杂任务本地模型质量差，hint 翻译用 DeepSeek）

## 工作流（必须执行）

### 优化前：查看 Obsidian 待办
每次做优化/修改前，必须先读取 Obsidian 项目文档中的待办清单：
```
/mnt/d/Onedrive/个人仓库/01_Areas/孩子成长/识字系统-项目文档.md
```
找到「待办」章节，确认本次是否涉及其中条目。

### 优化后：写回剩余待办
修改完成后，将未完成的待办原样写回同一文件的「待办」章节。
已完成的条目标记 `- [x]`，新增的条目追加到列表末尾。

## Privacy

- Never output API Keys, tokens, or secrets in conversation
- `.env` values are gitignored — never commit them
- FlowUs page IDs are internal only — do not expose to user-visible output
