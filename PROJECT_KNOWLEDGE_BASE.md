# Memory Assistant 项目知识库描述

## 一句话定位

Memory Assistant 是一个面向 AI Agent 时代的个人记忆迁移与持续维护工具。它把用户散落在不同 AI 平台、不同对话和不同项目里的长期信息整理成一个本地、可读、可导出、可注入的标准化知识库，让用户不必每换一个模型或平台就重新介绍自己、自己的项目和自己的工作方式。

## 项目最初想解决的问题

当前 AI 平台通常把记忆能力封闭在各自产品内部：ChatGPT、Gemini、DeepSeek、豆包等平台可能各自保存一部分用户偏好、历史摘要、custom instructions 或 agent 配置，但这些记忆难以迁移，也难以由用户统一审计和维护。

本项目最初的目标可以概括为三点：

1. **冷启动迁移**：当用户从 A 平台切换到 B 平台时，能够把已有历史对话和平台记忆整理成一个可注入的记忆包，帮助新平台快速理解用户。
2. **持续更新**：记忆不是一次性导入后就结束，而是随着用户的新对话、新项目、新偏好变化而动态维护。
3. **标准化管理**：形成一个平台独立、可被行业采纳的记忆存储与管理机制，让用户拥有自己的长期记忆资产，而不是被单一平台绑定。

## 知识库是什么

这里的知识库不是简单的聊天记录归档，而是一个由证据、信号、结构化记忆和规则共同组成的个人长期记忆层。

它既保存原始证据，也保存经过整理后的知识：

- 原始对话、上传文件和导入历史，用来提供可追溯证据。
- 平台原生记忆、custom instructions、agent config 和平台 skills，用来提供已有平台对用户的理解。
- 用户画像、偏好、项目、工作流、episodes、daily notes 和 skills，用来形成可被 AI Agent 直接使用的结构化上下文。
- schema、冲突处理、升级和隐私规则，用来决定哪些信息值得长期保存、如何合并、何时需要用户确认。

因此，Memory Assistant 的知识库更接近一个“本地个人记忆 wiki”：Markdown 面向人类阅读，JSON 面向程序调用，导出包面向跨平台迁移。

## 四层记忆架构

项目目前采用 L0-L3 的四层模型。

### L0 Raw Evidence：原始证据层

L0 保存最底层、最接近事实来源的数据，包括：

- 从 AI 平台采集的原始聊天记录。
- 用户手动导入的 `json`、`jsonl`、`md`、`txt` 历史文件。
- 对话中的消息、轮次、时间戳、平台和 conversation id。

L0 的价值是可追溯。后续所有结构化记忆都应该能回到原始对话或文件中找到依据。

### L1 Platform Signals：平台信号层

L1 保存平台已经加工过的记忆信号，核心是平台侧的 saved memory。这里的 saved memory 不只指单条记忆列表，也包括平台已经为用户或 Agent 维护过的上下文资产，例如：

- conversation summary。
- profile 和 preferences。
- custom instructions。
- agent config。
- platform skills。

L1 不是绝对权威来源，而是“已有平台怎么理解用户”的参考。它能帮助冷启动更快，也能和 L0 原始证据互相校验。

### L2 Managed Wiki：项目托管记忆层

L2 是项目真正维护和导出的核心知识库。它不是直接把 L0 和 L1 的内容简单分类存放，而是先从 L0 原始对话中提取 episode，再从 episodes 中进一步沉淀出更稳定的 persistent memory。

L2 的第一步是 `episodes/`。episode 的最小语义单元是一轮对话 turn：一个完整 conversation 里可能包含多轮用户与助手交互，每一轮都可以形成一个独立 episode。为了避免文件过碎或单条内容过长，当前实现会按 conversation 聚合存储：`episodes/<conversation_id>.json` 中包含该 conversation 下的多个 turn-level episodes。

每个 episode 通常包含：

- `episode_id`：轮次级记忆的唯一标识。
- summary：这一轮对话发生了什么、完成了什么、做出了什么决定。
- keywords：这一轮中的关键词，用来辅助同轮内容聚合和检索。
- connections：与其他 episodes、项目、偏好或 persistent nodes 的连接关系。
- source refs：回到原始 conversation、turn 或 message 的证据引用。

