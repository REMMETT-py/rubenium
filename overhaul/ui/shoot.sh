#!/bin/bash
# overhaul/ui/shoot.sh OUT [--online] [--admin] STEP...   (local stand-in server; see shoot.py)
set -u
OUT=$1; shift
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
export PGHOST=${PGHOST:-/var/tmp/pg} PGPORT=${PGPORT:-5433} PGUSER=${PGUSER:-postgres}
export RUBENIUM_PC=crawl-pc
PORT=${PORT:-54331}
ONLINE=""; WHO=Tester
while [ $# -gt 0 ]; do case "$1" in --online) ONLINE=--online; shift;; --admin) WHO=Boss; ONLINE=--online; shift;; *) break;; esac; done
mkdir -p "$OUT"; rm -f "$OUT"/*.png
if [ -z "${KEEP_DB:-}" ] || ! psql -X -At -d rb_shoot -c "select 1" >/dev/null 2>&1; then
psql -q -X -d postgres -c "drop database if exists rb_shoot with (force)" -c "create database rb_shoot template rb_template" || exit 1
psql -X -At -d rb_shoot -c "select t.player('Tester', 25000, 40), t.player('Boss', 5000, 5);" >/dev/null
psql -q -X -d rb_shoot -c "update public.profiles set admin = true where username = 'Boss'"
fi
UID_=$(psql -X -At -d rb_shoot -c "select id from public.profiles where username = '$WHO'")
python3 "$HERE/../stub/server.py" --db rb_shoot --port $PORT >/dev/null 2>&1 &
SRV=$!; trap 'kill $SRV 2>/dev/null' EXIT; sleep 1
home=/tmp/shoot_home_$WHO; rm -rf "$home"; mkdir -p "$home/Documents/Rubenium"
printf '{"screens": [{"name": "s", "x": 0, "y": 0, "width": 1920, "height": 1080, "logicalDpi": 96, "dpr": 1}]}' > /tmp/shoot_screen.json
if [ -n "$ONLINE" ]; then python3 - "$home/Documents/Rubenium/session.dat" "$UID_" "$WHO" <<'PY'
import base64, json, sys, time
path, uid, user = sys.argv[1:]
s = {"access_token": "stub." + uid, "refresh_token": "stub." + uid, "expires_at": time.time() + 86400, "username": user, "user_id": uid}
open(path, "wb").write(base64.b64encode(json.dumps(s).encode()))
PY
fi
printf '{"schema": 3, "v53_fresh": true, "v5_fresh": true, "lang": "en", "tutorial_done": true}' > "$home/Documents/Rubenium/settings.json"
HOME="$home" QT_QPA_PLATFORM="offscreen:configfile=/tmp/shoot_screen.json" RUBENIUM_API=http://127.0.0.1:$PORT timeout 600 \
  python3 "$HERE/shoot.py" "$REPO/${SCRIPT:-Rubenium.py}" --out "$OUT" $ONLINE "$@" 2>&1 | grep -v "^qt\.\|propagateSizeHints" | tail -30
