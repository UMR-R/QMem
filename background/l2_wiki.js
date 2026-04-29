// L2Wiki JS — Python-compatible layered memory storage
// Implements the same directory schema as llm_memory_transferor/l2_wiki.py
// so JS (Chrome extension) and Python (mwiki CLI) can share the same directory.

// ── dirHandle via IndexedDB ───────────────────────────────────────────────────

export async function getDirHandle() {
  return new Promise(resolve => {
    const req = indexedDB.open("MemAssistDB", 1);
    req.onerror = () => resolve(null);
    req.onsuccess = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("settings")) { resolve(null); return; }
      const get = db.transaction("settings", "readonly").objectStore("settings").get("dirHandle");
      get.onsuccess = () => resolve(get.result ?? null);
      get.onerror = () => resolve(null);
    };
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore("settings");
    };
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _now() { return new Date().toISOString(); }

function _safeName(name) {
  return String(name).toLowerCase().replace(/[\s/]/g, "_").slice(0, 64);
}

function _safeEpisodeContainerName(name) {
  return String(name || "unknown_conversation").replace(/\//g, "_").slice(0, 160);
}

async function _readJson(dirHandle, filename) {
  try {
    const fh = await dirHandle.getFileHandle(filename);
    const file = await fh.getFile();
    return JSON.parse(await file.text());
  } catch {
    return null;
  }
}

async function _writeJson(dirHandle, filename, data) {
  const fh = await dirHandle.getFileHandle(filename, { create: true });
  const writable = await fh.createWritable();
  await writable.write(JSON.stringify(data, null, 2));
  await writable.close();
}

function _episodeRecords(data) {
  if (data && Array.isArray(data.episodes)) return data.episodes.filter(Boolean);
  if (data && data.episode_id) return [data];
  return [];
}

async function _getSubDir(name) {
  const root = await getDirHandle();
  if (!root) throw new Error("No directory selected");
  return root.getDirectoryHandle(name, { create: true });
}

// ── Schema constructors (Python MemoryBase compatible) ────────────────────────

function _base() {
  const ts = _now();
  return {
    id: crypto.randomUUID(),
    created_at: ts,
    updated_at: ts,
    version: 1,
    evidence_links: [],
    conflict_log: [],
    user_confirmed: false,
    source_episode_ids: [],
  };
}

export function newProfile() {
  return {
    ..._base(),
    name_or_alias: "",
    role_identity: "",
    domain_background: [],
    organization_or_affiliation: "",
    common_languages: [],
    primary_task_types: [],
    long_term_research_or_work_focus: [],
  };
}

export function newPreferences() {
  return {
    ..._base(),
    style_preference: [],
    terminology_preference: [],
    formatting_constraints: [],
    forbidden_expressions: [],
    language_preference: "",
    revision_preference: [],
    response_granularity: "",
  };
}

export function newProject(name) {
  return {
    ..._base(),
    project_name: name,
    project_goal: "",
    current_stage: "",
    key_terms: {},
    finished_decisions: [],
    unresolved_questions: [],
    relevant_entities: [],
    important_constraints: [],
    next_actions: [],
    is_active: true,
  };
}

export function newWorkflow(name) {
  return {
    ..._base(),
    workflow_name: name,
    trigger_condition: "",
    typical_steps: [],
    preferred_artifact_format: "",
    review_style: "",
    escalation_rule: "",
    reuse_frequency: "ad-hoc",
    occurrence_count: 1,
  };
}

export function newEpisode() {
  return {
    ..._base(),
    episode_id: crypto.randomUUID().slice(0, 8),
    conv_id: "",
    topic: "",
    topics_covered: [],
    platform: "",
    time_range_start: null,
    time_range_end: null,
    summary: "",
    key_decisions: [],
    open_issues: [],
    relates_to_profile: false,
    relates_to_preferences: false,
    relates_to_projects: [],
    relates_to_workflows: [],
    promoted_to_persistent: false,
  };
}

// ── bump helpers (called before every save) ───────────────────────────────────

function _bump(obj) {
  obj.updated_at = _now();
  obj.version = (obj.version ?? 1) + 1;
  return obj;
}

// ── Profile ───────────────────────────────────────────────────────────────────

export async function loadProfile() {
  const root = await getDirHandle();
  if (!root) return null;
  return _readJson(root, "profile.json");
}

export async function saveProfile(p) {
  const root = await getDirHandle();
  if (!root) return;
  _bump(p);
  await _writeJson(root, "profile.json", p);
  await _logChange("profile", "update", "profile");
}

// ── Preferences ───────────────────────────────────────────────────────────────

export async function loadPreferences() {
  const root = await getDirHandle();
  if (!root) return null;
  return _readJson(root, "preferences.json");
}

export async function savePreferences(p) {
  const root = await getDirHandle();
  if (!root) return;
  _bump(p);
  await _writeJson(root, "preferences.json", p);
  await _logChange("preferences", "update", "preferences");
}

// ── Workflows ─────────────────────────────────────────────────────────────────

export async function loadWorkflows() {
  const root = await getDirHandle();
  if (!root) return [];
  return (await _readJson(root, "workflows.json")) ?? [];
}

export async function saveWorkflows(arr) {
  const root = await getDirHandle();
  if (!root) return;
  await _writeJson(root, "workflows.json", arr);
  await _logChange("workflows", "update", "workflows");
}

// ── Projects ──────────────────────────────────────────────────────────────────

export async function loadProject(name) {
  try {
    const projDir = await _getSubDir("projects");
    return await _readJson(projDir, `${_safeName(name)}.json`);
  } catch {
    return null;
  }
}

export async function saveProject(p) {
  const projDir = await _getSubDir("projects");
  _bump(p);
  await _writeJson(projDir, `${_safeName(p.project_name)}.json`, p);
  await _logChange("project", "update", p.project_name);
}

export async function listProjects() {
  try {
    const projDir = await _getSubDir("projects");
    const results = [];
    for await (const [name, handle] of projDir) {
      if (handle.kind === "file" && name.endsWith(".json")) {
        const file = await handle.getFile();
        try {
          results.push(JSON.parse(await file.text()));
        } catch { /* skip malformed */ }
      }
    }
    return results;
  } catch {
    return [];
  }
}

// ── Episodes ──────────────────────────────────────────────────────────────────

export async function saveEpisode(ep) {
  const epDir = await _getSubDir("episodes");
  const convId = ep.conv_id || ep.episode_id || "unknown_conversation";
  const filename = `${_safeEpisodeContainerName(convId)}.json`;
  const existing = _episodeRecords(await _readJson(epDir, filename))
    .filter(item => item.episode_id !== ep.episode_id);
  existing.push(ep);
  existing.sort((a, b) => {
    const aTurn = Number(String(a.turn_refs?.[0] || "").split(":turn:").pop());
    const bTurn = Number(String(b.turn_refs?.[0] || "").split(":turn:").pop());
    if (Number.isFinite(aTurn) && Number.isFinite(bTurn) && aTurn !== bTurn) return aTurn - bTurn;
    return String(a.created_at || "").localeCompare(String(b.created_at || ""));
  });
  await _writeJson(epDir, filename, {
    conversation_id: convId,
    episode_count: existing.length,
    episodes: existing,
  });
  await _logChange("episode", "create", ep.episode_id);
}

export async function listEpisodes() {
  try {
    const epDir = await _getSubDir("episodes");
    const results = [];
    for await (const [name, handle] of epDir) {
      if (handle.kind === "file" && name.endsWith(".json")) {
        const file = await handle.getFile();
        try {
          results.push(..._episodeRecords(JSON.parse(await file.text())));
        } catch { /* skip malformed */ }
      }
    }
    results.sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));
    return results;
  } catch {
    return [];
  }
}

