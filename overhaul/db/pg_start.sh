#!/bin/bash
# Starts a throwaway local Postgres 16 for the tests (socket in /var/tmp/pg, port 5433) if it is not running.
D=/var/tmp/pg; BIN=$(ls -d /usr/lib/postgresql/*/bin | sort -V | tail -1)
pg_isready -q -h $D -p 5433 2>/dev/null && exit 0
mkdir -p $D && chown postgres: $D
[ -f $D/data/PG_VERSION ] || su postgres -c "$BIN/initdb -D $D/data -U postgres --auth=trust >/dev/null"
su postgres -c "$BIN/pg_ctl -D $D/data -o '-p 5433 -k $D' -l $D/log -w start >/dev/null"
