"""语种识别层：语言代码表与检测策略。"""

from .codes import (
    CANTONESE_CHARS,
    LANGUAGE_BY_CODE,
    LATIN_LANGUAGES,
    SCRIPT_CANDIDATES,
    SCRIPT_TO_LANGUAGE,
    SENSEVOICE_TO_QWEN,
)
from .detector import (
    contains_cantonese,
    detect_language_by_script,
    detect_language_by_sensevoice,
    dominant_script,
    normalize_language,
)

__all__ = [
    "CANTONESE_CHARS",
    "LANGUAGE_BY_CODE",
    "LATIN_LANGUAGES",
    "SCRIPT_CANDIDATES",
    "SCRIPT_TO_LANGUAGE",
    "SENSEVOICE_TO_QWEN",
    "contains_cantonese",
    "detect_language_by_script",
    "detect_language_by_sensevoice",
    "dominant_script",
    "normalize_language",
]
