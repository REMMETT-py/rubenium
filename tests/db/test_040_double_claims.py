# The same claim sent 8 times at once (a double click, two PCs, a script) pays exactly once.
import threading

CLAIMS = [("rb_spin", "select public.rb_spin()"), ("rb_login_claim", "select public.rb_login_claim()"),
          ("rb_daily_case", "select public.rb_daily_case()"), ("rb_scratch", "select public.rb_scratch()"),
          ("rb_og_chest_claim", "select public.rb_og_chest_claim('same-req')")]


MAY_REFUSE = {"rb_og_chest_claim"}      # the OG chest is over: refusing is right, paying twice is not


def test(connect):
    admin = connect()
    for name, call in CLAIMS:
        uid = admin.execute("select t.player(%s)", ("P" + name[3:9].replace("_", ""),)).fetchone()[0]
        before = admin.execute("select coins, keys, (select count(*) from rb_items where owner = %s), "
                               "(select count(*) from rb_case_stock where owner = %s) from profiles where id = %s",
                               (uid, uid, uid)).fetchone()
        results, errors = [], []
        go = threading.Barrier(8)

        def one():
            c = connect()
            try:
                c.execute("begin")
                c.execute("select t.act(%s)", (uid,))
                go.wait()
                c.execute(call)
                c.execute("commit")
                results.append(1)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc).splitlines()[0])
            finally:
                c.close()
        th = [threading.Thread(target=one) for _ in range(8)]
        [t.start() for t in th]
        [t.join() for t in th]
        ledger = admin.execute("select count(*) from rb_ledger where owner = %s and (coins > 0 or keys > 0)", (uid,)).fetchone()[0]
        assert results or name in MAY_REFUSE, f"{name}: no call worked ({errors[:1]})"
        assert len(results) <= 1 or ledger <= 1, f"{name}: {len(results)} calls worked, {ledger} payouts"
        rows = admin.execute("select count(*) from rb_items where owner = %s", (uid,)).fetchone()[0]
        assert rows - before[2] <= 3, f"{name}: {rows - before[2]} items from one claim"
