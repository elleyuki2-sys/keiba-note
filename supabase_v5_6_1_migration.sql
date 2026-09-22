-- KEIBA NOTE V5.6.1 migration
-- Existing keiba_predictions / keiba_records data is preserved.

alter table public.keiba_predictions add column if not exists race_key text not null default '';
alter table public.keiba_predictions add column if not exists race_name text not null default '';
alter table public.keiba_predictions add column if not exists race_condition text not null default '';
alter table public.keiba_predictions add column if not exists distance text not null default '';
alter table public.keiba_predictions add column if not exists surface text not null default '';
alter table public.keiba_predictions add column if not exists field_size integer not null default 0;
alter table public.keiba_predictions add column if not exists going text not null default '';
alter table public.keiba_predictions add column if not exists fourth text not null default '';
alter table public.keiba_predictions add column if not exists fifth text not null default '';
alter table public.keiba_predictions add column if not exists status text not null default 'HOLD';
alter table public.keiba_predictions add column if not exists prediction_time timestamptz not null default now();
alter table public.keiba_predictions add column if not exists market_snapshot jsonb not null default '{}'::jsonb;
alter table public.keiba_predictions add column if not exists horse_evaluations jsonb not null default '{}'::jsonb;
create index if not exists keiba_predictions_user_race_key_idx on public.keiba_predictions (user_id, race_key);
