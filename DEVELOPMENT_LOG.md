# 开发日志

## 2026-04-30

- 🏠 梳理项目记忆架构与清理无用文件
  - 改了什么：
    - 新增 `PROJECT_KNOWLEDGE_BASE.md`，用中文描述 Memory Assistant 的项目目标、知识库定位、L0/L1/L2/L3 记忆架构，以及 ChromaDB 在项目中的派生索引定位。
    - 删除未接入当前主路径的 `offscreen/` 文件。
    - 清理 `manifest.json` 中无用的 `offscreen` 权限，修正插件名拼写，并更新插件描述。
    - 删除未被项目引用的 Python `storage.py` helper，并同步清理 `utils/__init__.py` 的导出。
    - 删除已跟踪但无内容的 LongMemEval 结果产物。
  - 为了什么：
    - 给后续在 `xhu` 分支上的大改建立清晰的产品和工程基线。
    - 明确项目自己的 canonical memory storage 与 ChromaDB 派生索引之间的边界。
    - 减少旧实现、运行产物和当前主路径无关文件对后续重构的干扰。

- 🏠 制定主路径重构规划并检查最小测试样本
  - 改了什么：
    - 新增 `REFACTOR_PLAN.md`，按层级结构规划 `memory_transferor`、`backend_service`、插件目录、prompt、外部数据库索引和 persistent memory 的边界。
    - 明确 `platform_memory/` 属于 workspace，`skills/` 属于 persistent memory，workflow 可以引用 skills。
    - 明确 ChromaDB 属于 `external_memory_index/`，是可重建的外部数据库索引，不是 canonical storage。
    - 用 `memory_test_samples_minimal.json` 做规划检查，确认该样本可模拟页面抓取后的 `sessions -> turns` 输入和期望 persistent memory 输出。
    - 明确测试样本不是正式导入格式，不要求 canonical raw parser 直接适配它的文件外壳。
    - 将目标 raw 层收敛为 `RawChatSession` 和 `RawChatTurn`，其中 `RawChatTurn` 是最小 raw evidence 单元，只保留一个 `timestamp`。
  - 为了什么：
    - 把后续大改拆成可 review、可测试、可回退的阶段。
    - 明确第一步应该先补齐 L0 raw chat session / turn 模型和测试 adapter，而不是先动 eval。
    - 用最小测试样本作为后续重构验收基线。

- 🏠 按 RawChatSession / RawChatTurn 语义重试最小测试样本
  - 改了什么：
    - 不再把测试样本当成正式导入格式，而是把 `cases[].sessions[]` 当成页面抓取后的模拟输入。
    - 在内存中将 9 个 session 映射成 33 个 `RawChatTurn`。
    - 确认所有 turn 都能从 session time 继承 `timestamp`。
    - 发现 4 个 turn 缺少 user 或 assistant 的一侧，后续 adapter 需要保留状态标记，不能静默丢弃。
    - 将检查结果写入 `REFACTOR_PLAN.md`。
  - 为了什么：
    - 验证目标 raw 层规划可以承接该测试样本提供的信息。
    - 明确下一步实现 raw adapter 时需要处理不完整 turn。

- 🏠 新增 memory_transferor 主路径骨架并跑通最小样本
  - 改了什么：
    - 新增 `memory_transferor/` 包，先落地 `runtime/`、`memory_models/`、`memory_builders/`、`memory_store/`、`external_memory_index/` 等目标目录。
    - 实现 `RawChatSession` / `RawChatTurn`，把 turn 作为最小 raw evidence 单元，并保留单一 `timestamp`。
    - 实现 turn-level `EpisodeBuilder`，每个 raw turn 生成一个 episode，保留 episode id、turn id、timestamp、summary 和 source text。
    - 实现第一版 `PersistentBuilder`，从 episodes 抽取 profile、preference、workflow、topic 等 persistent memory，并由代码生成稳定 `memory_id`。
    - 实现 workspace 写入：raw 写入 `raw/`，episodes 写入 `episodes/`，persistent memory 按 `profile/`、`preferences/`、`projects/`、`workflows/`、`daily_notes/`、`skills/` 分目录落盘。
    - 实现 `external_memory_index/documents.py`，明确外部索引只从 canonical memory 派生，不作为权威存储。
    - 新增 `scripts/run_memory_sample_case.py`，用最小样本跑通 raw → episodes → persistent 的端到端流程。
    - 测试结果：9 个 session、33 个 turn、33 个 episode 可以完整写入；第三轮 persistent 抽取生成 12 条记忆，preference/profile 与期望数量一致，topic 被拆得更细，workflow 仍需后续 policy 把独立 check 流程拆出来。
  - 为了什么：
    - 把项目从旧的 conversation-level 临时构建方式推进到新的 turn-level canonical storage 主路径。
    - 先证明我们的存储格式可以接上 LLM 抽取和后续 ChromaDB 派生索引，而不是继续照搬外部 benchmark 的分块存储。
    - 暴露下一步需要单独处理的 persistent 聚合/拆分策略问题。

