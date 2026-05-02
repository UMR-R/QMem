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

## 当前工程实现与重构方向

项目当前处在从旧实现迁移到新主路径的阶段。旧的 `llm_memory_transferor/` 仍然存在，`backend_service/` 和 `popup/` 里也还有大量现有功能；新的主路径已经开始落在 `memory_transferor/`，后续重构应该优先围绕这套目录继续推进。

新的目标结构是：

```text
memory_assistant/
├── prompts/
├── popup/
├── content/
├── background/
├── backend_service/
└── memory_transferor/
    ├── runtime/
    ├── memory_models/
    ├── memory_store/
    ├── memory_builders/
    ├── memory_policy/
    ├── episode_graph/
    ├── prompt_loader/
    ├── external_memory_index/
    └── memory_export/
```

各目录的定位如下：

- `runtime/`：运行时基础设施，包括 LLM client、时间工具和错误类型。
- `memory_models/`：只定义数据结构，包括 raw、platform memory、episode、persistent、profile、preference、project、workflow、daily_note、skill 等模型。
- `memory_store/`：权威本地 JSON/Markdown 存储层，负责读写 canonical memory storage。
- `memory_builders/`：从 raw / platform signals / episodes 生成 higher-level memory 的构建器。
- `memory_policy/`：L3 规则层，负责抽取、升级、冲突、隐私、时间关系和类型边界等确定性策略。
- `episode_graph/`：episode connection 和 grouping 层，负责跨 turn、跨 conversation 的连接、分组和错链验证。
- `prompt_loader/`：prompt 加载与渲染逻辑；prompt 文本仍保留在根目录 `prompts/`。
- `external_memory_index/`：外部数据库索引层，例如 ChromaDB、BM25、SQLite FTS 或 hybrid retrieval。它只从 canonical storage 派生，不保存权威记忆。
- `memory_export/`：前端展示 payload、导出包、注入 prompt 和目标平台映射。展示 payload 是从 persistent memory 派生出来的视图，不是新的权威存储；Profile / Preferences 先聚合成高层 checkbox 关键词，细粒度规则放入详情或 tooltip，Projects / Workflows / Daily Notes / Skills 则展示为短语加简要说明。具体 display taxonomy 不应在代码中写死领域 family，而应来自 policy、LLM 聚类归纳或用户在前端保存的编辑状态。

目前已经初步落地的是 `memory_transferor/` 的骨架，以及 `RawChatSession` / `RawChatTurn`、turn-level `Episode`、第一版 `PersistentMemoryItem`、基础 store、基础 builder 和 `external_memory_index/documents.py`。这证明新主路径可以跑通最小样本中的 `raw -> episodes -> persistent` 流程，但还没有完全替换旧 pipeline。

## Canonical Workspace 目录语义

后续本地知识库应按下面的 workspace 语义理解：

```text
memory_root/
├── raw/
├── platform_memory/
├── episodes/
├── profile/
├── preferences/
├── projects/
├── workflows/
├── daily_notes/
├── skills/
├── metadata/
└── logs/
```

- `raw/`：L0 原始证据仓库，保存 `RawChatSession` 和 `RawChatTurn`，不直接代表长期结论。
- `platform_memory/`：L1 平台信号，包括 saved memory、custom instructions、agent config、platform skills 等。
- `episodes/`：L2 turn-level episodic memory。每个 episode 对应一个 raw turn；一个 conversation 文件可以包含多个 episodes。
- `profile/`：L2 persistent 用户画像，例如身份、背景、长期方向、常用语言和 durable communication context。
- `preferences/`：L2 persistent 偏好规则，例如表达风格、术语偏好、格式约束、禁用表达、语言偏好。
- `projects/`：L2 persistent 项目记忆，例如长期项目、当前阶段、目标、关键上下文、决策、未解决问题和 next actions。
- `workflows/`：L2 persistent 工作流 / SOP，记录可复用步骤，并且后续可以引用 `skills/`。
- `daily_notes/`：L2 persistent 非项目类长期记忆，例如生活偏好、选择习惯、日常上下文和可复用小事实。
- `skills/`：L2 persistent Skill 资产，包括用户保存的 Skill、平台 Skill、推荐后被保存的 Skill，以及从高频工作模式中沉淀的 Skill。
- `metadata/`：索引、整理状态、展示文案、连接状态和派生信息。
- `logs/`：变更记录、整理日志和调试记录。

旧版本中的 `interest_discoveries/` 已被 `daily_notes/` 的设计取代；现有后端仍可能保留读取兼容，但新主路径不应继续把它作为核心目录。

## 暂不处理的范围

按照当前重构节奏，下面两块先不作为下一步工作重点：

