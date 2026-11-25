#!/bin/bash
# Builds a fresh local database the way the Supabase SQL editor would: the Supabase stand-in (shim.sql), then every
# migration in number order, each file as one transaction (_down.sql files skipped). Prints ok / FAIL per file.
# Needs a Postgres 16+ server. Settings: PGHOST, PGPORT, PGUSER (defaults: /var/tmp/pg, 5433, postgres), DB (rubenium).
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/../.." && pwd)"
export PGHOST="${PGHOST:-/var/tmp/pg}" PGPORT="${PGPORT:-5433}" PGUSER="${PGUSER:-postgres}"
DB="${DB:-rubenium}"
psql -q -d postgres -c "drop database if exists $DB" -c "create database $DB" >/dev/null 2>&1 || exit 1
psql -q -v ON_ERROR_STOP=1 -d "$DB" -c "alter database $DB set search_path = \"\$user\", public, extensions" >/dev/null
psql -q -1 -v ON_ERROR_STOP=1 -d "$DB" -f "$here/shim.sql" >/dev/null || exit 1
fail=0
for f in $(ls "$repo"/supabase/migrations/*.sql | grep -v _down.sql | sort -V); do
  out=$(psql -q -1 -v ON_ERROR_STOP=1 -d "$DB" -f "$f" 2>&1 >/dev/null | grep ERROR)
  if [ -n "$out" ]; then echo "FAIL $(basename "$f"): $out"; fail=1; else echo "ok   $(basename "$f")"; fi
done
exit $fail
