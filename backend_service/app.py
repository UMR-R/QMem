from __future__ import annotations

import json
import shutil
import sys
import urllib.error
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
LLM_TRANSFEROR_SRC = PROJECT_ROOT / "llm_memory_transferor" / "src"

if str(LLM_TRANSFEROR_SRC) not in sys.path:
    sys.path.insert(0, str(LLM_TRANSFEROR_SRC))

from llm_memory_transferor.exporters import BootstrapGenerator, PackageExporter  # noqa: E402
from llm_memory_transferor.layers.l0_raw import L0RawLayer, RawConversation, RawMessage  # noqa: E402
from llm_memory_transferor.layers.l1_signals import L1SignalLayer  # noqa: E402
from llm_memory_transferor.layers.l2_wiki import L2Wiki  # noqa: E402
from llm_memory_transferor.layers.l3_schema import L3Schema  # noqa: E402
from llm_memory_transferor.processors import MemoryBuilder, MemoryUpdater  # noqa: E402
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


RECOMMENDED_SKILLS = [
    {
        "id": "rec:pdf_reader",
        "title": "读 PDF",
        "description": "快速提取文档结构与关键结论",
        "selected": False,
    },
    {
        "id": "rec:paper_summary",
        "title": "读文献总结",
        "description": "把论文整理成问题、方法、结果和局限的结构化摘要",
        "selected": False,
    },
    {
        "id": "rec:project_plan",
        "title": "项目规划",
        "description": "拆解任务、设定优先级并输出行动计划",
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


class DeleteSkillsRequest(BaseModel):
    skill_ids: list[str]


class InjectSkillsRequest(BaseModel):
    skill_ids: list[str]
    target_platform: str = "chatgpt"


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


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    ensure_state_dir()
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged


def create_job(
    job_type: str,
    *,
    status: str = "completed",
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
    JOB_REGISTRY[job_id] = job
    return job


def _safe_slug(value: str, fallback: str = "item") -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    slug = slug.strip("_")[:80]
    return slug or fallback


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
    projects_dir = root / "projects"
    episodes_dir = root / "episodes"
    raw_dir = root / "raw"
    persistent_file = root / "js_persistent_nodes.json"

    profile_count = 1 if (root / "profile.json").exists() else 0
    preferences_count = 1 if (root / "preferences.json").exists() else 0

    workflows_file = root / "workflows.json"
    workflows_data = read_json_file(workflows_file) if workflows_file.exists() else []
    workflows_count = len(workflows_data) if isinstance(workflows_data, list) else 0

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


def build_memory_categories(settings: dict[str, Any]) -> list[dict[str, Any]]:
    summary = build_summary(settings)
    return [
        {"id": "profile", "label": "用户画像", "count": summary.breakdown["profile"]},
        {"id": "preferences", "label": "偏好设置", "count": summary.breakdown["preferences"]},
        {"id": "projects", "label": "项目记忆", "count": summary.breakdown["projects"]},
        {"id": "workflows", "label": "工作流 / SOP", "count": summary.breakdown["workflows"]},
        {"id": "persistent", "label": "Persistent Memory", "count": summary.breakdown["persistent"]},
    ]


def load_persistent_nodes(settings: dict[str, Any]) -> dict[str, Any]:
    root = get_storage_root(settings)
    data = read_json_file(root / "js_persistent_nodes.json")
    if isinstance(data, dict):
        return data
    return {"version": "1.0", "pn_next_id": 1, "episodic_tag_paths": [], "nodes": {}}


def memory_items_for_category(settings: dict[str, Any], category: str) -> list[dict[str, Any]]:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)

    if category == "projects":
        items = []
        for project in wiki.list_projects():
            description = project.current_stage or project.project_goal or "项目记忆"
            items.append(
                {
                    "id": f"project:{project.project_name}",
                    "title": project.project_name,
                    "description": description,
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
                "selected": False,
            }
            for workflow in wiki.load_workflows()
        ]

    if category == "persistent":
        persistent = load_persistent_nodes(settings)
        nodes = persistent.get("nodes", {}) if isinstance(persistent, dict) else {}
        return [
            {
                "id": f"persistent:{node_id}",
                "title": node.get("description") or node.get("key") or node_id,
                "description": node.get("type") or "persistent memory",
                "selected": False,
            }
            for node_id, node in nodes.items()
        ]

    if category == "profile":
        if (root / "profile.json").exists():
            return [{"id": "profile:default", "title": "用户画像", "description": "默认用户画像", "selected": False}]
        return []

    if category == "preferences":
        if (root / "preferences.json").exists():
            return [{"id": "preferences:default", "title": "偏好设置", "description": "默认偏好设置", "selected": False}]
        return []

    return []


def derive_my_skills(settings: dict[str, Any]) -> list[dict[str, Any]]:
    root = get_storage_root(settings)
    wiki = get_wiki(settings)
    saved_ids = set(settings.get("saved_skill_ids", []))
    dismissed_ids = set(settings.get("dismissed_skill_ids", []))
    items: list[dict[str, Any]] = []

    for workflow in wiki.load_workflows()[:4]:
        skill_id = f"workflow:{workflow.workflow_name}"
        items.append(
            {
                "id": skill_id,
                "title": workflow.workflow_name,
                "description": workflow.preferred_artifact_format
                or workflow.trigger_condition
                or "从现有工作流提炼出的可复用能力",
                "selected": skill_id in saved_ids,
            }
        )

    if len(items) < 4:
        for project in [p for p in wiki.list_projects() if p.is_active][: 4 - len(items)]:
            skill_id = f"project:{project.project_name}"
            items.append(
                {
                    "id": skill_id,
                    "title": f"{project.project_name} 协作",
                    "description": project.current_stage or project.project_goal or "从项目记忆提炼出的任务能力",
                    "selected": skill_id in saved_ids,
                }
            )

    if len(items) < 4:
        profile = wiki.load_profile()
        if profile and profile.primary_task_types:
            for idx, task in enumerate(profile.primary_task_types[: 4 - len(items)]):
                skill_id = f"profile_task:{idx}"
                items.append(
                    {
                        "id": skill_id,
                        "title": task,
                        "description": "从用户画像中提炼的高频任务能力",
                        "selected": skill_id in saved_ids,
                    }
                )

    if len(items) < 4 and (root / "js_persistent_nodes.json").exists():
        nodes = load_persistent_nodes(settings).get("nodes", {})
        for node_id, node in list(nodes.items())[: 4 - len(items)]:
            skill_id = f"persistent:{node_id}"
            items.append(
                {
                    "id": skill_id,
                    "title": node.get("description") or node.get("key") or node_id,
                    "description": "由长期记忆提炼出的稳定能力",
                    "selected": skill_id in saved_ids,
                }
            )

    return [item for item in items if item["id"] not in dismissed_ids]


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


def parse_selected_ids(selected_ids: list[str]) -> tuple[set[str], set[str]]:
    include_persistent: set[str] = set()
    include_specific: set[str] = set()
    for item_id in selected_ids:
        prefix, _, suffix = item_id.partition(":")
        if prefix == "profile":
            include_persistent.add("profile")
        elif prefix == "preferences":
            include_persistent.add("preferences")
        elif prefix == "project":
            include_persistent.add("projects")
        elif prefix == "workflow":
            include_persistent.add("workflows")
        elif prefix == "persistent" and suffix:
            include_specific.add(suffix)
    return include_persistent, include_specific


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


def export_memory_package(settings: dict[str, Any], payload: ExportPackageRequest) -> dict[str, Any]:
    wiki = get_wiki(settings)
    include_persistent, selected_node_ids = parse_selected_ids(payload.selected_ids)

    if not include_persistent and not selected_node_ids:
        raise HTTPException(status_code=400, detail="请至少选择一项记忆内容")

    package_dir = EXPORTS_DIR / f"package_{uuid4().hex[:8]}"
    exporter = PackageExporter(wiki)
    exporter.export(
        package_dir,
        target_platform=payload.target_format or "generic",
        zip_output=False,
        include_persistent=sorted(include_persistent) or ["profile", "preferences", "projects", "workflows"],
    )

    bootstrap_path = package_dir / "minimal_bootstrap_prompt.txt"
    bootstrap_text = bootstrap_path.read_text(encoding="utf-8") if bootstrap_path.exists() else ""
    manifest = read_json_file(package_dir / "manifest.json") or {}
    appendix = build_persistent_appendix(settings, selected_node_ids, payload.include_episodic_evidence)

    content = bootstrap_text + appendix
    if manifest:
        content += "\n\n## Package Manifest\n" + json.dumps(manifest, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "filename": f"memory_package_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        "content": content.strip(),
        "manifest": manifest,
    }


def build_skill_records(settings: dict[str, Any], skill_ids: list[str]) -> list[dict[str, Any]]:
    saved_ids = set(settings.get("saved_skill_ids", []))
    my_skills = {item["id"]: item for item in derive_my_skills(settings)}
    recommended = {item["id"]: item for item in RECOMMENDED_SKILLS}

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
            }
            for item in skill_records
        ],
    }
    return (
        f"请在当前 {target_platform} 会话中加载以下 Skill，并按照这些能力组织后续回答：\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


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


def organize_memory_job(settings: dict[str, Any]) -> dict[str, Any]:
    conversations = load_all_raw_conversations(settings)
    if not conversations:
        return create_job(
            "memory_organize",
            status="failed",
            progress={"current": 0, "total": 1, "message": "未找到可整理的历史对话"},
            error="No raw conversations found",
        )

    llm = get_llm(settings)
    wiki = get_wiki(settings)
    builder = MemoryBuilder(llm=llm, wiki=wiki)
    l1_layer = L1SignalLayer()
    progress_log: list[str] = []

    def on_progress(message: str) -> None:
        progress_log.append(message)

    result = builder.build(conversations, l1_layer, on_progress=on_progress)
    update_timestamp(settings)
    return create_job(
        "memory_organize",
        progress={
            "current": len(conversations),
            "total": len(conversations),
            "message": progress_log[-1] if progress_log else "Memory organize completed",
        },
        result={
            "raw_conversations": len(conversations),
            **result,
        },
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
        llm = get_llm(settings)
        wiki = get_wiki(settings)
        builder = MemoryBuilder(llm=llm, wiki=wiki)
        process_result = builder.build([conversation], L1SignalLayer())
        processed = True

    settings = update_timestamp(settings)
    job = create_job(
        "current_conversation_import",
        progress={
            "current": imported,
            "total": imported,
            "message": "当前对话已加入记忆",
        },
        result={
            "imported_conversations": imported,
            "processed": processed,
            "process_result": process_result,
        },
    )
    return {"ok": True, "job_id": job["id"]}


@app.post("/api/memory/organize")
def memory_organize() -> dict[str, Any]:
    settings = load_settings()
    try:
        job = organize_memory_job(settings)
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
def memory_categories() -> dict[str, Any]:
    return {"categories": build_memory_categories(load_settings())}


@app.get("/api/memory/items")
def memory_items(category: str = Query(...)) -> dict[str, Any]:
    return {"items": memory_items_for_category(load_settings(), category)}


@app.post("/api/export/package")
def export_package(payload: ExportPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    return export_memory_package(settings, payload)


@app.post("/api/inject/package")
def inject_package(payload: InjectPackageRequest) -> dict[str, Any]:
    settings = load_settings()
    wiki = get_wiki(settings)
    selected_persistent, selected_node_ids = parse_selected_ids(payload.selected_ids)
    generator = BootstrapGenerator(wiki)
    text = generator.generate(target_platform=payload.target_platform or "generic")
    appendix = build_persistent_appendix(settings, selected_node_ids, include_evidence=True)
    if selected_persistent or selected_node_ids:
        return {"ok": True, "text": (text + appendix).strip()}
    raise HTTPException(status_code=400, detail="请至少选择一项记忆内容")


@app.get("/api/skills/my")
def skills_my() -> dict[str, Any]:
    return {"items": derive_my_skills(load_settings())}


@app.get("/api/skills/recommended")
def skills_recommended() -> dict[str, Any]:
    settings = load_settings()
    saved_ids = set(settings.get("saved_skill_ids", []))
    items = []
    for item in RECOMMENDED_SKILLS:
        enriched = dict(item)
        enriched["selected"] = enriched["id"] in saved_ids
        items.append(enriched)
    return {"items": items}


@app.post("/api/skills/save")
def skills_save(payload: SaveSkillsRequest) -> dict[str, Any]:
    settings = load_settings()
    settings["saved_skill_ids"] = payload.skill_ids
    save_settings(settings)
    return {"ok": True, "saved_count": len(payload.skill_ids)}


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

        conversations = l0.ingest_file(source_path)
        imported_count = persist_raw_conversations(root, conversations, platform_hint=platform or "unknown")
        update_timestamp(settings)
        job = create_job(
            "import_history",
            progress={
                "current": imported_count,
                "total": imported_count,
                "message": f"Imported {imported_count} conversations",
            },
            result={
                "platform": platform,
                "source": str(source_path),
                "imported_conversations": imported_count,
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
