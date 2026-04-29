# 主路径重构规划

## 目标

这次重构的目标不是先改 LongMemEval 评测脚本，而是把项目主路径的命名、层次和职责整理清楚。后续所有功能都应该能围绕同一套 canonical memory storage 运转，再从这套存储派生外部索引、导出包和注入内容。

核心原则：

- `memory_transferor` 是通用记忆核心，不再使用 `llm_memory_transferor` 这个名字。
- 本地 JSON/Markdown 记忆目录是 canonical memory storage。
- ChromaDB 属于外部数据库派生索引，不是权威存储。
- Skills 是 persistent memory 的一部分；推荐 Skill 被用户保存后也属于 persistent memory。
- Workflow 可以引用 Skills，也可以从反复出现的 Skill 使用方式中沉淀。
- Platform saved memory 是 workspace 的一部分，对应 L1。
- `llm_memory_transferor/eval/` 暂时不动。

## 目标顶层结构

```text
memory_assistant/
├── manifest.json
├── README.md
├── README_zh.md
├── DEVELOP.md
├── PROJECT_KNOWLEDGE_BASE.md
├── REFACTOR_PLAN.md
├── DEVELOPMENT_LOG.md
├── prompts/
├── popup/
├── content/
├── background/
├── icons/
├── backend_service/
└── memory_transferor/
```

## `prompts/`

根目录 `prompts/` 保存 prompt 内容本身。它不是 Python 包内部代码目录。

```text
prompts/
├── episode_system.txt
├── profile_system.txt
├── preference_system.txt
├── projects_system.txt
├── workflows_system.txt
├── delta_system.txt
├── persistent_node_distill_bg.txt
├── schema.txt
├── cold_start.txt
└── platform_memory_collect.txt
```

职责：

- 存放可编辑 prompt 文本。
- 被 backend、memory_transferor 和 popup 注入流程读取。
- prompt 的加载、命名映射和渲染逻辑不放在这里，而放在 `prompt_loader/`。

## `memory_transferor/`

`memory_transferor` 是通用记忆核心。它只关心记忆如何表示、存储、构建、治理、连接、索引和导出，不包含 FastAPI 路由和浏览器 UI。

