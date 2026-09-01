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

## Rex 观察记录系统（2026-08-31 新增）

- **位置**：`/mnt/d/Onedrive/个人仓库/01_Areas/孩子成长/rex观察记录/`
- **命名**：周观察 `YY年-幼儿园-第X周-观察记录.md` / 月度 `YY年-幼儿园-M月-月度报告.md`
- **周次**：按德阳市 2026-2027 秋季校历，9/1 行课周=第1周（共20周）；第1周=9/1(周二)~9/6(周日)，其后每7天。FlowUs「本周主力」与观察记录共用此周次
- **手机录入**：手机 Obsidian 语音转文字 → 观察记录文件「原始记录」段落（`#### 时间 标题`），电脑端自动整理
- **脚本**（识字系统 `scripts/`）：
  - `rex_observe.py once|watch|show` — 扫描带`（待本地模型整理）`占位的段落，调本地 Ollama 整理到「整理」区（原文保留）
  - `rex_monthly.py [year month]` — 聚合指定月教学周记录，生成四部分（闪光点/优化/性格/下月）月度报告；保留"是否移动脚本"提示
  - `ollama_host.py` — 动态解析 WSL 默认网关（Windows 宿主）IP，供上面脚本访问 Windows Ollama
- **Ollama 关键环境**：WSL 内 Ollama 无 GPU 仅 0.5 tok/s 不可用；Windows 侧装 Ollama（`OLLAMA_HOST=0.0.0.0:11434`）用 Arc iGPU 加速（实测 7-16s 整理一条）。模型：`qwen3:0.6b`
- **systemd（user）**：`rex-observe-watch.service`（90s 轮询自动整理）+ `rex-observe-monthly.timer`（每月1日09:00 生成上月报告）。管理：`systemctl --user status|restart`
- **git**：脚本已入识字系统仓库（`scripts/rex_observe.py` 等）

## Environment

- **Python 3** — no requirements, stdlib only (no pip packages)
- `.env` contains: `FLOWUS_TOKEN`, `GITHUB_TOKEN`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`
- `.env` is gitignored — never commit it
- `books_from_flowus.json` is also gitignored (contains FlowUs page UUIDs)

## Conventions

- All paths are absolute (`/mnt/d/rex-识字系统/...`) in Python scripts
- Character extraction: `'\u4e00' <= c <= '\u9fff'` (CJK Unified Ideographs)
- Book status flow: FlowUs select field → `character_bank.json` `status`
- New books get `text_source: "pending"` until character text is extracted
- `auto_sync.py` auto-commits and pushes after sync (`auto-sync YYYY-MM-DD`)
- 书单批量录入（`batch_import_books.py`），两种输入源：
  - 电脑端：`rex-识字系统/books.txt`，用后清空、已 gitignore、不提交 → `python scripts/batch_import_books.py`
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
