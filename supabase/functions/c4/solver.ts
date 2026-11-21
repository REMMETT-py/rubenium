// Rubenium Connect 4: the Professional's perfect play (6.0).
// The board is a bitboard: 7 bits per column (6 cells + a sentinel), 49 bits in all, kept in two 32-bit words because
// JavaScript bit operations are 32-bit: columns 0-3 in `lo` (bits 0-27), columns 4-6 in `hi` (bits 0-20).
// Search: negamax + alpha-beta with null windows (a "weak" solve: win / draw / loss), a transposition table in typed
// arrays, moves that hand the opponent a win pruned before searching, and moves ordered by the threats they create.
// Before searching, an opening book (built offline by the same algorithm in C++, every position the first player can
// face up to 12 moves) gives the move instantly. Book keys are mirror-canonical (column c = column 6 - c).
export const W = 7, H = 6;
const LO_BITS = 28, LO_MASK = 0x0fffffff, HI_MASK = 0x1fffff;

// a 49-bit value as [lo, hi]
type B = { lo: number; hi: number };
const colMaskB = (c: number): B => c < 4 ? { lo: (0x3f << (c * 7)) & LO_MASK, hi: 0 } : { lo: 0, hi: 0x3f << ((c - 4) * 7) };
const COL_LO = [0, 1, 2, 3, 4, 5, 6].map((c) => colMaskB(c).lo);
const COL_HI = [0, 1, 2, 3, 4, 5, 6].map((c) => colMaskB(c).hi);
const BOTTOM_LO = (1 | 1 << 7 | 1 << 14 | 1 << 21), BOTTOM_HI = (1 | 1 << 7 | 1 << 14);
const BOARD_LO = (0x3f | 0x3f << 7 | 0x3f << 14 | 0x3f << 21), BOARD_HI = (0x3f | 0x3f << 7 | 0x3f << 14);
const TOP_LO = [0, 1, 2, 3, 4, 5, 6].map((c) => c < 4 ? (1 << 5) << (c * 7) : 0);
const TOP_HI = [0, 1, 2, 3, 4, 5, 6].map((c) => c >= 4 ? (1 << 5) << ((c - 4) * 7) : 0);

