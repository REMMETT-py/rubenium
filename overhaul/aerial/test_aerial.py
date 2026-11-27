"""Rubenium League tests: physics, match rules, points, ladder, replays and bots. No Qt.
Run: python overhaul/aerial/test_aerial.py   (or with pytest). The game code is read from Rubenium.py itself (the
"SECTION: aerial" blocks before the drawing code), so these always test what ships."""
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def load() -> dict:
    src = open(os.path.join(REPO, "Rubenium.py"), encoding="utf-8").read()
    a = src.index("# SECTION: aerial (sim)")
    b = src.index("# SECTION: aerial (drawing)")
    ns = {"__name__": "aerial_test"}
    exec(compile(src[a:b], "Rubenium.py:aerial", "exec"), ns)
    return ns


A = load()
I = A["AerialInput"]
T = A["AERIAL_TUNE"]


def sim(kinds=(0, 0)):
    s = A["AerialSim"](kinds)
    s.kickoff(0)
    s.frozen = False
    return s


# ------------------------------------------------------------------------------------------------ maths and physics
def test_trig():
    for k in range(-400, 400):
        x = k * 0.037
        assert abs(A["aerial_sin"](x) - math.sin(x)) < 1e-8
        assert abs(A["aerial_cos"](x) - math.cos(x)) < 1e-8
        y = math.sin(k) * 3
        assert abs(A["aerial_atan2"](y, x) - math.atan2(y, x)) < 1e-8


def test_jump_heights():
    s = sim()
    c = s.cars[0]
    top = 0.0
    for i in range(240):
        s.step([I(jump=i < 30), I()])
        top = max(top, c.y)
    assert 220 < top - c.r < 300, top
    s = sim()
    c = s.cars[0]
    top = 0.0
    for i in range(300):
        s.step([I(jump=(i < 30) or (36 <= i < 40)), I()])
        top = max(top, c.y)
    assert 430 < top - c.r < 560, top


def test_drive_and_boost_caps():
    s = sim()
    c = s.cars[0]
    c.boost = 100
    for _ in range(600):
        s.step([I(ix=1, boost=True), I()])
        assert math.hypot(c.vx, c.vy) <= T["car_max"] + 1e-6
    s = sim()
    c = s.cars[0]
    for _ in range(360):
        s.step([I(ix=1), I()])
    assert math.hypot(c.vx, c.vy) <= T["drive_max"] + 1


def test_boost_refills_on_ground_not_in_air():
    s = sim()
    c = s.cars[0]
    c.boost = 10.0
    for _ in range(120):
        s.step([I(), I()])
    assert c.boost > 40.0                       # about 40 a second on the ground
    s = sim()
    c = s.cars[0]
    c.boost = 10.0
    c.y, c.vy, c.ground, c.ground_lock = 700.0, 0.0, False, 10
    for _ in range(30):
        s.step([I(), I()])
        assert c.ground is False
    assert abs(c.boost - 10.0) < 1e-9


def test_flip_reset_gives_the_jump_back():
    s = sim()
    c, b = s.cars[0], s.ball
    s.ball_held = False
    c.reset(0.0, 600.0, 1.0)
    c.roll = -1.0                               # wheels up
    c.ground, c.jumped, c.has_action, c.ground_lock = False, True, False, 30
    c.vx, c.vy = 0.0, 400.0
    b.x, b.y, b.vx, b.vy = 0.0, 600.0 + c.r + T["ball_r"] + 20, 0.0, 0.0
    got = False
    for _ in range(60):
        s.step([I(), I()])
        got = got or any(e[0] == "reset" for e in s.ev)
    assert got and c.has_action


def test_flip_hits_harder_than_a_bump():
    def hit(flip: bool) -> float:
        s = sim()
        c, b = s.cars[0], s.ball
        s.ball_held = False
        c.reset(-900.0, c.r, 1.0)
        b.x, b.y = 0.0, T["ball_r"]
        st = 0
        for _ in range(400):
            gap, j = b.x - c.x, False
            if flip:
                if st == 0 and gap < 330:
                    j, st = True, 1
                elif st == 1:
                    st = 2
                elif st == 2 and gap < 230:
                    j, st = True, 3
            s.step([I(ix=1, jump=j), I()])
            if any(e[0] == "touch" for e in s.ev):
                return math.hypot(b.vx, b.vy)
        return 0.0
    assert hit(True) > hit(False) > 0


