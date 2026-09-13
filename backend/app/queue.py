from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AnalysisJob


ACTIVE_STATUSES = ("pending", "running")


def create_job(session: Session, job_type: str, payload: dict, dedupe_key: str, priority: int = 0) -> tuple[AnalysisJob, bool]:
    existing = session.scalar(
        select(AnalysisJob).where(AnalysisJob.dedupe_key == dedupe_key, AnalysisJob.status.in_(ACTIVE_STATUSES))
    )
    if existing:
        return existing, True
    job = AnalysisJob(job_type=job_type, payload=payload, dedupe_key=dedupe_key, priority=priority)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, False


def claim_job(session: Session, worker_id: str) -> AnalysisJob | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(AnalysisJob)
        .where(
            or_(
                (AnalysisJob.status == "pending") & (AnalysisJob.run_after <= now),
                (AnalysisJob.status == "running") & (AnalysisJob.lease_expires_at < now),
            )
        )
        .order_by(AnalysisJob.priority.desc(), AnalysisJob.created_at)
        .limit(1)
    )
    if session.bind and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = session.scalar(stmt)
    if not job:
        return None
    job.status = "running"
    job.locked_by = worker_id
    job.lease_expires_at = now + timedelta(minutes=5)
    job.attempts += 1
    job.started_at = job.started_at or now
    session.commit()
    session.refresh(job)
    return job


def update_progress(session: Session, job_id: str, current: int, total: int, step: str) -> None:
    job = session.get(AnalysisJob, job_id)
    if job and job.status == "running":
        job.progress_current = current
        job.progress_total = total
        job.current_step = step
        job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        session.commit()


def finish_job(session: Session, job: AnalysisJob, result: dict) -> None:
    current = session.get(AnalysisJob, job.id)
    if current:
        current.status = "succeeded"
        current.result = result
        current.finished_at = datetime.now(timezone.utc)
        current.progress_current = current.progress_total or 1
        current.progress_total = current.progress_total or 1
        current.current_step = "已完成"
        current.locked_by = None
        current.lease_expires_at = None
        session.commit()


def fail_job(session: Session, job: AnalysisJob, exc: Exception) -> None:
    current = session.get(AnalysisJob, job.id)
    if not current:
        return
    current.error_code = getattr(exc, "code", "job_failed")
    current.error_message = getattr(exc, "message", str(exc))
    current.locked_by = None
    current.lease_expires_at = None
    if current.attempts < current.max_attempts and not current.cancel_requested:
        current.status = "pending"
        current.run_after = datetime.now(timezone.utc) + timedelta(seconds=min(60, 2**current.attempts))
    else:
        current.status = "cancelled" if current.cancel_requested else "failed"
        current.finished_at = datetime.now(timezone.utc)
    session.commit()

