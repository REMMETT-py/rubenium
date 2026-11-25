import threading


def test(connect):
    c = connect()
    uid = c.execute("select t.player('Ogfan')").fetchone()[0]
    c.execute("insert into rb_items (owner, item, origin) values (%s, 'tag:og', 'og')", (uid,))
    c.execute("update profiles set og_coupon_50 = false where id = %s", (uid,))
    go = threading.Barrier(6)

    def one():
        k = connect()
        try:
            k.execute("begin"); k.execute("select t.act(%s)", (uid,))
            go.wait()
            k.execute("select public.rb_hello2(%s, 2026112301)", ("a" * 40,))
            k.execute("commit")
        except Exception:  # noqa: BLE001
            pass
        finally:
            k.close()
    th = [threading.Thread(target=one) for _ in range(6)]
    [t.start() for t in th]; [t.join() for t in th]
    n = c.execute("select count(*) from rb_items where owner = %s and item = 'coupon:og'", (uid,)).fetchone()[0]
    assert n == 1, f"{n} OG coupons"