episode 的连接需要分层处理：同一轮对话内部可以更多依赖 keywords 建立关联；跨轮或跨 conversation 的连接要更谨慎，通常需要基于 summary、语义相似度和上下文证据来判断，避免把只是表面相似的内容误连在一起。

在 episodes 之上，L2 会进一步提取和维护更稳定的 persistent memory：

- `profile/`：用户画像，偏 high-level，例如身份、背景、长期关注方向、常用语言。
- `preferences/`：偏好设置，偏关键词和规则化，例如表达风格、术语偏好、格式约束、禁用表达、语言偏好。
- `projects/`：项目型长期记忆，记录用户正在推进或长期维护的项目、阶段、目标、关键上下文和状态。
- `workflows/`：工作流 / SOP，记录用户反复使用的方法和标准流程；它可以组织、调用已经发现或保存的 skills，形成更可执行的任务流程。
- `daily_notes/`：非项目类 persistent memory，例如生活偏好、选择习惯、日常上下文和其他可复用的个人长期信息。
- `skills/`：可复用能力资产，既可以是用户手动保存的 Skill，也可以是系统推荐的 Skill，还可以来自系统发现用户频繁复用的能力模式。
- `metadata/` 和 `logs/`：索引、整理状态、展示文案和变更记录。

因此，L2 的核心不是一个静态目录列表，而是一个从 episodes 到 persistent memory 的沉淀过程：L0 原始对话先进入 L2 的 turn-level episodes，episodes 再经过 L3 规则治理，生成同样属于 L2 的 profile/preferences/projects/workflows/daily_notes/skills。episodes 保留具体语境和证据，persistent memory 则把多轮对话中反复出现、稳定可用的信息升级为长期记忆。L2 的存储同时服务人和程序：Markdown 供用户检查和编辑，JSON 供程序稳定调用。

### L3 Schema & Policy：规则、连接与评测层

L3 不是新的事实存储层，也不是 persistent memory 的存放位置。它是治理规则层，作用在 `L2 episodes -> L2 persistent memory` 的转化过程中，决定 episodes 如何被抽取、连接、分组、升级、检索和评测。

L3 至少包含几类策略：

- 抽取与升级策略：判断哪些 episode 信息值得进入 profile、preferences、projects、workflows、daily_notes 或 skills。
- 冲突与确认策略：处理新旧记忆冲突、高影响字段变更、敏感信息和临时信息。
- episode connection 策略：决定 episodes 之间是否应该连接、连接类型是什么、置信度是否足够。
- connected group 策略：控制多个 episodes 形成 group 时的边界，避免弱相关内容被无限串联。
- retrieval/index 策略：决定什么时候使用 keywords、metadata、summary 或向量索引来加速检索和聚合。
- benchmark/evaluation 策略：定义在 LongMemEval 等评测场景下如何构建检索索引、如何回答问题、如何比较不同 memory setting。

episode connection 需要特别谨慎。A 可以连到 B，B 可以连到 C，并不意味着 A 一定应该连到 C；即使 A、B、C 可以形成一个 group，也不代表这个 group 可以继续无约束地扩展到 D、E、F。L3 需要控制连接的双向验证、最大跳数、group 大小、边置信度和冗余边裁剪，避免所有项目、偏好和日常记忆因为少量相似关键词被连成一个过大的团。

ChromaDB 在当前项目里更适合作为检索索引和 benchmark setting，而不是 canonical memory store。知识库的权威来源仍然是 L2 的 JSON/Markdown 文件；ChromaDB 中保存的是从 L0/L2 派生出来的 chunks、embeddings、keywords、summary 和 metadata，用来支持 LongMemEval 等 benchmark 中的语义检索实验、大规模 episodes 或 raw evidence 的快速候选召回、基于 summary/keywords/metadata 的聚合加速，以及需要 top-k evidence 的问答或验证流程。

因此，是否使用 ChromaDB 应该由 L3 的 retrieval/index policy 决定。默认产品知识库不依赖 ChromaDB 才能成立；只有在评测、语义检索、证据召回或大规模聚合加速场景下，才把 ChromaDB 作为派生索引使用。

## 核心用户流程

### 场景一：冷启动迁移

