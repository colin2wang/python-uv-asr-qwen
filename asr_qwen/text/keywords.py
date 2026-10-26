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
                matched.append(
                    {
                        "timestamp": [segments[index]["start"], segments[last]["end"]],
                        "rule": keyword,
                        "confidence": 1.0,
                    }
                )
            start = index + 1
    return matched
