// Memory Engine — 增量记忆更新
// 存储层使用 chrome.storage.local（Service Worker 可访问）
// 数据格式与 Python L2Wiki 兼容，popup.js 打开时会自动同步到文件系统

import { extractJson } from "./llm_client.js";
import { newProfile, newPreferences, newProject, newWorkflow, newEpisode } from "./l2_wiki.js";

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
// 每次对话最多处理的轮数。超过时取最后 MAX_ROUNDS_PER_CONV 轮，
// 避免极长对话导致 Service Worker 超时（Chrome MV3 限制 ~5 分钟）。
const MAX_ROUNDS_PER_CONV = 20;

export async function updateMemory(chatData, apiKey) {
  const { platform, rounds: rawRounds } = chatData;
  if (rawRounds.length === 0) return;

  // 超长对话截取最后 N 轮（最近的对话对记忆更新价值最高）
  const rounds = rawRounds.length > MAX_ROUNDS_PER_CONV
    ? rawRounds.slice(-MAX_ROUNDS_PER_CONV)
    : rawRounds;

  const state = await _loadState();
  const episodeId = crypto.randomUUID().slice(0, 8);
  const firstTimestamp = rounds[0].timestamp;
  const lastTimestamp  = rounds[rounds.length - 1].timestamp;

  // 汇总所有 rounds 的 episode 内容，最终生成一个 episode
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
      delta = await extractJson(_getDeltaSystem(), userPrompt, apiKey);
    } catch (err) {
      console.error("[memory_engine] LLM call failed:", err.message);
      continue;
    }
    if (!delta || delta.is_noise) continue;
    hasContent = true;

    // 每轮独立更新 profile / prefs / projects / workflows
    _applyStateUpdates(delta, episodeId, round.timestamp, platform, state);

    // 累积 episode 内容
    const ed = delta.episode ?? {};
    if (ed.topic)   epParts.topics.push(ed.topic);
    if (ed.summary) epParts.summaries.push(ed.summary);
    epParts.decisions.push(...(ed.key_decisions    ?? []));
    epParts.issues.push(...(ed.open_issues         ?? []));
    if (ed.related_project) epParts.projects.push(ed.related_project);
  }

  if (!hasContent) return;

  // 状态只保存一次
  await _saveState(state);

  // 整批对话生成一个 episode
  const ep = newEpisode();
  ep.episode_id          = episodeId;
  ep.platform            = platform ?? "unknown";
  ep.topic               = epParts.topics[0] ?? "";
  ep.summary             = epParts.summaries.join(" | ");
  ep.key_decisions       = [...new Set(epParts.decisions)];
  ep.open_issues         = [...new Set(epParts.issues)];
  ep.relates_to_projects = [...new Set(epParts.projects)];
  ep.time_range_start    = firstTimestamp;
  ep.time_range_end      = lastTimestamp;
  ep.created_at          = firstTimestamp;
  ep.updated_at          = lastTimestamp;

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
    result = await extractJson(_getPersistentDistillSystem(), userPrompt, apiKey);
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

function _applyStateUpdates(delta, episodeId, timestamp, platform, state) {
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

  return lines.join("\n").slice(0, 4000);
}

function _getDeltaSystem() {
  return `You are a memory delta specialist. Given a new conversation and the current memory state,
identify ONLY what should be updated in the memory. Do NOT repeat already-known information.
Output ONLY valid JSON with this structure:
{
  "is_noise": false,
  "profile_updates": {},
  "preference_updates": {
    "add_style": [],
    "add_forbidden": [],
    "update_language": "",
    "update_granularity": ""
  },
  "project_updates": [
    {
      "project_name": "",
      "action": "update|create",
      "stage_update": "",
      "new_decisions": [],
      "new_questions": [],
      "resolved_questions": [],
      "new_next_actions": []
    }
  ],
  "workflow_updates": [
    {
      "workflow_name": "",
      "action": "confirm|create",
      "steps_update": []
    }
  ],
  "episode": {
    "topic": "",
    "summary": "",
    "key_decisions": [],
    "open_issues": [],
    "related_project": ""
  }
}
Rules:
- profile_updates: only fields that changed or are newly confirmed.
- preference_updates: only newly expressed preferences.
- is_noise: true if the conversation has no memory-worthy content.
- Be conservative: when in doubt, mark as noise.`;
}

function _getPersistentDistillSystem() {
  return `# 可迁移个人记忆层 — 架构定义 v1.0

## 核心概念

本系统将个人记忆分为两层：

### Episodic（情节记忆）
单次对话的完整导出，保留具体的对话细节、时间背景和上下文。
- 不进行跨会话归纳，只描述"本次对话发生了什么"
- 作为 Persistent 层的原始证据来源

### Persistent（持久记忆）
从多条 Episodic 中提炼的跨会话稳定规律。
- 代表用户的长期稳定特征，而非某次对话的具体内容
- 有置信度（confidence）和证据链（episode_refs）
- 每条 persistent 有唯一 ID，格式：pn_XXXX

## Persistent 节点 Schema

\`\`\`json
{
  "type":            "preference | profile | workflow | topic | platform",
  "key":             "snake_case，全局唯一",
  "description":     "一句中文规律描述，≤30字",
  "episode_refs":    ["ep_0001"],
  "confidence":      "low | medium | high",
  "export_priority": "low | medium | high"
}
\`\`\`

## Confidence 规则

| episode_refs 数量 | confidence |
|-------------------|------------|
| 1 条              | low        |
| 2–3 条            | medium     |
| ≥4 条             | high       |

## 你的角色：Persistent 层维护引擎

审视新增的 Episodic 记忆，更新或新建 Persistent 节点，并在发现语义重合时主动合并。

**updates**（现有节点被新 episodic 支撑时）
- 将此 episodic ID 加入 episode_refs
- 若 episode_refs 数量达到升级条件，更新 confidence
- 若无新贡献，不要出现在 updates 中

**new_nodes**（需要新建时）
- 只对有明确证据的规律建节点，不推断
- 单条 episodic 新建的节点 confidence 必须为 low
- key 全局唯一，snake_case

**merges**（节点合并）
- 语义重复的节点应合并
- topic 节点应建在课程/项目粒度，不为单个知识点建节点

**输出格式（只返回合法 JSON）**

{
  "updates": [{"id": "pn_XXXX", "add_ref": true, "description": "可选", "confidence": "可选"}],
  "new_nodes": [{"type": "...", "key": "...", "description": "...", "confidence": "low", "export_priority": "medium"}],
  "merges": [{"merged_into": "pn_XXXX", "merged_from": "pn_YYYY", "description": "可选"}]
}`;
}

function _appendEntries(existing, newTexts, timestamp) {
  const existingSet = new Set((existing ?? []).map(e => e.text));
  const toAdd = newTexts.filter(t => !existingSet.has(t)).map(t => ({ text: t, timestamp }));
  return [...(existing ?? []), ...toAdd];
}

function _dedup(arr) {
  return [...new Set(arr)];
}