```text
memory_transferor/
├── pyproject.toml
├── README.md
└── src/memory_transferor/
    ├── __init__.py
    ├── cli.py
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

### `runtime/`

运行时基础设施，不放记忆业务逻辑。

```text
runtime/
├── __init__.py
├── llm_client.py
├── clock.py
└── errors.py
```

职责：

- `llm_client.py`：统一模型 provider 调用。
- `clock.py`：统一时间获取、时间解析和测试可控时间。
- `errors.py`：统一异常类型，避免各层随意抛字符串异常。

### `memory_models/`

定义记忆对象的 schema，只描述“数据长什么样”，不负责生成、存储或业务编排。

```text
memory_models/
├── __init__.py
├── base.py
├── raw.py
├── platform_memory.py
├── episode.py
├── persistent.py
├── profile.py
├── preference.py
├── project.py
├── workflow.py
├── daily_note.py
├── skill.py
└── platform_mapping.py
```

职责：

- `raw.py`：L0 raw chat session 和 raw chat turn。`RawChatTurn` 是最小 raw evidence 单元；单条 message 只作为页面抓取或导入适配时的临时输入，不进入核心 raw 模型。
- `platform_memory.py`：L1 platform saved memory，包括 saved memory、custom instructions、agent config、platform skills 等。
- `episode.py`：L2 turn-level episode，必须包含 `episode_id`、`conversation_id`、`turn_refs`、`time_range_start/end`、summary、keywords、connections。
- `persistent.py`：persistent memory 通用基类或联合类型。
- `profile.py` / `preference.py` / `project.py` / `workflow.py` / `daily_note.py` / `skill.py`：persistent memory 的具体类型。
- `platform_mapping.py`：导出到目标平台时的字段映射。

### `memory_store/`

权威记忆存储层。这里负责读写本地 JSON/Markdown 文件，是 canonical memory storage。

```text
memory_store/
├── __init__.py
├── memory_workspace.py
├── raw_store.py
├── platform_memory_store.py
├── episode_store.py
├── persistent_store.py
└── metadata_store.py
```

职责：

- `memory_workspace.py`：整个本地记忆根目录入口，不是新的存储格式。它组合 raw、platform memory、episodes、persistent memory、metadata。
- `raw_store.py`：读写 `raw/`，对应 L0。
- `platform_memory_store.py`：读写 `platform_memory/`，对应 L1。
- `episode_store.py`：读写 `episodes/`，一个 conversation 文件可包含多个 turn-level episodes。
- `persistent_store.py`：读写 persistent memory，包括 `profile/`、`preferences/`、`projects/`、`workflows/`、`daily_notes/`、`skills/`。
- `metadata_store.py`：读写 `metadata/`、索引、organize state、display texts、logs。

目标 workspace 语义：

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

### `memory_builders/`

从低层材料生成高层记忆。它描述“怎么把材料整理成记忆”。

```text
memory_builders/
├── __init__.py
├── episode_builder.py
├── persistent_builder.py
├── profile_builder.py
├── preference_builder.py
├── project_builder.py
├── workflow_builder.py
├── daily_note_builder.py
├── skill_builder.py
└── workflow_skill_linker.py
```

职责：

- `episode_builder.py`：从 raw conversations 生成 turn-level episodes。
- `persistent_builder.py`：从 episodes 生成 persistent memory 的总编排器。
- `profile_builder.py` / `preference_builder.py` / `project_builder.py` / `workflow_builder.py` / `daily_note_builder.py`：分类型构建 persistent memory。
- `skill_builder.py`：从推荐 Skill、平台 Skill、用户保存和重复工作模式中沉淀 persistent skills。
- `workflow_skill_linker.py`：让 workflow 引用 skills，表达 workflow 由哪些 skill 组成或调用。

### `memory_policy/`

L3 规则层。它不保存事实，而是决定事实如何被抽取、升级、合并、确认或跳过。

```text
memory_policy/
├── __init__.py
├── extraction_policy.py
├── upgrade_policy.py
├── conflict_policy.py
├── privacy_policy.py
└── temporal_policy.py
```

职责：

- `extraction_policy.py`：什么内容值得抽取。
- `upgrade_policy.py`：episode 信息何时升级为 persistent memory。
- `conflict_policy.py`：新旧记忆冲突时如何处理。
- `privacy_policy.py`：敏感信息检测、确认和过滤。
- `temporal_policy.py`：current、previous、before、after、latest、earliest 等时间关系规则。

### `episode_graph/`

episode 连接和分组层。它负责 connection、grouping、跨对话验证和错链控制。

```text
episode_graph/
├── __init__.py
├── connection.py
├── connection_policy.py
├── grouping.py
└── validators.py
```

职责：

- `connection.py`：episode connection 的结构和基本操作。
- `connection_policy.py`：什么情况下允许 episode 相连。
- `grouping.py`：由 connections 形成 groups。
- `validators.py`：双向验证、最大跳数、group 大小、冗余边裁剪，防止 A-B、B-C、C-D 后一条错链导致整个项目记忆走样。

### `prompt_loader/`

代码层 prompt 加载器。prompt 内容仍在根目录 `prompts/`。

```text
prompt_loader/
├── __init__.py
├── loader.py
├── prompt_names.py
└── render.py
```

职责：

- `loader.py`：从根目录 `prompts/` 加载 prompt。
- `prompt_names.py`：维护 prompt 名字和文件名映射。
- `render.py`：可选的变量渲染和上下文拼接。

### `external_memory_index/`

外部数据库索引层。这里放 ChromaDB、BM25、SQLite FTS、hybrid retrieval 等派生索引。

```text
external_memory_index/
├── __init__.py
├── documents.py
├── source_refs.py
├── chroma_schema.py
├── chroma_index.py
└── rebuild.py
```

职责：

- 从 `memory_store/` 读取 canonical memory。
- 生成可检索 index documents。
- 写入 ChromaDB 等外部数据库。
- 查询 top-k evidence。
- 返回 source refs，再回 canonical storage 读取权威内容。

边界：

- 这里不是 L2。
- 这里不是权威存储。
- 删除外部索引后，必须能从 `memory_store/` 重建。

### `memory_export/`

导出、注入和 bootstrap prompt 生成。

```text
memory_export/
├── __init__.py
├── package_exporter.py
└── bootstrap_generator.py
```

职责：

- 生成迁移包。
- 生成目标平台 bootstrap prompt。
- 根据 platform mapping 控制字段转换。

## `backend_service/`

`backend_service` 是产品后端。它组合 `memory_transferor` 的能力，提供 API、任务、推荐、导入、导出、注入等产品逻辑。

```text
backend_service/
├── app.py
├── routes/
├── schemas/
├── services/
├── repositories/
├── jobs/
├── storage_paths.py
├── catalog/
└── README.md
```

### `routes/`

FastAPI endpoint，只负责 HTTP 入参、出参和调用 service。

```text
routes/
├── settings.py
├── conversations.py
├── platform_memory.py
├── memory.py
├── packages.py
├── skills.py
├── cache.py
└── jobs.py
```

### `schemas/`

API request / response models。

```text
schemas/
├── settings.py
├── conversations.py
├── platform_memory.py
├── memory.py
├── packages.py
├── skills.py
└── jobs.py
```

### `services/`

产品应用逻辑，不放在 route 里。

```text
services/
├── settings_service.py
├── conversation_import_service.py
├── platform_memory_service.py
├── organize_service.py
├── memory_query_service.py
├── package_service.py
├── injection_service.py
├── skill_library_service.py
├── recommended_skill_service.py
├── skill_ranking_service.py
└── cache_service.py
```

职责：

- `conversation_import_service.py`：加入当前对话、append conversation。
- `platform_memory_service.py`：加入平台记忆，处理平台 saved memory。
- `organize_service.py`：整理记忆任务编排。
- `memory_query_service.py`：memory categories/items 展示查询。
- `package_service.py`：导出 package。
- `injection_service.py`：注入 package 或 prompt。
- `skill_library_service.py`：我的 Skill 保存、读取、删除。
- `recommended_skill_service.py`：推荐 Skill catalog 管理。
- `skill_ranking_service.py`：基于 profile/preferences/projects/workflows/daily_notes/skills/platform memory 计算推荐。
- `cache_service.py`：临时缓存和本地记忆清理。

### `repositories/`

后端自己的文件资产读写，不放复杂业务逻辑。

```text
repositories/
├── settings_repository.py
├── job_repository.py
├── recommended_skill_catalog.py
└── backend_asset_store.py
```

### `jobs/`

长任务编排。

```text
jobs/
├── job_runner.py
├── organize_job.py
└── import_job.py
```

## 浏览器插件目录

```text
popup/
content/
background/
```

职责：

- `popup/`：用户界面，调用 backend API。
- `content/`：页面侧采集、输入框注入、平台记忆抓取。
- `background/`：后台捕获、同步状态、消息路由。

后续原则：

- 浏览器侧不定义 canonical memory schema。
- 浏览器侧只采集和展示，核心记忆构建尽量回到 backend + memory_transferor。

## 测试 case 规划检查

测试文件：

```text
memory_test_samples_minimal.json
```

这个文件只作为最小测试样本，提供模拟输入和期望记忆结果。它不是产品必须支持的正式导入格式，也不要求 canonical raw parser 直接适配这个文件外壳。

样本结构：

```text
dataset_name
version
cases[]
  case_id
  target_memory_type
  sessions[]
    session_id
    time
    platform
    messages[]
      role
      content
  expected_memory_items[]