def test_nothing_escapes_fuzz():
    rnd = random.Random(5)
    hw, h = T["arena_hw"] + T["goal_d"], T["arena_h"]
    for m in range(25):
        s = sim((m % 3, (m + 1) % 3))
        for _ in range(1200):
            ins = [I(rnd.choice((-1, 0, 1)), rnd.choice((-1, 0, 1)), rnd.randrange(-1, 1024), 0, rnd.random() < 0.5,
                     rnd.random() < 0.2, rnd.random() < 0.05) for _ in (0, 1)]
            s.step(ins)
            for body in (s.ball, *s.cars):
                assert all(math.isfinite(v) for v in (body.x, body.y, body.vx, body.vy))
                assert -hw - 60 < body.x < hw + 60 and -60 < body.y < h + 60, (body.x, body.y)
            assert math.hypot(s.ball.vx, s.ball.vy) <= T["ball_max"] + 1e-6
            if s.ball_in_goal() >= 0:
                s.kickoff(1)
                s.frozen = False


# ------------------------------------------------------------------------------------------------ the match
def test_goal_only_when_the_whole_ball_is_in():
    s = sim()
    b, hw, R = s.ball, s.arena.hw, T["ball_r"]
    b.x = hw + R - 1.0
    assert s.ball_in_goal() == -1
    b.x = hw + R + 1.0
    assert s.ball_in_goal() == 0
    b.x = -(hw + R + 1.0)
    assert s.ball_in_goal() == 1


def test_match_rules():
    m = A["AerialMatch"]((0, 0), seed=3, match_s=10.0, replays=True)
    assert m.phase == m.COUNT
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    assert m.phase == m.LIVE
    clock = m.clock
    for _ in range(120):
        m.step([I(), I()])
    assert abs((clock - m.clock) - 1.0) < 0.02
    # a goal pauses the clock, replays, then a new kickoff; skipping needs the player's jump
    m.sim.ball.x, m.sim.ball.y, m.sim.ball.vx = m.sim.arena.hw - 20, 300.0, 3000.0
    m.sim.ball_held = False
    for _ in range(20):
        m.step([I(), I()])
    assert m.score == [1, 0] and m.phase == m.GOAL
    c = m.clock
    while m.phase == m.GOAL:
        m.step([I(), I()])
    assert m.phase == m.REPLAY and m.clock == c
    m.step([I(jump=True, skip=True), I()])
    assert m.phase == m.COUNT


def test_zero_waits_for_the_floor_and_overtime():
    m = A["AerialMatch"]((0, 0), seed=4, match_s=1.0, replays=False)
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    b = m.sim.ball
    b.y, b.vy = 800.0, 0.0
    m.sim.ball_held = False
    for _ in range(130):
        m.step([I(), I()])
    assert m.waiting_floor or m.overtime
    for _ in range(400):
        m.step([I(), I()])
    assert m.overtime and m.phase in (m.COUNT, m.LIVE)        # 0-0: overtime with a new kickoff


def test_points_and_save():
    m = A["AerialMatch"]((0, 0), seed=1, match_s=60.0, replays=False)
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    s = m.sim
    s.ball_held = False
    c = s.cars[0]
    c.reset(-s.arena.hw + 200, c.r, 1.0)
    b = s.ball
    b.x, b.y, b.vx, b.vy = -s.arena.hw + 700, T["ball_r"] + 5, -2200.0, 0.0
    labels = []
    for _ in range(80):
        m.step([I(), I()])
        labels += [e[2] for e in m.ev if e[0] == "points"]
    assert any(x in ("Save", "Epic Save") for x in labels), labels
    assert c.stats["saves"] == 1 and c.stats["score"] >= 50


def test_determinism_snapshot_and_replay():
    def run(seed):
        return A["aerial_bot_match"]("halo", "ember", seed=seed, match_s=15.0)
    r1, r2 = run(9), run(9)
    assert r1["score"] == r2["score"] and r1["ticks"] == r2["ticks"] and r1["stats"] == r2["stats"]
    m = A["AerialMatch"]((1, 2), seed=11, match_s=20.0)
    a, b = A["AerialBot"](0, "vex", 1), A["AerialBot"](1, "torque", 2)
    log0, log1 = [], []
    for k in range(1500):
        x, y = a.think(m), b.think(m)
        log0.append(x.pack())
        log1.append(y.pack())
        m.step([x, y])
        if k == 700:
            snap, mid = m.snapshot(), m.state_hash()
    end = m.state_hash()
    m.restore(snap)
    assert m.state_hash() == mid
    for x, y in zip(log0[701:], log1[701:]):
        m.step([I.unpack(x), I.unpack(y)])
    assert m.state_hash() == end
    rep = A["aerial_unpack_replay"](A["aerial_pack_replay"]({"seed": 11, "kinds": [1, 2], "in0": log0, "in1": log1}))
    m2 = A["AerialMatch"]((1, 2), seed=11, match_s=20.0)
    for x, y in zip(rep["in0"], rep["in1"]):
        m2.step([I.unpack(x), I.unpack(y)])
    assert m2.state_hash() == end


