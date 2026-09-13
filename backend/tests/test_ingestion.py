import json
from pathlib import Path

from app.integrations.chess_com import ChessComClient
from app.models import Game, PlayerProfile
from app.protocols import ArchiveRef
from app.services.ingestion import ingest_game


def test_demo_player_fixture_imports_13_idempotently(db_session):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "demo_player_2026_09.json").read_text(encoding="utf-8"))
    profile = PlayerProfile(chess_com_username="demo_player", chess_com_username_normalized="demo_player")
    db_session.add(profile)
    db_session.commit()
    created = [ingest_game(db_session, profile, item)[1] for item in fixture["games"]]
    db_session.commit()
    assert sum(created) == fixture["expected_count"] == 13
    assert db_session.query(Game).count() == 13
    created_again = [ingest_game(db_session, profile, item)[1] for item in fixture["games"]]
    assert not any(created_again)
    assert db_session.query(Game).count() == 13


def test_invalid_pgn_is_saved_but_not_analysed(db_session):
    profile = PlayerProfile(chess_com_username="demo_player", chess_com_username_normalized="demo_player")
    db_session.add(profile)
    db_session.commit()
    game, created = ingest_game(db_session, profile, {"uuid": "bad", "pgn": "", "rules": "chess"})
    assert created is True
    assert game.parse_status == "invalid"
    assert game.analysis_status == "not_queued"


def test_chess_com_conditional_request_accepts_304():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["if-none-match"] == '"cached"'
        return httpx.Response(304, request=request)

    client = ChessComClient(httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.fetch_archive(
        ArchiveRef("https://api.chess.com/pub/player/test/games/2026/09", "2026-09"),
        etag='"cached"',
        last_modified=None,
    )
    assert result.status == "not_modified"
    assert result.games == []
