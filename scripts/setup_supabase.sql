-- Rex 识字系统 · Supabase 建表 + RLS
-- 用法：粘贴到 Supabase Dashboard → SQL Editor → 运行

-- 确保 words 表已启用 RLS（已有但可能未开）
alter table if exists words enable row level security;

-- 删除旧策略（幂等），重建 insert + select 策略
drop policy if exists "words_ro_i" on words;
drop policy if exists "words_insert" on words;
create policy "words_ro_i" on words for select using (true);
create policy "words_insert" on words for insert with check (true);

-- 艾宾浩斯复习状态表（每字一行）
create table if not exists reviews (
  char text primary key check (char ~ '^[一-龥]$'),
  stage int default 0 check (stage between 0 and 5),
  last_review date,
  next_review date,
  updated_by text default '',
  updated_at timestamptz default now()
);

alter table reviews enable row level security;
drop policy if exists "reviews_ro" on reviews;
drop policy if exists "reviews_insert" on reviews;
drop policy if exists "reviews_update" on reviews;
create policy "reviews_ro" on reviews for select using (true);
create policy "reviews_insert" on reviews for insert with check (true);
create policy "reviews_update" on reviews for update using (true) with check (true);
