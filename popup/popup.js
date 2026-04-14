// popup.js

// ─────────────────────────────────────────────────────────────────────────────
// IndexedDB — persist FileSystemDirectoryHandle across popup opens
// ─────────────────────────────────────────────────────────────────────────────

const DB_NAME = "MemAssistDB";
const DB_STORE = "settings";
const DIR_KEY = "dirHandle";

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = e => e.target.result.createObjectStore(DB_STORE);
    req.onsuccess = e => resolve(e.target.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbGet(key) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const req = db.transaction(DB_STORE, "readonly").objectStore(DB_STORE).get(key);
    req.onsuccess = () => resolve(req.result ?? null);
    req.onerror = () => reject(req.error);
  });
}

async function dbSet(key, value) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    tx.objectStore(DB_STORE).put(value, key);
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// API Key management (stored in chrome.storage.local)
// ─────────────────────────────────────────────────────────────────────────────

let _apiKey = "";

function loadApiKey() {
  return new Promise(resolve => {
    chrome.storage.local.get("deepseek_api_key", items => {
      _apiKey = items.deepseek_api_key || "";
      resolve(_apiKey);
    });
  });
}

function saveApiKey(key) {
  _apiKey = key;
  return new Promise(resolve => chrome.storage.local.set({ deepseek_api_key: key }, resolve));
}

function updateApiKeyDisplay() {
  const el = document.getElementById("apiKeyStatus");
  el.textContent = _apiKey ? "API Key: " + "●".repeat(8) : "API Key: 未配置";
}

// ─────────────────────────────────────────────────────────────────────────────
// Directory management
// ─────────────────────────────────────────────────────────────────────────────

let dirHandle = null;

async function loadSavedDir() {
  const saved = await dbGet(DIR_KEY);
  if (!saved) return null;
  // Only silent check on init — requestPermission requires user gesture
  return saved; // keep handle; permission checked on first action
}

async function ensureDirPermission() {
  if (!dirHandle) return false;
  const perm = await dirHandle.queryPermission({ mode: "readwrite" });
  if (perm === "granted") return true;
  const req = await dirHandle.requestPermission({ mode: "readwrite" });
  return req === "granted";
}

async function pickDirectory() {
  const handle = await window.showDirectoryPicker({ mode: "readwrite" });
  await dbSet(DIR_KEY, handle);
  return handle;
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline L2Wiki file I/O — mirrors background/l2_wiki.js (no ES module import)
//
// Directory layout (Python-compatible):
//   <dir>/
//   ├── profile.json          ← ProfileMemory schema
//   ├── preferences.json      ← PreferenceMemory schema
//   ├── workflows.json        ← [WorkflowMemory] array
//   ├── projects/
//   │   └── {safe_name}.json  ← ProjectMemory schema
//   ├── episodes/
//   │   └── {episode_id}.json ← EpisodicMemory schema
//   ├── raw/                  ← background.js raw capture (Python ignores)
//   └── js_persistent_nodes.json ← JS-only persistent nodes + episodic tags
// ─────────────────────────────────────────────────────────────────────────────

async function _readJson(dir, filename) {
  try {
    const fh = await dir.getFileHandle(filename);
    return JSON.parse(await (await fh.getFile()).text());
  } catch { return null; }
}

async function _writeJson(dir, filename, data) {
  const fh = await dir.getFileHandle(filename, { create: true });
  const w = await fh.createWritable();
  await w.write(JSON.stringify(data, null, 2));
  await w.close();
}

async function _getSubDir(name) {
  return dirHandle.getDirectoryHandle(name, { create: true });
}

// ── Schema constructors (Python MemoryBase compatible) ────────────────────────

function _newBase() {
  const ts = new Date().toISOString();
  return {
    id: crypto.randomUUID(), created_at: ts, updated_at: ts,
    version: 1, evidence_links: [], conflict_log: [],
    user_confirmed: false, source_episode_ids: [],
  };
}

function _newEpisode() {
  return {
    ..._newBase(),
    episode_id: crypto.randomUUID().slice(0, 8),
    conv_id: "", topic: "", topics_covered: [], platform: "",
    time_range_start: null, time_range_end: null,
    summary: "", key_decisions: [], open_issues: [],
    relates_to_profile: false, relates_to_preferences: false,
    relates_to_projects: [], relates_to_workflows: [],
    promoted_to_persistent: false,
  };
}

function _newProfile() {
  return {
    ..._newBase(),
    name_or_alias: "", role_identity: "", domain_background: [],
    organization_or_affiliation: "", common_languages: [],
    primary_task_types: [], long_term_research_or_work_focus: [],
  };
}

function _newPreferences() {
  return {
    ..._newBase(),
    style_preference: [], terminology_preference: [], formatting_constraints: [],
    forbidden_expressions: [], language_preference: "",
    revision_preference: [], response_granularity: "",
  };
}

function _newProject(name) {
  return {
    ..._newBase(),
    project_name: name, project_goal: "", current_stage: "",
    key_terms: {}, finished_decisions: [], unresolved_questions: [],
    relevant_entities: [], important_constraints: [], next_actions: [], is_active: true,
  };
}

// ── Persistent nodes (js_persistent_nodes.json) ───────────────────────────────

async function readPersistentNodes() {
  // 优先读 chrome.storage.local（background 实时更新的最新数据）
  const stored = await new Promise(r => chrome.storage.local.get("mw:persistent_nodes", r));
  if (stored["mw:persistent_nodes"]) return stored["mw:persistent_nodes"];
  // 降级：读文件（首次使用或 storage 被清空时）
  return (dirHandle ? await _readJson(dirHandle, "js_persistent_nodes.json") : null)
    ?? { version: "1.0", pn_next_id: 1, episodic_tag_paths: [], nodes: {} };
}

async function writePersistentNodes(data) {
  data.updated_at = new Date().toISOString();
  // 同时写 storage（供 background 读取）和文件（供 Python 读取）
  await new Promise(r => chrome.storage.local.set({ "mw:persistent_nodes": data }, r));
  if (dirHandle) await _writeJson(dirHandle, "js_persistent_nodes.json", data);
}

// ── Episodes ──────────────────────────────────────────────────────────────────

async function _saveEpisodeToDisk(ep) {
  // 同时写 storage（供 background/persistent nodes 引用）和文件
  await new Promise(r => chrome.storage.local.set({ [`mw:episodes:${ep.episode_id}`]: ep }, r));
  if (dirHandle) {
    const epDir = await _getSubDir("episodes");
    await _writeJson(epDir, `${ep.episode_id}.json`, ep);
  }
}

async function _loadEpisodeById(epId) {
  // 优先读 storage（auto-capture 写在这里，无需先同步）
  const stored = await new Promise(r => chrome.storage.local.get(`mw:episodes:${epId}`, r));
  if (stored[`mw:episodes:${epId}`]) return stored[`mw:episodes:${epId}`];
  // 降级：读文件（导出记忆写在这里，或已同步的 episode）
  if (!dirHandle) return null;
  try {
    const epDir = await _getSubDir("episodes");
    return await _readJson(epDir, `${epId}.json`);
  } catch { return null; }
}

// ── L2Wiki merge helpers ──────────────────────────────────────────────────────

// ── L2Wiki merge helpers（读写 chrome.storage.local，sync 时落盘）────────────
// storage 是唯一可信来源，避免导出记忆写文件后被 sync 覆盖。

async function _storageGet(keys) {
  return new Promise(r => chrome.storage.local.get(keys, r));
}
async function _storageSet(obj) {
  return new Promise(r => chrome.storage.local.set(obj, r));
}

async function _mergeProfileFromExport(exportedProfile) {
  if (!exportedProfile) return;
  const stored = await _storageGet("mw:profile");
  const existing = stored["mw:profile"] ?? _newProfile();
  for (const [k, v] of Object.entries(exportedProfile)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v) && v.length === 0) continue;
    existing[k] = v;
  }
  existing.updated_at = new Date().toISOString();
  existing.version = (existing.version ?? 1) + 1;
  await _storageSet({ "mw:profile": existing });
}

