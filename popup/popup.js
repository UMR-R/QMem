const DB_NAME = "MemAssistDB";
const DB_STORE = "settings";
const DIR_KEY = "dirHandle";

const STORAGE_KEYS = {
  apiProvider: "api_provider",
  apiKey: "deepseek_api_key",
  apiBaseUrl: "api_base_url",
  apiModel: "api_model",
  backendUrl: "backend_url",
  storagePath: "storage_path",
  keepUpdated: "keepUpdated",
  keepUpdatedStrategy: "keepUpdatedStrategy",
  realtimeUpdate: "realtimeUpdate",
  detailedInjection: "detailedInjection",
  lastSyncAt: "last_sync_at",
  lastRawAppendAt: "last_raw_append_at",
  lastSyncBackendError: "last_sync_backend_error",
  savedSkills: "saved_skill_ids",
  organizeJobState: "organize_job_state",
  memorySelection: "memory_selection_ids",
  lang: "ui_lang",
};

const SUPPORTED_HOSTS = new Set([
  "chatgpt.com",
  "chat.openai.com",
  "gemini.google.com",
  "chat.deepseek.com",
  "www.doubao.com",
]);

const UI_LOCALE = (
  chrome.i18n?.getUILanguage?.()
  || navigator.languages?.[0]
  || navigator.language
  || "zh-CN"
).toLowerCase();
const IS_ZH_UI = UI_LOCALE.startsWith("zh");
const CATEGORY_LABELS = IS_ZH_UI
  ? {
      profile: "用户画像",
      preferences: "偏好设置",
      projects: "项目记忆",
      workflows: "工作流 / SOP",
      daily_notes: "日常记忆",
    }
  : {
      profile: "Profile",
      preferences: "Preferences",
      projects: "Projects",
      workflows: "Workflows / SOP",
      daily_notes: "Daily Notes",
    };

const STRINGS = {
  zh: {
    appTitle: "迁忆",
    brandSubtitle: "让你的对话记忆，随你而行",
    syncBtnLabel: "同步对话",
    migrate: "迁移",
    settings: "设置",
    lastSync: "最近同步",
    conversationCount: "已记录对话",
    memoryCount: "记忆条目",
    contactUs: "联系我们",
    organizeMemoryTitle: "整理记忆",
    organizeRequirementHint: "请先在设置页配置 API Key",
    addCurrentConversation: "加入当前对话",
    addPlatformMemory: "加入平台记忆",
    selectMemoryTitle: "勾选记忆内容",
    export: "导出",
    inject: "注入",
    mySkill: "我的 Skill",
    recommended: "为你推荐",
    delete: "删除",
    addToMySkill: "加入我的 Skill",
    injectSession: "注入当前会话",
    settingsTitle: "设置",
    apiConfig: "API 配置",
    backendUrlLabel: "本地后端地址",
    save: "保存",
    backendUrlHint: "可选地址：http://127.0.0.1:8765",
    apiKeyLabel: "API Key",
    testConnection: "测试连接",
    localDirTitle: "本地目录",
    localDirHint: "留空时使用默认目录 backend_service/wiki；如需自定义，请填写当前操作系统可用的绝对路径。",
    syncStrategyTitle: "同步策略",
    syncMemoryLabel: "同步记忆",
    syncMemoryHint: "新对话到来后自动提取记忆",
    injectStrategyTitle: "注入策略",
    detailedInjectionLabel: "详细注入",
    detailedInjectionHint: "对细节保留更高",
    dataManagementTitle: "数据管理",
    importConversation: "导入对话",
    importConversationHint: "支持 txt/md/json 的原始对话",
    clearAllMemory: "清理所有记忆",
    clearAllMemoryHint: "删除已保存的对话和记忆文件，但保留当前设置",
    clearCache: "清理缓存",
    clearCacheHint: "清理本地临时缓存，保留主记忆文件",
    modalTitle: "启动本地后端",
    modalCopy: "请打开Terminal，在项目目录执行以下命令启动本地后端：",
    backendUrlPlaceholder: "请输入本地后端地址",
    apiKeyPlaceholder: "请输入 API Key",
    apiKeyChangePlaceholder: "如需更换，请重新输入新的 API Key",
    localDirPlaceholder: "留空使用默认目录",
    ariaMore: "更多",
    ariaBack: "返回",
    ariaCloseModal: "关闭弹窗",
    ariaCopyCommand: "复制启动命令",
    syncPaused: "同步对话已暂停",
    syncActive: "同步对话中",
    syncHintDefault: "点击开启后，持续记录你与大模型的对话到本地",
    syncHintWithMemory: "正在记录对话，并自动提取记忆",
    syncHintNoMemory: "正在记录原始对话，可稍后在迁移页整理记忆",
    syncHintNoKey: "正在记录原始对话，配置 API 后才会自动提取记忆",
    countSuffix: " 条",
    apiStatusUnconfigured: "API 调用：待配置",
    apiStatusUnverified: "API 调用：待验证",
    dirPlaceholder: "留空使用默认目录",
    skillEmptyTitle: "还没有提取出 Skill",
    skillEmptyDesc: "我的 Skill 会从已整理的记忆中自动提取。先开启同步或整理记忆，系统会逐步生成可复用的 Skill。",
    toastDirSet: "目录已设置：",
    toastBackendOnline: "本地后端已在线",
    toastBackendOffline: "无法连接到本地后端",
    toastBackendDisconnected: "本地后端已断开，同步对话已暂停",
    toastMemoryDeleted: "已删除这条记忆",
    toastSkillRemovedSingle: "Skill 已从列表中移除",
    toastSkillSelectFirst: "请先勾选要删除的 Skill",
    toastSkillDeleted: "已删除选中的 Skill",
    toastSettingsSaved: "设置已保存到本地后端",
    toastApiOk: "API 调用可用，设置已保存",
    toastSyncWithMemory: "同步对话已开启，将自动增量更新记忆",
    toastSyncNoMemory: "记录已开启，可稍后在迁移页整理记忆",
    toastSyncRawOnly: "记录已开启，当前仅保存原始对话",
    toastSyncStopped: "同步对话已暂停",
    toastNeedApiKey: "请先在设置页配置 API Key",
    toastOrganizeRunning: "整理任务已在后台进行中",
    toastOrganizeStarted: "已开始整理记忆，后台会继续运行",
    toastOrganizeDone: "整理完成，记忆已更新",
    toastMemoryUpToDate: "记忆已是最新版本",
    toastExported: "记忆包已导出",
    toastInjectFallback: "当前页面未就绪，记忆内容已复制到剪贴板。刷新当前对话页后可直接粘贴。",
    toastInjected: "记忆内容已注入当前会话输入框",
    toastAddingConversation: "正在加入当前对话...",
    toastConversationAdded: "当前对话加入完成，可稍后点击整理记忆",
    toastCollectingPlatform: "正在采集平台记忆...",
    toastPlatformAdded: "平台记忆加入完成，可稍后点击整理记忆",
    toastSkillSelectRecommended: "请至少选择一个推荐 Skill",
    toastSkillExported: "Skill 已导出",
    toastSkillInjectFallback: "当前页面未就绪，Skill 已复制到剪贴板。刷新当前对话页后可直接粘贴。",
    toastSkillInjected: "Skill 已注入当前会话输入框",
    toastCacheCleared: "临时缓存已清理",
    toastMemoryCleared: "所有记忆文件已清理",
    toastDirSaved: "本地目录已保存",
    toastCopyCommandOk: "启动命令已复制",
    toastCopyCommandFailed: "复制失败，请手动复制",
    toastSyncMemoryOnWithApi: "同步记忆已开启。重新同步或刷新当前会话页后，将自动提取记忆。",
    toastSyncMemoryOnNoApi: "同步记忆已开启，配置 API 后才会开始提取记忆。",
    toastSyncMemoryOff: "同步记忆已关闭。新对话可稍后手动整理。",
    toastDetailedOn: "详细注入已开启",
    toastDetailedOff: "详细注入已关闭",
    toastSkillSelectOne: "请至少选择一个 Skill",
    toastPrefixDeleteFailed: "删除失败：",
    toastPrefixSelectionFailed: "更新勾选失败：",
    toastPrefixExpandFailed: "展开失败：",
    toastPrefixBackendOnlineBut: "本地后端在线，但 ",
    toastPrefixConnectionFailed: "连接失败：",
    toastPrefixOrganizeFailed: "整理失败：",
    toastPrefixOrganizeDoneWith: "整理完成：",
    toastPrefixInjectFailed: "注入失败：",
    toastPrefixConversationFailed: "加入当前对话失败：",
    toastPrefixPlatformFailed: "加入平台记忆失败：",
    toastPrefixAddFailed: "加入失败：",
    toastPrefixExportFailed: "导出失败：",
    toastPrefixLoadRecommendedFailed: "加载推荐 Skill 失败：",
    toastPrefixImportFailed: "导入失败：",
    toastPrefixClearFailed: "清理失败：",
    toastPrefixSaveFailed: "保存失败：",
    toastPrefixInitFailed: "初始化失败：",
    toastImportComplete: "原始对话导入完成：",
    toastImportJobCreated: "原始对话导入任务已创建：",
    toastSavedSkillCount: "已加入我的 Skill：",
    toastSavedSkillSuffix: " 项",
    organizeProcessing: "正在整理记忆...",
    organizeReady: "准备开始...",
    organizeProcessingHint: "处理中...",
    confirmDeleteMemory: "删除这条记忆吗？\n\n",
    confirmClearAll: "这会删除已保存的对话和记忆文件，但保留当前设置。确定继续吗？",
    errDeleteMemory: "无法删除这条记忆",
    errSaveDir: "无法保存本地目录",
    errConnectBackend: "无法连接本地后端",
    errClearMemory: "无法清理所有记忆文件",
    errCheckBackend: "请检查本地后端",
    skillLabelDesc: "描述：",
    skillLabelOutput: "产出：",
    skillLabelGoal: "目标：",
    skillLabelSteps: "步骤：",
    skillUnnamed: "未命名 Skill",
    workflowFallbackTitle: "工作流",
    workflowFallbackDesc: "从你的记忆里提炼出的工作流程。",
    persistentFallbackDesc: "由长期对话稳定提炼出的习惯与能力。",
    selectionNoItems: "暂无细项",
    selectionNoItemsDesc: "当前类别还没有整理出可单独选择的内容。",
    apiStatusOk: "API 调用：可用",
    syncBackendRequired: "请先在设置页配置并启动本地后端",
    showMoreSkills: "查看更多",
    showLessSkills: "收起",
  },
  en: {
    appTitle: "QMem",
    brandSubtitle: "Take your AI memory wherever you go",
    syncBtnLabel: "Sync",
    migrate: "Migrate",
    settings: "Settings",
    lastSync: "Last Sync",
    conversationCount: "Conversations",
    memoryCount: "Memory Items",
    contactUs: "Contact Us",
    organizeMemoryTitle: "Organize Memory",
    organizeRequirementHint: "Please configure an API Key in Settings first",
    addCurrentConversation: "Add Current Chat",
    addPlatformMemory: "Add Platform Memory",
    selectMemoryTitle: "Select Memory Items",
    export: "Export",
    inject: "Inject",
    mySkill: "My Skills",
    recommended: "Recommended",
    delete: "Delete",
    addToMySkill: "Save to My Skills",
    injectSession: "Inject to Session",
    settingsTitle: "Settings",
    apiConfig: "API Configuration",
    backendUrlLabel: "Local Backend URL",
    save: "Save",
    backendUrlHint: "Default: http://127.0.0.1:8765",
    apiKeyLabel: "API Key",
    testConnection: "Test",
    localDirTitle: "Local Directory",
    localDirHint: "Leave blank to use the default directory (backend_service/wiki); or enter an absolute path for your OS.",
    syncStrategyTitle: "Sync Strategy",
    syncMemoryLabel: "Sync Memory",
    syncMemoryHint: "Auto-extract memory after new conversations",
    injectStrategyTitle: "Inject Strategy",
    detailedInjectionLabel: "Detailed Injection",
    detailedInjectionHint: "Preserve more detail in injections",
    dataManagementTitle: "Data Management",
    importConversation: "Import Conversations",
    importConversationHint: "Supports raw conversations in txt/md/json",
    clearAllMemory: "Clear All Memory",
    clearAllMemoryHint: "Delete all saved conversations and memory files, keeping current settings",
    clearCache: "Clear Cache",
    clearCacheHint: "Clear local temporary cache, keeping main memory files",
    modalTitle: "Start Local Backend",
    modalCopy: "Open a Terminal and run the following command in your project directory to start the local backend:",
    backendUrlPlaceholder: "Enter local backend URL",
    apiKeyPlaceholder: "Enter your API Key",
    apiKeyChangePlaceholder: "Enter a new API Key to replace the current one",
    localDirPlaceholder: "Leave blank for default directory",
    ariaMore: "More",
    ariaBack: "Back",
    ariaCloseModal: "Close dialog",
    ariaCopyCommand: "Copy startup command",
    syncPaused: "Sync paused",
    syncActive: "Syncing",
    syncHintDefault: "Click to start recording your AI conversations locally",
    syncHintWithMemory: "Recording conversations and auto-extracting memory",
    syncHintNoMemory: "Recording raw conversations, organize memory later in Migrate",
    syncHintNoKey: "Recording raw conversations, auto-extraction not started",
    countSuffix: "",
    apiStatusUnconfigured: "API: Not configured",
    apiStatusUnverified: "API: Not verified",
    dirPlaceholder: "Leave blank for default directory",
    skillEmptyTitle: "No Skills yet",
    skillEmptyDesc: "Skills are auto-extracted from your organized memory. Start syncing or run Organize Memory, and Skills will appear over time.",
    toastDirSet: "Directory set: ",
    toastBackendOnline: "Local backend is online",
    toastBackendOffline: "Cannot connect to local backend",
    toastBackendDisconnected: "Local backend disconnected, sync paused",
    toastMemoryDeleted: "Memory item deleted",
    toastSkillRemovedSingle: "Skill removed from list",
    toastSkillSelectFirst: "Select a Skill to delete first",
    toastSkillDeleted: "Selected Skills deleted",
    toastSettingsSaved: "Settings saved",
    toastApiOk: "API connection OK, settings saved",
    toastSyncWithMemory: "Sync started, memory will be auto-updated",
    toastSyncNoMemory: "Recording started, organize memory later in Migrate",
    toastSyncRawOnly: "Recording started, saving raw conversations only",
    toastSyncStopped: "Sync paused",
    toastNeedApiKey: "Please configure an API Key in Settings first",
    toastOrganizeRunning: "Organize task is already running",
    toastOrganizeStarted: "Organization started, running in background",
    toastOrganizeDone: "Organization complete, memory updated",
    toastMemoryUpToDate: "Memory is already up to date",
    toastExported: "Memory package exported",
    toastInjectFallback: "Page not ready — memory copied to clipboard. Refresh the page to paste.",
    toastInjected: "Memory injected into current session",
    toastAddingConversation: "Adding current conversation…",
    toastConversationAdded: "Conversation added, organize memory later",
    toastCollectingPlatform: "Collecting platform memory…",
    toastPlatformAdded: "Platform memory added, organize memory later",
    toastSkillSelectRecommended: "Select at least one recommended Skill",
    toastSkillExported: "Skill exported",
    toastSkillInjectFallback: "Page not ready — Skill copied to clipboard. Refresh the page to paste.",
    toastSkillInjected: "Skill injected into current session",
    toastCacheCleared: "Temporary cache cleared",
    toastMemoryCleared: "All memory files cleared",
    toastDirSaved: "Local directory saved",
    toastCopyCommandOk: "Startup command copied",
    toastCopyCommandFailed: "Copy failed, please copy manually",
    toastSyncMemoryOnWithApi: "Memory sync enabled. Auto-extraction starts after next sync or page refresh.",
    toastSyncMemoryOnNoApi: "Memory sync enabled. Configure an API Key to start extracting memory.",
    toastSyncMemoryOff: "Memory sync disabled. New conversations can be organized manually.",
    toastDetailedOn: "Detailed injection enabled",
    toastDetailedOff: "Detailed injection disabled",
    toastSkillSelectOne: "Select at least one Skill",
    toastPrefixDeleteFailed: "Delete failed: ",
    toastPrefixSelectionFailed: "Selection update failed: ",
    toastPrefixExpandFailed: "Expand failed: ",
    toastPrefixBackendOnlineBut: "Backend is online, but ",
    toastPrefixConnectionFailed: "Connection failed: ",
    toastPrefixOrganizeFailed: "Organization failed: ",
    toastPrefixOrganizeDoneWith: "Organization complete: ",
    toastPrefixInjectFailed: "Injection failed: ",
    toastPrefixConversationFailed: "Failed to add conversation: ",
    toastPrefixPlatformFailed: "Failed to add platform memory: ",
    toastPrefixAddFailed: "Add failed: ",
    toastPrefixExportFailed: "Export failed: ",
    toastPrefixLoadRecommendedFailed: "Failed to load recommended Skills: ",
    toastPrefixImportFailed: "Import failed: ",
    toastPrefixClearFailed: "Clear failed: ",
    toastPrefixSaveFailed: "Save failed: ",
    toastPrefixInitFailed: "Initialization failed: ",
    toastImportComplete: "Import complete: ",
    toastImportJobCreated: "Import task created: ",
    toastSavedSkillCount: "Added to My Skills: ",
    toastSavedSkillSuffix: "",
    organizeProcessing: "Organizing memory…",
    organizeReady: "Getting ready…",
    organizeProcessingHint: "Processing…",
    confirmDeleteMemory: "Delete this memory item?\n\n",
    confirmClearAll: "This will delete all saved conversations and memory files, but keep current settings. Are you sure?",
    errDeleteMemory: "Cannot delete this memory item",
    errSaveDir: "Cannot save local directory",
    errConnectBackend: "Cannot connect to local backend",
    errClearMemory: "Cannot clear memory files",
    errCheckBackend: "Check local backend",
    skillLabelDesc: "",
    skillLabelOutput: "",
    skillLabelGoal: "",
    skillLabelSteps: "",
    skillUnnamed: "Unnamed Skill",
    workflowFallbackTitle: "Workflow",
    workflowFallbackDesc: "A reusable workflow extracted from your memory.",
    persistentFallbackDesc: "A stable habit or capability extracted from your conversations.",
    selectionNoItems: "No items yet",
    selectionNoItemsDesc: "No individual items have been extracted for this category yet.",
    apiStatusOk: "API: OK",
    syncBackendRequired: "Please configure and start the local backend in Settings first",
    showMoreSkills: "Show more",
    showLessSkills: "Show less",
  },
};

