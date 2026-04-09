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
  const perm = await saved.queryPermission({ mode: "readwrite" });
  return perm === "granted" ? saved : saved; // keep handle; permission checked on first action
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
// Index (index.json) — master index for episodic + persistent layers
// ─────────────────────────────────────────────────────────────────────────────

/*
  Directory layout:
    <dir>/
    ├── index.json          ← episodic metadata + all persistent nodes
    └── ep/
        ├── ep_0001.json    ← raw AI memory export (episodic)
        └── ep_0002.json

  index.json structure:
  {
    "version": "2.0",
    "updated_at": "...",
    "ep_next_id": 1,
    "pn_next_id": 1,
    "episodics": {
      "ep_0001": { "file": "ep_0001.json", "title": "...", "created_at": "...", "platform": "..." }
    },
    "persistents": {
      "pn_0001": {
        "type": "preference",          // preference | profile | workflow | topic | platform
        "key": "prefer_structured_output",
        "description": "用户稳定偏好结构清晰、分层明确的输出形式",
        "episode_refs": ["ep_0001"],   // supporting episodic IDs
        "confidence": "high",          // high | medium | low
        "export_priority": "high",     // high | medium | low
        "created_at": "...",
        "updated_at": "..."
      }
    }
  }
*/

const INDEX_FILE = "index.json";

async function readIndex() {
  try {
    const fh = await dirHandle.getFileHandle(INDEX_FILE);
    const data = JSON.parse(await (await fh.getFile()).text());
    // Migrate older index.json that lacks episodic_tag_paths
    if (!data.episodic_tag_paths) data.episodic_tag_paths = [];
    if (!data.episodics)          data.episodics = {};
    if (!data.persistents)        data.persistents = {};
    return data;
  } catch {
    return {
      version: "2.0",
      ep_next_id: 1,
      pn_next_id: 1,
      episodic_tag_paths: [],
      episodics: {},
      persistents: {},
    };
  }
}

async function writeIndex(data) {
  data.updated_at = new Date().toISOString();
  const fh = await dirHandle.getFileHandle(INDEX_FILE, { create: true });
  const w = await fh.createWritable();
  await w.write(JSON.stringify(data, null, 2));
  await w.close();
}

async function getEpDir() {
  return dirHandle.getDirectoryHandle("ep", { create: true });
}

async function saveEpisodicFile(epDir, id, content) {
  const filename = `${id}.json`;
  const fh = await epDir.getFileHandle(filename, { create: true });
  const w = await fh.createWritable();
  await w.write(typeof content === "string" ? content : JSON.stringify(content, null, 2));
  await w.close();
  return filename;
}

async function readEpisodicFile(epId, index) {
  const meta = index.episodics[epId];
  if (!meta) throw new Error(`找不到 episodic 记录: ${epId}`);
  const epDir = await getEpDir();
  const fh = await epDir.getFileHandle(meta.file);
  return (await fh.getFile()).text();
}

// ─────────────────────────────────────────────────────────────────────────────
// Export prompt builder — injects existing episodic tag paths into the skill
// ─────────────────────────────────────────────────────────────────────────────

