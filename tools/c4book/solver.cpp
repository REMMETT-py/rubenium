// Connect 4 solver (7x6), Pascal Pons' algorithm: bitboards, negamax + alpha-beta with null-window, transposition
// table, anticipation of losing moves, move ordering by created threats. Used offline to build Rubenium's book.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <string>
#include <unordered_map>
#include <chrono>
#include <cassert>
#include <algorithm>
typedef uint64_t u64;
static const int W = 7, H = 6, MIN_SCORE = -(W * H) / 2 + 3, MAX_SCORE = (W * H + 1) / 2 - 3;

static constexpr u64 bottom(int w, int h) { return w == 0 ? 0 : bottom(w - 1, h) | 1ULL << (w - 1) * (h + 1); }
static const u64 BOTTOM = bottom(W, H), BOARD = BOTTOM * ((1ULL << H) - 1);

struct Pos {
  u64 cur = 0, mask = 0; int moves = 0;
  static u64 top_col(int c) { return (1ULL << (H - 1)) << c * (H + 1); }
  static u64 bottom_col(int c) { return 1ULL << c * (H + 1); }
  static u64 col_mask(int c) { return ((1ULL << H) - 1) << c * (H + 1); }
  bool canPlay(int c) const { return (mask & top_col(c)) == 0; }
  void play(u64 move) { cur ^= mask; mask |= move; moves++; }
  void playCol(int c) { play((mask + bottom_col(c)) & col_mask(c)); }
  bool isWinningMove(int c) const { return winning_position() & possible() & col_mask(c); }
  bool canWinNext() const { return winning_position() & possible(); }
  u64 key() const { return cur + mask; }
  u64 possible() const { return (mask + BOTTOM) & BOARD; }
  u64 opponent_winning_position() const { return compute_winning_position(cur ^ mask, mask); }
  u64 winning_position() const { return compute_winning_position(cur, mask); }
  u64 possibleNonLosingMoves() const {
    u64 pm = possible(), ow = opponent_winning_position(), forced = pm & ow;
    if (forced) { if (forced & (forced - 1)) return 0; pm = forced; }
    return pm & ~(ow >> 1);
  }
  static int popcount(u64 m) { return __builtin_popcountll(m); }
  int moveScore(u64 move) const { return popcount(compute_winning_position(cur | move, mask)); }
  static u64 compute_winning_position(u64 position, u64 mask) {
    u64 r = (position << 1) & (position << 2) & (position << 3);
    u64 p;
    p = (position << (H + 1)) & (position << 2 * (H + 1));
    r |= p & (position << 3 * (H + 1)); r |= p & (position >> (H + 1));
    p = (position >> (H + 1)) & (position >> 2 * (H + 1));
    r |= p & (position << (H + 1)); r |= p & (position >> 3 * (H + 1));
    p = (position << H) & (position << 2 * H);
    r |= p & (position << 3 * H); r |= p & (position >> H);
    p = (position >> H) & (position >> 2 * H);
    r |= p & (position << H); r |= p & (position >> 3 * H);
    p = (position << (H + 2)) & (position << 2 * (H + 2));
    r |= p & (position << 3 * (H + 2)); r |= p & (position >> (H + 2));
    p = (position >> (H + 2)) & (position >> 2 * (H + 2));
    r |= p & (position << (H + 2)); r |= p & (position >> 3 * (H + 2));
    return r & (BOARD ^ mask);
  }
  u64 mirrorKey() const {
    u64 c2 = 0, m2 = 0;
    for (int c = 0; c < W; c++) {
      c2 |= ((cur >> c * (H + 1)) & 0x7F) << (W - 1 - c) * (H + 1);
      m2 |= ((mask >> c * (H + 1)) & 0x7F) << (W - 1 - c) * (H + 1);
    }
    return c2 + m2;
  }
};

// transposition table: key (truncated) + value
struct TT {
  std::vector<uint32_t> K; std::vector<int8_t> V; size_t n;
  TT(size_t size) : K(size), V(size), n(size) {}
  void put(u64 key, int8_t v) { size_t i = key % n; K[i] = (uint32_t)key; V[i] = v; }
  int8_t get(u64 key) const { size_t i = key % n; return K[i] == (uint32_t)key ? V[i] : 0; }
  void clear() { std::fill(K.begin(), K.end(), 0); std::fill(V.begin(), V.end(), 0); }
};
static TT tt(1 << 24 | 1);   // ~16.7M entries, prime-ish (odd)
static u64 nodes = 0;
static int ORDER[W];

struct Sorter {
  u64 m[W]; int s[W]; int size = 0;
  void add(u64 move, int score) { int pos = size++; for (; pos && s[pos - 1] > score; --pos) { m[pos] = m[pos - 1]; s[pos] = s[pos - 1]; } m[pos] = move; s[pos] = score; }
  u64 next() { return size ? m[--size] : 0; }
};

