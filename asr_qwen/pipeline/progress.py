"""请求级进度登记：后台转写线程写入，查询接口读取。"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}

# 任务结果保留时长，超期由 create 时顺带清理
_RETAIN_SECONDS = 3600.0


def create_job() -> str:
    """登记新任务，返回任务 ID；顺带清理超期旧任务。"""
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    with _lock:
        expired = [k for k, v in _jobs.items() if now - v["updated"] > _RETAIN_SECONDS]
        for key in expired:
            del _jobs[key]
        _jobs[job_id] = {
            "status": "queued",
            "stage": "queued",
            "done": 0,
            "total": 0,
            "result": None,
            "error": None,
            "updated": now,
        }
    return job_id


def set_stage(job_id: str, stage: str, done: int = 0, total: int = 0) -> None:
    """更新任务阶段与分块进度（done/total）。"""
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(status="running", stage=stage, done=done, total=total, updated=time.time())


def finish(job_id: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    """结束任务：成功带 result，失败带 error。"""
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(
                status="error" if error else "done",
                result=result,
                error=error,
                updated=time.time(),
            )


def get_job(job_id: str) -> dict[str, Any] | None:
    """读取任务快照；不存在返回 None。"""
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job is not None else None


class ProgressReporter:
    """pipeline 用的进度上报句柄，封装任务 ID。"""

    def __init__(self, job_id: str) -> None:
        self._job_id = job_id

    def stage(self, stage: str, done: int = 0, total: int = 0) -> None:
        set_stage(self._job_id, stage, done, total)
