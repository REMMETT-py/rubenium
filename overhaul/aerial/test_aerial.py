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
                if st == 0 and gap < 450:
                    j, st = True, 1
                elif st == 1:
                    st = 2
                elif st == 2 and gap < 330:
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
        x = I(rnd.choice((-1, 0, 1)), rnd.choice((-1, 0, 1)), rnd.randrange(-1, 1024), rnd.choice((-1, 0, 1)),
              rnd.random() < .5, rnd.random() < .5, rnd.random() < .5, rnd.random() < .5)
        y = I.unpack(x.pack())
        assert (x.ix, x.iy, x.aim, x.rot, x.boost, x.jump, x.roll, x.skip) == (y.ix, y.iy, y.aim, y.rot, y.boost, y.jump,
                                                                                y.roll, y.skip)


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


def test_flip_reset_chain_with_grip():
    s = A["AerialSim"]()
    s.kickoff(0)
    s.frozen, s.ball_held = False, False
    c, b = s.cars[0], s.ball
    c.assist = {"boost": 0.5, "grip": 0.9, "shot": 5200.0, "catch": 0.0, "reach": 0.0, "steer": 0.0, "power": 0.0, "guard": 0.0, "speed": 1.0}
    c.reset(-600.0, c.r, 1.0)
    b.x, b.y = -600.0, T["ball_r"]
    for _ in range(120):
        s.step([I(), I()])
    assert c.holding
    for i in range(40):
        s.step([I(ix=1, jump=i < 20, boost=True, aim=A["aerial_aim_index"](1, 1)), I()])
    s.step([I(roll=True, boost=True, aim=A["aerial_aim_index"](1, 1)), I()])
    assert c.grip_side < 0 and c.holding
    resets = 0
    for i in range(200):
        s.step([I(jump=(i % 24) < 3 and c.has_action, boost=True, aim=A["aerial_aim_index"](1, 1.2)), I()])
        resets += sum(1 for e in s.ev if e[0] == "reset")
    assert resets >= 3, resets


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