- 🏠 将最新 main 合并回 xhu
  - 改了什么：
    - 先在 `xhu` 提交 memory_transferor 主路径改动。
    - 切到 `main` 后拉取 `origin/main`，确认 main 已经是最新。
    - 切回 `xhu` 并合并 `main`，合并过程无冲突。
  - 为了什么：
    - 确保后续大改继续建立在最新主分支之上。
    - 避免 `xhu` 长期偏离 main，减少后续持续重构时的冲突成本。

- 🏠 整理 memory prompt 语言策略和分类边界
  - 改了什么：
    - 重写 `prompts/episode_system.txt`、`delta_system.txt`、`profile_system.txt`、`preference_system.txt`、`projects_system.txt`、`workflows_system.txt`，统一为英文规则、明确中文输出策略。
    - 将 prompt 中不必要的中英混杂和具体场景 special case 改成通用 instruction 与 in-context example。
    - 补充时间规则：模型需要利用 timestamp / event order 处理 current、previous、before、after、latest、old 等关系，但不直接输出系统维护的时间字段。
    - 更新 `prompts/schema.txt`，明确 L0 RawChatSession / RawChatTurn、L1 平台信号、L2 turn-level episodes、L2 persistent、L3 policy / governance 和外部索引边界。
    - 重写 `prompts/persistent_node_distill_bg.txt`，把 daily_notes 边界、证据确认规则、连接证据使用规则整理成更通用的英文 prompt。
    - 更新 `memory_transferor` 新主路径的 persistent 抽取 prompt，补充 language policy、type boundaries、atomicity 和 skill 生成限制。
    - 测试结果：prompt 加载正常，Python 编译通过；最小样本流程可跑通。样本输出显示 profile/preference 基本可控，但 topic 拆分与 workflow final check 拆分仍存在不稳定，需要后续用 `memory_policy` 或 post-process 做确定性拆分/校验。
  - 为了什么：
    - 让 prompt 更像长期可维护的系统规则，而不是针对单个测试样本的答案。
    - 支持“中文输入 + 英文术语更清晰”的混合表达方式。
    - 为下一步把 prompt 判断迁移到 L3 policy / deterministic validation 打基础。

- 🏠 更新项目知识库文档以对齐重构规划
  - 改了什么：
    - 更新 `PROJECT_KNOWLEDGE_BASE.md` 的当前工程实现描述，明确 `memory_transferor/` 是后续重构主路径。
    - 补充 canonical workspace 目录语义，包括 `raw/`、`platform_memory/`、`episodes/`、persistent memory 各目录、`metadata/` 和 `logs/`。
    - 明确 `external_memory_index/` 与 ChromaDB 目前只作为未来派生索引方向，暂不作为当前实现重点。
    - 明确 `llm_memory_transferor/eval/` 暂时不处理，等 canonical storage、episode graph 和 memory policy 稳定后再接评测路径。
    - 补充当前完成状态、尚未完成内容，并把 `episode_graph + memory_policy` 标为下一步 P0。
  - 为了什么：
    - 让项目知识库文档和当前重构规划保持一致。
    - 避免后续继续混淆 canonical memory storage、外部索引和 eval benchmark 的边界。
    - 为下一阶段实现 episode connection/grouping 与 L3 policy 做上下文铺垫。