function t(key) {
  return STRINGS[state.lang]?.[key] ?? STRINGS.zh[key] ?? key;
}

const state = {
  dirHandle: null,
  apiKey: "",
  apiKeyConfigured: false,
  apiProvider: "openai_compat",
  apiBaseUrl: "https://api.deepseek.com/v1",
  apiModel: "deepseek-chat",
  backendUrl: "",
  keepUpdated: true,
  syncEnabled: false,
  realtimeUpdate: false,
  detailedInjection: false,
  lastSyncAt: null,
  apiConnectionStatus: "",
  organizeApiHintVisible: false,
  pendingBackendCheckOnModalClose: false,
  organizeJobState: null,
  organizePollTimer: null,
  currentView: "home",
  currentSkillTab: "my",
  selectedSkillIds: new Set(),
  selectedRecommendedIds: new Set(),
  selectedMemoryIds: new Set(),
  hasStoredMemorySelection: false,
  expandedCategories: new Set(),
  memoryItemsByCategory: {},
  recommendedSkillItems: [],
  recommendedExpanded: false,
  storagePath: "",
  categories: {
    profile: 0,
    preferences: 0,
    projects: 0,
    workflows: 0,
    daily_notes: 0,
  },
  categoryLabels: { ...CATEGORY_LABELS },
  selectionListScrollTop: 0,
  selectionChipScrollLefts: {},
  lang: "zh",
  lastSummary: null,
};

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8765";
const BACKEND_ERROR_EN = {
  "请先在设置页配置 API Key": "Please configure an API Key in Settings first",
  "请至少选择一项记忆内容": "Please select at least one memory item",
  "当前对话为空，无法加入记忆": "Current conversation is empty, cannot add to memory",
  "请至少选择一个 Skill": "Please select at least one Skill",
  "当前默认配置不匹配这把 key": "The current configuration does not match this API key",
  "加入当前对话失败": "Failed to add conversation",
  "导入失败": "Import failed",
  "整理失败": "Organization failed",
};
function translateBackendError(msg) {
  if (!msg || state.lang !== "en") return msg;
  const s = String(msg);
  if (BACKEND_ERROR_EN[s]) return BACKEND_ERROR_EN[s];
  if (s.startsWith("暂不支持 ")) return `Unsupported: ${s.slice(5)}`;
  return s;
}

const BACKEND_MSG_EN = {
  "正在并行整理画像、偏好和项目...": "Processing profile, preferences, and projects…",
  "正在整理偏好设置...": "Organizing preferences…",
  "正在整理项目记忆...": "Organizing project memory…",
  "正在整理工作流...": "Organizing workflows…",
  "正在重建索引...": "Rebuilding index…",
  "正在维护结构化记忆节点...": "Updating persistent memory nodes…",
  "正在归并平台记忆...": "Merging platform memory…",
  "未找到可整理的历史对话": "No conversations found to organize",
  "正在提取对话记忆...": "Extracting conversation memory…",
  "正在并行提取对话记忆...": "Extracting conversation memory in parallel…",
  "结构化记忆已是最新版本...": "Structured memory is already up to date…",
  "记忆已是最新版本": "Memory is already up to date",
  "结构化记忆节点已是最新版本...": "Persistent memory nodes are already up to date…",
  "整理完成": "Organization complete",
  "当前对话已加入记忆": "Current conversation added to memory",
  "正在整理当前对话...": "Organizing current conversation…",
  "当前对话已加入记忆，后台正在整理...": "Conversation added, organizing in background…",
  "准备开始整理": "Preparing to organize…",
  "整理失败": "Organization failed",
  "导入历史失败": "Import failed",
  "请先输入 API Key": "Please enter an API Key",
  "请至少勾选一项记忆内容": "Please select at least one memory item",
  "未找到当前标签页": "No active tab found",
  "请先切换到 ChatGPT、Gemini、DeepSeek 或豆包页面": "Please switch to a ChatGPT, Gemini, DeepSeek, or Doubao page first",
  "当前页面不支持注入": "This page does not support injection",
  "当前页面不支持抓取整段对话": "This page does not support conversation capture",
  "当前页面没有可加入的对话内容": "No conversation content found on this page",
  "当前页面不支持抓取平台记忆": "This page does not support platform memory capture",
  "当前页面没有可保存的平台记忆信息": "No platform memory found on this page",
  "平台没有返回可解析的内容": "Platform returned no parseable content",
  "未找到 JSON 结构": "No JSON structure found in response",
  "JSON 结构不完整": "JSON structure is incomplete",
  "当前页面未就绪，无法自动提交采集指令": "Page not ready, cannot auto-submit collection command",
  "平台记忆采集发送失败": "Failed to send memory collection command",
  "平台记忆采集失败": "Platform memory collection failed",
  "等待平台记忆采集结果超时": "Platform memory collection timed out",
  "平台返回的记忆内容不是对象": "Platform returned memory in unexpected format",
};
function translateBackendMsg(text) {
  if (state.lang !== "en") return text;
  return BACKEND_MSG_EN[text] ?? text;
}

const SYNC_HEALTH_CHECK_INTERVAL_MS = 5000;
let summaryRefreshTimer = null;
let syncBackendHealthTimer = null;

function logPopupError(scope, error, extra = {}) {
  const normalized = normalizeError(error, scope);
  console.error(`[popup] ${scope}`, {
    error: normalized,
    message: normalized.message,
    stack: normalized.stack || null,
    rawError: error,
    ...extra,
  });
}

function normalizeError(error, fallback = "操作失败") {
  if (error instanceof Error) return error;
  if (typeof error === "string" && error.trim()) return new Error(error.trim());
  if (Array.isArray(error)) {
    const parts = error
      .map(item => normalizeError(item, "").message)
      .filter(Boolean);
    return new Error(parts.length ? parts.join("；") : fallback);
  }
  if (error && typeof error === "object") {
    if (typeof error.message === "string" && error.message.trim()) {
      return new Error(error.message.trim());
    }
    if (typeof error.detail === "string" && error.detail.trim()) {
      return new Error(error.detail.trim());
    }
    if (error.detail !== undefined) {
      return normalizeError(error.detail, fallback);
    }
    if (Array.isArray(error.loc) && typeof error.msg === "string") {
      const location = error.loc.map(part => String(part)).filter(Boolean).join(".");
      return new Error(location ? `${location}: ${error.msg}` : error.msg);
    }
    try {
      return new Error(JSON.stringify(error));
    } catch {
      return new Error(fallback);
    }
  }
  return new Error(fallback);
}

function errorMessage(error, fallback = "操作失败") {
  return normalizeError(error, fallback).message;
}

function isExpectedSettingsFailure(error) {
  const message = errorMessage(error, "").trim();
  if (!message) return false;
  return (
    message.includes("无法连接到本地后端") ||
    message.includes("Failed to fetch") ||
    message.includes("HTTP 4") ||
    message.includes("HTTP 5") ||
    message.includes("body.") ||
    message.includes("api_key") ||
    message.includes("backend_url")
  );
}

window.addEventListener("error", event => {
  logPopupError("Unhandled error", event.error || event.message, {
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
  });
});

window.addEventListener("unhandledrejection", event => {
  logPopupError("Unhandled promise rejection", event.reason);
});

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

function backendApi() {
  if (!window.BackendAPI) {
    throw new Error("BackendAPI 未加载");
  }
  return window.BackendAPI;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeStoredMemoryIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map(item => String(item || "").trim()).filter(Boolean))];
}

function persistMemorySelection() {
  state.hasStoredMemorySelection = true;
  return storageSet({ [STORAGE_KEYS.memorySelection]: [...state.selectedMemoryIds] });
}

