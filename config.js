// 全局配置，popup.js / content.js 通过 <script> 或 manifest 引入后直接使用 CONFIG
const CONFIG = {

  // ── DeepSeek API ────────────────────────────────────────────────────────────
  deepseek: {
    endpoint: "https://api.deepseek.com/v1/chat/completions",
    model:    "deepseek-chat",
  },

  // ── Skills ──────────────────────────────────────────────────────────────────
  //
  // 三个 skill 的关系：
  //
  //   architecture        ← 共享的两层定义，两个 AI 都需要理解
  //       ├── episodicTag      ← 目标AI的任务（导出 + episodic 打标）
  //       └── persistentDistill ← DeepSeek 的任务（审视 episodic → 维护 persistent）
  //
  // 使用方式（由 popup.js 拼装）：
  //   目标AI prompt   = architecture + episodicTag（其中 {{EXISTING_TAGS}} 替换为当前标签列表）
  //   DeepSeek system = architecture + persistentDistill
  //   DeepSeek user   = 具体任务（现有节点 + 新 episodic 内容）
  //
  skills: {

    // ── 架构定义（两个 AI 共用）──────────────────────────────────────────────
    architecture: `\
# 可迁移个人记忆层 — 架构定义 v1.0

## 核心概念

本系统将个人记忆分为两层：

### Episodic（情节记忆）
单次对话的完整导出，保留具体的对话细节、时间背景和上下文。
- 不进行跨会话归纳，只描述"本次对话发生了什么"
- 作为 Persistent 层的原始证据来源
- 每条 episodic 有唯一 ID，格式：ep_XXXX

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
  "episode_refs":    ["ep_0001", "ep_0002"],
  "confidence":      "low | medium | high",
  "export_priority": "low | medium | high"
}
\`\`\`

## Type 说明

| type       | 含义                                |
|------------|-------------------------------------|
| preference | 用户稳定的偏好与约束（格式/风格/禁止项）|
| profile    | 用户身份与背景（角色/领域/技能）        |
| workflow   | 用户反复使用的工作流程或操作模式        |
| topic      | 涉及的主题/项目/任务类型               |
| platform   | 来源平台                             |

## Confidence 规则

| episode_refs 数量 | confidence |
|-------------------|------------|
| 1 条              | low        |
| 2–3 条            | medium     |
| ≥4 条             | high       |

confidence 必须随 episode_refs 增长而升级，不能手动越级设为 high。

## Description 质量标准

✓ 正确（规律描述）："用户写作时不使用破折号"
✗ 错误（事件描述）："用户在4月修改论文时提到不用破折号"

description 描述规律本身，而非触发该规律的具体事件。`,

    // ── 目标AI的任务：导出记忆 + 打 Episodic 标签 ───────────────────────────
    //
    // popup.js 使用前替换 {{EXISTING_TAGS}}
    // 注意：不要把 architecture 拼到这个 prompt 前面，
    //       目标AI只需要知道如何提取和标注，不需要理解两层架构。
    //
    episodicTag: `\
# Role: 可迁移个人记忆层提取引擎

## 任务
请基于我们本次对话的全部内容，提取结构化记忆，并在 JSON 末尾追加 "__episodic_tags__" 标签字段。

## 记忆提取规则

### 1. conversation_summary（本次对话详细总结）⭐ 重点字段
对本次对话做完整、详细的叙述性总结，作为日后回溯的原始证据。要求：
- 覆盖对话的完整过程：背景、问题、讨论过程、结论
- 有特定文件路径、URL、代码片段的，逐一列出
- 涉及数学公式的，给出未渲染的 LaTeX 源码（不要渲染效果）
- 有待解决问题或未完成事项的，明确列出
- 不做省略或概括，尽可能保留具体细节
- 格式：自由叙述文本（string），允许换行

### 2. user_profile（用户画像）
提取用户的稳定背景信息：
- name_or_alias
- role_identity（如：研究生、工程师、教授）
- domain_background（如：计算机视觉、机器学习、离散数学）
- common_languages
- primary_task_types

### 3. preferences（偏好与约束）
提取对输出风格、术语、排版的稳定偏好：
- style_preference
- terminology_preference
- formatting_constraints（如：公式必须提供未渲染的 LaTeX 源码）
- forbidden_expressions（如：不使用破折号）

### 4. active_projects（活跃项目）
提取当前有进展的长期项目，需有对话内容作为支撑：
- project_name
- project_goal
- current_stage
- key_terms
- finished_decisions
- unresolved_questions
- evidence_links

### 5. key_workflows（工作流程）
提取在对话中反复出现的任务模式或操作流程：
- workflow_name
- trigger_condition
- typical_steps
- preferred_artifact_format

## 现有标签（优先复用，避免重复建标）
{{EXISTING_TAGS}}

## 输出格式（只返回合法 JSON，不包含任何解释）

{
  "manifest": {
    "version": "1.0",
    "generated_from_platform": "Platform {Your name}"
  },
  "conversation_summary": "对本次对话的完整详细叙述，包含所有具体细节、文件路径、代码、公式（LaTeX 源码）、待解决问题等",
  "user_profile": { ... },
  "preferences": { ... },
  "active_projects": [ ... ],
  "key_workflows": [ ... ],
  "__episodic_tags__": {
    "use_existing": ["已有标签路径1", "已有标签路径2"],
    "new_tags": [{ "path": "维度.中文描述", "label": "显示名" }]
  }
}

## 标签规则
- 路径格式：维度.中文描述（如 preference.不用破折号、topic.ICLR2026投稿）
- 维度只能是：preference / profile / workflow / topic / platform
- 优先复用已有标签；确实没有对应标签时才新建
- 标签只反映本次对话涉及的维度，不做跨会话归纳
- 标签数量 3–8 个`,

    // ── DeepSeek 的任务：维护 Persistent 节点库 ─────────────────────────────
    //
    // 作为 DeepSeek API 的 system 消息（与 architecture 拼接后使用）
    //
    persistentDistill: `\
## 你在本系统中的角色：Persistent 层维护引擎

你的任务是审视新增的 Episodic 记忆，更新或新建 Persistent 节点，并在发现语义重合时主动合并。

### 操作规则

**updates**（现有节点被新 episodic 支撑时）
- 将此 episodic ID 加入 episode_refs
- 若 episode_refs 数量达到升级条件，更新 confidence
- 若 description 有明显改善空间，可以更新
- 若无新贡献，不要出现在 updates 中

**new_nodes**（需要新建时）
- 只对有明确证据的规律建节点，不推断
- 新建前确认与现有节点无语义重复
- 单条 episodic 新建的节点 confidence 必须为 low
- key 全局唯一，snake_case

**merges**（节点合并/聚合）
- merged_into：保留的节点 ID（优先选 confidence 更高或 episode_refs 更多的那个）
- merged_from：被删除的节点 ID 或 ID 数组（其全部 episode_refs 追加到 merged_into）
- description（可选）：合并后改进的规律描述，应覆盖被合并节点的含义
- 两种合并情形均需处理：
  1. **语义重复**：两个节点描述几乎相同的规律 → 直接合并
  2. **子话题聚合**（尤其是 topic 类型）：多个节点是同一课程/项目/领域的具体子话题 → 合并为一个领域级节点，description 改写为概括性描述（如"用户学习离散数学，涉及良序原理、容斥原理等多个主题"）
- 如无需合并，merges 留空数组即可

**topic 节点粒度规则**
- topic 节点应建在**课程/项目/研究方向**粒度，例如"离散数学"、"ICLR2026投稿"、"代码调试实践"
- 不要为课程内每个知识点单独建 topic 节点（错误示例："良序原理"、"容斥原理"各建一条）
- 若新 episodic 涉及某课程的多个知识点，应更新/新建该课程的 topic 节点并在 description 中注明，而非为每个知识点新建节点

**不做的事**
- 不替代 episodic 打标（那是目标AI的工作）
- 不因单条 episodic 就建 medium/high confidence 节点

### 输出格式（只返回合法 JSON）

{
  "updates": [
    {
      "id":          "pn_XXXX",
      "add_ref":     true,
      "description": "可选：更新后的规律描述",
      "confidence":  "可选：升级后的置信度"
    }
  ],
  "new_nodes": [
    {
      "type":            "preference | profile | workflow | topic | platform",
      "key":             "snake_case_key",
      "description":     "一句中文，≤30字",
      "confidence":      "low",
      "export_priority": "low | medium | high"
    }
  ],
  "merges": [
    {
      "merged_into":  "pn_XXXX",
      "merged_from":  "pn_YYYY 或 [\"pn_YYYY\", \"pn_ZZZZ\"]",
      "description":  "可选：合并后的改进描述（应概括所有被合并节点的含义）"
    }
  ]
}`,

  }, // end skills

  // ── 导入冷启动指令（注入给目标 AI，加载记忆包） ─────────────────────────────
  load: `# Role: 专属个性化 AI 助手 (Personalized AI Assistant)

## Context
你好！我是你的用户。我已将过去在其他 AI 平台沉淀的个人记忆包提取出来，请完整读取并装载，完成无缝冷启动。

## 记忆包结构说明
文件包含两层数据，请分别处理：

**persistent_nodes（持久记忆）**
从多次对话中提炼的稳定规律，confidence 越高越可信。
这是你需要立即内化并在后续交互中严格遵守的核心约束。

**episodic_evidence（情节记忆）**
支撑上述规律的原始对话导出，包含具体项目细节、决策记录、未解决问题等。
请结合这些原文理解规律的来源和适用场景，并接续项目进度。

## 装载准则

1. **偏好与约束（preference 类节点）**：无条件遵守，特别是格式约束（如公式必须给 LaTeX 源码）和禁止表达
2. **用户画像（profile 类节点）**：理解我的专业背景和角色，匹配专业深度，不做不必要的科普
3. **工作流（workflow 类节点）**：当我的指令触发对应工作流时，自动按其步骤和格式输出
4. **项目接续（episodic_evidence 中的 active_projects）**：直接使用约定术语，接续已有决策，不从零解释

## 首次回复要求
1. 确认已成功加载记忆包，说明读取到了几个 persistent 节点、几条 episodic 记录
2. 简述你理解的我的核心方向和当前最关键的活跃项目（来自 episodic 原文）
3. 确认已知晓关键格式偏好（如 LaTeX 源码要求）
4. 询问今天从哪个未解决问题开始推进
注意：简练专业，不要复述所有 JSON 细节。`,

}; // end CONFIG
