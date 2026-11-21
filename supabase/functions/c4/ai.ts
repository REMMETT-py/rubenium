// Rubenium Connect 4 AI (7 columns x 6 rows). Bitboards in two 32-bit halves are awkward in JS, so the board is
// kept as 7 column heights + one 49-cell array per player, with an incremental Zobrist hash (two 32-bit words) for
// the transposition table. Negamax + alpha-beta, iterative deepening, centre-first move order with the TT move first,
// a heuristic that scores 2- and 3-in-a-row windows, immediate wins / forced blocks and odd-even threat parity.
export const W = 7, H = 6;
const ORDER = [3, 2, 4, 1, 5, 0, 6];

let seed = 0x9e3779b9;
function rnd32(): number { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed >>> 0; }
const ZA: number[][] = [[], []], ZB: number[][] = [[], []];
for (let p = 0; p < 2; p++) for (let i = 0; i < W * H; i++) { ZA[p].push(rnd32()); ZB[p].push(rnd32()); }

// every line of 4 cells, and for each cell the lines through it
const LINES: number[][] = [];
for (let c = 0; c < W; c++) for (let r = 0; r < H; r++) {
  for (const [dc, dr] of [[1, 0], [0, 1], [1, 1], [1, -1]]) {
    const cells: number[] = [];
    for (let k = 0; k < 4; k++) {
      const cc = c + dc * k, rr = r + dr * k;
      if (cc < 0 || cc >= W || rr < 0 || rr >= H) break;
      cells.push(cc * H + rr);
    }
    if (cells.length === 4) LINES.push(cells);
  }
}
const LINES_AT: number[][] = Array.from({ length: W * H }, () => []);
LINES.forEach((l, i) => l.forEach((cell) => LINES_AT[cell].push(i)));

export class Board {
  cells: Int8Array = new Int8Array(W * H).fill(-1);   // -1 empty, 0 / 1 the players
  height: Int8Array = new Int8Array(W);
  moves = 0;
  ha = 0; hb = 0;
  static from(seq: number[]): Board { const b = new Board(); for (const c of seq) b.play(c); return b; }
  turn(): number { return this.moves & 1; }
  canPlay(c: number): boolean { return c >= 0 && c < W && this.height[c] < H; }
  play(c: number): void {
    const cell = c * H + this.height[c], p = this.turn();
    this.cells[cell] = p; this.height[c]++; this.moves++;
    this.ha ^= ZA[p][cell]; this.hb ^= ZB[p][cell];
  }
  undo(c: number): void {
    this.height[c]--; this.moves--;
    const cell = c * H + this.height[c], p = this.turn();
    this.cells[cell] = -1; this.ha ^= ZA[p][cell]; this.hb ^= ZB[p][cell];
  }
  winsAt(c: number, p: number): boolean {          // would playing c make 4 for p?
    if (!this.canPlay(c)) return false;
    const cell = c * H + this.height[c];
    for (const li of LINES_AT[cell]) {
      let n = 0;
      for (const x of LINES[li]) if (x === cell || this.cells[x] === p) n++;
      if (n === 4) return true;
    }
    return false;
  }
  lastWon(c: number): boolean {                    // did the move just played in c make 4?
    const cell = c * H + this.height[c] - 1, p = this.cells[cell];
    for (const li of LINES_AT[cell]) {
      let n = 0;
      for (const x of LINES[li]) if (this.cells[x] === p) n++;
      if (n === 4) return true;
    }
    return false;
  }
  full(): boolean { return this.moves >= W * H; }
}

