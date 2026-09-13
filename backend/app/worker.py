from __future__ import annotations

import logging
import os
import socket
import time

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .integrations.chess_com import ChessComClient
from .integrations.stockfish import StockfishAdapter
from .models import AnalysisJob, Game, PlayerProfile
from .queue import claim_job, fail_job, finish_job, update_progress
from .services.analysis import analyze_game
from .services.ingestion import sync_profile
from .services.training import generate_weekly_plan


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("chess-coach-worker")


def handle_job(job_id: str) -> None:
    with SessionLocal() as session:
        job = session.get(AnalysisJob, job_id)
        if not job:
            return
        progress = lambda current, total, step: update_progress(session, job.id, current, total, step)
        try:
            if job.cancel_requested:
                job.status = "cancelled"
                session.commit()
                return
            if job.job_type == "sync_games":
                profile = session.get(PlayerProfile, job.payload["profile_id"])
                if not profile:
                    raise RuntimeError("profile not found")
                result = sync_profile(session, profile, ChessComClient(), progress)
                new_games = session.scalars(
                    select(Game).where(Game.profile_id == profile.id, Game.analysis_status == "queued")
                ).all()
                from .queue import create_job

                created_count = 0
                for game in new_games:
                    _, already_active = create_job(
                        session,
                        "analyze_game",
                        {"game_id": game.id},
                        f"analyze:{game.id}",
                        priority=1,
                    )
                    created_count += int(not already_active)
                result["analysis_jobs_created"] = created_count
            elif job.job_type == "analyze_game":
                game = session.get(Game, job.payload["game_id"])
                if not game:
                    raise RuntimeError("game not found")
                with StockfishAdapter() as engine:
                    result = analyze_game(session, game, engine, progress)
            elif job.job_type == "generate_plan":
                profile = session.get(PlayerProfile, job.payload["profile_id"])
                if not profile:
                    raise RuntimeError("profile not found")
                plan = generate_weekly_plan(session, profile)
                result = {"plan_id": plan.id}
            else:
                raise RuntimeError(f"unsupported job type: {job.job_type}")
            finish_job(session, job, result)
        except Exception as exc:
            logger.exception("job %s failed", job.id)
            fail_job(session, job, exc)


def run() -> None:
    init_db()
    settings = get_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        with SessionLocal() as session:
            job = claim_job(session, worker_id)
        if job:
            handle_job(job.id)
        else:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