def test_input_packing():
    rnd = random.Random(2)
    for _ in range(2000):
        x = I(rnd.choice((-1, 0, 1)), rnd.choice((-1, 0, 1)), rnd.randrange(-1, 1024), rnd.choice((-1, 0, 1)),
              rnd.random() < .5, rnd.random() < .5, rnd.random() < .5, rnd.random() < .5)
        y = I.unpack(x.pack())
        assert (x.ix, x.iy, x.aim, x.rot, x.boost, x.jump, x.roll, x.skip) == (y.ix, y.iy, y.aim, y.rot, y.boost, y.jump,
                                                                                y.roll, y.skip)


# ------------------------------------------------------------------------------------------------ the ladder
def test_ranks():
    r = A["aerial_rank"]
    assert r(0)["label"] == "Rookie 1 · Div I"
    assert r(539)["label"] == "Rookie 3 · Div III"
    assert r(540)["label"] == "Challenger 1 · Div I"
    assert r(1259)["name"] == "Challenger" and r(1260)["name"] == "Elite"
    assert r(3240)["name"] == "Rubenite" and r(99999)["label"] == "Rubenite 3 · Div III"
    assert len({r(x)["index"] for x in range(0, 4600, 5)}) == 45


def test_mmr_change():
    f = A["aerial_mmr_change"]
    assert f(500, 500, True, 1.0) == 8 and f(500, 500, False, 1.0) == -8
    assert f(500, 500, False, 1.25) == -10
    assert f(0, 4600, True, 1.0) == 16 and f(4600, 0, True, 1.0) == 1 and f(4600, 0, False, 1.0) == -16


def test_series_and_shield():
    L = A["AerialLadder"]({"mmr": 535.0})
    out = L.result(590, True)
    assert L.mmr == 539.0 and L.series and L.series["bot"] == "ember" and L.series["need"] == 3
    L.result(590, True)
    out = L.result(590, True)
    assert out["promoted"] and L.mmr == 540.0 and L.shield == 3
    for _ in range(3):
        L.result(2000, False)
    assert L.mmr == 540.0                       # shielded
    L.result(2000, False)
    assert L.mmr < 540.0
    L2 = A["AerialLadder"]({"mmr": 1255.0})
    L2.result(1320, True)
    assert L2.series and L2.series["bot"] == "halo"
    L2.result(1320, False)
    L2.result(1320, False)
    assert L2.series is None and L2.mmr == 1260 - 80


def test_long_grind():
    """Winning every ranked match against opponents at your MMR: about 70 matches to Challenger, 420 to Rubenite."""
    L = A["AerialLadder"]()
    n = 0
    seen = {}
    while L.mmr < 3240 and n < 2000:
        L.result(L.mmr, True)
        n += 1
        r = A["aerial_rank"](L.mmr)["rank"]
        seen.setdefault(r, n)
    assert 60 <= seen[1] <= 85 and 380 <= seen[4] <= 480, seen


# ------------------------------------------------------------------------------------------------ bots
def test_bots_finish_and_play_their_rank():
    t0 = time.perf_counter()
    r = A["aerial_bot_match"]("pip", "pip", seed=2, match_s=20.0)
    assert not r["timeout"]
    wins = 0
    for seed in range(1, 6):                    # the top Champion against the weakest Rookie
        r = A["aerial_bot_match"]("apex", "pip", seed=seed, match_s=30.0)
        wins += r["winner"] == 0
    assert wins >= 4, wins
    assert time.perf_counter() - t0 < 120


if __name__ == "__main__":
    fails = 0
    for k, f in list(globals().items()):
        if k.startswith("test_") and callable(f):
            t = time.perf_counter()
            try:
                f()
                print("PASS %-40s %.1fs" % (k, time.perf_counter() - t))
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL %-40s %r" % (k, e))
    print("%d failed" % fails)
    sys.exit(1 if fails else 0)
