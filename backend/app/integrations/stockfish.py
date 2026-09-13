from __future__ import annotations

import shutil
from typing import Any

import chess
import chess.engine

from ..config import get_settings


def expectation_from_wdl(wins: int, draws: int, losses: int, color: chess.Color) -> float:
    return ((2 * wins + draws) if color == chess.WHITE else (2 * losses + draws)) / 2000.0


class StockfishAdapter:
    def __init__(self, path: str | None = None):
        configured = path or get_settings().stockfish_path
        self.path = shutil.which(configured) or configured
        self._engine: chess.engine.SimpleEngine | None = None
        self.version = "Stockfish 19"

    def __enter__(self):
        self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self._engine.configure({"Threads": 1, "Hash": 256})
        name = self._engine.id.get("name")
        if name:
            self.version = name
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._engine:
            self._engine.quit()
            self._engine = None

    def analyze(
        self,
        fen: str,
        *,
        nodes: int,
        multipv: int,
        root_moves: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        if self._engine is None:
            raise RuntimeError("Stockfish adapter must be used as a context manager")
        board = chess.Board(fen)
        legal_root = [chess.Move.from_uci(value) for value in root_moves]
        result = self._engine.analyse(
            board,
            chess.engine.Limit(nodes=nodes),
            multipv=multipv,
            root_moves=legal_root or None,
            info=chess.engine.INFO_ALL,
        )
        infos = result if isinstance(result, list) else [result]
        return [self._normalize(info, board, rank) for rank, info in enumerate(infos, start=1)]

    def _normalize(self, info: chess.engine.InfoDict, board: chess.Board, rank: int) -> dict[str, Any]:
        pov_score = info["score"].pov(chess.WHITE)
        wdl = info.get("wdl")
        if wdl is not None:
            pov_wdl = wdl.pov(chess.WHITE)
            wins, draws, losses = pov_wdl.wins, pov_wdl.draws, pov_wdl.losses
            source = "engine"
        else:
            derived = info["score"].wdl(model="sf", ply=board.ply()).pov(chess.WHITE)
            wins, draws, losses = derived.wins, derived.draws, derived.losses
            source = "derived"
        pv = [move.uci() for move in info.get("pv", [])]
        return {
            "rank": info.get("multipv", rank),
            "pv": pv,
            "best_move_uci": pv[0] if pv else None,
            "score_cp_white": pov_score.score(),
            "mate_white": pov_score.mate(),
            "wdl_white": {"wins": wins, "draws": draws, "losses": losses},
            "expected_score_white": expectation_from_wdl(wins, draws, losses, chess.WHITE),
            "depth": info.get("depth"),
            "seldepth": info.get("seldepth"),
            "nodes": info.get("nodes", 0),
            "wdl_source": source,
        }