function setMemoryItemSelected(itemId, checked) {
  const id = String(itemId || "").trim();
  if (!id) return;
  if (checked) state.selectedMemoryIds.add(id);
  else state.selectedMemoryIds.delete(id);
  persistMemorySelection().catch(err => {
    logPopupError("persistMemorySelection", err);
  });
}

function validMemorySelectionIds() {
  const valid = new Set();
  for (const [category, items] of Object.entries(state.memoryItemsByCategory || {})) {
    if (Array.isArray(items) && items.length) {
      items.forEach(item => {
        if (item?.id) valid.add(String(item.id));
      });
    } else if ((state.categories?.[category] || 0) > 0) {
      valid.add(`${category}:default`);
    }
  }
  return valid;
}

async function pruneUnavailableMemorySelection() {
  const valid = validMemorySelectionIds();
  if (!valid.size || !state.selectedMemoryIds.size) return;
  let changed = false;
  for (const itemId of [...state.selectedMemoryIds]) {
    if (valid.has(itemId)) continue;
    state.selectedMemoryIds.delete(itemId);
    changed = true;
  }
  if (changed) await persistMemorySelection();
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

function isSupportedTab(tab) {
  try {
    const url = new URL(tab?.url || "");
    return SUPPORTED_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

function isMissingReceiverError(error) {
  const message = String(error?.message || "").toLowerCase();
  return (
    message.includes("receiving end does not exist") ||
    message.includes("could not establish connection") ||
    message.includes("message port closed") ||
    message.includes("message channel closed") ||
    message.includes("channel closed before a response") ||
    message.includes("asynchronous response")
  );
}

async function copyTextToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } finally {
      textarea.remove();
    }
    return ok;
  }
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
  const previousDirName = state.dirHandle?.name || "";
  const handle = await window.showDirectoryPicker({ mode: "readwrite" });
  await dbSet(DIR_KEY, handle);
  state.dirHandle = handle;
  const currentInput = document.getElementById("storageDirInput")?.value.trim() || "";
  if (!state.storagePath || currentInput === previousDirName) {
    state.storagePath = handle.name || "";
  }
  renderDirectory();
  toast(`${t("toastDirSet")}${handle.name}`);
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
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (state.lang === "en") {
    if (!isoString) return "Not started";
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "Not started";
    const diff = Date.now() - date.getTime();
    if (diff < minute) return "Just now";
    if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
    if (diff < day) return `${Math.floor(diff / hour)}h ago`;
    return `${Math.floor(diff / day)}d ago`;
  }
  if (!isoString) return "未开始";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "未开始";
  const diff = Date.now() - date.getTime();
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

function buildBackendStartCommand(rawBackendUrl = "") {
  let host = "127.0.0.1";
  let port = "8765";
  const value = String(rawBackendUrl || "").trim();
  if (value) {
    try {
      const normalized = value.includes("://") ? value : `http://${value}`;
      const url = new URL(normalized);
      host = url.hostname || host;
      if (url.port) {
        port = url.port;
      } else if (url.protocol === "https:") {
        port = "443";
      } else if (url.protocol === "http:") {
        port = "80";
      }
    } catch {
      // Keep fallback host/port when user input is not a parseable URL.
    }
  }
  return [
    "pip install -r backend_service/requirements.txt",
    `uvicorn backend_service.app:app --host ${host} --port ${port} --reload`,
  ].join("\n");
}

function showCommandModal(command = buildBackendStartCommand(state.backendUrl), options = {}) {
  const modal = document.getElementById("commandModal");
  const commandEl = document.getElementById("commandModalText");
  commandEl.textContent = command;
  state.pendingBackendCheckOnModalClose = !!options.checkBackendOnClose;
  modal.classList.remove("hidden");
  commandEl.focus();
}

async function closeCommandModal() {
  document.getElementById("commandModal").classList.add("hidden");
  if (!state.pendingBackendCheckOnModalClose) return;
  state.pendingBackendCheckOnModalClose = false;
  try {
    await backendApi().getHealth(state.backendUrl);
    toast(t("toastBackendOnline"));
  } catch (err) {
    toast(t("toastBackendOffline"), true);
    logPopupError("Backend still offline after command modal close", err, {
      backendUrl: state.backendUrl || DEFAULT_BACKEND_URL,
    });
  }
}

function setView(viewName) {
  state.currentView = viewName;
  for (const view of document.querySelectorAll(".view")) {
    view.classList.toggle("is-active", view.id === `${viewName}View`);
  }
  renderSkillActions();
}

function renderSync() {
  const syncBtn = document.getElementById("syncBtn");
  const dot = document.getElementById("syncDot");

  let statusText = t("syncPaused");
  let hintText = t("syncHintDefault");

  if (state.syncEnabled) {
    statusText = t("syncActive");
    if (state.realtimeUpdate && state.keepUpdated) {
      hintText = state.apiKeyConfigured ? t("syncHintWithMemory") : t("syncHintNoKey");
    } else {
      hintText = t("syncHintNoMemory");
    }
  }

  document.getElementById("syncStatusText").textContent = statusText;
  document.getElementById("syncHintText").textContent = hintText;
  syncBtn.classList.toggle("is-active", state.syncEnabled);
  syncBtn.setAttribute("aria-pressed", String(state.syncEnabled));
  syncBtn.setAttribute("aria-disabled", "false");
  syncBtn.title = "";
  dot.classList.toggle("is-active", state.syncEnabled);
  updateSyncBackendHealthPolling();
}

function renderStats(summary) {
  state.lastSummary = summary;
  document.getElementById("lastSyncValue").textContent = formatRelativeTime(summary.lastSyncAt);
  document.getElementById("conversationCountValue").textContent = `${summary.conversationCount}${t("countSuffix")}`;
  document.getElementById("memoryCountValue").textContent = `${summary.memoryItemCount}${t("countSuffix")}`;
}

function renderDirectory() {
  const value = state.storagePath || "";
  document.getElementById("storageDirInput").value = value;
  document.getElementById("storageDirInput").placeholder = value ? "" : t("dirPlaceholder");
}

function renderSettings() {
  const apiKeyInput = document.getElementById("apiKeyInput");
  const apiKeyStatus = document.getElementById("apiKeyStatus");
  apiKeyInput.value = state.apiKey;
  document.getElementById("backendUrlInput").value = state.backendUrl;
  document.getElementById("realtimeUpdateToggle").checked = state.realtimeUpdate;
  document.getElementById("detailedInjectionToggle").checked = state.detailedInjection;
  if (state.apiKeyConfigured && !state.apiKey) {
    apiKeyInput.placeholder = t("apiKeyChangePlaceholder");
  } else {
    apiKeyInput.placeholder = t("apiKeyPlaceholder");
  }
  if (!state.apiKey && !state.apiKeyConfigured) {
    apiKeyStatus.textContent = t("apiStatusUnconfigured");
  } else if (state.apiConnectionStatus === "ok") {
    apiKeyStatus.textContent = t("apiStatusOk");
  } else if (typeof state.apiConnectionStatus === "string" && state.apiConnectionStatus.startsWith("failed:")) {
    const msg = translateBackendError(state.apiConnectionStatus.slice(7));
    apiKeyStatus.textContent = state.lang === "en"
      ? `API unavailable: ${msg}`
      : `API 调用：不可用（${msg}）`;
  } else if (state.apiConnectionStatus) {
    apiKeyStatus.textContent = state.apiConnectionStatus;
  } else {
    apiKeyStatus.textContent = t("apiStatusUnverified");
  }
}

function renderActionAvailability() {
  const organizeBtn = document.getElementById("organizeBtn");
  const organizeBtnWrap = document.getElementById("organizeBtnWrap");
  const organizeHint = document.getElementById("organizeRequirementHint");
  if (!organizeBtn) return;
  organizeBtn.disabled = false;
  organizeBtn.style.opacity = "";
  organizeBtn.title = "";
  if (organizeBtnWrap) {
    organizeBtnWrap.title = "";
  }
  if (organizeHint) {
    organizeHint.classList.toggle("hidden", !!state.apiKeyConfigured || !state.organizeApiHintVisible);
    organizeHint.textContent = t("organizeRequirementHint");
  }
}

function truncateText(text, maxLength = 56, ellipsis = true) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  if (value.length <= maxLength) return value;
  const cutLength = ellipsis ? Math.max(0, maxLength - 1) : maxLength;
  const cut = value.slice(0, cutLength).trim();
  return ellipsis ? `${cut}…` : cut;
}

function localizeMemoryDescription(categoryId, description) {
  const raw = String(description || "").trim();
  if (!raw) return "";
  return raw;
}

function buildSelectionPreview(categoryId, item) {
  const isDailyNote = categoryId === "daily_notes" || categoryId === "persistent";
  const displayTitle = item?.display_title || item?.title || "";
  const displayDescription = item?.display_description ?? item?.description ?? "";
  const title = truncateText(displayTitle, isDailyNote ? 44 : 30, !isDailyNote);
  const rawDescription = localizeMemoryDescription(categoryId, displayDescription);
  const description = isDailyNote ? rawDescription : truncateText(rawDescription, 42);
  return { title, description };
}

function selectionScrollKey(categoryId, groupLabel) {
  return `${categoryId}:${encodeURIComponent(String(groupLabel || ""))}`;
}

function snapshotSelectionScroll(listEl) {
  if (!listEl) return;
  state.selectionListScrollTop = listEl.scrollTop;
  const next = {};
  listEl.querySelectorAll(".selection-chip-row[data-scroll-key]").forEach(row => {
    next[row.dataset.scrollKey] = row.scrollLeft;
  });
  state.selectionChipScrollLefts = next;
}

function restoreSelectionScroll(listEl) {
  if (!listEl) return;
  requestAnimationFrame(() => {
    listEl.scrollTop = state.selectionListScrollTop || 0;
    listEl.querySelectorAll(".selection-chip-row[data-scroll-key]").forEach(row => {
      const key = row.dataset.scrollKey;
      if (key && typeof state.selectionChipScrollLefts[key] === "number") {
        row.scrollLeft = state.selectionChipScrollLefts[key];
      }
    });
  });
}

function normalizeOrganizeStatusText(text) {
  const fallback = t("organizeProcessing");
  const value = String(text || fallback).trim() || fallback;
  const translated = translateBackendMsg(value);
  const stripped = translated
    .replace(/[：:]\s*\d+(?:\s*-\s*\d+)?\s*\/\s*\d+\s*$/, "…")
    .replace(/\s+\d+\s*\/\s*\d+\s*$/, "…");
  return stripped || fallback;
}

function setOrganizeStatus(active, text, hint) {
  if (text === undefined) text = t("organizeProcessing");
  if (hint === undefined) hint = t("organizeReady");
  const card = document.getElementById("organizeStatusCard");
  card.classList.toggle("hidden", !active);
  document.getElementById("organizeStatusText").textContent = normalizeOrganizeStatusText(text);
  document.getElementById("organizeStatusHint").textContent = hint;
}

