# 8.0: the server rolls every golf shot with the app's own maths.
#  - a real hole in one (found with the app's simulate()) counts and pays, on all five holes of a solo game;
#  - a weak shot claimed as "in" with the new call does not count;
#  - in a 1 v 1, a claim of "in" from a weak shot is not believed, and a real one is.
import math
import os
import sys

sys.path.insert(0, "/home/user/rubenium/overhaul/golf")
import holes  # noqa: E402


def ace(hid, start=None):
    h = holes.get_hole(hid)
    x, y = start or h["tee"]
    base = math.atan2(h["cup"][1] - y, h["cup"][0] - x)
    for k in range(4000):
        ang = base + ((k % 400) - 200) * 0.0025
        pw = 0.15 + (k // 400) * 0.09
        if holes.simulate(h, x, y, ang, pw)[3]:
            return x, y, ang, pw
    return None


def test(connect):
    c = connect()
    uid = c.execute("select t.player('Golfer')").fetchone()[0]
    c.execute("begin"); c.execute("select t.act(%s)", (uid,))
    g = c.execute("select public.rb_golf_solo_start(5)").fetchone()[0]
    c.execute("commit")
    gid = g["id"]
    hs = [1, 2, 4, 101, 102]                       # holes where the search below finds an ace from the tee
    c.execute("update rb_golf_solo set holes = %s where id = %s", (hs, gid))
    coins0 = c.execute("select coins from profiles where id = %s", (uid,)).fetchone()[0]
    # a weak putt claimed as in: one stroke, not holed
    c.execute("update rb_golf_solo set last_at = now() - interval '2 seconds', at = now() - interval '5 minutes' where id = %s", (gid,))
    c.execute("begin"); c.execute("select t.act(%s)", (uid,))
    tee = holes.get_hole(hs[0])["tee"]
    c.execute("select public.rb_golf_solo_shot(%s, 0, %s, %s, 0.0, 0.05, 0.88, 0.31, true)", (gid, tee[0], tee[1]))
    c.execute("commit")
    st = c.execute("select hole, strokes, pos from rb_golf_solo where id = %s", (gid,)).fetchone()
    assert st[0] == 1 and st[1][0] == 1 and st[2] is not None, f"weak shot counted as in: {st}"
    # from where the server put the ball, play real aces on every hole
    n = 1
    for i, hid in enumerate(hs):
        pos = c.execute("select pos from rb_golf_solo where id = %s", (gid,)).fetchone()[0]
        shot = ace(hid, tuple(pos) if pos else None)
        assert shot, f"no ace found on hole {hid}"
        c.execute("update rb_golf_solo set last_at = now() - interval '2 seconds' where id = %s", (gid,))
        c.execute("begin"); c.execute("select t.act(%s)", (uid,))
        c.execute("select public.rb_golf_solo_shot(%s, %s, %s, %s, %s, %s, 0, 0, false)", (gid, n, *shot))
        c.execute("commit")
        n += 1
    st = c.execute("select state, strokes, paid from rb_golf_solo where id = %s", (gid,)).fetchone()
    assert st[0] == "done", st
    assert st[1] == [2, 1, 1, 1, 1], f"strokes {st[1]}"
    paid = c.execute("select coins from profiles where id = %s", (uid,)).fetchone()[0] - coins0
    assert paid == st[2] and paid > 0, f"paid {paid}, recorded {st[2]}"

    # 1 v 1 (no bet): a fake "in" from a weak shot is not believed; a real ace is
    a = c.execute("select t.player('GolfA')").fetchone()[0]
    b = c.execute("select t.player('GolfB')").fetchone()[0]
    c.execute("begin"); c.execute("select t.act(%s)", (a,))
    d = c.execute("select public.rb_golf_create(0, 3)").fetchone()[0]
    c.execute("commit")
    gid = d["id"]
    c.execute("begin"); c.execute("select t.act(%s)", (b,))
    c.execute("select public.rb_golf_join(%s)", (gid,))
    c.execute("commit")
    c.execute("update rb_golf set holes = '{1,2,4}' where id = %s", (gid,))
    g = c.execute("select turn, holes, seq from rb_golf where id = %s", (gid,)).fetchone()
    who = g[0]
    hid = g[1][0]
    tee = holes.get_hole(hid)["tee"]
    c.execute("begin"); c.execute("select t.act(%s)", (who,))
    c.execute("select public.rb_golf_shot(%s, %s, %s, %s, 0.0, 0.05, 0.88, 0.31, true)", (gid, g[2], tee[0], tee[1]))
    c.execute("commit")
    row = c.execute("select a, a_in, b_in, a_strokes, b_strokes from rb_golf where id = %s", (gid,)).fetchone()
    mine_in = row[1] if who == row[0] else row[2]
    assert not mine_in, f"1 v 1 believed a fake 'in': {row}"
    shots = c.execute("select shots from rb_golf where id = %s", (gid,)).fetchone()[0]
    assert shots and shots[-1]["in"] is False, shots
