"""关键词定位：把查询词映射到对齐时间戳。"""

from __future__ import annotations

from typing import Any


def find_keywords(
    text: str,
    segments: list[dict[str, Any]],
    question: str,
) -> list[dict[str, Any]]:
    """按逗号分隔的查询词在文本中定位，返回命中时间区间。"""
    matched: list[dict[str, Any]] = []
    if not question or not segments:
        return matched
    keywords = [word.strip() for word in question.replace("，", ",").split(",") if word.strip()]
    total = len(segments)
    for keyword in keywords:
        start = 0
        while True:
            index = text.find(keyword, start)
            if index < 0:
                break
            last = index + len(keyword) - 1
            if index < total and last < total:
                begin = round(float(segments[index]["start"]), 3)
                end = round(float(segments[last]["end"]), 3)
                matched.append(
                    {
                        "rule": keyword,
                        "start": begin,
                        "end": end,
                        "timestamp": [begin, end],
                        "confidence": 1.0,
                    }
                )
            start = index + 1
    return matched


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
