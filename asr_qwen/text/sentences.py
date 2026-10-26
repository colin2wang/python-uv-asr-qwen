"""Timestamp-preserving sentence grouping for ASR transcripts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


_SENTENCE_END_CHARS = set("。！？!?；;.")

# 紧跟其前不需要空格的符号（开引号、开括号、货币符号等）
_NO_SPACE_AFTER = set("（【《“‘([{<$_")
# 这些标点后若是数字，视为小数点或千分位，不补空格
_DECIMAL_POINTS = set(".,")


def _needs_space(left: str, right: str) -> bool:
    """相邻两个 token 之间是否补空格。

    拉丁语言的 aligner token 是词级且不含空格，拼接时按此规则补回：
    - 词与词之间补（英文词间、中英混排）；
    - CJK 内部不补；
    - 标点紧跟前一个 token，其后按语言再决定是否补空格。
    """
    if not left or not right or left.isspace() or right.isspace():
        return False
    if not right.isalnum():
        return False
    if left in _NO_SPACE_AFTER:
        return False
    if left in _DECIMAL_POINTS and right.isdigit():
        return False
    if left.isalnum():
        return left.isascii() or right.isascii()
    return left.isascii() and right.isascii()


def _ends_sentence(piece: str) -> bool:
    """片段是否落在句末标点上。"""
    return piece[-1:] in _SENTENCE_END_CHARS


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


def _join(parts: list[tuple[str, bool]]) -> str:
    """按 parts 记录的空格标记拼接 token。"""
    text = ""
    for piece, spaced in parts:
        if spaced and text:
            text += " "
        text += piece
    return text


def _flush(
    sentences: list[dict[str, object]],
    parts: list[tuple[str, bool]],
    start: float | None,
    end: float | None,
) -> None:
    text = _join(parts).strip()
    if text and start is not None and end is not None:
        sentences.append({"text": text, "start": round(float(start), 3), "end": round(float(end), 3)})
    parts.clear()


def merge_to_sentences(
    char_segments: Iterable[dict[str, object]],
    *,
    max_chars: int,
    max_duration_seconds: float,
    min_gap_seconds: float,
) -> list[dict[str, object]]:
    """Group timestamped ASR tokens into sentences, keeping the timeline.

    The aligner tokens are the source of truth. The model's whole-text field can
    contain normalization differences and punctuation absent from the token
    stream; attempting to walk both pointers simultaneously can desynchronize
    them and produce null timestamps after one mismatch.

    断句条件：字符数达 max_chars、时长达 max_duration_seconds、句末标点
    （_ends_sentence）、时间戳倒流；min_gap_seconds > 0 时相邻 token 的停顿也断句。
    max_chars / max_duration_seconds / min_gap_seconds 为 0 时该项不生效。
    """
    tokens = _ordered_tokens(char_segments)
    sentences: list[dict[str, object]] = []
    # 每个元素为 (片段, 是否与前一片段之间补空格)
    parts: list[tuple[str, bool]] = []
    sentence_start: float | None = None
    sentence_end: float | None = None

    for index, (token, start, end) in enumerate(tokens):
        current_chars = sum(len(piece) for piece, _ in parts)
        current_duration = end - sentence_start if sentence_start is not None else 0.0
        should_break = bool(parts) and (
            (max_chars > 0 and current_chars >= max_chars)
            or (max_duration_seconds > 0 and current_duration >= max_duration_seconds)
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
        is_head = True
        while remaining:
            # 未设上限时不切分 token，粘成一个整体
            available = len(remaining) if max_chars <= 0 else max_chars - sum(len(piece) for piece, _ in parts)
            if available <= 0:
                _flush(sentences, parts, sentence_start, sentence_end)
                sentence_start = start
                sentence_end = end
                available = max_chars
            piece = remaining[:available]
            tail = parts[-1][0][-1:] if parts else ""
            # 超长 token 被切开时，后续片段不再补空格
            parts.append((piece, is_head and _needs_space(tail, piece[:1])))
            remaining = remaining[available:]
            is_head = False

        # 句边界：句末标点/换行，或与后续 token 之间的停顿达到阈值
        gap = tokens[index + 1][1] - end if index + 1 < len(tokens) else 0.0
        if parts and (
            _ends_sentence(parts[-1][0]) or (min_gap_seconds > 0 and gap >= min_gap_seconds)
        ):
            _flush(sentences, parts, sentence_start, sentence_end)
            sentence_start = None
            sentence_end = None

    _flush(sentences, parts, sentence_start, sentence_end)
    return sentences


def _ordered_tokens(char_segments: Iterable[dict[str, object]]) -> list[tuple[str, float, float]]:
    """取出文本非空、时间戳合法的 token，按 (文本, 起始, 结束) 排列。"""
    tokens: list[tuple[str, float, float]] = []
    for record in _repair_invalid_timestamps(list(char_segments)):
        token = str(record.get("text") or "")
        start = record.get("start")
        end = record.get("end")
        if not token or not _is_valid_timestamp(start) or not _is_valid_timestamp(end):
            continue
        start = float(start)
        end = float(end)
        tokens.append((token, min(start, end), max(start, end)))
    return tokens


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
