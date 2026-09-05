# Rex 识字系统

Track Rex's Chinese character literacy progress. Data flows: FlowUs (book list + learning records) → `character_bank.json` → HTML progress page + GitHub Pages.

## Architecture

- **Data source**: FlowUs database (`DATABASE_ID` in scripts) + Supabase `words` table (web entry)
- **Central data file**: `character_bank.json` — books, chars, freq, learning status, log
- **Sync pipeline**: `scripts/run_sync.sh` → `auto_sync.py` (cron weekdays 10:00)
- **Web app**: `progress/index.html` — SPA with Supabase-powered review/entry tabs
- **Generated files**: `progress/data.json`, `progress/learned.json`, `progress/char_meta.json` (all from `generate_progress_html.py`)
- **Deployment**: GitHub Pages via `auto_sync.py` 内建 `git push origin main`（已移除旧 `deploy_github.sh`）

## Commands

```bash
# Full sync (runs via cron Mon-Fri 10:00)
scripts/run_sync.sh

# Manual sync (needs .env)
source .env && python3 scripts/auto_sync.py

# Generate progress HTML + JSON files
python3 scripts/generate_progress_html.py

# 识字录入入口：网页 progress/index.html（Supabase words 表，auto_sync 自动合并进字库）
# （已移除 process_log.py / report.py / build_character_bank.py / setup_supabase.sql）

# Update FlowUs progress page
python3 scripts/update_flowus_progress.py
```

### 识字系统脚本（`scripts/`）

| 脚本 | 功能 |
|------|------|
| `auto_sync.py` | 全自动同步（cron）：FlowUs 书单 → 字库 → progress JSON → git push |
| `generate_progress_html.py` | 生成 `progress/index.html` + data/learned/char_meta JSON |
| `update_flowus_progress.py` | 更新息流识字进度页 |
| `batch_import_books.py` | 书单批量录入（电脑 `books.txt` / 手机 `00_Inbox/录书.md`） |
| `fill_book_meta.py` / `fill_book_text.py` | 补全书元数据 / 提取正文文字 |
| `recommend_pool.py` | 推荐书单素材池 |

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
- **识字系统**（书单/识字/字库/FlowUs/Supabase/进度页）→ 只在 `孩子成长/识字系统-项目文档.md` 录入
- **观察记录**（周观察/月报/情绪行为等）→ 只在 `孩子成长/Rex观察记录-项目文档.md` 录入（单独笔记，不写入识字系统文档）

## Environment

- **Python 3** — no requirements, stdlib only (no pip packages)
- `.env` contains: `FLOWUS_TOKEN`, `GITHUB_TOKEN`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- `.env` is gitignored — never commit it
- `books_from_flowus.json` is also gitignored (contains FlowUs page UUIDs)

## Conventions

- All paths are absolute (`/mnt/d/rex/...`) in Python scripts
- Character extraction: `'\u4e00' <= c <= '\u9fff'` (CJK Unified Ideographs)
- Book status flow: FlowUs select field → `character_bank.json` `status`
- New books get `text_source: "pending"` until character text is extracted
- `auto_sync.py` auto-commits and pushes after sync (`auto-sync YYYY-MM-DD`)
- 书单批量录入（`batch_import_books.py`），两种输入源：
  - 电脑端：`rex/books.txt`，用后清空、已 gitignore、不提交 → `python scripts/batch_import_books.py`
  - 手机端 OB：`00_Inbox/录书.md`，导入后**直接删除**（有新书再重建，不归档）→ `python scripts/batch_import_books.py "00_Inbox/录书.md"`
  - 脚本自动去重 + DeepSeek 云端分类书籍类型（key 从 ~/.local/share/opencode/auth.json 读取，失败回退 Ollama）+ 自动确认，无需 `--yes`
  - 自动填 `存放位置`（书架，按主类型优先序映射 1#~8#）和 `系列`（书名精确映射 + 作者包含映射，限定 36 个已有系列选项）
  - 分类强约束 10 个类型 + `_clean()` 校验非法值回退文学；Ollama 仅回退用（本机 `qwen3.5:latest`）；系列/类型选项缺失时自动添加
  - 详细 SOP 见 playbooks/rex-flowus-book-import.md

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
| 存放位置 | select | 1#~8# / 未上架（按类型数量排布：文学1# 科普2# 情绪习惯3# 艺术4# 思维社会5# 传统6# 地域7# 神话/无字书/桥梁8#） |
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

### words table (web entry)
Columns: `new_words`, `date`, `recorder`, `book_name`
RLS: public select + insert

### reviews table (spaced repetition)
- `char` (PK, single CJK char `^[一-龥]$`)
- `stage` (0-5, Ebbinghaus intervals: 1,2,4,7,15,30 days)
- `last_review`, `next_review` (dates)
- `updated_by`, `updated_at` (metadata)
RLS: public select + insert + update

## Gotchas

- 识字录入统一走网页 `progress/index.html`（Supabase `words` 表），`auto_sync.py` 的 `merge_supabase_entries()` 自动汇入字库（标记已学 + 写 log）
- `progress/index.html` embeds Supabase credentials in JS (public anon key, not secret)
- GitHub Pages: `auto_sync.py` 内建 `git push origin main`（分支为 `main`，旧 `deploy_github.sh` 已删除）
- FlowUs API: every property must include `type` field in requests

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
