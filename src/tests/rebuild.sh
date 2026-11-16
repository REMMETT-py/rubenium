cd /home/claude/rubenium/supabase/migrations; P="psql -h /tmp -p 5544 -U postgres -v ON_ERROR_STOP=1 -q"
$P -c "drop schema if exists public cascade; drop schema if exists auth cascade; create schema public;" >/dev/null 2>&1
for f in /tmp/stub2.sql 001_accounts.sql 002_delete_account.sql 003_economy.sql 004_cases_casino.sql 005_friends.sql 008_ultimate_update.sql 008_ultimate_update.sql; do $P -f $f 2>&1 | grep -v NOTICE | head -5; done