function organizeProgressHint(jobState) {
  const current = Number(jobState?.current);
  const total = Number(jobState?.total);
  if (Number.isFinite(current) && Number.isFinite(total) && total > 0) {
    return `${Math.max(0, Math.min(current, total))} / ${total}`;
  }
  return t("organizeProcessingHint");
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function ensureCategoryItems(category) {
  if (state.memoryItemsByCategory[category]) return state.memoryItemsByCategory[category];
  try {
    const locale = state.lang === "en" ? "en-US" : "zh-CN";
    const result = await backendApi().getMemoryItems(state.backendUrl, category, locale);
    state.memoryItemsByCategory[category] = result.items || [];
  } catch {
    state.memoryItemsByCategory[category] = [];
  }
  return state.memoryItemsByCategory[category];
}

async function toggleCategoryExpanded(category) {
  if (state.expandedCategories.has(category)) {
    state.expandedCategories.delete(category);
    renderSelectionList();
    return;
  }
  state.expandedCategories.add(category);
  await ensureCategoryItems(category);
  renderSelectionList();
}

async function toggleCategorySelection(category, checked) {
  const items = await ensureCategoryItems(category);
  if (items.length === 0) {
    state.selectedMemoryIds[checked ? "add" : "delete"](`${category}:default`);
  } else {
    items.forEach(item => state.selectedMemoryIds[checked ? "add" : "delete"](item.id));
  }
  await persistMemorySelection();
  renderSelectionList();
}

async function deleteMemoryItem(categoryId, item) {
  const itemId = String(item?.id || "").trim();
  if (!itemId) return;
  const preview = buildSelectionPreview(categoryId, item);
  const label = preview.title || preview.description || itemId;
  const confirmed = confirm(`${t("confirmDeleteMemory")}${label}`);
  if (!confirmed) return;
  try {
    await backendApi().deleteMemoryItems(state.backendUrl, { item_ids: [itemId] });
    state.selectedMemoryIds.delete(itemId);
    await persistMemorySelection();
    state.memoryItemsByCategory = {};
    await refreshSummary();
    toast(t("toastMemoryDeleted"));
  } catch (err) {
    toast(`${t("toastPrefixDeleteFailed")}${translateBackendError(errorMessage(err, t("errDeleteMemory")))}`, true);
  }
}

function renderSelectionList() {
  const listEl = document.getElementById("selectionList");
  if (!listEl) return;
  snapshotSelectionScroll(listEl);

  const categories = [
    { id: "profile", label: state.categoryLabels.profile || CATEGORY_LABELS.profile, count: state.categories.profile },
    { id: "preferences", label: state.categoryLabels.preferences || CATEGORY_LABELS.preferences, count: state.categories.preferences },
    { id: "projects", label: state.categoryLabels.projects || CATEGORY_LABELS.projects, count: state.categories.projects },
    { id: "workflows", label: state.categoryLabels.workflows || CATEGORY_LABELS.workflows, count: state.categories.workflows },
    { id: "daily_notes", label: state.categoryLabels.daily_notes || CATEGORY_LABELS.daily_notes, count: state.categories.daily_notes },
  ];

  listEl.innerHTML = "";
  categories.forEach(category => {
    const items = state.memoryItemsByCategory[category.id] || [];
    const expanded = state.expandedCategories.has(category.id);
    const selectedCount = items.length === 0
      ? (state.selectedMemoryIds.has(`${category.id}:default`) ? 1 : 0)
      : items.filter(item => state.selectedMemoryIds.has(item.id)).length;
    const checked = category.count > 0 && selectedCount === Math.max(items.length, 1);

    const group = document.createElement("div");
    group.className = "selection-group";
    group.innerHTML = `
      <div class="selection-row">
        <input class="selection-parent-check" type="checkbox" data-category="${category.id}" ${checked ? "checked" : ""}>
        <span>${category.label}</span>
        <em>${category.count}</em>
        <button class="selection-expand-btn ${expanded ? "is-expanded" : ""}" type="button" data-expand="${category.id}" aria-label="展开 ${category.label}">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M6 9l6 6 6-6"></path>
          </svg>
        </button>
      </div>
      ${expanded ? `<div class="selection-children"></div>` : ""}
    `;

    const parentCheck = group.querySelector(".selection-parent-check");
    parentCheck.addEventListener("change", event => {
      toggleCategorySelection(category.id, event.target.checked).catch(err => {
        toast(`${t("toastPrefixSelectionFailed")}${err.message}`, true);
      });
    });

    const expandBtn = group.querySelector(".selection-expand-btn");
    expandBtn.addEventListener("click", () => {
      toggleCategoryExpanded(category.id).catch(err => {
        toast(`${t("toastPrefixExpandFailed")}${err.message}`, true);
      });
    });

    if (expanded) {
      const childList = group.querySelector(".selection-children");
      if (items.length === 0) {
        childList.innerHTML = `<div class="selection-child"><input type="checkbox" checked disabled><div><strong>${t("selectionNoItems")}</strong><p>${t("selectionNoItemsDesc")}</p></div></div>`;
      } else if (category.id === "profile" || category.id === "preferences") {
        const grouped = new Map();
        items.forEach(item => {
          const groupLabel = item.display_title || item.title || "未命名";
          if (!grouped.has(groupLabel)) grouped.set(groupLabel, []);
          grouped.get(groupLabel).push(item);
        });
        grouped.forEach((groupItems, groupLabel) => {
          const subgroup = document.createElement("div");
          subgroup.className = "selection-subgroup";
          const scrollKey = selectionScrollKey(category.id, groupLabel);
          const chips = groupItems.map(item => {
            const preview = buildSelectionPreview(category.id, item);
            return `
              <div class="selection-chip-item">
                <label class="selection-chip" title="${escapeHtml(item.display_description || item.description || "")}">
                  <input type="checkbox" data-item-id="${escapeHtml(item.id)}" ${state.selectedMemoryIds.has(item.id) ? "checked" : ""}>
                  <span>${escapeHtml(preview.description || preview.title)}</span>
                </label>
                <button class="selection-memory-delete-btn" type="button" data-delete-item-id="${escapeHtml(item.id)}" aria-label="删除 ${escapeHtml(preview.description || preview.title)}">×</button>
              </div>
            `;
          }).join("");
          subgroup.innerHTML = `
            <div class="selection-subgroup-title">${escapeHtml(groupLabel)}</div>
            <div class="selection-chip-row" data-scroll-key="${scrollKey}">${chips}</div>
          `;
          subgroup.querySelectorAll("input").forEach(checkbox => {
            checkbox.addEventListener("change", event => {
              const itemId = event.target.dataset.itemId;
              setMemoryItemSelected(itemId, event.target.checked);
              renderSelectionList();
            });
          });
          subgroup.querySelectorAll("[data-delete-item-id]").forEach(button => {
            button.addEventListener("click", event => {
              event.preventDefault();
              event.stopPropagation();
              const itemId = event.currentTarget.dataset.deleteItemId;
              const item = groupItems.find(candidate => candidate.id === itemId);
              deleteMemoryItem(category.id, item).catch(err => {
                toast(`${t("toastPrefixDeleteFailed")}${translateBackendError(errorMessage(err, t("errDeleteMemory")))}`, true);
              });
            });
          });
          childList.appendChild(subgroup);
        });
      } else {
        items.forEach(item => {
          const preview = buildSelectionPreview(category.id, item);
          const child = document.createElement("div");
          child.className = "selection-child";
          child.innerHTML = `
            <input type="checkbox" data-item-id="${escapeHtml(item.id)}" ${state.selectedMemoryIds.has(item.id) ? "checked" : ""}>
            <div>
              <strong title="${escapeHtml(item.title || "")}">${escapeHtml(preview.title)}</strong>
              <p title="${escapeHtml(item.description || "")}">${escapeHtml(preview.description)}</p>
            </div>
            <button class="selection-memory-delete-btn" type="button" data-delete-item-id="${escapeHtml(item.id)}" aria-label="删除 ${escapeHtml(preview.title || preview.description)}">×</button>
          `;
          const checkbox = child.querySelector("input");
          checkbox.addEventListener("change", event => {
            setMemoryItemSelected(item.id, event.target.checked);
            renderSelectionList();
          });
          const deleteBtn = child.querySelector("[data-delete-item-id]");
          deleteBtn.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            deleteMemoryItem(category.id, item).catch(err => {
              toast(`${t("toastPrefixDeleteFailed")}${translateBackendError(errorMessage(err, t("errDeleteMemory")))}`, true);
            });
          });
          childList.appendChild(child);
        });
      }
    }

    listEl.appendChild(group);
  });
  restoreSelectionScroll(listEl);
}

async function initializeDefaultMemorySelection() {
  if (state.selectedMemoryIds.size > 0) return;
  for (const category of ["profile", "preferences", "workflows"]) {
    const items = await ensureCategoryItems(category);
    if (items.length === 0) state.selectedMemoryIds.add(`${category}:default`);
    else items.forEach(item => state.selectedMemoryIds.add(item.id));
  }
  await persistMemorySelection();
}

function deriveMySkills(allData, pnData) {
  const skills = [];
  const workflows = allData["mw:workflows"] ?? [];
  workflows.slice(0, 4).forEach((workflow, index) => {
    skills.push({
      id: `workflow:${workflow.workflow_name || index}`,
      icon: "流",
      title: workflow.workflow_name || `${t("workflowFallbackTitle")} ${index + 1}`,
      description: workflow.preferred_artifact_format || workflow.trigger_condition || t("workflowFallbackDesc"),
    });
  });

  const nodes = Object.entries(pnData.nodes ?? {}).slice(0, Math.max(0, 4 - skills.length));
  nodes.forEach(([id, node]) => {
    skills.push({
      id: `persistent:${id}`,
      icon: "忆",
      title: node.description || node.key || id,
      description: t("persistentFallbackDesc"),
    });
  });

  if (skills.length === 0) {
    skills.push({
      id: "skill:empty",
      icon: state.lang === "en" ? "∅" : "空",
      title: t("skillEmptyTitle"),
      description: t("skillEmptyDesc"),
      selectable: false,
    });
  }

  return skills;
}

function getSkillIcon(item) {
  if (item?.icon && String(item.icon).trim() && String(item.icon) !== "undefined") {
    return String(item.icon).trim().slice(0, 1);
  }
  const fallback = item?.title?.trim()?.slice(0, 1);
  return fallback || "技";
}

function buildEmptySkillCard() {
  return {
    id: "skill:empty",
    icon: state.lang === "en" ? "∅" : "空",
    title: t("skillEmptyTitle"),
    description: t("skillEmptyDesc"),
    selectable: false,
  };
}

function truncateText(text, maxLength = 72, ellipsis = true) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  if (value.length <= maxLength) return value;
  const cutLength = ellipsis ? Math.max(0, maxLength - 1) : maxLength;
  const cut = value.slice(0, cutLength).trim();
  return ellipsis ? `${cut}…` : cut;
}

function buildSkillPreview(item) {
  if (item?.selectable === false) {
    return {
      title: item.title,
      summary: item.description || "",
      meta: "",
    };
  }

  const title = truncateText(item?.display_title || item?.title || t("skillUnnamed"), 28);
  const displaySummary = item?.display_summary ? `${t("skillLabelDesc")}${item.display_summary}` : "";
  const displayOutput = item?.display_output ? `${t("skillLabelOutput")}${item.display_output}` : "";
  const summaryCandidates = [
    displaySummary && displayOutput ? `${displaySummary} · ${displayOutput}` : "",
    displaySummary,
    displayOutput,
    item?.goal ? `${t("skillLabelGoal")}${item.goal}` : "",
    item?.output_format ? `${t("skillLabelOutput")}${item.output_format}` : "",
    item?.description || "",
  ].filter(Boolean);

  let summary = summaryCandidates[0] || "";
  if (!summary && Array.isArray(item?.steps) && item.steps.length > 0) {
    summary = `${t("skillLabelSteps")}${item.steps.slice(0, 2).join(" / ")}`;
  }
  if (summary.includes("|")) {
    summary = summary
      .split("|")
      .map(part => part.trim())
      .filter(Boolean)
      .slice(0, 2)
      .join(" · ");
  }

  return {
    title,
    summary: truncateText(summary, 64),
    meta: "",
  };
}

async function deleteSkill(skillId) {
  try {
    await backendApi().deleteSkills(state.backendUrl, { skill_ids: [skillId] });
    state.selectedSkillIds.delete(skillId);
    state.selectedRecommendedIds.delete(skillId);
    if (state.currentSkillTab === "recommended") {
      const result = await backendApi().getRecommendedSkills(state.backendUrl);
      renderRecommendedSkillMeta(result.meta || null);
      renderRecommendedSkillItems(result.items || [], result.meta || null);
    } else {
      const result = await backendApi().getMySkills(state.backendUrl);
      renderSkillList(result.items || [], state.selectedSkillIds, { showDelete: false });
    }
    toast(t("toastSkillRemovedSingle"));
  } catch (err) {
    toast(`${t("toastPrefixDeleteFailed")}${err.message}`, true);
  }
}

async function deleteSelectedSkills() {
  const skillIds = Array.from(state.selectedSkillIds);
  if (!skillIds.length) {
    toast(t("toastSkillSelectFirst"), true);
    return;
  }
  try {
    await backendApi().deleteSkills(state.backendUrl, { skill_ids: skillIds });
    skillIds.forEach(id => {
      state.selectedSkillIds.delete(id);
      state.selectedRecommendedIds.delete(id);
    });
    const result = await backendApi().getMySkills(state.backendUrl);
    renderSkillList(result.items || [], state.selectedSkillIds, { showDelete: false });
    toast(t("toastSkillDeleted"));
  } catch (err) {
    toast(`${t("toastPrefixDeleteFailed")}${err.message}`, true);
  }
}

function renderSkillList(items, selectedSet, options = {}) {
  const { showDelete = false } = options;
  const listEl = document.getElementById("skillList");
  listEl.innerHTML = "";
  const safeItems = items.length === 0 && state.currentSkillTab === "my" ? [buildEmptySkillCard()] : items;

  safeItems.forEach(item => {
    const wrapper = document.createElement("div");
    wrapper.className = "skill-item";
    wrapper.dataset.skillId = item.id;
    const iconText = getSkillIcon(item);
    const preview = buildSkillPreview(item);
    const actionNodes = item.selectable === false
      ? `<div class="skill-check-placeholder"></div>`
      : `
        <div class="skill-actions">
          <input class="skill-check" type="checkbox" ${selectedSet.has(item.id) ? "checked" : ""}>
          ${showDelete ? '<button class="skill-delete-btn" type="button" aria-label="删除 Skill">×</button>' : ""}
        </div>
      `;
    wrapper.innerHTML = `
      <div class="skill-icon">${iconText}</div>
      <div class="skill-copy">
        <h4 title="${item.title || ""}">${preview.title}</h4>
        ${preview.meta ? `<div class="skill-meta">${preview.meta}</div>` : ""}
        <p title="${item.description || ""}">${preview.summary}</p>
      </div>
      ${actionNodes}
    `;
    const checkbox = wrapper.querySelector("input");
    if (checkbox) {
      checkbox.addEventListener("change", () => {
        syncSkillSelection(item.id, checkbox.checked);
      });
    }
    const deleteBtn = wrapper.querySelector(".skill-delete-btn");
    if (deleteBtn) {
      deleteBtn.addEventListener("click", event => {
        event.preventDefault();
        deleteSkill(item.id);
      });
    }
    listEl.appendChild(wrapper);
  });
}