用户在一个源平台上积累了大量历史对话和平台记忆，希望迁移到另一个目标平台。Memory Assistant 会：

1. 采集或导入源平台历史对话。
2. 采集源平台已有的 memory、custom instructions、agent config 和 skills。
3. 运行整理流程，把原始材料重建为 profile、preferences、projects、workflows、episodes 和 daily notes。
4. 让用户选择要迁移的记忆条目。
5. 导出或直接注入到目标平台当前会话中，形成一个个性化冷启动包。

### 场景二：持续记忆维护

用户继续在不同 AI 平台上工作时，插件可以捕获新对话，并通过增量更新流程维护知识库：

1. content script 识别支持的 AI 页面并捕获新对话轮次。
2. background 或 backend 调用增量记忆 prompt。
3. 新信息被更新到相关 profile、preferences、projects、workflows 或 persistent nodes 中。
4. 系统根据 L3 规则处理重复、冲突、临时信息和敏感信息。

### 场景三：选择性导出与冻结

用户导入或整理记忆后，可以在迁移页面选择部分内容导出。被“冻结”的内容不会在目标平台临时可见，但仍保留在本地知识库中，方便用户控制迁移范围和隐私边界。

### 场景四：Skill 化沉淀

当某些工作流、输出规范或项目习惯变得稳定时，它们可以被进一步沉淀为 Skill。Skill 是比普通记忆更可执行的资产，适合在特定任务中被注入或复用。

## 当前工程实现

项目由三部分协作：

- Chrome 插件：负责 UI、页面采集、平台记忆采集、导出注入入口和同步控制。
- 本地 FastAPI 后端：负责设置、文件存储、整理任务、平台记忆导入、导出包、注入包和 Skill 管理。
- `llm_memory_transferor` Python pipeline：负责 L0-L3 模型、记忆构建、增量更新、wiki 持久化和评测。

主要运行路径是：

```text
AI 平台页面 / 本地导入文件
  -> Chrome 插件采集或上传
  -> backend_service 本地存储
  -> MemoryBuilder / MemoryUpdater 整理
  -> L2 wiki + daily_notes + skills
  -> 导出包或注入 prompt
```

## 知识库目录语义

当用户配置了本地存储目录时，后端会把知识库写入该目录；否则默认写入 `backend_service/.state/wiki/`。

推荐理解方式：

- `raw/` 是证据仓库，不直接代表长期结论。
- `platform_memory/` 是外部平台给出的参考信号。
- `episodes/` 是事件和上下文轨迹。
- `profile/`、`preferences/`、`projects/`、`workflows/` 是稳定结构化记忆。
- `daily_notes/` 是从 episodes 中蒸馏出的可复用、非项目类长期节点。
- `skills/` 是可被复用或注入的能力资产。
- `metadata/` 是系统运行需要的索引和状态。

旧版本中的 `interest_discoveries/` 已被 `daily_notes/` 取代，但后端仍保留读取兼容。

## 设计原则

1. **用户拥有记忆**：记忆首先属于用户，应该能被导出、查看、编辑和迁移。
2. **证据优先**：结构化记忆必须尽量来自可追溯的原始对话或平台信号。
3. **平台中立**：知识库不绑定某一个 AI 产品，而是服务于跨平台 Agent 使用。
4. **人机双读**：Markdown 让用户能读，JSON 让程序能稳定使用。
5. **可选择迁移**：用户可以选择导出哪些记忆，而不是一次性暴露全部上下文。
6. **持续维护**：长期记忆要能随着新对话更新，也要能处理过期、冲突和误提取。
7. **从记忆到能力**：高频、稳定、可执行的记忆最终可以沉淀为 Skill。

## 项目下一步可以完善的方向

- 完善产品方案文档，把冷启动、持续更新、冻结/筛选、Skill 化等流程画成更明确的用户旅程。
- 加强 L3 策略，让冲突处理、敏感信息处理和用户确认机制更可见。
- 提供知识库可视化浏览和手动编辑能力，让用户能直接管理自己的长期记忆。
- 建立更清晰的跨平台导出格式，降低不同 AI 平台之间的记忆注入成本。
- 将稳定的工作流自动推荐为 Skill，形成从“历史经验”到“可复用工具”的闭环。
