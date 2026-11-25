-- Undo of 077_v90_reset.sql (the reset itself is undone from the rb_bak90_* copies).
drop function if exists public.rb_reset_economy_90(bigint, integer);
