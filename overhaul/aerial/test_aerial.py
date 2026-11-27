"""Rubenium League tests (the flat top-down pitch): driving, the powerslide, boost pads, kickoffs, match rules, points,
ladder, replays and bots. No Qt.
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


def test_drive_and_boost_caps():
    s = sim()
    c = s.cars[0]
    c.reset(-1900.0, 800.0, 0.0, 0.0)                     # a lane clear of the ball
    for _ in range(200):
        s.step([I(thr=1), I()])
    v = c.speed()
    assert T["drive_max"] * 0.95 < v <= T["drive_max"] + 1, v
    c.reset(-1900.0, 800.0, 0.0, 100.0)
    for _ in range(150):
        s.step([I(thr=1, boost=True), I()])
    assert c.speed() <= T["boost_max"] + 1, c.speed()
    assert c.speed() > T["drive_max"] * 1.2, c.speed()
    assert c.boost < 100.0                                  # boost burns
    for _ in range(240):                                    # no refill on its own, away from the pads
        s.step([I(), I()])
    assert c.boost < 100.0


def test_powerslide_keeps_momentum_without_making_speed():
    s = sim()
    c = s.cars[0]
    c.reset(-1500.0, 0.0, 0.0, 0.0)
    for _ in range(240):
        s.step([I(thr=1), I()])
    v0 = c.speed()
    a0 = c.a
    for _ in range(50):
        s.step([I(thr=1, steer=8, drift=True), I()])
        assert c.speed() <= max(v0, T["drive_max"]) + 1.0
    turned = abs(A["aerial_wrap"](c.a - a0))
    assert c.speed() > v0 * 0.55, (c.speed(), v0)          # the slide keeps most of the speed
    s2 = sim()
    c2 = s2.cars[0]
    c2.reset(-1500.0, 0.0, 0.0, 0.0)
    for _ in range(240):
        s2.step([I(thr=1), I()])
    a1 = c2.a
    for _ in range(50):
        s2.step([I(thr=1, steer=8), I()])
    assert turned > abs(A["aerial_wrap"](c2.a - a1)) * 0.9  # and turns at least as hard as gripping


def test_cars_differ():
    specs = A["AERIAL_CARS"]
    assert [x["name"] for x in specs] == ["Comet", "Blade", "Titan"]
    assert specs[1]["turn"] > specs[0]["turn"] > specs[2]["turn"]
    assert specs[2]["mass"] > specs[0]["mass"] > specs[1]["mass"]


def test_nothing_escapes_fuzz():
    rnd = random.Random(5)
    s = A["AerialSim"]((0, 2))
    s.kickoff(0)
    s.frozen = False
    for _ in range(6000):
        s.step([I(rnd.choice((-1, 0, 1, 1)), rnd.randint(-8, 8), rnd.random() < .4, rnd.random() < .2),
                I(rnd.choice((-1, 0, 1, 1)), rnd.randint(-8, 8), rnd.random() < .4, rnd.random() < .2)])
        if s.ball_in_goal() >= 0:
            s.kickoff(rnd.randrange(3))
            s.frozen = False
        for c in s.cars:
            assert s.arena.inside(c.x, c.y), (c.x, c.y)
        assert abs(s.ball.y) < T["hw"] + 1 and abs(s.ball.x) < T["hl"] + T["goal_d"] + 1


def test_pads_give_boost_and_respawn():
    s = sim()
    c = s.cars[0]
    pads = s.arena.pads
    assert sum(1 for p in pads if p[2]) == 6 and len(pads) > 20
    k = next(i for i, p in enumerate(pads) if p[2])
    x, y, _ = pads[k]
    c.reset(x, y, 0.0, 10.0)
    s.step([I(), I()])
    assert c.boost == 100.0 and T["big_respawn"] - 0.1 < s.pad_t[k] <= T["big_respawn"]
    c.boost = 10.0
    s.step([I(), I()])
    assert c.boost == 10.0                                  # taken: empty until it respawns
    for _ in range(int(T["big_respawn"] * 120) - 10):
        s.step([I(), I()])
    assert c.boost == 10.0
    for _ in range(20):
        s.step([I(), I()])
    assert c.boost == 100.0                                 # back, and taken again


def test_kickoffs_are_mirrored():
    s = A["AerialSim"]((0, 0))
    for v in range(3):
        s.kickoff(v)
        a, b = s.cars
        assert abs(a.x + b.x) < 1e-9 and abs(a.y + b.y) < 1e-9 and a.boost == b.boost
        assert abs(A["aerial_wrap"](a.a - b.a - math.pi)) < 1e-9 or abs(A["aerial_wrap"](a.a - b.a + math.pi)) < 1e-9


def test_kickoff_settle_stops_kickoff_goals():
    """Both full boost straight at the ball: the touch is capped for a moment, so no goal comes off the kickoff."""
    for v in range(3):
        for kinds in ((0, 0), (2, 1), (1, 2)):
            m = A["AerialMatch"](kinds, seed=v + 1, match_s=30.0, replays=False)
            m.rng.s = m.rng.s                               # (the kickoff spot comes from the seed)
            for _ in range(int(T["count_s"] * 120) + 2):
                m.step([I(), I()])
            for k in range(int(1.5 * 120)):
                out = []
                for c in m.sim.cars:
                    a = A["aerial_atan2"](m.sim.ball.y - c.y, m.sim.ball.x - c.x)
                    d = A["aerial_wrap"](a - c.a)
                    out.append(I(thr=1, steer=max(-8, min(8, int(d * 16))), boost=True))
                m.step(out)
            assert m.score == [0, 0], (v, kinds, m.score)


def test_goal_only_when_the_whole_ball_is_in():
    s = sim()
    b = s.ball
    b.x, b.y = T["hl"] + T["ball_r"] - 5, 0.0
    assert s.ball_in_goal() == -1
    b.x = T["hl"] + T["ball_r"] + 5
    assert s.ball_in_goal() == 1
    b.x = -b.x
    assert s.ball_in_goal() == 0
    b.x, b.y = T["hl"] + T["ball_r"] + 5, T["goal_hw"] + 50
    assert s.ball_in_goal() == -1


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
    # a shot into orange's goal (+x) counts for blue; the clock stops, a replay, then a new kickoff
    b = m.sim.ball
    b.x, b.y, b.vx, b.vy = T["hl"] - 150, 0.0, 3000.0, 0.0
    m.sim.last_touch = 0
    for _ in range(30):
        m.step([I(), I()])
    assert m.score == [1, 0] and m.phase == m.GOAL
    c = m.clock
    while m.phase == m.GOAL:
        m.step([I(), I()])
    assert m.phase == m.REPLAY and m.clock == c
    m.step([I(skip=True), I()])
    assert m.phase == m.COUNT
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    b = m.sim.ball
    b.x, b.y, b.vx, b.vy = -T["hl"] + 150, 0.0, -3000.0, 0.0
    m.sim.last_touch = 1
    for _ in range(30):
        m.step([I(), I()])
    assert m.score == [1, 1]


def test_overtime():
    m = A["AerialMatch"]((0, 0), seed=4, match_s=1.0, replays=False)
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    for _ in range(140):
        m.step([I(), I()])
    assert m.overtime and m.phase in (m.COUNT, m.LIVE)        # 0-0: overtime with a new kickoff
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    b = m.sim.ball
    b.x, b.y, b.vx, b.vy = T["hl"] - 150, 0.0, 3000.0, 0.0
    m.sim.last_touch = 0
    for _ in range(400):
        m.step([I(), I()])
    assert m.phase == m.OVER and m.winner == 0                # golden goal


def test_points_and_save():
    m = A["AerialMatch"]((0, 0), seed=1, match_s=60.0, replays=False)
    for _ in range(int(3.0 * 120) + 2):
        m.step([I(), I()])
    s = m.sim
    c = s.cars[0]
    c.reset(-T["hl"] + 260, 0.0, 0.0)
    b = s.ball
    b.x, b.y, b.vx, b.vy = -T["hl"] + 900, 0.0, -2400.0, 0.0
    labels = []
    for _ in range(80):
        m.step([I(), I()])
        labels += [e[2] for e in m.ev if e[0] == "points"]
    assert any(x in ("Save", "Epic Save") for x in labels), labels
    assert c.stats["saves"] == 1 and c.stats["score"] >= 50
    assert m.score == [0, 0]


def test_determinism_snapshot_and_replay():
    def run(seed):
        return A["aerial_bot_match"]("halo", "ember", seed=seed, match_s=15.0)
    r1, r2 = run(9), run(9)
    assert r1["score"] == r2["score"] and r1["ticks"] == r2["ticks"] and r1["stats"] == r2["stats"]
    m = A["AerialMatch"]((1, 2), seed=11, match_s=20.0)
    a, b = A["AerialBot"](0, "ruben", 1), A["AerialBot"](1, "nova", 2)
    A["aerial_apply_assist"](m, 0, "ruben")
    A["aerial_apply_assist"](m, 1, "nova")
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
    A["aerial_apply_assist"](m2, 0, "ruben")
    A["aerial_apply_assist"](m2, 1, "nova")
    for x, y in zip(rep["in0"], rep["in1"]):
        m2.step([I.unpack(x), I.unpack(y)])
    assert m2.state_hash() == end


def test_input_packing():
    rnd = random.Random(2)
    for _ in range(2000):
        x = I(rnd.choice((-1, 0, 1)), rnd.randint(-8, 8), rnd.random() < .5, rnd.random() < .5, rnd.random() < .5,
              rnd.randrange(-1, 64), rnd.random() < .5)
        y = I.unpack(x.pack())
        assert (x.thr, x.steer, x.boost, x.drift, x.skip, x.aim, x.shot) == (y.thr, y.steer, y.boost, y.drift, y.skip,
                                                                              y.aim, y.shot)


# ------------------------------------------------------------------------------------------------ the ladder
def test_ranks():
    r = A["aerial_rank"]
    assert r(0)["label"] == "Rookie 1" and r(50)["v"] == 0 and r(0)["v"] == -5
    assert r(350)["label"] == "Challenger 1" and r(650)["label"] == "Master 1" and r(950)["label"] == "Rubenite"
    assert len({r(x)["index"] for x in range(0, 1001, 10)}) == 10
    for i, row in enumerate(A["AERIAL_BOT_ROSTER"]):            # one bot per rank, in order
        assert r(row[3])["index"] == i, row


def test_five_up_five_down():
    L = A["AerialLadder"]()
    for _ in range(4):
        L.result(None, True)
    assert L.r == 0 and L.v == 4
    out = L.result(None, True)
    assert out["promoted"] and L.r == 1 and L.v == 0
    for _ in range(4):
        L.result(None, False)
    assert L.r == 1 and L.v == -4
    out = L.result(None, False)
    assert out["demoted"] and L.r == 0 and L.v == 0
    for _ in range(20):                                          # nothing below Rookie 1
        L.result(None, False)
    assert L.r == 0
    L = A["AerialLadder"]({"r": 9, "v": 0})
    for _ in range(10):
        L.result(None, True)
    assert L.r == 9 and L.v == 5
    assert A["AerialLadder"]({"r": 4, "v": 2}).opponents() == [A["AERIAL_BOT_ROSTER"][4][0]]


def test_climb_needs_wins():
    """Winning every ranked match: 5 wins a rank, 45 from Rookie 1 to Rubenite."""
    L = A["AerialLadder"]()
    n = 0
    while L.r < 9:
        L.result(None, True)
        n += 1
    assert n == 45


def test_boost_and_speed_help_only_from_phantom():
    kit = A["AERIAL_BOT_KIT"]
    keys = [row[0] for row in A["AERIAL_BOT_ROSTER"]]
    for k in keys[:7]:
        assert kit[k]["boost"] == 1.0 and kit[k]["speed"] == 1.0, k
    assert kit[keys[9]]["boost"] <= 1.5 and kit[keys[9]]["speed"] <= 1.10
    assert kit[keys[7]]["speed"] < kit[keys[8]]["speed"] < kit[keys[9]]["speed"]


def test_bot_drives_another_car():
    for k in range(3):
        for row in A["AERIAL_BOT_ROSTER"]:
            assert A["aerial_bot_car"](row[0], k) != k


def test_bots_finish_and_play_their_rank():
    t0 = time.perf_counter()
    r = A["aerial_bot_match"]("pip", "pip", seed=2, match_s=20.0)
    assert not r["timeout"]
    wins = 0
    for seed in range(1, 6):                    # Rubenite against the first Rookie
        r = A["aerial_bot_match"]("ruben", "pip", seed=seed, match_s=30.0)
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