function formatRecommendedUpdatedAt(value) {
  if (!value) return state.lang !== "en" ? "最近更新：未知" : "Updated: unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return state.lang !== "en" ? "最近更新：未知" : "Updated: unknown";
  }
  const now = new Date();
  const sameDay = now.getFullYear() === date.getFullYear()
    && now.getMonth() === date.getMonth()
    && now.getDate() === date.getDate();
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  if (state.lang !== "en") {
    return sameDay
      ? `最近更新：今天 ${hh}:${mm}`
      : `最近更新：${date.getMonth() + 1}/${date.getDate()} ${hh}:${mm}`;
  }
  return sameDay
    ? `Updated: today ${hh}:${mm}`
    : `Updated: ${date.getMonth() + 1}/${date.getDate()} ${hh}:${mm}`;
}

function renderRecommendedSkillMeta(meta) {
  const el = document.getElementById("recommendedSkillMeta");
  if (!el) return;
  if (!meta) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  const status = meta.last_refresh_status === "success"
    ? (state.lang !== "en" ? "今日推荐" : "Today")
    : (state.lang !== "en" ? "推荐缓存" : "Cached");
  const sourceText = Array.isArray(meta.sources) && meta.sources.length
    ? (state.lang !== "en" ? `来源：${meta.sources.join(" / ")}` : `Sources: ${meta.sources.join(" / ")}`)
    : "";
  const updatedText = formatRecommendedUpdatedAt(meta.last_updated_at);
  el.textContent = [status, updatedText, sourceText].filter(Boolean).join(" · ");
  el.classList.remove("hidden");
}
function renderSkillActions() {
  const deleteBtn = document.getElementById("deleteSkillBtn");
  const saveBtn = document.getElementById("saveRecommendedSkillBtn");
  if (!saveBtn || !deleteBtn) return;
  deleteBtn.classList.toggle("hidden", state.currentSkillTab !== "my");
  saveBtn.classList.toggle("hidden", state.currentSkillTab !== "recommended");
}

function syncSkillSelection(skillId, checked) {
  if (checked) {
    state.selectedSkillIds.add(skillId);
  } else {
    state.selectedSkillIds.delete(skillId);
  }
  if (String(skillId).startsWith("rec:")) {
    if (checked) {
      state.selectedRecommendedIds.add(skillId);
    } else {
      state.selectedRecommendedIds.delete(skillId);
    }
  }
}

const RECOMMENDED_INITIAL_COUNT = 3;

function updateShowMoreBtn() {
  const btn = document.getElementById("showMoreSkillsBtn");
  const scroll = document.getElementById("skillListScroll");
  if (!btn) return;
  const total = state.recommendedSkillItems.length;
  const remaining = total - RECOMMENDED_INITIAL_COUNT;
  if (remaining <= 0 || state.currentSkillTab !== "recommended") {
    btn.classList.add("hidden");
    scroll?.classList.remove("is-scrollable");
    return;
  }
  btn.classList.remove("hidden");
  btn.textContent = state.recommendedExpanded
    ? t("showLessSkills")
    : `${t("showMoreSkills")} (${remaining})`;
  scroll?.classList.toggle("is-scrollable", state.recommendedExpanded);
}

function renderRecommendedSkillItems(items, meta = null) {
  state.recommendedSkillItems = Array.isArray(items) ? [...items] : [];
  renderRecommendedSkillMeta(meta);
  const displayItems = state.recommendedExpanded
    ? state.recommendedSkillItems
    : state.recommendedSkillItems.slice(0, RECOMMENDED_INITIAL_COUNT);
  renderSkillList(displayItems, state.selectedRecommendedIds, { showDelete: false });
  updateShowMoreBtn();
  renderSkillActions();
}

function scheduleSummaryRefresh(reason = "memory-updated") {
  if (summaryRefreshTimer) {
    clearTimeout(summaryRefreshTimer);
  }
  summaryRefreshTimer = setTimeout(() => {
    summaryRefreshTimer = null;
    refreshSummary().catch(err => {
      logPopupError(`Refresh summary after ${reason} failed`, err, {
        backendUrl: state.backendUrl || DEFAULT_BACKEND_URL,
      });
    });
  }, 300);
}


async function refreshSummary() {
  try {
    const locale = state.lang === "en" ? "en-US" : "zh-CN";
    const [summary, categories] = await Promise.all([
      backendApi().getSummary(state.backendUrl),
      backendApi().getMemoryCategories(state.backendUrl, locale),
    ]);

    state.categories.profile = categories.categories.find(item => item.id === "profile")?.count ?? 0;
    state.categories.preferences = categories.categories.find(item => item.id === "preferences")?.count ?? 0;
    state.categories.projects = categories.categories.find(item => item.id === "projects")?.count ?? 0;
    state.categories.workflows = categories.categories.find(item => item.id === "workflows")?.count ?? 0;
    const dailyNotesCategory = categories.categories.find(item => item.id === "daily_notes")
      || categories.categories.find(item => item.id === "persistent");
    state.categories.daily_notes = dailyNotesCategory?.count ?? 0;
    state.categoryLabels.profile = categories.categories.find(item => item.id === "profile")?.label || CATEGORY_LABELS.profile;
    state.categoryLabels.preferences = categories.categories.find(item => item.id === "preferences")?.label || CATEGORY_LABELS.preferences;
    state.categoryLabels.projects = categories.categories.find(item => item.id === "projects")?.label || CATEGORY_LABELS.projects;
    state.categoryLabels.workflows = categories.categories.find(item => item.id === "workflows")?.label || CATEGORY_LABELS.workflows;
    state.categoryLabels.daily_notes = dailyNotesCategory?.label || CATEGORY_LABELS.daily_notes;
    await Promise.all(["profile", "preferences", "projects", "workflows", "daily_notes"].map(category => ensureCategoryItems(category)));
    await pruneUnavailableMemorySelection();
    if (state.selectedMemoryIds.size === 0 && !state.hasStoredMemorySelection) {
      await initializeDefaultMemorySelection();
    }
    renderSelectionList();
    renderStats({
      lastSyncAt: summary.last_sync_at,
      conversationCount: summary.conversation_count,
      memoryItemCount: summary.memory_item_count,
    });

    if (state.currentSkillTab === "my") {
      const skillResponse = await backendApi().getMySkills(state.backendUrl);
      renderSkillList(skillResponse.items || [], state.selectedSkillIds, { showDelete: false });
    } else {
      const recommendedResponse = await backendApi().getRecommendedSkills(state.backendUrl);
      renderRecommendedSkillItems(recommendedResponse.items || [], recommendedResponse.meta || null);
    }
    renderSkillActions();
    return;
  } catch {
    // Fallback to local extension storage before backend is fully wired.
  }

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
  state.categories.daily_notes = Object.keys(pnData.nodes ?? {}).length;
  renderSelectionList();

  const summary = {
    lastSyncAt: state.lastSyncAt,
    conversationCount: conversations.length,
    memoryItemCount:
      state.categories.profile +
      state.categories.preferences +
      state.categories.projects +
      state.categories.workflows +
      state.categories.daily_notes +
      episodes.length,
  };

  renderStats(summary);
  const mySkills = deriveMySkills(allData, pnData);
  if (state.currentSkillTab === "my") renderSkillList(mySkills, state.selectedSkillIds, { showDelete: false });
}

async function saveSettings(showToast = true) {
  try {
    const backendUrlInput = document.getElementById("backendUrlInput");
    const rawBackendUrl = backendUrlInput.value.trim();
    state.apiKey = document.getElementById("apiKeyInput").value.trim();
    state.backendUrl = rawBackendUrl;
    state.storagePath = document.getElementById("storageDirInput").value.trim();
    await storageSet({
      [STORAGE_KEYS.apiProvider]: state.apiProvider,
      [STORAGE_KEYS.apiKey]: state.apiKey,
      [STORAGE_KEYS.apiBaseUrl]: state.apiBaseUrl,
      [STORAGE_KEYS.apiModel]: state.apiModel,
      [STORAGE_KEYS.backendUrl]: state.backendUrl,
      [STORAGE_KEYS.storagePath]: state.storagePath,
      [STORAGE_KEYS.keepUpdated]: state.syncEnabled,
      [STORAGE_KEYS.realtimeUpdate]: state.realtimeUpdate,
      [STORAGE_KEYS.detailedInjection]: state.detailedInjection,
    });
    const backendSettings = await backendApi().saveSettings(state.backendUrl, {
      api_provider: state.apiProvider,
      api_key: state.apiKey,
      api_base_url: state.apiBaseUrl,
      api_model: state.apiModel,
      storage_path: state.storagePath,
      keep_updated: state.syncEnabled,
      realtime_update: state.realtimeUpdate,
      detailed_injection: state.detailedInjection,
      backend_url: state.backendUrl,
    });
    state.apiKeyConfigured = backendSettings.api_key_configured;
    state.apiProvider = backendSettings.api_provider || state.apiProvider;
    state.apiBaseUrl = backendSettings.api_base_url || state.apiBaseUrl;
    state.apiModel = backendSettings.api_model || state.apiModel;
    state.storagePath = backendSettings.storage_path || "";
    state.syncEnabled = !!backendSettings.keep_updated;
    state.realtimeUpdate = !!backendSettings.realtime_update;
    state.detailedInjection = !!backendSettings.detailed_injection;
    if (state.apiKeyConfigured) {
      state.organizeApiHintVisible = false;
    }
    renderDirectory();
    renderSettings();
    renderSync();
    renderActionAvailability();
    if (showToast) {
      toast(t("toastSettingsSaved"));
    }
    if (showToast) {
      showCommandModal(buildBackendStartCommand(state.backendUrl));
    }
  } catch (error) {
    throw normalizeError(error, "保存设置失败");
  }
}