// ── Metadata index ────────────────────────────────────────────────────────────

export async function rebuildIndex() {
  const root = await getDirHandle();
  if (!root) return;

  const metaDir = await root.getDirectoryHandle("metadata", { create: true });
  const projects = await listProjects();
  const episodes = await listEpisodes();

  const index = {
    last_indexed: _now(),
    has_profile: (await _readJson(root, "profile.json")) !== null,
    has_preferences: (await _readJson(root, "preferences.json")) !== null,
    projects: projects.map(p => p.project_name),
    workflow_count: (await loadWorkflows()).length,
    episode_count: episodes.length,
  };

  await _writeJson(metaDir, "index.json", index);
}

// ── Change log ────────────────────────────────────────────────────────────────

async function _logChange(entityType, action, entityId) {
  try {
    const root = await getDirHandle();
    if (!root) return;
    const logsDir = await root.getDirectoryHandle("logs", { create: true });
    const fh = await logsDir.getFileHandle("change_log.jsonl", { create: true });

    const existing = await (await fh.getFile()).text();
    const line = JSON.stringify({ timestamp: _now(), entity_type: entityType, action, entity_id: entityId });
    const combined = existing ? existing.trimEnd() + "\n" + line : line;

    const writable = await fh.createWritable();
    await writable.write(combined);
    await writable.close();
  } catch { /* non-critical, swallow */ }
}
