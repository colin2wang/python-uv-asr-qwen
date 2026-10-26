"""标题拆分：规则优先，必要时借助 LLM，标题必须是原文的起始前缀。"""

from __future__ import annotations

import json
import re
import urllib.request

from ..config.settings import TitleSettings

# 规则拆分出的标题足够短且正文非空时，无需调用 LLM
OBVIOUS_TITLE_MAX_CHARS = 30

_TITLE_LABEL_PATTERN = re.compile(r"^\s*(?:标题|题目|title)\s*[:：]\s*", re.I)
_SENTENCE_PATTERN = "^(.{{1,{max_chars}}}?[。．！？!?；;：:])"
_CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

_SYSTEM_PROMPT = (
    "You split transcribed speech into an optional title and body. "
    "A title is a short opening naming phrase, not a complete narrative sentence. "
    'Return strict JSON: {"title": string, "body": string}. '
    "The title must be copied exactly from the beginning of the input, or be empty. "
    "The body must be the remaining input after removing that exact opening title. "
    "Never translate, transliterate, rewrite, or add punctuation."
)


class TitleSplitter:
    """把 ASR 转写文本拆分为标题与正文。"""

    def __init__(self, settings: TitleSettings) -> None:
        self._settings = settings

    def split(self, text: str, use_llm: bool | None = None) -> dict[str, str]:
        """Split an ASR transcript into an exact-prefix semantic title and body."""
        text = str(text or "").strip()
        if not text:
            return {"title": "", "body": ""}

        rule_title, rule_body = self._rule_split(text)
        obvious = bool(rule_title) and len(rule_title) <= OBVIOUS_TITLE_MAX_CHARS and bool(rule_body)
        if use_llm is False or obvious:
            return {"title": rule_title, "body": rule_body}

        try:
            title, body = self._llm_split(text)
            return {"title": title, "body": body}
        except Exception:
            if use_llm is True:
                raise
            return {"title": rule_title, "body": rule_body}

    def _word_count(self, value: str) -> int:
        return len([word for word in re.split(r"\s+", value.strip()) if word])

    def _looks_like_title(self, value: str) -> bool:
        value = value.strip()
        if not value or len(value) > self._settings.max_chars:
            return False
        if self._word_count(value) > self._settings.max_words:
            return False
        if len(value) <= 2 and not _CJK_PATTERN.search(value):
            return False
        return True

    def _rule_split(self, text: str) -> tuple[str, str]:
        text = _TITLE_LABEL_PATTERN.sub("", text).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1 and self._looks_like_title(lines[0]):
            return lines[0], "\n".join(lines[1:]).strip()

        pattern = _SENTENCE_PATTERN.format(max_chars=self._settings.max_chars)
        sentence = re.match(pattern, text, re.S)
        if sentence and self._looks_like_title(sentence.group(1)):
            title = sentence.group(1).strip()
            return title, text[len(sentence.group(1)):].strip()

        if "\n" not in text:
            words = text.split()
            head = " ".join(words[: self._settings.max_words])
            if len(words) > self._settings.max_words and self._looks_like_title(head):
                return head, " ".join(words[self._settings.max_words:])

        return "", text

    def _llm_split(self, text: str) -> tuple[str, str]:
        llm = self._settings.llm
        if not llm.api_key:
            raise RuntimeError("title.llm.api_key is required")

        payload = {
            "model": llm.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        request = urllib.request.Request(
            f"{llm.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {llm.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=llm.timeout_seconds) as response:
            result = json.load(response)

        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        title = str(parsed.get("title", "")).strip()
        if not title:
            return "", text

        match = re.match(r"\s*" + re.escape(title), text, re.S)
        if not match:
            raise ValueError("LLM title is not an exact opening prefix")
        source_title = text[:match.end()].strip()
        body = text[match.end():].strip()
        return source_title, body
