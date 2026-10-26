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

# 阶段顺序与权重（权重之和为 1）
# 整体百分比 = 已完成阶段权重之和 + 当前阶段权重 × 阶段内完成比例
_STAGE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("decode", 0.10),
    ("vad", 0.08),
    ("transcribe", 0.55),
    ("language", 0.12),
    ("postprocess", 0.15),
)
_STAGE_RANK = {name: rank for rank, (name, _) in enumerate(_STAGE_WEIGHTS)}

# 阶段展示名，供前端直接显示，避免各端重复维护文案
STAGE_LABELS: dict[str, str] = {
    "queued": "排队中",
    "upload": "上传中",
    "decode": "解码音频",
    "vad": "语音分段",
    "transcribe": "转写中",
    "language": "语种校正",
    "postprocess": "后处理",
    "done": "已完成",
    "error": "失败",
}


def _span(stage: str) -> tuple[float, float]:
    """返回阶段在整体进度中的 [起点, 终点) 区间（0~1）；未知阶段为空区间。"""
    base = 0.0
    for name, weight in _STAGE_WEIGHTS:
        if name == stage:
            return base, base + weight
        base += weight
    return base, base


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def create_job() -> str:
    """登记新任务，返回任务 ID；顺带清理超期旧任务。"""
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
    """更新任务阶段与整体进度；进度与阶段序号只增不减（避免二次转写让进度条倒退）。"""
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
    """结束任务：成功带 result（进度拉满），失败带 error（保留最后进度）。"""
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
    """读取任务快照；不存在返回 None。"""
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
    """pipeline 用的进度上报句柄：按阶段上报，内部换算为整体百分比。

    二次转写等会把局部进度重新从 0 开始的子流程，用 subrange 派生子句柄，
    使其 0~1 的进度落在父阶段的指定区间内，整体进度因此保持单调。
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
        """进入阶段或上报分块进度（done/total）。"""
        self.advance(stage, done / total if total > 0 else 0.0, done, total)

    def advance(self, stage: str, ratio: float = 0.0, done: int = 0, total: int = 0) -> None:
        """上报阶段内完成比例（0~1），可附带分块计数。"""
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
        """派生子句柄：子流程 0~1 的进度映射到父阶段的 [low, high] 区间。"""
        return ProgressReporter(self._job_id, parent=self, alias=alias, low=low, high=high)