```

覆盖类型：

- `preference`
- `profile`
- `workflow`
- `topic`

按目标架构测试时，应把 `sessions[]` 当作“已经从页面或平台抓取到的原始对话会话”，再转换成我们的 raw 层：

```text
memory_test_samples_minimal.json cases[].sessions[]
  -> test adapter
  -> RawChatSession[]
       turns: RawChatTurn[]
  -> EpisodeBuilder
  -> EpisodeStore
  -> PersistentBuilder
  -> PersistentStore
  -> optional ExternalMemoryIndex
```

目标 raw 层语义：

```text
RawChatSession
  session_id
  platform
  title
  url
  timestamp
  turns[]

RawChatTurn
  turn_id
  session_id
  timestamp
  user_text
  assistant_text
```

`RawChatTurn.timestamp` 是这一轮 Q&A 的发生时间，只保留一个时间字段。取值优先级：

1. assistant reply 时间。
2. user message 时间。
3. session time。
4. 都没有则为空，后续时间推理必须知道该证据缺少时间。

当前 `xhu` 分支状态：

- 当前 `L0RawLayer.ingest_file()` 不能直接解析这个测试文件，但这不是产品问题，因为该文件只是测试样本外壳。
- 当前 `l0_raw.py` 还没有清晰的 `RawChatSession` / `RawChatTurn` 目标模型。
- 因此第一步不是“适配测试文件格式”，而是明确并实现 raw chat session / turn 模型，然后写一个测试 adapter 把样本 sessions 映射进去。

按目标 raw 层语义做的内存映射检查：

```text
cases: 4
sessions: 9
turns: 33
complete_turns: 29
missing_side: 4
missing_timestamp: 0
```

结论：

- 该样本可以映射为 `RawChatSession -> RawChatTurn[]`。
- 每个 turn 都可以从 session time 继承一个 `timestamp`。
- 有 4 个 turn 缺少 user 或 assistant 的一侧，后续 raw adapter 需要保留 `status` 或等价标记，不能静默丢弃。

这个 case 可以作为重构后的最小验收样本：

- 每个 session 的 `time` 应转成 `RawChatSession.timestamp`，并作为 turn timestamp fallback。
- 每个 session 应能形成 `RawChatTurn[]`。
- episode 应有 `time_range_start/end` 和 `turn_refs`。
- persistent memory 输出应能与 `expected_memory_items` 做结构级比对。

## 分阶段迁移

### P0：建立规划和最小测试入口

- 新增 `REFACTOR_PLAN.md`。
- 用 `memory_test_samples_minimal.json` 作为最小结构测试样本。
- 不改 `llm_memory_transferor/eval/`。

### P1：补齐 L0 raw chat session / turn 基础

- 增加 `RawChatSession` 和 `RawChatTurn`。
- `RawChatTurn` 作为最小 raw evidence 单元，包含一轮 Q&A 和一个 `timestamp`。
- 页面抓取、同步捕获、历史导入最终都应落到 `RawChatSession -> RawChatTurn[]`。
- 测试 case 只通过 test adapter 映射成 `RawChatSession[]`，不作为正式导入格式。
- 保证 raw turn 可以追溯到原始 session。
- 验证：测试 case 能转成 `RawChatSession[]`，且 session 数、turn 数、timestamp 正确。

### P2：拆 episode 构建和存储

- 把 episode schema、builder、store 的职责分清。
- episode 必须保存 `time_range_start/end`、`turn_refs`、summary、keywords、connections。
- 验证：测试 case 能生成并保存 turn-level episodes。

### P3：persistent memory 构建

- 从 episodes 生成 profile/preferences/projects/workflows/daily_notes/skills。
- skills 纳入 persistent memory。
- workflow 支持引用 skills。
- 验证：测试 case 的 preference/profile/workflow/topic 能形成 persistent candidates。

### P4：episode connection / grouping

- 建统一 connection 机制。
- 先形成 connection group，再分发到 persistent memory 类型。
- 加双向验证、最大跳数、group size、冗余边裁剪。

### P5：prompt 整理

- 清理 overfit special case。
- 明确 raw evidence、summary evidence、timestamp 的使用方式。
- 时间关系用 general instruction，不写死失败样例。

### P6：外部数据库索引

- 增加 `external_memory_index/`。
- 从 canonical memory storage 派生 ChromaDB index。
- ChromaDB 返回 source refs，不作为权威存储。

### P7：后端拆分

- `backend_service/app.py` 拆 routes/schemas/services/repositories/jobs。
- 保留 API 行为。
- Skill 推荐逻辑拆到 service。

## 每步验证

每次改动后至少执行：

```text
python3 -m py_compile <changed python files>
pytest llm_memory_transferor/tests
node --check popup/popup.js
node --check background/background.js
```

如涉及 API：

```text
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765
GET /api/health
```

如涉及测试 case：

```text
memory_test_samples_minimal.json -> RawChatSession[] -> RawChatTurn[] -> episodes -> persistent candidates
```
