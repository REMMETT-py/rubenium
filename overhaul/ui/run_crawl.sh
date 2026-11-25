#!/bin/bash
# Pictures of every page: offline (logged out) and online (logged in on the local stand-in server), in English and
# French, as a player and as the admin. Never talks to the real server.
#   overhaul/ui/run_crawl.sh OUT_DIR [Rubenium.py]
# Needs the local Postgres (overhaul/db/pg_start.sh) and the test template database (overhaul/db/run_tests.py,
# with RB_BASELINE for the live-like server). Screens are simulated (Qt offscreen): 1920x1080 unless given.
set -u
OUT=${1:?out dir}; SCRIPT=${2:-Rubenium.py}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
export PGHOST=${PGHOST:-/var/tmp/pg} PGPORT=${PGPORT:-5433} PGUSER=${PGUSER:-postgres}
export RUBENIUM_PC=crawl-pc
PORT=${PORT:-54329}
mkdir -p "$OUT"
psql -q -X -d postgres -c "drop database if exists rb_stub with (force)" -c "create database rb_stub template rb_template" || exit 1
# Two accounts: a player with some coins and keys, and the admin.
read -r PLAYER ADMIN < <(psql -X -At -d rb_stub -F ' ' -c "
  select t.player('Tester', 25000, 40), t.player('Boss', 5000, 5);")
psql -q -X -d rb_stub -c "update public.profiles set admin = true where id = '$ADMIN'" || exit 1
python3 "$HERE/../stub/server.py" --db rb_stub --port $PORT --calls "$OUT/server_calls.json" &
SRV=$!
trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null' EXIT
sleep 1
status=0
run() {   # name lang online-user-id-or-empty username screen(WxH)
  local name=$1 lang=$2 uid=$3 user=$4 screen=${5:-1920x1080} home="$OUT/home_$1"
  printf '{"screens": [{"name": "s", "x": 0, "y": 0, "width": %s, "height": %s, "logicalDpi": 96, "dpr": 1}]}' \
      "${screen%x*}" "${screen#*x}" > "$OUT/screen_$name.json"
  mkdir -p "$home/Documents/Rubenium"
  rm -f "$home/Documents/Rubenium/rubenium.log"
  if [ -n "$uid" ]; then
    python3 - "$home/Documents/Rubenium/session.dat" "$uid" "$user" <<'PY'
import base64, json, sys, time
path, uid, user = sys.argv[1:]
s = {"access_token": "stub." + uid, "refresh_token": "stub." + uid, "expires_at": time.time() + 86400,
     "username": user, "user_id": uid}
open(path, "wb").write(base64.b64encode(json.dumps(s).encode()))
PY
  fi
  printf '{"schema": 3, "v53_fresh": true, "v5_fresh": true, "lang": "%s", "tutorial_done": true}' "$lang" > "$home/Documents/Rubenium/settings.json"
  local extra=""; [ -n "$uid" ] && extra=--online
  HOME="$home" QT_QPA_PLATFORM="offscreen:configfile=$OUT/screen_$name.json" RUBENIUM_API=http://127.0.0.1:$PORT timeout 1200 python3 "$HERE/crawl.py" "$REPO/$SCRIPT" \
      --out "$OUT/$name" --lang "$lang" $extra > "$OUT/$name.out" 2>&1 || status=1
  grep "^CRAWL" "$OUT/$name.out" | sed "s/^/$name: /" || echo "$name: did not finish"
}
run offline_en en "" ""
run player_en en "$PLAYER" Tester
run player_fr fr "$PLAYER" Tester
run admin_en en "$ADMIN" Boss
run player_small en "$PLAYER" Tester 1366x768
run offline_small_fr fr "" "" 1280x720
exit $status
