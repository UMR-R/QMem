from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
STATE_DIR = ROOT / ".state"
SETTINGS_PATH = STATE_DIR / "settings.json"
UPLOADS_DIR = STATE_DIR / "uploads"
EXPORTS_DIR = STATE_DIR / "exports"
DEFAULT_WIKI_ROOT = STATE_DIR / "wiki"
CATALOG_DIR = ROOT / "catalog"
RECOMMENDED_SKILLS_PATH = CATALOG_DIR / "recommended_skills.json"
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
LLM_TRANSFEROR_SRC = PROJECT_ROOT / "llm_memory_transferor" / "src"
JOB_LOCK = threading.Lock()

if str(LLM_TRANSFEROR_SRC) not in sys.path:
    sys.path.insert(0, str(LLM_TRANSFEROR_SRC))

from llm_memory_transferor.exporters import BootstrapGenerator, PackageExporter  # noqa: E402
from llm_memory_transferor.layers.l0_raw import L0RawLayer, RawConversation, RawMessage  # noqa: E402
from llm_memory_transferor.layers.l1_signals import L1SignalLayer  # noqa: E402
from llm_memory_transferor.layers.l2_wiki import L2Wiki  # noqa: E402
from llm_memory_transferor.layers.l3_schema import L3Schema  # noqa: E402
from llm_memory_transferor.models import EpisodicMemory, WorkflowMemory  # noqa: E402
from llm_memory_transferor.processors import MemoryBuilder, MemoryUpdater  # noqa: E402
from llm_memory_transferor.processors.prompts import (  # noqa: E402
    _PREFERENCE_SYSTEM,
    _PROFILE_SYSTEM,
    _PROJECTS_SYSTEM,
    _WORKFLOWS_SYSTEM,
)
from llm_memory_transferor.utils.llm_client import LLMClient  # noqa: E402


JOB_REGISTRY: dict[str, dict[str, Any]] = {}

DEFAULT_SETTINGS = {
    "api_provider": "deepseek",
    "api_key": "",
    "storage_path": "",
    "keep_updated": False,
    "realtime_update": False,
    "last_sync_at": None,
    "backend_url": "http://127.0.0.1:8765",
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
            "common_languages": "个人背景",
            "primary_task_types": "主要任务类型",
            "long_term_research_or_work_focus": "个人背景",
        },
        "en": {
            "name_or_alias": "Personal Background",
            "role_identity": "Personal Background",
            "domain_background": "Domain Background",
            "organization_or_affiliation": "Personal Background",
            "common_languages": "Personal Background",
            "primary_task_types": "Primary Task Types",
            "long_term_research_or_work_focus": "Personal Background",
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
        "persistent": "兴趣发现",
    },
    "en": {
        "profile": "Profile",
        "preferences": "Preferences",
        "projects": "Projects",
        "workflows": "Workflows / SOP",
        "persistent": "Topics & Habits",
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
    storage_path: str
    keep_updated: bool
    realtime_update: bool
    last_sync_at: str | None
    backend_url: str


class SettingsUpdate(BaseModel):
    api_provider: str = "deepseek"
    api_key: str = ""
    storage_path: str = ""
    keep_updated: bool = False
    realtime_update: bool = False
    backend_url: str = "http://127.0.0.1:8765"


class ConnectionTestRequest(BaseModel):
    api_provider: str = "deepseek"
    api_key: str = ""


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
    memoryHints: list[str] = []
    pageTextExcerpt: str = ""
    capturedAt: str = ""


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


class SaveSkillsRequest(BaseModel):
    skill_ids: list[str]


class ExportSkillsRequest(BaseModel):
    skill_ids: list[str]


class DeleteSkillsRequest(BaseModel):
    skill_ids: list[str]


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
    return merged


def ensure_catalog_dir() -> None:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)