static int negamax(const Pos &P, int alpha, int beta) {
  nodes++;
  u64 next = P.possibleNonLosingMoves();
  if (next == 0) return -(W * H - P.moves) / 2;
  if (P.moves >= W * H - 2) return 0;
  int min = -(W * H - 2 - P.moves) / 2;
  if (alpha < min) { alpha = min; if (alpha >= beta) return alpha; }
  int max = (W * H - 1 - P.moves) / 2;
  if (int val = tt.get(P.key())) max = val + MIN_SCORE - 1;
  if (beta > max) { beta = max; if (alpha >= beta) return beta; }
  Sorter mv;
  for (int i = W; i--;) if (u64 move = next & Pos::col_mask(ORDER[i])) mv.add(move, P.moveScore(move));
  while (u64 move = mv.next()) {
    Pos P2(P); P2.play(move);
    int score = -negamax(P2, -beta, -alpha);
    if (score >= beta) return score;
    if (score > alpha) alpha = score;
  }
  tt.put(P.key(), alpha - MIN_SCORE + 1);
  return alpha;
}

// weak = true: only the sign (-1 lose, 0 draw, +1 win) for the player to move
static int solve(const Pos &P, bool weak) {
  if (P.canWinNext()) return weak ? 1 : (W * H + 1 - P.moves) / 2;
  int min = -(W * H - P.moves) / 2, max = (W * H + 1 - P.moves) / 2;
  if (weak) { min = -1; max = 1; }
  while (min < max) {
    int med = min + (max - min) / 2;
    if (med <= 0 && min / 2 < med) med = min / 2;
    else if (med >= 0 && max / 2 > med) med = max / 2;
    int r = negamax(P, med, med + 1);
    if (r <= med) max = r; else min = r;
  }
  return min;
}

int main(int argc, char **argv) {
  for (int i = 0; i < W; i++) ORDER[i] = W / 2 + (1 - 2 * (i % 2)) * (i + 1) / 2;
  // mode "solve SEQ": weak-solve a position given as columns 1-7
  if (argc >= 3 && std::string(argv[1]) == "solve") {
    Pos P; for (char ch : std::string(argv[2])) P.playCol(ch - '1');
    auto t0 = std::chrono::steady_clock::now();
    int s = solve(P, argc > 3);
    double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    printf("%s score %d nodes %llu ms %.1f\n", argv[2], s, (unsigned long long)nodes, ms);
    return 0;
  }
  // mode "book PLY OUT": the first player's winning move for every position it can face up to PLY
  if (argc >= 4 && std::string(argv[1]) == "book") {
    int maxPly = atoi(argv[2]);
    std::unordered_map<u64, int> book;          // canonical key -> move (in canonical orientation)
    std::vector<std::pair<Pos, int>> stack;    // DFS over AI-to-move positions
    long done = 0; auto t0 = std::chrono::steady_clock::now();
    std::vector<Pos> todo; Pos root; todo.push_back(root);
    while (!todo.empty()) {
      Pos P = todo.back(); todo.pop_back();
      u64 k = P.key(), mk = P.mirrorKey();
      bool flip = mk < k; u64 ck = flip ? mk : k;
      int move = -1;
      auto it = book.find(ck);
      if (it != book.end()) { move = flip ? W - 1 - it->second : it->second; }
      else {
        // an immediate win first, else the first move (centre-out, by threats) whose result is still a win
        for (int c = 0; c < W && move < 0; c++) if (P.canPlay(c) && P.isWinningMove(c)) move = c;
        if (move < 0) {
          if (P.moves == 0) move = 3;
          else {
            Sorter mv; u64 nl = P.possibleNonLosingMoves();
            for (int i = W; i--;) if (u64 m = nl & Pos::col_mask(ORDER[i])) mv.add(m, P.moveScore(m));
            std::vector<u64> cand; while (u64 m = mv.next()) cand.push_back(m);
            for (u64 m : cand) {
              Pos Q(P); Q.play(m);
              if (solve(Q, true) < 0) { for (int c = 0; c < W; c++) if (m & Pos::col_mask(c)) move = c; break; }
            }
          }
          if (move < 0) { fprintf(stderr, "NO WIN at ply %d\n", P.moves); return 1; }
          book[ck] = flip ? W - 1 - move : move;
          if (++done % 2000 == 0) {
            double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
            fprintf(stderr, "%ld positions, ply %d, %.0f s\n", done, P.moves, s);
          }
        } else continue;     // already expanded from an identical position
      }
      if (P.isWinningMove(move)) continue;     // the game ends here
      Pos A(P); A.playCol(move);
      if (A.moves + 1 > maxPly) continue;
      for (int h = W - 1; h >= 0; h--) if (A.canPlay(h)) {
        Pos B(A); B.playCol(h);
        if (B.moves <= maxPly) todo.push_back(B);
      }
    }
    FILE *f = fopen(argv[3], "wb");
    std::vector<std::pair<u64, int>> v(book.begin(), book.end());
    std::sort(v.begin(), v.end());
    for (auto &e : v) { unsigned char b[8]; for (int i = 0; i < 7; i++) b[i] = (e.first >> (8 * i)) & 0xFF; b[7] = e.second; fwrite(b, 1, 8, f); }
    fclose(f);
    fprintf(stderr, "book: %zu entries\n", v.size());
    return 0;
  }
  return 0;
}