function buildExportPrompt(existingTagPaths) {
  const tagsList = existingTagPaths.length > 0
    ? existingTagPaths.join("\n")
    : "（暂无已有标签，请按规范新建）";
  // Only send episodicTag — target AI doesn't need the two-layer architecture definition
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

// Merge new tag paths into index.episodic_tag_paths (deduplication)
function mergeEpisodicTags(index, tagsResult) {
  if (!tagsResult) return [];
  const existing = new Set(index.episodic_tag_paths);
  const added = [];
  for (const path of (tagsResult.use_existing || [])) {
    if (!existing.has(path)) { existing.add(path); added.push(path); }
  }
  for (const { path } of (tagsResult.new_tags || [])) {
    if (!existing.has(path)) { existing.add(path); added.push(path); }
  }
  index.episodic_tag_paths = Array.from(existing);
  return [
    ...(tagsResult.use_existing || []),
    ...(tagsResult.new_tags || []).map(t => t.path),
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// DeepSeek API — distill persistent nodes from a new episodic memory
// ─────────────────────────────────────────────────────────────────────────────

async function callDeepSeekForPersistent(memoryText, existingPersistents) {
  if (!_apiKey) throw new Error("未配置 DeepSeek API Key，请点击「设置」按钮填写");
  const memStr = (typeof memoryText === "string" ? memoryText : JSON.stringify(memoryText)).slice(0, 3000);

  // Compact summary of existing nodes to save tokens
  const existingSummary = Object.entries(existingPersistents).map(([id, n]) => ({
    id, type: n.type, key: n.key, description: n.description,
    confidence: n.confidence, refs: n.episode_refs.length,
  }));

  const userMsg = `【现有 Persistent 节点】
${JSON.stringify(existingSummary, null, 2)}

【新 Episodic 记忆内容】
${memStr}`;

  const resp = await fetch(CONFIG.deepseek.endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${_apiKey}`,
    },
    body: JSON.stringify({
      model: CONFIG.deepseek.model,
      messages: [
        // architecture + persistentDistill as system context — stable across calls
        { role: "system", content: CONFIG.skills.architecture + "\n\n" + CONFIG.skills.persistentDistill },
        { role: "user",   content: userMsg },
      ],
      temperature: 0.2,
      max_tokens: 800,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`DeepSeek 请求失败 ${resp.status}: ${err.slice(0, 80)}`);
  }
  const data = await resp.json();
  const raw = data.choices[0].message.content.trim();
  const m = raw.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("DeepSeek 返回格式异常");
  return JSON.parse(m[0]);
}

// Apply DeepSeek result to index.persistents; returns summary string for display
// epId may be null when called from consolidation-only flow (no new episodic)
function applyPersistentResult(index, result, epId) {
  const now = new Date().toISOString();
  const updated = [];
  const created = [];
  const merged = [];

  for (const upd of (result.updates || [])) {
    const node = index.persistents[upd.id];
    if (!node) continue;
    if (epId && !node.episode_refs.includes(epId)) node.episode_refs.push(epId);
    if (upd.description) node.description = upd.description;
    if (upd.confidence) node.confidence = upd.confidence;
    node.updated_at = now;
    updated.push(node.key);
  }

  for (const nn of (result.new_nodes || [])) {
    const pnId = `pn_${String(index.pn_next_id).padStart(4, "0")}`;
    index.pn_next_id += 1;
    index.persistents[pnId] = {
      type: nn.type,
      key: nn.key,
      description: nn.description,
      episode_refs: epId ? [epId] : [],
      confidence: nn.confidence || "low",
      export_priority: nn.export_priority || "medium",
      created_at: now,
      updated_at: now,
    };
    created.push(nn.key);
  }

  for (const mg of (result.merges || [])) {
    const target = index.persistents[mg.merged_into];
    if (!target) continue;
    // merged_from may be a string or an array
    const sources = Array.isArray(mg.merged_from) ? mg.merged_from : [mg.merged_from];
    const sourceKeys = [];
    for (const srcId of sources) {
      const source = index.persistents[srcId];
      if (!source) continue;
      for (const ref of source.episode_refs) {
        if (!target.episode_refs.includes(ref)) target.episode_refs.push(ref);
      }
      sourceKeys.push(source.key);
      delete index.persistents[srcId];
    }
    if (sourceKeys.length === 0) continue;
    // Recalculate confidence from merged ref count
    const refCount = target.episode_refs.length;
    if (refCount >= 4) target.confidence = "high";
    else if (refCount >= 2) target.confidence = "medium";
    if (mg.description) target.description = mg.description;
    target.updated_at = now;
    merged.push(`[${sourceKeys.join(", ")}] → ${target.key}`);
  }

  return { updated, created, merged };
}

// Consolidation-only call: send all existing persistents, ask DeepSeek to find merges
async function callDeepSeekForConsolidate(existingPersistents) {
  if (!_apiKey) throw new Error("未配置 DeepSeek API Key，请点击「设置」按钮填写");
  const allNodes = Object.entries(existingPersistents).map(([id, n]) => ({
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
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${_apiKey}`,
    },
    body: JSON.stringify({
      model: CONFIG.deepseek.model,
      messages: [
        { role: "system", content: CONFIG.skills.architecture + "\n\n" + CONFIG.skills.persistentDistill },
        { role: "user",   content: userMsg },
      ],
      temperature: 0.2,
      max_tokens: 400,
    }),
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => "");
    throw new Error(`DeepSeek 请求失败 ${resp.status}: ${err.slice(0, 80)}`);
  }
  const data = await resp.json();
  const raw = data.choices[0].message.content.trim();
  const m = raw.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("DeepSeek 返回格式异常");
  return JSON.parse(m[0]);
}

async function handleConsolidate() {
  if (!dirHandle) { showResult("请先选择保存目录", true); return; }
  if (!await ensureDirPermission()) { showResult("目录访问权限被拒绝，请重新选择目录", true); return; }

  const btn = document.getElementById("consolidateBtn");
  btn.disabled = true;
  showResult("正在分析节点相似度...");

  try {
    const index = await readIndex();
    const nodeCount = Object.keys(index.persistents).length;
    if (nodeCount < 2) { showResult("节点数量不足，无需整合"); return; }

    const result = await callDeepSeekForConsolidate(index.persistents);
    const { merged } = applyPersistentResult(index, result, null);
    await writeIndex(index);

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

function renderPersistentNodes(persistents) {
  const container = document.getElementById("persistentList");
  container.innerHTML = "";

  const entries = Object.entries(persistents);
  if (entries.length === 0) {
    container.innerHTML = '<div class="pn-empty">暂无记忆节点，请先保存记忆</div>';
    return;
  }

  // Group by type
  const groups = {};
  for (const [id, node] of entries) {
    if (!groups[node.type]) groups[node.type] = [];
    groups[node.type].push({ id, ...node });
  }

  // Render each group
  for (const [type, nodes] of Object.entries(groups)) {
    const groupEl = document.createElement("div");
    groupEl.className = "pn-group";

    const headerEl = document.createElement("div");
    headerEl.className = "pn-group-header";
    headerEl.textContent = `${TYPE_LABELS[type] || type}  (${nodes.length})`;
    groupEl.appendChild(headerEl);

    for (const node of nodes) {
      const nodeEl = document.createElement("div");
      nodeEl.className = "pn-node";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "pn-checkbox";
      cb.dataset.id = node.id;
      // Pre-check high-priority nodes
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
      groupEl.appendChild(nodeEl);
    }

    container.appendChild(groupEl);
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
  const el = document.getElementById("dirName");
  if (!dirHandle) { el.textContent = "未选择目录"; return; }
  const perm = await dirHandle.queryPermission({ mode: "readwrite" });
  el.textContent = perm === "granted" ? dirHandle.name : `${dirHandle.name}（点击按钮重新授权）`;
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

function submitAndWait(tabId, prompt, isMemory = false, skipDownload = false) {
  const jobId = "job_" + Date.now();
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(
      tabId,
      { type: "SUBMIT_AND_WAIT", prompt, jobId, isMemory, skipDownload },
      res => {
        if (chrome.runtime.lastError || !res?.ok) {
          reject(new Error(res?.error ?? chrome.runtime.lastError?.message));
          return;
        }
        pollJobResult(jobId).then(resolve).catch(reject);
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
    // 1. Read index first (need existing tags for the prompt)
    const index = await readIndex();

    // 2. Build prompt with existing episodic tags injected, then send to target AI
    const exportPrompt = buildExportPrompt(index.episodic_tag_paths);
    await injectInput(tab.id, exportPrompt);
    showResult("等待 AI 回复...");
    const res = await submitAndWait(tab.id, exportPrompt, true, true);
    if (!res.text) throw new Error("未获取到 AI 回复内容");

    // 3. Split AI response into memory content + episodic tags
    const { memoryContent, tags: episodicTags } = extractEpisodicTags(res.text);
    const assignedTags = mergeEpisodicTags(index, episodicTags);

    showResult("AI 已回复，正在提炼持久化记忆节点...");

    // 4. Call DeepSeek to distill persistent nodes
    const result = await callDeepSeekForPersistent(memoryContent, index.persistents);

    // 5. Save episodic raw file (clean memory content, tags stripped)
    const epId = `ep_${String(index.ep_next_id).padStart(4, "0")}`;
    index.ep_next_id += 1;
    const epDir = await getEpDir();
    const filename = await saveEpisodicFile(epDir, epId, memoryContent);

    // 6. Update persistent nodes
    const { updated, created, merged } = applyPersistentResult(index, result, epId);

    // 7. Record episodic metadata (with its tags)
    index.episodics[epId] = {
      file: filename,
      title: `记忆 ${new Date().toLocaleDateString("zh-CN")}`,
      created_at: new Date().toISOString(),
      tags: assignedTags,
    };

    // 6. Persist index
    await writeIndex(index);

    const summary = [
      `已保存：${epId}`,
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

let _cachedIndex = null;

async function handleShowPanel() {
  if (!dirHandle) { showResult("请先选择保存目录", true); return; }
  if (!await ensureDirPermission()) { showResult("目录访问权限被拒绝，请重新选择目录", true); return; }

  showResult("正在读取记忆节点...");
  try {
    _cachedIndex = await readIndex();
    renderPersistentNodes(_cachedIndex.persistents);
    document.getElementById("importPanel").classList.remove("hidden");
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
      const n = _cachedIndex.persistents[id];
      return {
        type:             n.type,
        key:              n.key,
        description:      n.description,
        confidence:       n.confidence,
        export_priority:  n.export_priority,
        episode_refs:     n.episode_refs,
      };
    });

    // 2. Collect all unique episodic IDs referenced by selected nodes
    const epIds = new Set(persistentNodes.flatMap(n => n.episode_refs || []));

    // 3. Load episodic raw content as evidence
    const episodicEvidence = [];
    for (const epId of epIds) {
      const meta = _cachedIndex.episodics[epId];
      if (!meta) continue;
      try {
        const text = await readEpisodicFile(epId, _cachedIndex);
        let content;
        try { content = JSON.parse(text); } catch { content = { raw: text }; }
        episodicEvidence.push({
          id:         epId,
          title:      meta.title,
          created_at: meta.created_at,
          tags:       meta.tags || [],
          content,
        });
      } catch { /* skip unreadable file */ }
    }

    // 4. Build rich memory package:
    //    - persistent_nodes: distilled patterns (the "what")
    //    - episodic_evidence: original conversation exports (the "why / detail")
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
    dirHandle = await pickDirectory();
    await updateDirDisplay();
    document.getElementById("importPanel").classList.add("hidden");
    showResult("目录已选择：" + dirHandle.name);
  } catch (err) {
    if (err.name !== "AbortError") showResult("选择失败：" + err.message, true);
  }
});

document.getElementById("exportMemoryBtn").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url || /^(chrome|chrome-extension|about|edge):\/\//.test(tab.url)) {
    showResult("此页面不支持注入", true); return;
  }
  handleExport(tab);
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
// Init
// ─────────────────────────────────────────────────────────────────────────────

(async () => {
  await loadApiKey();
  updateApiKeyDisplay();
  dirHandle = await loadSavedDir();
  await updateDirDisplay();
})();
