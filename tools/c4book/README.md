# Connect 4 opening book (Rubenium 6.0)

`solver.cpp` is the Professional's solver (Pascal Pons' algorithm) in C++. It builds `book.bin`: for every
position the first player (the bot) can face up to 12 moves, a move that keeps the win.

    g++ -O3 -march=native -o solver solver.cpp
    ./solver book 12 book.bin        # about 4 minutes
    ./solver solve 4433 w            # weak-solve one position (columns 1-7)

Format: 8 bytes per position, sorted: the mirror-canonical position key (cur + mask, 7 bytes little endian) and the
column (0-6) to play. The edge function (`supabase/functions/c4/index.ts`) downloads it from this repo on start and
checks its SHA-256 (`BOOK_SHA`). Rebuild it and update `BOOK_SHA` together.