// a position's value for the player to move
function evaluate(b: Board): number {
  const me = b.turn(), op = 1 - me;
  let s = 0;
  for (let r = 0; r < H; r++) {                    // the centre column counts most
    const v = b.cells[3 * H + r];
    if (v === me) s += 6; else if (v === op) s -= 6;
    const v2 = b.cells[2 * H + r], v4 = b.cells[4 * H + r];
    if (v2 === me) s += 2; else if (v2 === op) s -= 2;
    if (v4 === me) s += 2; else if (v4 === op) s -= 2;
  }
  for (const l of LINES) {
    let m = 0, o = 0, empty = -1;
    for (const x of l) { const v = b.cells[x]; if (v === me) m++; else if (v === op) o++; else empty = x; }
    if (m && o) continue;
    if (m === 3) {                                 // a threat; better on the right parity (row index from 0)
      const row = empty % H;
      s += 40 + ((me === 0) === (row % 2 === 0) ? 25 : 0);
    } else if (m === 2) s += 6;
    else if (o === 3) {
      const row = empty % H;
      s -= 45 + ((op === 0) === (row % 2 === 0) ? 25 : 0);
    } else if (o === 2) s -= 6;
  }
  return s;
}

const WIN = 1_000_000;
type Entry = { b: number; depth: number; score: number; flag: number; move: number };

export class Searcher {
  tt = new Map<number, Entry>();
  nodes = 0;
  deadline = Infinity;
  stopped = false;

  negamax(b: Board, depth: number, alpha: number, beta: number): number {
    this.nodes++;
    if ((this.nodes & 4095) === 0 && Date.now() > this.deadline) { this.stopped = true; return 0; }
    const me = b.turn();
    for (const c of ORDER) if (b.winsAt(c, me)) return WIN - b.moves;     // win now
    if (b.moves >= W * H - 1) return 0;
    // the opponent's winning cells: if two, we lose; if one, we must block there
    let forced = -1, threats = 0;
    for (const c of ORDER) if (b.winsAt(c, 1 - me)) { threats++; forced = c; }
    if (threats > 1) return -(WIN - b.moves - 1);
    if (depth <= 0) return evaluate(b);
    const a0 = alpha;
    const e = this.tt.get(b.ha);
    let first = -1;
    if (e && e.b === b.hb) {
      first = e.move;
      if (e.depth >= depth) {
        if (e.flag === 0) return e.score;
        if (e.flag === 1 && e.score > alpha) alpha = e.score;
        else if (e.flag === 2 && e.score < beta) beta = e.score;
        if (alpha >= beta) return e.score;
      }
    }
    let list = forced >= 0 ? [forced] : (first >= 0 ? [first, ...ORDER.filter((c) => c !== first)] : ORDER);
    // never play under a cell where the opponent would then win (unless every move does)
    const safe = list.filter((c) => b.canPlay(c) && !this.givesWin(b, c));
    if (safe.length) list = safe;
    else if (forced < 0) { return -(WIN - b.moves - 2); }
    if (forced < 0 && safe.length > 1) list = this.order(b, list);
    let best = -Infinity, bestMove = -1;
    for (const c of list) {
      if (!b.canPlay(c)) continue;
      b.play(c);
      const v = -this.negamax(b, depth - 1, -beta, -alpha);
      b.undo(c);
      if (this.stopped) return 0;
      if (v > best) { best = v; bestMove = c; }
      if (v > alpha) alpha = v;
      if (alpha >= beta) { this.history[me * W * H + c * H + b.height[c]] += depth * depth; break; }
    }
    if (bestMove < 0) return 0;
    const flag = best <= a0 ? 2 : best >= beta ? 1 : 0;
    if (this.tt.size > 2_000_000) this.tt.clear();
    this.tt.set(b.ha, { b: b.hb, depth, score: best, flag, move: bestMove });
    return best;
  }

  givesWin(b: Board, c: number): boolean {         // after c, can the opponent win right on top of it?
    if (b.height[c] + 1 >= H) return false;
    const me = b.turn();
    b.play(c);
    const bad = b.winsAt(c, me ^ 1) ;
    b.undo(c);
    return bad;
  }

  history = new Int32Array(W * H * 2);
  order(b: Board, list: number[]): number[] {      // TT move first, then the moves that made threats before
    const first = list[0];
    const rest = list.slice(1).map((c) => [c, this.history[b.turn() * W * H + c * H + b.height[c]] * 8 - ORDER.indexOf(c)] as [number, number]);
    rest.sort((x, y) => y[1] - x[1]);
    return [first, ...rest.map((x) => x[0])];
  }