async function _mergePrefsFromExport(exportedPrefs) {
  if (!exportedPrefs) return;
  const stored = await _storageGet("mw:preferences");
  const existing = stored["mw:preferences"] ?? _newPreferences();
  const ARRAY_FIELDS = new Set([
    "style_preference", "terminology_preference", "formatting_constraints",
    "forbidden_expressions", "revision_preference",
  ]);
  for (const [k, v] of Object.entries(exportedPrefs)) {
    if (Array.isArray(v) && v.length > 0) {
      existing[k] = [...new Set([...(existing[k] ?? []), ...v])];
    } else if (typeof v === "string" && v) {
      if (ARRAY_FIELDS.has(k)) {
        // LLM may return array fields as a string; wrap to keep type consistent
        existing[k] = [...new Set([...(Array.isArray(existing[k]) ? existing[k] : []), v])];
      } else {
        existing[k] = v;
      }
    }
  }
  existing.updated_at = new Date().toISOString();
  existing.version = (existing.version ?? 1) + 1;
  await _storageSet({ "mw:preferences": existing });
}

async function _mergeProjectFromExport(exportedProject) {
  if (!exportedProject?.project_name) return;
  const key = `mw:projects:${encodeURIComponent(exportedProject.project_name)}`;
  const stored = await _storageGet(key);
  const existing = stored[key] ?? _newProject(exportedProject.project_name);
  const ts = new Date().toISOString();

  if (exportedProject.project_goal)  existing.project_goal  = exportedProject.project_goal;
  if (exportedProject.current_stage) existing.current_stage = exportedProject.current_stage;
  if (exportedProject.stage_update)  existing.current_stage = exportedProject.stage_update;

  function _mergeListField(arr, newItems) {
    const existingSet = new Set(arr.map(d => d.text ?? d));
    for (const item of (newItems ?? [])) {
      const text = typeof item === "string" ? item : item.text;
      if (text && !existingSet.has(text)) arr.push({ text, timestamp: ts });
    }
  }
  _mergeListField(existing.finished_decisions,   exportedProject.finished_decisions);
  _mergeListField(existing.unresolved_questions, exportedProject.unresolved_questions);
  _mergeListField(existing.next_actions,         exportedProject.next_actions);

  existing.updated_at = ts;
  existing.version = (existing.version ?? 1) + 1;
  await _storageSet({ [key]: existing });
}

// ── Platform guesser ──────────────────────────────────────────────────────────

function _guessPlatform(url) {
  if (!url) return "unknown";
  if (/chat\.openai\.com|chatgpt\.com/.test(url)) return "chatgpt";
  if (/gemini\.google\.com/.test(url))            return "gemini";
  if (/deepseek\.com/.test(url))                  return "deepseek";
  if (/doubao\.com/.test(url))                    return "doubao";
  return "unknown";
}

// ─────────────────────────────────────────────────────────────────────────────
// Export prompt builder — injects existing episodic tag paths into the skill
// ─────────────────────────────────────────────────────────────────────────────

function buildExportPrompt(existingTagPaths) {
  const tagsList = existingTagPaths.length > 0
    ? existingTagPaths.join("\n")
    : "（暂无已有标签，请按规范新建）";
  return CONFIG.skills.episodicTag.replace("{{EXISTING_TAGS}}", tagsList);
}

// Parse __episodic_tags__ from AI response; returns { memoryContent, tags }
function extractEpisodicTags(rawText) {
  const jsonStart = rawText.indexOf("{");
  if (jsonStart === -1) return { memoryContent: rawText, tags: null };
  try {
    const parsed = JSON.parse(rawText.slice(jsonStart));
    const tags = parsed.__episodic_tags__ ?? null;
    delete parsed.__episodic_tags__;
    return { memoryContent: JSON.stringify(parsed, null, 2), tags };
  } catch {
    return { memoryContent: rawText, tags: null };
  }
}

