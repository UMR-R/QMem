const DB_NAME = "MemAssistDB";
const DB_STORE = "settings";
const DIR_KEY = "dirHandle";

const STORAGE_KEYS = {
  apiKey: "deepseek_api_key",
  backendUrl: "backend_url",
  keepUpdated: "keepUpdated",
  realtimeUpdate: "realtimeUpdate",
  lastSyncAt: "last_sync_at",
  savedSkills: "saved_skill_ids",
};

const state = {
  dirHandle: null,
  apiKey: "",
  backendUrl: "http://127.0.0.1:8765",
  keepUpdated: false,
  realtimeUpdate: false,
  lastSyncAt: null,
  currentView: "home",
  currentSkillTab: "my",
  selectedSkillIds: new Set(),
  selectedRecommendedIds: new Set(),
  categories: {
    profile: 0,
    preferences: 0,
    projects: 0,
    workflows: 0,
    persistent: 0,
  },
};

const recommendedSkills = [
  {
    id: "rec:pdf_reader",
    icon: "PDF",
    title: "读 PDF",
    description: "快速提取 PDF 的结构、要点与关键结论。",
  },
  {
    id: "rec:paper_summary",
    icon: "研",
    title: "读文献总结",
    description: "按问题、方法、结果、局限结构化整理论文。",
  },
  {
    id: "rec:project_plan",
    icon: "计",
    title: "项目规划",
    description: "拆解任务、设定优先级并生成执行路径。",
  },
];

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

function storageGet(keys) {
  return new Promise(resolve => chrome.storage.local.get(keys, resolve));
}

function storageSet(obj) {
  return new Promise(resolve => chrome.storage.local.set(obj, resolve));
}

function runtimeSendMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, res => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}

function tabsQuery(queryInfo) {
  return new Promise(resolve => chrome.tabs.query(queryInfo, resolve));
}

function tabsSendMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, message, res => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}

async function loadSavedDir() {
  return dbGet(DIR_KEY);
}

async function ensureDirPermission() {
  if (!state.dirHandle) return false;
  const permission = await state.dirHandle.queryPermission({ mode: "readwrite" });
  if (permission === "granted") return true;
  const requested = await state.dirHandle.requestPermission({ mode: "readwrite" });
  return requested === "granted";
}

async function pickDirectory() {
  const handle = await window.showDirectoryPicker({ mode: "readwrite" });
  await dbSet(DIR_KEY, handle);
  state.dirHandle = handle;
  renderDirectory();
  toast(`目录已设置：${handle.name}`);
}

async function readJson(dir, filename) {
  try {
    const fh = await dir.getFileHandle(filename);
    return JSON.parse(await (await fh.getFile()).text());
  } catch {
    return null;
  }
}

async function writeJson(dir, filename, data) {
  const fh = await dir.getFileHandle(filename, { create: true });
  const writable = await fh.createWritable();
  await writable.write(JSON.stringify(data, null, 2));
  await writable.close();
}

async function getSubDir(name) {
  return state.dirHandle.getDirectoryHandle(name, { create: true });
}

async function readPersistentNodes() {
  const stored = await storageGet("mw:persistent_nodes");
  if (stored["mw:persistent_nodes"]) return stored["mw:persistent_nodes"];
  return (state.dirHandle ? await readJson(state.dirHandle, "js_persistent_nodes.json") : null)
    ?? { version: "1.0", pn_next_id: 1, episodic_tag_paths: [], nodes: {} };
}

async function loadEpisodeById(epId) {
  const key = `mw:episodes:${epId}`;
  const stored = await storageGet(key);
  if (stored[key]) return stored[key];
  if (!state.dirHandle) return null;
  try {
    const epDir = await getSubDir("episodes");
    return await readJson(epDir, `${epId}.json`);
  } catch {
    return null;
  }
}

function formatRelativeTime(isoString) {
  if (!isoString) return "未开始";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "未开始";
  const diff = Date.now() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diff < minute) return "刚刚";
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`;
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`;
  return `${Math.floor(diff / day)} 天前`;
}