async function testConnection() {
  state.backendUrl = document.getElementById("backendUrlInput").value.trim() || state.backendUrl;
  try {
    const apiKey = document.getElementById("apiKeyInput").value.trim();
    if (!apiKey) {
      throw new Error("请先输入 API Key");
    }
    const result = await backendApi().testConnection(state.backendUrl, {
      api_provider: state.apiProvider,
      api_key: apiKey,
      api_base_url: state.apiBaseUrl,
      api_model: state.apiModel,
    });
    if (!result.ok) {
      throw new Error(result.message || "当前默认配置不匹配这把 key");
    }
    state.apiConnectionStatus = "ok";
    await saveSettings(false);
    state.organizeApiHintVisible = false;
    renderSettings();
    renderActionAvailability();
    toast(t("toastApiOk"));
  } catch (err) {
    try {
      await backendApi().getHealth(state.backendUrl);
      state.apiConnectionStatus = `failed:${err.message}`;
      renderSettings();
      toast(`${t("toastPrefixBackendOnlineBut")}${translateBackendError(err.message)}`, true);
    } catch {
      toast(`${t("toastPrefixConnectionFailed")}${translateBackendError(err.message)}`, true);
    }
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

function updateSyncBackendHealthPolling() {
  if (!state.syncEnabled) {
    if (syncBackendHealthTimer) {
      clearInterval(syncBackendHealthTimer);
      syncBackendHealthTimer = null;
    }
    return;
  }
  if (syncBackendHealthTimer) return;
  syncBackendHealthTimer = setInterval(() => {
    checkSyncBackendHealth().catch(err => {
      logPopupError("Periodic sync backend health check failed", err);
    });
  }, SYNC_HEALTH_CHECK_INTERVAL_MS);
}

async function checkSyncBackendHealth() {
  if (!state.syncEnabled) {
    updateSyncBackendHealthPolling();
    return;
  }
  try {
    await backendApi().getHealth(state.backendUrl);
  } catch (err) {
    await handleSyncBackendUnavailable(err, {
      showCommand: false,
      toastMessage: t("toastBackendDisconnected"),
    });
  }
}

async function handleSyncBackendUnavailable(error, options = {}) {
  const {
    showCommand = true,
    toastMessage = t("syncBackendRequired"),
  } = options;
  state.syncEnabled = false;
  await storageSet({
    [STORAGE_KEYS.keepUpdated]: false,
    [STORAGE_KEYS.lastSyncBackendError]: {
      type: "backend_unavailable",
      source: "popup",
      message: errorMessage(error, "无法连接到本地后端"),
      backendUrl: state.backendUrl || DEFAULT_BACKEND_URL,
      updatedAt: Date.now(),
    },
  });
  try {
    await broadcastCaptureToggle(false);
  } catch (broadcastError) {
    logPopupError("Disable capture after backend check failed", broadcastError);
  }
  renderSync();
  renderSettings();
  logPopupError("Sync requires local backend", error, {
    backendUrl: state.backendUrl || DEFAULT_BACKEND_URL,
  });
  toast(toastMessage, true);
  if (showCommand) {
    showCommandModal(buildBackendStartCommand(state.backendUrl), { checkBackendOnClose: true });
  }
}

async function toggleSync() {
  const nextEnabled = !state.syncEnabled;

  if (nextEnabled) {
    try {
      await backendApi().getHealth(state.backendUrl);
    } catch (err) {
      await handleSyncBackendUnavailable(err);
      return;
    }
  }

  state.syncEnabled = nextEnabled;
  try {
    const result = await backendApi().toggleSync(state.backendUrl, { enabled: state.syncEnabled });
    state.lastSyncAt = result.last_sync_at ?? state.lastSyncAt;
  } catch (err) {
    if (nextEnabled) {
      await handleSyncBackendUnavailable(err);
      return;
    }
    // Keep the local off state even if the backend is already offline.
  }
  await storageSet({
    [STORAGE_KEYS.keepUpdated]: state.syncEnabled,
    [STORAGE_KEYS.lastSyncBackendError]: null,
  });
  await broadcastCaptureToggle(state.syncEnabled);
  renderSync();
  renderSettings();
  await refreshSummary();
  if (state.syncEnabled) {
    if (state.apiKeyConfigured && state.realtimeUpdate && state.keepUpdated) {
      toast(t("toastSyncWithMemory"));
    } else if (state.apiKeyConfigured) {
      toast(t("toastSyncNoMemory"));
    } else {
      toast(t("toastSyncRawOnly"));
    }
  } else {
      toast(t("toastSyncStopped"));
  }
}

async function runOrganize() {
  const organizeBtn = document.getElementById("organizeBtn");
  if (!state.apiKeyConfigured) {
    state.organizeApiHintVisible = true;
    renderActionAvailability();
    toast(t("toastNeedApiKey"), true);
    return;
  }
  state.organizeApiHintVisible = false;
  organizeBtn.disabled = true;
  organizeBtn.style.opacity = "0.65";
  setOrganizeStatus(true);

  try {
    if (state.organizeJobState?.status === "running") {
      toast(t("toastOrganizeRunning"));
      startOrganizeStatePolling();
      return;
    }
    toast(t("toastOrganizeStarted"));
    const response = await backendApi().organizeMemory(state.backendUrl);
    if (response.job_id) {
      state.organizeJobState = {
        jobId: response.job_id,
        status: "running",
        message: "",
        current: null,
        total: null,
        error: "",
        acknowledgedAt: "",
        updatedAt: new Date().toISOString(),
      };
      await storageSet({ [STORAGE_KEYS.organizeJobState]: state.organizeJobState });
      await applyOrganizeState();
      startOrganizeStatePolling();
    } else {
      toast(t("toastOrganizeDone"));
      setOrganizeStatus(false);
      organizeBtn.disabled = false;
      organizeBtn.style.opacity = "";
    }
  } catch (err) {
    logPopupError("Organize memory failed", err, {
      backendUrl: state.backendUrl,
    });
    toast(`${t("toastPrefixOrganizeFailed")}${translateBackendError(err.message)}`, true);
    setOrganizeStatus(false);
    organizeBtn.disabled = false;
    organizeBtn.style.opacity = "";
  }
}

async function syncOrganizeStateFromStorage() {
  const stored = await storageGet(STORAGE_KEYS.organizeJobState);
  state.organizeJobState = stored[STORAGE_KEYS.organizeJobState] || null;
  return state.organizeJobState;
}

function stopOrganizeStatePolling() {
  if (!state.organizePollTimer) return;
  clearInterval(state.organizePollTimer);
  state.organizePollTimer = null;
}

async function applyOrganizeState() {
  const organizeBtn = document.getElementById("organizeBtn");
  const jobState = state.organizeJobState;
  if (!jobState || !jobState.jobId) {
    setOrganizeStatus(false);
    if (organizeBtn) {
      organizeBtn.disabled = false;
      organizeBtn.style.opacity = "";
    }
    stopOrganizeStatePolling();
    return;
  }

  if (jobState.status === "running") {
    setOrganizeStatus(
      true,
      jobState.message,
      organizeProgressHint(jobState)
    );
    if (organizeBtn) {
      organizeBtn.disabled = true;
      organizeBtn.style.opacity = "0.65";
    }
    return;
  }

  stopOrganizeStatePolling();
  setOrganizeStatus(false);
  if (organizeBtn) {
    organizeBtn.disabled = false;
    organizeBtn.style.opacity = "";
  }

  if (jobState.status === "completed" && !jobState.acknowledgedAt) {
    const built = jobState.result?.episodes ?? 0;
    const updatedEpisodes = jobState.result?.updated_episodes ?? 0;
    const projects = jobState.result?.projects ?? 0;
    const workflows = jobState.result?.workflows ?? 0;
    if (jobState.result?.already_latest) {
      toast(t("toastMemoryUpToDate"));
    } else {
      const memorySummary = [`episodes ${built}`, `updated ${updatedEpisodes}`, `projects ${projects}`, `workflows ${workflows}`]
        .join(" · ");
      toast(`${t("toastPrefixOrganizeDoneWith")}${memorySummary}`);
    }
    state.lastSyncAt = new Date().toISOString();
    state.memoryItemsByCategory = {};
    state.organizeJobState = { ...jobState, acknowledgedAt: new Date().toISOString() };
    await storageSet({
      [STORAGE_KEYS.lastSyncAt]: state.lastSyncAt,
      [STORAGE_KEYS.organizeJobState]: state.organizeJobState,
    });
    await refreshSummary();
    return;
  }

  if (jobState.status === "failed" && !jobState.acknowledgedAt) {
    toast(`${t("toastPrefixOrganizeFailed")}${translateBackendError(jobState.error || "整理失败")}`, true);
    state.organizeJobState = { ...jobState, acknowledgedAt: new Date().toISOString() };
    await storageSet({ [STORAGE_KEYS.organizeJobState]: state.organizeJobState });
  }
}

function startOrganizeStatePolling() {
  stopOrganizeStatePolling();
  state.organizePollTimer = setInterval(() => {
    backendApi().getJob(state.backendUrl, state.organizeJobState?.jobId || "")
      .then(async job => {
        state.organizeJobState = {
          ...(state.organizeJobState || {}),
          jobId: job.id,
          status: job.status,
          message: job.progress?.message || "",
          current: typeof job.progress?.current === "number" ? job.progress.current : null,
          total: typeof job.progress?.total === "number" ? job.progress.total : null,
          error: job.error || "",
          result: job.result || null,
          updatedAt: new Date().toISOString(),
        };
        await storageSet({ [STORAGE_KEYS.organizeJobState]: state.organizeJobState });
        await applyOrganizeState();
      })
      .catch(err => {
        logPopupError("Sync organize job state failed", err, {
          jobId: state.organizeJobState?.jobId,
        });
      });
  }, 900);
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

async function getSelectedIdsForBackend() {
  const ids = [...state.selectedMemoryIds];
  if (ids.length === 0) throw new Error("请至少勾选一项记忆内容");
  return ids;
}

async function buildMemoryPackage() {
  const selectedIds = await getSelectedIdsForBackend();
  const selectedPrefixes = new Set(selectedIds.map(item => item.split(":")[0]));

  const allData = await storageGet(null);
  const packageData = {
    generated_at: new Date().toISOString(),
    selected_ids: selectedIds,
    data: {},
  };

  if (selectedPrefixes.has("profile") && allData["mw:profile"]) {
    packageData.data.profile = allData["mw:profile"];
  }
  if (selectedPrefixes.has("preferences") && allData["mw:preferences"]) {
    packageData.data.preferences = allData["mw:preferences"];
  }
  if (selectedPrefixes.has("project")) {
    packageData.data.projects = Object.entries(allData)
      .filter(([key]) => key.startsWith("mw:projects:"))
      .map(([, value]) => value);
  }
  if (selectedPrefixes.has("workflow")) {
    packageData.data.workflows = allData["mw:workflows"] ?? [];
  }
  if (selectedPrefixes.has("daily_notes") || selectedPrefixes.has("persistent")) {
    const pnData = await readPersistentNodes();
    const selectedNodeIds = new Set(
      selectedIds
        .filter(id => id.startsWith("daily_notes:") || id.startsWith("persistent:"))
        .map(id => id.split(":").slice(1).join(":"))
    );
    packageData.data.daily_notes = Object.entries(pnData.nodes ?? {})
      .filter(([id]) => selectedNodeIds.size === 0 || selectedNodeIds.has(id))
      .map(([id, node]) => ({ id, ...node }));

    const episodeIds = new Set(packageData.data.daily_notes.flatMap(node => node.episode_refs ?? []));
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
    const selectedIds = await getSelectedIdsForBackend();
    const result = await backendApi().exportPackage(state.backendUrl, {
      selected_ids: selectedIds,
      target_format: "generic",
      include_episodic_evidence: true,
    });
    const date = new Date().toISOString().slice(0, 10);
    downloadText(result.filename || `memory_package_${date}.txt`, result.content || "");
    toast(t("toastExported"));
  } catch {
    try {
      const pkg = await buildMemoryPackage();
      const text = buildMemoryPrompt(pkg);
      const date = new Date().toISOString().slice(0, 10);
      downloadText(`memory_package_${date}.txt`, text);
      toast(t("toastExported"));
    } catch (err) {
      toast(translateBackendError(err.message), true);
    }
  }
}

async function getActiveSupportedTab() {
  const [tab] = await tabsQuery({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("未找到当前标签页");
  if (!isSupportedTab(tab)) {
    throw new Error("请先切换到 ChatGPT、Gemini、DeepSeek 或豆包页面");
  }
  return tab;
}

async function injectTextIntoTab(text) {
  const tab = await getActiveSupportedTab();
  let result;
  try {
    result = await tabsSendMessage(tab.id, { type: "INJECT_INPUT", text });
  } catch (err) {
    if (isMissingReceiverError(err)) {
      const copied = await copyTextToClipboard(text);
      return {
        ok: copied,
        fallback: copied ? "clipboard" : "receiver_missing",
      };
    }
    throw err;
  }
  if (!result?.ok) throw new Error(result?.error ?? "当前页面不支持注入");
  return { ok: true, fallback: null };
}

async function scrapeCurrentConversationFromTab() {
  const tab = await getActiveSupportedTab();
  const result = await tabsSendMessage(tab.id, { type: "SCRAPE_CONVERSATION" });
  if (!result?.ok) throw new Error(result?.error ?? "当前页面不支持抓取整段对话");
  if (!result?.data?.messages?.length) throw new Error("当前页面没有可加入的对话内容");
  return result.data;
}

async function scrapePlatformMemoryFromTab() {
  const tab = await getActiveSupportedTab();
  const result = await tabsSendMessage(tab.id, { type: "SCRAPE_PLATFORM_MEMORY" });
  if (!result?.ok) throw new Error(result?.error ?? "当前页面不支持抓取平台记忆");
  const hasStructuredContent = Boolean(
    (result?.data?.savedMemoryItems || []).length
    || (result?.data?.customInstructions || []).length
    || (result?.data?.platformSkills || []).length
    || Object.keys(result?.data?.agentConfig || {}).length
  );
  if (!hasStructuredContent && !result?.data?.pageTextExcerpt && !(result?.data?.memoryHints || []).length) {
    throw new Error("当前页面没有可保存的平台记忆信息");
  }
  return result.data;
}

function _extractFirstJsonObject(text) {
  const raw = String(text || "").trim();
  if (!raw) throw new Error("平台没有返回可解析的内容");

  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = (fenced?.[1] || raw).trim();
  const start = candidate.indexOf('{');
  if (start < 0) throw new Error("未找到 JSON 结构");

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < candidate.length; i++) {
    const ch = candidate[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (ch === '\\') {
        escaped = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return candidate.slice(start, i + 1);
    }
  }
  throw new Error("JSON 结构不完整");
}

async function submitPromptAndWait(promptText, { timeoutMs = 120000 } = {}) {
  const tab = await getActiveSupportedTab();
  const injection = await injectTextIntoTab(promptText);
  if (injection?.fallback === "clipboard") {
    throw new Error("当前页面未就绪，无法自动提交采集指令");
  }

  const jobId = `platform-memory:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`;
  const ack = await tabsSendMessage(tab.id, {
    type: "SUBMIT_AND_WAIT",
    jobId,
    timeoutMs,
    skipDownload: true,
    isMemory: true,
  });
  if (!ack?.ok) throw new Error(ack?.error || "平台记忆采集发送失败");

  const deadline = Date.now() + timeoutMs + 5000;
  while (Date.now() < deadline) {
    const result = await storageGet(jobId);
    const payload = result?.[jobId];
    if (payload) {
      await new Promise(resolve => chrome.storage.local.remove([jobId], resolve));
      if (!payload.ok) throw new Error(payload.error || "平台记忆采集失败");
      return { tab, text: String(payload.text || "").trim(), source: payload.source || "assistant" };
    }
    await sleep(900);
  }
  await new Promise(resolve => chrome.storage.local.remove([jobId], resolve));
  throw new Error("等待平台记忆采集结果超时");
}

function normalizePlatformMemoryReport(report, tab) {
  if (!report || typeof report !== 'object') {
    throw new Error("平台返回的记忆内容不是对象");
  }
  return {
    platform: inferTargetPlatformFromTab(tab),
    url: tab.url || "",
    title: report.title || tab.title || "",
    heading: report.heading || report.agentName || tab.title || "",
    agentName: report.agentName || report.heading || "",
    capturedAt: new Date().toISOString(),
    pageType: report.pageType || "saved_memory_report",
    recordTypes: Array.isArray(report.recordTypes) ? report.recordTypes : [],
    savedMemoryItems: Array.isArray(report.savedMemoryItems) ? report.savedMemoryItems.filter(Boolean) : [],
    customInstructions: Array.isArray(report.customInstructions) ? report.customInstructions : [],
    agentConfig: report.agentConfig && typeof report.agentConfig === "object" ? report.agentConfig : {},
    platformSkills: Array.isArray(report.platformSkills) ? report.platformSkills : [],
    memoryHints: Array.isArray(report.savedMemoryItems) ? report.savedMemoryItems.filter(Boolean).slice(0, 20) : [],
    pageTextExcerpt: String(report.summary || report.heading || report.agentName || "").slice(0, 1200),
  };
}

async function collectPlatformMemoryWithPrompt() {
  const promptText = CONFIG.platformMemoryCollect;
  if (!promptText?.trim()) throw new Error("平台记忆采集提示词未加载");
  const { tab, text } = await submitPromptAndWait(promptText, { timeoutMs: 120000 });
  const report = JSON.parse(_extractFirstJsonObject(text));
  return normalizePlatformMemoryReport(report, tab);
}

async function injectPackage() {
  try {
    const selectedIds = await getSelectedIdsForBackend();
    const result = await backendApi().injectPackage(state.backendUrl, {
      selected_ids: selectedIds,
      target_platform: "chatgpt",
      detailed_injection: state.detailedInjection,
    });
    const injection = await injectTextIntoTab(result.text || "");
    if (injection?.fallback === "clipboard") {
      toast(t("toastInjectFallback"));
    } else {
      toast(t("toastInjected"));
    }
  } catch {
    try {
      const pkg = await buildMemoryPackage();
      const injection = await injectTextIntoTab(buildMemoryPrompt(pkg));
      if (injection?.fallback === "clipboard") {
        toast(t("toastInjectFallback"));
      } else {
        toast(t("toastInjected"));
      }
    } catch (err) {
      toast(`${t("toastPrefixInjectFailed")}${translateBackendError(err.message)}`, true);
    }
  }
}

async function addCurrentConversation() {
  const button = document.getElementById("addCurrentConversationBtn");
  button.disabled = true;
  button.style.opacity = "0.65";

  try {
    toast(t("toastAddingConversation"));
    const conversation = await scrapeCurrentConversationFromTab();
    const response = await backendApi().importCurrentConversation(state.backendUrl, {
      platform: conversation.platform,
      chat_id: conversation.chatId || crypto.randomUUID().slice(0, 8),
      url: conversation.url,
      title: conversation.title || "",
      messages: conversation.messages,
      process_now: false,
    });
    const job = response.job_id
      ? await backendApi().getJob(state.backendUrl, response.job_id)
      : null;
    if (job?.status === "failed") throw new Error(job.error || "加入当前对话失败");
    await refreshSummary();
    toast(t("toastConversationAdded"));
  } catch (err) {
    toast(`${t("toastPrefixConversationFailed")}${translateBackendError(err.message)}`, true);
  } finally {
    button.disabled = false;
    button.style.opacity = "";
  }
}

async function addPlatformMemory() {
  const button = document.getElementById("addPlatformMemoryBtn");
  button.disabled = true;
  button.style.opacity = "0.65";

  try {
    toast(t("toastCollectingPlatform"));
    let snapshot;
    try {
      snapshot = await collectPlatformMemoryWithPrompt();
    } catch (promptErr) {
      console.warn("[popup] prompt-based platform memory capture failed:", promptErr);
      snapshot = await scrapePlatformMemoryFromTab();
    }
    const response = await backendApi().importPlatformMemory(state.backendUrl, snapshot);
    toast(t("toastPlatformAdded"));
  } catch (err) {
    toast(`${t("toastPrefixPlatformFailed")}${translateBackendError(err.message)}`, true);
  } finally {
    button.disabled = false;
    button.style.opacity = "";
  }
}

function inferTargetPlatformFromTab(tab) {
  try {
    const hostname = new URL(tab?.url || "").hostname;
    if (hostname === "gemini.google.com") return "gemini";
    if (hostname === "chat.deepseek.com") return "deepseek";
    if (hostname === "www.doubao.com") return "doubao";
    return "chatgpt";
  } catch {
    return "chatgpt";
  }
}

async function saveRecommendedSkills() {
  const selectedIds = [...state.selectedRecommendedIds];
  if (selectedIds.length === 0) {
    toast(t("toastSkillSelectRecommended"), true);
    return;
  }
  try {
    const mergedIds = [...new Set([...state.selectedSkillIds, ...selectedIds])];
    const result = await backendApi().saveSkills(state.backendUrl, { skill_ids: mergedIds, merge: true });
    state.selectedSkillIds = new Set(result.saved_skill_ids || mergedIds);
    state.selectedRecommendedIds = new Set([...state.selectedRecommendedIds, ...selectedIds]);
    await storageSet({ [STORAGE_KEYS.savedSkills]: [...state.selectedSkillIds] });
    toast(`${t("toastSavedSkillCount")}${selectedIds.length}${t("toastSavedSkillSuffix")}`);
  } catch (err) {
    toast(`${t("toastPrefixAddFailed")}${translateBackendError(err.message)}`, true);
  }
}

async function exportSkills() {
  const allSkillIds = new Set([...state.selectedSkillIds, ...state.selectedRecommendedIds]);
  const selectedIds = [...allSkillIds];
  if (selectedIds.length === 0) {
    toast(t("toastSkillSelectOne"), true);
    return;
  }
  try {
    const result = await backendApi().exportSkills(state.backendUrl, { skill_ids: selectedIds });
    downloadText(result.filename || `skills_${new Date().toISOString().slice(0, 10)}.json`, result.content || "");
    toast(t("toastSkillExported"));
  } catch (err) {
    try {
      const allData = await storageGet(null);
      const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
      const mySkills = deriveMySkills(allData, pnData);
      const selected = [];
      mySkills.forEach(skill => {
        if (state.selectedSkillIds.has(skill.id)) selected.push(skill);
      });
      state.recommendedSkillItems.forEach(skill => {
        if (state.selectedRecommendedIds.has(skill.id)) selected.push(skill);
      });
      if (selected.length === 0) throw new Error("请至少选择一个 Skill");
      const payload = {
        generated_at: new Date().toISOString(),
        skills: selected,
      };
      downloadText(`skills_${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(payload, null, 2));
      toast(t("toastSkillExported"));
    } catch (fallbackErr) {
      toast(`${t("toastPrefixExportFailed")}${translateBackendError(fallbackErr.message || err.message)}`, true);
    }
  }
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
    const selectedIds = [...state.selectedSkillIds, ...state.selectedRecommendedIds];
    if (selectedIds.length === 0) throw new Error("请至少选择一个 Skill");
    const tab = await getActiveSupportedTab();
    const result = await backendApi().injectSkills(state.backendUrl, {
      skill_ids: selectedIds,
      target_platform: inferTargetPlatformFromTab(tab),
    });
    const injection = await injectTextIntoTab(result.text || "");
    if (injection?.fallback === "clipboard") {
      toast(t("toastSkillInjectFallback"));
    } else {
      toast(t("toastSkillInjected"));
    }
  } catch {
    try {
      const allData = await storageGet(null);
      const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
      const mySkills = deriveMySkills(allData, pnData);
      const selected = [];

      mySkills.forEach(skill => {
        if (state.selectedSkillIds.has(skill.id)) selected.push(skill);
      });
      state.recommendedSkillItems.forEach(skill => {
        if (state.selectedRecommendedIds.has(skill.id)) selected.push(skill);
      });

      if (selected.length === 0) throw new Error("请至少选择一个 Skill");
      const injection = await injectTextIntoTab(buildSkillPrompt(selected));
      if (injection?.fallback === "clipboard") {
        toast(t("toastSkillInjectFallback"));
      } else {
        toast(t("toastSkillInjected"));
      }
    } catch (err) {
      toast(`${t("toastPrefixInjectFailed")}${translateBackendError(err.message)}`, true);
    }
  }
}

async function clearCache() {
  try {
    await backendApi().clearCache(state.backendUrl, { scope: "temporary" });
  } catch {
    // Ignore backend failure and still clear local cache.
  }
  await new Promise(resolve => chrome.storage.local.remove(["_raw_progress", "_sw_keepalive", "pending_flush"], resolve));
  toast(t("toastCacheCleared"));
}

async function clearAllMemoryFiles() {
  const confirmed = window.confirm(t("confirmClearAll"));
  if (!confirmed) return;

  await backendApi().clearCache(state.backendUrl, { scope: "all_memory" });

  const allData = await storageGet(null);
  const removableKeys = Object.keys(allData).filter(key => (
    key.startsWith("mw:")
    || key.startsWith("chat:")
    || key === "_raw_progress"
    || key === "_sw_keepalive"
    || key === "pending_flush"
  ));
  if (removableKeys.length) {
    await new Promise(resolve => chrome.storage.local.remove(removableKeys, resolve));
  }

  state.selectedMemoryIds.clear();
  state.hasStoredMemorySelection = true;
  await storageSet({ [STORAGE_KEYS.memorySelection]: [] });
  state.expandedCategories.clear();
  state.memoryItemsByCategory = {};
  state.organizeJobState = null;
  await storageSet({ [STORAGE_KEYS.organizeJobState]: null });
  await refreshSummary();
  renderSettings();
  renderActionAvailability();
  toast(t("toastMemoryCleared"));
}

function bindEvents() {
  const clearCacheBtn = document.getElementById("clearCacheBtn");
  const clearAllMemoryBtn = document.getElementById("clearAllMemoryBtn");
  if (clearCacheBtn && clearAllMemoryBtn && clearCacheBtn.parentElement === clearAllMemoryBtn.parentElement) {
    clearCacheBtn.insertAdjacentElement("afterend", clearAllMemoryBtn);
  }

  document.getElementById("menuBtn").addEventListener("click", () => setView("settings"));
  const langBtn = document.getElementById("langToggleBtn");
  if (langBtn) {
    langBtn.addEventListener("click", async () => {
      state.lang = state.lang === "zh" ? "en" : "zh";
      await storageSet({ [STORAGE_KEYS.lang]: state.lang });
      state.memoryItemsByCategory = {};
      applyLang();
      refreshSummary().catch(() => {});
    });
  }
  document.getElementById("gotoMigrateBtn").addEventListener("click", () => setView("migrate"));
  document.getElementById("gotoSettingsBtn").addEventListener("click", () => setView("settings"));
  document.getElementById("gotoSkillBtn").addEventListener("click", async () => {
    setView("skill");
    renderSkillActions();
    try {
      const result = await backendApi().getMySkills(state.backendUrl);
      renderSkillList(result.items || [], state.selectedSkillIds, { showDelete: false });
    } catch {
      const allData = await storageGet(null);
      const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
      renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds, { showDelete: false });
    }
  });

  document.querySelectorAll("[data-back]").forEach(btn => {
    btn.addEventListener("click", () => setView(btn.dataset.back));
  });

  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName !== "local") return;
    if (changes[STORAGE_KEYS.keepUpdated]) {
      state.syncEnabled = Boolean(changes[STORAGE_KEYS.keepUpdated].newValue);
      renderSync();
      renderSettings();
    }
    if (changes[STORAGE_KEYS.lastRawAppendAt]) {
      state.lastSyncAt = new Date(changes[STORAGE_KEYS.lastRawAppendAt].newValue).toISOString();
      scheduleSummaryRefresh("raw append");
    }
    const syncBackendError = changes[STORAGE_KEYS.lastSyncBackendError]?.newValue;
    if (syncBackendError?.type === "backend_unavailable" && syncBackendError.source !== "popup") {
      state.syncEnabled = false;
      renderSync();
      renderSettings();
      toast(t("toastBackendDisconnected"), true);
    }
  });

  document.getElementById("syncBtn").addEventListener("click", toggleSync);
  document.getElementById("selectDirBtn").addEventListener("click", () => {
    saveSettings(false).then(() => {
      toast(t("toastDirSaved"));
    }).catch(err => {
      if (!isExpectedSettingsFailure(err)) {
        logPopupError("Save storage path failed", err, { backendUrl: state.backendUrl || DEFAULT_BACKEND_URL });
      }
      toast(`${t("toastPrefixSaveFailed")}${translateBackendError(errorMessage(err, t("errSaveDir")))}`, true);
    });
  });

  document.getElementById("saveSettingsBtn").addEventListener("click", () => {
    saveSettings().catch(err => {
      if (!isExpectedSettingsFailure(err)) {
        logPopupError("Save settings failed", err, { backendUrl: state.backendUrl || DEFAULT_BACKEND_URL });
      }
      toast(`${t("toastPrefixSaveFailed")}${translateBackendError(errorMessage(err, t("errConnectBackend")))}`, true);
      showCommandModal(buildBackendStartCommand(
        document.getElementById("backendUrlInput")?.value.trim() || state.backendUrl,
      ), { checkBackendOnClose: true });
    });
  });
  document.getElementById("testConnectionBtn").addEventListener("click", testConnection);
  document.getElementById("closeCommandModalBtn").addEventListener("click", () => {
    closeCommandModal().catch(err => logPopupError("Close command modal failed", err));
  });
  document.getElementById("copyCommandBtn").addEventListener("click", async () => {
    const command = document.getElementById("commandModalText")?.textContent || "";
    if (!command.trim()) return;
    const copied = await copyTextToClipboard(command);
    toast(copied ? t("toastCopyCommandOk") : t("toastCopyCommandFailed"), !copied);
  });
  document.getElementById("commandModal").addEventListener("click", event => {
    if (event.target.id === "commandModal") {
      closeCommandModal().catch(err => logPopupError("Close command modal failed", err));
    }
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      closeCommandModal().catch(err => logPopupError("Close command modal failed", err));
    }
  });

  document.getElementById("realtimeUpdateToggle").addEventListener("change", async event => {
    state.realtimeUpdate = event.target.checked;
    await storageSet({ [STORAGE_KEYS.realtimeUpdate]: state.realtimeUpdate });
    try {
      const backendSettings = await backendApi().saveSettings(state.backendUrl, {
        api_provider: state.apiProvider,
        api_key: state.apiKey,
        api_base_url: state.apiBaseUrl,
        api_model: state.apiModel,
        storage_path: state.storagePath,
        keep_updated: state.syncEnabled,
        realtime_update: state.realtimeUpdate,
        detailed_injection: state.detailedInjection,
        backend_url: state.backendUrl,
      });
      state.apiKeyConfigured = backendSettings.api_key_configured;
      state.syncEnabled = backendSettings.keep_updated;
      state.realtimeUpdate = backendSettings.realtime_update;
      state.detailedInjection = !!backendSettings.detailed_injection;
    } catch {
      // Keep local change when backend is offline.
    }
    renderSettings();
    renderSync();
    renderActionAvailability();
    if (state.realtimeUpdate && state.apiKeyConfigured && state.syncEnabled && state.keepUpdated) {
      toast(t("toastSyncMemoryOnWithApi"));
    } else if (state.realtimeUpdate && !state.apiKeyConfigured) {
      toast(t("toastSyncMemoryOnNoApi"));
    } else {
      toast(t("toastSyncMemoryOff"));
    }
  });

  document.getElementById("detailedInjectionToggle").addEventListener("change", async event => {
    state.detailedInjection = event.target.checked;
    await storageSet({ [STORAGE_KEYS.detailedInjection]: state.detailedInjection });
    try {
      const backendSettings = await backendApi().saveSettings(state.backendUrl, {
        api_provider: state.apiProvider,
        api_key: state.apiKey,
        api_base_url: state.apiBaseUrl,
        api_model: state.apiModel,
        storage_path: state.storagePath,
        keep_updated: state.syncEnabled,
        realtime_update: state.realtimeUpdate,
        detailed_injection: state.detailedInjection,
        backend_url: state.backendUrl,
      });
      state.apiKeyConfigured = backendSettings.api_key_configured;
      state.syncEnabled = backendSettings.keep_updated;
      state.realtimeUpdate = backendSettings.realtime_update;
      state.detailedInjection = !!backendSettings.detailed_injection;
    } catch {
      // Keep local change when backend is offline.
    }
    renderSettings();
    toast(t(state.detailedInjection ? "toastDetailedOn" : "toastDetailedOff"));
  });

  document.getElementById("organizeBtn").addEventListener("click", runOrganize);
  document.getElementById("addCurrentConversationBtn").addEventListener("click", addCurrentConversation);
  document.getElementById("addPlatformMemoryBtn").addEventListener("click", addPlatformMemory);
  document.getElementById("exportPackageBtn").addEventListener("click", exportPackage);
  document.getElementById("injectPackageBtn").addEventListener("click", injectPackage);

  document.getElementById("mySkillTab").addEventListener("click", async () => {
    state.currentSkillTab = "my";
    state.recommendedExpanded = false;
    document.getElementById("mySkillTab").classList.add("is-active");
    document.getElementById("recommendedSkillTab").classList.remove("is-active");
    renderRecommendedSkillMeta(null);
    updateShowMoreBtn();
    renderSkillActions();
    try {
      const result = await backendApi().getMySkills(state.backendUrl);
      renderSkillList(result.items || [], state.selectedSkillIds, { showDelete: false });
    } catch {
      const allData = await storageGet(null);
      const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
      renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds, { showDelete: false });
    }
  });

  document.getElementById("recommendedSkillTab").addEventListener("click", () => {
    state.currentSkillTab = "recommended";
    document.getElementById("recommendedSkillTab").classList.add("is-active");
    document.getElementById("mySkillTab").classList.remove("is-active");
    renderSkillActions();
    backendApi().getRecommendedSkills(state.backendUrl)
      .then(result => {
        renderRecommendedSkillItems(result.items || [], result.meta || null);
      })
      .catch(err => {
        logPopupError("Load recommended skills failed", err, { backendUrl: state.backendUrl || DEFAULT_BACKEND_URL });
        renderRecommendedSkillItems([], null);
        toast(`${t("toastPrefixLoadRecommendedFailed")}${translateBackendError(errorMessage(err, t("errCheckBackend")))}`, true);
      });
  });

  document.getElementById("showMoreSkillsBtn").addEventListener("click", () => {
    state.recommendedExpanded = !state.recommendedExpanded;
    renderRecommendedSkillItems(state.recommendedSkillItems);
  });

  document.getElementById("saveRecommendedSkillBtn").addEventListener("click", saveRecommendedSkills);
  document.getElementById("deleteSkillBtn").addEventListener("click", deleteSelectedSkills);
  document.getElementById("exportSkillBtn").addEventListener("click", exportSkills);
  document.getElementById("injectSkillBtn").addEventListener("click", injectSkills);

  document.getElementById("importHistoryBtn").addEventListener("click", () => {
    document.getElementById("importFileInput").click();
  });

  document.getElementById("importFileInput").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const platform = file.name.toLowerCase().includes("deepseek") ? "deepseek" : "chatgpt";
      const result = await backendApi().importHistory(state.backendUrl, { platform, file });
      const job = result.job_id
        ? await backendApi().getJob(state.backendUrl, result.job_id)
        : null;
      if (job?.status === "failed") throw new Error(job.error || "导入失败");
      const imported = job?.result?.imported_conversations;
      await refreshSummary();
      toast(imported ? `${t("toastImportComplete")}${imported}${t("countSuffix")}` : `${t("toastImportJobCreated")}${result.job_id}`);
    } catch (err) {
      toast(`${t("toastPrefixImportFailed")}${translateBackendError(err.message)}`, true);
    } finally {
      event.target.value = "";
    }
  });

  document.getElementById("clearCacheBtn").addEventListener("click", clearCache);
  document.getElementById("clearAllMemoryBtn").addEventListener("click", () => {
    clearAllMemoryFiles().catch(err => {
      toast(`${t("toastPrefixClearFailed")}${translateBackendError(errorMessage(err, t("errClearMemory")))}`, true);
    });
  });
}

function applyLang() {
  const btn = document.getElementById("langToggleBtn");
  if (btn) btn.textContent = state.lang === "zh" ? "EN" : "中";
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const str = t(el.dataset.i18n);
    if (str !== undefined) el.textContent = str;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const str = t(el.dataset.i18nPlaceholder);
    if (str !== undefined) el.placeholder = str;
  });
  document.querySelectorAll("[data-i18n-aria]").forEach(el => {
    const str = t(el.dataset.i18nAria);
    if (str !== undefined) el.setAttribute("aria-label", str);
  });
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const str = t(el.dataset.i18nTitle);
    if (str !== undefined) el.title = str;
  });
  renderSync();
  renderSettings();
  renderDirectory();
  updateShowMoreBtn();
  if (state.lastSummary) renderStats(state.lastSummary);
  const emptyCard = document.querySelector("[data-skill-id='skill:empty']");
  if (emptyCard) {
    const card = buildEmptySkillCard();
    const iconEl = emptyCard.querySelector(".skill-icon");
    const titleEl = emptyCard.querySelector(".skill-copy h4");
    const descEl = emptyCard.querySelector(".skill-copy p");
    if (iconEl) iconEl.textContent = card.icon;
    if (titleEl) titleEl.textContent = card.title;
    if (descEl) descEl.textContent = card.description;
  }
}

async function init() {
  await CONFIG.loadPrompts();

  const settings = await storageGet([
    STORAGE_KEYS.apiProvider,
    STORAGE_KEYS.apiKey,
    STORAGE_KEYS.apiBaseUrl,
    STORAGE_KEYS.apiModel,
    STORAGE_KEYS.backendUrl,
    STORAGE_KEYS.storagePath,
    STORAGE_KEYS.keepUpdated,
    STORAGE_KEYS.keepUpdatedStrategy,
    STORAGE_KEYS.realtimeUpdate,
    STORAGE_KEYS.detailedInjection,
    STORAGE_KEYS.lastSyncAt,
    STORAGE_KEYS.savedSkills,
    STORAGE_KEYS.organizeJobState,
    STORAGE_KEYS.memorySelection,
    STORAGE_KEYS.lang,
  ]);

  state.apiProvider = settings[STORAGE_KEYS.apiProvider] || state.apiProvider;
  state.apiKey = settings[STORAGE_KEYS.apiKey] || "";
  state.apiKeyConfigured = !!state.apiKey;
  state.apiBaseUrl = settings[STORAGE_KEYS.apiBaseUrl] || state.apiBaseUrl;
  state.apiModel = settings[STORAGE_KEYS.apiModel] || state.apiModel;
  state.backendUrl = settings[STORAGE_KEYS.backendUrl] || state.backendUrl;
  const hasStoredSyncPreference = typeof settings[STORAGE_KEYS.keepUpdated] === "boolean";
  state.syncEnabled = hasStoredSyncPreference ? !!settings[STORAGE_KEYS.keepUpdated] : false;
  state.keepUpdated = true;
  state.realtimeUpdate = !!settings[STORAGE_KEYS.realtimeUpdate];
  state.detailedInjection = !!settings[STORAGE_KEYS.detailedInjection];
  state.storagePath = settings[STORAGE_KEYS.storagePath] || state.storagePath;
  state.lastSyncAt = settings[STORAGE_KEYS.lastSyncAt] || null;
  state.organizeJobState = settings[STORAGE_KEYS.organizeJobState] || null;
  state.lang = settings[STORAGE_KEYS.lang] || "zh";
  state.dirHandle = await loadSavedDir();
  const savedSkillIds = settings[STORAGE_KEYS.savedSkills] || [];
  state.selectedSkillIds = new Set(savedSkillIds);
  state.selectedRecommendedIds = new Set(savedSkillIds.filter(id => String(id).startsWith("rec:")));
  if (Array.isArray(settings[STORAGE_KEYS.memorySelection])) {
    state.selectedMemoryIds = new Set(sanitizeStoredMemoryIds(settings[STORAGE_KEYS.memorySelection]));
    state.hasStoredMemorySelection = true;
  }

  try {
    const backendSettings = await backendApi().getSettings(state.backendUrl);
    state.realtimeUpdate = backendSettings.realtime_update;
    state.lastSyncAt = backendSettings.last_sync_at || state.lastSyncAt;
    state.storagePath = backendSettings.storage_path || state.storagePath;
    state.apiKeyConfigured = backendSettings.api_key_configured || state.apiKeyConfigured;
    state.apiProvider = backendSettings.api_provider || state.apiProvider;
    state.apiBaseUrl = backendSettings.api_base_url || state.apiBaseUrl;
    state.apiModel = backendSettings.api_model || state.apiModel;
    state.detailedInjection = !!backendSettings.detailed_injection;
    await storageSet({ [STORAGE_KEYS.storagePath]: state.storagePath });
  } catch {
    // Keep extension-local settings when backend is offline.
  }

  if (!hasStoredSyncPreference) {
    state.syncEnabled = false;
    await storageSet({ [STORAGE_KEYS.keepUpdated]: false });
    try {
      await backendApi().toggleSync(state.backendUrl, { enabled: false });
    } catch {
      // Ignore backend toggle failures during first-run initialization.
    }
    try {
      await broadcastCaptureToggle(false);
    } catch {
      // Ignore content-script toggle failures during first-run initialization.
    }
  }

  bindEvents();
  applyLang();
  renderActionAvailability();
  if (state.syncEnabled) {
    checkSyncBackendHealth().catch(err => {
      logPopupError("Initial sync backend health check failed", err);
    });
  }
  await refreshSummary();
  await initializeDefaultMemorySelection();
  renderSelectionList();
  await applyOrganizeState();
  if (state.organizeJobState?.status === "running") {
    startOrganizeStatePolling();
  }

  try {
    const result = await backendApi().getMySkills(state.backendUrl);
    renderSkillList(result.items || [], state.selectedSkillIds, { showDelete: false });
  } catch {
    const allData = await storageGet(null);
    const pnData = allData["mw:persistent_nodes"] ?? { nodes: {} };
    renderSkillList(deriveMySkills(allData, pnData), state.selectedSkillIds, { showDelete: false });
  }
  renderSkillActions();
}

init().catch(err => {
  logPopupError("Init failed", err);
  toast(`${t("toastPrefixInitFailed")}${err.message}`, true);
});
