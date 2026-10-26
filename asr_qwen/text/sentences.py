"""Timestamp-preserving sentence grouping for ASR transcripts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


_SENTENCE_END_CHARS = set("。！？!?；;.")


def _is_valid_timestamp(value: object) -> bool:
    return isinstance(value, (int, float)) and value >= 0


def _repair_invalid_timestamps(char_segments: list[dict[str, object]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for raw_segment in char_segments:
        token = str(raw_segment.get("text") or "")
        if not token:
            continue
        records.append(
            {
                "text": token,
                "start": raw_segment.get("start"),
                "end": raw_segment.get("end"),
            }
        )

    invalid_run: list[int] = []

    def repair_run(run_end: int) -> None:
        if not invalid_run:
            return
        left = records[invalid_run[0] - 1] if invalid_run[0] > 0 else None
        right = records[run_end] if run_end < len(records) else None
        left_end = float(left["end"]) if left is not None else None
        right_start = float(right["start"]) if right is not None else None

        if left_end is not None and right_start is not None and right_start >= left_end:
            interval = (right_start - left_end) / (len(invalid_run) + 1)
            for offset, index in enumerate(invalid_run):
                start = left_end + interval * offset
                records[index]["start"] = start
                records[index]["end"] = start + interval
        elif left_end is not None:
            for index in invalid_run:
                records[index]["start"] = left_end
                records[index]["end"] = left_end
        elif right_start is not None:
            for index in invalid_run:
                records[index]["start"] = right_start
                records[index]["end"] = right_start
        else:
            for index in invalid_run:
                records[index]["start"] = 0.0
                records[index]["end"] = 0.0
        invalid_run.clear()

    for index, record in enumerate(records):
        if _is_valid_timestamp(record["start"]) and _is_valid_timestamp(record["end"]):
            repair_run(index)
        else:
            invalid_run.append(index)
    repair_run(len(records))
    return records


def _flush(
    sentences: list[dict[str, object]],
    parts: list[str],
    start: float | None,
    end: float | None,
) -> None:
    text = "".join(parts).strip()
    if text and start is not None and end is not None:
        sentences.append({"text": text, "start": round(float(start), 3), "end": round(float(end), 3)})
    parts.clear()


def merge_to_sentences(
    char_segments: Iterable[dict[str, object]],
    *,
    max_chars: int,
    max_duration_seconds: float,
) -> list[dict[str, object]]:
    """Group timestamped ASR tokens without losing the timeline.

    The aligner tokens are the source of truth. The model's whole-text field can
    contain normalization differences and punctuation absent from the token
    stream; attempting to walk both pointers simultaneously can desynchronize
    them and produce null timestamps after one mismatch.
    """
    char_segments = _repair_invalid_timestamps(list(char_segments))
    sentences: list[dict[str, object]] = []
    parts: list[str] = []
    sentence_start: float | None = None
    sentence_end: float | None = None

    for raw_segment in char_segments:
        if not isinstance(raw_segment, dict):
            continue
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        token = str(raw_segment.get("text") or "")
        if not token or not _is_valid_timestamp(start) or not _is_valid_timestamp(end):
            continue

        start = float(start)
        end = float(end)
        if end < start:
            start, end = end, start

        current_chars = sum(len(part) for part in parts)
        current_duration = end - sentence_start if sentence_start is not None else 0.0
        should_break = bool(parts) and (
            current_chars >= max_chars
            or current_duration >= max_duration_seconds
            or start < (sentence_end if sentence_end is not None else start)
        )
        if should_break:
            _flush(sentences, parts, sentence_start, sentence_end)
            sentence_start = None
            sentence_end = None

        if sentence_start is None:
            sentence_start = start
        sentence_end = max(end, sentence_end) if sentence_end is not None else end

        remaining = token
        while remaining:
            available = max_chars - sum(len(part) for part in parts)
            if available <= 0:
                _flush(sentences, parts, sentence_start, sentence_end)
                sentence_start = start
                sentence_end = end
                available = max_chars
            parts.append(remaining[:available])
            remaining = remaining[available:]

        if parts and parts[-1][-1:] in _SENTENCE_END_CHARS:
            _flush(sentences, parts, sentence_start, sentence_end)
            sentence_start = None
            sentence_end = None

    _flush(sentences, parts, sentence_start, sentence_end)
    return sentences


def number_segments(sentences: Iterable[dict[str, object]]) -> list[dict[str, Any]]:
    """给句段编号（从 1 开始）并补出时长，输出对外统一的句段结构。"""
    numbered: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences, start=1):
        start = round(float(sentence["start"]), 3)
        end = round(float(sentence["end"]), 3)
        numbered.append(
            {
                "index": index,
                "text": str(sentence["text"]),
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
            }
        )
    return numbered