  // scores of every legal move at one depth
  rootScores(b: Board, depth: number): Map<number, number> {
    const out = new Map<number, number>();
    for (const c of ORDER) {
      if (!b.canPlay(c)) continue;
      if (b.winsAt(c, b.turn())) { out.set(c, WIN); continue; }
      b.play(c);
      const v = -this.negamax(b, depth - 1, -WIN * 2, WIN * 2);
      b.undo(c);
      if (this.stopped) break;
      out.set(c, v);
    }
    return out;
  }
}

// 6.0: four real levels. Easy is quick and makes plain mistakes; Medium sees a few moves ahead but misses deeper
// tactics now and then; Hard looks far ahead (it moves first) and only rarely falls into a well-built trap; the
// Professional plays perfectly (solver.ts: an opening book, then an exact solve) and moves first: it cannot lose.
export const LEVELS: Record<string, { depth: number; ms: number; slack: number; blunder: number; shallow: number; low: number }> = {
  easy: { depth: 2, ms: 150, slack: 45, blunder: 0.33, shallow: 0, low: 1 },     // a third of its moves are careless
  medium: { depth: 6, ms: 450, slack: 8, blunder: 0.03, shallow: 0.15, low: 3 },  // about 1 move in 7 it only looks 3 ahead
  hard: { depth: 12, ms: 1000, slack: 0, blunder: 0, shallow: 0.05, low: 8 },    // 1 in 20 it looks 8 ahead, not 12
  pro: { depth: 42, ms: 1500, slack: 0, blunder: 0, shallow: 0, low: 42 },
};

export function bestMove(seq: number[], level: string, rand: () => number = Math.random): { col: number; depth: number; score: number } {
  const L = LEVELS[level] ?? LEVELS.medium;
  const b = Board.from(seq);
  // a careless move: any column that does not hand over a win at once (Easy: even that, half of the time)
  if (L.blunder && rand() < L.blunder) {
    const s0 = new Searcher();
    const legal = ORDER.filter((c) => b.canPlay(c));
    const mine = legal.find((c) => b.winsAt(c, b.turn()));
    if (mine !== undefined && rand() < 0.5) return { col: mine, depth: 0, score: 0 };
    const careful = level === "easy" && rand() < 0.5 ? legal : legal.filter((c) => !s0.givesWin(b, c));
    const pool = careful.length ? careful : legal;
    return { col: pool[Math.floor(rand() * pool.length)], depth: 0, score: 0 };
  }
  const maxDepth = L.shallow && rand() < L.shallow ? L.low : L.depth;
  const s = new Searcher();
  s.deadline = Date.now() + L.ms;
  let scores = new Map<number, number>(), reached = 0;
  for (let d = 1; d <= maxDepth; d++) {
    const got = s.rootScores(b, d);
    if (s.stopped) break;
    scores = got; reached = d;
    const top = Math.max(...got.values());
    if (Math.abs(top) >= WIN - 100) break;         // a forced result is known
  }
  if (!scores.size) { for (const c of ORDER) if (b.canPlay(c)) return { col: c, depth: 0, score: 0 }; }
  const top = Math.max(...scores.values());
  const good = [...scores.entries()].filter(([, v]) => v >= top - L.slack && (top < WIN - 100 || v === top));
  // among equal moves the centre-most is kept for strong levels, a random close one for easy / medium
  const pick = L.slack ? good[Math.floor(rand() * good.length)] : good.sort((x, y) => ORDER.indexOf(x[0]) - ORDER.indexOf(y[0]))[0];
  return { col: pick[0], depth: reached, score: pick[1] };
}

// the state of a finished or running game: who won (0 / 1), a draw, or still on
export function result(seq: number[]): { winner: number | null; draw: boolean; line: number[] | null } {
  const b = new Board();
  for (const c of seq) {
    b.play(c);
    if (b.lastWon(c)) {
      const cell = c * H + b.height[c] - 1, p = b.cells[cell];
      const line = LINES_AT[cell].map((i) => LINES[i]).find((l) => l.every((x) => b.cells[x] === p)) ?? null;
      return { winner: p, draw: false, line };
    }
  }
  return { winner: null, draw: b.full(), line: null };
}