function shl(lo: number, hi: number, s: number, out: number[]): void {
  out[0] = (lo << s) & LO_MASK;
  out[1] = ((hi << s) | (lo >>> (LO_BITS - s))) & HI_MASK;
}
function shr(lo: number, hi: number, s: number, out: number[]): void {
  out[0] = ((lo >>> s) | (hi << (LO_BITS - s))) & LO_MASK;
  out[1] = (hi >>> s) & HI_MASK;
}
function pop32(x: number): number {
  x = x - ((x >>> 1) & 0x55555555);
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  return (((x + (x >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

const t1 = [0, 0], t2 = [0, 0], t3 = [0, 0];
// the empty cells where `pos` would complete four (Pons' compute_winning_position)
function winning(plo: number, phi: number, mlo: number, mhi: number, out: number[]): void {
  let rlo = 0, rhi = 0;
  // vertical
  shl(plo, phi, 1, t1); shl(plo, phi, 2, t2); shl(plo, phi, 3, t3);
  rlo |= t1[0] & t2[0] & t3[0]; rhi |= t1[1] & t2[1] & t3[1];
  for (const d of [H + 1, H, H + 2]) {             // horizontal, diagonal /, diagonal \
    let alo: number, ahi: number;
    // p = (pos << d) & (pos << 2d)
    shl(plo, phi, d, t1); shl(plo, phi, 2 * d, t2);
    alo = t1[0] & t2[0]; ahi = t1[1] & t2[1];
    shl(plo, phi, 3 * d, t3); rlo |= alo & t3[0]; rhi |= ahi & t3[1];
    shr(plo, phi, d, t3); rlo |= alo & t3[0]; rhi |= ahi & t3[1];
    // p = (pos >> d) & (pos >> 2d)
    shr(plo, phi, d, t1); shr(plo, phi, 2 * d, t2);
    alo = t1[0] & t2[0]; ahi = t1[1] & t2[1];
    shl(plo, phi, d, t3); rlo |= alo & t3[0]; rhi |= ahi & t3[1];
    shr(plo, phi, 3 * d, t3); rlo |= alo & t3[0]; rhi |= ahi & t3[1];
  }
  out[0] = rlo & (BOARD_LO ^ mlo);
  out[1] = rhi & (BOARD_HI ^ mhi);
}

export class Pos {
  clo = 0; chi = 0; mlo = 0; mhi = 0; moves = 0;    // clo/chi: the discs of the player to move; m: all discs
  static from(seq: number[]): Pos { const p = new Pos(); for (const c of seq) p.playCol(c); return p; }
  copy(): Pos { const p = new Pos(); p.clo = this.clo; p.chi = this.chi; p.mlo = this.mlo; p.mhi = this.mhi; p.moves = this.moves; return p; }
  canPlay(c: number): boolean { return ((this.mlo & TOP_LO[c]) | (this.mhi & TOP_HI[c])) === 0; }
  play(lo: number, hi: number): void {
    this.clo ^= this.mlo; this.chi ^= this.mhi;
    this.mlo |= lo; this.mhi |= hi; this.moves++;
  }
  playCol(c: number): void {
    const lo = ((this.mlo + (c < 4 ? 1 << (c * 7) : 0)) & COL_LO[c]);
    const hi = ((this.mhi + (c >= 4 ? 1 << ((c - 4) * 7) : 0)) & COL_HI[c]);
    // the new disc is the lowest empty cell: (mask + bottom_of_column) & column
    this.play(lo & ~this.mlo, hi & ~this.mhi);
  }
  possible(out: number[]): void { out[0] = (this.mlo + BOTTOM_LO) & BOARD_LO; out[1] = (this.mhi + BOTTOM_HI) & BOARD_HI; }
  isWinningMove(c: number): boolean {
    const w = [0, 0], p = [0, 0];
    winning(this.clo, this.chi, this.mlo, this.mhi, w); this.possible(p);
    return ((w[0] & p[0] & COL_LO[c]) | (w[1] & p[1] & COL_HI[c])) !== 0;
  }
  canWinNext(): boolean {
    const w = [0, 0], p = [0, 0];
    winning(this.clo, this.chi, this.mlo, this.mhi, w); this.possible(p);
    return ((w[0] & p[0]) | (w[1] & p[1])) !== 0;
  }
  // the moves that do not let the opponent win right after (0 if every move loses)
  nonLosing(out: number[]): void {
    const p = [0, 0], ow = [0, 0], below = [0, 0];
    this.possible(p);
    winning(this.clo ^ this.mlo, this.chi ^ this.mhi, this.mlo, this.mhi, ow);
    let flo = p[0] & ow[0], fhi = p[1] & ow[1];
    let plo = p[0], phi = p[1];
    if (flo | fhi) {
      const n = pop32(flo) + pop32(fhi);
      if (n > 1) { out[0] = 0; out[1] = 0; return; }
      plo = flo; phi = fhi;
    }
    shr(ow[0], ow[1], 1, below);
    out[0] = plo & ~below[0]; out[1] = phi & ~below[1];
  }
  moveScore(lo: number, hi: number): number {
    const w = [0, 0];
    winning(this.clo | lo, this.chi | hi, this.mlo, this.mhi, w);
    return pop32(w[0]) + pop32(w[1]);
  }
  // the position's key (unique, < 2^49) and the mirrored board's key
  key(): number { return (this.chi + this.mhi) * 2 ** LO_BITS + (this.clo + this.mlo); }
  mirrorKey(): number {
    let k = 0;
    for (let c = 0; c < W; c++) {
      const col = c < 4 ? ((this.clo + this.mlo) >>> (c * 7)) & 0x7f : ((this.chi + this.mhi) >>> ((c - 4) * 7)) & 0x7f;
      k += col * 2 ** ((W - 1 - c) * 7);
    }
    return k;
  }
}

const MIN_SCORE = -(W * H) / 2 + 3;
const ORDER = [3, 2, 4, 1, 5, 0, 6];
const TT_BITS = 22, TT_SIZE = 1 << TT_BITS;
const ttKeyLo = new Int32Array(TT_SIZE), ttKeyHi = new Int32Array(TT_SIZE), ttVal = new Int8Array(TT_SIZE);

export class Solver {
  nodes = 0;
  deadline = Infinity;
  stopped = false;

  private ttIndex(lo: number, hi: number): number { return ((lo ^ Math.imul(hi, 0x9e3779b1)) >>> 0) & (TT_SIZE - 1); }

  negamax(P: Pos, alpha: number, beta: number): number {
    this.nodes++;
    if ((this.nodes & 8191) === 0 && Date.now() > this.deadline) { this.stopped = true; return 0; }
    const next = [0, 0];
    P.nonLosing(next);
    if ((next[0] | next[1]) === 0) return -Math.floor((W * H - P.moves) / 2);
    if (P.moves >= W * H - 2) return 0;
    const min = -Math.floor((W * H - 2 - P.moves) / 2);
    if (alpha < min) { alpha = min; if (alpha >= beta) return alpha; }
    let max = Math.floor((W * H - 1 - P.moves) / 2);
    const klo = P.clo + P.mlo, khi = P.chi + P.mhi;
    const i = this.ttIndex(klo, khi);
    if (ttKeyLo[i] === klo && ttKeyHi[i] === khi && ttVal[i]) max = ttVal[i] + MIN_SCORE - 1;
    if (beta > max) { beta = max; if (alpha >= beta) return beta; }
    // moves, best (most threats created) first, centre first on ties
    const mlo: number[] = [], mhi: number[] = [], ms: number[] = [];
    for (let k = W - 1; k >= 0; k--) {
      const c = ORDER[k];
      const lo = next[0] & COL_LO[c], hi = next[1] & COL_HI[c];
      if (lo | hi) {
        const s = P.moveScore(lo, hi);
        let pos = ms.length;
        mlo.push(0); mhi.push(0); ms.push(0);
        for (; pos && ms[pos - 1] > s; pos--) { mlo[pos] = mlo[pos - 1]; mhi[pos] = mhi[pos - 1]; ms[pos] = ms[pos - 1]; }
        mlo[pos] = lo; mhi[pos] = hi; ms[pos] = s;
      }
    }
    for (let k = ms.length - 1; k >= 0; k--) {
      const Q = P.copy(); Q.play(mlo[k], mhi[k]);
      const score = -this.negamax(Q, -beta, -alpha);
      if (this.stopped) return 0;
      if (score >= beta) return score;
      if (score > alpha) alpha = score;
    }
    ttKeyLo[i] = klo; ttKeyHi[i] = khi; ttVal[i] = alpha - MIN_SCORE + 1;
    return alpha;
  }

  // the sign of the position for the player to move: 1 win, 0 draw, -1 loss
  weak(P: Pos): number {
    if (P.canWinNext()) return 1;
    let min = -1, max = 1;
    while (min < max) {
      let med = min + Math.floor((max - min) / 2);
      if (med <= 0 && Math.trunc(min / 2) < med) med = Math.trunc(min / 2);
      else if (med >= 0 && Math.trunc(max / 2) > med) med = Math.trunc(max / 2);
      const r = this.negamax(P, med, med + 1);
      if (this.stopped) return 0;
      if (r <= med) max = r; else min = r;
    }
    return Math.sign(min);
  }
}

// ---------------------------------------------------------------- the opening book
let BOOK: Map<number, number> | null = null;
export function loadBook(bytes: Uint8Array): number {
  const m = new Map<number, number>();
  for (let i = 0; i + 8 <= bytes.length; i += 8) {
    let k = 0;
    for (let j = 6; j >= 0; j--) k = k * 256 + bytes[i + j];
    m.set(k, bytes[i + 7]);
  }
  BOOK = m;
  return m.size;
}
export function bookMove(P: Pos): number {
  if (!BOOK) return -1;
  const k = P.key(), mk = P.mirrorKey();
  if (mk < k) { const m = BOOK.get(mk); return m === undefined ? -1 : W - 1 - m; }
  const m = BOOK.get(k);
  return m === undefined ? -1 : m;
}

// the perfect move: book, else an immediate win, else the first move (by threats, centre first) that keeps a win,
// else one that keeps a draw, else the move that loses the latest. ms: the time allowed for searching.
export function perfectMove(seq: number[], ms = 1500): { col: number; source: string; value: number; nodes: number } {
  const P = Pos.from(seq);
  for (const c of ORDER) if (P.canPlay(c) && P.isWinningMove(c)) return { col: c, source: "win", value: 1, nodes: 0 };
  const b = bookMove(P);
  if (b >= 0 && P.canPlay(b)) return { col: b, source: "book", value: 1, nodes: 0 };
  const S = new Solver();
  S.deadline = Date.now() + ms;
  const next = [0, 0];
  P.nonLosing(next);
  const cands: { c: number; s: number }[] = [];
  for (const c of ORDER) {
    if (!P.canPlay(c)) continue;
    const lo = next[0] & COL_LO[c], hi = next[1] & COL_HI[c];
    cands.push({ c, s: (lo | hi) ? P.moveScore(lo, hi) : -100 });    // a move that hands over a win goes last
  }
  cands.sort((x, y) => y.s - x.s);
  let best = cands[0]?.c ?? 3, bestV = -2;
  for (const { c } of cands) {
    const Q = P.copy(); Q.playCol(c);
    const v = -S.weak(Q);
    if (S.stopped) break;
    if (v > bestV) { bestV = v; best = c; }
    if (v === 1) break;
  }
  return { col: best, source: S.stopped ? "partial" : "search", value: bestV, nodes: S.nodes };
}
