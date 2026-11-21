// Rubenium Connect 4: the bot thinks here, on the server, so no PC can make it lose on purpose.
// POST { game, col }  (col = -1: just let the bot move, e.g. its first move on Professional)
import { createClient } from "jsr:@supabase/supabase-js@2";
import { bestMove, result, Board } from "./ai.ts";
import { perfectMove, loadBook } from "./solver.ts";

// 6.0: the Professional's opening book, built offline (tools/c4book), read once per server start from the public repo
// and checked against its SHA-256. Without it the Professional still solves, just more slowly early in a game.
const BOOK_URL = "https://raw.githubusercontent.com/REMMETT-py/rubenium/main/supabase/functions/c4/book.bin";
const BOOK_SHA = "dfcb8f7a4b79396acbf6a37fc236df020f4357a0503535c93be330f34ff726f1";
let bookState: "none" | "loading" | "ok" | "bad" = "none";
let bookWait: Promise<void> | null = null;
let bookTried = 0;
function ensureBook(): Promise<void> {
  if (bookState === "ok") return Promise.resolve();
  if (bookState === "bad") {
    if (Date.now() - bookTried < 60_000) return Promise.resolve();
    bookWait = null;                                // tried a minute ago and failed: try again
  }
  if (!bookWait) {
    bookTried = Date.now();
    bookState = "loading";
    bookWait = (async () => {
      try {
        const res = await fetch(BOOK_URL, { signal: AbortSignal.timeout(4000) });
        const buf = new Uint8Array(await res.arrayBuffer());
        const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buf)))
          .map((x) => x.toString(16).padStart(2, "0")).join("");
        if (sha !== BOOK_SHA) { console.error("c4 book checksum mismatch", sha); bookState = "bad"; return; }
        console.log("c4 book", loadBook(buf), "positions");
        bookState = "ok";
      } catch (e) { console.error("c4 book", e); bookState = "bad"; }
    })();
  }
  return bookWait;
}
ensureBook();

// the Professional: perfect play; if the exact search ran out of time (no book), the Hard search decides
function proMove(moves: number[]): { col: number; depth: number } {
  const m = perfectMove(moves, 1600);
  if (m.source === "partial" && m.value < 1) { const h = bestMove(moves, "hard"); return { col: h.col, depth: h.depth }; }
  return { col: m.col, depth: 42 };
}

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
      if (g.level === "pro") await ensureBook();
      const m = g.level === "pro" ? proMove(moves) : bestMove(moves, g.level);
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
    // how long the bot "thinks" on screen (6.0): the easier the bot, the quicker it plays
    const span: Record<string, [number, number]> = { easy: [0.6, 1.4], medium: [1.0, 2.4], hard: [1.8, 3.8], pro: [2.5, 5.5] };
    const [lo, hi] = span[g.level] ?? [1, 3];
    const think = botCol < 0 ? 0 : lo + Math.random() * (hi - lo) + (moves.length > 10 && g.level !== "easy" ? 0.5 : 0);
    return out({ moves, bot: botCol, state: finished ? "done" : "live", outcome: finished, line: r.line, paid, coins,
                 capped, think: Math.round(think * 10) / 10 });
  } catch (e) {
    console.error(e);
    return out({ message: "Something went wrong: try again" }, 500);
  }
});
