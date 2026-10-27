"""Timestamp-preserving sentence grouping for ASR transcripts."""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from typing import Any


_SENTENCE_END_CHARS = set("。！？!?；;.")
# Punctuation that consumes no token: it exists only in the full text, not in tokens
_PUNCT_CHARS = set("。！？!?；;：:，,、（）()「」『』【】《》〈〉…—–-·・.\"'")
# Units for splitting Latin full text into words: whitespace / word / punctuation run
_LATIN_UNIT_PATTERN = re.compile(r"\s+|[\w']+|[^\s\w]+", re.UNICODE)

# Symbols that must not be followed by a space (opening quotes, brackets, currency…)
_NO_SPACE_AFTER = set("（【《“‘([{<$_")
# Punctuation followed by a digit reads as a decimal or thousands separator: no space
_DECIMAL_POINTS = set(".,")


def _needs_space(left: str, right: str) -> bool:
    """Whether a space belongs between two adjacent tokens.

    Latin aligner tokens are word-level and carry no spaces, so merging re-inserts them:
    - between words (English, or CJK/Latin mixtures);
    - never inside CJK;
    - punctuation stays attached to the previous token, spacing after it depends on script.
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
    """Whether a piece ends on sentence-final punctuation."""
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
    """Join token pieces, inserting a space where the parts recorded one."""
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
    text: str = "",
) -> list[dict[str, object]]:
    """Group timestamped ASR tokens into sentences, keeping the timeline.

    When the model's full text is passed it becomes the skeleton (as the reference
    implementation does): punctuation and whitespace are copied into the segment but
    consume no token, so the output keeps the original punctuation; timestamps come from
    the token boundaries found by alignment. Without text it falls back to concatenating
    tokens, re-inserting spaces for Latin scripts by rule.

    Segments break on sentence-final punctuation, once the buffer reaches max_chars, once
    the span reaches max_duration_seconds, or when timestamps move backwards; with
    min_gap_seconds > 0 a pause between tokens breaks as well. A zero value disables the
    corresponding rule.
    """
    tokens = _ordered_tokens(char_segments)
    if text:
        return _merge_from_text(
            text,
            tokens,
            max_chars=max_chars,
            max_duration_seconds=max_duration_seconds,
            min_gap_seconds=min_gap_seconds,
        )
    return _merge_from_tokens(
        tokens,
        max_chars=max_chars,
        max_duration_seconds=max_duration_seconds,
        min_gap_seconds=min_gap_seconds,
    )


def _merge_from_text(
    text: str,
    tokens: list[tuple[str, float, float]],
    *,
    max_chars: int,
    max_duration_seconds: float,
    min_gap_seconds: float,
) -> list[dict[str, object]]:
    """Merge on the full text as skeleton: punctuation and spaces survive, timestamps
    come from the aligned tokens."""
    units = _split_units(text, _is_char_level(tokens))
    anchors = _align_timestamps(units, tokens)
    sentences: list[dict[str, object]] = []
    buffer: list[str] = []
    size = 0
    start: float | None = None
    end: float | None = None
    last_end = 0.0

    def flush() -> None:
        nonlocal buffer, size, start, end, last_end
        piece = "".join(buffer).strip()
        if piece and start is not None and end is not None:
            sentences.append({"text": piece, "start": round(start, 3), "end": round(end, 3)})
            last_end = end
        buffer = []
        size = 0
        start = None
        end = None

    for unit, anchor in zip(units, anchors):
        if anchor is None or _is_punctuation(unit):
            # Punctuation, whitespace and unaligned characters only feed the text
            buffer.append(unit)
            size += len(unit)
            if _ends_sentence(unit):
                if start is None:
                    start = end = last_end
                flush()
            continue

        if buffer and (
            (max_duration_seconds > 0 and start is not None and anchor[1] - start >= max_duration_seconds)
            or (min_gap_seconds > 0 and end is not None and anchor[0] - end >= min_gap_seconds)
            or (end is not None and anchor[0] < end)
        ):
            flush()
        if max_chars > 0 and size >= max_chars:
            flush()
        if start is None:
            start = anchor[0]
        end = anchor[1] if end is None else max(end, anchor[1])
        buffer.append(unit)
        size += len(unit)

    if start is None and buffer:
        start = end = last_end
    flush()
    return sentences


def _merge_from_tokens(
    tokens: list[tuple[str, float, float]],
    *,
    max_chars: int,
    max_duration_seconds: float,
    min_gap_seconds: float,
) -> list[dict[str, object]]:
    sentences: list[dict[str, object]] = []
    # Each element is (piece, whether a space belongs before the previous element)
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
            # Without a cap the token is never split; it stays one piece
            available = len(remaining) if max_chars <= 0 else max_chars - sum(len(piece) for piece, _ in parts)
            if available <= 0:
                _flush(sentences, parts, sentence_start, sentence_end)
                sentence_start = start
                sentence_end = end
                available = max_chars
            piece = remaining[:available]
            tail = parts[-1][0][-1:] if parts else ""
            # Pieces split out of one long token must not introduce a space
            parts.append((piece, is_head and _needs_space(tail, piece[:1])))
            remaining = remaining[available:]
            is_head = False

        # Sentence boundary: punctuation, or a pause before the next token
        gap = tokens[index + 1][1] - end if index + 1 < len(tokens) else 0.0
        if parts and (
            _ends_sentence(parts[-1][0]) or (min_gap_seconds > 0 and gap >= min_gap_seconds)
        ):
            _flush(sentences, parts, sentence_start, sentence_end)
            sentence_start = None
            sentence_end = None

    _flush(sentences, parts, sentence_start, sentence_end)
    return sentences


def _is_char_level(tokens: list[tuple[str, float, float]]) -> bool:
    """Whether tokens are mostly single characters (CJK); Latin tokens are word-level."""
    if not tokens:
        return True
    single = sum(1 for token, _, _ in tokens if len(token) == 1)
    return single / len(tokens) > 0.8


def _split_units(text: str, char_level: bool) -> list[str]:
    """Split the full text into alignment units: per character, or per word/space/punct."""
    return list(text) if char_level else _LATIN_UNIT_PATTERN.findall(text)


def _is_punctuation(unit: str) -> bool:
    """Whether a unit is whitespace or punctuation (consumes no token, skipped in aligning)."""
    stripped = unit.strip()
    return not stripped or all(char in _PUNCT_CHARS for char in stripped)


def _align_timestamps(
    units: list[str],
    tokens: list[tuple[str, float, float]],
) -> list[tuple[float, float] | None]:
    """Align full-text units with tokens; each unit gets (start, end) or None.

    The full text and the token stream can differ through normalization (ITN, casing,
    punctuation), so matching the longest common runs is safer than walking two pointers
    character by character: unmatched units simply get no timestamp instead of shifting
    everything that follows.
    """
    anchors: list[tuple[float, float] | None] = [None] * len(units)
    if not tokens:
        return anchors
    words = [(index, unit) for index, unit in enumerate(units) if not _is_punctuation(unit)]
    matcher = difflib.SequenceMatcher(
        a=[unit for _, unit in words],
        b=[token for token, _, _ in tokens],
        autojunk=False,
    )
    for a_start, b_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            unit_index = words[a_start + offset][0]
            _, start, end = tokens[b_start + offset]
            anchors[unit_index] = (start, end)
    return anchors


def _ordered_tokens(char_segments: Iterable[dict[str, object]]) -> list[tuple[str, float, float]]:
    """Keep tokens that have text and valid timestamps, as (text, start, end)."""
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
    """Number segments from 1 and add durations, producing the public segment shape."""
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
