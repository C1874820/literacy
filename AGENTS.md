# Rex 识字系统

Track Rex's Chinese character literacy progress. Data flows: FlowUs (book list + learning records) → `character_bank.json` → HTML progress page + GitHub Pages.

## Architecture

- **Data source**: FlowUs database (`DATABASE_ID` in scripts) + Supabase `words` table (web entry)
- **Central data file**: `character_bank.json` — books, chars, freq, learning status, log
- **Sync pipeline**: `scripts/run_sync.sh` → `auto_sync.py` (cron weekdays 10:00)
- **Web app**: `progress/index.html` — SPA with Supabase-powered review/entry tabs
- **Generated files**: `progress/data.json`, `progress/learned.json`, `progress/char_meta.json` (all from `generate_progress_html.py`)
- **Deployment**: GitHub Pages via `scripts/deploy_github.sh`, branch `master`

## Commands

```bash
# Full sync (runs via cron Mon-Fri 10:00)
scripts/run_sync.sh

# Manual sync (needs .env)
source .env && python3 scripts/auto_sync.py

# Rebuild character bank from hardcoded book data + FlowUs import
python3 scripts/build_character_bank.py

# Generate progress HTML + JSON files
python3 scripts/generate_progress_html.py

# Record a learning session
python3 scripts/process_log.py "6/28 大卫不可以 不、可"

# CLI progress report
python3 scripts/report.py
python3 scripts/report.py --top 30
python3 scripts/report.py --book "好饿的毛毛虫"

# Update FlowUs progress page
python3 scripts/update_flowus_progress.py
```

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

## FlowUs Database Schema

### Rex阅读记录 (ID: `10df60aa-aee0-4727-adab-f4d99e1cc053`)

| Field | Type | Notes |
|-------|------|-------|
| title | title | Book name |
| 状态 | select | 未读 / 在读 / 已读 |
| 认字情况 | rich_text | Learned chars (e.g. 大、小、上、下) |
| 书籍来源 | select | 纸质书 / 电子书 |

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

- `build_character_bank.py` has hardcoded book character lists (`BOOKS_DATA`) — when adding new books, either add them there or rely on the FlowUs sync to pull text
- `process_log.py` date parsing hardcodes year 2026 for short formats (`6/28` → `2026-06-28`)
- `progress/index.html` embeds Supabase credentials in JS (public anon key, not secret)
- GitHub Pages: `deploy_github.sh` pushes to `master` branch (not `main`)
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