function toast(message, isError = false) {
  const toastEl = document.getElementById("toast");
  toastEl.textContent = message;
  toastEl.classList.remove("hidden");
  toastEl.style.background = isError ? "rgba(176, 43, 43, 0.94)" : "rgba(22, 33, 58, 0.92)";
  clearTimeout(toastEl._timer);
  toastEl._timer = setTimeout(() => toastEl.classList.add("hidden"), 3200);
}

function setView(viewName) {
  state.currentView = viewName;
  for (const view of document.querySelectorAll(".view")) {
    view.classList.toggle("is-active", view.id === `${viewName}View`);
  }
}

function renderSync() {
  const syncBtn = document.getElementById("syncBtn");
  const dot = document.getElementById("syncDot");
  document.getElementById("syncStatusText").textContent = state.keepUpdated ? "同步中" : "同步已暂停";
  document.getElementById("syncHintText").textContent = state.keepUpdated
    ? "持续记录你与大模型的对话"
    : "点击开启后，持续记录你与大模型的对话";
  syncBtn.classList.toggle("is-active", state.keepUpdated);
  syncBtn.setAttribute("aria-pressed", String(state.keepUpdated));
  dot.classList.toggle("is-active", state.keepUpdated);
}

function renderStats(summary) {
  document.getElementById("lastSyncValue").textContent = formatRelativeTime(summary.lastSyncAt);
  document.getElementById("conversationCountValue").textContent = `${summary.conversationCount} 条`;
  document.getElementById("memoryCountValue").textContent = `${summary.memoryItemCount} 条`;
}

function renderDirectory() {
  const name = state.dirHandle?.name ?? "";
  document.getElementById("storageDirInput").value = name ? name : "";
  document.getElementById("storageDirInput").placeholder = name ? "" : "请选择本地存储目录";
}

function renderSettings() {
  document.getElementById("apiKeyInput").value = state.apiKey;
  document.getElementById("backendUrlInput").value = state.backendUrl;
  document.getElementById("keepUpdatedToggle").checked = state.keepUpdated;
  document.getElementById("realtimeUpdateToggle").checked = state.realtimeUpdate;
  document.getElementById("apiKeyStatus").textContent = state.apiKey
    ? `API Key: ${"●".repeat(8)}`
    : "API Key: 未配置";
}

function renderCategoryCounts() {
  document.getElementById("countProfile").textContent = state.categories.profile;
  document.getElementById("countPreferences").textContent = state.categories.preferences;
  document.getElementById("countProjects").textContent = state.categories.projects;
  document.getElementById("countWorkflows").textContent = state.categories.workflows;
  document.getElementById("countPersistent").textContent = state.categories.persistent;
}

function deriveMySkills(allData, pnData) {
  const skills = [];
  const workflows = allData["mw:workflows"] ?? [];
  workflows.slice(0, 4).forEach((workflow, index) => {
    skills.push({
      id: `workflow:${workflow.workflow_name || index}`,
      icon: "流",
      title: workflow.workflow_name || `工作流 ${index + 1}`,
      description: workflow.preferred_artifact_format || workflow.trigger_condition || "从你的记忆里提炼出的工作流程。",
    });
  });

  const nodes = Object.entries(pnData.nodes ?? {}).slice(0, Math.max(0, 4 - skills.length));
  nodes.forEach(([id, node]) => {
    skills.push({
      id: `persistent:${id}`,
      icon: "忆",
      title: node.description || node.key || id,
      description: `${node.type || "memory"} · 由长期对话稳定提炼出的习惯与能力。`,
    });
  });

  if (skills.length === 0) {
    skills.push({
      id: "skill:empty",
      icon: "空",
      title: "你的 Skill 会显示在这里",
      description: "先开启同步或整理记忆，系统会逐步从工作流和长期记忆里提炼 Skill。",
      selectable: false,
    });
  }

  return skills;
}