def ensure_recommended_skill_catalog() -> None:
    ensure_catalog_dir()
    if not RECOMMENDED_SKILLS_PATH.exists():
        RECOMMENDED_SKILLS_PATH.write_text(
            json.dumps(DEFAULT_RECOMMENDED_SKILLS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if not RECOMMENDED_SKILLS_META_PATH.exists():
        RECOMMENDED_SKILLS_META_PATH.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "last_updated_at": datetime.now(timezone.utc).isoformat(),
                    "last_refresh_status": "seeded",
                    "sources": ["built_in"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def load_recommended_skill_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ensure_recommended_skill_catalog()
    try:
        items = json.loads(RECOMMENDED_SKILLS_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = list(DEFAULT_RECOMMENDED_SKILLS)
    except json.JSONDecodeError:
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
    ensure_catalog_dir()
    RECOMMENDED_SKILLS_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    RECOMMENDED_SKILLS_META_PATH.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    last_updated = _parse_iso_datetime(meta.get("last_updated_at"))
    if last_updated is None:
        return True
    return (datetime.now(timezone.utc) - last_updated).total_seconds() >= RECOMMENDED_REFRESH_INTERVAL_HOURS * 3600


def _fetch_remote_text(url: str, timeout: float = 12.0) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MemAssist/0.2 (+https://127.0.0.1)",
            "Accept": "text/plain, text/csv, text/markdown; charset=utf-8",
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
    sections = _extract_markdown_sections(raw_text)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title = folder_name.replace("-", " ").replace("_", " ").strip().title()
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip() or title

    description = ""
    for key in ["summary", "overview", "body"]:
        value = sections.get(key, "")
        if value:
            description = re.sub(r"\s+", " ", value).strip()
            break
    if not description:
        description = title

    step_candidates: list[str] = []
    for key in sections:
        if "step" in key or "workflow" in key or "process" in key:
            for line in sections[key].splitlines():
                cleaned = re.sub(r"^[-*0-9. )]+", "", line).strip()
                if cleaned:
                    step_candidates.append(cleaned)
    if len(step_candidates) < 2:
        bullet_lines = []
        for line in raw_text.splitlines():
            if re.match(r"^\s*[-*]\s+", line):
                bullet_lines.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
        step_candidates.extend(bullet_lines[:3])

    record = _build_remote_skill_record(
        source_id=source["id"],
        title=title,
        prompt_text=description,
        usage_bias=float(source.get("usage_bias", 0.9)),
    )
    if not record:
        return None

    record["source"] = f"{source['id']}:{folder_name}"
    if len(step_candidates) >= 2:
        record["steps"] = step_candidates[:4]
    record["trigger"] = record.get("trigger") or f"需要使用 {title} 相关能力时"
    record["goal"] = record.get("goal") or description[:80]
    record["description"] = (
        f"触发：{record['trigger']} | 目标：{record['goal']} | 步骤：{'；'.join(record.get('steps', [])[:3])} | 产出：{record.get('output_format', '结构化结果')}"
    )
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

    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in [*DEFAULT_RECOMMENDED_SKILLS, *fetched_items]:
        title_key = str(item.get("title", "")).strip().lower()
        if not title_key or title_key in seen_titles:
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
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged


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
    return data if isinstance(data, dict) else {"profile": {}, "preferences": {}}


def save_display_texts(settings: dict[str, Any], data: dict[str, Any]) -> None:
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "profile": data.get("profile", {}),
        "preferences": data.get("preferences", {}),
    }
    get_display_texts_path(settings, create=True).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def _looks_like_english_ui_text(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if re.search(r"[\u4e00-\u9fff]", text):
        return False
    return bool(re.search(r"[A-Za-z]", text))


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
            "你是一个中英双语 UI 文案整理器。请把给定短语列表转成适合产品界面展示的中英文。中文要自然、简洁，技术词可以使用行业常见中文表达，必要时可保留缩写如 LLM。返回严格 JSON：{\"zh\": [...], \"en\": [...]}，长度必须与输入一致。",
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
        "你是一个中英双语 UI 文案整理器。请把给定短语转成适合产品界面展示的中英文。中文要自然、简洁，技术词可以使用行业常见中文表达，必要时可保留缩写如 LLM。返回严格 JSON：{\"zh\": \"...\", \"en\": \"...\"}。",
        json.dumps({"value": raw_text}, ensure_ascii=False, indent=2),
    )
    if isinstance(result, dict):
        zh_text = str(result.get("zh") or zh_text or raw_text).strip()
        en_text = str(result.get("en") or en_text or raw_text).strip()
    return zh_text or raw_text, en_text or raw_text


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
            "node_maintenance_signature": data.get("node_maintenance_signature", ""),
            "last_persistent_rebuild_at": data.get("last_persistent_rebuild_at"),
            "last_node_maintained_at": data.get("last_node_maintained_at"),
        }
    return {
        "raw_index": {},
        "last_organized_at": None,
        "l1_signature": "",
        "episode_signature": "",
        "persistent_signature": "",
        "node_maintenance_signature": "",
        "last_persistent_rebuild_at": None,
        "last_node_maintained_at": None,
    }


def save_organize_state(settings: dict[str, Any], state: dict[str, Any]) -> None:
    path = get_organize_state_path(settings, create=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _hash_payload(payload: Any) -> str:
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def compute_episode_signature(wiki: L2Wiki) -> str:
    episodes = [
        {
            "episode_id": ep.episode_id,
            "conv_id": ep.conv_id,
            "topic": ep.topic,
            "summary": ep.summary,
            "projects": ep.relates_to_projects,
            "workflows": ep.relates_to_workflows,
            "updated_at": ep.updated_at.isoformat() if ep.updated_at else "",
        }
        for ep in wiki.list_episodes()
    ]
    return _hash_payload(episodes)


def compute_persistent_signature(wiki: L2Wiki) -> str:
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


def build_platform_memory_record(payload: PlatformMemoryImportRequest) -> dict[str, Any]:
    hints = []
    seen = set()
    for item in payload.memoryHints:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        hints.append(text)

    excerpt = (payload.pageTextExcerpt or "").strip()
    if len(excerpt) > 8000:
        excerpt = excerpt[:8000]

    return {
        "platform": payload.platform,
        "url": payload.url,
        "title": payload.title,
        "heading": payload.heading,
        "agent_name": payload.agentName,
        "chat_id": payload.chatId,
        "captured_at": payload.capturedAt or datetime.now(timezone.utc).isoformat(),
        "memory": hints,
        "summary": payload.heading or payload.title or payload.agentName,
        "page_excerpt": excerpt,
        "source_type": "platform_memory_snapshot",
    }


def platform_memory_signature(record: dict[str, Any]) -> str:
    payload = {
        "platform": record.get("platform", ""),
        "title": record.get("title", ""),
        "heading": record.get("heading", ""),
        "agent_name": record.get("agent_name", ""),
        "memory": record.get("memory", []),
        "page_excerpt": record.get("page_excerpt", ""),
    }
    return _hash_payload(payload)


def _normalized_platform_text(value: str) -> str:
    compact = "".join(ch.lower() if ch.isalnum() else " " for ch in (value or ""))
    return " ".join(part for part in compact.split() if part)


def _platform_identity_key(record: dict[str, Any]) -> str:
    for value in (
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

    excerpt_existing = _normalized_platform_text(str(existing.get("page_excerpt", "")))[:400]
    excerpt_current = _normalized_platform_text(str(current.get("page_excerpt", "")))[:400]
    if excerpt_existing and excerpt_current and excerpt_existing == excerpt_current:
        score += 0.2

    return score


def _merge_platform_memory_records(primary: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    merged["platform"] = primary.get("platform") or incoming.get("platform", "")
    merged["url"] = primary.get("url") or incoming.get("url", "")
    merged["title"] = primary.get("title") or incoming.get("title", "")
    merged["heading"] = primary.get("heading") or incoming.get("heading", "")
    merged["agent_name"] = primary.get("agent_name") or incoming.get("agent_name", "")
    merged["summary"] = primary.get("summary") or incoming.get("summary", "")
    merged["chat_id"] = primary.get("chat_id") or incoming.get("chat_id", "")
    merged["source_type"] = "platform_memory_snapshot"

    merged_memory: list[str] = []
    seen_memory: set[str] = set()
    for item in [*(primary.get("memory") or []), *(incoming.get("memory") or [])]:
        text = str(item).strip()
        normalized = text.lower()
        if not text or normalized in seen_memory:
            continue
        seen_memory.add(normalized)
        merged_memory.append(text)
    merged["memory"] = merged_memory

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


def _looks_like_stable_project(project: ProjectMemory) -> bool:
    episode_count = len(set(project.source_episode_ids))
    signal_count = _project_signal_count(project)
    name = project.project_name.strip().lower()

    if episode_count < 2:
        return False

    if signal_count < 2:
        return False

    # Filter out topic-like or exploratory labels that are discussed repeatedly
    # but still don't yet look like an actual long-running project.
    exploratory_tokens = {
        "recommendation",
        "food",
        "recipe",
        "concert",
        "travel",
        "shopping",
        "price",
        "fruit",
        "skill",
        "configuration",
        "exploration",
    }
    token_hits = sum(1 for token in exploratory_tokens if token in name)
    if episode_count < 3 and token_hits >= 2:
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
        "troubleshooting",
        "shopping",
        "concert",
        "recipe",
        "travel",
        "fruit",
        "food",
    ]
    if any(token in lowered for token in generic_topic_tokens):
        return False

    return True


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
        "interest",
        "topic",
        "habit",
        "exploration",
        "configuration",
        "food",
        "fruit",
    ]
    lowered = clean_title.lower()
    if any(token in lowered for token in vague_tokens):
        return False
    if not str(output_format or "").strip():
        return False
    return True


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
    return normalized


def _valid_workflows(wiki: L2Wiki) -> list[WorkflowMemory]:
    return [workflow for workflow in wiki.load_workflows() if _looks_like_stable_workflow(workflow)]


def conversation_signature(conv: RawConversation) -> str:
    payload = {
        "platform": conv.platform,
        "conv_id": conv.conv_id,
        "title": conv.title,
        "messages": [{"role": m.role, "content": m.content} for m in conv.messages],
        "start_time": conv.start_time.isoformat() if conv.start_time else "",
        "end_time": conv.end_time.isoformat() if conv.end_time else "",
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


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
                meaningful = [sig for sig in signals if sig.signal_type != "generic"]
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


def build_display_texts(
    llm: LLMClient,
    profile: Any,
    preferences: Any,
) -> dict[str, Any]:
    profile_payload = profile.model_dump(mode="json") if profile else {}
    preferences_payload = preferences.model_dump(mode="json") if preferences else {}
    payload = {
        "profile": profile_payload,
        "preferences": preferences_payload,
    }
    system_prompt = (
        "你是一个双语记忆展示文案生成器。"
        "给定 profile 和 preferences 的 JSON，请返回严格 JSON。"
        "只支持 zh 和 en。"
        "字段结构必须保持不变；列表必须保持原顺序和原长度；"
        "只生成适合 UI 展示的简洁文本，不要解释。"
    )
    user_prompt = (
        "请把下面这份 memory 转成双语展示文本。\n"
        "返回格式必须是：\n"
        "{\n"
        '  "profile": {"field": {"zh": ..., "en": ...}},\n'
        '  "preferences": {"field": {"zh": ..., "en": ...}}\n'
        "}\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    result = llm.extract_json(system_prompt, user_prompt)
    if not isinstance(result, dict):
        result = {}

    profile_display = result.get("profile", {}) if isinstance(result.get("profile"), dict) else {}
    preferences_display = (
        result.get("preferences", {}) if isinstance(result.get("preferences"), dict) else {}
    )

    cache = {"profile": {}, "preferences": {}}

    for field, value in profile_payload.items():
        if not value:
            continue
        title_zh = FIELD_LABELS["profile"]["zh"].get(field, field)
        title_en = FIELD_LABELS["profile"]["en"].get(field, field)
        translated = profile_display.get(field, {}) if isinstance(profile_display.get(field), dict) else {}
        if isinstance(value, list):
            zh_values = translated.get("zh", value)
            en_values = translated.get("en", value)
            if not isinstance(zh_values, list) or len(zh_values) != len(value):
                zh_values = value
            if not isinstance(en_values, list) or len(en_values) != len(value):
                en_values = value
            zh_values, en_values = _ensure_bilingual_display_value(llm, value, zh_values, en_values)
            for raw, zh_text, en_text in zip(value, zh_values, en_values):
                raw_text = str(raw).strip()
                if not raw_text:
                    continue
                item_id = f"profile:{field}:{_safe_slug(raw_text, 'item')}"
                cache["profile"][item_id] = _make_display_entry(
                    title_zh=title_zh,
                    title_en=title_en,
                    desc_zh=str(zh_text).strip() or raw_text,
                    desc_en=str(en_text).strip() or raw_text,
                )
        else:
            raw_text = str(value).strip()
            if not raw_text:
                continue
            zh_text = translated.get("zh", raw_text)
            en_text = translated.get("en", raw_text)
            zh_text, en_text = _ensure_bilingual_display_value(llm, raw_text, zh_text, en_text)
            cache["profile"][f"profile:{field}"] = _make_display_entry(
                title_zh=title_zh,
                title_en=title_en,
                desc_zh=str(zh_text).strip() or raw_text,
                desc_en=str(en_text).strip() or raw_text,
            )

    for field, value in preferences_payload.items():
        if not value:
            continue
        title_zh = FIELD_LABELS["preferences"]["zh"].get(field, field)
        title_en = FIELD_LABELS["preferences"]["en"].get(field, field)
        translated = (
            preferences_display.get(field, {})
            if isinstance(preferences_display.get(field), dict)
            else {}
        )
        if isinstance(value, list):
            zh_values = translated.get("zh", value)
            en_values = translated.get("en", value)
            if not isinstance(zh_values, list) or len(zh_values) != len(value):
                zh_values = value
            if not isinstance(en_values, list) or len(en_values) != len(value):
                en_values = value
            zh_values, en_values = _ensure_bilingual_display_value(llm, value, zh_values, en_values)
            desc_zh = "，".join(str(item).strip() for item in zh_values if str(item).strip())
            desc_en = ", ".join(str(item).strip() for item in en_values if str(item).strip())
            raw_text = ", ".join(str(item).strip() for item in value if str(item).strip())
        else:
            desc_zh = str(translated.get("zh", value)).strip()
            desc_en = str(translated.get("en", value)).strip()
            raw_text = str(value).strip()
            desc_zh, desc_en = _ensure_bilingual_display_value(llm, raw_text, desc_zh, desc_en)

        if not raw_text:
            continue
        cache["preferences"][f"preferences:{field}"] = _make_display_entry(
            title_zh=title_zh,
            title_en=title_en,
            desc_zh=desc_zh or raw_text,
            desc_en=desc_en or raw_text,
        )

    return cache


def get_llm(settings: dict[str, Any]) -> LLMClient:
    api_key = settings.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="请先在设置页配置 DeepSeek API Key")
    return LLMClient(
        api_key=api_key,
        model="deepseek-chat",
        backend="openai_compat",
        base_url="https://api.deepseek.com/v1",
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
    projects_dir = root / "projects"
    episodes_dir = root / "episodes"
    raw_dir = root / "raw"
    persistent_file = root / "js_persistent_nodes.json"

    profile_count = len(memory_items_for_category(settings, "profile"))
    preferences_count = len(memory_items_for_category(settings, "preferences"))

    workflows_count = len(_valid_workflows(wiki))

    projects_count = count_json_files(projects_dir)
    episodes_count = count_json_files(episodes_dir)
    raw_count = count_raw_conversations(raw_dir)

    persistent_data = read_json_file(persistent_file) if persistent_file.exists() else {}
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
        memory_item_count=sum(breakdown.values()) - raw_count,
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
        {"id": "persistent", "label": labels["persistent"], "count": summary.breakdown["persistent"]},
    ]


def load_persistent_nodes(settings: dict[str, Any]) -> dict[str, Any]:
    root = get_storage_root(settings)
    data = read_json_file(root / "js_persistent_nodes.json")
    if isinstance(data, dict):
        return data
    return {"version": "1.0", "pn_next_id": 1, "episodic_tag_paths": [], "nodes": {}}


def memory_items_for_category(settings: dict[str, Any], category: str, locale: str | None = None) -> list[dict[str, Any]]:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)
    display_cache = load_display_texts(settings)

    if category == "projects":
        items = []
        for project in wiki.list_projects():
            description = project.current_stage or project.project_goal or "项目记忆"
            items.append(
                {
                    "id": f"project:{project.project_name}",
                    "title": project.project_name,
                    "description": description,
                    "display_title": project.project_name,
                    "display_description": description,
                    "selected": False,
                }
            )
        return items

    if category == "workflows":
        return [
            {
                "id": f"workflow:{workflow.workflow_name}",
                "title": workflow.workflow_name,
                "description": workflow.trigger_condition
                or workflow.preferred_artifact_format
                or "工作流 / SOP",
                "display_title": workflow.workflow_name,
                "display_description": workflow.trigger_condition
                or workflow.preferred_artifact_format
                or "工作流 / SOP",
                "selected": False,
            }
            for workflow in _valid_workflows(wiki)
        ]

    if category == "persistent":
        persistent = load_persistent_nodes(settings)
        nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
        items = []
        for node_id, node in nodes.items():
            title = node.get("description") or node.get("key") or node_id
            if _is_noise_memory_text(title):
                continue
            items.append(
                {
                    "id": f"persistent:{node_id}",
                    "title": title,
                    "description": "",
                    "display_title": title,
                    "display_description": "",
                    "selected": False,
                }
            )
        return items

    if category == "profile":
        profile = wiki.load_profile()
        if profile:
            items = []
            labels = FIELD_LABELS["profile"]["zh"]
            for field, label in labels.items():
                if field == "primary_task_types":
                    continue
                value = getattr(profile, field, None)
                if not value:
                    continue
                if isinstance(value, list):
                    for entry in value:
                        entry_text = str(entry).strip()
                        if not entry_text:
                            continue
                        item_id = f"profile:{field}:{_safe_slug(entry_text, 'item')}"
                        display_entry = display_cache.get("profile", {}).get(item_id, {})
                        items.append(
                            {
                                "id": item_id,
                                "title": label,
                                "description": entry_text,
                                "display_title": _display_text(
                                    display_entry.get("title"),
                                    locale,
                                    _localized_field_label("profile", field, locale),
                                ),
                                "display_description": _display_text(
                                    display_entry.get("description"),
                                    locale,
                                    entry_text,
                                ),
                                "selected": False,
                            }
                        )
                else:
                    item_id = f"profile:{field}"
                    display_entry = display_cache.get("profile", {}).get(item_id, {})
                    items.append(
                        {
                            "id": item_id,
                            "title": label,
                            "description": str(value)[:80],
                            "display_title": _display_text(
                                display_entry.get("title"),
                                locale,
                                _localized_field_label("profile", field, locale),
                            ),
                            "display_description": _display_text(
                                display_entry.get("description"),
                                locale,
                                str(value)[:80],
                            ),
                            "selected": False,
                        }
                    )
            return items
        return []

    if category == "preferences":
        prefs = wiki.load_preferences()
        if prefs:
            items = []
            labels = FIELD_LABELS["preferences"]["zh"]
            for field, label in labels.items():
                if field == "primary_task_types":
                    value = getattr(prefs, field, None)
                    if not value:
                        profile = wiki.load_profile()
                        value = getattr(profile, "primary_task_types", None) if profile else None
                else:
                    value = getattr(prefs, field, None)
                if not value:
                    continue
                description = ", ".join(value) if isinstance(value, list) else str(value)
                items.append(
                    {
                        "id": f"preferences:{field}",
                        "title": label,
                        "description": description[:80],
                        "display_title": _display_text(
                            display_cache.get("preferences", {}).get(f"preferences:{field}", {}).get("title"),
                            locale,
                            _localized_field_label("preferences", field, locale),
                        ),
                        "display_description": _display_text(
                            display_cache.get("preferences", {}).get(f"preferences:{field}", {}).get("description"),
                            locale,
                            description[:80],
                        )[:80],
                        "selected": False,
                    }
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

    if len(items) < 5:
        active_projects = [project for project in wiki.list_projects() if project.is_active]
        for project in active_projects[: 5 - len(items)]:
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

    if len(items) < 6 and (root / "js_persistent_nodes.json").exists():
        nodes = load_persistent_nodes(settings).get("nodes", {})
        episodes_by_id = {episode.episode_id: episode for episode in wiki.list_episodes()}
        for node_id, node in list(nodes.items()):
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

    deduped: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for item in items:
        title_key = item["title"].strip().lower()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        deduped.append(item)
    final_items = [item for item in deduped if item["id"] not in dismissed_ids][:6]
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
    }


def build_fallback_episode(conv: RawConversation, episode_id: str) -> EpisodicMemory:
    excerpt = conv.full_text().strip().replace("\n", " ")
    if len(excerpt) > 220:
        excerpt = excerpt[:217] + "..."
    episode = EpisodicMemory(
        episode_id=episode_id,
        conv_id=conv.conv_id,
        platform=conv.platform,
        topic=conv.title or conv.conv_id,
        topics_covered=[conv.title] if conv.title else [],
        summary=excerpt or "该对话已记录，但自动提取摘要失败。",
        key_decisions=[],
        open_issues=[],
        relates_to_profile=False,
        relates_to_preferences=False,
        relates_to_projects=[],
        relates_to_workflows=[],
        time_range_start=conv.start_time,
        time_range_end=conv.end_time,
    )
    if conv.start_time is not None:
        episode.created_at = conv.start_time
    if conv.end_time is not None:
        episode.updated_at = conv.end_time
    elif conv.start_time is not None:
        episode.updated_at = conv.start_time
    episode.add_evidence("l0_raw", conv.conv_id, excerpt[:100] if excerpt else conv.conv_id)
    return episode


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


def parse_selected_ids(selected_ids: list[str]) -> dict[str, set[str]]:
    selected = {
        "profile_fields": set(),
        "profile_values": set(),
        "preferences_fields": set(),
        "projects": set(),
        "workflows": set(),
        "persistent": set(),
    }
    for item_id in selected_ids:
        prefix, _, suffix = item_id.partition(":")
        if prefix == "profile":
            if suffix and suffix != "default":
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
        elif prefix == "persistent":
            if suffix and suffix != "default":
                selected["persistent"].add(suffix)
            else:
                selected["persistent"].add("*")
    return selected


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


def build_selected_memory_payload(
    settings: dict[str, Any],
    selected_ids: list[str],
    *,
    include_episodic_evidence: bool,
) -> dict[str, Any]:
    selected = parse_selected_ids(selected_ids)
    wiki = get_wiki(settings)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "memory": {},
    }
    episodes_dir = get_storage_root(settings) / "episodes"

    if selected["profile_fields"]:
        profile = wiki.load_profile()
        if profile:
            payload["memory"]["profile"] = _filter_profile_fields(
                profile.model_dump(mode="json"),
                selected["profile_fields"],
                selected["profile_values"],
            )

    if selected["preferences_fields"]:
        preferences = wiki.load_preferences()
        if preferences:
            payload["memory"]["preferences"] = _filter_fields(
                preferences.model_dump(mode="json"),
                selected["preferences_fields"],
            )

    if selected["projects"]:
        projects = wiki.list_projects()
        if "*" not in selected["projects"]:
            projects = [project for project in projects if project.project_name in selected["projects"]]
        payload["memory"]["projects"] = [project.model_dump(mode="json") for project in projects]

    if selected["workflows"]:
        workflows = _valid_workflows(wiki)
        if "*" not in selected["workflows"]:
            workflows = [workflow for workflow in workflows if workflow.workflow_name in selected["workflows"]]
        payload["memory"]["workflows"] = [workflow.model_dump(mode="json") for workflow in workflows]

    if selected["persistent"]:
        persistent = load_persistent_nodes(settings)
        nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
        if "*" in selected["persistent"]:
            selected_node_ids = set(nodes.keys())
        else:
            selected_node_ids = set(selected["persistent"])
        selected_nodes: list[dict[str, Any]] = []
        selected_episode_ids: set[str] = set()
        for node_id in sorted(selected_node_ids):
            node = nodes.get(node_id)
            if not isinstance(node, dict):
                continue
            selected_nodes.append({"id": node_id, **node})
            selected_episode_ids.update(node.get("episode_refs", []))
        if selected_nodes:
            payload["memory"]["persistent_nodes"] = selected_nodes
        if include_episodic_evidence and selected_episode_ids:
            evidence = []
            for ep_id in sorted(selected_episode_ids):
                episode = read_json_file(episodes_dir / f"{ep_id}.json")
                if episode:
                    evidence.append(episode)
            if evidence:
                payload["memory"]["episodic_evidence"] = evidence

    if not payload["memory"]:
        raise HTTPException(status_code=400, detail="请至少选择一项记忆内容")

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
            data = read_json_file(episodes_dir / f"{ep_id}.json")
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
            profile.primary_domain,
            profile.professional_role,
            profile.communication_tone,
            *profile.primary_task_types,
            *profile.recurring_topics,
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
        ranked.append(enriched)

    ranked.sort(key=lambda item: (-item.get("match_score", 0), item.get("title", "")))
    return ranked, meta


def export_memory_package(settings: dict[str, Any], payload: ExportPackageRequest) -> dict[str, Any]:
    package_payload = build_selected_memory_payload(
        settings,
        payload.selected_ids,
        include_episodic_evidence=payload.include_episodic_evidence,
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
        "skills": skill_records,
    }
    filename = f"skills_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return filename, json.dumps(payload, ensure_ascii=False, indent=2)


def test_deepseek_connection(api_key: str) -> tuple[bool, str]:
    if not api_key:
        return False, "API Key 为空"

    request = urllib.request.Request(
        "https://api.deepseek.com/v1/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "memory-assistant-local-backend",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, "Connection successful"
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def update_timestamp(settings: dict[str, Any]) -> dict[str, Any]:
    settings["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    return save_settings(settings)


def _load_persistent_distill_prompt() -> str:
    return (PROJECT_ROOT / "prompts" / "persistent_node_distill_bg.txt").read_text(encoding="utf-8")


def save_persistent_nodes(settings: dict[str, Any], data: dict[str, Any]) -> None:
    root = get_storage_root(settings, create=True)
    (root / "js_persistent_nodes.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def apply_persistent_result(
    pn_data: dict[str, Any],
    result: dict[str, Any],
    episode_id: str,
    platform: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    nodes = pn_data.setdefault("nodes", {})
    pn_data.setdefault("pn_next_id", 1)

    for upd in result.get("updates", []):
        node = nodes.get(upd.get("id"))
        if not node:
            continue
        if episode_id and episode_id not in (node.get("episode_refs") or []):
            node["episode_refs"] = [*(node.get("episode_refs") or []), episode_id]
        if platform and platform not in (node.get("platform") or []):
            node["platform"] = [*(node.get("platform") or []), platform]
        if upd.get("description"):
            node["description"] = upd["description"]
        if upd.get("confidence"):
            node["confidence"] = upd["confidence"]
        node["updated_at"] = now

    for new_node in result.get("new_nodes", []):
        node_id = f"pn_{str(pn_data['pn_next_id']).zfill(4)}"
        pn_data["pn_next_id"] += 1
        nodes[node_id] = {
            "type": new_node["type"],
            "key": new_node["key"],
            "description": new_node["description"],
            "episode_refs": [episode_id] if episode_id else [],
            "platform": [platform] if platform else [],
            "confidence": "low",
            "export_priority": new_node.get("export_priority", "medium"),
            "created_at": now,
            "updated_at": now,
        }

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
            for src_platform in source.get("platform", []):
                if src_platform not in (target.get("platform") or []):
                    target["platform"] = [*(target.get("platform") or []), src_platform]
            del nodes[src_id]
        ref_count = len(target.get("episode_refs") or [])
        if ref_count >= 4:
            target["confidence"] = "high"
        elif ref_count >= 2:
            target["confidence"] = "medium"
        if merge.get("description"):
            target["description"] = merge["description"]
        target["updated_at"] = now


def update_persistent_nodes_for_episode(
    settings: dict[str, Any],
    llm: LLMClient,
    episode: Any,
) -> None:
    pn_data = load_persistent_nodes(settings)
    existing_summary = [
        {
            "id": node_id,
            "type": node.get("type"),
            "key": node.get("key"),
            "description": node.get("description"),
            "confidence": node.get("confidence"),
            "refs": len(node.get("episode_refs") or []),
        }
        for node_id, node in pn_data.get("nodes", {}).items()
    ]
    episode_summary = {
        "episode_id": episode.episode_id,
        "topic": episode.topic,
        "summary": episode.summary,
        "key_decisions": episode.key_decisions,
        "open_issues": episode.open_issues,
        "relates_to_projects": episode.relates_to_projects,
    }
    user_prompt = (
        f"【现有 Persistent 节点】\n{json.dumps(existing_summary, ensure_ascii=False, indent=2)}\n\n"
        f"【新 Episodic 记忆内容】\n{json.dumps(episode_summary, ensure_ascii=False, indent=2)}"
    )
    result = llm.extract_json(_load_persistent_distill_prompt(), user_prompt)
    if isinstance(result, dict) and result:
        apply_persistent_result(pn_data, result, episode.episode_id, episode.platform)
        save_persistent_nodes(settings, pn_data)


def rebuild_persistent_nodes(
    settings: dict[str, Any],
    llm: LLMClient,
    episodes: list[EpisodicMemory],
    job_id: str,
    total_steps: int,
) -> dict[str, Any]:
    pn_data = {"version": "1.0", "pn_next_id": 1, "episodic_tag_paths": [], "nodes": {}}
    save_persistent_nodes(settings, pn_data)

    for index, episode in enumerate(episodes, start=1):
        update_job(
            job_id,
            status="running",
            progress={
                "current": total_steps,
                "total": total_steps,
                "message": f"正在维护 persistent 节点：{index}/{len(episodes)}",
            },
        )
        update_persistent_nodes_for_episode(settings, llm, episode)

    final_nodes = load_persistent_nodes(settings)
    return {
        "persistent_nodes": len(final_nodes.get("nodes", {})),
    }


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
    if not episodes:
        wiki.rebuild_index()
        return {"profile": False, "preferences": False, "projects": 0, "workflows": 0, "index": wiki.get_index()}

    l1_text = l1_layer.combined_text()
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

    def stage(message: str, offset: int) -> None:
        update_job(
            job_id,
            status="running",
            progress={"current": current_step + offset, "total": total_steps, "message": message},
        )

    stage("正在整理用户画像...", 1)
    profile_context = builder._filter_digest(episodes, l1_text, "profile")
    profile_data = builder.llm.extract_json(_PROFILE_SYSTEM, profile_context)
    profile = builder._build_profile(profile_data, l1_text, earliest_ts, profile_ep_ids, ep_by_id)
    wiki.save_profile(profile)

    stage("正在整理偏好设置...", 2)
    prefs_context = builder._filter_digest(episodes, l1_text, "preferences")
    prefs_data = builder.llm.extract_json(_PREFERENCE_SYSTEM, prefs_context)
    prefs = builder._build_preferences(prefs_data, l1_text, earliest_ts, pref_ep_ids, ep_by_id)
    if profile.primary_task_types:
        merged_task_types = list(
            dict.fromkeys((prefs.primary_task_types or []) + list(profile.primary_task_types))
        )
        prefs.primary_task_types = merged_task_types
        profile.primary_task_types = []
    wiki.save_preferences(prefs)
    save_display_texts(settings, build_display_texts(builder.llm, profile, prefs))

    stage("正在整理项目记忆...", 3)
    projects_context = builder._filter_digest(episodes, l1_text, "projects")
    projects_data = builder.llm.extract_json(_PROJECTS_SYSTEM, projects_context)
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

    stage("正在整理工作流...", 4)
    workflows_context = builder._filter_digest(episodes, l1_text, "workflows")
    workflows_data = builder.llm.extract_json(_WORKFLOWS_SYSTEM, workflows_context)
    workflows = builder._build_workflows(workflows_data, l1_text, earliest_ts, workflow_ep_map, ep_by_id)
    workflows = [workflow for workflow in workflows if _looks_like_stable_workflow(workflow)]
    wiki.save_workflows(workflows)
    save_workflow_asset_library(settings, workflows)

    stage("正在重建索引...", 5)
    index = wiki.rebuild_index()
    return {
        "profile": True,
        "preferences": True,
        "projects": len(projects),
        "workflows": len(workflows),
        "index": index,
    }


def _run_organize_job(job_id: str, settings: dict[str, Any]) -> None:
    try:
        consolidate_result = consolidate_platform_memory(settings)
        update_job(
            job_id,
            status="running",
            progress={
                "current": 0,
                "total": 1,
                "message": (
                    f"正在归并平台记忆（合并 {consolidate_result['merged']} 条，"
                    f"清理 {consolidate_result['removed']} 条）"
                ),
            },
        )
        conversations = load_all_raw_conversations(settings)
        if not conversations:
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
        l1_layer, l1_signature = load_l1_signals(settings)
        organize_state = load_organize_state(settings)
        raw_index = organize_state.get("raw_index", {})
        changed_episodes: list[EpisodicMemory] = []
        previous_l1_signature = organize_state.get("l1_signature", "")
        previous_episode_signature = organize_state.get("episode_signature", "")
        previous_persistent_signature = organize_state.get("persistent_signature", "")
        previous_node_signature = organize_state.get("node_maintenance_signature", "")

        total_steps = max(len(conversations), 1) + 5
        current_step = 0

        for conv in conversations:
            current_step += 1
            raw_key = f"{conv.platform}:{conv.conv_id}"
            signature = conversation_signature(conv)
            episode_id = raw_index.get(raw_key, {}).get("episode_id") or stable_episode_id(raw_key)
            existing_meta = raw_index.get(raw_key, {})
            episode_path = wiki.wiki_dir / "episodes" / f"{episode_id}.json"

            update_job(
                job_id,
                status="running",
                progress={
                    "current": current_step,
                    "total": total_steps,
                    "message": "正在提取对话记忆",
                },
            )

            if existing_meta.get("signature") == signature and episode_path.exists():
                continue

            episode = builder._build_episode(conv)
            if episode is None:
                episode = build_fallback_episode(conv, episode_id)
                status = "fallback_built"
            else:
                status = "episode_built"

            episode.episode_id = episode_id
            wiki.save_episode(episode)
            changed_episodes.append(episode)
            raw_index[raw_key] = {
                "signature": signature,
                "episode_id": episode_id,
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

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
        should_rebuild_persistent = bool(changed_episodes) or l1_signature != previous_l1_signature or episode_signature != previous_episode_signature
        if should_rebuild_persistent:
            persistent_result = rebuild_persistent_memory(
                settings,
                builder,
                l1_layer,
                job_id,
                len(conversations),
                total_steps,
            )
            persistent_result["persistent_rebuilt"] = True
        else:
            update_job(
                job_id,
                status="running",
                progress={"current": len(conversations) + 1, "total": total_steps, "message": "persistent 未变化，跳过重建"},
            )

        persistent_signature = compute_persistent_signature(wiki)
        node_maintenance_signature = _hash_payload(
            {
                "episode_signature": episode_signature,
                "persistent_signature": persistent_signature,
                "l1_signature": l1_signature,
            }
        )
        should_maintain_nodes = (
            bool(changed_episodes)
            or persistent_signature != previous_persistent_signature
            or node_maintenance_signature != previous_node_signature
        )
        if should_maintain_nodes:
            node_result = rebuild_persistent_nodes(settings, llm, wiki.list_episodes(), job_id, total_steps)
            persistent_result.update(node_result)
            persistent_result["nodes_maintained"] = True
        else:
            update_job(
                job_id,
                status="running",
                progress={"current": total_steps, "total": total_steps, "message": "persistent 节点未变化，跳过维护"},
            )

        organize_state["raw_index"] = raw_index
        organize_state["last_organized_at"] = datetime.now(timezone.utc).isoformat()
        organize_state["l1_signature"] = l1_signature
        organize_state["episode_signature"] = episode_signature
        organize_state["persistent_signature"] = persistent_signature
        organize_state["node_maintenance_signature"] = node_maintenance_signature
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
    return updater.update(
        conversation_text,
        platform=payload.platform,
        on_progress=None,
        conversation_end_time=datetime.now(timezone.utc),
    )


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

    for new_message in new_messages:
        duplicate = next(
            (
                existing
                for existing in reversed(messages)
                if existing.get("role") == new_message["role"]
                and existing.get("content") == new_message["content"]
            ),
            None,
        )
        if duplicate is None:
            messages.append(new_message)

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
    data["signature"] = platform_memory_signature(data)

    matched_path = _find_best_platform_memory_match(platform_root, data)
    target_path = matched_path or file_path
    existing = read_json_file(target_path)
    if isinstance(existing, dict):
        data = _merge_platform_memory_records(existing, data)

    target_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    consolidate_platform_memory(settings)

    refreshed = _find_best_platform_memory_match(platform_root, data, threshold=0.0)
    return refreshed or target_path


app = FastAPI(title="Memory Assistant Local Backend", version="0.2.0")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "memory-assistant-backend",
        "version": "0.2.0",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    settings = load_settings()
    return SettingsResponse(
        api_provider=settings["api_provider"],
        api_key_configured=bool(settings["api_key"]),
        storage_path=str(get_storage_root(settings)),
        keep_updated=bool(settings["keep_updated"]),
        realtime_update=bool(settings["realtime_update"]),
        last_sync_at=settings["last_sync_at"],
        backend_url=settings["backend_url"],
    )


@app.post("/api/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    settings = save_settings(payload.model_dump())
    get_storage_root(settings, create=True)
    return SettingsResponse(
        api_provider=settings["api_provider"],
        api_key_configured=bool(settings["api_key"]),
        storage_path=str(get_storage_root(settings)),
        keep_updated=bool(settings["keep_updated"]),
        realtime_update=bool(settings["realtime_update"]),
        last_sync_at=settings["last_sync_at"],
        backend_url=settings["backend_url"],
    )


@app.post("/api/settings/test-connection")
def settings_test_connection(payload: ConnectionTestRequest) -> dict[str, Any]:
    if payload.api_provider != "deepseek":
        return {"ok": False, "message": "当前仅支持 DeepSeek"}
    ok, message = test_deepseek_connection(payload.api_key)
    return {"ok": ok, "message": message}


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

    processed = False
    process_result: dict[str, Any] | None = None

    if payload.process_now and settings.get("api_key", "").strip():
        job = create_job(
            "current_conversation_import",
            status="running",
            progress={"current": 0, "total": 1, "message": "正在整理当前对话"},
        )
        _run_organize_job(job["id"], settings)
        process_result = JOB_REGISTRY[job["id"]].get("result")
        processed = True

    settings = update_timestamp(settings)
    job = create_job(
        "current_conversation_import",
        status="completed",
        progress={"current": imported, "total": imported, "message": "当前对话已加入记忆"},
        result={"imported_conversations": imported, "processed": processed, "process_result": process_result},
    )
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
def memory_items(category: str = Query(...), locale: str | None = Query(default=None)) -> dict[str, Any]:
    return {"items": memory_items_for_category(load_settings(), category, locale)}


@app.post("/api/export/package")
def export_package(payload: ExportPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    return export_memory_package(settings, payload)


@app.post("/api/inject/package")
def inject_package(payload: InjectPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    payload_data = build_selected_memory_payload(
        settings,
        payload.selected_ids,
        include_episodic_evidence=True,
    )
    text = (
        f"请在当前 {payload.target_platform or 'generic'} 会话中加载以下结构化记忆，并将其作为后续理解和回答的上下文基础：\n\n"
        + json.dumps(payload_data, ensure_ascii=False, indent=2)
    )
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
    settings["saved_skill_ids"] = payload.skill_ids
    save_settings(settings)
    return {"ok": True, "saved_count": len(payload.skill_ids)}


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
