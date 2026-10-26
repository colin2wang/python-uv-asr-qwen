"""关键词定位：把查询词映射到对齐时间戳。"""

from __future__ import annotations

import bisect
from typing import Any


def find_keywords(
    segments: list[dict[str, Any]],
    question: str,
) -> list[dict[str, Any]]:
    """按逗号分隔的查询词在 token 序列上定位，返回命中时间区间。

    匹配串是 token 文本的直接拼接：对齐 token（尤其拉丁语言）不含空格，
    而转写全文有空格等规范化差异，用全文下标去索引 token 会整体错位。
    查询词内部空白同样先去掉，因此 `killing me softly` 能命中英文歌词。
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
    """拼接 token 文本，返回可用 token 列表、拼接串与各 token 的起始下标。

    跳过无文本或时间戳非法的 token，使关键词命中与句段合并看到同一批 token。
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
    """拼接串下标落在第几个 token 上。"""
    index = bisect.bisect_right(offsets, position) - 1
    return max(0, min(len(offsets) - 1, index))


def with_sentence_index(
    matched: list[dict[str, Any]],
    sentences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """给命中项标注所在句段序号（1 起），便于直接跳到对应句段。"""
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
