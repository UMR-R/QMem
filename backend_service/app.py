from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field


def _configure_text_io() -> None:
    """Prefer UTF-8 process output on Windows consoles."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_text_io()


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATE_DIR = ROOT / ".state"
SETTINGS_PATH = STATE_DIR / "settings.json"
UPLOADS_DIR = STATE_DIR / "uploads"
EXPORTS_DIR = STATE_DIR / "exports"
DEFAULT_WIKI_ROOT = ROOT / "wiki"
CATALOG_DIR = ROOT / "catalog"
LEGACY_RECOMMENDED_SKILLS_PATH = CATALOG_DIR / "recommended_skills.json"
RECOMMENDED_SKILLS_DIR = CATALOG_DIR / "recommended_skills"
RECOMMENDED_SKILLS_INDEX_PATH = RECOMMENDED_SKILLS_DIR / "index.json"
RECOMMENDED_SKILLS_META_PATH = CATALOG_DIR / "recommended_skills_meta.json"
RECOMMENDED_REFRESH_INTERVAL_HOURS = 24
RECOMMENDED_REMOTE_SOURCES = [
    {
        "id": "anthropic_skills",
        "label": "Anthropic Skills",
        "url": "https://api.github.com/repos/anthropics/skills/contents/skills",
        "format": "github_skill_repo",
        "raw_base": "https://raw.githubusercontent.com/anthropics/skills/main/skills",
        "usage_bias": 0.96,
    },
]
MEMORY_TRANSFEROR_SRC = PROJECT_ROOT / "memory_transferor" / "src"
JOB_LOCK = threading.Lock()
L2_PERSISTENT_NODE_MAINTENANCE_VERSION = "l2_persistent_nodes_v8_node_delete_locks"
PERSISTENT_REBUILD_VERSION = "persistent_rebuild_v2_semantic_candidates"
EPISODE_SCHEMA_VERSION = "turn_v2_incremental"
ORGANIZE_EPISODE_MAX_WORKERS = 4
ORGANIZE_EPISODE_TURN_BATCH_SIZE = 4
PERSISTENT_NODE_BATCH_SIZE = 8

if str(MEMORY_TRANSFEROR_SRC) not in sys.path:
    sys.path.insert(0, str(MEMORY_TRANSFEROR_SRC))

from memory_transferor.managed_memory import L2Wiki, MemoryBuilder, MemoryUpdater  # noqa: E402
from memory_transferor.managed_memory.models import EpisodeConnection, EpisodicMemory, MemoryBase, PreferenceMemory, ProfileMemory, ProjectMemory, WorkflowMemory  # noqa: E402
from memory_transferor.memory_models import RawConversation, RawMessage  # noqa: E402
from memory_transferor.memory_export import BootstrapGenerator, PackageExporter, base_display_taxonomy, taxonomy_group_source_fields  # noqa: E402
from memory_transferor.memory_policy import L3Schema  # noqa: E402
from memory_transferor.memory_policy.semantic_retrieval import (  # noqa: E402
    DAILY_NOTE_SEMANTIC_ANCHORS as _DAILY_NOTE_SEMANTIC_ANCHORS,
    PROJECT_SEMANTIC_ANCHORS as _PROJECT_ONLY_SEMANTIC_ANCHORS,
    best_semantic_similarity as _best_semantic_similarity,
    semantic_similarity as _semantic_similarity,
)
from memory_transferor.memory_store import L0RawLayer  # noqa: E402
from memory_transferor.platform_memory import L1SignalLayer  # noqa: E402
from memory_transferor.prompt_loader import load_prompt  # noqa: E402
from memory_transferor.runtime import LLMClient  # noqa: E402


JOB_REGISTRY: dict[str, dict[str, Any]] = {}

DEFAULT_SETTINGS = {
    "api_provider": "openai_compat",
    "api_key": "",
    "api_base_url": "https://api.deepseek.com/v1",
    "api_model": "deepseek-chat",
    "storage_path": "",
    "keep_updated": False,
    "realtime_update": False,
    "detailed_injection": False,
    "last_sync_at": None,
    "backend_url": "",
    "saved_skill_ids": [],
    "dismissed_skill_ids": [],
}

FIELD_LABELS = {
    "profile": {
        "zh": {
            "name_or_alias": "个人背景",
            "role_identity": "个人背景",
            "domain_background": "领域背景",
            "organization_or_affiliation": "个人背景",
            "common_languages": "语言背景",
            "primary_task_types": "主要任务类型",
            "long_term_research_or_work_focus": "长期关注方向",
        },
        "en": {
            "name_or_alias": "Personal Background",
            "role_identity": "Personal Background",
            "domain_background": "Domain Background",
            "organization_or_affiliation": "Personal Background",
            "common_languages": "Language Background",
            "primary_task_types": "Primary Task Types",
            "long_term_research_or_work_focus": "Long-term Focus",
        },
    },
    "preferences": {
        "zh": {
            "style_preference": "回答风格偏好",
            "terminology_preference": "回答风格偏好",
            "formatting_constraints": "回答风格偏好",
            "forbidden_expressions": "回答风格偏好",
            "language_preference": "回答语言偏好",
            "primary_task_types": "主要任务类型",
            "revision_preference": "回答风格偏好",
            "response_granularity": "回答风格偏好",
        },
        "en": {
            "style_preference": "Response Style Preference",
            "terminology_preference": "Response Style Preference",
            "formatting_constraints": "Response Style Preference",
            "forbidden_expressions": "Response Style Preference",
            "language_preference": "Response Language Preference",
            "primary_task_types": "Primary Task Types",
            "revision_preference": "Response Style Preference",
            "response_granularity": "Response Style Preference",
        },
    },
}

CATEGORY_LABELS = {
    "zh": {
        "profile": "用户画像",
        "preferences": "偏好设置",
        "projects": "项目记忆",
        "workflows": "工作流 / SOP",
        "daily_notes": "日常记忆",
    },
    "en": {
        "profile": "Profile",
        "preferences": "Preferences",
        "projects": "Projects",
        "workflows": "Workflows / SOP",
        "daily_notes": "Daily Notes",
    },
}

DEFAULT_RECOMMENDED_SKILLS = [
    {
        "id": "rec:linux_terminal",
        "icon": ">_",
        "title": "Linux Terminal",
        "description": "触发：需要在终端语境里完成命令排查、脚本调试或系统操作时 | 目标：把问题转成可执行的命令路径并逐步验证 | 产出：可复制执行的终端命令与检查清单",
        "tags": ["coding", "terminal", "engineering"],
        "keywords": ["linux", "terminal", "shell", "command", "bash"],
        "persona_signals": ["code", "engineering", "debug", "terminal"],
        "usage_score": 0.97,
        "source": "built_in",
        "trigger": "需要在终端里排查命令、脚本或环境问题时",
        "goal": "把问题拆成可执行的命令步骤并逐步验证",
        "steps": ["确认当前环境与上下文", "给出最小可执行命令", "解释输出并继续下一步排查"],
        "output_format": "命令清单 / 终端操作步骤",
        "selected": False,
    },
    {
        "id": "rec:english_rewriter",
        "icon": "EN",
        "title": "English Rewriter",
        "description": "触发：需要把中文或生硬英文改写成自然、专业、可发送的英文时 | 目标：保留原意并提升表达质量 | 产出：可直接发送的英文版本",
        "tags": ["writing", "translation", "language"],
        "keywords": ["english", "rewrite", "translate", "polish", "email"],
        "persona_signals": ["writing", "translation", "language"],
        "usage_score": 0.95,
        "source": "built_in",
        "trigger": "需要把中文或普通英文改写成更自然的英文时",
        "goal": "保留原意并输出更地道、专业的英文",
        "steps": ["识别原文语气和用途", "改写为自然流畅的英文", "补充简短解释或备选版本"],
        "output_format": "英文改写稿 / 邮件文本",
        "selected": False,
    },
    {
        "id": "rec:prompt_generator",
        "icon": "生",
        "title": "Prompt Generator",
        "description": "触发：只有一个任务标题，但需要更完整的提示词时 | 目标：生成结构化、可复用的系统提示词 | 产出：带角色、步骤、约束的完整 prompt",
        "tags": ["writing", "prompt", "meta"],
        "keywords": ["prompt", "generator", "template", "instruction", "system"],
        "persona_signals": ["prompt", "workflow", "writing"],
        "usage_score": 0.93,
        "source": "built_in",
        "trigger": "只有一个任务方向，需要扩展成完整 prompt 时",
        "goal": "生成结构化、可复用的系统提示词或工作提示词",
        "steps": ["识别任务目标和输入输出", "补齐角色、步骤和约束", "输出可直接复制的 prompt"],
        "output_format": "系统提示词 / 工作提示词",
        "selected": False,
    },
    {
        "id": "rec:paper_summary",
        "icon": "研",
        "title": "读文献总结",
        "description": "触发：需要快速读懂论文并输出结构化摘要时 | 目标：提炼问题、方法、结果和局限 | 产出：结构化文献摘要",
        "tags": ["research", "paper", "summary"],
        "keywords": ["paper", "review", "literature", "summary", "research"],
        "persona_signals": ["paper", "research", "reading", "summary"],
        "usage_score": 0.92,
        "source": "built_in",
        "trigger": "需要快速理解论文内容并沉淀关键信息时",
        "goal": "提炼研究问题、方法、结果和局限",
        "steps": ["定位论文核心问题", "提取方法与实验设计", "总结结果、贡献与局限"],
        "output_format": "结构化文献摘要",
        "selected": False,
    },
    {
        "id": "rec:project_plan",
        "icon": "计",
        "title": "项目规划",
        "description": "触发：需要把模糊目标拆成可推进的项目计划时 | 目标：明确范围、优先级和里程碑 | 产出：任务拆解与行动计划",
        "tags": ["planning", "project", "roadmap"],
        "keywords": ["project", "plan", "roadmap", "tasks", "priority"],
        "persona_signals": ["project", "planning", "workflow", "roadmap"],
        "usage_score": 0.9,
        "source": "built_in",
        "trigger": "目标还比较模糊，需要转成明确项目计划时",
        "goal": "输出可执行的任务拆解、优先级与里程碑",
        "steps": ["梳理目标与边界", "拆解任务并排序优先级", "输出阶段计划与下一步"],
        "output_format": "行动计划 / Roadmap",
        "selected": False,
    },
    {
        "id": "rec:code_review",
        "icon": "码",
        "title": "Code Review",
        "description": "触发：需要评估代码改动质量与风险时 | 目标：发现行为风险、回归点和测试缺口 | 产出：结构化 review 结论",
        "tags": ["coding", "review", "engineering"],
        "keywords": ["code", "review", "bug", "test", "regression"],
        "persona_signals": ["code", "engineering", "debug", "review"],
        "usage_score": 0.88,
        "source": "built_in",
        "trigger": "需要对改动做质量审查或风险评估时",
        "goal": "梳理关键风险、行为变化和测试缺口",
        "steps": ["识别改动范围", "检查潜在回归与边界条件", "输出结论和补测建议"],
        "output_format": "Review 结论 / 风险清单",
        "selected": False,
    },
    {
        "id": "rec:bug_triage",
        "icon": "查",
        "title": "Bug 排查",
        "description": "触发：出现 bug 或异常行为需要排查时 | 目标：围绕复现、定位、验证给出排查路径 | 产出：排查步骤与修复建议",
        "tags": ["coding", "debug", "engineering"],
        "keywords": ["bug", "debug", "trace", "repro", "fix"],
        "persona_signals": ["code", "engineering", "debug"],
        "usage_score": 0.86,
        "source": "built_in",
        "trigger": "出现 bug、错误日志或异常行为时",
        "goal": "建立清晰的复现、定位和验证路径",
        "steps": ["先复现问题并收集上下文", "定位最可疑的模块或输入", "给出修复方向与验证方案"],
        "output_format": "排查清单 / 修复建议",
        "selected": False,
    },
    {
        "id": "rec:prd_writer",
        "icon": "策",
        "title": "PRD 草拟",
        "description": "触发：需要把功能想法整理成正式产品文档时 | 目标：梳理用户、场景、范围和验收标准 | 产出：PRD 初稿",
        "tags": ["product", "planning", "writing"],
        "keywords": ["prd", "product", "spec", "requirements", "feature"],
        "persona_signals": ["product", "planning", "requirements"],
        "usage_score": 0.84,
        "source": "built_in",
        "trigger": "需要把需求想法整理成正式产品文档时",
        "goal": "输出包含用户、场景、范围和验收标准的 PRD",
        "steps": ["确认目标用户与场景", "整理功能范围和边界", "输出 PRD 结构与验收标准"],
        "output_format": "PRD 初稿",
        "selected": False,
    },
    {
        "id": "rec:pdf_reader",
        "icon": "PDF",
        "title": "读 PDF",
        "description": "触发：需要快速读懂 PDF 文档时 | 目标：提取结构、重点结论与待跟进问题 | 产出：文档摘要与要点清单",
        "tags": ["research", "document", "pdf"],
        "keywords": ["pdf", "paper", "document", "reading", "summary"],
        "persona_signals": ["paper", "research", "reading", "summary"],
        "usage_score": 0.83,
        "source": "built_in",
        "trigger": "需要快速理解 PDF 文档内容时",
        "goal": "提取结构、结论和需要关注的细节",
        "steps": ["先识别文档结构", "提炼关键结论和数据点", "列出待跟进问题或引用片段"],
        "output_format": "摘要 / 要点清单",
        "selected": False,
    },
]


class SettingsResponse(BaseModel):
    api_provider: str
    api_key_configured: bool
    api_base_url: str
    api_model: str
    storage_path: str
    keep_updated: bool
    realtime_update: bool
    detailed_injection: bool
    last_sync_at: str | None
    backend_url: str


class SettingsUpdate(BaseModel):
    api_provider: str = "openai_compat"
    api_key: str = ""
    api_base_url: str = "https://api.deepseek.com/v1"
    api_model: str = "deepseek-chat"
    storage_path: str = ""
    keep_updated: bool = False
    realtime_update: bool = False
    detailed_injection: bool = False
    backend_url: str = ""


class ConnectionTestRequest(BaseModel):
    api_provider: str = "openai_compat"
    api_key: str = ""
    api_base_url: str = "https://api.deepseek.com/v1"
    api_model: str = "deepseek-chat"


class SyncToggleRequest(BaseModel):
    enabled: bool


class ConversationAppendRequest(BaseModel):
    platform: str
    chat_id: str
    url: str
    timestamp: str
    user_text: str
    assistant_text: str


class ConversationMessageInput(BaseModel):
    role: str
    text: str


class CurrentConversationImportRequest(BaseModel):
    platform: str
    chat_id: str
    url: str
    title: str = ""
    messages: list[ConversationMessageInput]
    process_now: bool = True


class PlatformMemoryImportRequest(BaseModel):
    platform: str
    url: str
    title: str = ""
    heading: str = ""
    agentName: str = ""
    chatId: str = ""
    memoryHints: list[str] = Field(default_factory=list)
    pageTextExcerpt: str = ""
    capturedAt: str = ""
    pageType: str = ""
    recordTypes: list[str] = Field(default_factory=list)
    savedMemoryItems: list[str] = Field(default_factory=list)
    customInstructions: list[dict[str, Any] | str] = Field(default_factory=list)
    agentConfig: dict[str, Any] = Field(default_factory=dict)
    platformSkills: list[dict[str, Any]] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    last_sync_at: str | None
    conversation_count: int
    memory_item_count: int
    sync_enabled: bool
    breakdown: dict[str, int]


class SelectedIdsRequest(BaseModel):
    selected_ids: list[str] = []


class ExportPackageRequest(SelectedIdsRequest):
    target_format: str = "generic"
    include_episodic_evidence: bool = True


class InjectPackageRequest(SelectedIdsRequest):
    target_platform: str = "chatgpt"
    detailed_injection: bool = False


class SaveSkillsRequest(BaseModel):
    skill_ids: list[str]
    merge: bool = True


class ExportSkillsRequest(BaseModel):
    skill_ids: list[str]


class DeleteSkillsRequest(BaseModel):
    skill_ids: list[str]


class DeleteMemoryItemsRequest(BaseModel):
    item_ids: list[str]


class InjectSkillsRequest(BaseModel):
    skill_ids: list[str]
    target_platform: str = "chatgpt"


class RefreshRecommendedSkillsRequest(BaseModel):
    force: bool = False


class CacheClearRequest(BaseModel):
    scope: str = "temporary"


class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, Any]:
    ensure_state_dir()
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(
            json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dict(DEFAULT_SETTINGS)

    try:
        loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        loaded = {}

    merged = dict(DEFAULT_SETTINGS)
    merged.update(loaded)
    return _normalize_api_config(merged)


def ensure_catalog_dir() -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)


def _build_skill_markdown_lines(skill: dict[str, Any]) -> list[str]:
    md_lines = [f"# {skill.get('title', 'Skill')}\n"]
    kind = skill.get("kind", "skill")
    md_lines.append(f"**Type:** {kind}")
    if skill.get("trigger"):
        md_lines.append(f"**Trigger:** {skill['trigger']}")
    if skill.get("goal"):
        md_lines.append(f"**Goal:** {skill['goal']}")
    if skill.get("output_format"):
        md_lines.append(f"**Output:** {skill['output_format']}")
    if skill.get("steps"):
        md_lines.append("\n**Steps:**")
        md_lines.extend(f"- {step}" for step in skill["steps"] if step)
    if skill.get("guardrails"):
        md_lines.append("\n**Guardrails:**")
        md_lines.extend(f"- {item}" for item in skill["guardrails"] if item)
    if skill.get("composition", {}).get("uses_skills"):
        md_lines.append("\n**Uses Skills:**")
        md_lines.extend(f"- {item}" for item in skill["composition"]["uses_skills"])
    if skill.get("composition", {}).get("prompt_template"):
        md_lines.append(f"\n**Prompt Template:** {skill['composition']['prompt_template']}")
    if skill.get("source_types"):
        md_lines.append(f"\n**Source Types:** {', '.join(skill['source_types'])}")
    if skill.get("confidence"):
        md_lines.append(f"**Confidence:** {skill['confidence']}")
    return md_lines


def _build_skill_forms_lines(skill: dict[str, Any]) -> list[str]:
    forms_lines = ["# Forms\n"]
    if skill.get("trigger"):
        forms_lines.append(f"## Trigger\n{skill['trigger']}\n")
    if skill.get("output_format"):
        forms_lines.append(f"## Output Format\n{skill['output_format']}\n")
    if skill.get("steps"):
        forms_lines.append("## Standard Steps")
        forms_lines.extend(f"{idx + 1}. {step}" for idx, step in enumerate(skill["steps"]) if step)
    if skill.get("guardrails"):
        forms_lines.append("\n## Guardrails")
        forms_lines.extend(f"- {item}" for item in skill["guardrails"] if item)
    return forms_lines


def _build_skill_reference_lines(skill: dict[str, Any]) -> list[str]:
    ref_lines = ["# Reference\n"]
    if skill.get("description"):
        ref_lines.append(f"## Summary\n{skill['description']}\n")
    if skill.get("source_types"):
        ref_lines.append("## Sources")
        ref_lines.extend(f"- {item}" for item in skill["source_types"] if item)
    if skill.get("evidence_episode_ids"):
        ref_lines.append("\n## Evidence Episodes")
        ref_lines.extend(f"- {item}" for item in skill["evidence_episode_ids"] if item)
    if skill.get("composition"):
        ref_lines.append("\n## Composition")
        for key, value in skill["composition"].items():
            if value:
                ref_lines.append(f"- {key}: {value}")
    return ref_lines


def save_recommended_skill_asset_library(items: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    ensure_catalog_dir()
    RECOMMENDED_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for child in RECOMMENDED_SKILLS_DIR.iterdir():
        if child.name == "index.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    index_items: list[dict[str, Any]] = []
    for item in items:
        slug = _safe_slug(str(item.get("id") or item.get("title") or "skill"))
        asset_dir = RECOMMENDED_SKILLS_DIR / slug
        asset_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = asset_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        normalized = _normalize_skill_record(item)
        canonical_skill = {
            "id": normalized.get("id"),
            "title": normalized.get("title"),
            "description": normalized.get("description"),
            "kind": normalized.get("kind") if normalized.get("kind") in {"skill", "workflow"} else "skill",
            "trigger": normalized.get("trigger", ""),
            "goal": normalized.get("goal", ""),
            "steps": normalized.get("steps", []),
            "output_format": normalized.get("output_format", ""),
            "guardrails": normalized.get("guardrails", []),
            "source_types": normalized.get("source_types") or ["recommended_catalog"],
            "confidence": normalized.get("confidence", "medium"),
            "selected": bool(normalized.get("selected", False)),
        }
        recommendation_meta = {
            "id": normalized.get("id"),
            "icon": normalized.get("icon"),
            "tags": normalized.get("tags", []),
            "keywords": normalized.get("keywords", []),
            "persona_signals": normalized.get("persona_signals", []),
            "usage_score": normalized.get("usage_score", 0.5),
            "source": normalized.get("source", "built_in"),
        }
        (asset_dir / "skill.json").write_text(
            json.dumps(canonical_skill, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (asset_dir / "recommendation.json").write_text(
            json.dumps(recommendation_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        skill_md = str(normalized.get("skill_md_content") or "").strip()
        if not skill_md:
            skill_md = "\n".join(_build_skill_markdown_lines(canonical_skill)).strip()
        (asset_dir / "SKILL.md").write_text(skill_md.rstrip() + "\n", encoding="utf-8")

        forms_md = str(normalized.get("forms_md_content") or "").strip()
        if not forms_md:
            forms_md = "\n".join(_build_skill_forms_lines(canonical_skill)).strip()
        (asset_dir / "forms.md").write_text(forms_md.rstrip() + "\n", encoding="utf-8")

        reference_md = str(normalized.get("reference_md_content") or "").strip()
        if not reference_md:
            reference_md = "\n".join(_build_skill_reference_lines(canonical_skill)).strip()
        (asset_dir / "reference.md").write_text(reference_md.rstrip() + "\n", encoding="utf-8")

        scripts_readme = str(normalized.get("scripts_readme") or "").strip()
        if not scripts_readme:
            scripts_readme = "# Scripts\n\nPlace executable helpers for this recommended skill here.\n"
        (scripts_dir / "README.md").write_text(scripts_readme.rstrip() + "\n", encoding="utf-8")

        index_items.append(
            {
                "id": normalized.get("id"),
                "title": normalized.get("title"),
                "kind": canonical_skill.get("kind", "skill"),
                "folder": slug,
                "json": f"{slug}/skill.json",
                "recommendation_json": f"{slug}/recommendation.json",
                "skill_md": f"{slug}/SKILL.md",
                "forms_md": f"{slug}/forms.md",
                "reference_md": f"{slug}/reference.md",
            }
        )

    RECOMMENDED_SKILLS_INDEX_PATH.write_text(
        json.dumps(
            {
                "folder": "recommended_skills",
                "updated_at": meta.get("last_updated_at") or datetime.now(timezone.utc).isoformat(),
                "items": index_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    RECOMMENDED_SKILLS_META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if LEGACY_RECOMMENDED_SKILLS_PATH.exists():
        LEGACY_RECOMMENDED_SKILLS_PATH.unlink()


def ensure_recommended_skill_catalog() -> None:
    ensure_catalog_dir()
    meta = {
        "version": "1.1",
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "last_refresh_status": "seeded",
        "sources": ["built_in"],
        "item_count": len(DEFAULT_RECOMMENDED_SKILLS),
        "last_error": None,
    }
    if RECOMMENDED_SKILLS_INDEX_PATH.exists() and RECOMMENDED_SKILLS_META_PATH.exists():
        return

    if LEGACY_RECOMMENDED_SKILLS_PATH.exists():
        try:
            legacy_items = json.loads(LEGACY_RECOMMENDED_SKILLS_PATH.read_text(encoding="utf-8"))
            if not isinstance(legacy_items, list):
                legacy_items = list(DEFAULT_RECOMMENDED_SKILLS)
        except json.JSONDecodeError:
            legacy_items = list(DEFAULT_RECOMMENDED_SKILLS)
        if RECOMMENDED_SKILLS_META_PATH.exists():
            try:
                loaded_meta = json.loads(RECOMMENDED_SKILLS_META_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded_meta, dict):
                    meta.update(loaded_meta)
            except json.JSONDecodeError:
                pass
        save_recommended_skill_asset_library(legacy_items, meta)
        return

    save_recommended_skill_asset_library(list(DEFAULT_RECOMMENDED_SKILLS), meta)


def load_recommended_skill_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ensure_recommended_skill_catalog()
    items: list[dict[str, Any]] = []
    try:
        index_payload = json.loads(RECOMMENDED_SKILLS_INDEX_PATH.read_text(encoding="utf-8"))
        index_items = index_payload.get("items", []) if isinstance(index_payload, dict) else []
        for entry in index_items:
            if not isinstance(entry, dict):
                continue
            relative_json = str(entry.get("json") or "").strip()
            if not relative_json:
                continue
            json_path = RECOMMENDED_SKILLS_DIR / relative_json
            if not json_path.exists():
                continue
            record = read_json_file(json_path)
            if isinstance(record, dict):
                recommendation_path = RECOMMENDED_SKILLS_DIR / str(entry.get("recommendation_json") or "")
                recommendation = read_json_file(recommendation_path) if recommendation_path.exists() else {}
                if isinstance(recommendation, dict):
                    record = {**record, **recommendation}

                skill_md_path = RECOMMENDED_SKILLS_DIR / str(entry.get("skill_md") or "")
                forms_md_path = RECOMMENDED_SKILLS_DIR / str(entry.get("forms_md") or "")
                reference_md_path = RECOMMENDED_SKILLS_DIR / str(entry.get("reference_md") or "")
                scripts_readme_path = skill_md_path.parent / "scripts" / "README.md"

                if skill_md_path.exists():
                    record["skill_md_content"] = skill_md_path.read_text(encoding="utf-8")
                    record["skill_md_path"] = str(skill_md_path.relative_to(RECOMMENDED_SKILLS_DIR))
                if forms_md_path.exists():
                    record["forms_md_content"] = forms_md_path.read_text(encoding="utf-8")
                    record["forms_md_path"] = str(forms_md_path.relative_to(RECOMMENDED_SKILLS_DIR))
                if reference_md_path.exists():
                    record["reference_md_content"] = reference_md_path.read_text(encoding="utf-8")
                    record["reference_md_path"] = str(reference_md_path.relative_to(RECOMMENDED_SKILLS_DIR))
                if scripts_readme_path.exists():
                    record["scripts_readme"] = scripts_readme_path.read_text(encoding="utf-8")
                    record["scripts_readme_path"] = str(scripts_readme_path.relative_to(RECOMMENDED_SKILLS_DIR))
                items.append(record)
    except json.JSONDecodeError:
        items = []
    if not items:
        items = list(DEFAULT_RECOMMENDED_SKILLS)

    try:
        meta = json.loads(RECOMMENDED_SKILLS_META_PATH.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            meta = {}
    except json.JSONDecodeError:
        meta = {}

    normalized_meta = {
        "version": meta.get("version", "1.0"),
        "last_updated_at": meta.get("last_updated_at"),
        "last_refresh_status": meta.get("last_refresh_status", "unknown"),
        "sources": meta.get("sources", ["built_in"]),
        "item_count": meta.get("item_count"),
        "last_error": meta.get("last_error"),
    }
    return items, normalized_meta

def save_recommended_skill_catalog(items: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    save_recommended_skill_asset_library(items, meta)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _needs_recommended_refresh(meta: dict[str, Any], force: bool = False) -> bool:
    if force:
        return True
    status = str(meta.get("last_refresh_status") or "").strip().lower()
    sources = {
        str(item).strip().lower()
        for item in meta.get("sources", [])
        if str(item).strip()
    }
    if status in {"seeded", "unknown", "failed"}:
        return True
    if not sources or sources == {"built_in"}:
        return True
    last_updated = _parse_iso_datetime(meta.get("last_updated_at"))
    if last_updated is None:
        return True
    return (datetime.now(timezone.utc) - last_updated).total_seconds() >= RECOMMENDED_REFRESH_INTERVAL_HOURS * 3600


def _fetch_remote_text(url: str, timeout: float = 12.0) -> str:
    parsed = urllib.parse.urlparse(url)
    accept = "text/plain, text/csv, text/markdown; charset=utf-8"
    if parsed.netloc == "api.github.com":
        accept = "application/vnd.github+json"
    elif parsed.netloc == "raw.githubusercontent.com":
        accept = "text/plain, text/markdown, application/octet-stream; charset=utf-8"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MemAssist/0.2 (+https://127.0.0.1)",
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def _extract_keywords(*values: str) -> list[str]:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
        "chatgpt", "prompt", "assistant", "help", "using", "user", "users",
        "skill", "skills", "chat", "tool", "please",
    }
    seen: set[str] = set()
    keywords: list[str] = []
    for value in values:
        text = str(value or "").lower().replace("/", " ").replace("_", " ")
        for token in re.findall(r"[a-z][a-z0-9+\-]{2,}", text):
            if token in stopwords or token in seen:
                continue
            seen.add(token)
            keywords.append(token)
    return keywords[:12]


def _infer_skill_tags(*values: str) -> list[str]:
    text = " ".join(str(value or "").lower() for value in values)
    tag_rules = {
        "research": ["paper", "research", "literature", "citation", "pdf"],
        "coding": ["code", "debug", "bug", "review", "python", "github"],
        "planning": ["plan", "roadmap", "project", "task", "prd", "spec"],
        "writing": ["write", "writing", "summary", "copy", "blog", "email"],
        "product": ["product", "requirements", "feature", "user story"],
        "analysis": ["analysis", "data", "excel", "report", "table"],
    }
    tags = [tag for tag, markers in tag_rules.items() if any(marker in text for marker in markers)]
    return tags or ["general"]


def _build_remote_skill_record(
    *,
    source_id: str,
    title: str,
    prompt_text: str,
    usage_bias: float,
) -> dict[str, Any] | None:
    clean_title = re.sub(r"\s+", " ", str(title or "").strip())
    if not clean_title or len(clean_title) < 3:
        return None
    clean_title = re.sub(r"^(act as|you are|i want you to act as)\s+", "", clean_title, flags=re.I).strip()
    summary = re.sub(r"\s+", " ", str(prompt_text or "").strip())
    if not summary:
        return None
    description = summary[:120].rsplit(" ", 1)[0] if len(summary) > 120 else summary
    if len(description) < 24:
        description = summary[:160]
    keywords = _extract_keywords(clean_title, description, prompt_text[:300])
    tags = _infer_skill_tags(clean_title, description)
    persona_signals = keywords[:6]
    trigger = f"需要处理与{clean_title}相关的任务时"
    goal = description[:60] if description else f"完成与{clean_title}相关的任务"
    if "research" in tags:
        steps = ["识别核心问题或文档结构", "提取关键结论与证据", "输出结构化摘要"]
        output_format = "结构化摘要 / 要点清单"
    elif "coding" in tags:
        steps = ["确认问题场景和上下文", "给出逐步排查或执行步骤", "输出验证方式与下一步建议"]
        output_format = "操作步骤 / 调试建议"
    elif "planning" in tags or "product" in tags:
        steps = ["澄清目标和边界", "拆解关键步骤与优先级", "输出可执行计划或模板"]
        output_format = "计划草案 / 模板"
    else:
        steps = ["澄清任务目标", "整理执行步骤", "输出结构化结果"]
        output_format = "结构化结果"
    return {
        "id": f"rec:{source_id}:{_safe_slug(clean_title, 'skill')}",
        "icon": clean_title[:1].upper(),
        "title": clean_title,
        "description": description,
        "trigger": trigger,
        "goal": goal,
        "steps": steps,
        "output_format": output_format,
        "tags": tags,
        "keywords": keywords,
        "persona_signals": persona_signals,
        "usage_score": usage_bias,
        "source": source_id,
        "selected": False,
    }


def _strip_markdown_frontmatter(text: str) -> str:
    raw = str(text or "")
    if not raw.startswith("---\n"):
        return raw
    closing = raw.find("\n---\n", 4)
    if closing == -1:
        return raw
    return raw[closing + 5:]


def _parse_simple_frontmatter(text: str) -> dict[str, str]:
    raw = str(text or "")
    if not raw.startswith("---\n"):
        return {}
    closing = raw.find("\n---\n", 4)
    if closing == -1:
        return {}
    block = raw[4:closing]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _normalize_title_case_words(value: str) -> str:
    words = []
    for word in re.split(r"\s+", str(value or "").strip()):
        lower = word.lower()
        if lower in {"api", "mcp", "pdf", "ppt", "pptx", "docx", "csv", "json", "xml", "sql"}:
            words.append(lower.upper())
        else:
            words.append(word.capitalize())
    return " ".join(word for word in words if word)


def _humanize_remote_skill_title(title: str, folder_name: str, description: str) -> str:
    raw = str(title or "").strip() or folder_name.replace("-", " ").replace("_", " ").strip()
    normalized = _normalize_title_case_words(raw)
    lowered = normalized.lower()
    description_l = str(description or "").lower()

    if lowered in {"pdf", "pdf processing", "pdf skill"} or (lowered == "pdf" and "pdf" in description_l):
        return "PDF 文档处理"
    if lowered in {"pdf processing guide"}:
        return "PDF 文档处理"
    if lowered in {"docx", "word", "word document"} or ".docx" in description_l:
        return "Word 文档处理"
    if lowered in {"pptx", "powerpoint", "slides"} or ".pptx" in description_l:
        return "PPT 演示文稿处理"
    if lowered in {"pptx skill"}:
        return "PPT 演示文稿处理"
    if lowered in {"mcp builder", "mcp", "mcp server development guide"}:
        return "MCP 服务开发"
    if lowered in {"claude api", "api"} and "api" in description_l:
        return "Claude API 集成"
    if lowered in {"building llm powered applications with claude", "building llm-powered applications with claude"}:
        return "Claude 应用开发"
    if lowered in {"anthropic brand styling"}:
        return "品牌风格套用"
    if lowered in {"internal comms", "internal comms"}:
        return "内部沟通写作"
    if lowered in {"frontend design", "frontend-design"}:
        return "前端界面设计"
    if lowered in {"canvas design", "canvas-design"}:
        return "画布与视觉设计"
    if lowered in {"doc coauthoring", "doc co-authoring workflow"}:
        return "文档协作写作"
    if lowered in {"algorithmic art", "algorithmic-art"}:
        return "算法艺术创作"
    if lowered in {"requirements for outputs"}:
        return "输出要求整理"
    if lowered in {"skill creator"}:
        return "技能设计"
    if lowered in {"theme factory skill"}:
        return "主题风格生成"
    if lowered in {"slack gif creator"}:
        return "Slack GIF 生成"
    if lowered in {"web application testing"}:
        return "Web 应用测试"
    if lowered in {"web artifacts builder"}:
        return "Web 组件构建"
    if len(normalized) <= 4 and normalized.isupper():
        return f"{normalized} 能力"
    generic_title_mappings = [
        (("test", "testing", "qa", "debug"), "应用测试"),
        (("build", "builder", "scaffold", "prototype"), "应用构建"),
        (("write", "writer", "rewriter", "rewrite", "copy"), "写作改写"),
        (("document", "doc", "docx"), "文档处理"),
        (("design", "ui", "ux", "frontend", "canvas"), "界面设计"),
        (("brand", "style", "theme"), "风格设计"),
        (("api", "integration", "sdk"), "API 集成"),
        (("mcp", "server"), "MCP 服务开发"),
        (("skill", "workflow"), "技能设计"),
        (("requirements", "output"), "输出要求整理"),
    ]
    for keywords, mapped in generic_title_mappings:
        if any(keyword in lowered for keyword in keywords) or any(keyword in description_l for keyword in keywords):
            return mapped
    return "通用任务辅助"


def _extract_natural_paragraph(text: str) -> str:
    stripped = _strip_markdown_frontmatter(text)
    lines = stripped.splitlines()
    paragraphs: list[str] = []
    current: list[str] = []
    in_code = False
    for line in lines:
        raw = line.rstrip()
        clean = raw.strip()
        if clean.startswith("```"):
            in_code = not in_code
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if in_code:
            continue
        if not clean:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if clean.startswith("#") or clean.startswith("|"):
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if re.match(r"^[-*]\s+", clean):
            continue
        current.append(clean)
    if current:
        paragraphs.append(" ".join(current).strip())
    for paragraph in paragraphs:
        if len(paragraph) >= 32 and "name:" not in paragraph.lower() and "description:" not in paragraph.lower():
            return paragraph[:320]
    return paragraphs[0][:320] if paragraphs else ""


def _parse_csv_prompt_source(raw_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(raw_text))
    for row in reader:
        if not isinstance(row, dict):
            continue
        title = row.get("act") or row.get("title") or row.get("name") or ""
        prompt_text = row.get("prompt") or row.get("content") or row.get("description") or ""
        item = _build_remote_skill_record(
            source_id=source["id"],
            title=title,
            prompt_text=prompt_text,
            usage_bias=float(source.get("usage_bias", 0.8)),
        )
        if item:
            rows.append(item)
    return rows


def _extract_markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "body"
    for line in text.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+?)\s*$", line.strip())
        if heading:
            current = heading.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line.rstrip())
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _parse_markdown_skill_source(raw_text: str, source: dict[str, Any], folder_name: str) -> dict[str, Any] | None:
    frontmatter = _parse_simple_frontmatter(raw_text)
    stripped_text = _strip_markdown_frontmatter(raw_text)
    sections = _extract_markdown_sections(stripped_text)
    lines = [line.strip() for line in stripped_text.splitlines() if line.strip()]

    raw_title = frontmatter.get("title") or frontmatter.get("name") or folder_name.replace("-", " ").replace("_", " ").strip()
    if lines and lines[0].startswith("# "):
        raw_title = lines[0][2:].strip() or raw_title

    description = ""
    for key in ["summary", "overview", "purpose", "body"]:
        value = sections.get(key, "")
        natural = _extract_natural_paragraph(value)
        if natural:
            description = re.sub(r"\s+", " ", natural).strip()
            break
    if not description:
        description = _extract_natural_paragraph(stripped_text)
    if not description:
        description = str(frontmatter.get("description") or "").strip()

    title = _humanize_remote_skill_title(raw_title, folder_name, description)

    step_candidates: list[str] = []
    for key in sections:
        if "step" in key or "workflow" in key or "process" in key or "quick reference" in key:
            for line in sections[key].splitlines():
                cleaned = re.sub(r"^[-*0-9. )]+", "", line).strip()
                if not cleaned or cleaned.startswith("```") or cleaned.startswith("|"):
                    continue
                if "name:" in cleaned.lower() or "description:" in cleaned.lower():
                    continue
                step_candidates.append(cleaned)
    if len(step_candidates) < 2:
        bullet_lines = []
        in_code = False
        for line in stripped_text.splitlines():
            clean = line.strip()
            if clean.startswith("```"):
                in_code = not in_code
                continue
            if in_code or clean.startswith("|"):
                continue
            if re.match(r"^\s*[-*]\s+", line):
                bullet = re.sub(r"^\s*[-*]\s+", "", line).strip()
                if bullet and "name:" not in bullet.lower() and "description:" not in bullet.lower():
                    bullet_lines.append(bullet)
        step_candidates.extend(bullet_lines[:3])

    record = _build_remote_skill_record(
        source_id=source["id"],
        title=title,
        prompt_text=description or title,
        usage_bias=float(source.get("usage_bias", 0.9)),
    )
    if not record:
        return None

    record["source"] = f"{source['id']}:{folder_name}"
    if len(step_candidates) >= 2:
        record["steps"] = step_candidates[:4]
    record["trigger"] = record.get("trigger") or f"需要使用 {title} 相关能力时"
    record["goal"] = record.get("goal") or (description[:80] if description else title)
    record["description"] = (
        f"触发：{record['trigger']} | 目标：{record['goal']} | 步骤：{'；'.join(record.get('steps', [])[:3])} | 产出：{record.get('output_format', '结构化结果')}"
    )
    record["skill_md_content"] = stripped_text.strip()
    return record


def _parse_github_skill_repo_source(raw_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        entries = json.loads(raw_text)
    except json.JSONDecodeError:
        return []
    if not isinstance(entries, list):
        return []

    raw_base = str(source.get("raw_base") or "").rstrip("/")
    rows: list[dict[str, Any]] = []
    for entry in entries[:24]:
        if not isinstance(entry, dict) or entry.get("type") != "dir":
            continue
        folder_name = str(entry.get("name") or "").strip()
        if not folder_name:
            continue
        skill_md_url = f"{raw_base}/{urllib.parse.quote(folder_name)}/SKILL.md"
        try:
            md_text = _fetch_remote_text(skill_md_url, timeout=10.0)
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        item = _parse_markdown_skill_source(md_text, source, folder_name)
        if item:
            for filename, key in [("forms.md", "forms_md_content"), ("reference.md", "reference_md_content")]:
                file_url = f"{raw_base}/{urllib.parse.quote(folder_name)}/{filename}"
                try:
                    item[key] = _fetch_remote_text(file_url, timeout=8.0).strip()
                except (urllib.error.URLError, TimeoutError, ValueError):
                    continue
            item["scripts_readme"] = (
                "# Scripts\n\n"
                f"Recommended helper scripts for `{item.get('title', folder_name)}` can be placed here.\n"
            )
            rows.append(item)
    return rows


def _refresh_recommended_skill_catalog(force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items, meta = load_recommended_skill_catalog()
    if not _needs_recommended_refresh(meta, force):
        return items, meta

    fetched_items: list[dict[str, Any]] = []
    source_ids: list[str] = []
    errors: list[str] = []
    for source in RECOMMENDED_REMOTE_SOURCES:
        try:
            raw_text = _fetch_remote_text(source["url"])
            if source.get("format") == "csv_act_prompt":
                parsed = _parse_csv_prompt_source(raw_text, source)
            elif source.get("format") == "github_skill_repo":
                parsed = _parse_github_skill_repo_source(raw_text, source)
            else:
                parsed = []
            if parsed:
                fetched_items.extend(parsed)
                source_ids.append(source["id"])
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            errors.append(f"{source['id']}: {exc}")

    combined_items = [*fetched_items, *DEFAULT_RECOMMENDED_SKILLS] if fetched_items else [*DEFAULT_RECOMMENDED_SKILLS]
    remote_keywords: set[str] = set()
    for item in fetched_items:
        for token in [*(item.get("keywords") or []), *(item.get("tags") or []), *(item.get("persona_signals") or [])]:
            token_str = str(token).strip().lower()
            if token_str:
                remote_keywords.add(token_str)

    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in combined_items:
        title_key = str(item.get("title", "")).strip().lower()
        if not title_key or title_key in seen_titles:
            continue
        if fetched_items and str(item.get("source") or "") == "built_in":
            built_in_keywords = {
                str(token).strip().lower()
                for token in [*(item.get("keywords") or []), *(item.get("tags") or []), *(item.get("persona_signals") or [])]
                if str(token).strip()
            }
            if built_in_keywords and len(built_in_keywords & remote_keywords) >= 2:
                continue
        seen_titles.add(title_key)
        deduped.append(item)

    if fetched_items:
        new_meta = {
            "version": "1.1",
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
            "last_refresh_status": "success",
            "sources": source_ids or ["built_in"],
            "item_count": len(deduped),
            "last_error": None,
        }
        save_recommended_skill_catalog(deduped, new_meta)
        return deduped, new_meta

    fallback_meta = {
        "version": meta.get("version", "1.1"),
        "last_updated_at": meta.get("last_updated_at") or datetime.now(timezone.utc).isoformat(),
        "last_refresh_status": "failed" if errors else meta.get("last_refresh_status", "unknown"),
        "sources": meta.get("sources", ["built_in"]),
        "item_count": len(items),
        "last_error": "; ".join(errors) if errors else meta.get("last_error"),
    }
    save_recommended_skill_catalog(items, fallback_meta)
    return items, fallback_meta


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    ensure_state_dir()
    existing = load_settings()
    merged = dict(DEFAULT_SETTINGS)
    merged.update(existing)
    merged.update(data)
    incoming_api_key = data.get("api_key", None)
    if isinstance(incoming_api_key, str) and not incoming_api_key.strip() and existing.get("api_key", "").strip():
        merged["api_key"] = existing["api_key"]
    merged = _normalize_api_config(merged)
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged


def _normalize_api_config(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settings)
    provider = str(normalized.get("api_provider") or "").strip() or "openai_compat"
    base_url = str(normalized.get("api_base_url") or "").strip()
    model = str(normalized.get("api_model") or "").strip()

    if provider == "deepseek":
        provider = "openai_compat"
        if not base_url:
            base_url = "https://api.deepseek.com/v1"
        if not model:
            model = "deepseek-chat"

    if not base_url:
        base_url = "https://api.deepseek.com/v1"
    if not model:
        model = "deepseek-chat"

    normalized["api_provider"] = provider
    normalized["api_base_url"] = base_url.rstrip("/")
    normalized["api_model"] = model
    return normalized


def create_job(
    job_type: str,
    *,
    status: str = "pending",
    progress: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    job_id = f"job_{uuid4().hex[:8]}"
    job = {
        "id": job_id,
        "type": job_type,
        "status": status,
        "progress": progress,
        "result": result,
        "error": error,
    }
    with JOB_LOCK:
        JOB_REGISTRY[job_id] = job
    return job


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    with JOB_LOCK:
        job = JOB_REGISTRY[job_id]
        job.update(changes)
        return dict(job)


def _safe_slug(value: str, fallback: str = "item") -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    slug = slug.strip("_")[:80]
    return slug or fallback


def _is_noise_memory_text(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    noisy_prefixes = [
        "新增 episode",
        "新增episode",
        "update episode",
        "updated episode",
    ]
    if any(text.startswith(prefix) for prefix in noisy_prefixes):
        return True
    noisy_fragments = [
        "支撑，补充了",
        "支撑, 补充了",
        "episode ",
    ]
    if "新增" in text and "支撑" in text:
        return True
    if any(fragment in text for fragment in noisy_fragments) and "episode" in text:
        return True
    if re.search(r"episode\s+[0-9a-f]{6,}", text):
        return True
    if re.search(r"新增\s*episode\s*[0-9a-f]{6,}", text):
        return True
    return False


def _looks_like_interest_text(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    interest_markers = [
        "用户对",
        "用户询问",
        "用户查询",
        "用户展示",
        "表现出兴趣",
        "保持关注",
        "倾向于关注",
        "感兴趣",
    ]
    lowered_markers = [marker.lower() for marker in interest_markers]
    if any(marker in text for marker in lowered_markers):
        return True
    if text.startswith("how to ") or text.startswith("what is "):
        return True
    return False


def _is_reusable_skill_candidate(title: str, steps: list[str] | None = None) -> bool:
    clean_title = str(title or "").strip()
    if not clean_title or _is_noise_memory_text(clean_title):
        return False
    if _looks_like_interest_text(clean_title):
        return False
    useful_steps = [step for step in (steps or []) if str(step).strip()]
    if len(useful_steps) >= 2:
        return True
    action_markers = [
        "下载",
        "导出",
        "整理",
        "提交",
        "填写",
        "读取",
        "提取",
        "分析",
        "写入",
        "同步",
        "配置",
        "调试",
        "报销",
        "review",
        "debug",
        "extract",
        "summarize",
        "plan",
    ]
    lowered = clean_title.lower()
    return any(marker in lowered for marker in action_markers)


def _has_standard_step_template(workflow: WorkflowMemory) -> bool:
    steps = [str(step).strip() for step in workflow.typical_steps if str(step).strip()]
    if len(steps) < 3:
        return False

    short_action_steps = 0
    for step in steps:
        if len(step) > 48:
            continue
        if re.match(r"^(第[一二三四五六七八九十0-9]+步|step\s*\d+|\d+[.)、])", step, re.I):
            short_action_steps += 1
            continue
        if any(marker in step.lower() for marker in ["确认", "收集", "下载", "填写", "整理", "提交", "核对", "导出", "识别", "提取", "输出", "review", "check", "collect", "download", "fill", "submit", "export"]):
            short_action_steps += 1

    if short_action_steps < 2:
        return False

    template_fields = [
        workflow.preferred_artifact_format,
        workflow.review_style,
        workflow.escalation_rule,
    ]
    return any(str(value or "").strip() for value in template_fields)


def _locale_bucket(locale: str | None) -> str:
    value = str(locale or "").lower()
    return "zh" if value.startswith("zh") else "en"


def _localized_field_label(group: str, field: str, locale: str | None) -> str:
    bucket = _locale_bucket(locale)
    return FIELD_LABELS.get(group, {}).get(bucket, {}).get(field, field)


def load_display_texts(settings: dict[str, Any]) -> dict[str, Any]:
    data = read_json_file(get_display_texts_path(settings, create=True))
    return data if isinstance(data, dict) else {"profile": {}, "preferences": {}, "persistent": {}}


def save_display_texts(settings: dict[str, Any], data: dict[str, Any]) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "profile": data.get("profile", {}),
        "preferences": data.get("preferences", {}),
        "projects": data.get("projects", {}),
        "workflows": data.get("workflows", {}),
        "skills": data.get("skills", {}),
        "persistent": data.get("persistent", {}),
    }
    get_display_texts_path(settings, create=True).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _preferences_payload_fallback(settings: dict[str, Any]) -> dict[str, Any]:
    display_cache = load_display_texts(settings).get("preferences", {})
    if not isinstance(display_cache, dict) or not display_cache:
        return {}

    payload: dict[str, Any] = {}
    list_fields = {"style_preference", "terminology_preference", "formatting_constraints", "forbidden_expressions", "revision_preference"}

    for item_id, entry in display_cache.items():
        if not str(item_id).startswith("preferences:"):
            continue
        suffix = str(item_id).split(":", 1)[1]
        if not suffix:
            continue
        field, has_item, _ = suffix.partition(":")
        if field in {"id", "created_at", "updated_at", "version", "evidence_links", "source_episode_ids", "source_turn_refs"}:
            continue
        if not field:
            continue

        desc = ""
        if isinstance(entry, dict):
            desc_data = entry.get("description")
            if isinstance(desc_data, dict):
                desc = str(desc_data.get("en") or desc_data.get("zh") or "").strip()
            else:
                desc = str(desc_data or "").strip()
        if not desc:
            continue

        if has_item:
            payload.setdefault(field, [])
            if desc not in payload[field]:
                payload[field].append(desc)
        elif field in list_fields and ("," in desc or "，" in desc):
            values = [part.strip() for part in re.split(r"[,，]", desc) if part.strip()]
            if values:
                payload[field] = values
        else:
            payload[field] = desc

    return payload


def _make_display_entry(
    *,
    title_zh: str,
    title_en: str,
    desc_zh: str,
    desc_en: str,
) -> dict[str, Any]:
    return {
        "title": {"zh": title_zh, "en": title_en},
        "description": {"zh": desc_zh, "en": desc_en},
    }


def _display_text(value: dict[str, Any] | None, locale: str | None, fallback: str) -> str:
    if not isinstance(value, dict):
        return fallback
    bucket = _locale_bucket(locale)
    text = str(value.get(bucket) or "").strip()
    return text or fallback


def _display_locale(locale: str | None) -> str:
    return _locale_bucket(locale or "zh")


def _localized_language_display(value: Any, locale: str | None, *, response_preference: bool = False) -> str:
    raw = str(value or "").strip()
    normalized = raw.lower()
    bucket = _display_locale(locale)
    language_map = {
        "zh": ("中文为主", "Mostly Chinese"),
        "zh-cn": ("中文为主", "Mostly Chinese"),
        "chinese": ("中文为主", "Mostly Chinese"),
        "中文": ("中文为主", "Mostly Chinese"),
        "汉语": ("中文为主", "Mostly Chinese"),
        "en": ("英文为主", "Mostly English"),
        "english": ("英文为主", "Mostly English"),
        "英文": ("英文为主", "Mostly English"),
        "英语": ("英文为主", "Mostly English"),
    }
    zh_text, en_text = language_map.get(normalized, language_map.get(raw, (raw, raw)))
    if response_preference:
        if bucket == "zh":
            return f"回答以{zh_text.removesuffix('为主')}为主" if zh_text.endswith("为主") else f"回答以{zh_text}为主"
        return f"Respond mostly in {en_text.removeprefix('Mostly ').lower()}" if en_text.startswith("Mostly ") else en_text
    return zh_text if bucket == "zh" else en_text


def _localized_granularity_display(value: Any, locale: str | None) -> str:
    raw = str(value or "").strip()
    normalized = raw.lower()
    bucket = _display_locale(locale)
    mapping = {
        "concise": ("偏简洁", "Concise"),
        "detailed": ("偏详细", "Detailed"),
        "step-by-step": ("步骤化说明", "Step-by-step"),
    }
    zh_text, en_text = mapping.get(normalized, (raw, raw))
    return zh_text if bucket == "zh" else en_text


def _memory_display_value(group: str, field: str, value: Any, locale: str | None) -> str:
    if isinstance(value, list):
        parts = [_memory_display_value(group, field, item, locale) for item in value]
        parts = [part for part in parts if part]
        return "；".join(dict.fromkeys(parts))

    if field in {"common_languages", "language_preference"}:
        return _localized_language_display(
            value,
            locale,
            response_preference=False,
        )
    if field == "response_granularity":
        return _localized_granularity_display(value, locale)
    return str(value or "").strip()


def _profile_display_title(field: str, locale: str | None) -> str:
    bucket = _display_locale(locale)
    zh = {
        "name_or_alias": "个人背景",
        "role_identity": "个人背景",
        "organization_or_affiliation": "个人背景",
        "domain_background": "领域背景",
        "common_languages": "语言与表达背景",
        "long_term_research_or_work_focus": "长期关注方向",
    }
    en = {
        "name_or_alias": "Personal Background",
        "role_identity": "Personal Background",
        "organization_or_affiliation": "Personal Background",
        "domain_background": "Domain Background",
        "common_languages": "Language and Expression Background",
        "long_term_research_or_work_focus": "Long-term Focus",
    }
    labels = zh if bucket == "zh" else en
    return labels.get(field, _localized_field_label("profile", field, locale))


def _preference_display_title(field: str, locale: str | None) -> str:
    bucket = _display_locale(locale)
    style_fields = {
        "style_preference",
        "terminology_preference",
        "formatting_constraints",
        "forbidden_expressions",
        "revision_preference",
        "response_granularity",
    }
    if field == "language_preference":
        return "回答语言偏好" if bucket == "zh" else "Response Language Preference"
    if field in style_fields:
        return "回答风格与格式" if bucket == "zh" else "Response Style and Format"
    return _localized_field_label("preferences", field, locale)


def _base_display_taxonomy(category: str) -> list[dict[str, Any]]:
    return [dict(group) for group in base_display_taxonomy(category)]


def _taxonomy_group_source_fields(category: str, group_id: str) -> list[str]:
    return taxonomy_group_source_fields(category, group_id)


def _taxonomy_title(group: dict[str, Any], locale: str | None) -> str:
    title = group.get("title")
    if isinstance(title, dict):
        return _display_text(title, locale, str(group.get("group_id") or ""))
    return str(title or group.get("group_id") or "").strip()


def _frontend_display_text(value: Any, *, max_length: int = 96) -> str:
    text = _normalize_snippet_text(str(value or "")).replace("…", "").replace("...", "")
    text = text.strip(" \t\r\n，,、；;：:。")
    if not text:
        return ""
    return truncate_text(text, max_length, ellipsis=False).rstrip("，,、；;：:。")


def _looks_incomplete_frontend_title(value: Any) -> bool:
    text = _frontend_display_text(value, max_length=120).lower()
    if not text:
        return True
    if text in {"未命名", "暂无", "暂无细项", "unknown", "none", "n/a", "null"}:
        return True
    if re.fullmatch(r"(pn_\d+|[a-f0-9]{8}|[a-f0-9-]{20,})", text):
        return True
    if re.fullmatch(r"[\W_]+", text, flags=re.UNICODE):
        return True
    return False


def _frontend_title_from_description(description: Any, fallback: str = "") -> str:
    text = _frontend_display_text(description, max_length=160)
    if not text:
        return fallback
    text = re.sub(
        r"^用户(正在|曾经|曾|明确表示|表示|希望|需要|喜欢|倾向于|进一步|正在寻找|寻找|询问|想要|想)?",
        "",
        text,
    ).strip("，,。；;：: ")
    first = re.split(r"[。；;\n]", text, maxsplit=1)[0].strip("，,。；;：: ")
    if not first:
        return fallback
    return truncate_text(first, 32, ellipsis=False).rstrip("，,、；;：:。")


def _frontend_memory_item(
    item: dict[str, Any],
    *,
    category: str,
    fallback_title: str = "",
    fallback_description: str = "",
) -> dict[str, Any]:
    normalized = dict(item)
    title = _frontend_display_text(
        normalized.get("display_title") or normalized.get("title") or fallback_title,
        max_length=64,
    )
    description = _frontend_display_text(
        normalized.get("display_description") or normalized.get("description") or fallback_description,
        max_length=140,
    )
    if _looks_incomplete_frontend_title(title):
        title = _frontend_title_from_description(description, fallback_title) or _frontend_display_text(
            normalized.get("id") or category,
            max_length=32,
        )
    if not description or description == title:
        description = _frontend_display_text(fallback_description, max_length=140)
    if not description and category in {"profile", "preferences"}:
        description = title
    normalized["title"] = title
    normalized["display_title"] = title
    normalized["description"] = description
    normalized["display_description"] = description
    return normalized


def _payload_field_value(
    payload: dict[str, Any],
    field: str,
    *,
    category: str,
    episodes: list[EpisodicMemory] | None = None,
    projects: list[ProjectMemory] | None = None,
) -> Any:
    value = payload.get(field)
    if field == "primary_task_types":
        return _stable_primary_task_types(
            [str(item) for item in (value or [])],
            episodes or [],
            projects or [],
        )
    return value


def _profile_long_term_focus_values(payload: dict[str, Any] | Any) -> list[str]:
    value = payload.get("long_term_research_or_work_focus") if isinstance(payload, dict) else payload
    raw_values = value if isinstance(value, list) else [value]
    values: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values or []:
        for part in re.split(r"[；;\n]+", str(raw_value or "")):
            text = " ".join(part.split()).strip("，,。；;：: ")
            normalized = text.lower()
            if not text or normalized in seen:
                continue
            seen.add(normalized)
            values.append(text)
    return values


def _taxonomy_group_description(
    *,
    category: str,
    payload: dict[str, Any],
    group: dict[str, Any],
    locale: str | None,
    episodes: list[EpisodicMemory] | None = None,
    projects: list[ProjectMemory] | None = None,
) -> tuple[str, list[str]]:
    parts: list[str] = []
    active_fields: list[str] = []
    for field in group.get("source_fields", []) or []:
        field_name = str(field or "").strip()
        if not field_name:
            continue
        value = _payload_field_value(
            payload,
            field_name,
            category=category,
            episodes=episodes,
            projects=projects,
        )
        if not value:
            continue
        text = _memory_display_value(category, field_name, value, locale)
        if not text or _is_noise_memory_text(text):
            continue
        active_fields.append(field_name)
        parts.append(text)
    description = "；".join(dict.fromkeys(parts))
    return truncate_text(description, 140, ellipsis=False), active_fields


def _daily_note_title_from_key(raw_key: str) -> str:
    key = str(raw_key or "").strip().lower()
    if not key or key.startswith("pn_"):
        return ""
    ignored = {
        "context",
        "candidate",
        "candidates",
        "option",
        "options",
        "suggestion",
        "suggestions",
        "note",
        "notes",
        "prefers",
        "preference",
        "preferences",
        "taste",
        "criteria",
    }
    tokens = [token for token in re.split(r"[_\-\s]+", key) if token]
    content_tokens = [token for token in tokens if token not in ignored]
    if not content_tokens:
        return ""
    title = "".join(content_tokens[:3]) if re.search(r"[\u4e00-\u9fff]", key) else " ".join(content_tokens[:3])
    return truncate_text(title, 24, ellipsis=False)


def _strip_daily_note_display_prefix(text: str) -> str:
    return re.sub(
        r"^用户(正在|曾经|曾|明确表示|表示|希望|需要|喜欢|倾向于|进一步|正在寻找|寻找|询问|想要|想|要求)?",
        "",
        str(text or ""),
    ).strip("，,。；;：: ")


def _clean_daily_note_display_text(value: Any, *, max_length: int) -> str:
    text = str(value or "").strip("，,。；;：: ")
    if not text:
        return ""
    text = _normalize_snippet_text(text).replace("…", "").replace("...", "")
    text = re.sub(
        r"\b(?:pending|pending choice|pending preference|to be confirmed|needs confirmation)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?:，|,|、|；|;)?\s*(?:偏好|选择|方案|选项)?待确认$", "", text)
    text = re.sub(r"(?:，|,|、|；|;)?\s*待确认(?:偏好|选择|方案|选项)?$", "", text)
    text = re.sub(r"^(?:偏好|选择|方案|选项)?待确认$", "", text)
    text = re.sub(r"^待确认(?:偏好|选择|方案|选项)?$", "", text)
    text = re.sub(r"\b(?:context|candidate|node|memory|support|episode|display)\b", "", text, flags=re.IGNORECASE)
    text = _strip_daily_note_display_prefix(text)
    return truncate_text(text.strip("，,。；;：: "), max_length, ellipsis=False).rstrip("，,、；;：: ")


def _daily_note_first_sentence(value: str, *, max_length: int) -> str:
    text = _normalize_snippet_text(value).replace("…", "").replace("...", "")
    if not text:
        return ""
    first = re.split(r"[。；;\n]", text, maxsplit=1)[0]
    return _clean_daily_note_display_text(first, max_length=max_length)


def _daily_note_fallback_title(raw_description: str, raw_key: str, node_id: str) -> str:
    title = _daily_note_first_sentence(raw_description, max_length=24)
    if title and not _is_noise_memory_text(title):
        return title
    key_title = _daily_note_title_from_key(raw_key)
    if key_title and not _is_noise_memory_text(key_title):
        return key_title
    return _clean_daily_note_display_text(node_id, max_length=24) or "日常记忆"


def _daily_note_fallback_description(raw_description: str, title: str, raw_key: str) -> str:
    description = _daily_note_first_sentence(raw_description, max_length=36)
    if description and description != title and not _is_noise_memory_text(description):
        return description
    if re.search(r"[_\-]", str(raw_key or "")):
        return ""
    key_description = _clean_daily_note_display_text(raw_key, max_length=36)
    if key_description and key_description != title and not _is_noise_memory_text(key_description):
        return key_description
    return ""


def _daily_note_display_texts(
    node_id: str,
    node: dict[str, Any],
    display_entry: dict[str, Any],
    locale: str | None,
) -> tuple[str, str]:
    raw_description = str(node.get("description") or "").strip()
    raw_key = str(node.get("key") or node_id).strip()
    if not display_entry:
        display_entry = _node_display_entry(node, raw_description or raw_key) or {}
    cached_title = _clean_daily_note_display_text(
        _display_text(display_entry.get("title"), locale, ""),
        max_length=24,
    )
    cached_description = _clean_daily_note_display_text(
        _display_text(display_entry.get("description"), locale, ""),
        max_length=36,
    )

    title = cached_title if cached_title and not _is_noise_memory_text(cached_title) else ""
    description = (
        cached_description
        if cached_description
        and cached_description != title
        and not _is_noise_memory_text(cached_description)
        else ""
    )
    if not title:
        title = _daily_note_fallback_title(raw_description, raw_key, node_id)
    if not description:
        description = _daily_note_fallback_description(raw_description, title, raw_key)
    return title, description


def _display_cache_entry(display_cache: dict[str, Any], category: str, item_id: str) -> dict[str, Any]:
    category_cache = display_cache.get(category)
    if not isinstance(category_cache, dict):
        return {}
    entry = category_cache.get(item_id)
    return entry if isinstance(entry, dict) else {}


def _display_cache_texts(
    display_cache: dict[str, Any],
    category: str,
    item_id: str,
    locale: str | None,
    *,
    fallback_title: str,
    fallback_description: str,
) -> tuple[str, str]:
    entry = _display_cache_entry(display_cache, category, item_id)
    title = _display_text(entry.get("title"), locale, fallback_title) if entry else fallback_title
    description = _display_text(entry.get("description"), locale, fallback_description) if entry else fallback_description
    title = _frontend_display_text(title, max_length=64) or _frontend_display_text(fallback_title, max_length=64)
    description = _frontend_display_text(description, max_length=140)
    if not description or description == title:
        description = _frontend_display_text(fallback_description, max_length=140)
    return title, description


def _split_display_list_text(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，]", str(text or "")) if part.strip()]


def _looks_like_english_ui_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"[\u4e00-\u9fff]", text):
        return False
    return bool(re.search(r"[A-Za-z]", text))


def _looks_like_response_style_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    direct_keywords = [
        "中文", "英文", "双语", "简洁", "详细", "严谨", "活泼", "正式", "口语", "分点", "列表", "表格", "自然段", "结论先行", "步骤化",
        "concise", "detailed", "formal", "casual", "professional", "bullet", "bullets", "numbered", "table", "tables", "structured", "tone", "style", "format", "formatting", "granularity",
    ]
    if any(keyword in lowered for keyword in direct_keywords):
        return True
    noise_keywords = [
        "zero-shot", "few-shot", "llm", "model", "memory", "migration", "audit", "mapping", "standardization", "validation", "benchmark",
        "免训练", "零样本", "小样本", "大模型", "记忆", "迁移", "可审计", "映射", "标准化", "验证", "产品", "市场分析",
        "paper", "research", "ssh", "pdf", "excel", "workflow", "skill", "prompt", "mcp", "server",
    ]
    if any(keyword in lowered for keyword in noise_keywords):
        return False
    short_terms = {"简洁", "详细", "严谨", "活泼", "礼貌", "直接", "精炼", "正式", "专业", "清晰"}
    return text in short_terms


def _ensure_bilingual_display_value(
    llm: LLMClient,
    raw_value: Any,
    zh_value: Any,
    en_value: Any,
) -> tuple[Any, Any]:
    if isinstance(raw_value, list):
        raw_list = [str(item).strip() for item in raw_value if str(item).strip()]
        zh_list = zh_value if isinstance(zh_value, list) else raw_list
        en_list = en_value if isinstance(en_value, list) else raw_list
        need_fix = (
            not raw_list
            or not isinstance(zh_value, list)
            or len(zh_list) != len(raw_list)
            or all(
                _looks_like_english_ui_text(candidate) and str(candidate).strip() == raw_item
                for candidate, raw_item in zip(zh_list, raw_list)
            )
        )
        if not raw_list or not need_fix:
            return zh_list, en_list

        result = llm.extract_json(
            "你是一个中英双语 UI 文案整理器。请只根据输入短语生成适合产品界面展示的中英文。"
            "中文要自然、简洁，技术词可以保留原文或行业常用缩写。"
            "不要根据示例、字段名或个别关键词推断固定领域分类；不要新增输入中没有的含义。"
            "返回严格 JSON：{\"zh\": [...], \"en\": [...]}，长度必须与输入一致。",
            json.dumps({"values": raw_list}, ensure_ascii=False, indent=2),
        )
        if isinstance(result, dict):
            zh_new = result.get("zh")
            en_new = result.get("en")
            if isinstance(zh_new, list) and len(zh_new) == len(raw_list):
                zh_list = [str(item).strip() or raw_item for item, raw_item in zip(zh_new, raw_list)]
            if isinstance(en_new, list) and len(en_new) == len(raw_list):
                en_list = [str(item).strip() or raw_item for item, raw_item in zip(en_new, raw_list)]
        return zh_list, en_list

    raw_text = str(raw_value or "").strip()
    zh_text = str(zh_value or "").strip()
    en_text = str(en_value or "").strip() or raw_text
    need_fix = raw_text and (not zh_text or (_looks_like_english_ui_text(zh_text) and zh_text == raw_text))
    if not need_fix:
        return zh_text or raw_text, en_text or raw_text

    result = llm.extract_json(
        "你是一个中英双语 UI 文案整理器。请只根据输入短语生成适合产品界面展示的中英文。"
        "中文要自然、简洁，技术词可以保留原文或行业常用缩写。"
        "不要根据示例、字段名或个别关键词推断固定领域分类；不要新增输入中没有的含义。"
        "返回严格 JSON：{\"zh\": \"...\", \"en\": \"...\"}。",
        json.dumps({"value": raw_text}, ensure_ascii=False, indent=2),
    )
    if isinstance(result, dict):
        zh_text = str(result.get("zh") or zh_text or raw_text).strip()
        en_text = str(result.get("en") or en_text or raw_text).strip()
    return zh_text or raw_text, en_text or raw_text


def _daily_note_display_entry_from_result(result: Any, fallback: str) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    title = result.get("title")
    description = result.get("description")
    if not isinstance(title, dict) or not isinstance(description, dict):
        return None
    title_zh = _clean_daily_note_display_text(title.get("zh"), max_length=24)
    title_en = _clean_daily_note_display_text(title.get("en"), max_length=80)
    desc_zh = _clean_daily_note_display_text(description.get("zh"), max_length=36)
    desc_en = _clean_daily_note_display_text(description.get("en"), max_length=120)
    if not title_zh and not title_en:
        return None
    title_zh = title_zh or title_en or fallback
    title_en = title_en or title_zh or fallback
    desc_zh = desc_zh or title_zh
    desc_en = desc_en or title_en
    return _make_display_entry(
        title_zh=title_zh,
        title_en=title_en,
        desc_zh=desc_zh,
        desc_en=desc_en,
    )


def _node_display_entry(node: dict[str, Any], fallback: str) -> dict[str, Any] | None:
    display = node.get("display")
    if isinstance(display, dict):
        entry = _daily_note_display_entry_from_result(display, fallback)
        if entry is not None:
            return entry
    return None


def _get_persistent_display_entry(
    raw_text: str,
    node: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node_entry = _node_display_entry(node or {}, raw_text)
    if node_entry is not None:
        return node_entry

    return _make_display_entry(
        title_zh=raw_text,
        title_en=raw_text,
        desc_zh=raw_text,
        desc_en=raw_text,
    )


def get_storage_root(settings: dict[str, Any], *, create: bool = False) -> Path:
    raw_path = settings.get("storage_path", "").strip()
    root = Path(raw_path).expanduser() if raw_path else DEFAULT_WIKI_ROOT
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def get_wiki(settings: dict[str, Any]) -> L2Wiki:
    return L2Wiki(get_storage_root(settings, create=True))


def get_raw_root(settings: dict[str, Any], *, create: bool = False) -> Path:
    raw_root = get_storage_root(settings, create=create) / "raw"
    if create:
        raw_root.mkdir(parents=True, exist_ok=True)
    return raw_root


def get_l1_root(settings: dict[str, Any], *, create: bool = False) -> Path:
    l1_root = get_storage_root(settings, create=create) / "platform_memory"
    if create:
        l1_root.mkdir(parents=True, exist_ok=True)
    return l1_root


def get_legacy_l1_root(settings: dict[str, Any]) -> Path:
    return get_storage_root(settings) / "l1_signals"


def get_skills_root(settings: dict[str, Any], *, create: bool = False) -> Path:
    skills_root = get_storage_root(settings, create=create) / "skills"
    if create:
        skills_root.mkdir(parents=True, exist_ok=True)
    return skills_root


def get_workflows_root(settings: dict[str, Any], *, create: bool = False) -> Path:
    workflows_root = get_storage_root(settings, create=create) / "workflows"
    if create:
        workflows_root.mkdir(parents=True, exist_ok=True)
    return workflows_root


def get_organize_state_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    metadata_dir = get_storage_root(settings, create=create) / "metadata"
    if create:
        metadata_dir.mkdir(parents=True, exist_ok=True)
    return metadata_dir / "organize_state.json"


def get_display_texts_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    metadata_dir = get_storage_root(settings, create=create) / "metadata"
    if create:
        metadata_dir.mkdir(parents=True, exist_ok=True)
    return metadata_dir / "display_texts.json"


def get_memory_ignore_state_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    metadata_dir = get_storage_root(settings, create=create) / "metadata"
    if create:
        metadata_dir.mkdir(parents=True, exist_ok=True)
    return metadata_dir / "memory_ignore_state.json"


def _persistent_memory_assets_missing(settings: dict[str, Any]) -> bool:
    root = get_storage_root(settings)
    required_paths = [
        root / "profile" / "profile.json",
        root / "preferences" / "preferences.json",
        root / "metadata" / "index.json",
        get_display_texts_path(settings, create=False),
        root / "projects" / "index.json",
        root / "workflows" / "index.json",
    ]
    return any(not path.exists() for path in required_paths)


def _persistent_node_assets_missing(settings: dict[str, Any]) -> bool:
    root = get_storage_root(settings)
    persistent_root = _readable_persistent_root(root)
    return not persistent_root.exists() or not _readable_persistent_index_path(root).exists()


def _clear_project_assets_for_rebuild(settings: dict[str, Any]) -> None:
    projects_root = get_storage_root(settings, create=True) / "projects"
    if not projects_root.exists():
        return
    for child in projects_root.iterdir():
        if child.name == "index.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        elif child.suffix in {".json", ".md"}:
            child.unlink()


def get_platform_memory_index_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    return get_l1_root(settings, create=create) / "index.json"


def get_skill_index_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    return get_skills_root(settings, create=create) / "index.json"


def get_workflow_asset_index_path(settings: dict[str, Any], *, create: bool = False) -> Path:
    return get_workflows_root(settings, create=create) / "index.json"


def load_organize_state(settings: dict[str, Any]) -> dict[str, Any]:
    path = get_organize_state_path(settings, create=True)
    data = read_json_file(path)
    if isinstance(data, dict):
        return {
            "raw_index": data.get("raw_index", {}),
            "last_organized_at": data.get("last_organized_at"),
            "l1_signature": data.get("l1_signature", ""),
            "episode_signature": data.get("episode_signature", ""),
            "persistent_signature": data.get("persistent_signature", ""),
            "persistent_rebuild_version": data.get("persistent_rebuild_version", ""),
            "node_maintenance_signature": data.get("node_maintenance_signature", ""),
            "last_persistent_rebuild_at": data.get("last_persistent_rebuild_at"),
            "last_node_maintained_at": data.get("last_node_maintained_at"),
            "last_run_stats": data.get("last_run_stats", {}),
        }
    return {
        "raw_index": {},
        "last_organized_at": None,
        "l1_signature": "",
        "episode_signature": "",
        "persistent_signature": "",
        "persistent_rebuild_version": "",
        "node_maintenance_signature": "",
        "last_persistent_rebuild_at": None,
        "last_node_maintained_at": None,
        "last_run_stats": {},
    }


def save_organize_state(settings: dict[str, Any], state: dict[str, Any]) -> None:
    path = get_organize_state_path(settings, create=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_memory_ignore_state() -> dict[str, Any]:
    return {
        "version": "1.0",
        "profile": {"fields": [], "values": {}},
        "preferences": {"fields": [], "values": {}},
        "deleted_items": [],
    }


def _sanitize_memory_ignore_bucket(value: Any) -> dict[str, Any]:
    bucket = value if isinstance(value, dict) else {}
    fields = [
        str(field).strip()
        for field in (bucket.get("fields") or [])
        if str(field or "").strip()
    ]
    values: dict[str, list[dict[str, str]]] = {}
    raw_values = bucket.get("values")
    if isinstance(raw_values, dict):
        for field, entries in raw_values.items():
            field_name = str(field or "").strip()
            if not field_name:
                continue
            normalized_entries: list[dict[str, str]] = []
            raw_entries = entries if isinstance(entries, list) else [entries]
            for entry in raw_entries:
                if isinstance(entry, dict):
                    slug = str(entry.get("slug") or "").strip()
                    text = str(entry.get("text") or "").strip()
                else:
                    text = str(entry or "").strip()
                    slug = _safe_slug(text, "item") if text else ""
                if slug or text:
                    normalized_entries.append({"slug": slug, "text": text})
            if normalized_entries:
                seen: set[tuple[str, str]] = set()
                deduped: list[dict[str, str]] = []
                for entry in normalized_entries:
                    key = (entry.get("slug", ""), entry.get("text", ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(entry)
                values[field_name] = deduped
    return {
        "fields": sorted(set(fields)),
        "values": values,
    }


def load_memory_ignore_state(settings: dict[str, Any]) -> dict[str, Any]:
    data = read_json_file(get_memory_ignore_state_path(settings, create=True))
    payload = _default_memory_ignore_state()
    if isinstance(data, dict):
        payload["version"] = str(data.get("version") or payload["version"])
        payload["profile"] = _sanitize_memory_ignore_bucket(data.get("profile"))
        payload["preferences"] = _sanitize_memory_ignore_bucket(data.get("preferences"))
        deleted_items = data.get("deleted_items", [])
        if isinstance(deleted_items, list):
            payload["deleted_items"] = [item for item in deleted_items if isinstance(item, dict)]
    return payload


def save_memory_ignore_state(settings: dict[str, Any], state: dict[str, Any]) -> None:
    payload = _default_memory_ignore_state()
    if isinstance(state, dict):
        payload["version"] = str(state.get("version") or payload["version"])
        payload["profile"] = _sanitize_memory_ignore_bucket(state.get("profile"))
        payload["preferences"] = _sanitize_memory_ignore_bucket(state.get("preferences"))
        deleted_items = state.get("deleted_items", [])
        if isinstance(deleted_items, list):
            payload["deleted_items"] = [item for item in deleted_items if isinstance(item, dict)]
    get_memory_ignore_state_path(settings, create=True).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _hash_payload(payload: Any) -> str:
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _elapsed_seconds(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _organize_episode_worker_count(settings: dict[str, Any], changed_count: int) -> int:
    configured = settings.get("organize_episode_workers")
    default = min(ORGANIZE_EPISODE_MAX_WORKERS, max(1, changed_count))
    return _bounded_int(
        configured,
        default=default,
        minimum=1,
        maximum=min(ORGANIZE_EPISODE_MAX_WORKERS, max(1, changed_count)),
    )


def _persistent_node_batch_size(settings: dict[str, Any]) -> int:
    return _bounded_int(
        settings.get("persistent_node_batch_size"),
        default=PERSISTENT_NODE_BATCH_SIZE,
        minimum=1,
        maximum=8,
    )


def compute_episode_signature(wiki: L2Wiki) -> str:
    episodes = [
        {
            "episode_id": ep.episode_id,
            "conv_id": ep.conv_id,
            "granularity": ep.granularity,
            "turn_refs": ep.turn_refs,
            "topic": ep.topic,
            "summary": ep.summary,
            "connections": [item.model_dump(mode="json") for item in ep.connections],
            "projects": ep.relates_to_projects,
            "workflows": ep.relates_to_workflows,
            "updated_at": ep.updated_at.isoformat() if ep.updated_at else "",
        }
        for ep in wiki.list_episodes()
    ]
    return _hash_payload(episodes)


def compute_persistent_signature(wiki: L2Wiki, settings: dict[str, Any] | None = None) -> str:
    profile = wiki.load_profile()
    preferences = wiki.load_preferences()
    projects = [project.model_dump(mode="json") for project in wiki.list_projects()]
    workflows = [workflow.model_dump(mode="json") for workflow in wiki.load_workflows()]
    payload = {
        "profile": profile.model_dump(mode="json") if profile else None,
        "preferences": preferences.model_dump(mode="json") if preferences else None,
        "projects": projects,
        "workflows": workflows,
    }
    if settings is not None:
        ignore_state = load_memory_ignore_state(settings)
        persistent_nodes = load_persistent_nodes(settings)
        payload["memory_ignore_state"] = ignore_state
        payload["persistent_node_deleted_locks"] = persistent_nodes.get("deleted_node_locks", [])
    return _hash_payload(payload)


def update_platform_memory_index(
    settings: dict[str, Any],
    files: list[dict[str, Any]],
    signature: str = "",
) -> None:
    index_path = get_platform_memory_index_path(settings, create=True)
    payload = {
        "folder": "platform_memory",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "signature": signature,
        "files": files,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _unique_string_list(values: list[Any], *, max_items: int = 24) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").replace("\n", " ").strip()
        normalized = " ".join(text.split()).lower()
        if not text or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(" ".join(text.split()))
        if len(items) >= max_items:
            break
    return items


def _normalize_custom_instruction_blocks(values: list[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values or []:
        label = "instruction"
        content = ""
        if isinstance(value, dict):
            label = str(value.get("label") or value.get("name") or value.get("title") or label).strip() or label
            content = str(value.get("content") or value.get("text") or "").strip()
        else:
            content = str(value or "").strip()
        if not content:
            continue
        key = f"{label.lower()}::{content.lower()}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"label": label, "content": content})
    return normalized[:12]


def _normalize_platform_skill_records(values: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values or []:
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("title") or "").strip()
            summary = str(value.get("summary") or value.get("description") or "").strip()
            trigger = str(value.get("trigger") or "").strip()
            output_format = str(value.get("output_format") or "").strip()
            steps = _unique_string_list(list(value.get("steps") or []), max_items=8)
            references = _unique_string_list(list(value.get("references") or []), max_items=8)
        else:
            name = str(value or "").strip()
            summary = ""
            trigger = ""
            output_format = ""
            steps = []
            references = []
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "name": name,
                "summary": summary,
                "trigger": trigger,
                "steps": steps,
                "output_format": output_format,
                "references": references,
            }
        )
    return normalized[:16]


def _normalize_agent_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    raw_instructions = value.get("instructions") or ""
    if isinstance(raw_instructions, list):
        instructions = "\n".join(str(item).strip() for item in raw_instructions if str(item).strip())
    else:
        instructions = str(raw_instructions or "").strip()
    goal = str(value.get("goal") or "").strip()
    description = str(value.get("description") or goal).strip()
    normalized = {
        "name": str(value.get("name") or "").strip(),
        "description": description,
        "goal": goal,
        "instructions": instructions,
        "conversation_starters": _unique_string_list(
            list(value.get("conversation_starters") or value.get("conversationStarters") or []),
            max_items=8,
        ),
        "knowledge": _unique_string_list(list(value.get("knowledge") or []), max_items=8),
        "tools": _unique_string_list(list(value.get("tools") or []), max_items=8),
        "handoff_rules": _unique_string_list(
            list(value.get("handoff_rules") or value.get("handoffRules") or []),
            max_items=8,
        ),
    }
    if not any(
        normalized.get(field)
        for field in [
            "name",
            "description",
            "goal",
            "instructions",
            "conversation_starters",
            "knowledge",
            "tools",
            "handoff_rules",
        ]
    ):
        return {}
    return normalized


def build_platform_memory_record(payload: PlatformMemoryImportRequest) -> dict[str, Any]:
    hints = _unique_string_list(list(payload.memoryHints or []), max_items=30)
    saved_memory = _unique_string_list(list(payload.savedMemoryItems or []), max_items=24)
    custom_instructions = _normalize_custom_instruction_blocks(list(payload.customInstructions or []))
    agent_config = _normalize_agent_config(payload.agentConfig)
    platform_skills = _normalize_platform_skill_records(list(payload.platformSkills or []))
    record_types = _unique_string_list(
        list(payload.recordTypes or [])
        + (["saved_memory"] if saved_memory else [])
        + (["custom_instruction"] if custom_instructions else [])
        + (["agent_config"] if agent_config else [])
        + (["platform_skill"] if platform_skills else []),
        max_items=8,
    )

    excerpt = (payload.pageTextExcerpt or "").strip()
    if len(excerpt) > 8000:
        excerpt = excerpt[:8000]

    summary_candidates = [
        payload.heading,
        payload.title,
        payload.agentName,
        saved_memory[0] if saved_memory else "",
        agent_config.get("description", ""),
        platform_skills[0].get("name", "") if platform_skills else "",
    ]
    summary = next((str(item).strip() for item in summary_candidates if str(item or "").strip()), "")

    return {
        "record_id": "",
        "platform": payload.platform,
        "url": payload.url,
        "title": payload.title,
        "heading": payload.heading,
        "agent_name": payload.agentName,
        "chat_id": payload.chatId,
        "captured_at": payload.capturedAt or datetime.now(timezone.utc).isoformat(),
        "page_type": payload.pageType or (record_types[0] if record_types else "platform_context"),
        "record_types": record_types,
        "memory": saved_memory or hints,
        "saved_memory": saved_memory,
        "custom_instructions": custom_instructions,
        "agent_config": agent_config,
        "platform_skills": platform_skills,
        "context_hints": hints,
        "summary": summary,
        "page_excerpt": excerpt,
        "source_type": "platform_memory_asset",
    }


def platform_memory_signature(record: dict[str, Any]) -> str:
    payload = {
        "platform": record.get("platform", ""),
        "title": record.get("title", ""),
        "heading": record.get("heading", ""),
        "agent_name": record.get("agent_name", ""),
        "page_type": record.get("page_type", ""),
        "record_types": record.get("record_types", []),
        "memory": record.get("memory", []),
        "saved_memory": record.get("saved_memory", []),
        "custom_instructions": record.get("custom_instructions", []),
        "agent_config": record.get("agent_config", {}),
        "platform_skills": record.get("platform_skills", []),
        "page_excerpt": record.get("page_excerpt", ""),
    }
    return _hash_payload(payload)


def _normalized_platform_text(value: str) -> str:
    compact = "".join(ch.lower() if ch.isalnum() else " " for ch in (value or ""))
    return " ".join(part for part in compact.split() if part)


def _platform_identity_key(record: dict[str, Any]) -> str:
    for value in (
        record.get("agent_config", {}).get("name", "") if isinstance(record.get("agent_config"), dict) else "",
        record.get("agent_name", ""),
        record.get("heading", ""),
        record.get("title", ""),
    ):
        normalized = _normalized_platform_text(str(value))
        if normalized:
            return normalized
    return _normalized_platform_text(str(record.get("platform", ""))) or "platform_memory"


def _platform_url_key(record: dict[str, Any]) -> str:
    raw_url = str(record.get("url", "")).strip()
    if not raw_url:
        return ""
    parsed = urllib.parse.urlparse(raw_url)
    path = parsed.path or ""
    segments = [seg for seg in path.split("/") if seg]
    if segments and len(segments[-1]) >= 20:
        segments = segments[:-1]
    normalized = "/".join(segments[:3])
    return normalized.lower()


def _platform_memory_match_score(existing: dict[str, Any], current: dict[str, Any]) -> float:
    if str(existing.get("platform", "")).strip().lower() != str(current.get("platform", "")).strip().lower():
        return 0.0

    if existing.get("signature") and existing.get("signature") == current.get("signature"):
        return 1.0

    score = 0.0
    existing_types = {str(item).strip().lower() for item in existing.get("record_types", []) if str(item).strip()}
    current_types = {str(item).strip().lower() for item in current.get("record_types", []) if str(item).strip()}
    if existing_types and current_types:
        if existing_types == current_types:
            score += 0.2
        elif existing_types & current_types:
            score += 0.1

    if _platform_identity_key(existing) == _platform_identity_key(current):
        score += 0.5

    url_key_existing = _platform_url_key(existing)
    url_key_current = _platform_url_key(current)
    if url_key_existing and url_key_existing == url_key_current:
        score += 0.25

    existing_memory = {str(item).strip().lower() for item in existing.get("memory", []) if str(item).strip()}
    current_memory = {str(item).strip().lower() for item in current.get("memory", []) if str(item).strip()}
    if existing_memory and current_memory:
        overlap = len(existing_memory & current_memory) / max(len(existing_memory | current_memory), 1)
        score += overlap * 0.3

    existing_saved = {str(item).strip().lower() for item in existing.get("saved_memory", []) if str(item).strip()}
    current_saved = {str(item).strip().lower() for item in current.get("saved_memory", []) if str(item).strip()}
    if existing_saved and current_saved:
        overlap = len(existing_saved & current_saved) / max(len(existing_saved | current_saved), 1)
        score += overlap * 0.25

    existing_skills = {
        str(item.get("name") or "").strip().lower()
        for item in existing.get("platform_skills", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    current_skills = {
        str(item.get("name") or "").strip().lower()
        for item in current.get("platform_skills", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    if existing_skills and current_skills:
        overlap = len(existing_skills & current_skills) / max(len(existing_skills | current_skills), 1)
        score += overlap * 0.2

    excerpt_existing = _normalized_platform_text(str(existing.get("page_excerpt", "")))[:400]
    excerpt_current = _normalized_platform_text(str(current.get("page_excerpt", "")))[:400]
    if excerpt_existing and excerpt_current and excerpt_existing == excerpt_current:
        score += 0.2

    return score


def _merge_platform_memory_records(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["record_id"] = primary.get("record_id") or incoming.get("record_id") or ""
    merged["platform"] = primary.get("platform") or incoming.get("platform", "")
    merged["url"] = primary.get("url") or incoming.get("url", "")
    merged["title"] = primary.get("title") or incoming.get("title", "")
    merged["heading"] = primary.get("heading") or incoming.get("heading", "")
    merged["agent_name"] = primary.get("agent_name") or incoming.get("agent_name", "")
    merged["summary"] = primary.get("summary") or incoming.get("summary", "")
    merged["chat_id"] = primary.get("chat_id") or incoming.get("chat_id", "")
    merged["page_type"] = primary.get("page_type") or incoming.get("page_type", "")
    merged["source_type"] = "platform_memory_asset"
    merged["record_types"] = _unique_string_list(
        [*(primary.get("record_types") or []), *(incoming.get("record_types") or [])],
        max_items=8,
    )

    merged["memory"] = _unique_string_list(
        [*(primary.get("memory") or []), *(incoming.get("memory") or [])],
        max_items=30,
    )
    merged["saved_memory"] = _unique_string_list(
        [*(primary.get("saved_memory") or []), *(incoming.get("saved_memory") or [])],
        max_items=24,
    )
    merged["context_hints"] = _unique_string_list(
        [*(primary.get("context_hints") or []), *(incoming.get("context_hints") or [])],
        max_items=24,
    )
    merged["custom_instructions"] = _normalize_custom_instruction_blocks(
        [*(primary.get("custom_instructions") or []), *(incoming.get("custom_instructions") or [])]
    )
    merged_agent = dict(primary.get("agent_config") or {})
    incoming_agent = dict(incoming.get("agent_config") or {})
    merged["agent_config"] = {
        "name": merged_agent.get("name") or incoming_agent.get("name", ""),
        "description": merged_agent.get("description") or incoming_agent.get("description", ""),
        "instructions": merged_agent.get("instructions") or incoming_agent.get("instructions", ""),
        "conversation_starters": _unique_string_list(
            [*(merged_agent.get("conversation_starters") or []), *(incoming_agent.get("conversation_starters") or [])],
            max_items=8,
        ),
        "knowledge": _unique_string_list(
            [*(merged_agent.get("knowledge") or []), *(incoming_agent.get("knowledge") or [])],
            max_items=8,
        ),
        "tools": _unique_string_list(
            [*(merged_agent.get("tools") or []), *(incoming_agent.get("tools") or [])],
            max_items=8,
        ),
    }
    merged["platform_skills"] = _normalize_platform_skill_records(
        [*(primary.get("platform_skills") or []), *(incoming.get("platform_skills") or [])]
    )

    merged["captured_at"] = primary.get("captured_at") or incoming.get("captured_at")
    merged["first_captured_at"] = (
        primary.get("first_captured_at")
        or primary.get("captured_at")
        or incoming.get("first_captured_at")
        or incoming.get("captured_at")
    )
    merged["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    merged["capture_count"] = int(primary.get("capture_count", 1)) + int(incoming.get("capture_count", 1))

    primary_excerpt = str(primary.get("page_excerpt", "")).strip()
    incoming_excerpt = str(incoming.get("page_excerpt", "")).strip()
    if len(incoming_excerpt) > len(primary_excerpt):
        merged["page_excerpt"] = incoming_excerpt
    else:
        merged["page_excerpt"] = primary_excerpt

    if not merged.get("summary"):
        merged["summary"] = (
            merged.get("heading")
            or merged.get("title")
            or merged.get("agent_name")
            or next(iter(merged.get("saved_memory") or []), "")
            or next((item.get("name", "") for item in merged.get("platform_skills", []) if isinstance(item, dict)), "")
        )
    merged["signature"] = platform_memory_signature(merged)
    return merged


def consolidate_platform_memory(settings: dict[str, Any]) -> dict[str, int]:
    platform_root = get_l1_root(settings, create=True)
    files = sorted(
        path for path in platform_root.glob("*.json") if path.is_file() and path.name != "index.json"
    )
    kept_files: list[Path] = []
    merged_count = 0
    removed_count = 0

    for path in files:
        current = read_json_file(path)
        if not isinstance(current, dict):
            continue
        current.setdefault("record_id", path.stem)
        current.setdefault("platform", "")
        current.setdefault("memory", [])
        current["signature"] = platform_memory_signature(current)

        matched_path: Path | None = None
        for kept in kept_files:
            existing = read_json_file(kept)
            if not isinstance(existing, dict):
                continue
            if _platform_memory_match_score(existing, current) >= 0.55:
                matched_path = kept
                break

        if matched_path is None:
            path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
            kept_files.append(path)
            continue

        existing = read_json_file(matched_path)
        if not isinstance(existing, dict):
            continue
        existing.setdefault("record_id", matched_path.stem)
        merged = _merge_platform_memory_records(existing, current)
        matched_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        if path != matched_path and path.exists():
            path.unlink()
            removed_count += 1
        merged_count += 1

    load_l1_signals(settings)
    return {"merged": merged_count, "removed": removed_count, "remaining": len(kept_files)}


def _find_best_platform_memory_match(
    platform_root: Path,
    current: dict[str, Any],
    *,
    threshold: float = 0.55,
) -> Path | None:
    best_path: Path | None = None
    best_score = 0.0
    for path in sorted(platform_root.glob("*.json")):
        if not path.is_file() or path.name == "index.json":
            continue
        existing = read_json_file(path)
        if not isinstance(existing, dict):
            continue
        score = _platform_memory_match_score(existing, current)
        if score >= threshold and score > best_score:
            best_score = score
            best_path = path
    return best_path


def save_skill_library(settings: dict[str, Any], skills: list[dict[str, Any]]) -> None:
    skills_root = get_skills_root(settings, create=True)
    for child in skills_root.iterdir():
        if child.name == "index.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    index_items = []
    for skill in skills:
        slug = _safe_slug(skill.get("id", skill.get("title", "skill")))
        asset_dir = skills_root / slug
        asset_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = asset_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        json_path = asset_dir / "skill.json"
        json_path.write_text(json.dumps(skill, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = [f"# {skill.get('title', slug)}\n"]
        kind = skill.get("kind", "skill")
        md_lines.append(f"**Type:** {kind}")
        if skill.get("trigger"):
            md_lines.append(f"**Trigger:** {skill['trigger']}")
        if skill.get("goal"):
            md_lines.append(f"**Goal:** {skill['goal']}")
        if skill.get("output_format"):
            md_lines.append(f"**Output:** {skill['output_format']}")
        if skill.get("steps"):
            md_lines.append("\n**Steps:**")
            md_lines.extend(f"- {step}" for step in skill["steps"] if step)
        if skill.get("guardrails"):
            md_lines.append("\n**Guardrails:**")
            md_lines.extend(f"- {item}" for item in skill["guardrails"] if item)
        if skill.get("composition", {}).get("uses_skills"):
            md_lines.append("\n**Uses Skills:**")
            md_lines.extend(f"- {item}" for item in skill["composition"]["uses_skills"])
        if skill.get("composition", {}).get("prompt_template"):
            md_lines.append(f"\n**Prompt Template:** {skill['composition']['prompt_template']}")
        if skill.get("source_types"):
            md_lines.append(f"\n**Source Types:** {', '.join(skill['source_types'])}")
        if skill.get("confidence"):
            md_lines.append(f"**Confidence:** {skill['confidence']}")
        (asset_dir / "SKILL.md").write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

        forms_lines = ["# Forms\n"]
        if skill.get("trigger"):
            forms_lines.append(f"## Trigger\n{skill['trigger']}\n")
        if skill.get("output_format"):
            forms_lines.append(f"## Output Format\n{skill['output_format']}\n")
        if skill.get("steps"):
            forms_lines.append("## Standard Steps")
            forms_lines.extend(f"{idx + 1}. {step}" for idx, step in enumerate(skill["steps"]) if step)
        if skill.get("guardrails"):
            forms_lines.append("\n## Guardrails")
            forms_lines.extend(f"- {item}" for item in skill["guardrails"] if item)
        (asset_dir / "forms.md").write_text("\n".join(forms_lines).strip() + "\n", encoding="utf-8")

        ref_lines = ["# Reference\n"]
        if skill.get("description"):
            ref_lines.append(f"## Summary\n{skill['description']}\n")
        if skill.get("source_types"):
            ref_lines.append("## Sources")
            ref_lines.extend(f"- {item}" for item in skill["source_types"] if item)
        if skill.get("evidence_episode_ids"):
            ref_lines.append("\n## Evidence Episodes")
            ref_lines.extend(f"- {item}" for item in skill["evidence_episode_ids"] if item)
        if skill.get("composition"):
            ref_lines.append("\n## Composition")
            for key, value in skill["composition"].items():
                if value:
                    ref_lines.append(f"- {key}: {value}")
        (asset_dir / "reference.md").write_text("\n".join(ref_lines).strip() + "\n", encoding="utf-8")
        (scripts_dir / "README.md").write_text(
            "# Scripts\n\nPlace executable helpers for this skill here when the skill becomes operationalized.\n",
            encoding="utf-8",
        )
        index_items.append(
            {
                "id": skill.get("id"),
                "title": skill.get("title"),
                "kind": skill.get("kind", "skill"),
                "folder": slug,
                "json": f"{slug}/skill.json",
                "skill_md": f"{slug}/SKILL.md",
                "forms_md": f"{slug}/forms.md",
                "reference_md": f"{slug}/reference.md",
            }
        )

    get_skill_index_path(settings, create=True).write_text(
        json.dumps(
            {
                "folder": "skills",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "items": index_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def save_workflow_asset_library(settings: dict[str, Any], workflows: list[WorkflowMemory]) -> None:
    workflows_root = get_workflows_root(settings, create=True)
    for child in workflows_root.iterdir():
        if child.name == "index.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    index_items: list[dict[str, Any]] = []
    for workflow in workflows:
        slug = _safe_slug(workflow.workflow_name or "workflow")
        asset_dir = workflows_root / slug
        asset_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = asset_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)

        workflow_payload = workflow.model_dump(mode="json")
        (asset_dir / "workflow.json").write_text(
            json.dumps(workflow_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        skill_lines = [f"# {workflow.workflow_name}\n", "**Type:** workflow"]
        if workflow.trigger_condition:
            skill_lines.append(f"**Trigger:** {workflow.trigger_condition}")
        if workflow.reuse_frequency:
            skill_lines.append(f"**Frequency:** {workflow.reuse_frequency}")
        if workflow.preferred_artifact_format:
            skill_lines.append(f"**Output:** {workflow.preferred_artifact_format}")
        if workflow.review_style:
            skill_lines.append(f"**Review Style:** {workflow.review_style}")
        if workflow.typical_steps:
            skill_lines.append("\n**Standard Steps:**")
            skill_lines.extend(f"{idx + 1}. {step}" for idx, step in enumerate(workflow.typical_steps) if step)
        if workflow.escalation_rule:
            skill_lines.append(f"\n**Escalation Rule:** {workflow.escalation_rule}")
        (asset_dir / "SKILL.md").write_text("\n".join(skill_lines).strip() + "\n", encoding="utf-8")

        forms_lines = ["# Forms\n"]
        if workflow.preferred_artifact_format:
            forms_lines.append(f"## Output Template\n{workflow.preferred_artifact_format}\n")
        if workflow.typical_steps:
            forms_lines.append("## Checklist")
            forms_lines.extend(f"- {step}" for step in workflow.typical_steps if step)
        if workflow.review_style:
            forms_lines.append(f"\n## Review Style\n{workflow.review_style}")
        if workflow.escalation_rule:
            forms_lines.append(f"\n## Escalation Rule\n{workflow.escalation_rule}")
        (asset_dir / "forms.md").write_text("\n".join(forms_lines).strip() + "\n", encoding="utf-8")

        ref_lines = ["# Reference\n"]
        ref_lines.append(f"## Occurrence Count\n{workflow.occurrence_count}")
        if workflow.evidence_links:
            ref_lines.append("\n## Evidence")
            for link in workflow.evidence_links:
                excerpt = str(getattr(link, "excerpt", "") or "").strip()
                source_type = str(getattr(link, "source_type", "") or "").strip()
                source_id = str(getattr(link, "source_id", "") or "").strip()
                line = f"- {source_type}:{source_id}"
                if excerpt:
                    line += f" — {excerpt[:100]}"
                ref_lines.append(line)
        (asset_dir / "reference.md").write_text("\n".join(ref_lines).strip() + "\n", encoding="utf-8")
        (scripts_dir / "README.md").write_text(
            "# Scripts\n\nPlace reusable automation helpers for this workflow here.\n",
            encoding="utf-8",
        )

        index_items.append(
            {
                "id": workflow.workflow_name,
                "title": workflow.workflow_name,
                "folder": slug,
                "json": f"{slug}/workflow.json",
                "skill_md": f"{slug}/SKILL.md",
                "forms_md": f"{slug}/forms.md",
                "reference_md": f"{slug}/reference.md",
            }
        )

    get_workflow_asset_index_path(settings, create=True).write_text(
        json.dumps(
            {
                "folder": "workflows",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "items": index_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def stable_episode_id(raw_key: str) -> str:
    return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:8]


def _project_signal_count(project: ProjectMemory) -> int:
    buckets = 0
    if project.project_goal.strip():
        buckets += 1
    if project.current_stage.strip():
        buckets += 1
    if project.next_actions:
        buckets += 1
    if project.unresolved_questions:
        buckets += 1
    if project.finished_decisions:
        buckets += 1
    if project.important_constraints:
        buckets += 1
    return buckets


def _looks_like_reference_analysis_project(project: ProjectMemory) -> bool:
    text_parts = [
        project.project_name,
        project.project_goal,
        project.current_stage,
        *(entry.text for entry in project.relevant_entities[:4]),
        *(entry.text for entry in project.important_constraints[:4]),
        *(entry.text for entry in project.unresolved_questions[:4]),
        *(entry.text for entry in project.next_actions[:4]),
    ]
    haystack = ' '.join(str(part or '').lower() for part in text_parts)
    reference_tokens = {
        'baseline', 'benchmark', 'dataset', 'paper', 'survey', 'algorithm', 'method', 'ablation',
        'compare', 'comparison', 'literature', 'related work', 'sota', 'reference', 'references',
        'arxiv', 'cvpr', 'iccv', 'neurips', 'iclr', 'aaai',
    }
    project_tokens = {
        'submission', 'submitted', 'prototype', 'system', 'repo', 'repository', 'codebase', 'experiment',
        'milestone', 'deliverable', 'implementation', 'deploy', 'deployment', 'roadmap', '计划', '实验',
        '投稿', '系统', '实现', '代码库', '原型', '里程碑', '部署',
    }
    reference_hits = sum(1 for token in reference_tokens if token in haystack)
    project_hits = sum(1 for token in project_tokens if token in haystack)
    if reference_hits >= 2 and project_hits == 0:
        return True
    return False


def _looks_like_user_owned_build_project(project: ProjectMemory) -> bool:
    text_parts = [
        project.project_name,
        project.project_goal,
        project.current_stage,
        *(entry.text for entry in project.next_actions[:4]),
        *(entry.text for entry in project.unresolved_questions[:4]),
        *(entry.text for entry in project.finished_decisions[:4]),
    ]
    haystack = " ".join(str(part or "").lower() for part in text_parts)
    owner_intent_tokens = {
        "build", "building", "create", "creating", "develop", "developing", "launch", "ship",
        "submit", "submission", "mvp", "prototype", "plan", "roadmap",
        "想做", "希望做", "要做", "准备做", "构建", "搭建", "开发", "实现", "推进", "投稿", "平台", "系统",
    }
    project_shape_tokens = {
        "platform", "framework", "system", "project", "evaluation", "benchmark",
        "平台", "框架", "系统", "项目", "评测", "统一评测",
    }
    has_owner_intent = any(token in haystack for token in owner_intent_tokens)
    has_project_shape = any(token in haystack for token in project_shape_tokens)
    return has_owner_intent and has_project_shape


def _looks_like_stable_project(project: ProjectMemory) -> bool:
    episode_count = len(set(project.source_episode_ids))
    signal_count = _project_signal_count(project)
    name = project.project_name.strip().lower()

    if signal_count < 2:
        return False

    # Allow a single strong episode to count as a project when it already
    # contains concrete project structure such as goals, stage, decisions,
    # questions, constraints, or next actions.
    if episode_count < 1:
        return False

    # Filter out topic-like or exploratory labels that are discussed repeatedly
    # but still don't yet look like an actual long-running project.
    exploratory_tokens = {
        "recommendation",
        "suggestion",
        "option",
        "choice",
        "selection",
        "comparison",
        "price",
        "list",
        "guide",
        "question",
        "advice",
        "configuration",
        "exploration",
    }
    token_hits = sum(1 for token in exploratory_tokens if token in name)
    if episode_count < 2 and token_hits >= 2 and signal_count < 3:
        return False

    if _looks_like_reference_analysis_project(project) and not _looks_like_user_owned_build_project(project) and signal_count < 4:
        return False

    return True


def _looks_like_stable_workflow(workflow: WorkflowMemory) -> bool:
    name = workflow.workflow_name.strip()
    if not name or _is_noise_memory_text(name) or _looks_like_interest_text(name):
        return False

    steps = [step for step in workflow.typical_steps if str(step).strip()]
    if workflow.occurrence_count < 3:
        return False
    if len(steps) < 2:
        return False
    if not workflow.trigger_condition.strip():
        return False

    has_template_signal = any(
        str(value or "").strip()
        for value in [
            workflow.preferred_artifact_format,
            workflow.review_style,
            workflow.escalation_rule,
            workflow.reuse_frequency,
        ]
    )
    if not has_template_signal:
        return False
    if not _has_standard_step_template(workflow):
        return False

    lowered = name.lower()
    generic_topic_tokens = [
        "recommendation",
        "suggestion",
        "option",
        "choice",
        "comparison",
        "list",
        "guide",
        "question",
        "advice",
        "exploration",
    ]
    if any(token in lowered for token in generic_topic_tokens):
        return False

    return True


def _episode_has_workflow_candidate(episode: EpisodicMemory) -> bool:
    if getattr(episode, "relates_to_workflows", None):
        return True
    text = _canonical_memory_text(
        " ".join(
            [
                str(getattr(episode, "topic", "") or ""),
                str(getattr(episode, "summary", "") or ""),
                " ".join(getattr(episode, "topics_covered", []) or []),
                " ".join(getattr(episode, "key_decisions", []) or []),
                " ".join(getattr(episode, "open_issues", []) or []),
            ]
        )
    )
    if not text:
        return False
    procedure_markers = {
        "workflow", "sop", "process", "procedure", "pipeline", "playbook", "checklist", "template",
        "流程", "工作流", "步骤", "清单", "模板", "规范", "标准流程", "固定流程",
    }
    reuse_markers = {
        "reuse", "repeat", "recurring", "whenever", "every time", "standard", "habit",
        "复用", "重复", "每次", "以后", "固定", "标准", "长期", "习惯",
    }
    return any(marker in text for marker in procedure_markers) and any(marker in text for marker in reuse_markers)


def _has_workflow_extraction_candidates(
    episodes: list[EpisodicMemory],
    l1_text: str,
    platform_workflows: list[WorkflowMemory],
) -> bool:
    if platform_workflows:
        return True
    if any(_episode_has_workflow_candidate(episode) for episode in episodes):
        return True
    l1 = _canonical_memory_text(l1_text)
    return bool(l1 and any(marker in l1 for marker in ["workflow", "sop", "流程", "工作流", "固定步骤", "复用流程"]))


def _is_concrete_skill_record(
    *,
    title: str,
    trigger: str = "",
    goal: str = "",
    steps: list[str] | None = None,
    output_format: str = "",
) -> bool:
    clean_title = str(title or "").strip()
    useful_steps = [str(step).strip() for step in (steps or []) if str(step).strip()]
    if not _is_reusable_skill_candidate(clean_title, useful_steps):
        return False
    if len(useful_steps) < 2:
        return False
    if not str(trigger or "").strip() and not str(goal or "").strip():
        return False
    if len(clean_title) < 3:
        return False
    vague_tokens = [
        "recommendation",
        "suggestion",
        "option",
        "choice",
        "interest",
        "topic",
        "habit",
        "exploration",
        "configuration",
    ]
    lowered = clean_title.lower()
    if any(token in lowered for token in vague_tokens):
        return False
    if not str(output_format or "").strip():
        return False
    return True


def _project_can_derive_skill(project: ProjectMemory) -> bool:
    text = _canonical_memory_text(
        " ".join(
            [
                project.project_name,
                project.project_goal,
                project.current_stage,
                " ".join(entry.text for entry in project.next_actions[:4]),
            ]
        )
    )
    if not text:
        return False
    project_tokens = {
        "project", "platform", "system", "benchmark", "evaluation",
        "项目", "平台", "系统", "评测", "基准",
    }
    reusable_tokens = {
        "workflow", "sop", "pipeline", "automation", "template", "playbook", "methodology",
        "流程", "自动化", "模板", "工作流", "方法论",
    }
    if any(token in text for token in project_tokens) and not any(token in text for token in reusable_tokens):
        return False
    return any(token in text for token in reusable_tokens)


def load_platform_memory_records(settings: dict[str, Any]) -> list[dict[str, Any]]:
    root = get_l1_root(settings, create=True)
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if not path.is_file() or path.name == "index.json":
            continue
        data = read_json_file(path)
        if isinstance(data, dict):
            data.setdefault("record_id", path.stem)
            records.append(data)
    return records


def _load_platform_memory_record_map(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    record_map: dict[str, dict[str, Any]] = {}
    for record in load_platform_memory_records(settings):
        record_id = str(record.get("record_id") or record.get("signature") or "").strip()
        if not record_id:
            continue
        record_map[record_id] = record
    return record_map


def _normalize_merge_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _extend_unique(target: list[str], values: list[str]) -> list[str]:
    seen = {item.strip().lower() for item in target if item.strip()}
    for value in values:
        clean = _normalize_merge_text(value)
        if not clean:
            continue
        lowered = clean.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        target.append(clean)
    return target


_L1_LANGUAGE_VARIANTS = {
    "中文": "中文",
    "汉语": "中文",
    "chinese": "中文",
    "mandarin": "中文",
    "英文": "英文",
    "英语": "英文",
    "english": "英文",
    "日文": "日文",
    "日语": "日文",
    "japanese": "日文",
}

_L1_ROLE_PATTERNS = [
    (r"\b(student|phd student|graduate student|undergraduate|postdoc|researcher|professor|teacher|engineer|developer|product manager|designer)\b", {
        "student": "学生",
        "phd student": "博士生",
        "graduate student": "研究生",
        "undergraduate": "本科生",
        "postdoc": "博士后",
        "researcher": "研究者",
        "professor": "教授",
        "teacher": "老师",
        "engineer": "工程师",
        "developer": "开发者",
        "product manager": "产品经理",
        "designer": "设计师",
    }),
    (r"(学生|研究生|博士生|老师|教授|研究员|工程师|开发者|产品经理|设计师)", None),
]


def _extract_languages_from_text(text: str) -> list[str]:
    lowered = str(text or "").lower()
    languages: list[str] = []
    for needle, label in _L1_LANGUAGE_VARIANTS.items():
        if needle in lowered or needle in text:
            languages.append(label)
    return _unique_string_list(languages, max_items=6)


def _extract_language_preference(text: str) -> str:
    lowered = str(text or "").lower()
    preference_markers = [
        "请用", "使用", "回答用", "reply in", "respond in", "answer in", "write in", "prefer responses in",
    ]
    if any(marker in text for marker in ["请用中文", "使用中文", "回答用中文"]) or (
        any(marker in lowered for marker in ["reply in chinese", "respond in chinese", "answer in chinese", "write in chinese"])
    ):
        return "中文"
    if any(marker in text for marker in ["请用英文", "使用英文", "回答用英文"]) or (
        any(marker in lowered for marker in ["reply in english", "respond in english", "answer in english", "write in english"])
    ):
        return "英文"
    if any(marker in lowered for marker in preference_markers):
        langs = _extract_languages_from_text(text)
        return langs[0] if langs else ""
    return ""


def _extract_role_identity(text: str) -> str:
    raw_text = str(text or "")
    lowered = raw_text.lower()
    for pattern, mapping in _L1_ROLE_PATTERNS:
        match = re.search(pattern, lowered if mapping else raw_text, re.IGNORECASE)
        if not match:
            continue
        role = match.group(1).strip()
        if mapping:
            return mapping.get(role.lower(), role)
        return role
    return ""


def _extract_domain_background(text: str) -> list[str]:
    raw_text = _normalize_merge_text(text)
    lowered = raw_text.lower()
    patterns = [
        r"(?:background in|research in|research on|work on|focus on|domain[:：]|领域[:：]|研究方向[:：]|专业方向[:：])\s*([A-Za-z0-9 \-/+,&]+)",
        r"(?:做|研究|方向是|领域是)([A-Za-z\u4e00-\u9fff0-9 \-/+,&]{2,40})",
    ]
    values: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, raw_text, flags=re.IGNORECASE):
            candidate = _normalize_merge_text(match)
            if not candidate:
                continue
            candidate = re.split(r"[。；;,.，]", candidate)[0].strip()
            if 2 <= len(candidate) <= 40:
                values.append(candidate)
    return _unique_string_list(values, max_items=6)


def _extract_response_style_claims(text: str) -> dict[str, list[str] | str]:
    raw_text = _normalize_merge_text(text)
    lowered = raw_text.lower()
    claims: dict[str, list[str] | str] = {
        "style_preference": [],
        "formatting_constraints": [],
        "revision_preference": [],
        "response_granularity": "",
    }
    if not raw_text or not _looks_like_response_style_text(raw_text):
        return claims

    style_terms = {
        "简洁": "简洁",
        "concise": "简洁",
        "详细": "详细",
        "detailed": "详细",
        "严谨": "严谨",
        "formal": "正式",
        "professional": "专业",
        "活泼": "活泼",
        "casual": "自然",
    }
    formatting_terms = {
        "分点": "分点表达",
        "bullet": "分点表达",
        "bullets": "分点表达",
        "列表": "列表形式",
        "numbered": "编号列表",
        "表格": "表格形式",
        "table": "表格形式",
        "结论先行": "结论先行",
        "步骤化": "步骤化说明",
        "step-by-step": "步骤化说明",
    }
    revision_terms = {
        "不要太长": "避免冗长",
        "shorter": "避免冗长",
        "精炼": "精炼表达",
        "polish": "适度润色",
    }
    for keyword, mapped in style_terms.items():
        if keyword in lowered or keyword in raw_text:
            claims["style_preference"] = _extend_unique(list(claims["style_preference"]), [mapped])
    for keyword, mapped in formatting_terms.items():
        if keyword in lowered or keyword in raw_text:
            claims["formatting_constraints"] = _extend_unique(list(claims["formatting_constraints"]), [mapped])
    for keyword, mapped in revision_terms.items():
        if keyword in lowered or keyword in raw_text:
            claims["revision_preference"] = _extend_unique(list(claims["revision_preference"]), [mapped])

    if any(keyword in lowered or keyword in raw_text for keyword in ["详细", "detailed", "step-by-step"]):
        claims["response_granularity"] = "detailed"
    elif any(keyword in lowered or keyword in raw_text for keyword in ["简洁", "concise", "short"]):
        claims["response_granularity"] = "concise"
    return claims


def _record_excerpt(record: dict[str, Any], fallback: str = "") -> str:
    for value in [
        record.get("summary", ""),
        next(iter(record.get("saved_memory") or []), ""),
        next((item.get("content", "") for item in (record.get("custom_instructions") or []) if isinstance(item, dict)), ""),
        fallback,
    ]:
        text = _normalize_merge_text(value)
        if text:
            return text[:160]
    return ""


def _merge_scalar_field_from_l1(
    obj: MemoryBase,
    field: str,
    value: str,
    record_id: str,
    excerpt: str,
) -> None:
    clean = _normalize_merge_text(value)
    if not clean:
        return
    existing = _normalize_merge_text(getattr(obj, field, ""))
    if not existing:
        setattr(obj, field, clean)
        obj.add_evidence("l1_signal", record_id, excerpt or clean[:100])
        return
    if existing.lower() == clean.lower():
        obj.add_evidence("l1_signal", record_id, excerpt or clean[:100])
        return
    obj.record_conflict(field, existing, clean, f"l1_signal:{record_id}")


def _merge_list_field_from_l1(
    obj: MemoryBase,
    field: str,
    values: list[str],
    record_id: str,
    excerpt: str,
) -> None:
    current = list(getattr(obj, field, []) or [])
    merged = _extend_unique(current[:], values)
    if merged != current:
        setattr(obj, field, merged)
    if values:
        obj.add_evidence("l1_signal", record_id, excerpt or "；".join(values)[:100])


def _merge_l1_claims_into_profile_preferences(
    settings: dict[str, Any],
    profile: ProfileMemory,
    preferences: PreferenceMemory,
) -> tuple[ProfileMemory, PreferenceMemory]:
    for record in load_platform_memory_records(settings):
        record_id = str(record.get("record_id") or record.get("signature") or "").strip()
        if not record_id:
            continue
        textual_units: list[str] = []
        textual_units.extend(str(item).strip() for item in (record.get("saved_memory") or []) if str(item).strip())
        textual_units.extend(
            str(item.get("content") or "").strip()
            for item in (record.get("custom_instructions") or [])
            if isinstance(item, dict) and str(item.get("content") or "").strip()
        )
        agent = record.get("agent_config") or {}
        if isinstance(agent, dict):
            for key in ["description", "instructions"]:
                value = str(agent.get(key) or "").strip()
                if value:
                    textual_units.append(value)

        for unit in textual_units:
            excerpt = _record_excerpt(record, unit)
            language_pref = _extract_language_preference(unit)
            if language_pref:
                _merge_scalar_field_from_l1(preferences, "language_preference", language_pref, record_id, excerpt)

            languages = _extract_languages_from_text(unit)
            if languages:
                _merge_list_field_from_l1(profile, "common_languages", languages, record_id, excerpt)

            role_identity = _extract_role_identity(unit)
            if role_identity:
                _merge_scalar_field_from_l1(profile, "role_identity", role_identity, record_id, excerpt)

            domains = _extract_domain_background(unit)
            if domains:
                _merge_list_field_from_l1(profile, "domain_background", domains, record_id, excerpt)

            if re.search(r"(?:organization|affiliation|institution|学校|单位|实验室|学院)[:：]?\s*", unit, re.IGNORECASE):
                organization = re.split(r"[:：]", unit, maxsplit=1)[-1].strip() if ":" in unit or "：" in unit else unit.strip()
                if organization:
                    _merge_scalar_field_from_l1(profile, "organization_or_affiliation", organization[:80], record_id, excerpt)

            style_claims = _extract_response_style_claims(unit)
            if style_claims.get("style_preference"):
                _merge_list_field_from_l1(
                    preferences,
                    "style_preference",
                    list(style_claims["style_preference"]),
                    record_id,
                    excerpt,
                )
            if style_claims.get("formatting_constraints"):
                _merge_list_field_from_l1(
                    preferences,
                    "formatting_constraints",
                    list(style_claims["formatting_constraints"]),
                    record_id,
                    excerpt,
                )
            if style_claims.get("revision_preference"):
                _merge_list_field_from_l1(
                    preferences,
                    "revision_preference",
                    list(style_claims["revision_preference"]),
                    record_id,
                    excerpt,
                )
            if style_claims.get("response_granularity"):
                _merge_scalar_field_from_l1(
                    preferences,
                    "response_granularity",
                    str(style_claims["response_granularity"]),
                    record_id,
                    excerpt,
                )
    return profile, preferences


def _normalize_primary_task_type(value: str) -> str:
    label = re.sub(r"\s+", "", str(value or "").strip())
    label = re.sub(r"^[：:、，,\-\s]+|[：:、，,\-\s]+$", "", label)
    if not label:
        return ""
    label = re.sub(r"^(用户常见|常见|长期|主要|高频)", "", label)
    label = re.sub(r"(任务|需求|场景)$", "", label)
    if not label or len(label) > 12:
        return ""
    return label


def _looks_like_over_specific_task_type(value: str) -> bool:
    label = _normalize_primary_task_type(value)
    if not label:
        return True
    text = _canonical_memory_text(label).replace(" ", "")
    action_markers = {
        "推荐", "建议", "选择", "选购", "搭配", "分析", "总结", "规划", "写作", "润色",
        "调试", "实现", "测试", "排查", "比较", "整理", "设计",
        "recommend", "advice", "suggest", "choose", "compare", "analyze", "summarize",
        "plan", "write", "debug", "test", "design",
    }
    # A broad label should usually be an action mode, not action + one concrete object.
    broad_connectors = {"与", "和", "或", "及", "、", "and", "or"}
    has_broad_connector = any(connector in text for connector in broad_connectors)
    if "/" in label or "／" in label:
        return True
    if len(label) >= 5 and not has_broad_connector and any(text.startswith(marker) for marker in action_markers):
        return True
    if len(label) > 10:
        return True
    return False


def _task_type_similarity_key(value: str) -> str:
    text = _canonical_memory_text(value).replace(" ", "")
    for suffix in ("任务", "需求", "场景", "工作", "处理"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _dedupe_primary_task_types(
    values: list[str],
    projects: list[ProjectMemory] | None = None,
    max_items: int = 3,
) -> list[str]:
    project_keys = {
        _canonical_memory_text(project.project_name).replace(" ", "")
        for project in projects or []
        if str(project.project_name or "").strip()
    }
    labels: list[str] = []
    keys: list[str] = []
    for value in values:
        label = _normalize_primary_task_type(value)
        if not label:
            continue
        if _looks_like_over_specific_task_type(label):
            continue
        key = _task_type_similarity_key(label)
        if not key:
            continue
        if any(project_key and (key in project_key or project_key in key) for project_key in project_keys):
            continue
        duplicate_index = next(
            (
                index
                for index, existing_key in enumerate(keys)
                if key == existing_key or key in existing_key or existing_key in key
            ),
            None,
        )
        if duplicate_index is not None:
            if len(label) < len(labels[duplicate_index]):
                labels[duplicate_index] = label
                keys[duplicate_index] = key
            continue
        labels.append(label)
        keys.append(key)
        if len(labels) >= max_items:
            break
    return labels


def _task_type_support_text(episode: EpisodicMemory) -> str:
    return _canonical_memory_text(
        " ".join(
            [
                episode.topic,
                episode.summary,
                " ".join(episode.key_decisions),
                " ".join(episode.open_issues),
                " ".join(episode.topics_covered),
            ]
        )
    )


def _task_type_is_mentioned(label: str, text: str) -> bool:
    key = _task_type_similarity_key(label)
    if not key or not text:
        return False
    compact_text = text.replace(" ", "")
    if key in compact_text:
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{4,}", key):
        edge_tokens = list(dict.fromkeys([key[:2], key[-2:]]))
        weak_tokens = {"建议", "列表", "任务", "类型", "需求", "场景"}
        if any(token not in weak_tokens and token in compact_text for token in edge_tokens):
            return True
    tokens = [
        token
        for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", label)
        if token and len(token) >= 2
    ]
    if re.search(r"[\u4e00-\u9fff]", key) and len(key) >= 4:
        tokens.extend(key[index:index + 2] for index in range(0, len(key) - 1))
    if not tokens and len(key) >= 4:
        tokens = [key[index:index + 2] for index in range(0, len(key) - 1)]
    tokens = list(dict.fromkeys(tokens))
    if not tokens:
        return False
    hits = sum(1 for token in tokens if token in compact_text)
    return hits >= min(2, len(tokens))


def _task_type_has_explicit_stability_signal(text: str) -> bool:
    markers = {
        "经常", "常常", "长期", "反复", "通常", "主要", "偏好", "喜欢让你", "以后",
        "每次", "稳定", "固定", "习惯", "always", "usually", "often", "frequently",
        "prefer", "preference", "from now on",
    }
    return any(marker in text for marker in markers)


def _episode_route_text(episode: EpisodicMemory) -> str:
    return _canonical_memory_text(
        " ".join(
            [
                episode.topic,
                episode.summary,
                " ".join(episode.key_decisions or []),
                " ".join(episode.open_issues or []),
                " ".join(episode.topics_covered or []),
            ]
        )
    )


def _episode_has_profile_memory_signal(episode: EpisodicMemory) -> bool:
    text = _episode_route_text(episode)
    if not text:
        return False
    markers = {
        "我是", "我的身份", "我的职业", "我的专业", "我的背景", "我的研究方向",
        "长期关注", "研究方向", "工作方向", "专业背景", "所在机构", "来自",
        "i am", "my role", "my background", "my research", "my work", "affiliation",
        "student", "researcher", "engineer", "developer", "professor",
    }
    return any(marker in text for marker in markers)


def _episode_has_response_preference_signal(episode: EpisodicMemory) -> bool:
    text = _episode_route_text(episode)
    if not text:
        return False
    markers = {
        "以后回答", "以后回复", "回答时", "回复时", "请用中文", "请用英文", "用中文回答",
        "用英文回答", "输出格式", "回答格式", "表达风格", "语气", "不要使用", "避免",
        "先确认", "先问我", "每次都", "从现在开始", "记住我希望",
        "reply in", "respond in", "answer in", "when replying", "output format",
        "response style", "tone", "do not use", "avoid", "from now on",
    }
    return any(marker in text for marker in markers)


def _normalize_episode_memory_routes(episode: EpisodicMemory) -> EpisodicMemory:
    """Keep daily-life context out of profile/preferences route flags."""
    if MemoryBuilder._episode_has_daily_memory_signal(episode):
        if not _episode_has_profile_memory_signal(episode):
            episode.relates_to_profile = False
        if not _episode_has_response_preference_signal(episode):
            episode.relates_to_preferences = False
    elif _episode_has_response_preference_signal(episode):
        episode.relates_to_preferences = True
    return episode


def _infer_primary_task_type_candidates(
    episodes: list[EpisodicMemory],
    projects: list[ProjectMemory] | None = None,
    workflows: list[WorkflowMemory] | None = None,
) -> list[str]:
    candidates: list[str] = []

    def add(label: str) -> None:
        if label:
            candidates.append(label)

    for episode in episodes:
        text = _task_type_support_text(episode)
        compact = text.replace(" ", "")
        is_project_episode = bool(episode.relates_to_projects)

        if any(token in compact for token in ["搭配", "配色", "styling", "matching"]):
            add("搭配建议")

        if any(token in compact for token in ["推荐", "建议", "有哪些", "有什么", "哪个", "哪些", "比较", "recommend", "suggest", "compare"]):
            add("推荐列表")

        research_markers = {
            "研究", "调研", "论文", "发表", "benchmark", "评测", "现有工作", "项目",
            "平台", "mvp", "roadmap", "research", "survey", "literature",
        }
        if is_project_episode or any(token in compact for token in research_markers):
            add("研究规划")

        if any(token in compact for token in ["写作", "润色", "改写", "draft", "rewrite", "editing"]):
            add("写作修改")

        if any(token in compact for token in ["报错", "调试", "排查", "修复", "debug", "error", "bug", "fix"]):
            add("问题排查")

    for project in projects or []:
        project_text = _canonical_memory_text(
            " ".join([project.project_name, project.project_goal, project.current_stage])
        )
        if any(token in project_text for token in ["研究", "benchmark", "评测", "论文", "调研", "项目", "平台"]):
            add("研究规划")

    for workflow in workflows or []:
        workflow_text = _canonical_memory_text(
            " ".join([workflow.workflow_name, workflow.trigger_condition, " ".join(workflow.typical_steps or [])])
        )
        if any(token in workflow_text for token in ["写作", "润色", "改写", "draft", "rewrite"]):
            add("写作修改")
        if any(token in workflow_text for token in ["调试", "排查", "修复", "debug", "bug"]):
            add("问题排查")

    return _dedupe_primary_task_types(candidates, projects, max_items=6)


def _stable_primary_task_types(
    values: list[str],
    episodes: list[EpisodicMemory],
    projects: list[ProjectMemory] | None = None,
    explicit_text: str = "",
) -> list[str]:
    """Keep only durable task modes, not one-off episode topics."""
    candidates = _dedupe_primary_task_types(values, projects, max_items=3)
    if not candidates:
        return []

    explicit_haystack = _canonical_memory_text(explicit_text)
    total_episodes = len(episodes)
    total_conversations = len({episode.conv_id or episode.episode_id for episode in episodes})
    kept: list[str] = []
    for label in candidates:
        if explicit_haystack and _task_type_is_mentioned(label, explicit_haystack):
            kept.append(label)
            continue

        supporting_conversations: set[str] = set()
        supporting_episodes: set[str] = set()
        explicit_episode_signal = False
        for episode in episodes:
            text = _task_type_support_text(episode)
            if not _task_type_is_mentioned(label, text):
                continue
            supporting_episodes.add(episode.episode_id)
            supporting_conversations.add(episode.conv_id or episode.episode_id)
            if _task_type_has_explicit_stability_signal(text):
                explicit_episode_signal = True

        support_episode_count = len(supporting_episodes)
        support_conversation_count = len(supporting_conversations)
        episode_ratio = support_episode_count / total_episodes if total_episodes else 0.0
        conversation_ratio = support_conversation_count / total_conversations if total_conversations else 0.0
        strong_absolute_support = support_conversation_count >= 2 or support_episode_count >= 3
        small_sample_ratio_support = (
            1 <= total_episodes <= 12
            and support_episode_count >= 1
            and (episode_ratio >= 0.1 or conversation_ratio >= 0.2)
        )

        if explicit_episode_signal or strong_absolute_support or small_sample_ratio_support:
            kept.append(label)

    return kept[:3]


def _infer_primary_task_types_fallback(
    episodes: list[EpisodicMemory],
    projects: list[ProjectMemory],
    workflows: list[WorkflowMemory],
    existing: list[str] | None = None,
) -> list[str]:
    candidates = [
        *[str(value) for value in existing or []],
        *_infer_primary_task_type_candidates(episodes, projects, workflows),
    ]
    return _stable_primary_task_types(candidates, episodes, projects)


def _infer_primary_task_types(
    llm: LLMClient,
    episodes: list[EpisodicMemory],
    projects: list[ProjectMemory],
    workflows: list[WorkflowMemory],
    existing: list[str] | None = None,
) -> list[str]:
    seed_candidates = [
        *[str(value) for value in existing or []],
        *_infer_primary_task_type_candidates(episodes, projects, workflows),
    ]
    stable_existing = _stable_primary_task_types(seed_candidates, episodes, projects)
    if not stable_existing:
        return []

    episode_evidence = []
    for episode in episodes[-12:]:
        episode_evidence.append(
            {
                "topic": episode.topic,
                "summary": episode.summary,
                "key_decisions": episode.key_decisions[:3],
                "open_issues": episode.open_issues[:2],
                "relates_to_projects": episode.relates_to_projects[:3],
            }
        )

    project_evidence = []
    for project in projects[:8]:
        project_evidence.append(
            {
                "name": project.project_name,
                "goal": project.project_goal,
                "stage": project.current_stage,
                "next_actions": [entry.text for entry in project.next_actions[:3]],
            }
        )

    workflow_evidence = []
    for workflow in workflows[:8]:
        workflow_evidence.append(
            {
                "name": workflow.workflow_name,
                "trigger": workflow.trigger_condition,
                "steps": workflow.typical_steps[:3],
            }
        )

    system_prompt = (
        "你是一个用户任务习惯归纳器。"
        "请根据 episodic、project、workflow 证据，归纳用户最常见、最稳定的任务类型。"
        "任务类型必须是宽泛、可复用的类别，而不是项目名、研究主题或一次性问题。"
        "任务类型要描述反复出现的动作方式，不要包含具体对象、商品、地点、饮品、衣物、论文、模型或数据集。"
        "如果证据只是一次具体咨询，应归并为更宽泛的动作类型，或直接忽略。"
        "必须主动合并近义项，不要把同一类习惯拆成多个相近标签。"
        "标签必须来自证据中体现的长期使用习惯，不要根据单个关键词强行命名。"
        "输出数量控制在 1 到 3 个。"
        "使用自然、简洁的中文短标签。"
        "示例风格：研究规划、文档写作、资料分析、生活建议；这些只是粒度参考，不是固定备选项。"
        "只返回严格 JSON：{\"task_types\": [\"...\", \"...\"]}"
    )
    user_prompt = json.dumps(
        {
            "existing": existing or [],
            "episodes": episode_evidence,
            "projects": project_evidence,
            "workflows": workflow_evidence,
        },
        ensure_ascii=False,
        indent=2,
    )

    try:
        result = llm.extract_json(system_prompt, user_prompt)
    except Exception:
        result = {}

    normalized: list[str] = []
    if isinstance(result, dict):
        for value in result.get("task_types", []) or []:
            normalized.append(str(value))

    deduped = _stable_primary_task_types(normalized, episodes, projects)
    if deduped:
        return deduped
    return stable_existing


def _merge_project_focus_into_profile(profile: ProfileMemory, projects: list[ProjectMemory]) -> ProfileMemory:
    focus_candidates = list(profile.long_term_research_or_work_focus or [])
    source_episode_ids = list(profile.source_episode_ids or [])
    source_turn_refs = list(profile.source_turn_refs or [])
    stable_project_focuses: list[str] = []
    stable_project_texts: list[str] = []

    for project in projects:
        if not getattr(project, "is_active", True):
            continue
        project_episode_ids = [str(ref).strip() for ref in (project.source_episode_ids or []) if str(ref).strip()]
        if len(project_episode_ids) < 2:
            continue
        focus = str(project.project_name or project.project_goal or "").strip()
        if focus:
            stable_project_focuses.append(focus)
            stable_project_texts.append(
                " ".join(
                    str(part or "").strip()
                    for part in [
                        project.project_name,
                        project.project_goal,
                        project.current_stage,
                        " ".join(str(key) for key in (project.key_terms or {}).keys()),
                        " ".join(str(value) for value in (project.key_terms or {}).values()),
                    ]
                    if str(part or "").strip()
                )
            )
        for ref in project_episode_ids:
            if ref not in source_episode_ids:
                source_episode_ids.append(ref)
        for turn_ref in project.source_turn_refs or []:
            turn_ref = str(turn_ref).strip()
            if turn_ref and turn_ref not in source_turn_refs:
                source_turn_refs.append(turn_ref)
        if project.created_at and (not profile.created_at or project.created_at < profile.created_at):
            profile.created_at = project.created_at
        if project.updated_at and (not profile.updated_at or project.updated_at > profile.updated_at):
            profile.updated_at = project.updated_at

    if stable_project_texts:
        focus_candidates = [
            focus
            for focus in focus_candidates
            if not _focus_overlaps_project(focus, stable_project_texts)
        ]
        focus_candidates.extend(stable_project_focuses)
    profile.long_term_research_or_work_focus = _unique_string_list(focus_candidates, max_items=6)
    profile.source_episode_ids = source_episode_ids
    profile.source_turn_refs = source_turn_refs
    return profile


def _focus_overlaps_project(focus: str, project_texts: list[str]) -> bool:
    focus_tokens = _memory_text_tokens(focus)
    if len(focus_tokens) < 2:
        return False
    for project_text in project_texts:
        project_tokens = _memory_text_tokens(project_text)
        if not project_tokens:
            continue
        overlap = focus_tokens & project_tokens
        if len(overlap) >= 2 and len(overlap) / max(1, min(len(focus_tokens), len(project_tokens))) >= 0.45:
            return True
    return False


def _memory_text_tokens(text: str) -> set[str]:
    raw = str(text or "").lower()
    for phrase in re.findall(r"\b[a-z0-9]+(?:[-_/][a-z0-9]+)+\b", raw):
        parts = [part for part in re.split(r"[-_/]+", phrase) if part]
        if len(parts) >= 2:
            raw += " " + " ".join(parts)
            acronym = "".join("2" if part == "to" else part[0] for part in parts if part)
            if len(acronym) >= 2:
                raw += f" {acronym}"
    tokens = {token for token in re.findall(r"[a-z0-9]+", raw) if len(token) >= 2}
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", raw))
    stopwords = {
        "project",
        "platform",
        "system",
        "user",
        "memory",
        "统一",
        "项目",
        "平台",
        "用户",
        "记忆",
    }
    return {token for token in tokens if token not in stopwords}


def _extract_ordered_steps_from_text(text: str) -> list[str]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    explicit_steps: list[str] = []
    for line in lines:
        if re.match(r"^(\d+[.)、]|[-*•]|第[一二三四五六七八九十0-9]+步)", line):
            explicit_steps.append(re.sub(r"^(\d+[.)、]|[-*•]|第[一二三四五六七八九十0-9]+步)\s*", "", line).strip())
    if explicit_steps:
        return _unique_string_list(explicit_steps, max_items=8)

    sentence_chunks = re.split(r"[。；;]\s*|\n+", str(text or ""))
    candidate_steps = [
        chunk.strip()
        for chunk in sentence_chunks
        if 4 <= len(chunk.strip()) <= 80
    ]
    return _unique_string_list(candidate_steps, max_items=6)


def _platform_workflows_from_records(settings: dict[str, Any]) -> list[WorkflowMemory]:
    workflows: list[WorkflowMemory] = []
    for record in load_platform_memory_records(settings):
        record_id = str(record.get("record_id") or record.get("signature") or "platform_memory").strip()
        agent = record.get("agent_config")
        if not isinstance(agent, dict):
            continue
        name = str(agent.get("name") or record.get("agent_name") or record.get("title") or "").strip()
        instructions = str(agent.get("instructions") or "").strip()
        steps = _extract_ordered_steps_from_text(instructions)
        if not steps:
            starter_steps = [str(item).strip() for item in agent.get("conversation_starters", []) if str(item).strip()]
            steps = _unique_string_list(starter_steps, max_items=6)
        starter_list = [str(item).strip() for item in agent.get("conversation_starters", []) if str(item).strip()]
        workflow = WorkflowMemory(
            workflow_name=name,
            trigger_condition=str(agent.get("description") or (starter_list[0] if starter_list else "当用户需要执行该平台流程")).strip(),
            typical_steps=steps,
            preferred_artifact_format="平台配置流程",
            review_style=str(agent.get("description") or "").strip(),
            escalation_rule="如平台配置发生变化，以平台原始配置为准复核",
            reuse_frequency="per-project",
            occurrence_count=max(int(record.get("capture_count", 1) or 1), 3),
        )
        if not _looks_like_stable_workflow(workflow):
            continue
        workflow.add_evidence("l1_signal", record_id, str(record.get("summary") or name)[:120])
        workflows.append(workflow)
    return workflows


def _platform_skills_from_records(settings: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for record in load_platform_memory_records(settings):
        agent = record.get("agent_config")
        if isinstance(agent, dict):
            agent_title = str(agent.get("name") or record.get("agent_name") or record.get("title") or "").strip()
            agent_steps = _extract_ordered_steps_from_text(str(agent.get("instructions") or ""))
            agent_goal = str(agent.get("description") or "").strip()
            starter_list = [str(item).strip() for item in agent.get("conversation_starters", []) if str(item).strip()]
            agent_trigger = starter_list[0] if starter_list else f"当用户需要执行 {agent_title} 对应流程时"
            if _is_concrete_skill_record(
                title=agent_title,
                trigger=agent_trigger,
                goal=agent_goal or agent_title,
                steps=agent_steps,
                output_format="平台 Agent 执行结果",
            ):
                skills.append(
                    {
                        "id": f"platform_agent:{agent_title}",
                        "title": agent_title,
                        "description": agent_goal or f"从平台 Agent 配置导入的可复用能力：{agent_title}",
                        "kind": "skill",
                        "trigger": agent_trigger,
                        "goal": agent_goal or f"复用 {agent_title} 这项 Agent 能力",
                        "steps": agent_steps,
                        "output_format": "平台 Agent 执行结果",
                        "guardrails": ["优先遵循平台原始 Agent 配置"],
                        "source_types": ["agent_config", "platform_memory"],
                        "confidence": "high",
                        "selected": False,
                    }
                )
        for item in record.get("platform_skills", []) or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("name") or "").strip()
            steps = [str(step).strip() for step in item.get("steps", []) if str(step).strip()]
            summary = str(item.get("summary") or "").strip()
            trigger = str(item.get("trigger") or f"当用户需要执行 {title} 时").strip()
            output_format = str(item.get("output_format") or "结构化执行结果").strip()
            if not steps:
                steps = _extract_ordered_steps_from_text(summary)
            if not _is_concrete_skill_record(
                title=title,
                trigger=trigger,
                goal=summary or title,
                steps=steps,
                output_format=output_format,
            ):
                continue
            skills.append(
                {
                    "id": f"platform_skill:{title}",
                    "title": title,
                    "description": summary or f"从平台记忆导入的正式 skill：{title}",
                    "kind": "skill",
                    "trigger": trigger,
                    "goal": summary or f"复用 {title} 这项平台能力",
                    "steps": steps,
                    "output_format": output_format,
                    "guardrails": ["优先遵循平台原始 skill 配置"],
                    "source_types": ["platform_skill", "platform_memory"],
                    "confidence": "high",
                    "selected": False,
                }
            )
    return skills


def _extract_catalog_skill_summary(item: dict[str, Any]) -> str:
    reference_md = str(item.get("reference_md_content") or "").strip()
    if reference_md:
        lines = reference_md.splitlines()
        for idx, line in enumerate(lines):
            if line.strip().lower() == "## summary":
                for next_line in lines[idx + 1:]:
                    clean = next_line.strip()
                    if not clean or clean.startswith("#") or clean.startswith("```"):
                        continue
                    if "name:" in clean.lower() or "description:" in clean.lower():
                        continue
                    return clean[:240]
                break
    skill_md = str(item.get("skill_md_content") or "").strip()
    natural = _extract_natural_paragraph(skill_md)
    if natural:
        return natural[:240]
    return ""


def _build_recommended_display_text(item: dict[str, Any]) -> tuple[str, str, str]:
    title = str(item.get("title") or "").strip() or "未命名 Skill"
    title_l = title.lower()
    text = " ".join([
        title,
        str(item.get("goal") or ""),
        str(item.get("trigger") or ""),
        str(item.get("description") or ""),
        str(item.get("catalog_summary") or ""),
        *[str(step) for step in item.get("steps", [])],
    ]).lower()
    mappings = [
        (("pdf",), "PDF 文档处理", "提取文档结构、关键信息与引用证据", "结构化摘要 / 要点清单"),
        (("docx", "word"), "Word 文档处理", "整理、改写并输出可复用的文档内容", "文档草稿 / 修订稿"),
        (("ppt", "pptx", "slides"), "PPT 演示稿处理", "提炼演示结构并生成可展示内容", "演示大纲 / 幻灯片草稿"),
        (("english rewriter",), "英文改写润色", "把中文或生硬英文改成自然、专业、可发送的英文", "英文邮件 / 英文文本"),
        (("llm-powered", "claude"), "Claude 应用开发", "构建基于 Claude 的应用流程、提示词与调用方案", "开发说明 / 实现方案"),
        (("algorithmic", "art"), "算法艺术创作", "把生成规则转成可执行的视觉创作方案", "创作方案 / 视觉稿"),
        (("brand", "styling"), "品牌风格套用", "按既定品牌风格改写文案与视觉说明", "品牌化文案 / 风格说明"),
        (("doc co-authoring", "co-authoring"), "文档协作写作", "多人协作整理文档内容并统一结构与语气", "协作文档 / 修订建议"),
        (("frontend", "design"), "前端界面设计", "规划界面结构、风格方向与实现要点", "界面方案 / 设计说明"),
        (("canvas", "design"), "画布视觉设计", "生成适合画布场景的视觉构图与设计说明", "视觉方案 / 设计稿"),
        (("internal", "comms"), "内部沟通写作", "整理适合团队内部传播的说明、同步与 FAQ 文案", "内部公告 / 沟通稿"),
        (("mcp", "server"), "MCP 服务开发", "创建或整理 MCP 服务的实现、配置与调试步骤", "开发步骤 / 配置说明"),
        (("api",), "API 集成说明", "整理接口接入方式、参数与调用步骤", "接入说明 / 示例代码"),
        (("web", "application", "testing"), "Web 应用测试", "测试本地 Web 应用并输出可复现的问题与修复建议", "测试步骤 / 调试建议"),
        (("web", "artifacts", "builder"), "Web 组件构建", "搭建可交互的 Web 页面或小型应用原型", "页面原型 / 实现说明"),
        (("requirements", "outputs"), "输出要求整理", "把任务要求转成清晰、可检查的输出规范", "输出规范 / 检查清单"),
        (("skill", "creator"), "技能设计", "把能力整理成可复用的技能结构与说明", "技能草案 / 结构说明"),
        (("theme", "factory"), "主题风格生成", "生成一套统一的主题风格和配色说明", "主题方案 / 配色说明"),
        (("slack", "gif"), "Slack GIF 生成", "根据场景生成适合团队沟通的 GIF 创意与制作说明", "GIF 方案 / 制作步骤"),
        (("code", "review"), "代码审查", "检查实现风险、行为问题与改进点", "审查意见 / 修改建议"),
        (("bug", "debug", "troubleshoot"), "问题排查", "定位问题原因并整理修复步骤", "排查结论 / 修复建议"),
        (("plan", "planning", "roadmap"), "任务规划", "把目标拆成可执行的计划与优先级", "行动计划 / 拆解清单"),
        (("research", "paper", "literature"), "文献分析", "梳理论文重点、方法差异与结论", "文献总结 / 对比结论"),
        (("email", "communication", "comms"), "沟通写作", "整理适合发送的沟通文本与说明", "邮件草稿 / 沟通稿"),
    ]
    for keywords, mapped_title, short_desc, output in mappings:
        if any(keyword in title_l for keyword in keywords) or all(keyword in text for keyword in keywords):
            return mapped_title, short_desc, output
    goal = str(item.get("goal") or "").strip()
    output_format = str(item.get("output_format") or "").strip() or "结构化结果"
    short_desc = str(item.get("catalog_summary") or "").strip() or goal or str(item.get("description") or "").strip()
    if short_desc:
        lowered = short_desc.lower()
        if "llm-powered" in lowered or "claude" in lowered:
            title = "Claude 应用开发"
            short_desc = "构建基于 Claude 的应用能力与调用流程"
            output_format = "开发说明 / 实现方案"
        elif "brand" in lowered and "style" in lowered:
            title = "品牌风格套用"
            short_desc = "按品牌规范整理视觉与文案风格"
            output_format = "品牌化文案 / 风格说明"
        elif "document" in lowered or "co-author" in lowered:
            title = "文档协作写作"
            short_desc = "协助多人共同撰写、整理和修订文档"
            output_format = "协作文档 / 修订建议"
        elif "mcp" in lowered:
            short_desc = "创建、配置并调试 MCP 服务"
            output_format = "开发步骤 / 配置说明"
        elif "web" in lowered and "application" in lowered and "testing" in lowered:
            title = "Web 应用测试"
            short_desc = "测试本地 Web 应用并输出可复现的问题与修复建议"
            output_format = "测试步骤 / 调试建议"
        elif "web" in lowered and "artifacts" in lowered:
            title = "Web 组件构建"
            short_desc = "搭建可交互的 Web 页面或小型应用原型"
            output_format = "页面原型 / 实现说明"
        elif "requirements" in lowered and "outputs" in lowered:
            title = "输出要求整理"
            short_desc = "把任务要求转成清晰、可检查的输出规范"
            output_format = "输出规范 / 检查清单"
        elif "skill" in lowered and "creator" in lowered:
            title = "技能设计"
            short_desc = "把能力整理成可复用的技能结构与说明"
            output_format = "技能草案 / 结构说明"
        elif "theme" in lowered and "factory" in lowered:
            title = "主题风格生成"
            short_desc = "生成一套统一的主题风格和配色说明"
            output_format = "主题方案 / 配色说明"
        elif "slack" in lowered and "gif" in lowered:
            title = "Slack GIF 生成"
            short_desc = "根据场景生成适合团队沟通的 GIF 创意与制作说明"
            output_format = "GIF 方案 / 制作步骤"
        elif "frontend" in lowered:
            title = "前端界面设计"
            short_desc = "规划前端界面结构、交互和设计方向"
            output_format = "界面方案 / 设计说明"
        elif "canvas" in lowered:
            title = "画布视觉设计"
            short_desc = "生成适合画布场景的视觉设计方案"
            output_format = "视觉方案 / 设计稿"
        elif "internal" in lowered and "comms" in lowered:
            title = "内部沟通写作"
            short_desc = "撰写适合团队内部同步和传播的文案"
            output_format = "内部公告 / 沟通稿"
    if not short_desc:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ("test", "testing", "debug", "bug")):
            short_desc = "测试应用并整理问题与修复建议"
            output_format = output_format or "测试结果 / 修复建议"
        elif any(keyword in lowered for keyword in ("build", "builder", "prototype", "scaffold")):
            short_desc = "搭建原型或工作流，并整理实现步骤"
            output_format = output_format or "实现步骤 / 原型说明"
        elif any(keyword in lowered for keyword in ("write", "rewriter", "rewrite", "document", "doc")):
            short_desc = "整理、改写并输出可直接使用的文本内容"
            output_format = output_format or "文本草稿 / 修订稿"
        elif any(keyword in lowered for keyword in ("design", "ui", "ux", "theme", "brand")):
            short_desc = "整理设计方向、风格规范与实现说明"
            output_format = output_format or "设计说明 / 风格方案"
        elif any(keyword in lowered for keyword in ("api", "sdk", "integration", "mcp")):
            short_desc = "整理接入方式、配置步骤与调用说明"
            output_format = output_format or "接入说明 / 配置步骤"
        elif any(keyword in lowered for keyword in ("research", "paper", "literature")):
            short_desc = "梳理论文重点、方法差异与结论"
            output_format = output_format or "文献总结 / 对比结论"
        else:
            short_desc = "协助完成一类可复用任务"
            output_format = output_format or "结构化结果"
    short_desc = short_desc[:36]
    if not re.search(r"[\u4e00-\u9fff]", title):
        title = _humanize_remote_skill_title(title, str(item.get("folder_name") or ""), short_desc)
    return title, short_desc, output_format


def _normalize_skill_record(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    title = str(normalized.get("title") or "").strip()
    description = str(normalized.get("description") or "").strip()
    trigger = str(normalized.get("trigger") or "").strip()
    goal = str(normalized.get("goal") or "").strip()
    steps = [str(step).strip() for step in normalized.get("steps", []) if str(step).strip()]
    output_format = str(normalized.get("output_format") or "").strip()

    tags = [str(tag).strip().lower() for tag in normalized.get("tags", []) if str(tag).strip()]
    text = " ".join([title, description, trigger, goal, *steps, output_format, *tags]).lower()

    if not trigger:
        if "pdf" in text or "paper" in text or "document" in text:
            trigger = "需要阅读论文、PDF 或长文档时"
        elif "review" in text or "code" in text or "bug" in text or "debug" in text:
            trigger = "需要检查代码、排查 bug 或做技术审查时"
        elif "prd" in text or "product" in text or "project" in text or "plan" in text:
            trigger = "需要把需求或目标整理成计划与文档时"
        else:
            trigger = f"需要处理与{title}相关的任务时" if title else ""

    if not goal:
        goal = description[:64] if description else (f"完成与{title}相关的任务" if title else "")

    if len(steps) < 2:
        if "pdf" in text or "paper" in text or "document" in text:
            steps = ["识别文档结构", "提取关键结论与证据", "输出摘要或要点"]
            output_format = output_format or "摘要 / 要点清单"
        elif "review" in text or "code" in text or "bug" in text or "debug" in text:
            steps = ["确认问题上下文", "逐步检查关键风险或故障点", "输出结论与下一步建议"]
            output_format = output_format or "检查清单 / 修复建议"
        elif "prd" in text or "product" in text or "project" in text or "plan" in text:
            steps = ["澄清目标和边界", "拆解任务与优先级", "输出计划或文档初稿"]
            output_format = output_format or "计划草案 / 文档初稿"
        elif title:
            steps = ["澄清目标", "整理关键步骤", "输出结构化结果"]
            output_format = output_format or "结构化结果"

    normalized["trigger"] = trigger
    normalized["goal"] = goal
    normalized["steps"] = steps
    normalized["output_format"] = output_format
    if not normalized.get("description"):
        parts = []
        if trigger:
            parts.append(f"触发：{trigger}")
        if goal:
            parts.append(f"目标：{goal}")
        if output_format:
            parts.append(f"产出：{output_format}")
        if steps:
            parts.append(f"步骤：{'；'.join(steps[:3])}")
        normalized["description"] = " | ".join(parts[:4])
    display_title, display_summary, display_output = _build_recommended_display_text(normalized)
    normalized["display_title"] = display_title
    normalized["display_summary"] = display_summary
    normalized["display_output"] = display_output
    return normalized


def _valid_workflows(wiki: L2Wiki) -> list[WorkflowMemory]:
    return [workflow for workflow in wiki.load_workflows() if _looks_like_stable_workflow(workflow)]


def _valid_projects(wiki: L2Wiki) -> list[ProjectMemory]:
    return [project for project in wiki.list_projects() if _looks_like_stable_project(project)]


def conversation_signature(conv: RawConversation) -> str:
    payload = {
        "platform": conv.platform,
        "conv_id": conv.conv_id,
        "title": conv.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in conv.messages
        ],
        "turns": [
            {
                "turn_id": turn.turn_id,
                "message_ids": list(turn.message_ids or []),
            }
            for turn in (conv.turns or [])
        ],
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _raw_turn_messages(conv: RawConversation, turn_id: str) -> list[RawMessage]:
    id_to_message = {msg.msg_id: msg for msg in conv.messages}
    turn = next((item for item in conv.turns if item.turn_id == turn_id), None)
    if turn is None:
        return []
    return [
        id_to_message[msg_id]
        for msg_id in (turn.message_ids or [])
        if msg_id in id_to_message
    ]


def turn_signature(conv: RawConversation, turn_id: str) -> str:
    messages = _raw_turn_messages(conv, turn_id)
    payload = {
        "turn_id": turn_id,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for msg in messages
        ],
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def conversation_turn_signatures(conv: RawConversation) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for turn in conv.turns:
        turn_id = str(turn.turn_id or "").strip()
        if turn_id:
            signatures[turn_id] = turn_signature(conv, turn_id)
    return signatures


def load_l1_signals(settings: dict[str, Any]) -> tuple[L1SignalLayer, str]:
    l1_root = get_l1_root(settings, create=True)
    legacy_root = get_legacy_l1_root(settings)
    layer = L1SignalLayer()
    source_roots = [root for root in [l1_root, legacy_root] if root.exists()]
    if not source_roots:
        return layer, ""

    meaningful_parts: list[str] = []
    indexed_files: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for root in source_roots:
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            if path.name == "index.json":
                continue
            target_path = l1_root / path.name
            if root != l1_root and path.name not in seen_names and not target_path.exists():
                shutil.copy2(path, target_path)
            seen_names.add(path.name)
            try:
                signals = layer.load_file(target_path if target_path.exists() else path)
                meaningful = [sig for sig in signals if sig.is_meaningful()]
                if meaningful:
                    serialized = [
                        {
                            "type": sig.signal_type,
                            "platform": sig.platform,
                            "text": sig.text(),
                        }
                        for sig in meaningful
                    ]
                    meaningful_parts.append(
                        json.dumps(
                            {"file": path.name, "signals": serialized},
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                    indexed_files.append(
                        {
                            "record_id": (target_path if target_path.exists() else path).stem,
                            "file": path.name,
                            "platform": meaningful[0].platform if meaningful else "",
                            "signal_count": len(meaningful),
                            "signature": _hash_payload(serialized),
                            "updated_at": datetime.fromtimestamp((target_path if target_path.exists() else path).stat().st_mtime, tz=timezone.utc).isoformat(),
                            "source": root.name,
                        }
                    )
            except Exception:  # noqa: BLE001
                continue

    signature = hashlib.sha1("|".join(meaningful_parts).encode("utf-8")).hexdigest() if meaningful_parts else ""
    update_platform_memory_index(settings, indexed_files, signature)
    return layer, signature


def _display_entry_from_title_description(title: dict[str, Any], description: dict[str, Any]) -> dict[str, Any] | None:
    title_zh = _clean_daily_note_display_text(title.get("zh"), max_length=64)
    title_en = _clean_daily_note_display_text(title.get("en"), max_length=100)
    desc_zh = _clean_daily_note_display_text(description.get("zh"), max_length=140)
    desc_en = _clean_daily_note_display_text(description.get("en"), max_length=180)
    if not title_zh and not title_en:
        return None
    title_zh = title_zh or title_en
    title_en = title_en or title_zh
    desc_zh = desc_zh or title_zh
    desc_en = desc_en or title_en
    return _make_display_entry(
        title_zh=title_zh,
        title_en=title_en,
        desc_zh=desc_zh,
        desc_en=desc_en,
    )


def _display_entry_from_card(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    title = value.get("title")
    description = value.get("description")
    if not isinstance(title, dict) or not isinstance(description, dict):
        return None
    return _display_entry_from_title_description(title, description)


def _build_memory_display_with_llm(
    llm: LLMClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    system_prompt = (
        "You are the canonical frontend display generator for a memory picker UI.\n"
        "Given structured memory, generate concise card display copy for every provided item.\n"
        "Return ONLY strict JSON. Preserve item ids exactly. Use zh and en only.\n"
        "Each display card must have title.zh, title.en, description.zh, description.en.\n"
        "Profile and preference cards are checkbox keywords: title should be a high-level label, "
        "description should contain compact supporting detail.\n"
        "Projects, workflows, daily notes, and skills are phrase cards: title should be a normal short phrase, "
        "description should be a short user-facing summary.\n"
        "Do not expose internal ids, keys, field names, node/memory/episode/display labels, or backend status words.\n"
        "Do not surface assistant-only suggestions unless the user accepted or requested them.\n"
        "Do not write mechanical phrases like 待确认, 偏好待确认, pending, or X pending.\n"
        "For zh display, ordinary role labels, job titles, task labels, and UI-facing summaries "
        "must be natural Chinese. Do not generate English role labels such as group manager, "
        "team lead, manager, lead, researcher, engineer, designer, or product manager unless the "
        "exact English phrase appears in user-authored evidence as an official title or preferred wording.\n"
        "Chinese titles should usually be 6 to 18 Chinese characters and never exceed 24. "
        "Chinese descriptions should usually be 12 to 28 Chinese characters and never exceed 36 when possible.\n"
        "Preserve proper nouns and domain-specific terms in their original language when clearer.\n"
        "Before returning, silently self-check every card. Verify that the card is faithful to "
        "user-stated or user-accepted evidence, that it does not promote assistant-only advice "
        "or inferred labels into user memory, that it does not expose internal fields/status, "
        "and that the zh/en versions describe the same memory. If a card fails this check, "
        "revise it before returning. Do not include the self-check in the output."
    )
    user_prompt = (
        "Generate display cards for this memory payload.\n"
        "Return shape:\n"
        "{\n"
        '  "profile": {"item_id": {"title": {"zh": "", "en": ""}, "description": {"zh": "", "en": ""}}},\n'
        '  "preferences": {"item_id": {"title": {"zh": "", "en": ""}, "description": {"zh": "", "en": ""}}},\n'
        '  "projects": {"item_id": {"title": {"zh": "", "en": ""}, "description": {"zh": "", "en": ""}}},\n'
        '  "workflows": {"item_id": {"title": {"zh": "", "en": ""}, "description": {"zh": "", "en": ""}}},\n'
        '  "skills": {"item_id": {"title": {"zh": "", "en": ""}, "description": {"zh": "", "en": ""}}}\n'
        "}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    result = llm.extract_json(system_prompt, user_prompt)
    return result if isinstance(result, dict) else {}


def _project_display_payload(project: ProjectMemory) -> dict[str, Any]:
    return {
        "project_name": project.project_name,
        "project_goal": project.project_goal,
        "current_stage": project.current_stage,
        "finished_decisions": [entry.text for entry in project.finished_decisions[:4]],
        "unresolved_questions": [entry.text for entry in project.unresolved_questions[:4]],
        "important_constraints": [entry.text for entry in project.important_constraints[:4]],
        "next_actions": [entry.text for entry in project.next_actions[:4]],
    }


def _workflow_display_payload(workflow: WorkflowMemory) -> dict[str, Any]:
    return {
        "workflow_name": workflow.workflow_name,
        "trigger_condition": workflow.trigger_condition,
        "typical_steps": workflow.typical_steps[:5],
        "preferred_artifact_format": workflow.preferred_artifact_format,
        "review_style": workflow.review_style,
        "escalation_rule": workflow.escalation_rule,
        "reuse_frequency": workflow.reuse_frequency,
        "occurrence_count": workflow.occurrence_count,
    }


def _skill_display_payload(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": skill.get("title", ""),
        "description": skill.get("description", ""),
        "kind": skill.get("kind", ""),
        "trigger": skill.get("trigger", ""),
        "goal": skill.get("goal", ""),
        "steps": (skill.get("steps") or [])[:5],
        "output_format": skill.get("output_format", ""),
    }


def _cache_display_cards(category: str, raw_cards: Any) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    if not isinstance(raw_cards, dict):
        return cache
    for item_id, card in raw_cards.items():
        entry = _display_entry_from_card(card)
        if entry is not None:
            entry["source"] = "llm"
            cache[str(item_id)] = entry
    return cache


def _cache_fallback_display_entry(
    cache: dict[str, Any],
    category: str,
    item_id: str,
    *,
    title_zh: str,
    title_en: str = "",
    desc_zh: str = "",
    desc_en: str = "",
    source: str = "fallback",
) -> None:
    if item_id in cache.get(category, {}):
        return
    entry = _make_display_entry(
        title_zh=_frontend_display_text(title_zh, max_length=64),
        title_en=_frontend_display_text(title_en or title_zh, max_length=100),
        desc_zh=_frontend_display_text(desc_zh or title_zh, max_length=140),
        desc_en=_frontend_display_text(desc_en or desc_zh or title_en or title_zh, max_length=180),
    )
    entry["source"] = source
    cache.setdefault(category, {})[item_id] = entry


def _model_payload(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _display_source_payload(
    profile: Any,
    preferences: Any,
    projects: list[ProjectMemory] | None = None,
    workflows: list[WorkflowMemory] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    profile_payload = _model_payload(profile)
    preferences_payload = _model_payload(preferences)
    projects = projects or []
    workflows = workflows or []
    skills = skills or []

    profile_groups = []
    for group in _base_display_taxonomy("profile"):
        description, active_fields = _taxonomy_group_description(
            category="profile",
            payload=profile_payload,
            group=group,
            locale="zh",
        )
        group_id = str(group.get("group_id") or "").strip()
        if group_id == "long_term_focus":
            title = _taxonomy_title(group, "zh")
            for focus_label in _profile_long_term_focus_values(profile_payload):
                if _is_noise_memory_text(focus_label):
                    continue
                profile_groups.append({
                    "id": f"profile:long_term_research_or_work_focus:{_safe_slug(focus_label, 'item')}",
                    "group_id": group_id,
                    "label": title,
                    "description": focus_label,
                    "source_fields": ["long_term_research_or_work_focus"],
                })
            continue
        if group_id and description:
            profile_groups.append({
                "id": f"profile:group:{group_id}",
                "group_id": group_id,
                "label": _taxonomy_title(group, "zh"),
                "description": description,
                "source_fields": active_fields,
            })

    preference_groups = []
    for group in _base_display_taxonomy("preferences"):
        description, active_fields = _taxonomy_group_description(
            category="preferences",
            payload=preferences_payload,
            group=group,
            locale="zh",
        )
        group_id = str(group.get("group_id") or "").strip()
        if not group_id or not description:
            continue
        if group_id == "main_task_types":
            for task_type in _payload_field_value(preferences_payload, "primary_task_types", category="preferences") or []:
                task_label = str(task_type or "").strip()
                if task_label:
                    preference_groups.append({
                        "id": f"preferences:primary_task_types:{_safe_slug(task_label, 'item')}",
                        "group_id": group_id,
                        "label": _taxonomy_title(group, "zh"),
                        "description": task_label,
                        "source_fields": ["primary_task_types"],
                    })
            continue
        preference_groups.append({
            "id": f"preferences:group:{group_id}",
            "group_id": group_id,
            "label": _taxonomy_title(group, "zh"),
            "description": description,
            "source_fields": active_fields,
        })

    return {
        "profile": profile_groups,
        "preferences": preference_groups,
        "projects": [
            {"id": f"project:{project.project_name}", **_project_display_payload(project)}
            for project in projects
        ],
        "workflows": [
            {"id": f"workflow:{workflow.workflow_name}", **_workflow_display_payload(workflow)}
            for workflow in workflows
        ],
        "skills": [
            {"id": str(skill.get("id") or ""), **_skill_display_payload(skill)}
            for skill in skills
            if str(skill.get("id") or "").strip()
        ],
    }


def _fallback_display_cache_from_payload(
    display_payload: dict[str, Any],
    *,
    source: str = "fallback",
) -> dict[str, Any]:
    cache = {"profile": {}, "preferences": {}, "projects": {}, "workflows": {}, "skills": {}}
    for card in display_payload.get("profile", []) or []:
        _cache_fallback_display_entry(
            cache,
            "profile",
            str(card.get("id") or ""),
            title_zh=str(card.get("label") or ""),
            desc_zh=str(card.get("description") or ""),
            source=source,
        )
    for card in display_payload.get("preferences", []) or []:
        _cache_fallback_display_entry(
            cache,
            "preferences",
            str(card.get("id") or ""),
            title_zh=str(card.get("label") or ""),
            desc_zh=str(card.get("description") or ""),
            source=source,
        )
    for card in display_payload.get("projects", []) or []:
        item_id = str(card.get("id") or "").strip()
        if not item_id:
            continue
        _cache_fallback_display_entry(
            cache,
            "projects",
            item_id,
            title_zh=str(card.get("project_name") or ""),
            desc_zh=str(card.get("current_stage") or card.get("project_goal") or "项目记忆"),
            source=source,
        )
    for card in display_payload.get("workflows", []) or []:
        item_id = str(card.get("id") or "").strip()
        if not item_id:
            continue
        _cache_fallback_display_entry(
            cache,
            "workflows",
            item_id,
            title_zh=str(card.get("workflow_name") or ""),
            desc_zh=str(card.get("trigger_condition") or card.get("preferred_artifact_format") or "工作流 / SOP"),
            source=source,
        )
    for card in display_payload.get("skills", []) or []:
        item_id = str(card.get("id") or "").strip()
        if not item_id:
            continue
        _cache_fallback_display_entry(
            cache,
            "skills",
            item_id,
            title_zh=str(card.get("title") or ""),
            desc_zh=str(card.get("description") or ""),
            source=source,
        )
    return cache


def build_display_texts(
    llm: LLMClient,
    profile: Any,
    preferences: Any,
    projects: list[ProjectMemory] | None = None,
    workflows: list[WorkflowMemory] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    display_payload = _display_source_payload(profile, preferences, projects, workflows, skills)
    result = _build_memory_display_with_llm(llm, display_payload)

    profile_display = result.get("profile", {}) if isinstance(result.get("profile"), dict) else {}
    preferences_display = (
        result.get("preferences", {}) if isinstance(result.get("preferences"), dict) else {}
    )
    cache = {
        "profile": _cache_display_cards("profile", profile_display),
        "preferences": _cache_display_cards("preferences", preferences_display),
        "projects": _cache_display_cards("projects", result.get("projects", {})),
        "workflows": _cache_display_cards("workflows", result.get("workflows", {})),
        "skills": _cache_display_cards("skills", result.get("skills", {})),
    }

    fallback_cache = _fallback_display_cache_from_payload(display_payload, source="llm_fallback")
    for category, entries in fallback_cache.items():
        cache.setdefault(category, {})
        for item_id, entry in entries.items():
            cache[category].setdefault(item_id, entry)
    return cache


def build_display_fallback_texts(
    profile: Any,
    preferences: Any,
    projects: list[ProjectMemory] | None = None,
    workflows: list[WorkflowMemory] | None = None,
    skills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _fallback_display_cache_from_payload(
        _display_source_payload(profile, preferences, projects, workflows, skills)
    )


def _merge_display_cache(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base) if isinstance(base, dict) else {}
    for category in ["profile", "preferences", "projects", "workflows", "skills", "persistent"]:
        current = merged.get(category)
        if not isinstance(current, dict):
            current = {}
        incoming = updates.get(category)
        if isinstance(incoming, dict):
            current.update(incoming)
        merged[category] = current
    return merged


def _display_cache_missing_category(
    cache: dict[str, Any],
    category: str,
    expected_ids: list[str],
    *,
    include_fallback: bool = False,
) -> bool:
    if not expected_ids:
        return False
    category_cache = cache.get(category)
    if not isinstance(category_cache, dict):
        return True
    for item_id in expected_ids:
        entry = category_cache.get(item_id)
        if not isinstance(entry, dict):
            return True
        if include_fallback and entry.get("source") == "fallback":
            return True
    return False


def ensure_display_cache_for_category(
    settings: dict[str, Any],
    category: str,
    *,
    refresh_display: bool = False,
) -> dict[str, Any]:
    category = "daily_notes" if category == "persistent" else category
    cache = load_display_texts(settings)
    if category == "daily_notes":
        return cache

    wiki = get_wiki(settings)
    profile = wiki.load_profile()
    prefs = wiki.load_preferences()
    projects = _valid_projects(wiki) if category == "projects" else []
    workflows = _valid_workflows(wiki) if category == "workflows" else []
    skills = derive_my_skills(settings) if category == "skills" else []

    if category == "profile":
        source_payload = _display_source_payload(profile, prefs, [], [], [])
        expected_ids = [str(item.get("id") or "") for item in source_payload.get("profile", []) if item.get("id")]
    elif category == "preferences":
        prefs_payload = prefs.model_dump(mode="json") if prefs else _preferences_payload_fallback(settings)
        prefs = prefs_payload
        source_payload = _display_source_payload(profile, prefs_payload, [], [], [])
        expected_ids = [str(item.get("id") or "") for item in source_payload.get("preferences", []) if item.get("id")]
    elif category == "projects":
        expected_ids = [f"project:{project.project_name}" for project in projects]
    elif category == "workflows":
        expected_ids = [f"workflow:{workflow.workflow_name}" for workflow in workflows]
    elif category == "skills":
        expected_ids = [str(skill.get("id") or "") for skill in skills if str(skill.get("id") or "").strip()]
    else:
        return cache

    needs_missing_fill = _display_cache_missing_category(cache, category, expected_ids)
    needs_llm_refresh = refresh_display and _display_cache_missing_category(
        cache,
        category,
        expected_ids,
        include_fallback=True,
    )
    if not needs_missing_fill and not needs_llm_refresh:
        return cache

    if needs_llm_refresh:
        update = build_display_texts(
            get_llm(settings),
            profile if category in {"profile", "preferences"} else None,
            prefs if category in {"profile", "preferences"} else None,
            projects=projects,
            workflows=workflows,
            skills=skills,
        )
    else:
        update = build_display_fallback_texts(
            profile if category in {"profile", "preferences"} else None,
            prefs if category in {"profile", "preferences"} else None,
            projects=projects,
            workflows=workflows,
            skills=skills,
        )
    cache = _merge_display_cache(cache, update)
    save_display_texts(settings, cache)
    return cache


def get_llm(settings: dict[str, Any]) -> LLMClient:
    api_key = settings.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="请先在设置页配置 API Key")
    base_url = str(settings.get("api_base_url") or "").strip()
    model = str(settings.get("api_model") or "").strip()
    return LLMClient(
        api_key=api_key,
        model=model or "deepseek-chat",
        backend=str(settings.get("api_provider") or "openai_compat"),
        base_url=base_url or "https://api.deepseek.com/v1",
    )


def read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def count_json_files(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return len(list(path.glob("*.json")))


def count_raw_conversations(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return len([file for file in path.rglob("*.json") if file.is_file()])


def build_summary(settings: dict[str, Any]) -> SummaryResponse:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)
    episodes_dir = root / "episodes"
    raw_dir = root / "raw"

    profile_count = len(memory_items_for_category(settings, "profile"))
    preferences_count = len(memory_items_for_category(settings, "preferences"))

    workflows_count = len(_valid_workflows(wiki))

    projects_count = len(_valid_projects(wiki))
    episodes_count = len(wiki.list_episodes())
    raw_count = count_raw_conversations(raw_dir)

    persistent_data = load_persistent_nodes(settings)
    persistent_count = (
        len((persistent_data or {}).get("nodes", {}))
        if isinstance(persistent_data, dict)
        else 0
    )

    breakdown = {
        "profile": profile_count,
        "preferences": preferences_count,
        "workflows": workflows_count,
        "projects": projects_count,
        "persistent": persistent_count,
        "episodes": episodes_count,
        "raw_conversations": raw_count,
    }

    return SummaryResponse(
        last_sync_at=settings.get("last_sync_at"),
        conversation_count=raw_count,
        memory_item_count=profile_count
        + preferences_count
        + workflows_count
        + projects_count
        + persistent_count,
        sync_enabled=bool(settings.get("keep_updated")),
        breakdown=breakdown,
    )


def build_memory_categories(settings: dict[str, Any], locale: str | None = None) -> list[dict[str, Any]]:
    summary = build_summary(settings)
    labels = CATEGORY_LABELS.get(_locale_bucket(locale), CATEGORY_LABELS["en"])
    return [
        {"id": "profile", "label": labels["profile"], "count": summary.breakdown["profile"]},
        {"id": "preferences", "label": labels["preferences"], "count": summary.breakdown["preferences"]},
        {"id": "projects", "label": labels["projects"], "count": summary.breakdown["projects"]},
        {"id": "workflows", "label": labels["workflows"], "count": summary.breakdown["workflows"]},
        {"id": "daily_notes", "label": labels["daily_notes"], "count": summary.breakdown["persistent"]},
    ]


def _default_persistent_payload() -> dict[str, Any]:
    return {
        "version": "1.1",
        "pn_next_id": 1,
        "episodic_tag_paths": [],
        "nodes": {},
        "deleted_node_locks": [],
        "ignored_episode_ids": [],
        "ignored_turn_refs": [],
    }


def _persistent_root(root: Path) -> Path:
    return root / "daily_notes"


def _legacy_interest_discoveries_root(root: Path) -> Path:
    return root / "interest_discoveries"


def _readable_persistent_root(root: Path) -> Path:
    current = _persistent_root(root)
    if current.exists():
        return current
    legacy = _legacy_interest_discoveries_root(root)
    if legacy.exists():
        try:
            legacy.rename(current)
            return current
        except OSError:
            pass
        return legacy
    return current


def _persistent_index_path(root: Path) -> Path:
    return _persistent_root(root) / "index.json"


def _readable_persistent_index_path(root: Path) -> Path:
    return _readable_persistent_root(root) / "index.json"


def _legacy_persistent_path(root: Path) -> Path:
    return root / "js_persistent_nodes.json"


def _persistent_node_dir(root: Path, node_id: str) -> Path:
    return _persistent_root(root) / node_id


def _persistent_node_markdown(node_id: str, node: dict[str, Any]) -> str:
    lines = [f"# {node.get('description') or node.get('key') or node_id}", ""]
    lines.append(f"- ID: `{node_id}`")
    if node.get("type"):
        lines.append(f"- 类型: `{node.get('type')}`")
    if node.get("key"):
        lines.append(f"- 键: `{node.get('key')}`")
    if node.get("confidence"):
        lines.append(f"- 置信度: `{node.get('confidence')}`")
    if node.get("export_priority"):
        lines.append(f"- 导出优先级: `{node.get('export_priority')}`")
    if node.get("platform"):
        lines.append(f"- 平台: {', '.join(str(item) for item in node.get('platform', []) if str(item).strip())}")
    if node.get("episode_refs"):
        lines.append(f"- Episode 引用: {', '.join(str(item) for item in node.get('episode_refs', []) if str(item).strip())}")
    if node.get("turn_refs"):
        lines.append(f"- Turn 引用: {', '.join(str(item) for item in node.get('turn_refs', []) if str(item).strip())}")
    display_entry = _node_display_entry(node, str(node.get("description") or node.get("key") or node_id))
    if display_entry:
        display_title = _display_text(display_entry.get("title"), "zh", "")
        display_description = _display_text(display_entry.get("description"), "zh", "")
        if display_title:
            lines.append(f"- 前端标题: {display_title}")
        if display_description:
            lines.append(f"- 前端摘要: {display_description}")
    if node.get("created_at"):
        lines.append(f"- 创建时间: `{node.get('created_at')}`")
    if node.get("updated_at"):
        lines.append(f"- 更新时间: `{node.get('updated_at')}`")
    lines.append("")
    lines.append("## 描述")
    lines.append(str(node.get("description") or "").strip() or "暂无描述")
    lines.append("")
    return "\n".join(lines)


def _load_persistent_nodes_from_directory(root: Path) -> dict[str, Any]:
    persistent_root = _readable_persistent_root(root)
    index_path = _readable_persistent_index_path(root)
    payload = _default_persistent_payload()
    if not persistent_root.exists():
        return payload

    index_data = read_json_file(index_path)
    if isinstance(index_data, dict):
        payload["version"] = index_data.get("version", payload["version"])
        payload["pn_next_id"] = index_data.get("pn_next_id", payload["pn_next_id"])
        payload["episodic_tag_paths"] = index_data.get("episodic_tag_paths", payload["episodic_tag_paths"])
        locks = index_data.get("deleted_node_locks", [])
        if isinstance(locks, list):
            payload["deleted_node_locks"] = [lock for lock in locks if isinstance(lock, dict)]
        ignored_episode_ids = index_data.get("ignored_episode_ids", [])
        if isinstance(ignored_episode_ids, list):
            payload["ignored_episode_ids"] = [str(item).strip() for item in ignored_episode_ids if str(item or "").strip()]
        ignored_turn_refs = index_data.get("ignored_turn_refs", [])
        if isinstance(ignored_turn_refs, list):
            payload["ignored_turn_refs"] = [str(item).strip() for item in ignored_turn_refs if str(item or "").strip()]
        items = index_data.get("items", [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                node_id = str(item.get("id") or "").strip()
                if not node_id:
                    continue
                payload["nodes"][node_id] = {k: v for k, v in item.items() if k != "id"}

    for node_json in sorted(persistent_root.glob("*/node.json")):
        node_data = read_json_file(node_json)
        if not isinstance(node_data, dict):
            continue
        node_id = str(node_data.get("id") or node_json.parent.name).strip()
        if not node_id:
            continue
        payload["nodes"][node_id] = {k: v for k, v in node_data.items() if k != "id"}

    if payload["nodes"]:
        pn_next = payload.get("pn_next_id", 1)
        highest = 0
        for node_id in payload["nodes"]:
            match = re.search(r"(\d+)$", node_id)
            if match:
                highest = max(highest, int(match.group(1)))
        payload["pn_next_id"] = max(int(pn_next or 1), highest + 1)
    return payload


def load_persistent_nodes(settings: dict[str, Any]) -> dict[str, Any]:
    root = get_storage_root(settings)
    directory_data = _load_persistent_nodes_from_directory(root)
    if directory_data.get("nodes") or directory_data.get("deleted_node_locks"):
        return directory_data
    data = read_json_file(_legacy_persistent_path(root))
    if isinstance(data, dict):
        return data
    return _default_persistent_payload()


def memory_items_for_category(
    settings: dict[str, Any],
    category: str,
    locale: str | None = None,
    *,
    refresh_display: bool = False,
) -> list[dict[str, Any]]:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)
    display_cache = ensure_display_cache_for_category(
        settings,
        category,
        refresh_display=refresh_display,
    )

    if category == "projects":
        items = []
        for project in _valid_projects(wiki):
            item_id = f"project:{project.project_name}"
            description = project.current_stage or project.project_goal or "项目记忆"
            display_title, display_description = _display_cache_texts(
                display_cache,
                "projects",
                item_id,
                locale,
                fallback_title=project.project_name,
                fallback_description=project.project_goal or description,
            )
            items.append(
                _frontend_memory_item(
                    {
                        "id": item_id,
                        "title": display_title,
                        "description": display_description,
                        "display_title": display_title,
                        "display_description": display_description,
                        "selected": False,
                    },
                    category="projects",
                    fallback_title=project.project_name,
                    fallback_description=project.project_goal or description,
                )
            )
        return items

    if category == "workflows":
        items = []
        for workflow in _valid_workflows(wiki):
            item_id = f"workflow:{workflow.workflow_name}"
            fallback_description = workflow.trigger_condition or workflow.preferred_artifact_format or "工作流 / SOP"
            display_title, display_description = _display_cache_texts(
                display_cache,
                "workflows",
                item_id,
                locale,
                fallback_title=workflow.workflow_name,
                fallback_description=fallback_description,
            )
            items.append(
                _frontend_memory_item(
                    {
                        "id": item_id,
                        "title": display_title,
                        "description": display_description,
                        "display_title": display_title,
                        "display_description": display_description,
                        "selected": False,
                    },
                    category="workflows",
                    fallback_title=workflow.workflow_name,
                    fallback_description=fallback_description,
                )
            )
        return items

    if category in {"persistent", "daily_notes"}:
        persistent = load_persistent_nodes(settings)
        nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
        items = []
        for node_id, node in nodes.items():
            title = node.get("description") or node.get("key") or node_id
            if _is_noise_memory_text(title):
                continue
            item_id = f"daily_notes:{node_id}"
            display_entry = _get_persistent_display_entry(str(title), node)
            display_title, display_description = _daily_note_display_texts(
                node_id,
                node,
                display_entry,
                locale,
            )
            items.append(
                _frontend_memory_item(
                    {
                        "id": item_id,
                        "title": display_title,
                        "description": display_description,
                        "display_title": display_title,
                        "display_description": display_description,
                        "selected": False,
                    },
                    category="daily_notes",
                    fallback_title=str(title),
                    fallback_description=str(node.get("description") or title),
                )
            )
        return items

    if category == "profile":
        profile = wiki.load_profile()
        if profile:
            items = []
            profile_payload = profile.model_dump(mode="json")
            for group in _base_display_taxonomy("profile"):
                description, active_fields = _taxonomy_group_description(
                    category="profile",
                    payload=profile_payload,
                    group=group,
                    locale=locale,
                )
                if not description:
                    continue
                group_id = str(group.get("group_id") or "").strip()
                if not group_id:
                    continue
                title = _taxonomy_title(group, locale)
                if group_id == "long_term_focus":
                    for focus_label in _profile_long_term_focus_values(profile_payload):
                        if _is_noise_memory_text(focus_label):
                            continue
                        item_id = f"profile:long_term_research_or_work_focus:{_safe_slug(focus_label, 'item')}"
                        display_title = _frontend_display_text(title, max_length=64)
                        display_description = _frontend_display_text(focus_label, max_length=140)
                        items.append(
                            _frontend_memory_item(
                                {
                                    "id": item_id,
                                    "title": display_title,
                                    "description": display_description,
                                    "display_title": display_title,
                                    "display_description": display_description,
                                    "source_fields": ["long_term_research_or_work_focus"],
                                    "status": group.get("status", "active"),
                                    "selected": False,
                                },
                                category="profile",
                                fallback_title=title,
                                fallback_description=focus_label,
                            )
                        )
                    continue
                item_id = f"profile:group:{group_id}"
                display_title, display_description = _display_cache_texts(
                    display_cache,
                    "profile",
                    item_id,
                    locale,
                    fallback_title=title,
                    fallback_description=description,
                )
                items.append(
                    _frontend_memory_item(
                        {
                            "id": item_id,
                            "title": display_title,
                            "description": display_description,
                            "display_title": display_title,
                            "display_description": display_description,
                            "source_fields": active_fields,
                            "status": group.get("status", "active"),
                            "selected": False,
                        },
                        category="profile",
                        fallback_title=title,
                        fallback_description=description,
                    )
                )
            return items
        return []

    if category == "preferences":
        prefs = wiki.load_preferences()
        prefs_payload = prefs.model_dump(mode="json") if prefs else _preferences_payload_fallback(settings)
        if prefs_payload:
            items = []
            episodes = wiki.list_episodes()
            projects = _valid_projects(wiki)
            for group in _base_display_taxonomy("preferences"):
                description, active_fields = _taxonomy_group_description(
                    category="preferences",
                    payload=prefs_payload,
                    group=group,
                    locale=locale,
                    episodes=episodes,
                    projects=projects,
                )
                if not description:
                    continue
                group_id = str(group.get("group_id") or "").strip()
                if not group_id:
                    continue
                title = _taxonomy_title(group, locale)
                if group_id == "main_task_types":
                    task_types = _payload_field_value(
                        prefs_payload,
                        "primary_task_types",
                        category="preferences",
                        episodes=episodes,
                        projects=projects,
                    )
                    for task_type in task_types or []:
                        task_label = str(task_type or "").strip()
                        if not task_label or _is_noise_memory_text(task_label):
                            continue
                        item_id = f"preferences:primary_task_types:{_safe_slug(task_label, 'item')}"
                        display_title, display_description = _display_cache_texts(
                            display_cache,
                            "preferences",
                            item_id,
                            locale,
                            fallback_title=title,
                            fallback_description=task_label,
                        )
                        items.append(
                            _frontend_memory_item(
                                {
                                    "id": item_id,
                                    "title": display_title,
                                    "description": display_description,
                                    "display_title": display_title,
                                    "display_description": display_description,
                                    "source_fields": ["primary_task_types"],
                                    "status": group.get("status", "active"),
                                    "selected": False,
                                },
                                category="preferences",
                                fallback_title=title,
                                fallback_description=task_label,
                            )
                        )
                    continue
                item_id = f"preferences:group:{group_id}"
                display_title, display_description = _display_cache_texts(
                    display_cache,
                    "preferences",
                    item_id,
                    locale,
                    fallback_title=title,
                    fallback_description=description,
                )
                items.append(
                    _frontend_memory_item(
                        {
                            "id": item_id,
                            "title": display_title,
                            "description": display_description,
                            "display_title": display_title,
                            "display_description": display_description,
                            "source_fields": active_fields,
                            "status": group.get("status", "active"),
                            "selected": False,
                        },
                        category="preferences",
                        fallback_title=title,
                        fallback_description=description,
                    )
                )
            return items
        return []

    return []


def derive_my_skills(settings: dict[str, Any]) -> list[dict[str, Any]]:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)
    saved_ids = set(settings.get("saved_skill_ids", []))
    dismissed_ids = set(settings.get("dismissed_skill_ids", []))
    items: list[dict[str, Any]] = []
    preferences = wiki.load_preferences()
    preference_guardrails: list[str] = []
    if preferences:
        if preferences.language_preference:
            preference_guardrails.append(f"使用 {preferences.language_preference}")
        if preferences.response_granularity:
            preference_guardrails.append(f"回答粒度：{preferences.response_granularity}")
        preference_guardrails.extend(preferences.formatting_constraints[:2])
        preference_guardrails.extend(preferences.revision_preference[:2])

    def format_skill_description(
        *,
        trigger: str = "",
        goal: str = "",
        steps: list[str] | None = None,
        output_format: str = "",
        guardrails: list[str] | None = None,
    ) -> str:
        parts: list[str] = []
        if trigger:
            parts.append(f"触发：{trigger}")
        if goal:
            parts.append(f"目标：{goal}")
        if output_format:
            parts.append(f"产出：{output_format}")
        if steps:
            parts.append(f"步骤：{'；'.join(step for step in steps[:3] if step)}")
        if guardrails:
            parts.append(f"约束：{'；'.join(item for item in guardrails[:2] if item)}")
        return " | ".join(parts[:4]) or "从已整理 memory 中提炼出的可复用能力"

    for workflow in _valid_workflows(wiki)[:4]:
        skill_id = f"workflow:{workflow.workflow_name}"
        workflow_steps = [step for step in workflow.typical_steps if step]
        composed_skills = [step for step in workflow_steps[:3] if len(step) <= 24]
        if not _is_concrete_skill_record(
            title=workflow.workflow_name,
            trigger=workflow.trigger_condition,
            goal=workflow.review_style or workflow.workflow_name,
            steps=workflow_steps,
            output_format=workflow.preferred_artifact_format,
        ):
            continue
        items.append(
            {
                "id": skill_id,
                "title": workflow.workflow_name,
                "description": format_skill_description(
                    trigger=workflow.trigger_condition,
                    goal=workflow.review_style or workflow.workflow_name,
                    steps=workflow.typical_steps,
                    output_format=workflow.preferred_artifact_format,
                    guardrails=[workflow.escalation_rule, *preference_guardrails],
                ),
                "kind": "workflow",
                "trigger": workflow.trigger_condition,
                "goal": workflow.review_style or workflow.workflow_name,
                "steps": workflow_steps,
                "output_format": workflow.preferred_artifact_format,
                "guardrails": [workflow.escalation_rule, *preference_guardrails],
                "composition": {
                    "layer": "workflow",
                    "uses_skills": composed_skills,
                    "prompt_template": workflow.preferred_artifact_format or workflow.review_style or "",
                },
                "source_types": ["workflow"],
                "confidence": "high" if workflow.occurrence_count >= 3 else "medium",
                "selected": skill_id in saved_ids,
            }
        )

    for platform_skill in _platform_skills_from_records(settings):
        platform_skill["selected"] = platform_skill["id"] in saved_ids
        items.append(platform_skill)

    if len(items) < 5:
        active_projects = [project for project in _valid_projects(wiki) if project.is_active]
        for project in active_projects[: 5 - len(items)]:
            if not _project_can_derive_skill(project):
                continue
            skill_id = f"project:{project.project_name}"
            steps = [entry.text for entry in project.next_actions[:3]]
            if not steps:
                steps = [entry.text for entry in project.finished_decisions[:3]]
            if not _is_concrete_skill_record(
                title=f"{project.project_name} 推进",
                trigger=project.current_stage or "当用户需要推进该项目",
                goal=project.project_goal or f"把 {project.project_name} 往前推进",
                steps=steps,
                output_format="项目计划 / 决策建议",
            ):
                continue
            items.append(
                {
                    "id": skill_id,
                    "title": f"{project.project_name} 推进",
                    "description": format_skill_description(
                        trigger=project.current_stage or "当用户需要推进该项目",
                        goal=project.project_goal or f"把 {project.project_name} 往前推进",
                        steps=steps,
                        output_format="项目计划 / 决策建议",
                        guardrails=[entry.text for entry in project.important_constraints[:2]] + preference_guardrails,
                    ),
                    "kind": "skill",
                    "trigger": project.current_stage or "当用户需要推进该项目",
                    "goal": project.project_goal or f"把 {project.project_name} 往前推进",
                    "steps": steps,
                    "output_format": "项目计划 / 决策建议",
                    "guardrails": [entry.text for entry in project.important_constraints[:2]] + preference_guardrails,
                    "source_types": ["project"],
                    "confidence": "medium",
                    "selected": skill_id in saved_ids,
                }
            )

    persistent_nodes = load_persistent_nodes(settings).get("nodes", {})
    if len(items) < 6 and persistent_nodes:
        nodes = persistent_nodes
        episodes_by_id = {episode.episode_id: episode for episode in wiki.list_episodes()}
        for node_id, node in list(nodes.items()):
            if str(node.get("type") or "").strip().lower() != "workflow":
                continue
            refs = node.get("episode_refs", []) or []
            if len(refs) < 2:
                continue
            title = node.get("description") or node.get("key") or node_id
            if _is_noise_memory_text(title):
                continue
            evidence = [episodes_by_id[ep_id] for ep_id in refs if ep_id in episodes_by_id][:3]
            steps = []
            for ep in evidence:
                steps.extend(ep.key_decisions[:2] or ep.open_issues[:1])
            if not _is_concrete_skill_record(
                title=title,
                trigger=node.get("key") or "当用户提出类似长期任务",
                goal=node.get("description") or "复用长期稳定的方法",
                steps=steps,
                output_format="结构化建议 / 可执行步骤",
            ):
                continue
            skill_id = f"persistent:{node_id}"
            items.append(
                {
                    "id": skill_id,
                    "title": title,
                    "description": format_skill_description(
                        trigger=node.get("key") or "当用户提出类似长期任务",
                        goal=node.get("description") or "复用长期稳定的方法",
                        steps=steps,
                        output_format="结构化建议 / 可执行步骤",
                        guardrails=preference_guardrails,
                    ),
                    "kind": "skill",
                    "trigger": node.get("key") or "当用户提出类似长期任务",
                    "goal": node.get("description") or "复用长期稳定的方法",
                    "steps": steps,
                    "output_format": "结构化建议 / 可执行步骤",
                    "guardrails": preference_guardrails,
                    "source_types": ["persistent_node", "episodes"],
                    "confidence": "high" if len(refs) >= 3 else "medium",
                    "evidence_episode_ids": refs[:5],
                    "selected": skill_id in saved_ids,
                }
            )
            if len(items) >= 6:
                break

    if saved_ids:
        recommended_items, _ = rank_recommended_skills(settings)
        for item in recommended_items:
            if item.get("id") not in saved_ids or item.get("id") in dismissed_ids:
                continue
            saved_item = dict(item)
            saved_item["selected"] = True
            items.append(saved_item)

    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in items:
        title_key = item["title"].strip().lower()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(item)
    final_items = [item for item in deduped if item["id"] not in dismissed_ids][:6]
    skill_display_cache = load_display_texts(settings).get("skills", {})
    if isinstance(skill_display_cache, dict):
        for item in final_items:
            entry = skill_display_cache.get(item.get("id"))
            if not isinstance(entry, dict):
                continue
            display_title = _display_text(entry.get("title"), "zh", "")
            display_summary = _display_text(entry.get("description"), "zh", "")
            if display_title:
                item["display_title"] = display_title
            if display_summary:
                item["display_summary"] = display_summary
    save_skill_library(settings, final_items)
    return final_items


def raw_conversation_payload(conv: RawConversation) -> dict[str, Any]:
    return {
        "id": conv.conv_id,
        "conversation_id": conv.conv_id,
        "platform": conv.platform,
        "title": conv.title,
        "create_time": conv.start_time.isoformat() if conv.start_time else "",
        "update_time": conv.end_time.isoformat() if conv.end_time else "",
        "messages": [
            {
                "id": msg.msg_id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "conversation_id": conv.conv_id,
                "platform": conv.platform,
            }
            for msg in conv.messages
        ],
        "turns": [
            {
                "turn_id": turn.turn_id,
                "conversation_id": turn.conversation_id,
                "message_ids": list(turn.message_ids or []),
            }
            for turn in (conv.turns or [])
        ],
    }


def detect_primary_language(text: str) -> str:
    cjk_count = sum(1 for ch in str(text or "") if "\u4e00" <= ch <= "\u9fff")
    ascii_alpha_count = sum(1 for ch in str(text or "") if ("a" <= ch.lower() <= "z"))
    if cjk_count >= max(2, ascii_alpha_count // 3):
        return "zh"
    if ascii_alpha_count:
        return "en"
    return ""


def build_fallback_episode(
    conv: RawConversation,
    episode_id: str,
    *,
    turn_ref: str = "",
) -> EpisodicMemory:
    turn_messages = _raw_turn_messages(conv, turn_ref) if turn_ref else []
    preview_source = (
        "\n\n".join(f"[{message.role.upper()}]: {message.content}" for message in turn_messages)
        if turn_messages
        else conv.full_text()
    )
    preview = preview_source.strip().replace("\n", " ")
    if len(preview) > 220:
        preview = preview[:217] + "..."
    summary = preview or "该对话已记录，但自动提取摘要失败。"
    primary_language = detect_primary_language(preview_source)
    turn_times = [
        parsed
        for parsed in (_parse_iso_datetime(message.timestamp) for message in turn_messages)
        if parsed is not None
    ]
    start_time = min(turn_times) if turn_times else conv.start_time
    end_time = max(turn_times) if turn_times else (conv.end_time or conv.start_time)
    display = {}
    if primary_language:
        display[primary_language] = {
            "title": conv.title or conv.conv_id,
            "summary": summary,
        }
    episode = EpisodicMemory(
        episode_id=episode_id,
        conv_id=conv.conv_id,
        platform=conv.platform,
        topic=conv.title or conv.conv_id,
        primary_language=primary_language,
        display=display,
        topics_covered=[conv.title] if conv.title else [],
        summary=summary,
        key_decisions=[],
        open_issues=[],
        granularity="turn" if turn_ref else "conversation",
        turn_refs=[turn_ref] if turn_ref else [turn.turn_id for turn in (conv.turns or []) if getattr(turn, "turn_id", "")],
        relates_to_profile=False,
        relates_to_preferences=False,
        relates_to_projects=[],
        relates_to_workflows=[],
        time_range_start=start_time,
        time_range_end=end_time,
    )
    if start_time is not None:
        episode.created_at = start_time
    if end_time is not None:
        episode.updated_at = end_time
    elif start_time is not None:
        episode.updated_at = start_time
    episode.add_evidence("l0_raw", conv.conv_id, summary[:240] if summary else conv.conv_id)
    return episode


def build_episodes_for_conversation(settings: dict[str, Any], conv: RawConversation) -> list[EpisodicMemory]:
    # `_build_episodes` only needs the LLM and prompts; avoid touching L2Wiki
    # from worker threads because canonical episode writes happen serially.
    builder = MemoryBuilder(llm=get_llm(settings), wiki=None)  # type: ignore[arg-type]
    return builder._build_episodes(conv)


def build_episodes_for_turn_refs(
    settings: dict[str, Any],
    conv: RawConversation,
    turn_refs: list[str],
) -> list[EpisodicMemory]:
    builder = MemoryBuilder(llm=get_llm(settings), wiki=None)  # type: ignore[arg-type]
    return builder._build_episodes(conv, target_turn_refs=turn_refs)


def persist_raw_conversations(root: Path, conversations: list[RawConversation], *, platform_hint: str = "") -> int:
    raw_root = root / "raw"
    saved = 0
    for conv in conversations:
        platform = _safe_slug(conv.platform or platform_hint or "unknown")
        conv_id = _safe_slug(conv.conv_id, fallback=f"conversation_{saved + 1}")
        platform_dir = raw_root / platform
        platform_dir.mkdir(parents=True, exist_ok=True)
        (platform_dir / f"{conv_id}.json").write_text(
            json.dumps(raw_conversation_payload(conv), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        saved += 1
    return saved


def load_all_raw_conversations(settings: dict[str, Any]) -> list[RawConversation]:
    raw_root = get_raw_root(settings)
    if not raw_root.exists():
        return []

    l0 = L0RawLayer(raw_root / "_raw_index")
    conversations: list[RawConversation] = []
    for path in sorted(raw_root.rglob("*.json")):
        if "_raw_index" in path.parts:
            continue
        try:
            conversations.extend(l0.ingest_file(path))
        except Exception:  # noqa: BLE001
            continue
    return conversations


def _load_raw_conversation_object_map(settings: dict[str, Any]) -> dict[str, RawConversation]:
    conversation_map: dict[str, RawConversation] = {}
    for conv in load_all_raw_conversations(settings):
        conv_id = str(conv.conv_id or "").strip()
        if not conv_id:
            continue
        conversation_map[conv_id] = conv
    return conversation_map


def _load_raw_conversation_map(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    conversation_map: dict[str, dict[str, Any]] = {}
    for conv in load_all_raw_conversations(settings):
        conv_id = str(conv.conv_id or "").strip()
        if not conv_id:
            continue
        conversation_map[conv_id] = raw_conversation_payload(conv)
    return conversation_map


def parse_selected_ids(selected_ids: list[str]) -> dict[str, set[str]]:
    selected = {
        "profile_fields": set(),
        "profile_values": set(),
        "preferences_fields": set(),
        "preferences_values": set(),
        "projects": set(),
        "workflows": set(),
        "persistent": set(),
    }
    for item_id in selected_ids:
        prefix, _, suffix = item_id.partition(":")
        if prefix == "profile":
            if suffix and suffix != "default":
                if suffix.startswith("group:"):
                    group_id = suffix.split(":", 1)[1]
                    selected["profile_fields"].update(_taxonomy_group_source_fields("profile", group_id))
                    continue
                parts = suffix.split(":", 1)
                if len(parts) == 2:
                    selected["profile_values"].add(suffix)
                    selected["profile_fields"].add(parts[0])
                else:
                    selected["profile_fields"].add(suffix)
            else:
                selected["profile_fields"].add("*")
        elif prefix == "preferences":
            if suffix and suffix != "default":
                if suffix.startswith("group:"):
                    group_id = suffix.split(":", 1)[1]
                    selected["preferences_fields"].update(_taxonomy_group_source_fields("preferences", group_id))
                    continue
                parts = suffix.split(":", 1)
                if len(parts) == 2:
                    selected["preferences_values"].add(suffix)
                    selected["preferences_fields"].add(parts[0])
                else:
                    selected["preferences_fields"].add(suffix)
            else:
                selected["preferences_fields"].add("*")
        elif prefix in {"project", "projects"}:
            if suffix and suffix != "default":
                selected["projects"].add(suffix)
            else:
                selected["projects"].add("*")
        elif prefix in {"workflow", "workflows"}:
            if suffix and suffix != "default":
                selected["workflows"].add(suffix)
            else:
                selected["workflows"].add("*")
        elif prefix in {"persistent", "daily_notes"}:
            if suffix and suffix != "default":
                selected["persistent"].add(suffix)
            else:
                selected["persistent"].add("*")
    return selected


def _empty_memory_field_value(value: Any) -> Any:
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    if isinstance(value, bool):
        return False
    return ""


def _model_field_values_for_ignore(model: ProfileMemory | PreferenceMemory, field: str) -> list[str]:
    value = getattr(model, field, None)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, bool):
        return [str(value).lower()]
    return []


def _record_model_memory_ignore(
    state: dict[str, Any],
    category: str,
    suffix: str,
    touched_fields: set[str],
    before_model: ProfileMemory | PreferenceMemory,
) -> None:
    bucket = state.setdefault(category, {"fields": [], "values": {}})
    if not isinstance(bucket, dict):
        bucket = {"fields": [], "values": {}}
        state[category] = bucket
    fields = [field for field in touched_fields if field]
    if not fields:
        return

    if suffix and not suffix.startswith("group:"):
        field, sep, value_slug = suffix.partition(":")
        if sep and field in fields and value_slug:
            values = bucket.setdefault("values", {})
            if not isinstance(values, dict):
                values = {}
                bucket["values"] = values
            entries = values.setdefault(field, [])
            if not isinstance(entries, list):
                entries = []
                values[field] = entries
            matched_values = [
                text
                for text in _model_field_values_for_ignore(before_model, field)
                if _safe_slug(text, "item") == value_slug
            ]
            if not matched_values:
                matched_values = [value_slug]
            existing = {
                (str(entry.get("slug") or ""), str(entry.get("text") or ""))
                for entry in entries
                if isinstance(entry, dict)
            }
            for text in matched_values:
                entry = {"slug": value_slug, "text": str(text or "").strip()}
                key = (entry["slug"], entry["text"])
                if key not in existing:
                    entries.append(entry)
                    existing.add(key)
        else:
            bucket["fields"] = sorted(set([*(bucket.get("fields") or []), *fields]))
    else:
        bucket["fields"] = sorted(set([*(bucket.get("fields") or []), *fields]))

    deleted_items = state.setdefault("deleted_items", [])
    if isinstance(deleted_items, list):
        deleted_items.append(
            {
                "category": category,
                "item": suffix,
                "fields": sorted(fields),
                "deleted_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def _ignored_value_slugs(entries: Any) -> set[str]:
    slugs: set[str] = set()
    raw_entries = entries if isinstance(entries, list) else []
    for entry in raw_entries:
        if isinstance(entry, dict):
            slug = str(entry.get("slug") or "").strip()
            text = str(entry.get("text") or "").strip()
        else:
            text = str(entry or "").strip()
            slug = ""
        if slug:
            slugs.add(slug)
        if text:
            slugs.add(_safe_slug(text, "item"))
    return slugs


def _apply_ignore_bucket_to_model(model: ProfileMemory | PreferenceMemory, bucket: dict[str, Any]) -> None:
    ignored_fields = {str(field).strip() for field in (bucket.get("fields") or []) if str(field or "").strip()}
    ignored_values = bucket.get("values") if isinstance(bucket.get("values"), dict) else {}

    for field in ignored_fields:
        if hasattr(model, field):
            setattr(model, field, _empty_memory_field_value(getattr(model, field)))

    for field, entries in ignored_values.items():
        field_name = str(field or "").strip()
        if not field_name or field_name in ignored_fields or not hasattr(model, field_name):
            continue
        current = getattr(model, field_name)
        slugs = _ignored_value_slugs(entries)
        if not slugs:
            continue
        if isinstance(current, list):
            setattr(
                model,
                field_name,
                [item for item in current if _safe_slug(str(item), "item") not in slugs],
            )
        elif isinstance(current, str) and _safe_slug(current, "item") in slugs:
            setattr(model, field_name, "")


def apply_memory_ignore_rules(
    settings: dict[str, Any],
    profile: ProfileMemory | None = None,
    preferences: PreferenceMemory | None = None,
) -> tuple[ProfileMemory | None, PreferenceMemory | None]:
    state = load_memory_ignore_state(settings)
    if profile is not None:
        _apply_ignore_bucket_to_model(profile, state.get("profile", {}))
    if preferences is not None:
        _apply_ignore_bucket_to_model(preferences, state.get("preferences", {}))
    return profile, preferences


def _remove_slugged_list_value(values: Any, slug: str) -> tuple[Any, bool]:
    if not isinstance(values, list):
        return values, False
    kept = [item for item in values if _safe_slug(str(item), "item") != slug]
    return kept, len(kept) != len(values)


def _remove_slugged_profile_focus_value(values: Any, slug: str) -> tuple[Any, bool]:
    split_values = _profile_long_term_focus_values(values)
    kept = [item for item in split_values if _safe_slug(str(item), "item") != slug]
    return kept, len(kept) != len(split_values)


def _persistent_node_delete_lock(node_id: str, node: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "key": node.get("key"),
        "description": node.get("description"),
        "display": node.get("display") if isinstance(node.get("display"), dict) else {},
        "episode_refs": [str(ref) for ref in (node.get("episode_refs") or []) if str(ref).strip()],
        "turn_refs": [str(ref) for ref in (node.get("turn_refs") or []) if str(ref).strip()],
    }


def _append_unique_strings(target: list[Any], values: list[Any]) -> list[str]:
    merged = [str(item).strip() for item in target if str(item or "").strip()]
    for value in values:
        text = str(value or "").strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _clear_global_episode_ignores(payload: dict[str, Any]) -> None:
    payload["ignored_episode_ids"] = []
    payload["ignored_turn_refs"] = []


def _delete_model_memory_item(
    model: ProfileMemory | PreferenceMemory,
    category: str,
    suffix: str,
) -> tuple[bool, set[str]]:
    changed = False
    touched_fields: set[str] = set()
    if not suffix or suffix == "default":
        fields = [
            field
            for field in type(model).model_fields
            if field not in MemoryBase.model_fields
        ]
        value_slug = ""
    elif suffix.startswith("group:"):
        group_id = suffix.split(":", 1)[1]
        fields = _taxonomy_group_source_fields(category, group_id)
        value_slug = ""
    else:
        field, sep, value_slug = suffix.partition(":")
        fields = [field] if field else []
        if not sep:
            value_slug = ""

    for field in fields:
        if not hasattr(model, field):
            continue
        current = getattr(model, field)
        if value_slug:
            if category == "profile" and field == "long_term_research_or_work_focus":
                next_value, field_changed = _remove_slugged_profile_focus_value(current, value_slug)
            else:
                next_value, field_changed = _remove_slugged_list_value(current, value_slug)
        else:
            next_value = _empty_memory_field_value(current)
            field_changed = next_value != current
        if not field_changed:
            continue
        setattr(model, field, next_value)
        touched_fields.add(field)
        changed = True
    return changed, touched_fields


def _drop_memory_display_cache(
    settings: dict[str, Any],
    *,
    item_ids: set[str],
    profile_fields: set[str],
    preferences_fields: set[str],
) -> None:
    cache = load_display_texts(settings)
    changed = False
    if not isinstance(cache, dict):
        return

    for category, fields in (("profile", profile_fields), ("preferences", preferences_fields)):
        entries = cache.get(category)
        if not isinstance(entries, dict):
            continue
        for item_id in item_ids:
            if item_id in entries:
                entries.pop(item_id, None)
                changed = True
        for field in fields:
            direct_key = f"{category}:{field}"
            if direct_key in entries:
                entries.pop(direct_key, None)
                changed = True
            prefix = f"{category}:{field}:"
            for key in list(entries.keys()):
                if str(key).startswith(prefix):
                    entries.pop(key, None)
                    changed = True

    persistent_entries = cache.get("persistent")
    if isinstance(persistent_entries, dict):
        for item_id in item_ids:
            if item_id in persistent_entries:
                persistent_entries.pop(item_id, None)
                changed = True

    if changed:
        save_display_texts(settings, cache)


def delete_memory_items(settings: dict[str, Any], item_ids: list[str]) -> dict[str, Any]:
    wiki = get_wiki(settings)
    profile = wiki.load_profile()
    preferences = wiki.load_preferences()
    persistent = load_persistent_nodes(settings)
    persistent_nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
    ignore_state = load_memory_ignore_state(settings)

    deleted: list[str] = []
    missing: list[str] = []
    profile_changed = False
    preferences_changed = False
    persistent_changed = False
    ignore_changed = False
    touched_profile_fields: set[str] = set()
    touched_preference_fields: set[str] = set()

    for raw_item_id in item_ids:
        item_id = str(raw_item_id or "").strip()
        if not item_id:
            continue
        prefix, _, suffix = item_id.partition(":")
        removed = False

        if prefix == "profile":
            if profile is not None:
                before_profile = profile.model_copy(deep=True)
                removed, fields = _delete_model_memory_item(profile, "profile", suffix)
                if removed:
                    profile_changed = True
                    ignore_changed = True
                    _record_model_memory_ignore(ignore_state, "profile", suffix, fields, before_profile)
                    touched_profile_fields.update(fields)

        elif prefix == "preferences":
            if preferences is not None:
                before_preferences = preferences.model_copy(deep=True)
                removed, fields = _delete_model_memory_item(preferences, "preferences", suffix)
                if removed:
                    preferences_changed = True
                    ignore_changed = True
                    _record_model_memory_ignore(ignore_state, "preferences", suffix, fields, before_preferences)
                    touched_preference_fields.update(fields)

        elif prefix in {"project", "projects"} and suffix:
            removed = wiki.delete_project(suffix)

        elif prefix in {"workflow", "workflows"} and suffix:
            workflows = wiki.load_workflows()
            kept = [workflow for workflow in workflows if workflow.workflow_name != suffix]
            removed = len(kept) != len(workflows)
            if removed:
                wiki.save_workflows(kept)

        elif prefix in {"persistent", "daily_notes"} and suffix:
            if suffix in persistent_nodes:
                node = persistent_nodes.pop(suffix, None)
                if isinstance(node, dict):
                    locks = persistent.setdefault("deleted_node_locks", [])
                    if isinstance(locks, list):
                        locks.append(_persistent_node_delete_lock(suffix, node))
                persistent_changed = True
                removed = True

        if removed:
            deleted.append(item_id)
        else:
            missing.append(item_id)

    if profile_changed and profile is not None:
        wiki.save_profile(profile)
    if preferences_changed and preferences is not None:
        wiki.save_preferences(preferences)
    if persistent_changed:
        persistent["nodes"] = persistent_nodes
        save_persistent_nodes(settings, persistent)
    if ignore_changed:
        save_memory_ignore_state(settings, ignore_state)
    if deleted:
        _drop_memory_display_cache(
            settings,
            item_ids=set(deleted),
            profile_fields=touched_profile_fields,
            preferences_fields=touched_preference_fields,
        )
        refresh_organize_memory_signatures(settings)

    return {
        "ok": True,
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "missing_ids": missing,
    }


def _filter_fields(data: dict[str, Any], selected_fields: set[str]) -> dict[str, Any]:
    if "*" in selected_fields:
        return dict(data)
    filtered = {"id": data.get("id")}
    for field in selected_fields:
        if field in data and data[field]:
            filtered[field] = data[field]
    return filtered


def _filter_profile_fields(data: dict[str, Any], selected_fields: set[str], selected_values: set[str]) -> dict[str, Any]:
    if "*" in selected_fields:
        return dict(data)

    filtered = {"id": data.get("id")}
    value_map: dict[str, set[str]] = {}
    for token in selected_values:
        field, _, slug = token.partition(":")
        if field and slug:
            value_map.setdefault(field, set()).add(slug)

    for field in selected_fields:
        if field not in data or not data[field]:
            continue
        value = data[field]
        if isinstance(value, list) and field in value_map:
            source_values = (
                _profile_long_term_focus_values(value)
                if field == "long_term_research_or_work_focus"
                else value
            )
            kept = [item for item in source_values if _safe_slug(str(item), "item") in value_map[field]]
            if kept:
                filtered[field] = kept
        else:
            filtered[field] = value
    return filtered


def _filter_preference_fields(data: dict[str, Any], selected_fields: set[str], selected_values: set[str]) -> dict[str, Any]:
    if "*" in selected_fields:
        return dict(data)

    filtered = {"id": data.get("id")}
    value_map: dict[str, set[str]] = {}
    for token in selected_values:
        field, _, slug = token.partition(":")
        if field and slug:
            value_map.setdefault(field, set()).add(slug)

    for field in selected_fields:
        if field not in data or not data[field]:
            continue
        value = data[field]
        if isinstance(value, list) and field in value_map:
            kept = [
                item
                for item in value
                if _safe_slug(str(item), "item") in value_map[field]
            ]
            if kept:
                filtered[field] = kept
        else:
            filtered[field] = value
    return filtered


_INJECTION_STORAGE_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "version",
    "evidence_links",
    "conflict_log",
    "user_confirmed",
    "source_episode_ids",
    "source_turn_refs",
    "platform",
    "primary_language",
}


def _is_empty_injection_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _entry_text_for_injection(value: Any) -> Any:
    if isinstance(value, dict) and "text" in value:
        return str(value.get("text") or "").strip()
    return value


def _compact_injection_value(value: Any, *, max_items: int = 8) -> Any:
    value = _entry_text_for_injection(value)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if key in _INJECTION_STORAGE_FIELDS or key == "timestamp":
                continue
            compact_item = _compact_injection_value(item, max_items=max_items)
            if not _is_empty_injection_value(compact_item):
                compact[str(key)] = compact_item
        return compact
    if isinstance(value, list):
        compact_list: list[Any] = []
        for item in value:
            compact_item = _compact_injection_value(item, max_items=max_items)
            if _is_empty_injection_value(compact_item):
                continue
            if compact_item not in compact_list:
                compact_list.append(compact_item)
            if len(compact_list) >= max_items:
                break
        return compact_list
    if isinstance(value, str):
        return value.strip()
    return value


def _is_generic_language_value(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {
        "zh",
        "cn",
        "chinese",
        "mandarin",
        "中文",
        "中文为主",
        "回答以中文为主",
        "en",
        "english",
        "英文",
        "英语",
        "英文为主",
    }


def _compact_profile_for_injection(data: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "name_or_alias",
        "role_identity",
        "domain_background",
        "organization_or_affiliation",
        "long_term_research_or_work_focus",
    ]
    compact: dict[str, Any] = {}
    for field in allowed_fields:
        value = _compact_injection_value(data.get(field))
        if not _is_empty_injection_value(value):
            compact[field] = value
    return compact


def _compact_preferences_for_injection(data: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "style_preference",
        "terminology_preference",
        "formatting_constraints",
        "forbidden_expressions",
        "language_preference",
        "primary_task_types",
        "revision_preference",
        "response_granularity",
    ]
    compact: dict[str, Any] = {}
    generic_language_value: Any = None
    for field in allowed_fields:
        value = _compact_injection_value(data.get(field))
        if _is_empty_injection_value(value):
            continue
        if field == "language_preference" and _is_generic_language_value(value):
            generic_language_value = value
            continue
        compact[field] = value
    if not compact and generic_language_value:
        compact["language_preference"] = _localized_language_display(
            generic_language_value,
            "zh",
            response_preference=True,
        )
    return compact


def _compact_project_for_injection(data: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "project_name",
        "project_goal",
        "current_stage",
        "key_terms",
        "finished_decisions",
        "unresolved_questions",
        "relevant_entities",
        "important_constraints",
        "next_actions",
    ]
    compact: dict[str, Any] = {}
    for field in allowed_fields:
        max_items = 5 if field != "key_terms" else 8
        value = _compact_injection_value(data.get(field), max_items=max_items)
        if field == "project_goal":
            value = _trim_unconfirmed_project_goal_for_injection(str(value or ""), data)
        if not _is_empty_injection_value(value):
            compact[field] = value
    return compact


def _trim_unconfirmed_project_goal_for_injection(goal: str, data: dict[str, Any]) -> str:
    goal = str(goal or "").strip()
    if not goal:
        return ""
    support_text = " ".join(
        str(_entry_text_for_injection(item) or "")
        for field in ("unresolved_questions", "next_actions")
        for item in (data.get(field) or [])
    )
    if not support_text:
        return goal
    uncertainty_markers = (
        "是否采纳",
        "是否采用",
        "是否确定",
        "待确认",
        "尚未确认",
        "pending confirmation",
        "confirm whether",
        "whether to adopt",
    )
    if not any(marker.lower() in support_text.lower() for marker in uncertainty_markers):
        return goal
    parts = [part.strip() for part in re.split(r"[，,；;]", goal) if part.strip()]
    if len(parts) <= 1:
        return goal
    tentative_tail = " ".join(parts[1:])
    proposal_markers = (
        "主打",
        "导向",
        "定位",
        "面向",
        "目标用户",
        "应用场景",
        "业务场景",
        "策略",
        "路线",
        "positioning",
        "audience",
        "scenario",
        "strategy",
    )
    if any(marker.lower() in tentative_tail.lower() for marker in proposal_markers):
        return parts[0]
    return goal


def _compact_workflow_for_injection(data: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "workflow_name",
        "trigger_condition",
        "typical_steps",
        "preferred_artifact_format",
        "review_style",
        "escalation_rule",
        "reuse_frequency",
        "occurrence_count",
    ]
    compact: dict[str, Any] = {}
    for field in allowed_fields:
        value = _compact_injection_value(data.get(field), max_items=6)
        if not _is_empty_injection_value(value):
            compact[field] = value
    return compact


def _compact_persistent_node_for_injection(data: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = ["type", "description", "steps"]
    compact: dict[str, Any] = {}
    for field in allowed_fields:
        value = _compact_injection_value(data.get(field), max_items=6)
        if not _is_empty_injection_value(value):
            compact[field] = value
    return compact


def _persistent_node_for_injection(node_id: str, node: dict[str, Any]) -> dict[str, Any]:
    title, display_description = _daily_note_display_texts(node_id, node, {}, "zh-CN")
    compact: dict[str, Any] = {}
    node_type = str(node.get("type") or "").strip()
    if node_type:
        compact["type"] = node_type
    if title:
        compact["title"] = title
    if display_description:
        compact["description"] = display_description
    return compact


def _normalize_snippet_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _extract_snippet_hint_segments(excerpt: str) -> list[str]:
    text = str(excerpt or "").strip()
    if not text:
        return []
    segments = re.split(r"\[[A-Z_]+\]:", text)
    cleaned = []
    for segment in segments:
        normalized = _normalize_snippet_text(segment)
        if len(normalized) >= 12:
            cleaned.append(normalized)
    if cleaned:
        return cleaned[:4]
    normalized = _normalize_snippet_text(text)
    return [normalized] if len(normalized) >= 12 else []


def _turn_index_from_ref(turn_ref: Any) -> int:
    try:
        return int(str(turn_ref or "").rsplit(":turn:", 1)[1])
    except (IndexError, ValueError):
        return 10**9


def _first_turn_ref(value: Any) -> str:
    if isinstance(value, dict):
        refs = value.get("turn_refs") or []
        if isinstance(refs, list) and refs:
            return str(refs[0] or "")
        return str(value.get("turn_id") or "")
    return ""


def _turn_conversation_id(turn_ref: str) -> str:
    return str(turn_ref or "").split(":turn:", 1)[0]


def _sort_timestamp_value(value: Any) -> float:
    dt = _parse_iso_datetime(str(value or ""))
    if dt is None:
        return float("inf")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _episode_payload_sort_key(episode: dict[str, Any]) -> tuple[float, str, int, str]:
    turn_ref = _first_turn_ref(episode)
    return (
        _sort_timestamp_value(
            episode.get("time_range_start")
            or episode.get("created_at")
            or episode.get("updated_at")
        ),
        _turn_conversation_id(turn_ref),
        _turn_index_from_ref(turn_ref),
        str(episode.get("episode_id") or episode.get("id") or ""),
    )


def _raw_turn_payload_sort_key(turn: dict[str, Any]) -> tuple[float, str, int, str]:
    turn_ref = str(turn.get("turn_id") or "")
    return (
        _sort_timestamp_value(turn.get("timestamp")),
        _turn_conversation_id(turn_ref),
        _turn_index_from_ref(turn_ref),
        turn_ref,
    )


def truncate_text(value: str, max_length: int = 120, *, ellipsis: bool = True) -> str:
    normalized = _normalize_snippet_text(value)
    if len(normalized) <= max_length:
        return normalized
    if max_length <= 0:
        return ""
    if not ellipsis or max_length == 1:
        return normalized[:max_length].rstrip()
    return f"{normalized[: max(0, max_length - 1)].rstrip()}…"


def _turn_payloads_from_message_dicts(conversation_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current_message_ids: list[str] = []
    for index, msg in enumerate(messages):
        role = str(msg.get("role") or "").strip().lower()
        message_id = str(msg.get("id") or f"{conversation_id}_{index}")
        if role == "user" and current_message_ids:
            turns.append(
                {
                    "turn_id": f"{conversation_id}:turn:{len(turns)}",
                    "conversation_id": conversation_id,
                    "message_ids": current_message_ids[:],
                }
            )
            current_message_ids = [message_id]
        else:
            current_message_ids.append(message_id)
    if current_message_ids:
        turns.append(
            {
                "turn_id": f"{conversation_id}:turn:{len(turns)}",
                "conversation_id": conversation_id,
                "message_ids": current_message_ids[:],
            }
        )
    return turns


def _episode_container_path(episodes_dir: Path, conv_id: str) -> Path:
    safe_name = str(conv_id or "unknown_conversation").replace("/", "_")[:160]
    return episodes_dir / f"{safe_name}.json"


def _episode_records_from_file(path: Path) -> list[dict[str, Any]]:
    data = read_json_file(path)
    if isinstance(data, dict) and isinstance(data.get("episodes"), list):
        return [item for item in data.get("episodes", []) if isinstance(item, dict)]
    if isinstance(data, dict) and data.get("episode_id"):
        return [data]
    return []


def _read_episode_record(episodes_dir: Path, episode_id: str) -> dict[str, Any] | None:
    episode_id = str(episode_id or "").strip()
    if not episode_id:
        return None
    direct = episodes_dir / f"{episode_id}.json"
    for episode in _episode_records_from_file(direct):
        if str(episode.get("episode_id") or "").strip() == episode_id:
            return episode
    for path in episodes_dir.glob("*.json"):
        for episode in _episode_records_from_file(path):
            if str(episode.get("episode_id") or "").strip() == episode_id:
                return episode
    return None


def _episode_container_has_ids(episodes_dir: Path, conv_id: str, episode_ids: list[str]) -> bool:
    path = _episode_container_path(episodes_dir, conv_id)
    if not path.exists():
        return False
    existing_ids = {
        str(episode.get("episode_id") or "").strip()
        for episode in _episode_records_from_file(path)
    }
    return all(episode_id in existing_ids for episode_id in episode_ids)


def _remove_episode_storage_for_conversation(episodes_dir: Path, conv_id: str, episode_ids: list[str]) -> None:
    for path in (
        _episode_container_path(episodes_dir, conv_id),
        _episode_container_path(episodes_dir, conv_id).with_suffix(".md"),
    ):
        if path.exists():
            path.unlink()
    for old_episode_id in episode_ids:
        for suffix in (".json", ".md"):
            old_path = episodes_dir / f"{old_episode_id}{suffix}"
            if old_path.exists():
                old_path.unlink()


def _episode_record_sort_key(record: dict[str, Any]) -> tuple[str, int, str]:
    turn_index = 10**9
    turn_refs = record.get("turn_refs") or []
    if turn_refs:
        try:
            turn_index = int(str(turn_refs[0]).rsplit(":turn:", 1)[1])
        except (IndexError, ValueError):
            turn_index = 10**9
    created = str(record.get("created_at") or record.get("time_range_start") or "")
    episode_id = str(record.get("episode_id") or "")
    return created, turn_index, episode_id


def _write_episode_records_for_conversation(
    episodes_dir: Path,
    conv_id: str,
    records: list[dict[str, Any]],
) -> None:
    path = _episode_container_path(episodes_dir, conv_id)
    md_path = path.with_suffix(".md")
    clean_records = sorted(records, key=_episode_record_sort_key)
    if not clean_records:
        for target in (path, md_path):
            if target.exists():
                target.unlink()
        return

    episodes: list[EpisodicMemory] = []
    for record in clean_records:
        try:
            episodes.append(EpisodicMemory.model_validate(record))
        except Exception:
            continue
    if not episodes:
        for target in (path, md_path):
            if target.exists():
                target.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "conversation_id": conv_id,
                "episode_count": len(episodes),
                "episodes": [episode.model_dump(mode="json") for episode in episodes],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    md_path.write_text(
        "\n\n---\n\n".join(episode.to_markdown() for episode in episodes),
        encoding="utf-8",
    )


def _remove_episode_ids_from_conversation(
    episodes_dir: Path,
    conv_id: str,
    episode_ids: list[str],
) -> None:
    remove_ids = {str(episode_id or "").strip() for episode_id in episode_ids if str(episode_id or "").strip()}
    if not remove_ids:
        return
    path = _episode_container_path(episodes_dir, conv_id)
    kept_records = [
        record
        for record in _episode_records_from_file(path)
        if str(record.get("episode_id") or "").strip() not in remove_ids
    ]
    _write_episode_records_for_conversation(episodes_dir, conv_id, kept_records)
    for old_episode_id in remove_ids:
        for suffix in (".json", ".md"):
            old_path = episodes_dir / f"{old_episode_id}{suffix}"
            if old_path.exists():
                old_path.unlink()


def _collect_raw_support_from_episode_ids(
    episodes_dir: Path,
    episode_ids: list[str] | set[str],
) -> tuple[set[str], dict[str, list[str]], dict[str, set[str]]]:
    raw_ids: set[str] = set()
    excerpt_hints: dict[str, list[str]] = {}
    turn_refs: dict[str, set[str]] = {}
    for episode_id in episode_ids:
        ep_id = str(episode_id or "").strip()
        if not ep_id:
            continue
        episode = _read_episode_record(episodes_dir, ep_id)
        if not isinstance(episode, dict):
            continue
        conv_id = str(episode.get("conv_id") or "").strip()
        if conv_id:
            raw_ids.add(conv_id)
            semantic_hints = [
                str(episode.get("summary") or "").strip(),
                *[str(item or "").strip() for item in (episode.get("key_decisions") or [])],
                *[str(item or "").strip() for item in (episode.get("open_issues") or [])],
            ]
            for hint in semantic_hints:
                if hint:
                    excerpt_hints.setdefault(conv_id, []).append(hint)
        for turn_id in episode.get("turn_refs", []) or []:
            turn_text = str(turn_id or "").strip()
            if not turn_text:
                continue
            turn_conv_id = conv_id or turn_text.split(":turn:", 1)[0]
            if not turn_conv_id:
                continue
            raw_ids.add(turn_conv_id)
            turn_refs.setdefault(turn_conv_id, set()).add(turn_text)
        for link in episode.get("evidence_links", []) or []:
            if not isinstance(link, dict):
                continue
            source_type = str(link.get("source_type") or "").strip().lower()
            source_id = str(link.get("source_id") or "").strip()
            if source_type in {"l0_raw", "chat_history"} and source_id:
                raw_ids.add(source_id)
                excerpt = str(link.get("excerpt") or "").strip()
                if excerpt:
                    excerpt_hints.setdefault(source_id, []).append(excerpt)
            elif source_type in {"l0_raw", "chat_history"} and conv_id:
                excerpt = str(link.get("excerpt") or "").strip()
                if excerpt:
                    excerpt_hints.setdefault(conv_id, []).append(excerpt)
    return raw_ids, excerpt_hints, turn_refs


def _expand_episode_ids_with_connections(
    episodes_dir: Path,
    episode_ids: set[str],
) -> set[str]:
    expanded = set(episode_ids)
    for episode_id in list(episode_ids):
        episode = _read_episode_record(episodes_dir, episode_id)
        if not isinstance(episode, dict):
            continue
        for connection in episode.get("connections", []) or []:
            if not isinstance(connection, dict):
                continue
            connected_id = str(connection.get("episode_id") or "").strip()
            if connected_id:
                expanded.add(connected_id)
    return expanded


def _collect_raw_support_from_memory_object(
    memory_obj: Any,
    episodes_dir: Path,
) -> tuple[set[str], dict[str, list[str]], dict[str, set[str]]]:
    raw_ids: set[str] = set()
    excerpt_hints: dict[str, list[str]] = {}
    episode_turn_refs: dict[str, set[str]] = {}
    if memory_obj is None:
        return raw_ids, excerpt_hints, episode_turn_refs
    evidence_links = getattr(memory_obj, "evidence_links", []) or []
    for link in evidence_links:
        source_type = str(getattr(link, "source_type", "") or "").strip().lower()
        source_id = str(getattr(link, "source_id", "") or "").strip()
        if source_type in {"l0_raw", "chat_history"} and source_id:
            raw_ids.add(source_id)
            excerpt = str(getattr(link, "excerpt", "") or "").strip()
            if excerpt:
                excerpt_hints.setdefault(source_id, []).append(excerpt)
    source_episode_ids = getattr(memory_obj, "source_episode_ids", []) or []
    episode_raw_ids, episode_hints, turn_refs = _collect_raw_support_from_episode_ids(episodes_dir, source_episode_ids)
    raw_ids.update(episode_raw_ids)
    for conv_id, hints in episode_hints.items():
        excerpt_hints.setdefault(conv_id, []).extend(hints)
    for conv_id, refs in turn_refs.items():
        episode_turn_refs.setdefault(conv_id, set()).update(refs)
    for turn_id in getattr(memory_obj, "source_turn_refs", []) or []:
        turn_text = str(turn_id or "").strip()
        if not turn_text:
            continue
        turn_conv_id = turn_text.split(":turn:", 1)[0]
        if not turn_conv_id:
            continue
        raw_ids.add(turn_conv_id)
        episode_turn_refs.setdefault(turn_conv_id, set()).add(turn_text)
    return raw_ids, excerpt_hints, episode_turn_refs


def _collect_platform_support_from_memory_object(memory_obj: Any) -> set[str]:
    record_ids: set[str] = set()
    if memory_obj is None:
        return record_ids
    evidence_links = getattr(memory_obj, "evidence_links", []) or []
    for link in evidence_links:
        source_type = str(getattr(link, "source_type", "") or "").strip().lower()
        source_id = str(getattr(link, "source_id", "") or "").strip()
        if source_type == "l1_signal" and source_id and source_id != "platform_export":
            record_ids.add(source_id)
    return record_ids


def _merge_raw_hint_maps(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for conv_id, hints in source.items():
        bucket = target.setdefault(conv_id, [])
        for hint in hints:
            clean = str(hint or "").strip()
            if clean and clean not in bucket:
                bucket.append(clean)


def _build_relevant_raw_snippets(
    conversations: dict[str, RawConversation],
    hint_map: dict[str, list[str]],
    *,
    turn_ref_map: dict[str, set[str]] | None = None,
    window: int = 1,
) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    for conv_id in sorted(hint_map):
        conv = conversations.get(conv_id)
        if conv is None:
            continue
        hints = [hint for hint in hint_map.get(conv_id, []) if str(hint).strip()]
        matched_indexes: set[int] = set()
        exact_turn_refs = set(turn_ref_map.get(conv_id, set())) if turn_ref_map else set()
        for hint in hints:
            for segment in _extract_snippet_hint_segments(hint):
                segment_norm = _normalize_snippet_text(segment).lower()
                if not segment_norm:
                    continue
                segment_head = segment_norm[:48]
                for idx, msg in enumerate(conv.messages):
                    msg_norm = _normalize_snippet_text(msg.content).lower()
                    if not msg_norm:
                        continue
                    if segment_norm in msg_norm or (segment_head and segment_head in msg_norm):
                        matched_indexes.add(idx)
        if not matched_indexes and not exact_turn_refs:
            continue
        snippet_indexes: set[int] = set()
        for idx in matched_indexes:
            start = max(0, idx - window)
            end = min(len(conv.messages), idx + window + 1)
            snippet_indexes.update(range(start, end))
        if exact_turn_refs:
            for turn in _conversation_turns(conv):
                if str(turn.get("turn_id") or "") in exact_turn_refs:
                    snippet_indexes.update(
                        idx for idx in turn.get("message_indexes", []) if isinstance(idx, int)
                    )
        ordered_indexes = sorted(snippet_indexes)
        snippet_messages = [
            {
                "id": conv.messages[idx].msg_id,
                "role": conv.messages[idx].role,
                "content": conv.messages[idx].content,
                "timestamp": conv.messages[idx].timestamp,
            }
            for idx in ordered_indexes
        ]
        if not snippet_messages:
            continue
        snippets.append(
            {
                "conversation_id": conv.conv_id,
                "platform": conv.platform,
                "title": conv.title,
                "matched_excerpts": hints[:3],
                "messages": snippet_messages,
            }
        )
    return snippets


def _message_payload(msg: RawMessage) -> dict[str, Any]:
    return {
        "id": msg.msg_id,
        "role": msg.role,
        "content": msg.content,
        "timestamp": msg.timestamp,
    }


def _raw_message_injection_payload(msg: RawMessage) -> dict[str, Any]:
    payload = {
        "role": msg.role,
        "content": msg.content,
    }
    if msg.timestamp:
        payload["timestamp"] = msg.timestamp
    return payload


def _conversation_turns(conv: RawConversation) -> list[dict[str, Any]]:
    if getattr(conv, "turns", None):
        id_to_index = {str(msg.msg_id or ""): idx for idx, msg in enumerate(conv.messages)}
        persisted_turns: list[dict[str, Any]] = []
        for turn_index, turn in enumerate(conv.turns):
            message_indexes = [
                id_to_index[msg_id]
                for msg_id in (turn.message_ids or [])
                if str(msg_id or "") in id_to_index
            ]
            if not message_indexes:
                continue
            persisted_turns.append(
                {
                    "turn_index": turn_index,
                    "turn_id": turn.turn_id,
                    "message_indexes": message_indexes,
                }
            )
        if persisted_turns:
            return persisted_turns

    turns: list[dict[str, Any]] = []
    current_indexes: list[int] = []

    for idx, msg in enumerate(conv.messages):
        role = str(msg.role or "").strip().lower()
        if role == "user" and current_indexes:
            turns.append(
                {
                    "turn_index": len(turns),
                    "turn_id": f"{conv.conv_id}:turn:{len(turns)}",
                    "message_indexes": current_indexes[:],
                }
            )
            current_indexes = [idx]
        else:
            current_indexes.append(idx)

    if current_indexes:
        turns.append(
            {
                "turn_index": len(turns),
                "turn_id": f"{conv.conv_id}:turn:{len(turns)}",
                "message_indexes": current_indexes[:],
            }
        )

    return turns


def _summarize_turn_messages(messages: list[RawMessage]) -> str:
    user_parts = [str(msg.content or "").strip() for msg in messages if str(msg.role or "").strip().lower() == "user"]
    assistant_parts = [str(msg.content or "").strip() for msg in messages if str(msg.role or "").strip().lower() == "assistant"]
    user_text = truncate_text(" ".join(user_parts), 80, ellipsis=False)
    assistant_text = truncate_text(" ".join(assistant_parts), 120, ellipsis=False)
    if user_text and assistant_text:
        return f"用户询问：{user_text}；助手回应：{assistant_text}"
    if user_text:
        return f"用户询问：{user_text}"
    if assistant_text:
        return f"助手回应：{assistant_text}"
    return truncate_text(" ".join(str(msg.content or "").strip() for msg in messages), 140, ellipsis=False)


def _build_related_qa_turns(
    conversations: dict[str, RawConversation],
    hint_map: dict[str, list[str]],
    *,
    turn_ref_map: dict[str, set[str]] | None = None,
    detailed: bool,
) -> list[dict[str, Any]]:
    related_turns: list[dict[str, Any]] = []
    for conv_id in sorted(hint_map):
        conv = conversations.get(conv_id)
        if conv is None:
            continue
        hints = [hint for hint in hint_map.get(conv_id, []) if str(hint).strip()]
        matched_indexes: set[int] = set()
        exact_turn_refs = set(turn_ref_map.get(conv_id, set())) if turn_ref_map else set()
        for hint in hints:
            for segment in _extract_snippet_hint_segments(hint):
                segment_norm = _normalize_snippet_text(segment).lower()
                if not segment_norm:
                    continue
                segment_head = segment_norm[:48]
                for idx, msg in enumerate(conv.messages):
                    msg_norm = _normalize_snippet_text(msg.content).lower()
                    if not msg_norm:
                        continue
                    if segment_norm in msg_norm or (segment_head and segment_head in msg_norm):
                        matched_indexes.add(idx)
        if not matched_indexes and not exact_turn_refs:
            continue

        turns = _conversation_turns(conv)
        if not turns:
            continue

        matched_turn_indexes: set[int] = set()
        for turn in turns:
            if str(turn.get("turn_id") or "") in exact_turn_refs:
                matched_turn_indexes.add(int(turn["turn_index"]))
            indexes = set(turn.get("message_indexes", []))
            if indexes & matched_indexes:
                matched_turn_indexes.add(int(turn["turn_index"]))

        if not matched_turn_indexes and exact_turn_refs:
            for turn in turns:
                if str(turn.get("turn_id") or "") in exact_turn_refs:
                    matched_turn_indexes.add(int(turn["turn_index"]))

        for turn in turns:
            if int(turn["turn_index"]) not in matched_turn_indexes:
                continue
            turn_messages = [conv.messages[idx] for idx in turn["message_indexes"] if 0 <= idx < len(conv.messages)]
            if not turn_messages:
                continue
            if detailed:
                turn_payload = {
                    "title": conv.title,
                    "turn_id": turn["turn_id"],
                    "timestamp": next((msg.timestamp for msg in turn_messages if msg.timestamp), ""),
                    "messages": [_raw_message_injection_payload(msg) for msg in turn_messages],
                }
            else:
                turn_payload = {
                    "conversation_id": conv.conv_id,
                    "platform": conv.platform,
                    "title": conv.title,
                    "turn_id": turn["turn_id"],
                    "message_ids": [msg.msg_id for msg in turn_messages],
                    "matched_reasons": hints[:3],
                    "turn_excerpt": _summarize_turn_messages(turn_messages),
                }
            related_turns.append(turn_payload)

    return sorted(related_turns, key=_raw_turn_payload_sort_key)


def _episode_summary_evidence_payload(episode: dict[str, Any], *, detailed: bool) -> dict[str, Any]:
    if detailed:
        return {
            "episode_id": str(episode.get("episode_id") or "").strip(),
            "time_range_start": str(episode.get("time_range_start") or "").strip(),
            "time_range_end": str(episode.get("time_range_end") or "").strip(),
            "topic": str(episode.get("topic") or "").strip(),
            "summary": str(episode.get("summary") or "").strip(),
            "key_decisions": [
                str(item).strip()
                for item in (episode.get("key_decisions") or [])
                if str(item).strip()
            ],
            "open_issues": _compact_episode_open_issues(episode.get("open_issues") or []),
            "turn_refs": [
                str(item).strip()
                for item in (episode.get("turn_refs") or [])
                if str(item).strip()
            ],
        }
    return {
        "episode_id": str(episode.get("episode_id") or "").strip(),
        "topic": str(episode.get("topic") or "").strip(),
        "summary": str(episode.get("summary") or "").strip(),
        "time_range_start": str(episode.get("time_range_start") or "").strip(),
        "time_range_end": str(episode.get("time_range_end") or "").strip(),
        "key_decisions": [
            str(item).strip()
            for item in (episode.get("key_decisions") or [])
            if str(item).strip()
        ],
        "open_issues": _compact_episode_open_issues(episode.get("open_issues") or []),
    }


def _compact_episode_open_issues(open_issues: list[Any]) -> list[str]:
    kept: list[str] = []
    for item in open_issues:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        assistant_followup_markers = (
            ("尚未回应" in text and ("助理" in text or "助手" in text)),
            ("助理" in text or "助手" in text) and ("提议" in text or "询问是否需要继续" in text),
            "assistant follow-up" in lowered,
            "assistant offer" in lowered,
        )
        if any(assistant_followup_markers):
            continue
        kept.append(text)
    return kept


def _episode_ids_for_primary_task_types(
    episodes: list[EpisodicMemory],
    task_types: list[str] | tuple[str, ...] | set[str] | None,
) -> list[str]:
    labels = [str(label or "").strip() for label in (task_types or []) if str(label or "").strip()]
    if not labels:
        return []
    matched: list[str] = []
    for episode in episodes:
        text = _task_type_support_text(episode)
        if any(_task_type_is_mentioned(label, text) for label in labels):
            matched.append(episode.episode_id)
    return list(dict.fromkeys(matched))


def build_selected_memory_payload(
    settings: dict[str, Any],
    selected_ids: list[str],
    *,
    include_episodic_evidence: bool,
    detailed_injection: bool,
) -> dict[str, Any]:
    selected = parse_selected_ids(selected_ids)
    wiki = get_wiki(settings)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "memory": {},
        "evidence": {},
    }
    include_episode_evidence = bool(include_episodic_evidence or detailed_injection)
    include_raw_evidence = bool(detailed_injection)
    episodes_dir = get_storage_root(settings) / "episodes"
    raw_conversation_map: dict[str, RawConversation] | None = None
    raw_conversation_ids: set[str] = set()
    raw_excerpt_hints: dict[str, list[str]] = {}
    raw_turn_refs: dict[str, set[str]] = {}
    selected_episode_ids: set[str] = set()
    selected_platform_record_ids: set[str] = set()

    if selected["profile_fields"]:
        profile = wiki.load_profile()
        if profile:
            profile_payload = _filter_profile_fields(
                profile.model_dump(mode="json"),
                selected["profile_fields"],
                selected["profile_values"],
            )
            profile_payload = _compact_profile_for_injection(profile_payload)
            if profile_payload:
                payload["memory"]["profile"] = profile_payload
            if include_episode_evidence:
                selected_episode_ids.update(getattr(profile, "source_episode_ids", []) or [])
            if include_raw_evidence:
                profile_raw_ids, profile_hints, profile_turn_refs = _collect_raw_support_from_memory_object(profile, episodes_dir)
                raw_conversation_ids.update(profile_raw_ids)
                _merge_raw_hint_maps(raw_excerpt_hints, profile_hints)
                for conv_id, refs in profile_turn_refs.items():
                    raw_turn_refs.setdefault(conv_id, set()).update(refs)
                selected_platform_record_ids.update(_collect_platform_support_from_memory_object(profile))

    if selected["preferences_fields"]:
        preferences = wiki.load_preferences()
        preferences_payload = preferences.model_dump(mode="json") if preferences else _preferences_payload_fallback(settings)
        if preferences_payload:
            filtered_preferences = _filter_preference_fields(
                preferences_payload,
                selected["preferences_fields"],
                selected["preferences_values"],
            )
            filtered_preferences = _compact_preferences_for_injection(filtered_preferences)
            if filtered_preferences:
                payload["memory"]["preferences"] = filtered_preferences
            if include_episode_evidence:
                if preferences is not None:
                    selected_episode_ids.update(getattr(preferences, "source_episode_ids", []) or [])
                task_type_values = filtered_preferences.get("primary_task_types")
                if isinstance(task_type_values, list):
                    selected_episode_ids.update(_episode_ids_for_primary_task_types(wiki.list_episodes(), task_type_values))
            if include_raw_evidence:
                pref_raw_ids, pref_hints, pref_turn_refs = _collect_raw_support_from_memory_object(preferences, episodes_dir)
                raw_conversation_ids.update(pref_raw_ids)
                _merge_raw_hint_maps(raw_excerpt_hints, pref_hints)
                for conv_id, refs in pref_turn_refs.items():
                    raw_turn_refs.setdefault(conv_id, set()).update(refs)
                if preferences is not None:
                    selected_platform_record_ids.update(_collect_platform_support_from_memory_object(preferences))

    if selected["projects"]:
        projects = _valid_projects(wiki)
        if "*" not in selected["projects"]:
            projects = [project for project in projects if project.project_name in selected["projects"]]
        projects_payload = [project.model_dump(mode="json") for project in projects]
        projects_payload = [
            compact
            for compact in (_compact_project_for_injection(project_payload) for project_payload in projects_payload)
            if compact
        ]
        if projects_payload:
            payload["memory"]["projects"] = projects_payload
        for project in projects:
            if include_episode_evidence:
                selected_episode_ids.update(getattr(project, "source_episode_ids", []) or [])
            if include_raw_evidence:
                project_raw_ids, project_hints, project_turn_refs = _collect_raw_support_from_memory_object(project, episodes_dir)
                raw_conversation_ids.update(project_raw_ids)
                _merge_raw_hint_maps(raw_excerpt_hints, project_hints)
                for conv_id, refs in project_turn_refs.items():
                    raw_turn_refs.setdefault(conv_id, set()).update(refs)
                selected_platform_record_ids.update(_collect_platform_support_from_memory_object(project))

    if selected["workflows"]:
        workflows = _valid_workflows(wiki)
        if "*" not in selected["workflows"]:
            workflows = [workflow for workflow in workflows if workflow.workflow_name in selected["workflows"]]
        workflows_payload = [workflow.model_dump(mode="json") for workflow in workflows]
        workflows_payload = [
            compact
            for compact in (_compact_workflow_for_injection(workflow_payload) for workflow_payload in workflows_payload)
            if compact
        ]
        if workflows_payload:
            payload["memory"]["workflows"] = workflows_payload
        for workflow in workflows:
            if include_episode_evidence:
                selected_episode_ids.update(getattr(workflow, "source_episode_ids", []) or [])
            if include_raw_evidence:
                workflow_raw_ids, workflow_hints, workflow_turn_refs = _collect_raw_support_from_memory_object(workflow, episodes_dir)
                raw_conversation_ids.update(workflow_raw_ids)
                _merge_raw_hint_maps(raw_excerpt_hints, workflow_hints)
                for conv_id, refs in workflow_turn_refs.items():
                    raw_turn_refs.setdefault(conv_id, set()).update(refs)
                selected_platform_record_ids.update(_collect_platform_support_from_memory_object(workflow))

    if selected["persistent"]:
        persistent = load_persistent_nodes(settings)
        nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
        if "*" in selected["persistent"]:
            selected_node_ids = set(nodes.keys())
        else:
            selected_node_ids = set(selected["persistent"])
        selected_nodes: list[dict[str, Any]] = []
        for node_id in sorted(selected_node_ids):
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                continue
            node_payload = _persistent_node_for_injection(node_id, node)
            if node_payload:
                selected_nodes.append(node_payload)
            if include_episode_evidence:
                selected_episode_ids.update(node.get("episode_refs", []))
            if include_raw_evidence:
                for turn_id in node.get("turn_refs", []) or []:
                    turn_text = str(turn_id or "").strip()
                    if not turn_text:
                        continue
                    conv_id = turn_text.split(":turn:", 1)[0]
                    if conv_id:
                        raw_conversation_ids.add(conv_id)
                        raw_turn_refs.setdefault(conv_id, set()).add(turn_text)
        if selected_nodes:
            payload["memory"]["persistent_nodes"] = selected_nodes

    if include_episode_evidence and selected_episode_ids:
        if detailed_injection:
            selected_episode_ids = _expand_episode_ids_with_connections(episodes_dir, selected_episode_ids)
        episode_records: list[dict[str, Any]] = []
        for ep_id in sorted(selected_episode_ids):
            episode = _read_episode_record(episodes_dir, ep_id)
            if episode:
                episode_records.append(episode)
        episode_records.sort(key=_episode_payload_sort_key)
        evidence = [
            _episode_summary_evidence_payload(episode, detailed=detailed_injection)
            for episode in episode_records
        ]
        if include_raw_evidence:
            episode_raw_ids, episode_hints, episode_turn_refs = _collect_raw_support_from_episode_ids(episodes_dir, selected_episode_ids)
            raw_conversation_ids.update(episode_raw_ids)
            _merge_raw_hint_maps(raw_excerpt_hints, episode_hints)
            for conv_id, refs in episode_turn_refs.items():
                raw_turn_refs.setdefault(conv_id, set()).update(refs)
        if evidence:
            payload["evidence"]["episodes"] = evidence

    if include_raw_evidence and selected_platform_record_ids:
        platform_record_map = _load_platform_memory_record_map(settings)
        platform_records = [
            platform_record_map[record_id]
            for record_id in sorted(selected_platform_record_ids)
            if record_id in platform_record_map
        ]
        if platform_records:
            payload["evidence"]["platform_memory_records"] = platform_records

    if include_raw_evidence and raw_conversation_ids:
        if raw_conversation_map is None:
            raw_conversation_map = _load_raw_conversation_object_map(settings)
        for conv_id in raw_conversation_ids:
            raw_excerpt_hints.setdefault(conv_id, [])
        related_turns = _build_related_qa_turns(
            raw_conversation_map,
            raw_excerpt_hints,
            turn_ref_map=raw_turn_refs,
            detailed=detailed_injection,
        )
        if related_turns:
            payload["evidence"]["raw_turns" if detailed_injection else "related_qa_turns"] = related_turns
        elif detailed_injection:
            raw_snippets = _build_relevant_raw_snippets(
                raw_conversation_map,
                raw_excerpt_hints,
                turn_ref_map=raw_turn_refs,
            )
            if raw_snippets:
                payload["evidence"]["relevant_raw_snippets"] = raw_snippets

    if not payload["memory"]:
        raise HTTPException(status_code=400, detail="请至少选择一项记忆内容")

    if not payload["evidence"]:
        payload.pop("evidence", None)

    payload["injection_mode"] = "detailed" if detailed_injection else "compact"
    return payload


def build_persistent_appendix(settings: dict[str, Any], selected_node_ids: set[str], include_evidence: bool) -> str:
    if not selected_node_ids:
        return ""

    root = get_storage_root(settings)
    persistent = load_persistent_nodes(settings)
    nodes = persistent.get("nodes", {})
    selected_nodes: list[dict[str, Any]] = []
    selected_episode_ids: set[str] = set()

    for node_id in selected_node_ids:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        selected_nodes.append({"id": node_id, **node})
        selected_episode_ids.update(node.get("episode_refs", []))

    if not selected_nodes:
        return ""

    payload: dict[str, Any] = {"persistent_nodes": selected_nodes}
    if include_evidence:
        episodes_dir = root / "episodes"
        evidence = []
        for ep_id in sorted(selected_episode_ids):
            data = _read_episode_record(episodes_dir, ep_id)
            if data:
                evidence.append(data)
        payload["episodic_evidence"] = evidence

    return "\n\n## Selected Persistent Memory\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _collect_recommendation_signals(settings: dict[str, Any]) -> set[str]:
    wiki = get_wiki(settings)
    signals: set[str] = set()

    preferences = wiki.load_preferences()
    if preferences:
        for value in [
            preferences.language_preference,
            preferences.response_granularity,
            *preferences.formatting_constraints,
            *preferences.revision_preference,
        ]:
            for token in str(value or "").lower().replace("/", " ").replace("_", " ").split():
                if token:
                    signals.add(token)

    profile = wiki.load_profile()
    if profile:
        for value in [
            profile.role_identity,
            profile.organization_or_affiliation,
            *profile.domain_background,
            *profile.common_languages,
            *profile.primary_task_types,
            *profile.long_term_research_or_work_focus,
        ]:
            for token in str(value or "").lower().replace("/", " ").replace("_", " ").split():
                if token:
                    signals.add(token)

    for workflow in wiki.load_workflows():
        for value in [
            workflow.workflow_name,
            workflow.trigger_condition,
            workflow.preferred_artifact_format,
            workflow.review_style,
            *workflow.typical_steps,
        ]:
            for token in str(value or "").lower().replace("/", " ").replace("_", " ").split():
                if token:
                    signals.add(token)

    for project in wiki.list_projects():
        for value in [
            project.project_name,
            project.project_goal,
            project.current_stage,
            *[entry.text for entry in project.next_actions[:3]],
            *[entry.text for entry in project.important_constraints[:2]],
        ]:
            for token in str(value or "").lower().replace("/", " ").replace("_", " ").split():
                if token:
                    signals.add(token)

    persistent = load_persistent_nodes(settings).get("nodes", {})
    for node in persistent.values():
        if not isinstance(node, dict):
            continue
        for value in [node.get("type", ""), node.get("key", ""), node.get("description", "")]:
            for token in str(value or "").lower().replace("/", " ").replace("_", " ").split():
                if token:
                    signals.add(token)

    return signals


def rank_recommended_skills(settings: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    saved_ids = set(settings.get("saved_skill_ids", []))
    dismissed_ids = set(settings.get("dismissed_skill_ids", []))
    items, meta = _refresh_recommended_skill_catalog(force=False)
    signals = _collect_recommendation_signals(settings)

    ranked: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or item.get("id") in dismissed_ids:
            continue
        enriched = _normalize_skill_record(item)
        if not _is_concrete_skill_record(
            title=str(enriched.get("title") or ""),
            trigger=str(enriched.get("trigger") or ""),
            goal=str(enriched.get("goal") or ""),
            steps=enriched.get("steps") or [],
            output_format=str(enriched.get("output_format") or ""),
        ):
            continue
        keywords = {
            token.strip().lower()
            for token in [
                *(enriched.get("keywords") or []),
                *(enriched.get("persona_signals") or []),
                *(enriched.get("tags") or []),
            ]
            if str(token).strip()
        }
        overlap = len(signals & keywords)
        base_score = float(enriched.get("usage_score", 0.5))
        score = round(base_score + overlap * 0.08, 3)
        enriched["selected"] = enriched["id"] in saved_ids
        enriched["match_score"] = score
        enriched["match_reason"] = "高度匹配" if overlap >= 3 else "较匹配" if overlap >= 1 else "通用推荐"
        enriched["catalog_summary"] = _extract_catalog_skill_summary(enriched)
        ranked.append(enriched)

    ranked.sort(key=lambda item: (-item.get("match_score", 0), item.get("title", "")))
    return ranked, meta


def export_memory_package(settings: dict[str, Any], payload: ExportPackageRequest) -> dict[str, Any]:
    package_payload = build_selected_memory_payload(
        settings,
        payload.selected_ids,
        include_episodic_evidence=payload.include_episodic_evidence,
        detailed_injection=bool(settings.get("detailed_injection")),
    )
    content = (
        "请将以下结构化记忆作为冷启动记忆包导入目标平台，并在后续对话中以其为参考。\n\n"
        + json.dumps(
            {
                "target_format": payload.target_format or "generic",
                "memory_package": package_payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return {
        "ok": True,
        "filename": f"memory_package_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        "content": content.strip(),
        "manifest": package_payload,
    }


def build_skill_records(settings: dict[str, Any], skill_ids: list[str]) -> list[dict[str, Any]]:
    saved_ids = set(settings.get("saved_skill_ids", []))
    my_skills = {item["id"]: item for item in derive_my_skills(settings)}
    recommended_items, _ = rank_recommended_skills(settings)
    recommended = {item["id"]: item for item in recommended_items}

    records: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        item = my_skills.get(skill_id) or recommended.get(skill_id)
        if item:
            record = dict(item)
            record["selected"] = skill_id in saved_ids
            records.append(record)
    return records


def build_skill_inject_text(settings: dict[str, Any], skill_ids: list[str], target_platform: str) -> str:
    skill_records = build_skill_records(settings, skill_ids)
    if not skill_records:
        return ""
    payload = {
        "target_platform": target_platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skills": [
            {
                "id": item["id"],
                "title": item["title"],
                "description": item["description"],
                "trigger": item.get("trigger", ""),
                "goal": item.get("goal", ""),
                "steps": item.get("steps", []),
                "output_format": item.get("output_format", ""),
                "guardrails": item.get("guardrails", []),
                "source_types": item.get("source_types", []),
                "confidence": item.get("confidence", ""),
                "skill_md": item.get("skill_md_content", ""),
                "forms_md": item.get("forms_md_content", ""),
                "reference_md": item.get("reference_md_content", ""),
            }
            for item in skill_records
        ],
    }
    return (
        f"请在当前 {target_platform} 会话中加载以下 Skill，并按照这些能力组织后续回答：\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

def build_skill_export_text(settings: dict[str, Any], skill_ids: list[str]) -> tuple[str, str]:
    skill_records = build_skill_records(settings, skill_ids)
    if not skill_records:
        return "", ""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skills": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "kind": item.get("kind", "skill"),
                "folder": _safe_slug(str(item.get("id") or item.get("title") or "skill")),
                "skill": {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "kind": item.get("kind", "skill"),
                    "trigger": item.get("trigger", ""),
                    "goal": item.get("goal", ""),
                    "steps": item.get("steps", []),
                    "output_format": item.get("output_format", ""),
                    "guardrails": item.get("guardrails", []),
                    "source_types": item.get("source_types", []),
                    "confidence": item.get("confidence", ""),
                    "selected": bool(item.get("selected", False)),
                },
                "SKILL.md": item.get("skill_md_content", ""),
                "forms.md": item.get("forms_md_content", ""),
                "reference.md": item.get("reference_md_content", ""),
                "scripts/README.md": item.get("scripts_readme", ""),
            }
            for item in skill_records
        ],
    }
    filename = f"skills_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return filename, json.dumps(payload, ensure_ascii=False, indent=2)

def test_openai_compat_connection(api_key: str, base_url: str) -> tuple[bool, str]:
    if not api_key:
        return False, "API Key 为空"
    normalized_base = str(base_url or "").strip().rstrip("/")
    if not normalized_base:
        return False, "Base URL 为空"

    request = urllib.request.Request(
        f"{normalized_base}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "qmem-local-backend",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, "可调用"
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 401, 403, 404}:
            return False, "当前默认配置不匹配这把 key"
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def update_timestamp(settings: dict[str, Any]) -> dict[str, Any]:
    return save_settings({"last_sync_at": datetime.now(timezone.utc).isoformat()})


def _load_persistent_distill_prompt() -> str:
    return (PROJECT_ROOT / "prompts" / "nodes" / "daily_notes_system.txt").read_text(encoding="utf-8")


def compute_l2_persistent_node_maintenance_signature(
    *,
    episode_signature: str,
    persistent_signature: str,
    l1_signature: str,
    persistent_node_ignore_signature: str = "",
) -> str:
    return _hash_payload(
        {
            "episode_signature": episode_signature,
            "persistent_signature": persistent_signature,
            "l1_signature": l1_signature,
            "persistent_node_ignore_signature": persistent_node_ignore_signature,
            "maintenance_version": L2_PERSISTENT_NODE_MAINTENANCE_VERSION,
            "prompt_hash": _hash_payload(_load_persistent_distill_prompt()),
        }
    )


def compute_persistent_node_ignore_signature(settings: dict[str, Any]) -> str:
    persistent_nodes = load_persistent_nodes(settings)
    return _hash_payload(
        {
            "deleted_node_locks": persistent_nodes.get("deleted_node_locks", []),
        }
    )


def refresh_organize_memory_signatures(settings: dict[str, Any]) -> None:
    try:
        wiki = get_wiki(settings)
        organize_state = load_organize_state(settings)
        _, l1_signature = load_l1_signals(settings)
        episode_signature = compute_episode_signature(wiki)
        persistent_signature = compute_persistent_signature(wiki, settings)
        node_maintenance_signature = compute_l2_persistent_node_maintenance_signature(
            episode_signature=episode_signature,
            persistent_signature=persistent_signature,
            l1_signature=l1_signature,
            persistent_node_ignore_signature=compute_persistent_node_ignore_signature(settings),
        )
        organize_state["l1_signature"] = l1_signature
        organize_state["episode_signature"] = episode_signature
        organize_state["persistent_signature"] = persistent_signature
        organize_state["persistent_rebuild_version"] = PERSISTENT_REBUILD_VERSION
        organize_state["node_maintenance_signature"] = node_maintenance_signature
        save_organize_state(settings, organize_state)
    except Exception:
        return


def _canonical_memory_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"([a-z0-9])([\u4e00-\u9fff])", r"\1 \2", text)
    text = re.sub(r"([\u4e00-\u9fff])([a-z0-9])", r"\1 \2", text)
    text = re.sub(r"[\-_/]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_overlap_text(value: Any) -> str:
    return _canonical_memory_text(value)


_PERSISTENT_SUPPORT_STOPWORDS = {
    "user", "assistant", "episode", "summary", "topic", "context", "memory", "node",
    "用户", "助手", "助理", "建议", "推荐", "询问", "了解", "选择", "偏好", "日常", "记忆",
    "上下文", "相关", "提供", "讨论", "表达", "希望", "需要", "可以", "适合", "关于",
    "进行", "寻找", "比较", "参考", "问题", "内容", "信息", "方向", "个人", "具体",
    "进一步", "尚未", "确认", "正在", "后续", "搭配", "选项", "场景", "上下游",
}

_PERSISTENT_SUPPORT_STOP_SUBSTRINGS = {
    "用户", "助手", "助理", "询问", "进一步", "尚未", "确认", "推荐", "建议",
    "寻找", "比较", "适合", "正在", "曾按", "曾建议", "具体", "后续",
}


def _is_memory_support_term(term: str) -> bool:
    if not term or len(term) < 2:
        return False
    if term in _PERSISTENT_SUPPORT_STOPWORDS:
        return False
    return not any(stop in term for stop in _PERSISTENT_SUPPORT_STOP_SUBSTRINGS)


def _memory_support_terms(value: Any) -> set[str]:
    text = _canonical_memory_text(value)
    if not text:
        return set()
    for phrase in sorted(_PERSISTENT_SUPPORT_STOP_SUBSTRINGS, key=len, reverse=True):
        text = text.replace(phrase, " ")
    text = re.sub(r"\s+", " ", text).strip()

    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9_]{2,}", text):
        token = token.strip("_")
        if _is_memory_support_term(token):
            terms.add(token)

    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if _is_memory_support_term(chunk) and 2 <= len(chunk) <= 12:
            terms.add(chunk)
        for size in (2, 3):
            if len(chunk) < size:
                continue
            for index in range(0, len(chunk) - size + 1):
                gram = chunk[index:index + size]
                if _is_memory_support_term(gram):
                    terms.add(gram)

    return {term for term in terms if _is_memory_support_term(term)}


def _daily_note_existing_anchor_texts(settings: dict[str, Any]) -> list[str]:
    nodes = load_persistent_nodes(settings).get("nodes", {})
    anchors: list[str] = []
    if isinstance(nodes, dict):
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            text = " ".join(
                str(value or "")
                for value in [
                    node.get("key"),
                    node.get("description"),
                    json.dumps(node.get("display"), ensure_ascii=False) if isinstance(node.get("display"), dict) else "",
                ]
            ).strip()
            if text:
                anchors.append(text)
    return anchors


def _daily_note_semantic_score(settings: dict[str, Any], episode: Any) -> float:
    text = _episode_support_text(episode)
    anchors = [*_DAILY_NOTE_SEMANTIC_ANCHORS, *_daily_note_existing_anchor_texts(settings)]
    return _best_semantic_similarity(text, anchors)


def _project_only_semantic_score(episode: Any) -> float:
    return _best_semantic_similarity(_episode_support_text(episode), _PROJECT_ONLY_SEMANTIC_ANCHORS)


def _persistent_node_support_text(node: dict[str, Any]) -> str:
    display = node.get("display") if isinstance(node.get("display"), dict) else {}
    display_text = ""
    if isinstance(display, dict):
        display_text = json.dumps(display, ensure_ascii=False)
    return " ".join(
        str(value or "")
        for value in [
            node.get("key"),
            node.get("description"),
            node.get("display_title"),
            node.get("display_summary"),
            display_text,
        ]
    )


def _persistent_node_matches_deleted_lock(
    pn_data: dict[str, Any],
    candidate_node: dict[str, Any],
    refs: list[str],
) -> bool:
    if not refs:
        return False
    candidate_text = _persistent_node_support_text(candidate_node)
    candidate_terms = _memory_support_terms(candidate_text)
    candidate_refs = set(refs)
    locks = pn_data.get("deleted_node_locks", [])
    if not isinstance(locks, list):
        return False
    for lock in locks:
        if not isinstance(lock, dict):
            continue
        lock_refs = {str(ref).strip() for ref in (lock.get("episode_refs") or []) if str(ref).strip()}
        if not lock_refs or not (candidate_refs & lock_refs):
            continue
        lock_text = " ".join(str(lock.get(field) or "") for field in ["key", "description"])
        lock_terms = _memory_support_terms(lock_text)
        if candidate_refs <= lock_refs and candidate_terms and lock_terms and candidate_terms & lock_terms:
            return True
        if _semantic_similarity(candidate_text, lock_text) >= 0.12:
            return True
    return False


def _episode_support_text(episode: Any) -> str:
    display = getattr(episode, "display", {}) or {}
    display_texts: list[str] = []
    if isinstance(display, dict):
        for value in display.values():
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            if isinstance(value, dict):
                display_texts.extend(str(item or "") for item in value.values())
    return " ".join(
        str(value or "")
        for value in [
            getattr(episode, "topic", ""),
            getattr(episode, "summary", ""),
            " ".join(getattr(episode, "topics_covered", []) or []),
            " ".join(getattr(episode, "key_decisions", []) or []),
            " ".join(getattr(episode, "open_issues", []) or []),
            " ".join(display_texts),
        ]
    )


def _episode_supports_persistent_node(node: dict[str, Any], episode: Any) -> bool:
    """Require direct semantic support before linking an episode to a daily note."""
    if episode is None:
        return False
    node_terms = _memory_support_terms(_persistent_node_support_text(node))
    episode_terms = _memory_support_terms(_episode_support_text(episode))
    if node_terms and episode_terms:
        overlap = node_terms & episode_terms
        if len(overlap) >= 2:
            return True

        if any(len(term) >= 4 for term in overlap):
            return True

    return _semantic_similarity(_persistent_node_support_text(node), _episode_support_text(episode)) >= 0.12


def _persistent_node_is_project_like(node: dict[str, Any]) -> bool:
    text = _normalize_overlap_text(" ".join([
        str(node.get("key") or ""),
        str(node.get("description") or ""),
    ]))
    project_shape_tokens = {
        "project", "platform", "system", "framework", "mvp", "prototype", "build", "develop",
        "evaluation", "benchmark", "leaderboard",
        "项目", "平台", "系统", "框架", "构建", "搭建", "开发", "推进", "评测", "排行榜",
    }
    project_decision_tokens = {
        "positioning", "architecture", "roadmap", "diagnostic", "pipeline", "dataset",
        "定位", "架构", "路线", "能力诊断", "数据集", "指标", "模块",
    }
    return any(token in text for token in project_shape_tokens) or (
        any(token in text for token in project_decision_tokens)
        and any(token in text for token in {"用户", "user", "倾向", "关注", "prefer", "focus"})
    )


def _persistent_node_overlaps_project(node: dict[str, Any], project: ProjectMemory) -> bool:
    node_type = str(node.get("type") or "").strip().lower()
    if node_type not in {"topic", "preference"}:
        return False
    if not _persistent_node_is_project_like(node):
        return False

    node_refs = {str(ref).strip() for ref in (node.get("episode_refs") or []) if str(ref).strip()}
    node_turn_refs = {str(ref).strip() for ref in (node.get("turn_refs") or []) if str(ref).strip()}
    project_refs = set(getattr(project, "source_episode_ids", []) or [])
    project_turn_refs = set(getattr(project, "source_turn_refs", []) or [])
    has_episode_overlap = bool(node_refs & project_refs)
    has_turn_overlap = bool(node_turn_refs & project_turn_refs)

    node_text = _normalize_overlap_text(" ".join([
        str(node.get("key") or ""),
        str(node.get("description") or ""),
    ]))
    project_text = _normalize_overlap_text(" ".join([
        project.project_name,
        project.project_goal,
        project.current_stage,
        " ".join(entry.text for entry in project.finished_decisions[:5]),
        " ".join(entry.text for entry in project.unresolved_questions[:5]),
        " ".join(entry.text for entry in project.relevant_entities[:8]),
        " ".join(entry.text for entry in project.important_constraints[:5]),
        " ".join(entry.text for entry in project.next_actions[:5]),
    ]))
    lexical_overlap = False
    if node_text and project_text:
        project_tokens = [
            token
            for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", project_text)
            if token and len(token) >= 2
        ]
        lexical_overlap = (
            node_text in project_text
            or project_text in node_text
            or sum(1 for token in project_tokens if token in node_text) >= 2
        )

    return (has_episode_overlap or has_turn_overlap) and lexical_overlap


def _prune_persistent_nodes_against_projects(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return payload

    wiki = get_wiki(settings)
    projects = _valid_projects(wiki)
    if not projects:
        return payload

    pruned_nodes: dict[str, Any] = {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        if any(_persistent_node_overlaps_project(node, project) for project in projects):
            continue
        pruned_nodes[node_id] = node

    payload["nodes"] = pruned_nodes
    return payload


def _prune_persistent_node_support_refs(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        return payload

    try:
        episodes = get_wiki(settings).list_episodes()
    except Exception:
        return payload

    ep_by_id = {episode.episode_id: episode for episode in episodes}
    if not ep_by_id:
        return payload

    nodes_to_drop: list[str] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        node_for_match = {"id": node_id, **node}
        refs = [str(ref).strip() for ref in (node.get("episode_refs") or []) if str(ref).strip()]
        known_refs = [ref for ref in refs if ref in ep_by_id]
        if not known_refs:
            if refs:
                nodes_to_drop.append(str(node_id))
            continue

        kept_refs = [
            ref
            for ref in known_refs
            if _episode_supports_persistent_node(node_for_match, ep_by_id[ref])
        ]
        if not kept_refs:
            nodes_to_drop.append(str(node_id))
            continue

        allowed_turn_refs: list[str] = []
        for ref in kept_refs:
            for turn_ref in getattr(ep_by_id[ref], "turn_refs", []) or []:
                turn_ref = str(turn_ref).strip()
                if turn_ref and turn_ref not in allowed_turn_refs:
                    allowed_turn_refs.append(turn_ref)

        node["episode_refs"] = kept_refs
        existing_turn_refs = [str(ref).strip() for ref in (node.get("turn_refs") or []) if str(ref).strip()]
        if allowed_turn_refs:
            filtered_turn_refs = [ref for ref in existing_turn_refs if ref in allowed_turn_refs]
            node["turn_refs"] = filtered_turn_refs or allowed_turn_refs

    for node_id in nodes_to_drop:
        nodes.pop(node_id, None)

    return payload


def _persistent_node_refs(node: dict[str, Any], field: str) -> list[str]:
    return [str(ref).strip() for ref in (node.get(field) or []) if str(ref).strip()]


def _persistent_nodes_should_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_episode_refs = set(_persistent_node_refs(left, "episode_refs"))
    right_episode_refs = set(_persistent_node_refs(right, "episode_refs"))
    if not left_episode_refs or not right_episode_refs:
        return False

    overlap = left_episode_refs & right_episode_refs
    if not overlap:
        return False

    smaller_ref_count = min(len(left_episode_refs), len(right_episode_refs))
    if smaller_ref_count and len(overlap) == smaller_ref_count:
        return True

    left_terms = _memory_support_terms(_persistent_node_support_text(left))
    right_terms = _memory_support_terms(_persistent_node_support_text(right))
    term_overlap = left_terms & right_terms
    return len(overlap) >= 2 and bool(term_overlap)


def _merge_persistent_node_description(primary: dict[str, Any], secondary: dict[str, Any]) -> str:
    primary_description = str(primary.get("description") or "").strip()
    secondary_description = str(secondary.get("description") or "").strip()
    if not secondary_description:
        return primary_description
    if not primary_description:
        return secondary_description
    if secondary_description in primary_description:
        return primary_description
    if primary_description in secondary_description:
        return secondary_description
    return f"{primary_description} {secondary_description}"


def _merge_persistent_node_pair(primary: dict[str, Any], secondary: dict[str, Any]) -> None:
    for field in ("episode_refs", "turn_refs", "platform"):
        merged = _persistent_node_refs(primary, field)
        for ref in _persistent_node_refs(secondary, field):
            if ref not in merged:
                merged.append(ref)
        primary[field] = merged

    primary["description"] = _merge_persistent_node_description(primary, secondary)
    if not _node_display_entry(primary, str(primary.get("description") or primary.get("key") or "")):
        secondary_display = _node_display_entry(secondary, str(secondary.get("description") or secondary.get("key") or ""))
        if secondary_display is not None:
            primary["display"] = {
                "title": secondary_display.get("title", {}),
                "description": secondary_display.get("description", {}),
            }
    primary["updated_at"] = max(
        str(primary.get("updated_at") or ""),
        str(secondary.get("updated_at") or ""),
    ) or datetime.now(timezone.utc).isoformat()
    if not primary.get("primary_language") and secondary.get("primary_language"):
        primary["primary_language"] = secondary.get("primary_language")

    ref_count = len(primary.get("episode_refs") or [])
    if ref_count >= 4:
        primary["confidence"] = "high"
    elif ref_count >= 2:
        primary["confidence"] = "medium"


def _preferred_persistent_node_id(left_id: str, left: dict[str, Any], right_id: str, right: dict[str, Any]) -> str:
    left_type = str(left.get("type") or "").strip().lower()
    right_type = str(right.get("type") or "").strip().lower()
    if left_type == "preference" and right_type != "preference":
        return left_id
    if right_type == "preference" and left_type != "preference":
        return right_id
    if len(_persistent_node_refs(left, "episode_refs")) >= len(_persistent_node_refs(right, "episode_refs")):
        return left_id
    return right_id


def _merge_related_persistent_nodes(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict) or len(nodes) < 2:
        return payload

    changed = True
    while changed:
        changed = False
        node_ids = [node_id for node_id, node in nodes.items() if isinstance(node, dict)]
        for left_index, left_id in enumerate(node_ids):
            if left_id not in nodes:
                continue
            for right_id in node_ids[left_index + 1:]:
                if right_id not in nodes:
                    continue
                left = nodes[left_id]
                right = nodes[right_id]
                if not _persistent_nodes_should_merge(left, right):
                    continue
                target_id = _preferred_persistent_node_id(left_id, left, right_id, right)
                source_id = right_id if target_id == left_id else left_id
                _merge_persistent_node_pair(nodes[target_id], nodes[source_id])
                del nodes[source_id]
                changed = True
                break
            if changed:
                break

    payload["nodes"] = nodes
    return payload


def save_persistent_nodes(settings: dict[str, Any], data: dict[str, Any]) -> None:
    root = get_storage_root(settings, create=True)
    payload = _default_persistent_payload()
    if isinstance(data, dict):
        payload.update({
            "version": data.get("version", payload["version"]),
            "pn_next_id": data.get("pn_next_id", payload["pn_next_id"]),
            "episodic_tag_paths": data.get("episodic_tag_paths", payload["episodic_tag_paths"]),
            "nodes": data.get("nodes", payload["nodes"]),
            "deleted_node_locks": data.get("deleted_node_locks", payload["deleted_node_locks"]),
            "ignored_episode_ids": data.get("ignored_episode_ids", payload["ignored_episode_ids"]),
            "ignored_turn_refs": data.get("ignored_turn_refs", payload["ignored_turn_refs"]),
        })
    _clear_global_episode_ignores(payload)
    payload = _prune_persistent_nodes_against_projects(settings, payload)
    payload = _prune_persistent_node_support_refs(settings, payload)
    payload = _merge_related_persistent_nodes(payload)

    persistent_root = _persistent_root(root)
    persistent_root.mkdir(parents=True, exist_ok=True)
    for child in persistent_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        elif child.is_file():
            child.unlink()

    items: list[dict[str, Any]] = []
    nodes = payload.get("nodes", {})
    if isinstance(nodes, dict):
        for node_id, node in sorted(nodes.items()):
            if not isinstance(node, dict):
                continue
            node_dir = _persistent_node_dir(root, str(node_id))
            node_dir.mkdir(parents=True, exist_ok=True)
            node_payload = {"id": node_id, **node}
            (node_dir / "node.json").write_text(
                json.dumps(node_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (node_dir / "node.md").write_text(
                _persistent_node_markdown(str(node_id), node),
                encoding="utf-8",
            )
            items.append(node_payload)

    index_payload = {
        "version": payload.get("version", "1.1"),
        "pn_next_id": payload.get("pn_next_id", 1),
        "episodic_tag_paths": payload.get("episodic_tag_paths", []),
        "deleted_node_locks": payload.get("deleted_node_locks", []),
        "ignored_episode_ids": payload.get("ignored_episode_ids", []),
        "ignored_turn_refs": payload.get("ignored_turn_refs", []),
        "item_count": len(items),
        "items": items,
    }
    _persistent_index_path(root).write_text(
        json.dumps(index_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (persistent_root / "README.md").write_text(
        "# Daily Notes\n\n"
        "此目录存放“日常记忆”层的节点化记忆资产，包含可复用的非项目类生活上下文、个人选择、约束条件和小事实。\n\n"
        "- `index.json`：索引与汇总\n"
        "- `<node-id>/node.json`：单条节点结构化数据\n"
        "- `<node-id>/node.md`：单条节点说明\n",
        encoding="utf-8",
    )

    legacy_path = _legacy_persistent_path(root)
    if legacy_path.exists():
        legacy_path.unlink()

    legacy_root = _legacy_interest_discoveries_root(root)
    if legacy_root.exists() and legacy_root != persistent_root:
        shutil.rmtree(legacy_root)


def apply_persistent_result(
    pn_data: dict[str, Any],
    result: dict[str, Any],
    episode_id: str,
    platform: str,
    turn_refs: list[str] | None = None,
    primary_language: str = "",
    support_turn_refs_by_episode: dict[str, list[str]] | None = None,
    support_episodes_by_id: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    nodes = pn_data.setdefault("nodes", {})
    pn_data.setdefault("pn_next_id", 1)
    support_turn_refs_by_episode = support_turn_refs_by_episode or {}
    support_episodes_by_id = support_episodes_by_id or {}

    def support_refs(item: dict[str, Any], node: dict[str, Any]) -> tuple[list[str], list[str]]:
        allowed_ids = {episode_id, *support_turn_refs_by_episode.keys()}
        refs: list[str] = []
        for raw_ref in [episode_id, *(item.get("support_episode_ids") or [])]:
            ref = str(raw_ref or "").strip()
            support_episode = support_episodes_by_id.get(ref)
            if (
                ref
                and ref in allowed_ids
                and ref not in refs
                and support_episode is not None
                and _episode_supports_persistent_node(node, support_episode)
            ):
                refs.append(ref)
        turn_ids: list[str] = []
        for ref in refs:
            for turn_ref in support_turn_refs_by_episode.get(ref, []):
                if turn_ref and turn_ref not in turn_ids:
                    turn_ids.append(turn_ref)
        return refs, turn_ids

    def apply_display(item: dict[str, Any], node: dict[str, Any]) -> None:
        display_entry = _daily_note_display_entry_from_result(
            item.get("display"),
            str(node.get("description") or node.get("key") or ""),
        )
        if display_entry is not None:
            node["display"] = {
                "title": display_entry.get("title", {}),
                "description": display_entry.get("description", {}),
            }

    for upd in result.get("updates", []):
        node = nodes.get(upd.get("id"))
        if not node:
            continue
        refs, turn_ids = support_refs(upd, node)
        if not refs:
            continue
        for ref in refs:
            if ref not in (node.get("episode_refs") or []):
                node["episode_refs"] = [*(node.get("episode_refs") or []), ref]
        for turn_ref in turn_ids:
            if turn_ref not in (node.get("turn_refs") or []):
                node["turn_refs"] = [*(node.get("turn_refs") or []), turn_ref]
        if platform and platform not in (node.get("platform") or []):
            node["platform"] = [*(node.get("platform") or []), platform]
        if upd.get("description"):
            node["description"] = upd["description"]
        apply_display(upd, node)
        if primary_language:
            node["primary_language"] = primary_language
        if upd.get("confidence"):
            node["confidence"] = upd["confidence"]
        node["updated_at"] = now

    for new_node in result.get("new_nodes", []):
        candidate_node = {
            "type": new_node.get("type"),
            "key": new_node.get("key"),
            "description": new_node.get("description"),
        }
        refs, turn_ids = support_refs(new_node, candidate_node)
        if not refs:
            continue
        if _persistent_node_matches_deleted_lock(pn_data, candidate_node, refs):
            continue
        node_id = f"pn_{str(pn_data['pn_next_id']).zfill(4)}"
        pn_data["pn_next_id"] += 1
        nodes[node_id] = {
            "type": new_node["type"],
            "key": new_node["key"],
            "description": new_node["description"],
            "episode_refs": refs,
            "turn_refs": turn_ids,
            "platform": [platform] if platform else [],
            "confidence": "low",
            "export_priority": new_node.get("export_priority", "medium"),
            "primary_language": primary_language,
            "created_at": now,
            "updated_at": now,
        }
        apply_display(new_node, nodes[node_id])

    for merge in result.get("merges", []):
        target = nodes.get(merge.get("merged_into"))
        if not target:
            continue
        merged_from = merge.get("merged_from")
        sources = merged_from if isinstance(merged_from, list) else [merged_from]
        for src_id in sources:
            source = nodes.get(src_id)
            if not source:
                continue
            for ref in source.get("episode_refs", []):
                if ref not in (target.get("episode_refs") or []):
                    target["episode_refs"] = [*(target.get("episode_refs") or []), ref]
            for turn_ref in source.get("turn_refs", []):
                if turn_ref not in (target.get("turn_refs") or []):
                    target["turn_refs"] = [*(target.get("turn_refs") or []), turn_ref]
            for src_platform in source.get("platform", []):
                if src_platform not in (target.get("platform") or []):
                    target["platform"] = [*(target.get("platform") or []), src_platform]
            if not target.get("primary_language") and source.get("primary_language"):
                target["primary_language"] = source.get("primary_language")
            del nodes[src_id]
        ref_count = len(target.get("episode_refs") or [])
        if ref_count >= 4:
            target["confidence"] = "high"
        elif ref_count >= 2:
            target["confidence"] = "medium"
        if merge.get("description"):
            target["description"] = merge["description"]
        apply_display(merge, target)
        if primary_language:
            target["primary_language"] = primary_language
        target["updated_at"] = now


def update_persistent_nodes_for_episode(
    settings: dict[str, Any],
    llm: LLMClient,
    episode: Any,
) -> None:
    update_persistent_nodes_for_episodes(settings, llm, [episode])


def _dominant_language_from_episodes(episodes: list[Any]) -> str:
    counts: dict[str, int] = {}
    for episode in episodes:
        language = str(getattr(episode, "primary_language", "") or "").strip().lower()
        if language not in {"zh", "en"}:
            language = detect_primary_language(
                " ".join(
                    [
                        str(getattr(episode, "topic", "") or ""),
                        str(getattr(episode, "summary", "") or ""),
                        " ".join(getattr(episode, "key_decisions", []) or []),
                        " ".join(getattr(episode, "open_issues", []) or []),
                    ]
                )
            )
        if language:
            counts[language] = counts.get(language, 0) + 1
    if not counts:
        return ""
    return max(counts.items(), key=lambda item: item[1])[0]


def _ensure_persistent_result_support_refs(result: dict[str, Any], fallback_episode_ids: list[str]) -> None:
    if len(fallback_episode_ids) != 1:
        return
    fallback = fallback_episode_ids[0]
    for section in ("updates", "new_nodes"):
        for item in result.get(section, []) or []:
            if isinstance(item, dict) and not item.get("support_episode_ids"):
                item["support_episode_ids"] = [fallback]


def _episode_has_daily_note_candidate(settings: dict[str, Any], episode: Any) -> bool:
    if _is_bootstrap_memory_import_episode(episode):
        return False
    text = _canonical_memory_text(
        " ".join(
            [
                str(getattr(episode, "topic", "") or ""),
                str(getattr(episode, "summary", "") or ""),
                " ".join(getattr(episode, "topics_covered", []) or []),
                " ".join(getattr(episode, "key_decisions", []) or []),
                " ".join(getattr(episode, "open_issues", []) or []),
            ]
        )
    )
    if not text:
        return False
    daily_score = _daily_note_semantic_score(settings, episode)
    project_score = _project_only_semantic_score(episode)
    project_only = bool(getattr(episode, "relates_to_projects", None)) and not getattr(
        episode,
        "relates_to_preferences",
        False,
    )
    if project_only and project_score >= max(0.18, daily_score + 0.04):
        return False
    if daily_score >= 0.08:
        return True
    if project_only:
        return False
    if getattr(episode, "relates_to_preferences", False):
        assistant_only_markers = {
            "assistant suggested", "assistant recommended", "助理建议", "助手建议", "助手推荐", "assistant offered",
        }
        if any(marker in text for marker in assistant_only_markers):
            return False
        return True
    # Do not use keyword matching as a hard gate. Non-project episodes are sent
    # to the daily_notes maintenance prompt, which decides whether to create,
    # update, or ignore a node based on evidence boundaries.
    return True


def update_persistent_nodes_for_episodes(
    settings: dict[str, Any],
    llm: LLMClient,
    episodes: list[Any],
) -> bool:
    episodes = [episode for episode in episodes if _episode_has_daily_note_candidate(settings, episode)]
    if not episodes:
        return False

    pn_data = load_persistent_nodes(settings)
    existing_summary = [
        {
            "id": node_id,
            "type": node.get("type"),
            "key": node.get("key"),
            "description": node.get("description"),
            "display": node.get("display"),
            "refs": len(node.get("episode_refs") or []),
        }
        for node_id, node in pn_data.get("nodes", {}).items()
    ]
    wiki = get_wiki(settings)
    support_turn_refs_by_episode: dict[str, list[str]] = {}
    support_episodes_by_id: dict[str, Any] = {}
    episode_summaries: list[dict[str, Any]] = []
    platforms = {str(getattr(episode, "platform", "") or "").strip() for episode in episodes if str(getattr(episode, "platform", "") or "").strip()}

    for episode in episodes:
        episode_id = str(getattr(episode, "episode_id", "") or "").strip()
        if not episode_id:
            continue
        support_turn_refs_by_episode[episode_id] = [
            str(ref).strip() for ref in (getattr(episode, "turn_refs", []) or []) if str(ref).strip()
        ]
        support_episodes_by_id[episode_id] = episode
        connected_episode_summaries: list[dict[str, Any]] = []
        for connection in (getattr(episode, "connections", []) or [])[:4]:
            if str(getattr(connection, "relation", "") or "") not in {"preferences", "persistent_node", "conversation_context"}:
                continue
            connected = wiki.load_episode(str(getattr(connection, "episode_id", "") or ""))
            if not connected:
                continue
            support_episodes_by_id[connected.episode_id] = connected
            support_turn_refs_by_episode[connected.episode_id] = [
                str(ref).strip() for ref in (connected.turn_refs or []) if str(ref).strip()
            ]
            connected_episode_summaries.append(
                {
                    "episode_id": connected.episode_id,
                    "relation": getattr(connection, "relation", ""),
                    "topic": connected.topic,
                    "summary": connected.summary,
                }
            )
        episode_summaries.append(
            {
                "episode_id": episode_id,
                "topic": getattr(episode, "topic", "") or "",
                "primary_language": getattr(episode, "primary_language", "") or "",
                "summary": getattr(episode, "summary", "") or "",
                "key_decisions": (getattr(episode, "key_decisions", []) or [])[:3],
                "open_issues": (getattr(episode, "open_issues", []) or [])[:2],
                "relates_to_projects": getattr(episode, "relates_to_projects", []) or [],
                "daily_note_semantic_score": round(_daily_note_semantic_score(settings, episode), 3),
                "project_only_semantic_score": round(_project_only_semantic_score(episode), 3),
                "connected_episode_summaries": connected_episode_summaries,
            }
        )

    if not episode_summaries:
        return False

    primary_language = _dominant_language_from_episodes(episodes)
    language_context = {
        "primary_language": primary_language,
        "policy": (
            "description 使用中文，必要专名和技术词保留原文"
            if primary_language == "zh"
            else (
                "description uses English; preserve necessary proper nouns and technical terms"
                if primary_language == "en"
                else "infer from episode language; preserve necessary proper nouns and technical terms"
            )
        ),
    }
    user_prompt = (
        f"【TARGET DISPLAY LANGUAGE】\n{json.dumps(language_context, ensure_ascii=False, indent=2)}\n\n"
        f"【现有 Persistent 节点】\n{json.dumps(existing_summary, ensure_ascii=False, indent=2)}\n\n"
        f"【新 Episodic 记忆内容】\n{json.dumps(episode_summaries, ensure_ascii=False, indent=2)}"
    )
    result = llm.extract_json(_load_persistent_distill_prompt(), user_prompt)
    if isinstance(result, dict) and result:
        _ensure_persistent_result_support_refs(
            result,
            [str(getattr(episode, "episode_id", "") or "").strip() for episode in episodes if str(getattr(episode, "episode_id", "") or "").strip()],
        )
        apply_persistent_result(
            pn_data,
            result,
            "",
            next(iter(platforms)) if len(platforms) == 1 else "",
            [],
            primary_language,
            support_turn_refs_by_episode,
            support_episodes_by_id,
        )
        save_persistent_nodes(settings, pn_data)
        return True
    return False


def _is_bootstrap_memory_import_episode(episode: Any) -> bool:
    platform = str(getattr(episode, "platform", "") or "").strip().lower()
    topic = str(getattr(episode, "topic", "") or "").strip().lower()
    summary = str(getattr(episode, "summary", "") or "").strip().lower()
    topics = [str(item or "").strip().lower() for item in (getattr(episode, "topics_covered", []) or [])]
    key_decisions = [str(item or "").strip().lower() for item in (getattr(episode, "key_decisions", []) or [])]

    if platform != "text_import":
        return False

    marker_hits = 0
    markers = [
        "memory import",
        "cold start",
        "memory_package",
        "memory package",
        "profile setup",
        "import the provided memory package",
        "structured cold-start memory package",
        "冷启动记忆包",
        "结构化记忆",
        "导入目标平台",
    ]

    haystacks = [topic, summary, *topics, *key_decisions]
    for marker in markers:
        if any(marker in haystack for haystack in haystacks if haystack):
            marker_hits += 1

    return marker_hits >= 2


def rebuild_persistent_nodes(
    settings: dict[str, Any],
    llm: LLMClient,
    episodes: list[EpisodicMemory],
    job_id: str,
    total_steps: int,
    *,
    reset: bool = True,
) -> dict[str, Any]:
    if reset:
        previous = load_persistent_nodes(settings)
        pn_data = {
            "version": "1.1",
            "pn_next_id": 1,
            "episodic_tag_paths": [],
            "nodes": {},
            "deleted_node_locks": previous.get("deleted_node_locks", []),
            "ignored_episode_ids": previous.get("ignored_episode_ids", []),
            "ignored_turn_refs": previous.get("ignored_turn_refs", []),
        }
        save_persistent_nodes(settings, pn_data)
    elif _persistent_node_assets_missing(settings):
        previous = load_persistent_nodes(settings)
        pn_data = {
            "version": "1.1",
            "pn_next_id": 1,
            "episodic_tag_paths": [],
            "nodes": {},
            "deleted_node_locks": previous.get("deleted_node_locks", []),
            "ignored_episode_ids": previous.get("ignored_episode_ids", []),
            "ignored_turn_refs": previous.get("ignored_turn_refs", []),
        }
        save_persistent_nodes(settings, pn_data)
        reset = True

    batch_size = _persistent_node_batch_size(settings)
    llm_calls = 0
    batches = [episodes[index:index + batch_size] for index in range(0, len(episodes), batch_size)]
    for batch_index, episode_batch in enumerate(batches, start=1):
        update_job(
            job_id,
            status="running",
            progress={
                "current": total_steps,
                "total": total_steps,
                "message": "正在维护结构化记忆节点...",
            },
        )
        if update_persistent_nodes_for_episodes(settings, llm, episode_batch):
            llm_calls += 1

    final_nodes = load_persistent_nodes(settings)
    return {
        "persistent_nodes": len(final_nodes.get("nodes", {})),
        "persistent_node_episodes_processed": len(episodes),
        "persistent_node_full_rebuild": reset,
        "persistent_node_llm_calls": llm_calls,
        "persistent_node_batch_size": batch_size,
    }


def connect_episodes_by_persistent_nodes(settings: dict[str, Any], wiki: L2Wiki) -> None:
    episodes = wiki.list_episodes()
    ep_by_id = {episode.episode_id: episode for episode in episodes}
    for episode in episodes:
        original_count = len(episode.connections)
        episode.connections = [
            connection
            for connection in episode.connections
            if connection.relation != "persistent_node"
        ]
        if len(episode.connections) != original_count:
            wiki.save_episode(episode)
    nodes = load_persistent_nodes(settings).get("nodes", {})
    changed: set[str] = set()
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        refs = [str(ref).strip() for ref in (node.get("episode_refs") or []) if str(ref).strip() in ep_by_id]
        if len(refs) < 2:
            continue
        display_entry = _node_display_entry(node, str(node.get("description") or node.get("key") or node_id))
        display_title = _display_text(display_entry.get("title"), "zh", "") if display_entry else ""
        label = str(display_title or node.get("key") or node.get("description") or node_id).strip()[:80]
        for ref in refs:
            episode = ep_by_id[ref]
            for other_ref in refs[:20]:
                if other_ref == ref:
                    continue
                connection = EpisodeConnection(
                    episode_id=other_ref,
                    relation="persistent_node",
                    key=label,
                    reason="same persistent memory node",
                )
                if not any(
                    existing.episode_id == connection.episode_id
                    and existing.relation == connection.relation
                    and existing.key == connection.key
                    for existing in episode.connections
                ):
                    episode.connections.append(connection)
                    changed.add(ref)
    for episode_id in changed:
        wiki.save_episode(ep_by_id[episode_id])


def rebuild_persistent_memory(
    settings: dict[str, Any],
    builder: MemoryBuilder,
    l1_layer: L1SignalLayer,
    job_id: str,
    current_step: int,
    total_steps: int,
) -> dict[str, Any]:
    wiki = get_wiki(settings)
    episodes = wiki.list_episodes()
    l1_text = l1_layer.combined_text()
    platform_records = load_platform_memory_records(settings)
    if not episodes and not l1_text and not platform_records:
        wiki.rebuild_index()
        return {"profile": False, "preferences": False, "projects": 0, "workflows": 0, "index": wiki.get_index()}

    ep_by_id = {ep.episode_id: ep for ep in episodes}
    earliest_ts = min((ep.time_range_start for ep in episodes if ep.time_range_start), default=None)

    profile_ep_ids = [ep.episode_id for ep in episodes if ep.relates_to_profile]
    pref_ep_ids = [ep.episode_id for ep in episodes if ep.relates_to_preferences]
    project_ep_map: dict[str, list[str]] = {}
    workflow_ep_map: dict[str, list[str]] = {}
    for ep in episodes:
        for project_name in ep.relates_to_projects:
            project_ep_map.setdefault(project_name, []).append(ep.episode_id)
        for workflow_name in ep.relates_to_workflows:
            workflow_ep_map.setdefault(workflow_name, []).append(ep.episode_id)
    builder.maintain_episode_connections(
        episodes,
        profile_ep_ids,
        pref_ep_ids,
        project_ep_map,
        workflow_ep_map,
    )

    def stage(message: str, offset: int) -> None:
        update_job(
            job_id,
            status="running",
            progress={"current": current_step + offset, "total": total_steps, "message": message},
        )

    stage("正在并行整理画像、偏好和项目...", 1)
    profile_context = builder._filter_digest(episodes, l1_text, "profile")
    prefs_context = builder._filter_digest(episodes, l1_text, "preferences")
    projects_context = builder._filter_digest(episodes, l1_text, "projects")
    with ThreadPoolExecutor(max_workers=3) as executor:
        profile_future = executor.submit(builder.llm.extract_json, builder.prompts["profile_system"], profile_context)
        prefs_future = executor.submit(builder.llm.extract_json, builder.prompts["preference_system"], prefs_context)
        projects_future = executor.submit(builder.llm.extract_json, builder.prompts["projects_system"], projects_context)
        profile_data = profile_future.result()
        prefs_data = prefs_future.result()
        projects_data = projects_future.result()

    profile = builder._build_profile(profile_data, l1_text, earliest_ts, profile_ep_ids, ep_by_id)
    profile, _ = apply_memory_ignore_rules(settings, profile=profile)
    wiki.save_profile(profile)

    stage("正在整理偏好设置...", 2)
    prefs = builder._build_preferences(prefs_data, l1_text, earliest_ts, pref_ep_ids, ep_by_id)
    profile, prefs = _merge_l1_claims_into_profile_preferences(settings, profile, prefs)
    if not pref_ep_ids and not l1_text:
        prefs.style_preference = []
        prefs.terminology_preference = []
        prefs.formatting_constraints = []
        prefs.forbidden_expressions = []
        prefs.revision_preference = []
        prefs.response_granularity = ""
    if not prefs.language_preference:
        dominant_language = builder._dominant_episode_language(episodes)
        if dominant_language:
            prefs.language_preference = dominant_language
    if profile.primary_task_types:
        profile.primary_task_types = []
    profile, prefs = apply_memory_ignore_rules(settings, profile=profile, preferences=prefs)
    if profile is not None:
        wiki.save_profile(profile)
    prefs.primary_task_types = _infer_primary_task_types_fallback(
        episodes,
        [],
        [],
        list(prefs.primary_task_types or []),
    )
    _, prefs = apply_memory_ignore_rules(settings, preferences=prefs)
    wiki.save_preferences(prefs)

    stage("正在整理项目记忆...", 3)
    _clear_project_assets_for_rebuild(settings)
    projects = builder._build_projects(projects_data, l1_text, earliest_ts, project_ep_map, ep_by_id)
    projects = [project for project in projects if _looks_like_stable_project(project)]
    existing_projects = {project.project_name for project in wiki.list_projects()}
    current_projects = {project.project_name for project in projects}
    for stale_project in sorted(existing_projects - current_projects):
        stale_path = wiki._project_path(stale_project)
        stale_json = stale_path.with_suffix(".json")
        stale_md = stale_path.with_suffix(".md")
        if stale_json.exists():
            stale_json.unlink()
        if stale_md.exists():
            stale_md.unlink()
    for project in projects:
        wiki.save_project(project)
    profile = _merge_project_focus_into_profile(profile, projects)
    profile, _ = apply_memory_ignore_rules(settings, profile=profile)
    wiki.save_profile(profile)

    platform_workflows = _platform_workflows_from_records(settings)
    workflow_extraction_skipped = False
    stage("正在整理工作流...", 4)
    if _has_workflow_extraction_candidates(episodes, l1_text, platform_workflows):
        workflows_context = builder._filter_digest(episodes, l1_text, "workflows")
        workflows_data = builder.llm.extract_json(builder.prompts["workflows_system"], workflows_context)
        workflows = builder._build_workflows(workflows_data, l1_text, earliest_ts, workflow_ep_map, ep_by_id)
    else:
        workflows_data = []
        workflows = []
        workflow_extraction_skipped = True
    workflow_map: dict[str, WorkflowMemory] = {}
    for workflow in [*workflows, *platform_workflows]:
        if not _looks_like_stable_workflow(workflow):
            continue
        existing = workflow_map.get(workflow.workflow_name)
        if existing is None:
            workflow_map[workflow.workflow_name] = workflow
            continue
        if len(workflow.typical_steps) > len(existing.typical_steps):
            existing.typical_steps = workflow.typical_steps
        existing.trigger_condition = existing.trigger_condition or workflow.trigger_condition
        existing.preferred_artifact_format = existing.preferred_artifact_format or workflow.preferred_artifact_format
        existing.review_style = existing.review_style or workflow.review_style
        existing.escalation_rule = existing.escalation_rule or workflow.escalation_rule
        existing.reuse_frequency = existing.reuse_frequency or workflow.reuse_frequency
        existing.occurrence_count = max(existing.occurrence_count, workflow.occurrence_count)
        existing.source_episode_ids = list(dict.fromkeys(existing.source_episode_ids + workflow.source_episode_ids))
        existing.source_turn_refs = list(dict.fromkeys(existing.source_turn_refs + workflow.source_turn_refs))
    workflows = list(workflow_map.values())
    wiki.save_workflows(workflows)
    save_workflow_asset_library(settings, workflows)

    prefs.primary_task_types = _infer_primary_task_types_fallback(
        episodes,
        projects,
        workflows,
        list(prefs.primary_task_types or []),
    )
    _, prefs = apply_memory_ignore_rules(settings, preferences=prefs)
    wiki.save_preferences(prefs)

    builder.maintain_episode_connections(
        episodes,
        list(profile.source_episode_ids or []),
        list(prefs.source_episode_ids or []),
        {project.project_name: list(project.source_episode_ids or []) for project in projects},
        {workflow.workflow_name: list(workflow.source_episode_ids or []) for workflow in workflows},
    )

    skills = derive_my_skills(settings)
    save_display_texts(
        settings,
        build_display_fallback_texts(
            profile,
            prefs,
            projects=projects,
            workflows=workflows,
            skills=skills,
        ),
    )

    stage("正在重建索引...", 5)
    index = wiki.rebuild_index()
    return {
        "profile": True,
        "preferences": True,
        "projects": len(projects),
        "workflows": len(workflows),
        "workflow_extraction_skipped": workflow_extraction_skipped,
        "index": index,
    }


def _run_organize_job(job_id: str, settings: dict[str, Any]) -> None:
    try:
        run_started = time.perf_counter()
        timings: dict[str, float] = {}
        organize_stats: dict[str, Any] = {
            "raw_conversations": 0,
            "raw_conversations_changed": 0,
            "raw_conversations_skipped": 0,
            "raw_turns_changed": 0,
            "raw_turns_skipped": 0,
            "episode_llm_calls": 0,
            "episodes_built": 0,
            "persistent_rebuilt": False,
            "persistent_nodes_maintained": False,
            "persistent_node_full_rebuild": False,
            "persistent_node_episodes_processed": 0,
            "persistent_node_llm_calls": 0,
            "episode_parallel_workers": 0,
        }

        stage_started = time.perf_counter()
        consolidate_result = consolidate_platform_memory(settings)
        timings["platform_memory_consolidation_sec"] = _elapsed_seconds(stage_started)
        update_job(
            job_id,
            status="running",
            progress={
                "current": 0,
                "total": 1,
                "message": "正在归并平台记忆...",
            },
        )
        stage_started = time.perf_counter()
        conversations = load_all_raw_conversations(settings)
        l1_layer, l1_signature = load_l1_signals(settings)
        timings["load_inputs_sec"] = _elapsed_seconds(stage_started)
        organize_stats["raw_conversations"] = len(conversations)
        if not conversations and not l1_signature:
            update_job(
                job_id,
                status="failed",
                progress={"current": 0, "total": 1, "message": "未找到可整理的历史对话"},
                error="No raw conversations found",
            )
            return

        llm = get_llm(settings)
        wiki = get_wiki(settings)
        builder = MemoryBuilder(llm=llm, wiki=wiki)
        organize_state = load_organize_state(settings)
        raw_index = organize_state.get("raw_index", {})
        changed_episodes: list[EpisodicMemory] = []
        previous_l1_signature = organize_state.get("l1_signature", "")
        previous_episode_signature = organize_state.get("episode_signature", "")
        previous_persistent_signature = organize_state.get("persistent_signature", "")
        previous_persistent_rebuild_version = organize_state.get("persistent_rebuild_version", "")
        previous_node_signature = organize_state.get("node_maintenance_signature", "")

        total_steps = max(len(conversations), 1) + 5
        current_step = 0

        episode_stage_started = time.perf_counter()
        changed_conversations: list[dict[str, Any]] = []
        episode_batches: list[dict[str, Any]] = []
        for conv in conversations:
            current_step += 1
            raw_key = f"{conv.platform}:{conv.conv_id}"
            signature = conversation_signature(conv)
            current_turn_signatures = conversation_turn_signatures(conv)
            current_turn_refs = list(current_turn_signatures.keys())
            existing_meta = raw_index.get(raw_key, {})
            previous_turn_signatures = (
                existing_meta.get("turn_signatures")
                if isinstance(existing_meta.get("turn_signatures"), dict)
                else {}
            )
            raw_turn_episode_ids = (
                existing_meta.get("turn_episode_ids")
                if isinstance(existing_meta.get("turn_episode_ids"), dict)
                else {}
            )
            previous_turn_episode_ids: dict[str, list[str]] = {}
            for turn_ref, ids in raw_turn_episode_ids.items():
                raw_ids = ids if isinstance(ids, list) else [ids]
                clean_ids = [str(item).strip() for item in raw_ids if str(item or "").strip()]
                previous_turn_episode_ids[str(turn_ref)] = clean_ids
            existing_episode_ids = list(
                dict.fromkeys(
                    [
                        episode_id
                        for ids in previous_turn_episode_ids.values()
                        for episode_id in ids
                    ]
                    or [
                        str(item).strip()
                        for item in (
                            existing_meta.get("episode_ids")
                            or ([existing_meta.get("episode_id")] if existing_meta.get("episode_id") else [])
                        )
                        if str(item or "").strip()
                    ]
                )
            )
            episodes_dir = wiki.wiki_dir / "episodes"

            update_job(
                job_id,
                status="running",
                progress={
                    "current": current_step,
                    "total": total_steps,
                    "message": "正在提取对话记忆...",
                },
            )

            schema_ok = (
                existing_meta.get("episode_schema") == EPISODE_SCHEMA_VERSION
                and isinstance(previous_turn_signatures, dict)
                and isinstance(raw_turn_episode_ids, dict)
            )
            episode_storage_ok = (
                not existing_episode_ids
                or _episode_container_has_ids(episodes_dir, conv.conv_id, existing_episode_ids)
            )
            turn_index_complete = all(turn_ref in previous_turn_episode_ids for turn_ref in current_turn_refs)
            if (
                schema_ok
                and episode_storage_ok
                and previous_turn_signatures == current_turn_signatures
                and turn_index_complete
            ):
                organize_stats["raw_conversations_skipped"] += 1
                organize_stats["raw_turns_skipped"] += len(current_turn_refs)
                continue

            organize_stats["raw_conversations_changed"] += 1
            if not schema_ok or not episode_storage_ok:
                changed_turn_refs = current_turn_refs
                removed_turn_refs: list[str] = []
                retained_turn_episode_ids: dict[str, list[str]] = {}
                episode_ids_to_remove = existing_episode_ids
            else:
                changed_turn_refs = [
                    turn_ref
                    for turn_ref, turn_sig in current_turn_signatures.items()
                    if previous_turn_signatures.get(turn_ref) != turn_sig
                    or turn_ref not in previous_turn_episode_ids
                ]
                removed_turn_refs = [
                    turn_ref
                    for turn_ref in previous_turn_signatures
                    if turn_ref not in current_turn_signatures
                ]
                retained_turn_episode_ids = {
                    turn_ref: previous_turn_episode_ids.get(turn_ref, [])
                    for turn_ref in current_turn_refs
                    if turn_ref not in changed_turn_refs
                }
                episode_ids_to_remove = list(
                    dict.fromkeys(
                        [
                            episode_id
                            for turn_ref in [*changed_turn_refs, *removed_turn_refs]
                            for episode_id in previous_turn_episode_ids.get(turn_ref, [])
                        ]
                    )
                )

            if episode_ids_to_remove:
                _remove_episode_ids_from_conversation(episodes_dir, conv.conv_id, episode_ids_to_remove)
            organize_stats["raw_turns_changed"] += len(changed_turn_refs)
            organize_stats["raw_turns_skipped"] += max(0, len(current_turn_refs) - len(changed_turn_refs))

            batch_size = max(1, ORGANIZE_EPISODE_TURN_BATCH_SIZE)
            for start in range(0, len(changed_turn_refs), batch_size):
                episode_batches.append(
                    {
                        "conv": conv,
                        "raw_key": raw_key,
                        "turn_refs": changed_turn_refs[start:start + batch_size],
                    }
                )
            changed_conversations.append(
                {
                    "conv": conv,
                    "raw_key": raw_key,
                    "signature": signature,
                    "turn_signatures": current_turn_signatures,
                    "changed_turn_refs": changed_turn_refs,
                    "retained_turn_episode_ids": retained_turn_episode_ids,
                }
            )

        built_by_raw_key: dict[str, list[EpisodicMemory]] = {}
        if episode_batches:
            worker_count = _organize_episode_worker_count(settings, len(episode_batches))
            organize_stats["episode_parallel_workers"] = worker_count
            update_job(
                job_id,
                status="running",
                progress={
                    "current": organize_stats["raw_conversations_skipped"],
                    "total": total_steps,
                    "message": "正在并行提取对话记忆...",
                },
            )
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_map = {
                    executor.submit(
                        build_episodes_for_turn_refs,
                        settings,
                        item["conv"],
                        item["turn_refs"],
                    ): item
                    for item in episode_batches
                }
                for completed_count, future in enumerate(as_completed(future_map), start=1):
                    item = future_map[future]
                    built_by_raw_key.setdefault(str(item["raw_key"]), []).extend(future.result())
                    update_job(
                        job_id,
                        status="running",
                        progress={
                            "current": min(len(conversations), organize_stats["raw_conversations_skipped"] + completed_count),
                            "total": total_steps,
                            "message": "正在并行提取对话记忆...",
                        },
                    )
            organize_stats["episode_llm_calls"] += len(episode_batches)

        for item in changed_conversations:
            conv = item["conv"]
            raw_key = str(item["raw_key"])
            signature = str(item["signature"])
            changed_turn_refs = set(item.get("changed_turn_refs") or [])
            turn_episode_ids: dict[str, list[str]] = {
                str(turn_ref): list(ids or [])
                for turn_ref, ids in (item.get("retained_turn_episode_ids") or {}).items()
            }
            built_episodes = built_by_raw_key.get(raw_key, [])
            status = "turn_episodes_incremental"
            saved_new_episode_count = 0
            for episode in built_episodes:
                _normalize_episode_memory_routes(episode)
                first_turn = episode.turn_refs[0] if episode.turn_refs else "conversation"
                if changed_turn_refs and first_turn not in changed_turn_refs:
                    continue
                episode.episode_id = stable_episode_id(f"{raw_key}:{first_turn}:{episode.topic}")
                wiki.save_episode(episode)
                changed_episodes.append(episode)
                turn_episode_ids.setdefault(first_turn, []).append(episode.episode_id)
                saved_new_episode_count += 1
            for turn_ref in item.get("changed_turn_refs") or []:
                turn_episode_ids.setdefault(str(turn_ref), [])
            saved_episode_ids = [
                episode_id
                for turn_ref in item.get("turn_signatures", {})
                for episode_id in turn_episode_ids.get(str(turn_ref), [])
            ]
            organize_stats["episodes_built"] += saved_new_episode_count
            raw_index[raw_key] = {
                "signature": signature,
                "episode_id": saved_episode_ids[0] if saved_episode_ids else "",
                "episode_ids": saved_episode_ids,
                "turn_signatures": item.get("turn_signatures", {}),
                "turn_episode_ids": turn_episode_ids,
                "episode_schema": EPISODE_SCHEMA_VERSION,
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        timings["episode_extraction_sec"] = _elapsed_seconds(episode_stage_started)

        episode_signature = compute_episode_signature(wiki)
        persistent_result = {
            "profile": False,
            "preferences": False,
            "projects": len(wiki.list_projects()),
            "workflows": len(wiki.load_workflows()),
            "index": wiki.get_index(),
            "persistent_rebuilt": False,
            "persistent_nodes": len(load_persistent_nodes(settings).get("nodes", {})),
            "nodes_maintained": False,
        }
        should_rebuild_persistent = (
            bool(changed_episodes)
            or l1_signature != previous_l1_signature
            or episode_signature != previous_episode_signature
            or previous_persistent_rebuild_version != PERSISTENT_REBUILD_VERSION
            or _persistent_memory_assets_missing(settings)
        )
        if should_rebuild_persistent:
            stage_started = time.perf_counter()
            persistent_result = rebuild_persistent_memory(
                settings,
                builder,
                l1_layer,
                job_id,
                len(conversations),
                total_steps,
            )
            timings["persistent_rebuild_sec"] = _elapsed_seconds(stage_started)
            persistent_result["persistent_rebuilt"] = True
            organize_stats["persistent_rebuilt"] = True
        else:
            update_job(
                job_id,
                status="running",
                progress={"current": len(conversations) + 1, "total": total_steps, "message": "结构化记忆已是最新版本..."},
            )
            timings["persistent_rebuild_sec"] = 0.0

        episode_signature = compute_episode_signature(wiki)
        persistent_signature = compute_persistent_signature(wiki, settings)
        persistent_node_ignore_signature = compute_persistent_node_ignore_signature(settings)
        node_maintenance_signature = compute_l2_persistent_node_maintenance_signature(
            episode_signature=episode_signature,
            persistent_signature=persistent_signature,
            l1_signature=l1_signature,
            persistent_node_ignore_signature=persistent_node_ignore_signature,
        )
        should_maintain_nodes = (
            bool(changed_episodes)
            or persistent_signature != previous_persistent_signature
            or node_maintenance_signature != previous_node_signature
            or _persistent_node_assets_missing(settings)
        )
        if not should_rebuild_persistent and not should_maintain_nodes:
            timings["persistent_node_maintenance_sec"] = 0.0
            timings["total_sec"] = _elapsed_seconds(run_started)
            organize_stats["timings"] = timings
            organize_state["raw_index"] = raw_index
            organize_state["last_organized_at"] = datetime.now(timezone.utc).isoformat()
            organize_state["l1_signature"] = l1_signature
            organize_state["episode_signature"] = episode_signature
            organize_state["persistent_signature"] = persistent_signature
            organize_state["persistent_rebuild_version"] = PERSISTENT_REBUILD_VERSION
            organize_state["node_maintenance_signature"] = node_maintenance_signature
            organize_state["last_run_stats"] = organize_stats
            save_organize_state(settings, organize_state)
            update_timestamp(settings)
            update_job(
                job_id,
                status="completed",
                progress={"current": total_steps, "total": total_steps, "message": "记忆已是最新版本"},
                result={
                    "raw_conversations": len(conversations),
                    "episodes": len(wiki.list_episodes()),
                    "updated_episodes": 0,
                    "performance": organize_stats,
                    "already_latest": True,
                    **persistent_result,
                },
            )
            return

        if should_maintain_nodes:
            node_assets_missing = _persistent_node_assets_missing(settings)
            full_node_rebuild = (
                node_assets_missing
                or not previous_node_signature
                or (node_maintenance_signature != previous_node_signature and not changed_episodes)
            )
            all_episodes_for_nodes = wiki.list_episodes()
            if full_node_rebuild:
                node_episodes = all_episodes_for_nodes
            else:
                changed_episode_ids = {changed.episode_id for changed in changed_episodes}
                node_episodes = [
                    episode for episode in all_episodes_for_nodes if episode.episode_id in changed_episode_ids
                ]
            stage_started = time.perf_counter()
            node_result = rebuild_persistent_nodes(
                settings,
                llm,
                node_episodes,
                job_id,
                total_steps,
                reset=full_node_rebuild,
            )
            timings["persistent_node_maintenance_sec"] = _elapsed_seconds(stage_started)
            persistent_result.update(node_result)
            persistent_result["nodes_maintained"] = True
            organize_stats["persistent_nodes_maintained"] = True
            organize_stats["persistent_node_full_rebuild"] = bool(node_result.get("persistent_node_full_rebuild"))
            organize_stats["persistent_node_episodes_processed"] = int(node_result.get("persistent_node_episodes_processed", 0) or 0)
            organize_stats["persistent_node_llm_calls"] = int(node_result.get("persistent_node_llm_calls", 0) or 0)
            connect_episodes_by_persistent_nodes(settings, wiki)
        else:
            update_job(
                job_id,
                status="running",
                progress={"current": total_steps, "total": total_steps, "message": "结构化记忆节点已是最新版本..."},
            )
            timings["persistent_node_maintenance_sec"] = 0.0

        episode_signature = compute_episode_signature(wiki)
        persistent_signature = compute_persistent_signature(wiki, settings)
        persistent_node_ignore_signature = compute_persistent_node_ignore_signature(settings)
        node_maintenance_signature = compute_l2_persistent_node_maintenance_signature(
            episode_signature=episode_signature,
            persistent_signature=persistent_signature,
            l1_signature=l1_signature,
            persistent_node_ignore_signature=persistent_node_ignore_signature,
        )
        timings["total_sec"] = _elapsed_seconds(run_started)
        organize_stats["timings"] = timings
        organize_state["raw_index"] = raw_index
        organize_state["last_organized_at"] = datetime.now(timezone.utc).isoformat()
        organize_state["l1_signature"] = l1_signature
        organize_state["episode_signature"] = episode_signature
        organize_state["persistent_signature"] = persistent_signature
        organize_state["persistent_rebuild_version"] = PERSISTENT_REBUILD_VERSION
        organize_state["node_maintenance_signature"] = node_maintenance_signature
        organize_state["last_run_stats"] = organize_stats
        if should_rebuild_persistent:
            organize_state["last_persistent_rebuild_at"] = datetime.now(timezone.utc).isoformat()
        if should_maintain_nodes:
            organize_state["last_node_maintained_at"] = datetime.now(timezone.utc).isoformat()
        save_organize_state(settings, organize_state)
        update_timestamp(settings)

        update_job(
            job_id,
            status="completed",
            progress={"current": total_steps, "total": total_steps, "message": "整理完成"},
            result={
                "raw_conversations": len(conversations),
                "episodes": len(wiki.list_episodes()),
                "updated_episodes": len(changed_episodes),
                "performance": organize_stats,
                **persistent_result,
            },
        )
    except Exception as exc:  # noqa: BLE001
        update_job(
            job_id,
            status="failed",
            progress=JOB_REGISTRY.get(job_id, {}).get("progress"),
            error=str(exc),
        )


def update_from_new_round(settings: dict[str, Any], payload: ConversationAppendRequest) -> dict[str, Any]:
    llm = get_llm(settings)
    wiki = get_wiki(settings)
    updater = MemoryUpdater(llm=llm, wiki=wiki, schema=L3Schema())
    conversation_text = f"[USER]: {payload.user_text}\n\n[ASSISTANT]: {payload.assistant_text}"
    conversation_time = _parse_iso_datetime(payload.timestamp) or datetime.now(timezone.utc)
    if conversation_time.tzinfo is None:
        conversation_time = conversation_time.replace(tzinfo=timezone.utc)
    conv_path = get_raw_root(settings, create=True) / _safe_slug(payload.platform or "unknown") / f"{_safe_slug(payload.chat_id, fallback='conversation')}.json"
    conv_data = read_json_file(conv_path) if conv_path.exists() else None
    latest_turn_refs: list[str] = []
    if isinstance(conv_data, dict):
        turns = conv_data.get("turns") or []
        if isinstance(turns, list) and turns:
            last_turn = turns[-1]
            if isinstance(last_turn, dict) and str(last_turn.get("turn_id") or "").strip():
                latest_turn_refs = [str(last_turn.get("turn_id")).strip()]
    result = updater.update(
        conversation_text,
        platform=payload.platform,
        conv_id=payload.chat_id,
        turn_refs=latest_turn_refs,
        on_progress=None,
        conversation_end_time=conversation_time,
    )
    episode_id = str(result.get("episode_created") or "").strip() if isinstance(result, dict) else ""
    if episode_id:
        episode = wiki.load_episode(episode_id)
        if episode and update_persistent_nodes_for_episodes(settings, llm, [episode]):
            connect_episodes_by_persistent_nodes(settings, wiki)
            result["persistent_nodes_updated"] = True
            result["persistent_nodes"] = len(load_persistent_nodes(settings).get("nodes", {}))
    if isinstance(result, dict) and result.get("status") == "updated":
        profile = wiki.load_profile()
        preferences = wiki.load_preferences()
        save_display_texts(
            settings,
            _merge_display_cache(
                load_display_texts(settings),
                build_display_fallback_texts(
                    profile,
                    preferences,
                    projects=_valid_projects(wiki),
                    workflows=_valid_workflows(wiki),
                    skills=derive_my_skills(settings),
                ),
            ),
        )
    return result


def _raw_turn_pair_exists(conversation_id: str, messages: list[dict[str, Any]], user_text: str, assistant_text: str) -> bool:
    id_to_message = {str(msg.get("id") or ""): msg for msg in messages if isinstance(msg, dict)}
    for turn in _turn_payloads_from_message_dicts(conversation_id, messages):
        turn_messages = [
            id_to_message[msg_id]
            for msg_id in (turn.get("message_ids") or [])
            if msg_id in id_to_message
        ]
        turn_user = next(
            (msg for msg in turn_messages if str(msg.get("role") or "").strip().lower() == "user"),
            None,
        )
        turn_assistant = next(
            (msg for msg in reversed(turn_messages) if str(msg.get("role") or "").strip().lower() == "assistant"),
            None,
        )
        if (
            turn_user
            and turn_assistant
            and str(turn_user.get("content") or "") == user_text
            and str(turn_assistant.get("content") or "") == assistant_text
        ):
            return True
    return False


def append_raw_round(settings: dict[str, Any], payload: ConversationAppendRequest) -> Path:
    raw_root = get_raw_root(settings, create=True)
    platform_dir = raw_root / _safe_slug(payload.platform or "unknown")
    platform_dir.mkdir(parents=True, exist_ok=True)
    file_path = platform_dir / f"{_safe_slug(payload.chat_id, fallback='conversation')}.json"

    data = read_json_file(file_path) or {
        "id": payload.chat_id,
        "conversation_id": payload.chat_id,
        "platform": payload.platform,
        "title": payload.chat_id,
        "url": payload.url,
        "create_time": payload.timestamp,
        "update_time": payload.timestamp,
        "messages": [],
    }

    messages = data.setdefault("messages", [])
    if _raw_turn_pair_exists(payload.chat_id, messages, payload.user_text, payload.assistant_text):
        if not data.get("turns"):
            data["turns"] = _turn_payloads_from_message_dicts(payload.chat_id, messages)
            file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return file_path

    new_messages = [
        {
            "id": f"{payload.chat_id}_u_{len(messages)}",
            "role": "user",
            "content": payload.user_text,
            "timestamp": payload.timestamp,
            "conversation_id": payload.chat_id,
            "platform": payload.platform,
        },
        {
            "id": f"{payload.chat_id}_a_{len(messages) + 1}",
            "role": "assistant",
            "content": payload.assistant_text,
            "timestamp": payload.timestamp,
            "conversation_id": payload.chat_id,
            "platform": payload.platform,
        },
    ]

    messages.extend(new_messages)

    data["turns"] = _turn_payloads_from_message_dicts(payload.chat_id, messages)
    data["update_time"] = payload.timestamp
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path


def build_raw_conversation_from_payload(payload: CurrentConversationImportRequest) -> RawConversation:
    timestamp = datetime.now(timezone.utc).isoformat()
    raw_messages = []
    for index, item in enumerate(payload.messages):
        if not item.text.strip():
            continue
        raw_messages.append(
            RawMessage(
                msg_id=f"{payload.chat_id}_{index}",
                role=item.role,
                content=item.text,
                timestamp=timestamp,
                conversation_id=payload.chat_id,
                platform=payload.platform,
            )
        )

    if not raw_messages:
        raise HTTPException(status_code=400, detail="当前对话为空，无法加入记忆")

    now = datetime.now(timezone.utc)
    return RawConversation(
        conv_id=payload.chat_id or _safe_slug(payload.title or "current_chat"),
        platform=payload.platform,
        title=payload.title,
        messages=raw_messages,
        start_time=now,
        end_time=now,
    )


def save_platform_memory_snapshot(settings: dict[str, Any], payload: PlatformMemoryImportRequest) -> Path:
    platform_root = get_l1_root(settings, create=True)
    platform_slug = _safe_slug(payload.platform or "platform")
    identity_slug = _safe_slug(payload.agentName or payload.heading or payload.title or "platform_memory")
    data = build_platform_memory_record(payload)
    file_path = platform_root / f"{platform_slug}_{identity_slug}.json"

    data["first_captured_at"] = data["captured_at"]
    data["last_updated_at"] = datetime.now(timezone.utc).isoformat()
    data["capture_count"] = 1
    data["record_id"] = file_path.stem
    data["signature"] = platform_memory_signature(data)

    matched_path = _find_best_platform_memory_match(platform_root, data)
    target_path = matched_path or file_path
    existing = read_json_file(target_path)
    if isinstance(existing, dict):
        existing.setdefault("record_id", target_path.stem)
        data = _merge_platform_memory_records(existing, data)
    data["record_id"] = target_path.stem

    target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    consolidate_platform_memory(settings)

    refreshed = _find_best_platform_memory_match(platform_root, data, threshold=0.0)
    return refreshed or target_path


app = FastAPI(title="QMem Local Backend", version="0.2.0")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "qmem-backend",
        "version": "0.2.0",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    settings = load_settings()
    return SettingsResponse(
        api_provider=settings["api_provider"],
        api_key_configured=bool(settings["api_key"]),
        api_base_url=settings["api_base_url"],
        api_model=settings["api_model"],
        storage_path=str(settings.get("storage_path") or ""),
        keep_updated=bool(settings["keep_updated"]),
        realtime_update=bool(settings["realtime_update"]),
        detailed_injection=bool(settings.get("detailed_injection")),
        last_sync_at=settings["last_sync_at"],
        backend_url=settings["backend_url"],
    )


@app.post("/api/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    payload_data = payload.model_dump()
    configured_path = str(payload_data.get("storage_path") or "").strip()
    if configured_path and not Path(configured_path).expanduser().is_absolute():
        raise HTTPException(status_code=400, detail="本地目录请填写绝对路径，或留空使用默认目录 backend_service/wiki")
    settings = save_settings(payload_data)
    get_storage_root(settings, create=True)
    return SettingsResponse(
        api_provider=settings["api_provider"],
        api_key_configured=bool(settings["api_key"]),
        api_base_url=settings["api_base_url"],
        api_model=settings["api_model"],
        storage_path=str(settings.get("storage_path") or ""),
        keep_updated=bool(settings["keep_updated"]),
        realtime_update=bool(settings["realtime_update"]),
        detailed_injection=bool(settings.get("detailed_injection")),
        last_sync_at=settings["last_sync_at"],
        backend_url=settings["backend_url"],
    )


@app.post("/api/settings/test-connection")
def settings_test_connection(payload: ConnectionTestRequest) -> dict[str, Any]:
    normalized = _normalize_api_config(payload.model_dump())
    provider = (normalized.get("api_provider") or "openai_compat").strip()
    if provider not in {"openai_compat", "deepseek"}:
        return {"ok": False, "message": f"暂不支持 {provider}"}
    ok, message = test_openai_compat_connection(
        str(normalized.get("api_key") or ""),
        str(normalized.get("api_base_url") or ""),
    )
    if ok:
        return {
            "ok": True,
            "message": "可调用",
            "provider": provider,
            "base_url": normalized.get("api_base_url"),
            "model": normalized.get("api_model"),
        }
    return {
        "ok": False,
        "message": message or "当前默认配置不匹配这把 key",
        "provider": provider,
        "base_url": normalized.get("api_base_url"),
        "model": normalized.get("api_model"),
    }


@app.get("/api/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    return build_summary(load_settings())


@app.get("/api/sync/status")
def sync_status() -> dict[str, Any]:
    settings = load_settings()
    return {
        "enabled": bool(settings["keep_updated"]),
        "keep_updated": bool(settings["keep_updated"]),
        "realtime_update": bool(settings["realtime_update"]),
        "last_sync_at": settings["last_sync_at"],
    }


@app.post("/api/sync/toggle")
def sync_toggle(payload: SyncToggleRequest) -> dict[str, Any]:
    settings = load_settings()
    settings["keep_updated"] = payload.enabled
    if payload.enabled:
        settings = update_timestamp(settings)
    else:
        settings = save_settings(settings)
    return {
        "ok": True,
        "enabled": payload.enabled,
        "last_sync_at": settings["last_sync_at"],
    }


@app.post("/api/conversations/append")
def conversations_append(payload: ConversationAppendRequest) -> dict[str, Any]:
    settings = load_settings()
    append_raw_round(settings, payload)
    settings = update_timestamp(settings)

    job_triggered = bool(settings.get("realtime_update"))
    update_result: dict[str, Any] | None = None
    if job_triggered:
        try:
            update_result = update_from_new_round(settings, payload)
        except Exception as exc:  # noqa: BLE001
            update_result = {"status": "failed", "error": str(exc)}

    return {
        "ok": True,
        "conversation_updated": True,
        "job_triggered": job_triggered,
        "update_result": update_result,
    }


@app.post("/api/conversations/current/import")
def conversations_current_import(payload: CurrentConversationImportRequest) -> dict[str, Any]:
    settings = load_settings()
    root = get_storage_root(settings, create=True)
    conversation = build_raw_conversation_from_payload(payload)
    imported = persist_raw_conversations(root, [conversation], platform_hint=payload.platform)

    settings = update_timestamp(settings)
    job = create_job(
        "current_conversation_import",
        status="completed",
        progress={"current": imported, "total": imported, "message": "当前对话已加入记忆"},
        result={
            "imported_conversations": imported,
            "processed": False,
            "processing_started": False,
            "organize_job_id": None,
        },
    )

    if payload.process_now and settings.get("api_key", "").strip():
        organize_job = create_job(
            "memory_organize",
            status="running",
            progress={"current": 0, "total": 1, "message": "正在整理当前对话..."},
        )
        thread = threading.Thread(target=_run_organize_job, args=(organize_job["id"], dict(settings)), daemon=True)
        thread.start()
        job["result"] = {
            "imported_conversations": imported,
            "processed": False,
            "processing_started": True,
            "organize_job_id": organize_job["id"],
        }
        job["progress"] = {
            "current": imported,
            "total": imported,
            "message": "当前对话已加入记忆，后台正在整理...",
        }
        JOB_REGISTRY[job["id"]] = job

    return {"ok": True, "job_id": job["id"]}


@app.post("/api/platform-memory/import")
def platform_memory_import(payload: PlatformMemoryImportRequest) -> dict[str, Any]:
    settings = load_settings()
    file_path = save_platform_memory_snapshot(settings, payload)
    return {
        "ok": True,
        "message": f"平台记忆已保存到 {file_path.name}",
        "file": file_path.name,
    }


@app.post("/api/memory/organize")
def memory_organize() -> dict[str, Any]:
    settings = load_settings()
    try:
        get_llm(settings)
        job = create_job(
            "memory_organize",
            status="running",
            progress={"current": 0, "total": 1, "message": "准备开始整理"},
        )
        thread = threading.Thread(target=_run_organize_job, args=(job["id"], dict(settings)), daemon=True)
        thread.start()
    except HTTPException as exc:
        job = create_job(
            "memory_organize",
            status="failed",
            progress={"current": 0, "total": 1, "message": exc.detail},
            error=exc.detail,
        )
    except Exception as exc:  # noqa: BLE001
        job = create_job(
            "memory_organize",
            status="failed",
            progress={"current": 0, "total": 1, "message": "整理失败"},
            error=str(exc),
        )
    return {"ok": job["status"] != "failed", "job_id": job["id"]}


@app.get("/api/memory/categories")
def memory_categories(locale: str | None = Query(default=None)) -> dict[str, Any]:
    return {"categories": build_memory_categories(load_settings(), locale)}


@app.get("/api/memory/items")
def memory_items(
    category: str = Query(...),
    locale: str | None = Query(default=None),
    refresh_display: bool = Query(default=False),
) -> dict[str, Any]:
    return {
        "items": memory_items_for_category(
            load_settings(),
            category,
            locale,
            refresh_display=refresh_display,
        )
    }


@app.post("/api/memory/items/delete")
def memory_items_delete(payload: DeleteMemoryItemsRequest) -> dict[str, Any]:
    return delete_memory_items(load_settings(), payload.item_ids)


@app.post("/api/export/package")
def export_package(payload: ExportPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    return export_memory_package(settings, payload)


@app.post("/api/inject/package")
def inject_package(payload: InjectPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    detailed = bool(payload.detailed_injection)
    payload_data = build_selected_memory_payload(
        settings,
        payload.selected_ids,
        include_episodic_evidence=True,
        detailed_injection=detailed,
    )
    intro = (
        f"请在当前 {payload.target_platform or 'generic'} 会话中加载以下结构化记忆和相关 episode 摘要，并将其作为后续理解和回答的上下文参考。"
        "以下内容已按历史记录先后排序："
        if not detailed
        else f"请在当前 {payload.target_platform or 'generic'} 会话中加载以下结构化记忆、证据和相关原始对话片段，并将其作为后续理解和回答的上下文基础。"
        "以下内容已按历史记录先后排序："
    )
    text = intro + "\n\n" + json.dumps(payload_data, ensure_ascii=False, indent=2)
    return {"ok": True, "text": text}


@app.get("/api/skills/my")
def skills_my() -> dict[str, Any]:
    return {"items": derive_my_skills(load_settings())}


@app.get("/api/skills/recommended")
def skills_recommended() -> dict[str, Any]:
    settings = load_settings()
    items, meta = rank_recommended_skills(settings)
    return {"items": items, "meta": meta}


@app.post("/api/skills/recommended/refresh")
def skills_recommended_refresh(payload: RefreshRecommendedSkillsRequest | None = None) -> dict[str, Any]:
    settings = load_settings()
    force = bool(payload.force) if payload else False
    _refresh_recommended_skill_catalog(force=force)
    items, meta = rank_recommended_skills(settings)
    return {"ok": True, "items": items, "meta": meta}


@app.post("/api/skills/save")
def skills_save(payload: SaveSkillsRequest) -> dict[str, Any]:
    settings = load_settings()
    saved_ids = set(settings.get("saved_skill_ids", [])) if payload.merge else set()
    saved_ids.update(payload.skill_ids)
    dismissed_ids = set(settings.get("dismissed_skill_ids", []))
    dismissed_ids.difference_update(payload.skill_ids)
    settings["saved_skill_ids"] = sorted(saved_ids)
    settings["dismissed_skill_ids"] = sorted(dismissed_ids)
    save_settings(settings)
    return {"ok": True, "saved_count": len(payload.skill_ids), "saved_skill_ids": settings["saved_skill_ids"]}


@app.post("/api/skills/export")
def skills_export(payload: ExportSkillsRequest) -> dict[str, Any]:
    settings = load_settings()
    filename, content = build_skill_export_text(settings, payload.skill_ids)
    if not content:
        raise HTTPException(status_code=400, detail="请至少选择一个 Skill")
    return {"ok": True, "filename": filename, "content": content}


@app.post("/api/skills/delete")
def skills_delete(payload: DeleteSkillsRequest) -> dict[str, Any]:
    settings = load_settings()
    dismissed_ids = set(settings.get("dismissed_skill_ids", []))
    saved_ids = set(settings.get("saved_skill_ids", []))
    dismissed_ids.update(payload.skill_ids)
    saved_ids.difference_update(payload.skill_ids)
    settings["dismissed_skill_ids"] = sorted(dismissed_ids)
    settings["saved_skill_ids"] = sorted(saved_ids)
    save_settings(settings)
    return {"ok": True, "deleted_count": len(payload.skill_ids)}


@app.post("/api/skills/inject")
def skills_inject(payload: InjectSkillsRequest) -> dict[str, Any]:
    settings = load_settings()
    text = build_skill_inject_text(settings, payload.skill_ids, payload.target_platform)
    if not text:
        raise HTTPException(status_code=400, detail="请至少选择一个 Skill")
    return {"ok": True, "text": text}


@app.post("/api/import/history")
async def import_history(
    platform: str = Form(""),
    file_path: str = Form(""),
    file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    settings = load_settings()
    root = get_storage_root(settings, create=True)
    l0 = L0RawLayer(get_raw_root(settings, create=True) / "_raw_index")
    l1_root = get_l1_root(settings, create=True)

    if file is None and not file_path:
        raise HTTPException(status_code=400, detail="file or file_path is required")

    try:
        source_path: Path
        if file is not None:
            destination = UPLOADS_DIR / f"{uuid4().hex}_{file.filename}"
            with destination.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)
            source_path = destination
        else:
            source_path = Path(file_path).expanduser()

        conversations = [conv for conv in l0.ingest_file(source_path) if conv.messages]
        imported_count = persist_raw_conversations(root, conversations, platform_hint=platform or "unknown")
        l1_temp = L1SignalLayer()
        try:
            signals = l1_temp.load_file(source_path, platform=platform or "unknown")
            meaningful = [sig for sig in signals if sig.signal_type != "generic"]
            if meaningful:
                target_path = l1_root / source_path.name
                if source_path != target_path:
                    shutil.copy2(source_path, target_path)
        except Exception:  # noqa: BLE001
            meaningful = []
        update_timestamp(settings)
        job = create_job(
            "import_history",
            status="completed",
            progress={
                "current": imported_count,
                "total": imported_count,
                "message": f"Imported {imported_count} conversations",
            },
            result={
                "platform": platform,
                "source": str(source_path),
                "imported_conversations": imported_count,
                "l1_signals_detected": len(meaningful),
            },
        )
        return {"ok": True, "job_id": job["id"]}
    except Exception as exc:  # noqa: BLE001
        job = create_job(
            "import_history",
            status="failed",
            progress={"current": 0, "total": 1, "message": "导入历史失败"},
            error=str(exc),
        )
        return {"ok": False, "job_id": job["id"]}


@app.post("/api/cache/clear")
def cache_clear(payload: CacheClearRequest) -> dict[str, Any]:
    if payload.scope == "all_memory":
        root = get_storage_root(load_settings(), create=True)
        target_dirs = [
            "raw",
            "platform_memory",
            "episodes",
            "profile",
            "preferences",
            "projects",
            "workflows",
            "skills",
            "daily_notes",
            "metadata",
            "logs",
        ]
        cleared: list[str] = []
        for name in target_dirs:
            path = root / name
            if not path.exists():
                continue
            if path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)
            cleared.append(name)
        return {
            "ok": True,
            "message": "All memory files cleared",
            "cleared": cleared,
            "memory_root": str(root),
        }
    if payload.scope == "temporary" and UPLOADS_DIR.exists():
        for child in UPLOADS_DIR.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
        return {"ok": True, "message": "Temporary cache cleared"}
    return {"ok": True, "message": "No cache cleared"}


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = JOB_REGISTRY.get(job_id)
    if not job:
        return JobResponse(
            id=job_id,
            type="unknown",
            status="not_found",
            progress=None,
            result=None,
            error="Job not found",
        )
    return JobResponse(**job)
