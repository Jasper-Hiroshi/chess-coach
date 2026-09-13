import chess

from app.integrations.stockfish import expectation_from_wdl
from app.services.analysis import severity_from_loss
from app.services.ingestion import classify_phase


def test_wdl_perspective():
    assert expectation_from_wdl(700, 200, 100, chess.WHITE) == 0.8
    assert expectation_from_wdl(700, 200, 100, chess.BLACK) == 0.2


def test_severity_boundaries():
    assert severity_from_loss(0.0499) == "normal"
    assert severity_from_loss(0.05) == "inaccuracy"
    assert severity_from_loss(0.0999) == "inaccuracy"
    assert severity_from_loss(0.10) == "mistake"
    assert severity_from_loss(0.1999) == "mistake"
    assert severity_from_loss(0.20) == "blunder"


def test_phase_moves_from_opening_to_endgame():
    assert classify_phase(chess.Board(), 1) == "opening"
    board = chess.Board("8/8/8/8/8/4k3/8/4K3 w - - 0 50")
    assert classify_phase(board, 40) == "endgame"

