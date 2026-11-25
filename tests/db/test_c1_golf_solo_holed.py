# A modified app says "in the hole" on every first shot, from a spot where the ball cannot be in the cup.
# The server must not pay for it.


def test(connect):
    c = connect()
    uid = c.execute("select t.player('Golfer')").fetchone()[0]
    c.execute("begin"); c.execute("select t.act(%s)", (uid,))
    g = c.execute("select public.rb_golf_solo_start(5)").fetchone()[0]
    c.execute("commit")
    gid = g["id"] if isinstance(g, dict) else g
    coins0 = c.execute("select coins from profiles where id = %s", (uid,)).fetchone()[0]
    for n in range(5):
        c.execute("update rb_golf_solo set last_at = now() - interval '2 seconds', at = now() - interval '5 minutes' where id = %s", (gid,))
        c.execute("begin"); c.execute("select t.act(%s)", (uid,))
        try:
            c.execute("select public.rb_golf_solo_shot(%s, %s, 0.01, 0.01, true)", (gid, n))
            c.execute("commit")
        except Exception:  # noqa: BLE001  (refused: good)
            c.execute("rollback")
    paid = c.execute("select coins from profiles where id = %s", (uid,)).fetchone()[0] - coins0
    holes_in_one = c.execute("select count(*) from unnest((select strokes from rb_golf_solo where id = %s)) s where s = 1", (gid,)).fetchone()[0]
    assert holes_in_one == 0 and paid == 0, f"accepted {holes_in_one} holes in one from the corner, paid {paid} coins"
