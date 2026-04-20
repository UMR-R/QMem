// Memory Engine — 增量记忆更新
// 存储层使用 chrome.storage.local（Service Worker 可访问）
// 数据格式与 Python L2Wiki 兼容，popup.js 打开时会自动同步到文件系统

import { extractJson } from "./llm_client.js";
import { newProfile, newPreferences, newProject, newWorkflow, newEpisode } from "./l2_wiki.js";

// ── Prompt file loader ────────────────────────────────────────────────────────

const _promptCache = new Map();

async function _loadPromptFile(name) {
  if (_promptCache.has(name)) return _promptCache.get(name);
  try {
    const url = chrome.runtime.getURL(`prompts/${name}.txt`);
    const text = await fetch(url).then(r => {
      if (!r.ok) throw new Error(r.status);
      return r.text();
    });
    const trimmed = text.trimEnd();
    _promptCache.set(name, trimmed);
    return trimmed;
  } catch (e) {
    console.warn(`[memory_engine] prompt file ${name}.txt not loaded:`, e.message);
    return null;
  }
}

// ── Storage keys（chrome.storage.local） ──────────────────────────────────────

const KEY = {
  profile:          "mw:profile",
  preferences:      "mw:preferences",
  workflows:        "mw:workflows",
  persistent_nodes: "mw:persistent_nodes",
  episode:          (id)   => `mw:episodes:${id}`,
  project:          (name) => `mw:projects:${encodeURIComponent(name)}`,
};

// ── 公开接口 ──────────────────────────────────────────────────────────────────

/**
 * 对一批 rounds 执行增量记忆更新，结果存入 chrome.storage.local。
 * popup 打开时会将结果同步到文件系统。
 * @param {object} chatData  { platform, url, rounds: [{timestamp, user, assistant}] }
 * @param {string} apiKey
 */
/**
 * 对一批 rounds 执行增量记忆更新。
 * @param {object} chatData  { platform, url, rounds: [{timestamp, user, assistant}] }
 * @param {string} apiKey
 * @param {object} [opts]
 * @param {boolean} [opts.batchMode=false]  true = 整条对话拼接后一次 API 调用（历史导入用，快 5-10 倍）
 */
export async function updateMemory(chatData, apiKey, { batchMode = false } = {}) {
  if (batchMode) return _updateMemoryBatch(chatData, apiKey);
  return _updateMemoryPerRound(chatData, apiKey);
}

// ── 逐轮模式（实时捕获用）─────────────────────────────────────────────────────

async function _updateMemoryPerRound(chatData, apiKey) {
  const { platform, rounds } = chatData;
  if (rounds.length === 0) return;

  const state = await _loadState();
  const episodeId = crypto.randomUUID().slice(0, 8);
  const firstTimestamp = rounds[0].timestamp;
  const lastTimestamp  = rounds[rounds.length - 1].timestamp;

  const epParts = { topics: [], summaries: [], decisions: [], issues: [], projects: [] };
  let hasContent = false;

  for (const round of rounds) {
    const stateSummary = _buildStateSummary(state);
    const convText = `User: ${round.user}\n\nAssistant: ${round.assistant}`;
    const userPrompt =
`CURRENT MEMORY STATE:
${stateSummary}

NEW CONVERSATION (${platform}, ${round.timestamp}):
${convText.slice(0, 4000)}`;

    let delta;
    try {
      delta = await extractJson(await _getDeltaSystem(), userPrompt, apiKey);
    } catch (err) {
      console.error("[memory_engine] LLM call failed:", err.message);
      continue;
    }
    if (!delta || delta.is_noise) continue;
    hasContent = true;

    _applyStateUpdates(delta, episodeId, round.timestamp, state);

    const ed = delta.episode ?? {};
    if (ed.topic)   epParts.topics.push(ed.topic);
    if (ed.summary) epParts.summaries.push(ed.summary);
    epParts.decisions.push(...(ed.key_decisions    ?? []));
    epParts.issues.push(...(ed.open_issues         ?? []));
    if (ed.related_project) epParts.projects.push(ed.related_project);
  }

  if (!hasContent) return;
  await _saveState(state);
  await _buildAndSaveEpisode(episodeId, platform, firstTimestamp, lastTimestamp, epParts, apiKey);
}