function renderSkillList(items, selectedSet) {
  const listEl = document.getElementById("skillList");
  listEl.innerHTML = "";

  items.forEach(item => {
    const wrapper = document.createElement("label");
    wrapper.className = "skill-item";
    const selectionNode = item.selectable === false
      ? `<div class="skill-check-placeholder"></div>`
      : `<input class="skill-check" type="checkbox" ${selectedSet.has(item.id) ? "checked" : ""}>`;
    wrapper.innerHTML = `
      <div class="skill-icon">${item.icon}</div>
      <div class="skill-copy">
        <h4>${item.title}</h4>
        <p>${item.description}</p>
      </div>
      ${selectionNode}
    `;
    const checkbox = wrapper.querySelector("input");
    if (checkbox) {
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedSet.add(item.id);
        else selectedSet.delete(item.id);
      });
    }
    listEl.appendChild(wrapper);
  });
}

async function refreshSummary() {
  const allData = await storageGet(null);
  const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
  const workflows = allData["mw:workflows"] ?? [];
  const projects = Object.keys(allData).filter(key => key.startsWith("mw:projects:"));
  const episodes = Object.keys(allData).filter(key => key.startsWith("mw:episodes:"));
  const conversations = Object.keys(allData).filter(key => key.startsWith("chat:"));

  state.categories.profile = allData["mw:profile"] ? 1 : 0;
  state.categories.preferences = allData["mw:preferences"] ? 1 : 0;
  state.categories.projects = projects.length;
  state.categories.workflows = workflows.length;
  state.categories.persistent = Object.keys(pnData.nodes ?? {}).length;

  renderCategoryCounts();

  const summary = {
    lastSyncAt: state.lastSyncAt,
    conversationCount: conversations.length,
    memoryItemCount:
      state.categories.profile +
      state.categories.preferences +
      state.categories.projects +
      state.categories.workflows +
      state.categories.persistent +
      episodes.length,
  };

  renderStats(summary);
  const mySkills = deriveMySkills(allData, pnData);
  if (state.currentSkillTab === "my") renderSkillList(mySkills, state.selectedSkillIds);
}

async function saveSettings() {
  state.apiKey = document.getElementById("apiKeyInput").value.trim();
  state.backendUrl = document.getElementById("backendUrlInput").value.trim() || "http://127.0.0.1:8765";
  await storageSet({
    [STORAGE_KEYS.apiKey]: state.apiKey,
    [STORAGE_KEYS.backendUrl]: state.backendUrl,
  });
  renderSettings();
  toast("设置已保存");
}

