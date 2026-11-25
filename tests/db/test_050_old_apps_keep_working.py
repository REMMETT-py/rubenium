# Old apps keep calling the server functions they know until min_build moves (DECISIONS: never rename, drop or
# change an rb_* function's arguments or what it returns).
#  - compat_7_0.json: every call the 7.0 app makes (overhaul/db/rpc_calls.py on the 7.0 Rubenium.py), with the
#    argument names it sends: the function must exist, players must be allowed to call it (except the admin's),
#    and one version of it must take those argument names.
#  - compat_signatures.json: every rb_* function players could call on 25/11/2026: it must still exist with the same
#    arguments and the same return type.
# The repo migrations alone do not hold the functions made directly on the live server (see the audit), so this
# test needs the live snapshot (RB_BASELINE) and is skipped without it.
NEEDS_LIVE_SNAPSHOT = True
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
# switched off on purpose before 7.0 (the app shows a message): rb_sell (quick sell left for the market, 2.2) and
# rb_swap_create (making item swaps closed in 5.12)
RETIRED = {"rb_sell", "rb_swap_create"}
PRE_LOGIN = {"rb_username_free", "rb_device_free", "rb_login_for", "rb_reset_ask", "rb_reset_status", "rb_swaps_list"}


def test(connect):
    c = connect()
    rows = c.execute("""select p.proname, coalesce(p.proargnames, '{}'), p.pronargs, p.pronargdefaults,
                               has_function_privilege('authenticated', p.oid, 'execute'),
                               has_function_privilege('anon', p.oid, 'execute'),
                               p.oid::regprocedure::text, pg_get_function_arguments(p.oid), pg_get_function_result(p.oid)
                          from pg_proc p where p.pronamespace = 'public'::regnamespace""").fetchall()
    by_name = {}
    for r in rows:
        by_name.setdefault(r[0], []).append(r)
    problems = []
    for call in json.load(open(os.path.join(HERE, "compat_7_0.json"))):
        fn, args = call["fn"], call["args"]
        where = f"{fn} (Rubenium.py 7.0 line {call['lines'][0]})"
        versions = by_name.get(fn)
        if not versions:
            problems.append(f"{where}: gone")
            continue
        role = 5 if fn in PRE_LOGIN else 4
        if not fn.startswith("rb_admin") and fn not in RETIRED and not any(v[role] for v in versions):
            problems.append(f"{where}: no longer callable by {'anon' if role == 5 else 'players'}")
        if args is not None and not any(set(args) <= set(v[1][:v[2]]) for v in versions):
            problems.append(f"{where}: no version takes ({', '.join(args)})")
    now = {r[6]: r for r in rows}
    for s in json.load(open(os.path.join(HERE, "compat_signatures.json"))):
        r = now.get(s["sig"])
        if r is None:
            problems.append(f"{s['sig']}: gone")
        elif r[7] != s["args"] or r[8] != s["returns"]:
            problems.append(f"{s['sig']}: was ({s['args']}) -> {s['returns']}, now ({r[7]}) -> {r[8]}")
    assert not problems, "old apps would break:\n  " + "\n  ".join(problems)
