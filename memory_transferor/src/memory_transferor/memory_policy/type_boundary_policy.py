from __future__ import annotations


class TypeBoundaryPolicy:
    """Deterministic guardrails for persistent memory type labels."""

    _ACTIVE_WORK_MARKERS = (
        "正在", "项目", "proposal", "project", "system", "平台", "插件", "benchmark",
        "实现", "设计", "开发", "写成", "research", "product",
    )
    _PROFILE_MARKERS = (
        "背景", "身份", "role", "background", "常用", "习惯用", "讨论想法", "语言",
        "domain", "专业", "领域", "研究方向",
    )
    _PREFERENCE_MARKERS = (
        "偏好", "喜欢", "不要", "避免", "格式", "语气", "风格", "输出", "回答",
        "explain", "解释", "先用", "先给", "from now on",
    )

    def normalize_type(self, memory_type: str, key: str, description: str) -> str:
        text = f"{key} {description}".lower()
        current = memory_type or "daily_note"
        if current == "profile" and self._looks_like_active_work(text):
            return "topic"
        if current == "preference" and self._looks_like_profile_language_mode(text):
            return "profile"
        if current == "profile" and self._looks_like_output_preference(text):
            return "preference"
        return current

    def _looks_like_active_work(self, text: str) -> bool:
        if any(marker in text for marker in ("背景", "background", "之前", "transition")):
            return False
        return any(marker in text for marker in self._ACTIVE_WORK_MARKERS)

    def _looks_like_profile_language_mode(self, text: str) -> bool:
        return (
            any(marker in text for marker in ("讨论想法", "习惯用中文", "common language", "language mode"))
            and not any(marker in text for marker in ("输出", "回答", "reply", "response"))
        )

    def _looks_like_output_preference(self, text: str) -> bool:
        return any(marker in text for marker in self._PREFERENCE_MARKERS) and not any(
            marker in text for marker in ("背景", "background", "identity")
        )