// ── 批量模式（历史导入用）──────────────────────────────────────────────────────
// 把整条对话拼成一段文本，一次 API 调用提取全部更新。
// 比逐轮模式快 N 倍（N = 轮数），适合 processAllRaw 批量处理。

async function _updateMemoryBatch(chatData, apiKey) {
  const { platform, rounds: rawRounds } = chatData;
  if (rawRounds.length === 0) return;

  const state = await _loadState();
  const episodeId = crypto.randomUUID().slice(0, 8);
  const firstTimestamp = rawRounds[0].timestamp;
  const lastTimestamp  = rawRounds[rawRounds.length - 1].timestamp;

  const allText = rawRounds.map((r, i) =>
    `[Round ${i + 1}] (${r.timestamp ?? ""})\nUser: ${r.user}\nAssistant: ${r.assistant}`
  ).join("\n\n");

  const stateSummary = _buildStateSummary(state);
  const userPrompt =
`CURRENT MEMORY STATE:
${stateSummary}

FULL CONVERSATION (${platform}, ${rawRounds.length} rounds):
${allText}`;

  let delta;
  try {
    delta = await extractJson(await _getDeltaSystem(), userPrompt, apiKey);
  } catch (err) {
    console.error("[memory_engine] Batch LLM call failed:", err.message);
    return;
  }
  if (!delta || delta.is_noise) return;

  _applyStateUpdates(delta, episodeId, lastTimestamp, state);
  await _saveState(state);

  const ed = delta.episode ?? {};
  const epParts = {
    topics:    ed.topic   ? [ed.topic]   : [],
    summaries: ed.summary ? [ed.summary] : [],
    decisions: ed.key_decisions ?? [],
    issues:    ed.open_issues   ?? [],
    projects:  ed.related_project ? [ed.related_project] : [],
  };
  await _buildAndSaveEpisode(episodeId, platform, firstTimestamp, lastTimestamp, epParts, apiKey);
}

// ── 共用：构建并保存 episode ──────────────────────────────────────────────────

async function _buildAndSaveEpisode(episodeId, platform, firstTs, lastTs, epParts, apiKey) {
  const ep = newEpisode();
  ep.episode_id          = episodeId;
  ep.platform            = platform ?? "unknown";
  ep.topic               = epParts.topics[0] ?? "";
  ep.summary             = epParts.summaries.join(" | ");
  ep.key_decisions       = [...new Set(epParts.decisions)];
  ep.open_issues         = [...new Set(epParts.issues)];
  ep.relates_to_projects = [...new Set(epParts.projects)];
  ep.time_range_start    = firstTs;
  ep.time_range_end      = lastTs;
  ep.created_at          = firstTs;
  ep.updated_at          = lastTs;

  await _saveEpisode(episodeId, ep);

  if (apiKey) {
    _updatePersistentNodes(ep, apiKey).catch(err =>
      console.error("[memory_engine] persistent nodes update failed:", err.message)
    );
  }
}

// ── 加载 / 保存（chrome.storage.local） ──────────────────────────────────────

async function _loadState() {
  const base = await chrome.storage.local.get([KEY.profile, KEY.preferences, KEY.workflows]);
  const allData = await chrome.storage.local.get(null);

  const projects = {};
  for (const [k, v] of Object.entries(allData)) {
    if (k.startsWith("mw:projects:")) {
      const name = decodeURIComponent(k.slice("mw:projects:".length));
      projects[name] = v;
    }
  }

  return {
    profile:     base[KEY.profile]     ?? newProfile(),
    preferences: base[KEY.preferences] ?? newPreferences(),
    workflows:   base[KEY.workflows]   ?? [],
    projects,
  };
}

async function _saveState(state) {
  const toSet = {
    [KEY.profile]:     state.profile,
    [KEY.preferences]: state.preferences,
    [KEY.workflows]:   state.workflows,
  };
  for (const [name, proj] of Object.entries(state.projects)) {
    toSet[KEY.project(name)] = proj;
  }
  await chrome.storage.local.set(toSet);
}

async function _saveEpisode(episodeId, episode) {
  await chrome.storage.local.set({ [KEY.episode(episodeId)]: episode });
}

