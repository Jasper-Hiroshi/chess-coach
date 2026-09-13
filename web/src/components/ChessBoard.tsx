import { useMemo, useState } from "react";

const PIECES: Record<string, string> = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟"
};

function parseFen(fen: string) {
  const rows = fen.split(" ")[0].split("/");
  return rows.flatMap((row, rowIndex) => {
    const squares: Array<{ square: string; piece: string }> = [];
    let file = 0;
    for (const token of row) {
      if (/\d/.test(token)) {
        for (let count = 0; count < Number(token); count += 1) {
          squares.push({ square: `${"abcdefgh"[file]}${8 - rowIndex}`, piece: "" });
          file += 1;
        }
      } else {
        squares.push({ square: `${"abcdefgh"[file]}${8 - rowIndex}`, piece: PIECES[token] });
        file += 1;
      }
    }
    return squares;
  });
}

export function ChessBoard({ fen, flipped = false, interactive = false, onMove }: { fen: string; flipped?: boolean; interactive?: boolean; onMove?: (uci: string) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const squares = useMemo(() => {
    const parsed = parseFen(fen);
    return flipped ? [...parsed].reverse() : parsed;
  }, [fen, flipped]);

  const choose = (square: string, piece: string) => {
    if (!interactive) return;
    if (!selected) {
      if (piece) setSelected(square);
      return;
    }
    if (selected === square) {
      setSelected(null);
      return;
    }
    onMove?.(`${selected}${square}`);
    setSelected(null);
  };

  return (
    <div className="chessboard" aria-label="国际象棋棋盘">
      {squares.map(({ square, piece }, index) => {
        const file = square.charCodeAt(0) - 97;
        const rank = Number(square[1]);
        const light = (file + rank) % 2 === 1;
        return (
          <button
            className={`square ${light ? "light" : "dark"} ${selected === square ? "selected" : ""}`}
            key={square}
            onClick={() => choose(square, piece)}
            aria-label={`${square}${piece ? ` ${piece}` : " 空格"}`}
            tabIndex={interactive ? 0 : -1}
          >
            <span className="piece">{piece}</span>
            {(index % 8 === 0) && <i className="rank-label">{square[1]}</i>}
            {(index >= 56) && <i className="file-label">{square[0]}</i>}
          </button>
        );
      })}
    </div>
  );
}