// Merge new tag paths into pnData.episodic_tag_paths (deduplication)
function mergeEpisodicTagsPN(pnData, tagsResult) {
  if (!tagsResult) return [];
  const existing = new Set(pnData.episodic_tag_paths ?? []);
  for (const path of (tagsResult.use_existing || [])) existing.add(path);
  for (const { path } of (tagsResult.new_tags || [])) existing.add(path);
  pnData.episodic_tag_paths = Array.from(existing);
  return [
    ...(tagsResult.use_existing || []),
    ...(tagsResult.new_tags || []).map(t => t.path),
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// DeepSeek API — distill persistent nodes from a new episodic memory
// ─────────────────────────────────────────────────────────────────────────────

async function callDeepSeekForPersistent(memoryText, existingNodes) {
  if (!_apiKey) throw new Error("未配置 DeepSeek API Key，请点击「设置」按钮填写");
  const memStr = (typeof memoryText === "string" ? memoryText : JSON.stringify(memoryText)).slice(0, 3000);

  const existingSummary = Object.entries(existingNodes).map(([id, n]) => ({
    id, type: n.type, key: n.key, description: n.description,
    confidence: n.confidence, refs: n.episode_refs.length,
  }));

  const userMsg = `【现有 Persistent 节点】
${JSON.stringify(existingSummary, null, 2)}

【新 Episodic 记忆内容】
${memStr}`;

  const resp = await fetch(CONFIG.deepseek.endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${_apiKey}` },
    body: JSON.stringify({
      model: CONFIG.deepseek.model,
      messages: [
        { role: "system", content: CONFIG.skills.architecture + "\n\n" + CONFIG.skills.persistentDistill },
        { role: "user",   content: userMsg },
      ],
      temperature: 0.2,
      max_tokens: 2000,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`DeepSeek 请求失败 ${resp.status}: ${err.slice(0, 80)}`);
  }
  const data = await resp.json();
  const raw = data.choices[0].message.content.trim();
  try { return JSON.parse(raw); } catch { /* fall through */ }
  const m = raw.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("DeepSeek 返回格式异常（可能被截断）：" + raw.slice(0, 120));
  return JSON.parse(m[0]);
}

// Apply DeepSeek result to pnData.nodes; returns { updated, created, merged }
// epId may be null when called from consolidation-only flow
function applyPersistentResult(pnData, result, epId) {
  const now = new Date().toISOString();
  const nodes = pnData.nodes;
  const updated = [];
  const created = [];
  const merged = [];

  for (const upd of (result.updates || [])) {
    const node = nodes[upd.id];
    if (!node) continue;
    if (epId && !node.episode_refs.includes(epId)) node.episode_refs.push(epId);
    if (upd.description) node.description = upd.description;
    if (upd.confidence)  node.confidence  = upd.confidence;
    node.updated_at = now;
    updated.push(node.key);
  }

  for (const nn of (result.new_nodes || [])) {
    const pnId = `pn_${String(pnData.pn_next_id).padStart(4, "0")}`;
    pnData.pn_next_id += 1;
    nodes[pnId] = {
      type: nn.type, key: nn.key, description: nn.description,
      episode_refs: epId ? [epId] : [],
      confidence: nn.confidence || "low",
      export_priority: nn.export_priority || "medium",
      created_at: now, updated_at: now,
    };
    created.push(nn.key);
  }

  for (const mg of (result.merges || [])) {
    const target = nodes[mg.merged_into];
    if (!target) continue;
    const sources = Array.isArray(mg.merged_from) ? mg.merged_from : [mg.merged_from];
    const sourceKeys = [];
    for (const srcId of sources) {
      const source = nodes[srcId];
      if (!source) continue;
      for (const ref of source.episode_refs) {
        if (!target.episode_refs.includes(ref)) target.episode_refs.push(ref);
      }
      sourceKeys.push(source.key);
      delete nodes[srcId];
    }
    if (sourceKeys.length === 0) continue;
    const refCount = target.episode_refs.length;
    if (refCount >= 4) target.confidence = "high";
    else if (refCount >= 2) target.confidence = "medium";
    if (mg.description) target.description = mg.description;
    target.updated_at = now;
    merged.push(`[${sourceKeys.join(", ")}] → ${target.key}`);
  }

  return { updated, created, merged };
}

// Consolidation-only call: ask DeepSeek to find merges in existing nodes
async function callDeepSeekForConsolidate(existingNodes) {
  if (!_apiKey) throw new Error("未配置 DeepSeek API Key，请点击「设置」按钮填写");
  const allNodes = Object.entries(existingNodes).map(([id, n]) => ({
    id, type: n.type, key: n.key, description: n.description,
    confidence: n.confidence, refs: n.episode_refs.length,
  }));

  const userMsg = `【整合任务】
请审视以下全部 Persistent 节点，给出合并建议。只返回 merges 列表，updates 和 new_nodes 留空数组。

需要处理两种情况：
1. **语义重复**：两个节点描述几乎相同的规律 → 合并为一个
2. **子话题聚合**（重点）：topic 类型下，若多个节点是同一课程/项目/领域的具体子话题（如"良序原理"和"容斥原理"都属于"离散数学"），应合并为一个领域级节点，description 改写为概括性描述，merged_from 可以是数组

如无需合并，merges 留空数组。

${JSON.stringify(allNodes, null, 2)}`;

  const resp = await fetch(CONFIG.deepseek.endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${_apiKey}` },
    body: JSON.stringify({
      model: CONFIG.deepseek.model,
      messages: [
        { role: "system", content: CONFIG.skills.architecture + "\n\n" + CONFIG.skills.persistentDistill },
        { role: "user",   content: userMsg },
      ],
      temperature: 0.2,
      max_tokens: 3000,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`DeepSeek 请求失败 ${resp.status}: ${err.slice(0, 80)}`);
  }
  const data = await resp.json();
  const raw = data.choices[0].message.content.trim();
  // 先尝试整体解析，再尝试提取 {...}，最后提取 [...] 作为 merges 列表
  try { return JSON.parse(raw); } catch { /* fall through */ }
  const objM = raw.match(/\{[\s\S]*\}/);
  if (objM) { try { return JSON.parse(objM[0]); } catch { /* fall through */ } }
  throw new Error("DeepSeek 返回格式异常（可能被截断）：" + raw.slice(0, 120));
}

// ── 导入历史记录文件（ChatGPT / DeepSeek 导出格式）──────────────────────────────

async function handleImportFile(file) {
  showResult("正在解析文件...");

  let json;
  try {
    json = JSON.parse(await file.text());
  } catch (err) {
    showResult("JSON 解析失败：" + err.message, true);
    return;
  }

  let conversations;
  try {
    conversations = _parseExportedConversations(json);
  } catch (err) {
    showResult("格式不支持：" + err.message, true);
    return;
  }

  if (conversations.length === 0) {
    showResult("未找到可导入的对话", true);
    return;
  }

  const detectedPlatform = conversations[0]?.platform ?? "unknown";
  showResult(`识别为 ${detectedPlatform}，解析到 ${conversations.length} 条对话，正在写入存储...`);

  let imported = 0;
  let skipped = 0;

  for (const conv of conversations) {
    const storageKey = `chat:${conv.platform}:${conv.chatId}`;
    const existing = await _storageGet(storageKey);
    const existingData = existing[storageKey];

    if (existingData) {
      const existingSet = new Set(
        (existingData.rounds ?? []).map(r => r.user + "\x00" + r.assistant)
      );
      const newRounds = conv.rounds.filter(
        r => !existingSet.has(r.user + "\x00" + r.assistant)
      );
      if (newRounds.length > 0) {
        existingData.rounds = [...existingData.rounds, ...newRounds];
        await _storageSet({ [storageKey]: existingData });
        imported++;
      } else {
        skipped++;
      }
    } else {
      await _storageSet({
        [storageKey]: {
          platform: conv.platform,
          url: "",
          first_seen: conv.first_seen,
          last_updated: conv.last_updated,
          rounds: conv.rounds,
        },
      });
      imported++;
    }
  }

  showResult(
    `已导入 ${imported} 条对话（${skipped} 条已存在跳过）\n` +
    `点击"同步"按钮提取 episode 并保存到文件`
  );
}

/**
 * 从 conversations.json 内容自动识别平台。
 * DeepSeek：对话有 inserted_at 字段，或消息有 fragments 字段。
 * ChatGPT：对话有 create_time（数字），或消息有 author 字段。
 * 返回 "deepseek" | "chatgpt"。
 */
function _detectPlatform(list) {
  const conv = list[0];
  if (!conv) return "chatgpt";

  // 对话级时间戳
  if (typeof conv.inserted_at === "string") return "deepseek";
  if (typeof conv.create_time === "number") return "chatgpt";

  // 消息级结构
  if (conv.mapping && typeof conv.mapping === "object") {
    for (const node of Object.values(conv.mapping)) {
      const msg = node.message;
      if (!msg) continue;
      if (Array.isArray(msg.fragments)) return "deepseek";
      if (msg.author?.role)             return "chatgpt";
    }
  }

  return "chatgpt"; // 默认回退
}

/**
 * 将 ChatGPT / DeepSeek 导出的 conversations.json 解析为内部 rounds 格式。
 *
 * ChatGPT：message.author.role + message.content.parts + create_time（Unix 秒）
 * DeepSeek：message.fragments[].type (REQUEST/RESPONSE) + fragments[].content
 *           + message.inserted_at（ISO 字符串）；conv.inserted_at 为对话时间
 */
function _parseExportedConversations(json, _platformHint) {
  const list = Array.isArray(json) ? json
    : Array.isArray(json.conversations) ? json.conversations
    : null;
  if (!list) throw new Error("顶层应为数组或含 conversations 字段的对象");

  const platform = _detectPlatform(list);

  const results = [];
  for (const conv of list) {
    // 时间戳：ChatGPT 用 create_time（Unix 秒），DeepSeek 用 inserted_at（ISO）
    const createTime = conv.create_time
      ? new Date(conv.create_time * 1000).toISOString()
      : (conv.inserted_at ?? new Date().toISOString());

    const chatId = conv.id
      ?? `${platform}_${createTime.replace(/\W/g, "_")}`;

    let rounds = [];
    if (conv.mapping && typeof conv.mapping === "object") {
      rounds = _extractRoundsFromMapping(conv.mapping, createTime);
    } else if (Array.isArray(conv.messages)) {
      rounds = _extractRoundsFromArray(conv.messages, createTime);
    }

    if (rounds.length > 0) {
      results.push({ chatId, platform, first_seen: createTime, last_updated: createTime, rounds });
    }
  }
  return results;
}

function _extractRoundsFromMapping(mapping, defaultTs) {
  const allIds = new Set(Object.keys(mapping));

  // 找根节点：parent 为 null 或 parent 不在 mapping 里
  let rootId = null;
  for (const [id, node] of Object.entries(mapping)) {
    if (!node.parent || !allIds.has(node.parent)) {
      rootId = id;
      break;
    }
  }
  if (!rootId) return [];

  // 沿树收集消息（跟随最后一个 child，对应用户最新选择的分支）
  const messages = [];
  const visited = new Set();
  let cur = rootId;
  while (cur && !visited.has(cur)) {
    visited.add(cur);
    const node = mapping[cur];
    if (!node) break;
    const msg = node.message;
    if (msg) {
      const extracted = _extractMessageContent(msg, defaultTs);
      if (extracted) messages.push(extracted);
    }
    const children = node.children ?? [];
    cur = children[children.length - 1] ?? null;
  }

  return _pairMessages(messages, defaultTs);
}

/**
 * 从单条 message 对象提取 { role, text, timestamp }。
 * 兼容 ChatGPT（author.role + content.parts）和
 * DeepSeek（fragments[].type REQUEST/RESPONSE + fragments[].content）。
 */
function _extractMessageContent(msg, defaultTs) {
  let role = null;
  let text = "";
  let timestamp = defaultTs;

  // ChatGPT 格式
  if (msg.author?.role) {
    role = msg.author.role === "user" ? "user"
         : msg.author.role === "assistant" ? "assistant"
         : null;
    if (!role) return null;
    const parts = msg.content?.parts ?? [];
    text = parts.filter(p => typeof p === "string").join("\n").trim();
    timestamp = msg.create_time
      ? new Date(msg.create_time * 1000).toISOString()
      : defaultTs;

  // DeepSeek 格式
  } else if (Array.isArray(msg.fragments) && msg.fragments.length > 0) {
    const firstType = msg.fragments[0].type;
    role = firstType === "REQUEST" ? "user"
         : firstType === "RESPONSE" ? "assistant"
         : null;
    if (!role) return null;
    text = msg.fragments
      .map(f => (typeof f.content === "string" ? f.content : ""))
      .join("\n")
      .trim();
    timestamp = msg.inserted_at ?? defaultTs;
  }

  if (!role || !text) return null;
  return { role, text, timestamp };
}

function _extractRoundsFromArray(messages, defaultTs) {
  const normalized = messages
    .filter(m => m.role === "user" || m.role === "assistant")
    .map(m => ({
      role: m.role,
      text: (typeof m.content === "string" ? m.content : m.text ?? "").trim(),
      timestamp: m.create_time
        ? new Date(m.create_time * 1000).toISOString()
        : (m.created_at ?? defaultTs),
    }))
    .filter(m => m.text);
  return _pairMessages(normalized, defaultTs);
}

function _pairMessages(messages, defaultTs) {
  const rounds = [];
  for (let i = 0; i < messages.length - 1; i++) {
    if (messages[i].role === "user" && messages[i + 1].role === "assistant") {
      rounds.push({
        user: messages[i].text,
        assistant: messages[i + 1].text,
        timestamp: messages[i + 1].timestamp ?? messages[i].timestamp ?? defaultTs,
      });
      i++;
    }
  }
  return rounds;
}

// ── 从已有 episodes 重建 persistent nodes ─────────────────────────────────────

async function handleRebuildFromEpisodes() {
  if (!_apiKey) { showResult("请先配置 DeepSeek API Key", true); return; }

  const btn = document.getElementById("rebuildBtn");
  btn.disabled = true;

  try {
    // 1. 读取所有 episodes（storage 优先，再读文件）
    const allData = await new Promise(r => chrome.storage.local.get(null, r));
    const storageEpisodes = Object.entries(allData)
      .filter(([k]) => k.startsWith("mw:episodes:"))
      .map(([, v]) => v)
      .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));

    // 如果选了目录，也把文件里的 episodes 扫入（可能是更早的导出记忆）
    let fileEpisodes = [];
    if (dirHandle && await ensureDirPermission()) {
      try {
        const epDir = await _getSubDir("episodes");
        for await (const [name, handle] of epDir) {
          if (handle.kind !== "file" || !name.endsWith(".json")) continue;
          try {
            const ep = JSON.parse(await (await handle.getFile()).text());
            // 只补充 storage 里没有的
            if (ep.episode_id && !allData[`mw:episodes:${ep.episode_id}`]) {
              fileEpisodes.push(ep);
            }
          } catch { /* skip */ }
        }
      } catch { /* no episodes dir */ }
    }

    const episodes = [...storageEpisodes, ...fileEpisodes]
      .sort((a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? ""));

    if (episodes.length === 0) {
      showResult("没有找到历史 episodes，请先进行对话（需开启实时更新）", true);
      return;
    }

    showResult(`找到 ${episodes.length} 条 episodes，开始逐条提炼...`);

    // 2. 读取当前 persistent nodes
    const pnData = await readPersistentNodes();

    // 已处理过的 episode ID（已出现在某个节点的 episode_refs 中）
    const processedEpIds = new Set();
    for (const node of Object.values(pnData.nodes)) {
      for (const ref of (node.episode_refs ?? [])) processedEpIds.add(ref);
    }

    const toProcess = episodes.filter(ep => ep.episode_id && !processedEpIds.has(ep.episode_id));
    if (toProcess.length === 0) {
      showResult(`所有 ${episodes.length} 条 episodes 均已处理，无新内容`);
      return;
    }
    showResult(`跳过 ${episodes.length - toProcess.length} 条已处理，处理 ${toProcess.length} 条新 episodes...`);

    // 3. 只处理未曾提炼过的 episodes
    let processed = 0;
    for (const ep of toProcess) {
      const memText = [
        `topic: ${ep.topic ?? ""}`,
        `summary: ${ep.summary ?? ""}`,
        ep.key_decisions?.length  ? `key_decisions: ${ep.key_decisions.join("; ")}` : "",
        ep.open_issues?.length    ? `open_issues: ${ep.open_issues.join("; ")}` : "",
        ep.relates_to_projects?.length ? `projects: ${ep.relates_to_projects.join(", ")}` : "",
      ].filter(Boolean).join("\n");

      if (!memText.trim()) continue;

      try {
        const result = await callDeepSeekForPersistent(memText, pnData.nodes);
        applyPersistentResult(pnData, result, ep.episode_id);
        processed++;
        showResult(`已处理 ${processed}/${toProcess.length}...`);
      } catch (err) {
        console.warn("[rebuild] episode", ep.episode_id, "失败:", err.message);
      }
    }

    // 4. 保存
    await writePersistentNodes(pnData);

    const nodeCount = Object.keys(pnData.nodes).length;
    showResult(`完成：新处理 ${processed} 条 episodes，共 ${nodeCount} 个记忆节点`);
  } catch (err) {
    showResult("重建失败：" + err.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function handleConsolidate() {
  if (!dirHandle) { showResult("请先选择保存目录", true); return; }
  if (!await ensureDirPermission()) { showResult("目录访问权限被拒绝，请重新选择目录", true); return; }

  const btn = document.getElementById("consolidateBtn");
  btn.disabled = true;
  showResult("正在分析节点相似度...");

  try {
    const pnData = await readPersistentNodes();
    const nodeCount = Object.keys(pnData.nodes).length;
    if (nodeCount < 2) { showResult("节点数量不足，无需整合"); return; }

    const result = await callDeepSeekForConsolidate(pnData.nodes);
    const { merged } = applyPersistentResult(pnData, result, null);
    await writePersistentNodes(pnData);

    showResult(merged.length
      ? `已合并 ${merged.length} 组节点：\n${merged.join("\n")}`
      : "无需合并，所有节点语义已足够清晰");
  } catch (err) {
    showResult("整合失败：" + err.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Persistent node UI
// ─────────────────────────────────────────────────────────────────────────────

const TYPE_LABELS = {
  preference: "偏好与约束",
  profile:    "用户画像",
  workflow:   "工作流程",
  topic:      "主题与项目",
  platform:   "来源平台",
};

const CONF_DOTS = { high: "●●●", medium: "●●○", low: "●○○" };

function renderPersistentNodes(nodes) {
  const container = document.getElementById("persistentList");
  container.innerHTML = "";

  const entries = Object.entries(nodes);
  if (entries.length === 0) {
    container.innerHTML = '<div class="pn-empty">暂无记忆节点，请先保存记忆</div>';
    return;
  }

  const groups = {};
  for (const [id, node] of entries) {
    if (!groups[node.type]) groups[node.type] = [];
    groups[node.type].push({ id, ...node });
  }

  for (const [type, nodeList] of Object.entries(groups)) {
    const groupEl = document.createElement("div");
    groupEl.className = "pn-group";

    // ── Header ──────────────────────────────────────────────────
    const headerEl = document.createElement("div");
    headerEl.className = "pn-group-header";

    const titleEl = document.createElement("span");
    titleEl.className = "pn-group-title";
    titleEl.textContent = `${TYPE_LABELS[type] || type} (${nodeList.length})`;

    const actionsEl = document.createElement("div");
    actionsEl.className = "pn-group-actions";

    const btnAll = document.createElement("button");
    btnAll.className = "pn-btn-sel";
    btnAll.textContent = "全选";

    const btnNone = document.createElement("button");
    btnNone.className = "pn-btn-sel";
    btnNone.textContent = "全不选";

    const toggleEl = document.createElement("span");
    toggleEl.className = "pn-toggle";
    toggleEl.textContent = "▾";

    actionsEl.append(btnAll, btnNone, toggleEl);
    headerEl.append(titleEl, actionsEl);
    groupEl.appendChild(headerEl);

    // ── Body ─────────────────────────────────────────────────────
    const bodyEl = document.createElement("div");
    bodyEl.className = "pn-body";

    for (const node of nodeList) {
      const nodeEl = document.createElement("div");
      nodeEl.className = "pn-node";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "pn-checkbox";
      cb.dataset.id = node.id;
      cb.checked = node.export_priority === "high";

      const infoEl = document.createElement("div");
      infoEl.className = "pn-info";

      const keyEl = document.createElement("div");
      keyEl.className = "pn-key";
      keyEl.textContent = node.key;

      const descEl = document.createElement("div");
      descEl.className = "pn-desc";
      descEl.textContent = node.description;

      const metaEl = document.createElement("div");
      metaEl.className = "pn-meta";
      metaEl.textContent = `${CONF_DOTS[node.confidence] || "●○○"} · ${node.episode_refs.length} 条记录`;

      infoEl.append(keyEl, descEl, metaEl);
      nodeEl.append(cb, infoEl);
      bodyEl.appendChild(nodeEl);
    }

    groupEl.appendChild(bodyEl);
    container.appendChild(groupEl);

    // ── 事件 ─────────────────────────────────────────────────────
    // 折叠 / 展开（点 header 任意区域，但不触发按钮）
    headerEl.addEventListener("click", e => {
      if (e.target === btnAll || e.target === btnNone) return;
      groupEl.classList.toggle("collapsed");
    });

    btnAll.addEventListener("click", e => {
      e.stopPropagation();
      bodyEl.querySelectorAll(".pn-checkbox").forEach(cb => cb.checked = true);
    });

    btnNone.addEventListener("click", e => {
      e.stopPropagation();
      bodyEl.querySelectorAll(".pn-checkbox").forEach(cb => cb.checked = false);
    });
  }
}

function getSelectedNodeIds() {
  return Array.from(document.querySelectorAll(".pn-checkbox:checked")).map(cb => cb.dataset.id);
}

// ─────────────────────────────────────────────────────────────────────────────
// UI helpers
// ─────────────────────────────────────────────────────────────────────────────

function showResult(text, isError = false) {
  const el = document.getElementById("result");
  el.textContent = text;
  el.classList.remove("hidden", "error");
  if (isError) el.classList.add("error");
}

async function updateDirDisplay() {
  const dirNameEl = document.getElementById("dirName");
  const selectBtn = document.getElementById("selectDirBtn");
  if (!dirHandle) {
    dirNameEl.textContent = "未选择目录";
    selectBtn.textContent = "选择目录";
  } else {
    dirNameEl.textContent = dirHandle.name;
    selectBtn.textContent = "同步";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Messaging helpers
// ─────────────────────────────────────────────────────────────────────────────

function pollJobResult(jobId, timeoutMs = 180000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      chrome.storage.local.get(jobId, items => {
        const result = items[jobId];
        if (result) {
          chrome.storage.local.remove(jobId);
          result.ok ? resolve(result) : reject(new Error(result.error));
        } else if (Date.now() < deadline) {
          setTimeout(check, 800);
        } else {
          reject(new Error("等待超时"));
        }
      });
    };
    check();
  });
}

function submitAndWait(tabId, prompt, isMemory = false, skipDownload = false, timeoutMs = 90000) {
  const jobId = "job_" + Date.now();
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(
      tabId,
      { type: "SUBMIT_AND_WAIT", prompt, jobId, isMemory, skipDownload, timeoutMs },
      res => {
        if (chrome.runtime.lastError || !res?.ok) {
          reject(new Error(res?.error ?? chrome.runtime.lastError?.message));
          return;
        }
        // pollJobResult 超时要比 content.js 的 waitForResponse 多 30s，
        // 保证 content.js 超时后写入 storage，popup 还能读到错误信息
        pollJobResult(jobId, timeoutMs + 30000).then(resolve).catch(reject);
      }
    );
  });
}

function injectInput(tabId, text) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, { type: "INJECT_INPUT", text }, res => {
      if (chrome.runtime.lastError || !res?.ok) {
        reject(new Error(res?.error ?? chrome.runtime.lastError?.message));
      } else {
        resolve();
      }
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Export flow
// ─────────────────────────────────────────────────────────────────────────────

async function handleExport(tab) {
  if (!dirHandle) { showResult("请先选择保存目录", true); return; }
  if (!await ensureDirPermission()) { showResult("目录访问权限被拒绝，请重新选择目录", true); return; }

  const btn = document.getElementById("exportMemoryBtn");
  btn.disabled = true;
  showResult("正在向 AI 发送记忆请求...");

  try {
    // 1. Read persistent nodes (for existing tags)
    const pnData = await readPersistentNodes();

    // 2. Build prompt with existing episodic tags, then send to target AI
    const exportPrompt = buildExportPrompt(pnData.episodic_tag_paths ?? []);
    await injectInput(tab.id, exportPrompt);
    showResult("等待 AI 回复（导出 prompt 较长，可能需要 1-3 分钟）...");
    const res = await submitAndWait(tab.id, exportPrompt, true, true, 300000); // 5 min
    if (!res.text) throw new Error("未获取到 AI 回复内容");

    // 3. Split AI response into memory content + episodic tags
    const { memoryContent, tags: episodicTags } = extractEpisodicTags(res.text);
    mergeEpisodicTagsPN(pnData, episodicTags);

    showResult("AI 已回复，正在提炼持久化记忆节点...");

    // 4. Call DeepSeek to distill persistent nodes
    const result = await callDeepSeekForPersistent(memoryContent, pnData.nodes);

    // 5. Parse AI memory content for L2Wiki structured updates
    let parsed = null;
    try {
      parsed = typeof memoryContent === "string" ? JSON.parse(memoryContent) : memoryContent;
    } catch { /* raw text — skip structured merge */ }

    // 6. Build and save EpisodicMemory (Python-compatible)
    const ep = _newEpisode();
    ep.platform          = _guessPlatform(tab.url);
    ep.topic             = (parsed?.conversation_summary ?? memoryContent ?? "").slice(0, 60);
    ep.summary           = parsed?.conversation_summary ?? "";
    ep.relates_to_projects = (parsed?.active_projects ?? []).map(p => p.project_name).filter(Boolean);
    ep.key_decisions     = (parsed?.active_projects ?? []).flatMap(p =>
      (p.finished_decisions ?? []).map(d => typeof d === "string" ? d : d.text).filter(Boolean)
    );
    ep.open_issues       = (parsed?.active_projects ?? []).flatMap(p =>
      (p.unresolved_questions ?? []).map(q => typeof q === "string" ? q : q.text).filter(Boolean)
    );
    ep.time_range_start  = ep.created_at;
    ep.time_range_end    = ep.created_at;
    await _saveEpisodeToDisk(ep);

    // 7. Merge structured data into L2Wiki files (Python-readable)
    if (parsed) {
      await _mergeProfileFromExport(parsed.user_profile);
      await _mergePrefsFromExport(parsed.preferences);
      for (const p of (parsed.active_projects ?? [])) {
        await _mergeProjectFromExport(p);
      }
    }

    // 8. Apply DeepSeek result to persistent nodes
    const { updated, created, merged } = applyPersistentResult(pnData, result, ep.episode_id);

    // 9. Persist js_persistent_nodes.json
    await writePersistentNodes(pnData);

    const summary = [
      `已保存：${ep.episode_id}`,
      updated.length ? `更新节点：${updated.join(", ")}` : "",
      created.length ? `新建节点：${created.join(", ")}` : "",
      merged.length  ? `合并节点：${merged.join(", ")}` : "",
    ].filter(Boolean).join("\n");
    showResult(summary);
  } catch (err) {
    showResult("保存失败：" + err.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Import flow
// ─────────────────────────────────────────────────────────────────────────────

let _cachedPnData = null;

async function handleShowPanel() {
  const panel = document.getElementById("importPanel");

  // 已展开时再次点击则收起
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }

  if (!dirHandle) { showResult("请先选择保存目录", true); return; }
  if (!await ensureDirPermission()) { showResult("目录访问权限被拒绝，请重新选择目录", true); return; }

  showResult("正在读取记忆节点...");
  try {
    _cachedPnData = await readPersistentNodes();
    renderPersistentNodes(_cachedPnData.nodes);
    panel.classList.remove("hidden");
    document.getElementById("result").classList.add("hidden");
  } catch (err) {
    showResult("读取失败：" + err.message, true);
  }
}

async function handleConfirmImport(tab) {
  const selectedIds = getSelectedNodeIds();
  if (selectedIds.length === 0) { showResult("请至少选中一个记忆节点", true); return; }

  document.getElementById("confirmImportBtn").disabled = true;
  showResult("正在加载记忆内容...");

  try {
    // 1. Full persistent node data for selected nodes
    const persistentNodes = selectedIds.map(id => {
      const n = _cachedPnData.nodes[id];
      return {
        type: n.type, key: n.key, description: n.description,
        confidence: n.confidence, export_priority: n.export_priority,
        episode_refs: n.episode_refs,
      };
    });

    // 2. Collect all unique episodic IDs referenced by selected nodes
    const epIds = new Set(persistentNodes.flatMap(n => n.episode_refs || []));

    // 3. Load episodic content from episodes/ directory (Python-compatible format)
    const episodicEvidence = [];
    for (const epId of epIds) {
      const ep = await _loadEpisodeById(epId);
      if (!ep) continue;
      episodicEvidence.push({
        id:                  ep.episode_id,
        topic:               ep.topic,
        created_at:          ep.created_at,
        summary:             ep.summary,
        key_decisions:       ep.key_decisions,
        open_issues:         ep.open_issues,
        relates_to_projects: ep.relates_to_projects,
      });
    }

    // 4. Build rich memory package
    const pkg = JSON.stringify({
      memory_package: {
        loaded_at:         new Date().toISOString(),
        persistent_nodes:  persistentNodes,
        episodic_evidence: episodicEvidence,
      }
    }, null, 2);

    chrome.tabs.sendMessage(
      tab.id,
      { type: "UPLOAD_FILE", fileBuffer: pkg, fileName: "memory_package.json", promptText: CONFIG.load },
      res => {
        document.getElementById("confirmImportBtn").disabled = false;
        if (chrome.runtime.lastError || !res?.ok) {
          showResult("注入失败：" + (res?.error ?? chrome.runtime.lastError?.message), true);
          return;
        }
        document.getElementById("importPanel").classList.add("hidden");
        showResult(`已导入 ${persistentNodes.length} 个节点 + ${episodicEvidence.length} 条原始记录`);
      }
    );
  } catch (err) {
    document.getElementById("confirmImportBtn").disabled = false;
    showResult("导入失败：" + err.message, true);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Event listeners
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById("apiKeyBtn").addEventListener("click", () => {
  const panel = document.getElementById("apiKeyPanel");
  const isHidden = panel.classList.toggle("hidden");
  if (!isHidden) {
    const input = document.getElementById("apiKeyInput");
    input.value = _apiKey;
    input.focus();
  }
});

document.getElementById("apiKeySaveBtn").addEventListener("click", async () => {
  const key = document.getElementById("apiKeyInput").value.trim();
  await saveApiKey(key);
  updateApiKeyDisplay();
  document.getElementById("apiKeyPanel").classList.add("hidden");
  showResult(key ? "API Key 已保存" : "API Key 已清除");
});

document.getElementById("selectDirBtn").addEventListener("click", async () => {
  try {
    if (dirHandle) {
      // 目录已选：只重新授权（user gesture 可用），无需重新选择
      const perm = await dirHandle.requestPermission({ mode: "readwrite" });
      if (perm !== "granted") { showResult("权限被拒绝", true); return; }
    } else {
      // 第一次选目录
      dirHandle = await pickDirectory();
    }
    await updateDirDisplay();
    document.getElementById("importPanel").classList.add("hidden");

    // 有未处理的 RAW 数据时，先提取 episode 再同步
    let extractResult = null;
    const apiSettings = await new Promise(r => chrome.storage.local.get("deepseek_api_key", r));
    if (apiSettings["deepseek_api_key"]) {
      showResult("正在从 RAW 对话提取 episode...");

      // 轮询进度，每秒更新一次状态文字
      const progressTimer = setInterval(async () => {
        const pd = await new Promise(r => chrome.storage.local.get("_raw_progress", r));
        const prog = pd["_raw_progress"];
        if (prog) {
          const pct = prog.total > 0 ? Math.round((prog.current / prog.total) * 100) : 0;
          const bar = "█".repeat(Math.floor(pct / 5)) + "░".repeat(20 - Math.floor(pct / 5));
          showResult(`提取 episode 中...\n[${bar}] ${prog.current}/${prog.total}`);
        }
      }, 1000);

      try {
        extractResult = await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage({ type: "PROCESS_ALL_RAW", limit: 10 }, res => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else if (!res?.ok) reject(new Error(res?.error ?? "处理失败"));
            else resolve(res);
          });
        });
        if (extractResult.processed > 0) {
          console.log(`[Popup] 已从 ${extractResult.processed} 条对话提取 episode，还剩 ${extractResult.remaining}`);
        }
      } catch (err) {
        console.warn("[Popup] episode 提取失败（跳过，继续同步）:", err.message);
      } finally {
        clearInterval(progressTimer);
      }
    }

    // 同步 chrome.storage → 文件
    showResult("正在同步记忆到文件...");
    await _syncStorageToFiles();

    const allData = await new Promise(r => chrome.storage.local.get(null, r));
    const count = Object.keys(allData).filter(k => k.startsWith("mw:")).length;
    const remaining = extractResult?.remaining ?? 0;
    const baseMsg = count > 0 ? `已同步 ${count} 条记忆到文件` : "目录已授权（暂无记忆数据）";
    showResult(remaining > 0
      ? `${baseMsg}\n还有 ${remaining} 条对话待提取，再次点击同步继续`
      : baseMsg);
  } catch (err) {
    if (err.name !== "AbortError") showResult("操作失败：" + err.message, true);
  }
});

document.getElementById("exportMemoryBtn").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || /^(chrome|chrome-extension|about|edge):\/\//.test(tab.url)) {
    showResult("此页面不支持注入", true); return;
  }
  handleExport(tab);
});

document.getElementById("importFileBtn").addEventListener("click", () => {
  document.getElementById("importFileInput").click();
});

document.getElementById("importFileInput").addEventListener("change", async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  e.target.value = "";
  await handleImportFile(file);
});

document.getElementById("rebuildBtn").addEventListener("click", () => {
  handleRebuildFromEpisodes();
});

document.getElementById("consolidateBtn").addEventListener("click", () => {
  handleConsolidate();
});

document.getElementById("importMemoryBtn").addEventListener("click", () => {
  handleShowPanel();
});

document.getElementById("confirmImportBtn").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || /^(chrome|chrome-extension|about|edge):\/\//.test(tab.url)) {
    showResult("此页面不支持注入", true); return;
  }
  handleConfirmImport(tab);
});