// ── Persistent nodes（chrome.storage.local） ──────────────────────────────────

async function _loadPersistentNodes() {
  const data = await chrome.storage.local.get(KEY.persistent_nodes);
  return data[KEY.persistent_nodes] ?? { pn_next_id: 1, episodic_tag_paths: [], nodes: {} };
}

async function _savePersistentNodes(pnData) {
  await chrome.storage.local.set({ [KEY.persistent_nodes]: pnData });
}

async function _updatePersistentNodes(episode, apiKey) {
  const pnData = await _loadPersistentNodes();

  const existingSummary = Object.entries(pnData.nodes).map(([id, n]) => ({
    id, type: n.type, key: n.key, description: n.description,
    confidence: n.confidence, refs: (n.episode_refs ?? []).length,
  }));

  const epSummary = {
    episode_id:          episode.episode_id,
    topic:               episode.topic,
    summary:             episode.summary,
    key_decisions:       episode.key_decisions,
    open_issues:         episode.open_issues,
    relates_to_projects: episode.relates_to_projects,
  };

  const userPrompt =
`【现有 Persistent 节点】
${JSON.stringify(existingSummary, null, 2)}

【新 Episodic 记忆内容】
${JSON.stringify(epSummary, null, 2)}`;

  let result;
  try {
    result = await extractJson(await _getPersistentDistillSystem(), userPrompt, apiKey);
  } catch (err) {
    console.error("[memory_engine] persistent distill failed:", err.message);
    return;
  }

  if (!result || Object.keys(result).length === 0) return;

  _applyPersistentResult(pnData, result, episode.episode_id);
  await _savePersistentNodes(pnData);
  console.log("[memory_engine] persistent nodes updated, episode:", episode.episode_id);
}

function _applyPersistentResult(pnData, result, epId) {
  const now = new Date().toISOString();
  const nodes = pnData.nodes;

  for (const upd of (result.updates || [])) {
    const node = nodes[upd.id];
    if (!node) continue;
    if (epId && !(node.episode_refs ?? []).includes(epId)) {
      node.episode_refs = [...(node.episode_refs ?? []), epId];
    }
    if (upd.description) node.description = upd.description;
    if (upd.confidence)  node.confidence  = upd.confidence;
    node.updated_at = now;
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
  }

  for (const mg of (result.merges || [])) {
    const target = nodes[mg.merged_into];
    if (!target) continue;
    const sources = Array.isArray(mg.merged_from) ? mg.merged_from : [mg.merged_from];
    for (const srcId of sources) {
      const source = nodes[srcId];
      if (!source) continue;
      for (const ref of (source.episode_refs ?? [])) {
        if (!(target.episode_refs ?? []).includes(ref)) {
          target.episode_refs = [...(target.episode_refs ?? []), ref];
        }
      }
      delete nodes[srcId];
    }
    const refCount = (target.episode_refs ?? []).length;
    if (refCount >= 4)      target.confidence = "high";
    else if (refCount >= 2) target.confidence = "medium";
    if (mg.description) target.description = mg.description;
    target.updated_at = now;
  }
}

// ── 应用 delta 中的状态更新（profile / prefs / projects / workflows） ──────────
// 不保存 episode，episode 由 updateMemory 在所有 rounds 处理完后统一生成。

