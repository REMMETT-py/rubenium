# In a 1v1 with a bet, a modified app claims a hole in one from the corner of the course. The server must refuse it.


def test(connect):
    c = connect()
    a = c.execute("select t.player('Cheater', 10000)").fetchone()[0]
    b = c.execute("select t.player('Honest', 10000)").fetchone()[0]

    def as_(who, sql, args=()):
        c.execute("begin"); c.execute("select t.act(%s)", (who,))
        try:
            r = c.execute(sql, args).fetchone()
            c.execute("commit")
            return r[0] if r else None
        except Exception as exc:  # noqa: BLE001
            c.execute("rollback")
            return exc
    g = as_(a, "select public.rb_golf_create(1000, 3)")
    gid = g["id"]
    as_(b, "select public.rb_golf_join(%s)", (gid,))
    r = as_(a, "select public.rb_golf_shot(%s, 0, 0.5, 0.3, 0, 0.1, 0.01, 0.01, true)", (gid,))
    a_in = c.execute("select a_in, a_strokes[hole] from rb_golf where id = %s", (gid,)).fetchone()
    assert isinstance(r, Exception) or not a_in[0], f"a hole in one from the corner was accepted: {a_in}"
