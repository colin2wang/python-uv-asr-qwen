"""HTTP 接口：健康检查与转写定位。"""

from __future__ import annotations

import logging
import threading

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..audio.io import load_mono_audio, temporary_upload
from ..pipeline.localizer import localize
from ..pipeline.progress import ProgressReporter, create_job, finish, get_job
from .context import AppContext

logger = logging.getLogger(__name__)

router = APIRouter()


def _context(request: Request) -> AppContext:
    return request.app.state.context


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    context = _context(request)
    return {
        "status": "ok",
        "loaded": context.registry.ready,
        "lid": context.registry.lid is not None,
        "model": str(context.settings.model.asr_path),
        "device": context.settings.model.device,
    }


@router.post("/asr/localize")
async def localize_audio(
    request: Request,
    file: UploadFile = File(...),
    question: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
) -> dict[str, Any]:
    context = _context(request)
    if not context.registry.ready:
        raise HTTPException(503, "model not loaded")

    settings = context.settings
    payload = await file.read()
    try:
        with temporary_upload(file.filename, payload) as audio_path:
            mono, sample_rate = load_mono_audio(audio_path, settings.audio.sample_rate)
            return localize(
                context.registry,
                settings,
                audio_path=audio_path,
                mono=mono,
                sample_rate=sample_rate,
                question=question,
                language=language,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("transcription failed")
        raise HTTPException(500, f"transcription failed: {exc}") from exc


def _run_job(
    context: AppContext,
    job_id: str,
    filename: str | None,
    payload: bytes,
    question: Optional[str],
    language: Optional[str],
) -> None:
    """后台线程执行转写，进度与结果写入进度登记表。"""
    settings = context.settings
    reporter = ProgressReporter(job_id)
    try:
        with temporary_upload(filename, payload) as audio_path:
            reporter.stage("decode")
            mono, sample_rate = load_mono_audio(audio_path, settings.audio.sample_rate)
            result = localize(
                context.registry,
                settings,
                audio_path=audio_path,
                mono=mono,
                sample_rate=sample_rate,
                question=question,
                language=language,
                progress=reporter,
            )
        finish(job_id, result=result)
    except Exception as exc:
        logger.exception("job %s transcription failed", job_id)
        finish(job_id, error=str(exc))


@router.post("/asr/jobs")
async def create_localize_job(
    request: Request,
    file: UploadFile = File(...),
    question: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
) -> dict[str, Any]:
    """创建异步转写任务，立即返回任务 ID；进度与结果经 GET /asr/jobs/{job_id} 查询。"""
    context = _context(request)
    if not context.registry.ready:
        raise HTTPException(503, "model not loaded")

    payload = await file.read()
    job_id = create_job()
    threading.Thread(
        target=_run_job,
        args=(context, job_id, file.filename, payload, question, language),
        daemon=True,
        name=f"asr-job-{job_id}",
    ).start()
    return {"job_id": job_id}


@router.get("/asr/jobs/{job_id}")
def localize_job_status(job_id: str) -> dict[str, Any]:
    """查询异步任务进度；status=done 时附带 result，error 时附带 error 信息。"""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job
