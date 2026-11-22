-- 6.2.5: the pawn shop takes 5 proposals an hour (offers and refusals), so the refuse-and-offer loop can't be spammed.
-- Applied live: table rb_pawn_props (one row per offer or refusal), and rb_pawn_trade checks the last hour first.
create table if not exists public.rb_pawn_props (id bigserial primary key, owner uuid not null, at timestamptz not null default now());
create index if not exists rb_pawn_props_owner_at on public.rb_pawn_props (owner, at);
alter table public.rb_pawn_props enable row level security;
-- the check is inserted just before the item lookup in rb_pawn_trade (see the live function); a failed call rolls back its row
