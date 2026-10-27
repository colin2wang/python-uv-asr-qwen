"""Per-request progress registry: worker threads write, the status endpoint reads."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

# How long a finished job is kept; expired jobs are cleaned up on the next create
_RETAIN_SECONDS = 3600.0

# Stage order and weights (weights sum to 1)
# Overall percentage = sum of finished stage weights + current weight x stage ratio
_STAGE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("decode", 0.10),
    ("vad", 0.08),
    ("transcribe", 0.55),
    ("language", 0.12),
    ("postprocess", 0.15),
)
_STAGE_RANK = {name: rank for rank, (name, _) in enumerate(_STAGE_WEIGHTS)}

# Display names served to clients so no client has to maintain its own wording
STAGE_LABELS: dict[str, str] = {
    "queued": "Queued",
    "upload": "Uploading",
    "decode": "Decoding audio",
    "vad": "Splitting speech",
    "transcribe": "Transcribing",
    "language": "Correcting language",
    "postprocess": "Post-processing",
    "done": "Done",
    "error": "Failed",
}


def _span(stage: str) -> tuple[float, float]:
    """Return a stage's [start, end) slice of the overall progress; empty if unknown."""
    base = 0.0
    for name, weight in _STAGE_WEIGHTS:
        if name == stage:
            return base, base + weight
        base += weight
    return base, base


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def create_job() -> str:
    """Register a new job and return its id; expired jobs are cleaned up on the way."""
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    with _lock:
        expired = [k for k, v in _jobs.items() if now - v["updated"] > _RETAIN_SECONDS]
        for key in expired:
            del _jobs[key]
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "rank": -1,
            "progress": 0.0,
            "done": 0,
            "total": 0,
            "result": None,
            "error": None,
            "created": now,
            "updated": now,
        }
    return job_id


def set_progress(
    job_id: str,
    stage: str,
    ratio: float,
    done: int = 0,
    total: int = 0,
) -> None:
    """Update the stage and overall progress; neither progress nor stage rank goes back."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        start, end = _span(stage)
        value = _clamp(start + (end - start) * _clamp(ratio))
        job["progress"] = max(job["progress"], value)
        if _STAGE_RANK.get(stage, -1) >= job["rank"]:
            job["stage"] = stage
            job["rank"] = _STAGE_RANK.get(stage, job["rank"])
        job["done"] = done
        job["total"] = total
        job["status"] = "running"
        job["updated"] = time.time()


def finish(job_id: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    """Finish a job: success carries result (progress 100%), failure carries error."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job["status"] = "error" if error else "done"
        job["stage"] = "error" if error else "done"
        job["rank"] = len(_STAGE_WEIGHTS)
        if error is None:
            job["progress"] = 1.0
        job["result"] = result
        job["error"] = error
        job["updated"] = time.time()


def get_job(job_id: str) -> dict[str, Any] | None:
    """Return a snapshot of the job, or None when it is unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        now = time.time()
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "stage": job["stage"],
            "stage_label": STAGE_LABELS.get(job["stage"], job["stage"]),
            "progress": round(job["progress"], 4),
            "percent": int(round(job["progress"] * 100)),
            "done": job["done"],
            "total": job["total"],
            "elapsed_seconds": round(now - job["created"], 2),
            "result": job["result"],
            "error": job["error"],
        }


class ProgressReporter:
    """Progress handle used by the pipeline: report per stage, converted to a percentage.

    Sub-flows that restart their own progress from zero (such as a re-transcription) get
    a derived handle via `subrange`, so their 0..1 progress maps into a slice of the
    parent stage and the overall progress stays monotonic.
    """

    def __init__(
        self,
        job_id: str,
        *,
        parent: "ProgressReporter | None" = None,
        alias: str | None = None,
        low: float = 0.0,
        high: float = 1.0,
    ) -> None:
        self._job_id = job_id
        self._parent = parent
        self._alias = alias
        self._low = low
        self._high = high

    def stage(self, stage: str, done: int = 0, total: int = 0) -> None:
        """Enter a stage or report chunk progress (done/total)."""
        self.advance(stage, done / total if total > 0 else 0.0, done, total)

    def advance(self, stage: str, ratio: float = 0.0, done: int = 0, total: int = 0) -> None:
        """Report the completion ratio inside a stage (0..1), optionally with counters."""
        if self._alias is not None:
            stage = self._alias
        if self._parent is not None:
            self._parent.advance(
                stage,
                self._low + (self._high - self._low) * _clamp(ratio),
                done,
                total,
            )
            return
        set_progress(self._job_id, stage, _clamp(ratio), done, total)

    def subrange(self, low: float, high: float, *, alias: str | None = None) -> "ProgressReporter":
        """Derive a child handle mapping a sub-flow's 0..1 progress into [low, high]."""
        return ProgressReporter(self._job_id, parent=self, alias=alias, low=low, high=high)
