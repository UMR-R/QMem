from __future__ import annotations

from copy import deepcopy
from typing import Any


BASE_DISPLAY_TAXONOMY: dict[str, list[dict[str, Any]]] = {
    "profile": [
        {
            "group_id": "identity",
            "title": {"zh": "身份", "en": "Identity"},
            "source_fields": ["name_or_alias", "role_identity", "organization_or_affiliation"],
            "match_terms": [
                "identity",
                "role",
                "affiliation",
                "name_or_alias",
                "role_identity",
                "organization_or_affiliation",
                "身份",
                "角色",
                "单位",
            ],
            "status": "active",
            "selectable": True,
        },
        {
            "group_id": "knowledge_background",
            "title": {"zh": "知识背景", "en": "Knowledge Background"},
            "source_fields": ["domain_background"],
            "match_terms": ["domain_background", "domain", "background", "knowledge", "领域", "背景", "知识"],
            "status": "active",
            "selectable": True,
        },
        {
            "group_id": "long_term_focus",
            "title": {"zh": "长期关注方向", "en": "Long-term Focus"},
            "source_fields": ["long_term_research_or_work_focus"],
            "match_terms": ["long_term_focus", "research_focus", "work_focus", "长期", "关注方向", "研究方向"],
            "status": "active",
            "selectable": True,
        },
    ],
    "preferences": [
        {
            "group_id": "language",
            "title": {"zh": "语言", "en": "Language"},
            "source_fields": ["language_preference", "terminology_preference"],
            "match_terms": ["language_preference", "terminology_preference", "language", "terms", "语言", "术语"],
            "status": "active",
            "selectable": True,
        },
        {
            "group_id": "expression_style",
            "title": {"zh": "表达风格", "en": "Expression Style"},
            "source_fields": [
                "style_preference",
                "formatting_constraints",
                "forbidden_expressions",
                "revision_preference",
                "response_granularity",
            ],
            "match_terms": [
                "style_preference",
                "formatting_constraints",
                "forbidden_expressions",
                "revision_preference",
                "response_granularity",
                "style",
                "format",
                "tone",
                "granularity",
                "表达",
                "风格",
                "格式",
                "语气",
                "粒度",
            ],
            "status": "active",
            "selectable": True,
        },
        {
            "group_id": "main_task_types",
            "title": {"zh": "主要任务类型", "en": "Main Task Types"},
            "source_fields": ["primary_task_types"],
            "match_terms": ["primary_task_types", "task_types", "main_tasks", "任务类型", "常用任务"],
            "status": "active",
            "selectable": True,
        },
    ],
}


def base_display_taxonomy(category: str | None = None) -> dict[str, list[dict[str, Any]]] | list[dict[str, Any]]:
    if category is None:
        return deepcopy(BASE_DISPLAY_TAXONOMY)
    return deepcopy(BASE_DISPLAY_TAXONOMY.get(category, []))


def taxonomy_group_source_fields(category: str, group_id: str) -> list[str]:
    for group in BASE_DISPLAY_TAXONOMY.get(category, []):
        if group.get("group_id") == group_id:
            return [str(field) for field in group.get("source_fields", []) if str(field).strip()]
    return []