// ─────────────────────────────────────────────────────────────────────────────
// 保持更新 / 实时更新 开关
// ─────────────────────────────────────────────────────────────────────────────

async function loadToggles() {
  const { keepUpdated, realtimeUpdate } = await chrome.storage.local.get(["keepUpdated", "realtimeUpdate"]);
  document.getElementById("keepUpdatedToggle").checked = !!keepUpdated;
  document.getElementById("realtimeUpdateToggle").checked = !!realtimeUpdate;
  document.getElementById("realtimeRow").style.display = keepUpdated ? "" : "none";
}

document.getElementById("keepUpdatedToggle").addEventListener("change", async (e) => {
  const enabled = e.target.checked;
  await chrome.storage.local.set({ keepUpdated: enabled });
  document.getElementById("realtimeRow").style.display = enabled ? "" : "none";

  const tabs = await chrome.tabs.query({});
  for (const tab of tabs) {
    if (!tab.url || /^(chrome|chrome-extension|about|edge):\/\//.test(tab.url)) continue;
    chrome.tabs.sendMessage(tab.id, { type: "TOGGLE_CAPTURE", enabled }).catch(() => {});
  }

  showResult(enabled ? "保持更新已开启" : "保持更新已关闭");
});

document.getElementById("realtimeUpdateToggle").addEventListener("change", async (e) => {
  await chrome.storage.local.set({ realtimeUpdate: e.target.checked });
  showResult(e.target.checked ? "实时更新已开启（每轮对话后自动构建记忆）" : "实时更新已关闭");
});

// ─────────────────────────────────────────────────────────────────────────────
// 同步 chrome.storage.local → 文件系统
// background.js 的 LLM 处理结果存在 chrome.storage（mw:* 前缀），
// popup 打开时将其同步到文件，供 Python CLI 读取。
// ─────────────────────────────────────────────────────────────────────────────

async function _syncStorageToFiles() {
  if (!dirHandle) return;
  // 调用方负责在 user gesture 上下文中已通过 requestPermission 授权

  const allData = await new Promise(resolve => chrome.storage.local.get(null, resolve));

  let synced = 0;

  // Profile
  const profile = allData["mw:profile"];
  if (profile) { await _writeJson(dirHandle, "profile.json", profile); synced++; }

  // Preferences
  const prefs = allData["mw:preferences"];
  if (prefs) { await _writeJson(dirHandle, "preferences.json", prefs); synced++; }

  // Workflows
  const workflows = allData["mw:workflows"];
  if (workflows?.length) { await _writeJson(dirHandle, "workflows.json", workflows); synced++; }

  // Projects
  const projEntries = Object.entries(allData).filter(([k]) => k.startsWith("mw:projects:"));
  if (projEntries.length > 0) {
    const projDir = await _getSubDir("projects");
    for (const [k, v] of projEntries) {
      const name = decodeURIComponent(k.slice("mw:projects:".length));
      const safeName = name.toLowerCase().replace(/[\s/]/g, "_").slice(0, 64);
      await _writeJson(projDir, `${safeName}.json`, v);
      synced++;
    }
  }

  // Episodes
  const epEntries = Object.entries(allData).filter(([k]) => k.startsWith("mw:episodes:"));
  if (epEntries.length > 0) {
    const epDir = await _getSubDir("episodes");
    for (const [, ep] of epEntries) {
      const epId = ep.episode_id ?? crypto.randomUUID().slice(0, 8);
      await _writeJson(epDir, `${epId}.json`, ep);
      synced++;
    }
  }

  // Persistent nodes → js_persistent_nodes.json
  const pn = allData["mw:persistent_nodes"];
  if (pn) { await _writeJson(dirHandle, "js_persistent_nodes.json", pn); synced++; }

  // Raw conversations: chat:{platform}:{chatId} → raw/{platform}/{chatId}.json
  // 同时对 rounds 去重（user+assistant 完全相同则保留首条）
  const rawEntries = Object.entries(allData).filter(([k]) => k.startsWith("chat:"));
  if (rawEntries.length > 0) {
    const rawRootDir = await _getSubDir("raw");
    const storageUpdates = {};
    for (const [k, chatData] of rawEntries) {
      const parts = k.split(":");
      const platform = parts[1];
      const chatId = parts.slice(2).join(":");
      if (!platform || !chatId) continue;

      // 去重 rounds
      const seen = new Set();
      const dedupedRounds = (chatData.rounds ?? []).filter(r => {
        const key = r.user + "\x00" + r.assistant;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      const removedCount = (chatData.rounds ?? []).length - dedupedRounds.length;
      if (removedCount > 0) {
        chatData.rounds = dedupedRounds;
        // last_processed_idx 不能超过新的 rounds 长度
        if (chatData.last_processed_idx > dedupedRounds.length) {
          chatData.last_processed_idx = dedupedRounds.length;
        }
        storageUpdates[k] = chatData;
        console.log(`[Popup] 去重 ${k}：移除 ${removedCount} 条重复 rounds`);
      }

      const platformDir = await rawRootDir.getDirectoryHandle(platform, { create: true });
      const safeId = chatId.replace(/[^a-zA-Z0-9\-_]/g, "_");
      await _writeJson(platformDir, `${safeId}.json`, chatData);
      synced++;
    }
    // 将去重后的数据写回 storage
    if (Object.keys(storageUpdates).length > 0) {
      await new Promise(r => chrome.storage.local.set(storageUpdates, r));
    }
  }

  if (synced > 0) console.log(`[Popup] 已同步 ${synced} 条记忆到文件`);
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────

(async () => {
  await loadApiKey();
  updateApiKeyDisplay();
  dirHandle = await loadSavedDir();
  await updateDirDisplay();
  await loadToggles();
})();