function _applyStateUpdates(delta, episodeId, timestamp, state) {
  // Profile
  if (delta.profile_updates && Object.keys(delta.profile_updates).length > 0) {
    state.profile = { ...state.profile, ...delta.profile_updates };
    state.profile.updated_at = timestamp;
  }

  // Preferences
  if (delta.preference_updates) {
    const pu = delta.preference_updates;
    const p = state.preferences;
    const _toArr = v => Array.isArray(v) ? v : (v ? [String(v)] : []);
    if (pu.add_style?.length)     p.style_preference      = _dedup([..._toArr(p.style_preference), ..._toArr(pu.add_style)]);
    if (pu.add_forbidden?.length) p.forbidden_expressions = _dedup([..._toArr(p.forbidden_expressions), ..._toArr(pu.add_forbidden)]);
    if (pu.update_language)       p.language_preference   = pu.update_language;
    if (pu.update_granularity)    p.response_granularity  = pu.update_granularity;
    p.updated_at = timestamp;
  }

  // Projects
  for (const pu of (delta.project_updates ?? [])) {
    if (!pu.project_name) continue;
    const existing = state.projects[pu.project_name] ?? newProject(pu.project_name);

    if (pu.stage_update)             existing.current_stage       = pu.stage_update;
    if (pu.new_decisions?.length)    existing.finished_decisions   = _appendEntries(existing.finished_decisions, pu.new_decisions, timestamp);
    if (pu.new_questions?.length)    existing.unresolved_questions = _appendEntries(existing.unresolved_questions, pu.new_questions, timestamp);
    if (pu.new_next_actions?.length) existing.next_actions         = _appendEntries(existing.next_actions, pu.new_next_actions, timestamp);
    if (pu.resolved_questions?.length) {
      existing.unresolved_questions = existing.unresolved_questions.filter(
        e => !pu.resolved_questions.includes(e.text)
      );
    }
    if (!existing.source_episode_ids.includes(episodeId)) existing.source_episode_ids.push(episodeId);
    existing.updated_at = timestamp;

    state.projects[pu.project_name] = existing;
  }

  // Workflows
  for (const wu of (delta.workflow_updates ?? [])) {
    if (!wu.workflow_name) continue;
    const idx = state.workflows.findIndex(w => w.workflow_name === wu.workflow_name);
    if (idx >= 0) {
      state.workflows[idx].occurrence_count = (state.workflows[idx].occurrence_count ?? 1) + 1;
      if (wu.steps_update?.length) state.workflows[idx].typical_steps = wu.steps_update;
      state.workflows[idx].updated_at = timestamp;
    } else if (wu.action === "create") {
      const wf = newWorkflow(wu.workflow_name);
      if (wu.steps_update?.length) wf.typical_steps = wu.steps_update;
      state.workflows.push(wf);
    }
  }
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────

function _buildStateSummary(state) {
  const lines = [];

  if (state.profile && Object.keys(state.profile).length > 0) {
    lines.push("## Profile");
    for (const [k, v] of Object.entries(state.profile)) {
      if (v && (Array.isArray(v) ? v.length : true)) lines.push(`- ${k}: ${JSON.stringify(v)}`);
    }
  }

  const p = state.preferences;
  if (p) {
    // Normalise: LLM may have stored array fields as strings; coerce back to arrays
    const toArr = v => Array.isArray(v) ? v : (v ? [String(v)] : []);
    lines.push("## Preferences");
    if (toArr(p.style_preference).length)      lines.push(`- style: ${toArr(p.style_preference).join(", ")}`);
    if (toArr(p.forbidden_expressions).length) lines.push(`- forbidden: ${toArr(p.forbidden_expressions).join(", ")}`);
    if (p.language_preference)                 lines.push(`- language: ${p.language_preference}`);
    if (p.response_granularity)                lines.push(`- granularity: ${p.response_granularity}`);
  }

  for (const [name, proj] of Object.entries(state.projects)) {
    lines.push(`## Project: ${name}`);
    if (proj.current_stage)                lines.push(`- stage: ${proj.current_stage}`);
    if (proj.unresolved_questions?.length) lines.push(`- open: ${proj.unresolved_questions.map(e => e.text).join("; ")}`);
  }

  if (state.workflows?.length) {
    lines.push("## Workflows");
    for (const wf of state.workflows) {
      const steps = wf.typical_steps?.length ? ` [${wf.typical_steps.join(" → ")}]` : "";
      lines.push(`- ${wf.workflow_name} (x${wf.occurrence_count ?? 1})${steps}`);
    }
  }

  return lines.join("\n").slice(0, 4000);
}

async function _getDeltaSystem() {
  return await _loadPromptFile("extract_delta");
}

async function _getPersistentDistillSystem() {
  const arch   = await _loadPromptFile("architecture");
  const distill = await _loadPromptFile("distill_nodes_bg");
  return arch + "\n\n" + distill;
}

function _appendEntries(existing, newTexts, timestamp) {
  const existingSet = new Set((existing ?? []).map(e => e.text));
  const toAdd = newTexts.filter(t => !existingSet.has(t)).map(t => ({ text: t, timestamp }));
  return [...(existing ?? []), ...toAdd];
}

function _dedup(arr) {
  return [...new Set(arr)];
}

// ── Parallel batch processing ──────────────────────────────────────────────────

function _withConcurrency(items, limit, fn) {
  return new Promise(resolve => {
    if (!items.length) { resolve([]); return; }
    const out = new Array(items.length).fill(null);
    let idx = 0, done = 0;
    const n = items.length;
    function next() {
      if (idx >= n) return;
      const i = idx++;
      Promise.resolve().then(() => fn(items[i], i))
        .then(v  => { out[i] = { ok: true,  value: v }; })
        .catch(e => { out[i] = { ok: false, error: e.message }; })
        .finally(() => { if (++done === n) resolve(out); else next(); });
    }
    for (let k = 0; k < Math.min(limit, n); k++) next();
  });
}

/**
 * Process multiple conversations in parallel, then apply results sequentially.
 * Speedup ≈ min(concurrency, n) × vs. sequential.
 * Phase 1: LLM calls in parallel (all see a state snapshot taken at call time).
 * Phase 2: Load fresh state, apply all deltas in order, save state once.
 * Phase 3: Save episodes (fire persistent node updates in background).
 * @param {Array<{ chatData: {platform, url, rounds}, storageKey?: string }>} items
 * @param {string} apiKey
 * @param {{ concurrency?: number, onProgress?: (done: number, total: number) => void }} opts
 * @returns {{ processed: number, skipped: number, succeededIndices: number[] }}
 */
export async function processConversationsBatch(items, apiKey, { concurrency = 4, onProgress } = {}) {
  if (!items.length) return { processed: 0, skipped: 0, succeededIndices: [] };

  const deltaSystem = await _getDeltaSystem();

  // Snapshot current state for context — all parallel calls use the same summary.
  const snapshot = await _loadState();
  const stateSummary = _buildStateSummary(snapshot);

  let fetched = 0;

  // Phase 1: parallel LLM calls
  const rawResults = await _withConcurrency(items, concurrency, async ({ chatData }) => {
    const { platform, rounds } = chatData;
    const allText = rounds.map((r, j) =>
      `[Round ${j + 1}] (${r.timestamp ?? ""})\nUser: ${r.user}\nAssistant: ${r.assistant}`
    ).join("\n\n");

    const userPrompt =
`CURRENT MEMORY STATE:
${stateSummary}

FULL CONVERSATION (${platform}, ${rounds.length} rounds):
${allText}`;

    const delta = await extractJson(deltaSystem, userPrompt, apiKey);
    onProgress?.(++fetched, items.length);
    return delta;
  });

  // Phase 2: re-load state, apply all deltas sequentially, save once
  const state = await _loadState();
  const episodes = [];
  const succeededIndices = [];

  for (let i = 0; i < rawResults.length; i++) {
    const r = rawResults[i];
    if (!r?.ok || !r.value || r.value.is_noise) continue;
    const { chatData } = items[i];
    const delta = r.value;
    const episodeId = crypto.randomUUID().slice(0, 8);
    const firstTimestamp = chatData.rounds[0]?.timestamp;
    const lastTimestamp  = chatData.rounds[chatData.rounds.length - 1]?.timestamp;

    _applyStateUpdates(delta, episodeId, lastTimestamp, state);

    const ed = delta.episode ?? {};
    episodes.push({
      episodeId, platform: chatData.platform, firstTimestamp, lastTimestamp,
      epParts: {
        topics:    ed.topic           ? [ed.topic]           : [],
        summaries: ed.summary         ? [ed.summary]         : [],
        decisions: ed.key_decisions   ?? [],
        issues:    ed.open_issues     ?? [],
        projects:  ed.related_project ? [ed.related_project] : [],
      },
    });
    succeededIndices.push(i);
  }

  if (episodes.length > 0) {
    await _saveState(state);
    for (const ep of episodes) {
      await _buildAndSaveEpisode(ep.episodeId, ep.platform, ep.firstTimestamp, ep.lastTimestamp, ep.epParts, apiKey);
    }
  }

  return { processed: episodes.length, skipped: items.length - episodes.length, succeededIndices };
}
