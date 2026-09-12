-- KEIBA NOTE V5.1 - Supabase database setup
-- Run this entire script in Supabase SQL Editor.

create table if not exists public.keiba_records (
  user_id uuid not null references auth.users(id) on delete cascade,
  id text not null,
  date date not null,
  course text not null default 'その他',
  race integer not null default 0,
  type text not null default 'その他',
  inv numeric not null default 0,
  ret numeric not null default 0,
  memo text not null default '',
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);

alter table public.keiba_records enable row level security;

drop policy if exists "Users can read their own records" on public.keiba_records;
create policy "Users can read their own records"
on public.keiba_records for select
to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "Users can insert their own records" on public.keiba_records;
create policy "Users can insert their own records"
on public.keiba_records for insert
to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update their own records" on public.keiba_records;
create policy "Users can update their own records"
on public.keiba_records for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete their own records" on public.keiba_records;
create policy "Users can delete their own records"
on public.keiba_records for delete
to authenticated
using ((select auth.uid()) = user_id);

-- Optional index for date-based queries.
create index if not exists keiba_records_user_date_idx
on public.keiba_records (user_id, date desc);

-- Least-privilege Data API grants for signed-in users.
grant select, insert, update, delete on table public.keiba_records to authenticated;
revoke all on table public.keiba_records from anon;


-- V5.2 AI予想
create table if not exists public.keiba_predictions (
  user_id uuid not null references auth.users(id) on delete cascade,
  id text not null,
  date date not null,
  course text not null default 'その他',
  race integer not null default 0,
  main text not null default '',
  second text not null default '',
  third text not null default '',
  fukusho text not null default '',
  wide text not null default '',
  confidence numeric not null default 0,
  comment text not null default '',
  result text not null default '',
  fukusho_hit boolean not null default false,
  wide_hit boolean not null default false,
  result_entered boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);
alter table public.keiba_predictions enable row level security;
drop policy if exists "Users can read their own predictions" on public.keiba_predictions;
create policy "Users can read their own predictions" on public.keiba_predictions for select to authenticated using ((select auth.uid())=user_id);
drop policy if exists "Users can insert their own predictions" on public.keiba_predictions;
create policy "Users can insert their own predictions" on public.keiba_predictions for insert to authenticated with check ((select auth.uid())=user_id);
drop policy if exists "Users can update their own predictions" on public.keiba_predictions;
create policy "Users can update their own predictions" on public.keiba_predictions for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
drop policy if exists "Users can delete their own predictions" on public.keiba_predictions;
create policy "Users can delete their own predictions" on public.keiba_predictions for delete to authenticated using ((select auth.uid())=user_id);
create index if not exists keiba_predictions_user_date_idx on public.keiba_predictions (user_id,date desc);
grant select,insert,update,delete on table public.keiba_predictions to authenticated;
revoke all on table public.keiba_predictions from anon;