async function testConnection() {
  const url = (document.getElementById("backendUrlInput").value.trim() || state.backendUrl).replace(/\/$/, "");
  try {
    const response = await fetch(`${url}/api/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    toast("本地后端连接正常");
  } catch (err) {
    toast(`连接失败：${err.message}`, true);
  }
}

async function broadcastCaptureToggle(enabled) {
  const tabs = await tabsQuery({});
  await Promise.allSettled(
    tabs
      .filter(tab => tab.id && tab.url && !/^(chrome|chrome-extension|about|edge):\/\//.test(tab.url))
      .map(tab => tabsSendMessage(tab.id, { type: "TOGGLE_CAPTURE", enabled }))
  );
}

async function toggleSync() {
  state.keepUpdated = !state.keepUpdated;
  await storageSet({ [STORAGE_KEYS.keepUpdated]: state.keepUpdated });
  await broadcastCaptureToggle(state.keepUpdated);
  renderSync();
  renderSettings();
  toast(state.keepUpdated ? "同步已开启" : "同步已暂停");
}

async function runOrganize() {
  const organizeBtn = document.getElementById("organizeBtn");
  organizeBtn.disabled = true;
  organizeBtn.style.opacity = "0.65";

  try {
    let extractResult = null;
    if (state.apiKey) {
      toast("正在整理记忆...");
      extractResult = await runtimeSendMessage({ type: "PROCESS_ALL_RAW", limit: 10 });
      if (!extractResult?.ok) throw new Error(extractResult?.error ?? "整理失败");
    }

    if (state.dirHandle && await ensureDirPermission()) {
      await syncStorageToFiles();
    }

    state.lastSyncAt = new Date().toISOString();
    await storageSet({ [STORAGE_KEYS.lastSyncAt]: state.lastSyncAt });
    await refreshSummary();

    const remaining = extractResult?.remaining ?? 0;
    toast(
      remaining > 0
        ? `本轮整理完成，还有 ${remaining} 条对话待继续处理`
        : "整理完成，记忆已更新"
    );
  } catch (err) {
    toast(`整理失败：${err.message}`, true);
  } finally {
    organizeBtn.disabled = false;
    organizeBtn.style.opacity = "";
  }
}

async function syncStorageToFiles() {
  if (!state.dirHandle) return;

  const allData = await storageGet(null);

  const profile = allData["mw:profile"];
  if (profile) await writeJson(state.dirHandle, "profile.json", profile);

  const preferences = allData["mw:preferences"];
  if (preferences) await writeJson(state.dirHandle, "preferences.json", preferences);

  const workflows = allData["mw:workflows"];
  if (workflows?.length) await writeJson(state.dirHandle, "workflows.json", workflows);

  const projectEntries = Object.entries(allData).filter(([key]) => key.startsWith("mw:projects:"));
  if (projectEntries.length > 0) {
    const projectDir = await getSubDir("projects");
    for (const [key, value] of projectEntries) {
      const name = decodeURIComponent(key.slice("mw:projects:".length));
      const safeName = name.toLowerCase().replace(/[\s/]/g, "_").slice(0, 64);
      await writeJson(projectDir, `${safeName}.json`, value);
    }
  }

  const episodeEntries = Object.entries(allData).filter(([key]) => key.startsWith("mw:episodes:"));
  if (episodeEntries.length > 0) {
    const epDir = await getSubDir("episodes");
    for (const [, episode] of episodeEntries) {
      const epId = episode.episode_id ?? crypto.randomUUID().slice(0, 8);
      await writeJson(epDir, `${epId}.json`, episode);
    }
  }

  const persistent = allData["mw:persistent_nodes"];
  if (persistent) await writeJson(state.dirHandle, "js_persistent_nodes.json", persistent);

  const rawEntries = Object.entries(allData).filter(([key]) => key.startsWith("chat:"));
  if (rawEntries.length > 0) {
    const rawRoot = await getSubDir("raw");
    for (const [key, chatData] of rawEntries) {
      const parts = key.split(":");
      const platform = parts[1];
      const chatId = parts.slice(2).join(":").replace(/[^a-zA-Z0-9\-_]/g, "_");
      if (!platform || !chatId) continue;
      const platformDir = await rawRoot.getDirectoryHandle(platform, { create: true });
      await writeJson(platformDir, `${chatId}.json`, chatData);
    }
  }
}

function getSelectedCategories() {
  return Array.from(document.querySelectorAll("[data-category]"))
    .filter(checkbox => checkbox.checked)
    .map(checkbox => checkbox.dataset.category);
}

async function buildMemoryPackage() {
  const selected = getSelectedCategories();
  if (selected.length === 0) throw new Error("请至少勾选一项记忆内容");

  const allData = await storageGet(null);
  const packageData = {
    generated_at: new Date().toISOString(),
    selected_categories: selected,
    data: {},
  };

  if (selected.includes("profile") && allData["mw:profile"]) {
    packageData.data.profile = allData["mw:profile"];
  }
  if (selected.includes("preferences") && allData["mw:preferences"]) {
    packageData.data.preferences = allData["mw:preferences"];
  }
  if (selected.includes("projects")) {
    packageData.data.projects = Object.entries(allData)
      .filter(([key]) => key.startsWith("mw:projects:"))
      .map(([, value]) => value);
  }
  if (selected.includes("workflows")) {
    packageData.data.workflows = allData["mw:workflows"] ?? [];
  }
  if (selected.includes("persistent")) {
    const pnData = await readPersistentNodes();
    packageData.data.persistent = Object.entries(pnData.nodes ?? {}).map(([id, node]) => ({ id, ...node }));

    const episodeIds = new Set(packageData.data.persistent.flatMap(node => node.episode_refs ?? []));
    packageData.data.episodic_evidence = [];
    for (const epId of episodeIds) {
      const episode = await loadEpisodeById(epId);
      if (episode) packageData.data.episodic_evidence.push(episode);
    }
  }

  return packageData;
}

function buildMemoryPrompt(pkg) {
  return `${CONFIG.load}\n\n---\n\n${JSON.stringify({ memory_package: pkg }, null, 2)}`;
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function exportPackage() {
  try {
    const pkg = await buildMemoryPackage();
    const text = buildMemoryPrompt(pkg);
    const date = new Date().toISOString().slice(0, 10);
    downloadText(`memory_package_${date}.txt`, text);
    toast("记忆包已导出");
  } catch (err) {
    toast(err.message, true);
  }
}

async function getActiveSupportedTab() {
  const [tab] = await tabsQuery({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("未找到当前标签页");
  return tab;
}

async function injectTextIntoTab(text) {
  const tab = await getActiveSupportedTab();
  const result = await tabsSendMessage(tab.id, { type: "INJECT_INPUT", text });
  if (!result?.ok) throw new Error(result?.error ?? "当前页面不支持注入");
}

async function injectPackage() {
  try {
    const pkg = await buildMemoryPackage();
    await injectTextIntoTab(buildMemoryPrompt(pkg));
    toast("记忆内容已注入当前会话输入框");
  } catch (err) {
    toast(`注入失败：${err.message}`, true);
  }
}

async function saveSkills() {
  const allSkillIds = new Set([...state.selectedSkillIds, ...state.selectedRecommendedIds]);
  await storageSet({ [STORAGE_KEYS.savedSkills]: [...allSkillIds] });
  toast("Skill 选择已保存");
}

function buildSkillPrompt(selectedSkills) {
  const payload = {
    generated_at: new Date().toISOString(),
    skills: selectedSkills.map(skill => ({
      title: skill.title,
      description: skill.description,
    })),
  };
  return `请在本次会话中加载以下技能，并将其作为后续回答风格与工作流参考。\n\n${JSON.stringify(payload, null, 2)}`;
}

async function injectSkills() {
  try {
    const allData = await storageGet(null);
    const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
    const mySkills = deriveMySkills(allData, pnData);
    const selected = [];

    mySkills.forEach(skill => {
      if (state.selectedSkillIds.has(skill.id)) selected.push(skill);
    });
    recommendedSkills.forEach(skill => {
      if (state.selectedRecommendedIds.has(skill.id)) selected.push(skill);
    });

    if (selected.length === 0) throw new Error("请至少选择一个 Skill");
    await injectTextIntoTab(buildSkillPrompt(selected));
    toast("Skill 已注入当前会话输入框");
  } catch (err) {
    toast(`注入失败：${err.message}`, true);
  }
}

async function clearCache() {
  await new Promise(resolve => chrome.storage.local.remove(["_raw_progress", "_sw_keepalive", "pending_flush"], resolve));
  toast("临时缓存已清理");
}

function bindEvents() {
  document.getElementById("menuBtn").addEventListener("click", () => setView("settings"));
  document.getElementById("gotoMigrateBtn").addEventListener("click", () => setView("migrate"));
  document.getElementById("gotoSettingsBtn").addEventListener("click", () => setView("settings"));
  document.getElementById("gotoSkillBtn").addEventListener("click", async () => {
    setView("skill");
    const allData = await storageGet(null);
    const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
    renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds);
  });

  document.querySelectorAll("[data-back]").forEach(btn => {
    btn.addEventListener("click", () => setView(btn.dataset.back));
  });

  document.getElementById("syncBtn").addEventListener("click", toggleSync);
  document.getElementById("selectDirBtn").addEventListener("click", async () => {
    try {
      await pickDirectory();
    } catch (err) {
      if (err.name !== "AbortError") toast(`选择目录失败：${err.message}`, true);
    }
  });

  document.getElementById("saveSettingsBtn").addEventListener("click", saveSettings);
  document.getElementById("testConnectionBtn").addEventListener("click", testConnection);

  document.getElementById("keepUpdatedToggle").addEventListener("change", async event => {
    state.keepUpdated = event.target.checked;
    await storageSet({ [STORAGE_KEYS.keepUpdated]: state.keepUpdated });
    await broadcastCaptureToggle(state.keepUpdated);
    renderSync();
  });

  document.getElementById("realtimeUpdateToggle").addEventListener("change", async event => {
    state.realtimeUpdate = event.target.checked;
    await storageSet({ [STORAGE_KEYS.realtimeUpdate]: state.realtimeUpdate });
    toast(state.realtimeUpdate ? "实时更新已开启" : "实时更新已关闭");
  });

  document.getElementById("organizeBtn").addEventListener("click", runOrganize);
  document.getElementById("exportPackageBtn").addEventListener("click", exportPackage);
  document.getElementById("injectPackageBtn").addEventListener("click", injectPackage);

  document.getElementById("mySkillTab").addEventListener("click", async () => {
    state.currentSkillTab = "my";
    document.getElementById("mySkillTab").classList.add("is-active");
    document.getElementById("recommendedSkillTab").classList.remove("is-active");
    const allData = await storageGet(null);
    const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
    renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds);
  });

  document.getElementById("recommendedSkillTab").addEventListener("click", () => {
    state.currentSkillTab = "recommended";
    document.getElementById("recommendedSkillTab").classList.add("is-active");
    document.getElementById("mySkillTab").classList.remove("is-active");
    renderSkillList(recommendedSkills, state.selectedRecommendedIds);
  });

  document.getElementById("saveSkillBtn").addEventListener("click", saveSkills);
  document.getElementById("injectSkillBtn").addEventListener("click", injectSkills);

  document.getElementById("importHistoryBtn").addEventListener("click", () => {
    toast("历史导入会在接入本地 Python 后端后恢复到完整可用版");
  });

  document.getElementById("clearCacheBtn").addEventListener("click", clearCache);
}

async function init() {
  await CONFIG.loadPrompts();

  const settings = await storageGet([
    STORAGE_KEYS.apiKey,
    STORAGE_KEYS.backendUrl,
    STORAGE_KEYS.keepUpdated,
    STORAGE_KEYS.realtimeUpdate,
    STORAGE_KEYS.lastSyncAt,
    STORAGE_KEYS.savedSkills,
  ]);

  state.apiKey = settings[STORAGE_KEYS.apiKey] || "";
  state.backendUrl = settings[STORAGE_KEYS.backendUrl] || state.backendUrl;
  state.keepUpdated = !!settings[STORAGE_KEYS.keepUpdated];
  state.realtimeUpdate = !!settings[STORAGE_KEYS.realtimeUpdate];
  state.lastSyncAt = settings[STORAGE_KEYS.lastSyncAt] || null;
  state.dirHandle = await loadSavedDir();
  const savedSkillIds = settings[STORAGE_KEYS.savedSkills] || [];
  state.selectedSkillIds = new Set(savedSkillIds.filter(id => !String(id).startsWith("rec:")));
  state.selectedRecommendedIds = new Set(savedSkillIds.filter(id => String(id).startsWith("rec:")));

  bindEvents();
  renderDirectory();
  renderSettings();
  renderSync();
  await refreshSummary();

  const allData = await storageGet(null);
  const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
  renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds);
}

init().catch(err => {
  console.error("[popup] init failed:", err);
  toast(`初始化失败：${err.message}`, true);
});
