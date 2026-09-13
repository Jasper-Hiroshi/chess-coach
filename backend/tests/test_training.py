from datetime import datetime, timezone

from app.models import Mistake, Move, MoveAssessment, PlayerProfile, TrainingItem
from app.services.training import apply_attempt


def test_spaced_repetition_and_idempotency(db_session):
    profile = PlayerProfile(chess_com_username="demo_player", chess_com_username_normalized="demo_player")
    db_session.add(profile)
    db_session.flush()
    # Foreign keys are not enforced by SQLite tests; the item exercises scheduling only.
    item = TrainingItem(profile_id=profile.id, mistake_id="m1", fen="8/8/8/8/8/4k3/8/4K3 w - - 0 1", side_to_move="white", answer_moves=["e1e2"], solution_pv=["e1e2"], theme="calculation")
    db_session.add(item)
    db_session.commit()
    first = apply_attempt(db_session, item, "e1e2", False, 1200, "attempt-1")
    assert first.correct is True
    assert first.previous_level == 0 and first.new_level == 1
    due_after_first = item.due_at
    duplicate = apply_attempt(db_session, item, "e1e2", False, 1200, "attempt-1")
    assert duplicate.id == first.id
    assert item.due_at == due_after_first
    failed = apply_attempt(db_session, item, "e1d1", False, 900, "attempt-2")
    assert failed.correct is False
    assert item.interval_level == 0

