"""语种识别相关的常量映射表。"""

# SenseVoice 语言标签 → Qwen3-ASR 语言名（仅映射 Qwen3-ASR 支持的 30 语言）
SENSEVOICE_TO_QWEN = {
    "zh": "Chinese", "en": "English", "yue": "Cantonese", "ja": "Japanese",
    "ko": "Korean", "ru": "Russian", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "pt": "Portuguese", "ar": "Arabic",
    "hi": "Hindi", "th": "Thai", "vi": "Vietnamese", "id": "Indonesian",
    "ms": "Malay", "nl": "Dutch", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "pl": "Polish", "cs": "Czech", "fil": "Filipino",
    "fa": "Persian", "el": "Greek", "ro": "Romanian", "hu": "Hungarian",
    "mk": "Macedonian",
}

LANGUAGE_BY_CODE = {
    "ja": "Japanese", "jp": "Japanese", "jpn": "Japanese",
    "ko": "Korean", "kor": "Korean",
    "ru": "Russian", "rus": "Russian",
    "zh": "Chinese", "cmn": "Chinese",
    "en": "English", "eng": "English",
    "de": "German", "deu": "German",
    "fr": "French", "fra": "French",
    "es": "Spanish", "spa": "Spanish",
    "it": "Italian", "ita": "Italian",
    "pt": "Portuguese", "por": "Portuguese",
    "ar": "Arabic", "ara": "Arabic",
    "hi": "Hindi", "hin": "Hindi",
    "th": "Thai", "tha": "Thai",
    "vi": "Vietnamese", "vie": "Vietnamese",
    "id": "Indonesian", "ind": "Indonesian",
    "ms": "Malay", "zsm": "Malay",
    "yue": "Cantonese", "cantonese": "Cantonese",
}

# 拉丁字母语系（字符集无法区分）
LATIN_LANGUAGES = {
    "English", "German", "French", "Spanish", "Italian", "Portuguese",
    "Dutch", "Swedish", "Danish", "Finnish", "Polish", "Czech",
    "Romanian", "Hungarian", "Indonesian", "Malay", "Vietnamese", "Filipino",
}

# 非拉丁语脚本候选（唱歌时模型对多个强制语言输出同一个母语脚本）
SCRIPT_CANDIDATES = ["Russian", "Chinese", "Japanese", "Korean"]
SCRIPT_TO_LANGUAGE = {"Cyrillic": "Russian", "Han": "Chinese", "Kana": "Japanese", "Hangul": "Korean"}

# 粤语专用字（几乎不出现在普通话中）
CANTONESE_CHARS = set("嘅唔咗哋佢乜冇啲喺嚟嘢瞓冧掂啱乸揾喎㗎啩攞嘥嬲咁揸嚿")
