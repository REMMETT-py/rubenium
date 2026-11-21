// Rubenium Connect 4: the bot thinks here, on the server, so no PC can make it lose on purpose.
// POST { game, col }  (col = -1: just let the bot move, e.g. its first move on Professional)
import { createClient } from "jsr:@supabase/supabase-js@2";
import { bestMove, result, Board } from "./ai.ts";

const HEAD = { "Content-Type": "application/json" };
const out = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: HEAD });

Deno.serve(async (req) => {
  try {
    const url = Deno.env.get("SUPABASE_URL")!;
    const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
    const { data: who, error: authErr } = await admin.auth.getUser(jwt);
    if (authErr || !who?.user) return out({ message: "rb_not_logged_in" }, 401);
    const body = await req.json().catch(() => ({}));
    const gid = String(body.game ?? "");
    const col = Number.isInteger(body.col) ? body.col : -1;
    const { data: g } = await admin.from("rb_c4").select("*").eq("id", gid).maybeSingle();
    if (!g || g.owner !== who.user.id) return out({ message: "rb_round_gone" }, 400);
    if (g.state !== "live") return out({ message: "rb_round_gone" }, 400);
    const moves: number[] = (g.moves ?? []).map(Number);
    const human = g.bot_first ? 1 : 0;
    const b = Board.from(moves);
    let finished: string | null = null;

    if (col >= 0) {
      if (b.turn() !== human) return out({ message: "rb_not_your_turn" }, 400);
      if (!b.canPlay(col)) return out({ message: "rb_bad_choice" }, 400);
      moves.push(col);
      const r = result(moves);
      if (r.winner === human) finished = "win";
      else if (r.draw) finished = "draw";
    }
    let botCol = -1, depth = 0;
    if (!finished && Board.from(moves).turn() !== human) {
      const t0 = Date.now();
      const m = bestMove(moves, g.level);
      botCol = m.col; depth = m.depth;
      moves.push(botCol);
      const r = result(moves);
      if (r.winner !== null && r.winner !== human) finished = "lose";
      else if (r.draw) finished = "draw";
      console.log("c4", g.level, "depth", depth, "ms", Date.now() - t0);
    }
    // the update only lands if nobody moved meanwhile (same number of moves as we read)
    const { data: upd } = await admin.from("rb_c4").update({ moves, updated_at: new Date().toISOString() })
      .eq("id", gid).eq("state", "live").eq("n", g.n).select("id");
    if (!upd || !upd.length) return out({ message: "rb_too_soon" }, 409);
    let paid = 0, coins = null, capped = false;
    if (finished) {
      const { data: fin, error } = await admin.rpc("rb_c4_finish", { gid, outcome: finished });
      if (error) return out({ message: error.message }, 400);
      paid = fin?.paid ?? 0; coins = fin?.coins ?? null; capped = !!fin?.capped;
    }
    const r = result(moves);
    // how long the bot "thinks" on screen: 3 to 7 seconds, longer when the position is tense
    const free = [0, 1, 2, 3, 4, 5, 6].filter((c) => Board.from(moves).canPlay(c)).length;
    const think = botCol < 0 ? 0 : Math.min(7, Math.max(3, 3 + (moves.length > 8 ? 1.5 : 0) + (free > 5 ? 0.5 : 0)
      + Math.random() * 2 + (g.level === "pro" ? 1 : 0)));
    return out({ moves, bot: botCol, state: finished ? "done" : "live", outcome: finished, line: r.line, paid, coins,
                 capped, think: Math.round(think * 10) / 10 });
  } catch (e) {
    console.error(e);
    return out({ message: "Something went wrong: try again" }, 500);
  }
});