- **ChromaDB / external memory index 实现**：当前只保留 `external_memory_index/` 的派生索引定位和 documents 雏形。还不急着把 `RawChatTurn`、`Episode` 或 persistent memory 真正写入 ChromaDB。
- **`llm_memory_transferor/eval/` 评测体系**：main 合进来的 LongMemEval / ChromaDB runner 逻辑暂时保留，不在当前阶段重构。后续需要等 canonical storage、episode graph 和 memory policy 更稳定之后，再把 eval 改成“我们的存储格式 + 外部派生索引”的评测路径。

也就是说，当前产品知识库的权威来源仍然是本地 JSON/Markdown canonical storage；ChromaDB 和 eval 之后再接。

## 设计原则

1. **用户拥有记忆**：记忆首先属于用户，应该能被导出、查看、编辑和迁移。
2. **证据优先**：结构化记忆必须尽量来自可追溯的原始对话或平台信号。
3. **平台中立**：知识库不绑定某一个 AI 产品，而是服务于跨平台 Agent 使用。
4. **人机双读**：Markdown 让用户能读，JSON 让程序能稳定使用。
5. **可选择迁移**：用户可以选择导出哪些记忆，而不是一次性暴露全部上下文。
6. **持续维护**：长期记忆要能随着新对话更新，也要能处理过期、冲突和误提取。
7. **从记忆到能力**：高频、稳定、可执行的记忆最终可以沉淀为 Skill。

## 当前完成状态

已经完成或初步完成：

- 新建 `memory_transferor/` 主路径骨架。
- 实现 `RawChatSession` / `RawChatTurn`，确认 turn 是最小 raw evidence 单元，只保留一个 timestamp。
- 实现第一版 turn-level episode builder 和 persistent builder。
- 实现基础 `memory_store/`，可把 raw、episodes、profile、preferences、projects、workflows、daily_notes、skills 分目录落盘。
- 实现第一版 `episode_graph/`，可生成 conversation context connection、semantic connection 和受限制的 connection groups。
- 实现第一版 `memory_policy/`，对 persistent memory 做类型边界、拆分、置信度和导出优先级后处理。
- 实现第一版 `memory_export/display.py`，可把 persistent memory 转成前端展示 payload，并支持由外部 taxonomy hint 控制高层关键词分组。
- 整理 prompt：统一语言策略、时间规则、类型边界，去掉明显 hard-coded special case。
- 明确 `external_memory_index/` 是派生索引，不是权威存储。
- 用最小样本跑通过 `raw -> episodes -> persistent` 流程。

尚未完成：

- 旧的 `llm_memory_transferor/`、`backend_service/` 和 `popup/` 还没有全面迁移到新结构。
- `platform_memory/` 的新主路径 store 和 L1 ingestion 还没有完整落地。
- `skills/` 虽然已纳入 persistent 设计，但“推荐 Skill -> 用户保存 -> persistent skills -> workflow 调用 skills”的链路还没接上新主路径。
- `memory_policy/` 和 `episode_graph/` 还只是第一版，需要更多测试样本和前端 review 后继续收敛。
- `memory_export/display.py` 尚未接入正式 backend / popup UI，只在 sample runner 和本地验证中可用。

## 下一步优先级

下一步优先把 **episode_graph + memory_policy + display payload** 接到更真实的样本和前端 review 流程中，暂时不碰 eval 和 ChromaDB。

### P0：episode_graph

目标是让 episode 先形成可信 connection group，再把 group 分发给不同 persistent memory 类型，而不是先由 profile/preferences/projects/workflows 分别抽取后再补连接。

需要实现：

- 统一的 episode connection 数据结构和操作 API。
- 同 conversation 内相邻 turn 的 conversation-context connection。
- 跨 conversation 的 semantic connection，但必须有双向验证。
- connected group 生成逻辑。
- 最大跳数、最大 group size、弱边裁剪、冗余边裁剪。
- 防止 A 连 B、B 连 C、C 连 D 后，一条错链导致整个项目记忆走样。

### P0：memory_policy

目标是把 prompt 里不稳定的判断迁移到可测试、可复用的确定性规则中。

需要实现：

- extraction policy：判断 episode 是否值得进入长期记忆。
- upgrade policy：判断 episode group 何时升级为 persistent memory。
- temporal policy：处理 current / previous / before / after / latest / old 等时间关系。
- type boundary policy：稳定区分 profile、preference、topic/project、workflow、daily_note、skill。
- split / merge policy：确定性处理 topic 拆分、workflow final check 拆分、重复节点合并。

这两个模块完成后，再继续考虑：

- L1 platform memory store 和 ingestion。
- skills persistent 主路径和 workflow-skill linker。
- backend / popup 服务层拆分。
- external_memory_index / ChromaDB 接入。
- LongMemEval / eval 路径重构。
