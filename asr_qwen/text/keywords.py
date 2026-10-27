"""Keyword localization: map query terms onto aligned timestamps."""

from __future__ import annotations

import bisect
from typing import Any


def find_keywords(
    segments: list[dict[str, Any]],
    question: str,
) -> list[dict[str, Any]]:
    """Locate comma-separated query terms on the token stream, returning time ranges.

    Matching runs on the plain concatenation of token texts: aligner tokens (especially
    for Latin languages) contain no spaces while the full transcript does, so indexing
    tokens with offsets from the full text would be off. Whitespace inside a query term
    is ignored too, so `killing me softly` matches English lyrics.
    """
    matched: list[dict[str, Any]] = []
    if not question or not segments:
        return matched
    tokens, flat, offsets = _flatten(segments)
    if not tokens:
        return matched
    for keyword in _parse(question):
        needle = "".join(keyword.split())
        if not needle:
            continue
        position = 0
        while True:
            index = flat.find(needle, position)
            if index < 0:
                break
            first = _token_at(offsets, index)
            last = _token_at(offsets, index + len(needle) - 1)
            begin = round(float(tokens[first]["start"]), 3)
            end = round(float(tokens[last]["end"]), 3)
            matched.append(
                {
                    "rule": keyword,
                    "start": begin,
                    "end": end,
                    "timestamp": [begin, end],
                    "confidence": 1.0,
                }
            )
            position = index + 1
    return matched


def _parse(question: str) -> list[str]:
    return [word.strip() for word in question.replace("，", ",").split(",") if word.strip()]


def _flatten(
    segments: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, list[int]]:
    """Concatenate token texts; return usable tokens, the string and each start offset.

    Tokens without text or with invalid timestamps are skipped so keyword hits and
    sentence grouping see the same token set.
    """
    tokens: list[dict[str, Any]] = []
    pieces: list[str] = []
    offsets: list[int] = []
    position = 0
    for segment in segments:
        token = str(segment.get("text") or "")
        if not token or not _timestamps_valid(segment):
            continue
        offsets.append(position)
        position += len(token)
        pieces.append(token)
        tokens.append(segment)
    return tokens, "".join(pieces), offsets


def _timestamps_valid(segment: dict[str, Any]) -> bool:
    start = segment.get("start")
    end = segment.get("end")
    return isinstance(start, (int, float)) and isinstance(end, (int, float)) and start >= 0 and end >= 0


def _token_at(offsets: list[int], position: int) -> int:
    """Return the index of the token covering a position in the concatenated string."""
    index = bisect.bisect_right(offsets, position) - 1
    return max(0, min(len(offsets) - 1, index))


def with_sentence_index(
    matched: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate each hit with the segment index (1-based) it belongs to."""
    located: list[dict[str, Any]] = []
    for item in matched:
        hit = dict(item)
        hit["segment_index"] = _segment_index(sentences, float(hit["start"]))
        located.append(hit)
    return located


def _segment_index(sentences: list[dict[str, Any]], position: float) -> int | None:
    for sentence in sentences:
        if float(sentence["start"]) <= position <= float(sentence["end"]):
            return int(sentence["index"])
    return None
