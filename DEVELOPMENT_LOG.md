# 开发日志

## 2026-05-07

- 🏠 修复同步记忆链路
  - 改了什么：
    - 修正 raw conversation 追加去重逻辑：从“单条消息内容去重”改成“整轮 user+assistant pair 去重”，避免用户重复问同一句但回答不同的时候丢失 user turn。
    - 增量同步创建 episode 后，会同步维护 Daily Notes persistent nodes 和 persistent node episode connections。
    - 增量同步的 episode 时间改用捕获到的 round timestamp，避免使用后端处理时间影响历史顺序。
    - 关闭 background 里旧的 JS memory_engine 自动增量调用，正式同步统一走本地后端，避免重复 API 调用和旧格式 `mw:*` 记忆并行生成。
  - 为了什么：
    - 让“同步对话”保存的 raw history 和 turns 更可靠。
    - 让“同步记忆”与当前 L2 存储、Daily Notes 展示和连接机制保持一致。
    - 避免旧 DeepSeek-only 前端增量路径和后端新路径互相打架。

- 🏠 改进 Daily Notes 的 episode 召回
  - 改了什么：
    - 将 Daily Notes 候选筛选从关键词硬门禁改成轻量语义向量召回：用本地 token / 字符 n-gram 向量计算 episode 与 daily note anchor、已有 daily note、项目型 anchor 的相似度。
    - 非项目 episode 不再因为没命中关键词就被挡在 daily_notes prompt 外；明显项目型 episode 仍会被过滤。
    - support 校验增加语义相似兜底，避免模型生成的 daily note 因为词面不完全重合被静默丢弃。
    - 在 daily_notes prompt 输入中加入语义分数作为检索提示，并明确分数不是用户事实，模型可以忽略不该进入 daily_notes 的候选。
  - 为了什么：
    - 避免“拒绝同事临时加任务”“学习方式”“个人计划”等日常记忆因为缺少固定关键词而无法进入 Daily Notes。
    - 保持后端负责召回和证据边界，模型负责判断是否形成日常记忆节点。

- 🏠 拆分用户画像的长期关注方向展示
  - 改了什么：
    - 将 `long_term_research_or_work_focus` 从“一个字段组合并展示”改成“长期关注方向”分组下的多个子选项。
    - 单个关注方向的 item id 继续使用 `profile:<field>:<value>` 格式，前端按同一个分组标题展示，复用现有的单项选择、注入过滤和删除逻辑。
  - 为了什么：
    - 避免“教育技术实证研究；学习视频剪辑”被挤在同一个 chip 里。
    - 让用户画像里的长期关注方向和主要任务类型一样，在同一个分组下面按单个小项勾选和管理。

- 🏠 继续加速“正在提取对话记忆”
  - 改了什么：
    - 将整理阶段的前端 display 生成改成懒加载：整理记忆时先写入后端字段兜底展示，需要精修某类展示时再显式调用 display LLM 补全。
    - 将 profile、preferences、projects 三类 persistent 抽取改成并行调用，保持写入仍串行。
    - 给 Daily Notes 节点维护增加候选过滤，只把可能形成日常记忆的 episode 送进节点维护 prompt。
    - 将 Daily Notes 默认 batch size 从 4 提到 8，减少中小规模整理时的重复 LLM 调用。
    - 给记忆条目接口增加 `refresh_display` 参数：默认加载只使用兜底展示，不额外调用 LLM；显式刷新时才按类别补全 display 文案。
  - 为了什么：
    - 把整理记忆的等待时间优先花在真正影响记忆结构的步骤上。
    - 避免前端展示文案在整理阶段阻塞用户。
    - 减少 Daily Notes 长 prompt 的调用次数，同时保留后续按需精修展示文案的能力。

## 2026-05-06

- 🏠 优化整理记忆的慢路径
  - 改了什么：
    - 将 episode 抽取改成并发 LLM 调用：先串行判断哪些 raw conversation 发生变化，再并行抽取 episode，最后串行写入 L2Wiki，避免并发写文件。
    - 给 workflow 抽取增加候选判断：只有 episode、L1 平台记忆或文本中出现可复用流程信号时才调用 workflow prompt，否则跳过这次 LLM 调用。
    - 将 Daily Notes 节点维护从逐 episode 调用改成 batch 调用，并记录 `persistent_node_llm_calls` 与 batch size，方便后续看真实调用数。
    - 瘦身 `daily_notes_system` prompt，保留 schema、证据边界、前端 display、自检、粒度与合并规则，删掉重复背景和过细说明。
    - 修正 `update_timestamp()`：整理任务只更新 `last_sync_at`，不再把整份运行时 settings 写回磁盘，避免临时测试路径污染真实配置。
  - 为了什么：
    - 降低新增/变更 raw 对话后的完整整理耗时。
    - 避免没有 workflow 证据时仍跑一次 10 秒级 workflow LLM 调用。
    - 减少 Daily Notes 维护阶段重复发送长 prompt 的次数。
    - 保持真实 wiki 写入仍然串行，减少并发优化带来的存储风险。

## 2026-05-05

- 🏠 改进记忆勾选、单条删除和前端展示兜底
  - 改了什么：
    - 将“勾选记忆内容”的选择写入扩展本地 storage，弹窗刷新或下次打开时复用上次选择，不再总是回到默认画像和偏好。
    - 给前端每条可见记忆增加单条删除入口，并新增后端 `/api/memory/items/delete`，支持删除 profile 分组、preference 单值或分组、project、workflow、daily note。
    - 后端输出 `memory/items` 前统一做展示文本清理和兜底，过滤空标题、内部 id、未命名文本和省略号式截断，标题不完整时从描述里提取自然短标题。
    - 给 L2Wiki 增加 project 删除能力，删除后同步刷新项目索引和根 README。
  - 为了什么：
    - 修复测试反馈中“每次勾选都回默认项”的体验问题。
    - 让用户能管理单条前端记忆，而不是只能一次性清空所有记忆。
    - 降低模型输出不完整或不自然展示文案时对前端可读性的影响。

- 🏠 修正沟通模板类 Daily Notes 展示主题
  - 改了什么：
    - 删除针对沟通、回复、短消息、邮件等具体场景的专门正则分支。
    - 标题生成规则改成由 prompt 泛化判断：标题写底层事情、活动、对象或目标，语气、格式、版本要求放到摘要。
    - 更新 daily_notes prompt，把规则泛化成“输出格式、渠道、语气、风格、版本要求不应抢占记忆主题”。
    - 补充学习、练习、规划、推荐类展示规则：标题写用户更大的学习目标或活动，具体练习、工具、样例产物放摘要。
    - 收紧摘要语言，避免 `X 待确认`、`偏好待确认` 这类系统状态式短语；用户已明确的方法偏好直接写成自然短句。
    - 再次收紧 Daily Notes 前端摘要：后端仍可保留未确认状态，但前端摘要改为展示推荐、需求、选择内容或方法偏好，不再默认输出 `待确认`。
    - 收紧助手建议边界：前端摘要只展示用户明确表达或接受的内容，助手补充的策略包、后续建议和未确认标签留在后端证据里，不再展示到卡片摘要。
    - 回收过重的后端语义兜底逻辑：Daily Notes 前端标题和摘要以节点维护 API 生成的 `display` 为准，后端只做格式清理、长度裁剪和极简空值兜底。
    - 将 Daily Notes 前端展示字段前移到节点维护 API：`daily_notes_system` 现在要求模型在生成或更新节点时同步输出 `display.title` 和 `display.description`，前端优先读取节点自带 display。
    - 将 Profile、Preferences、Projects、Workflows 和 Skills 统一接入 display cache：整理记忆结束时通过同一次后端 LLM API 生成前端卡片文案，前端读取时优先使用这些 display 文案。
    - 给统一 display API 和 Daily Notes 节点维护 prompt 增加 silent self-check：模型输出前需要自检标题摘要是否忠于用户证据、是否混入助手建议或内部字段、是否中英文一致，不合格则先修正再返回 JSON。
    - 删除缺失 display 时额外调用展示文案 prompt 的路径；新设定下所有前端可见节点都应在生成或维护阶段写入 display。
  - 为了什么：
    - 避免“覆盖微信短消息偏好”“借口偏好”这类不符合主题的前端展示，同时减少面向单个 case 的硬编码。
    - 避免“15 秒小成品”“工具练习”等助手建议抢占标题，让标题更稳定地表达记忆主题。
    - 让“视频剪辑入门练习”这类摘要更像用户能读懂的记忆说明，例如“先做小成品再补理论”。
    - 让 Daily Notes 的短 summary 更贴近原始记忆主题，方便用户快速判断这条记忆是什么。
    - 明确“模型负责理解和生成展示文案，后端负责存储、校验和展示”的边界，避免后端正则反复补规则。
    - 让所有前端可见记忆类型使用同一套 display contract，减少不同节点各自展示逻辑不一致的问题。
    - 让 display 文案生成时自带质量检查，减少“模型生成了但不适合前端”的后处理补丁。

## 2026-05-04

- 🏠 将 backend 主路径迁到 memory_transferor
  - 改了什么：
    - 将 raw 导入解析、L1 平台记忆信号、LLM client、L3 lifecycle policy、export/bootstrap、typed managed memory models、L2Wiki、MemoryBuilder 和 MemoryUpdater 逐步迁入 `memory_transferor`。
    - 更新 `backend_service/app.py` 的 import，backend 不再从 `llm_memory_transferor` 加载产品主路径模块，也不再把 `llm_memory_transferor/src` 注入 `sys.path`。
    - 保留现有存储格式、API 行为和前端选择逻辑，只改变模块归属与依赖方向。
    - 同步更新 `backend_service/README.md` 中关于 backend runtime 依赖的说明。
  - 为了什么：
    - 为后续删除旧 `llm_memory_transferor` 目录铺路。
    - 让产品后端统一依赖新的 canonical `memory_transferor` 包，减少新旧两套命名和模块边界混用。
    - 先完成可验证的主路径迁移，再处理旧 CLI、eval、tests 和文档引用。

## 2026-05-02

- 🏠 优化记忆整理速度和前端展示口径
  - 改了什么：
    - 给“正在提取对话记忆”流程增加运行耗时与处理数量统计，记录 raw 会话数量、跳过数量、LLM 调用数量、episode 构建数量、persistent 重建和节点维护耗时。
    - 将 persistent node 维护改成可增量处理：raw conversation 未变化时跳过 episode 抽取，只有变更 episode 进入节点维护；必要时才触发全量重建。
    - 增加节点支持证据清理，避免旧 episode 引用失效后仍保留过期 daily/project 节点。
    - 调整 Daily Notes prompt，要求约束和条件必须保留其所属生活场景，不能输出脱离上下文的条件列表。
    - 修正 Daily Notes 前端展示：标题只保留自然主题，例如“晚餐偏好”；20 分钟、少油、不辣、低碳水等细节放在摘要里，不再拼成“20分钟内只用一口锅偏好”。
    - 修改前端顶部“记忆条目”统计口径，只统计 profile、preferences、projects、workflows、daily_notes 这些用户可见记忆，不再把内部 episodes 数量算进去。
  - 为了什么：
    - 缩短重复整理已有 raw 记忆时的等待时间，减少不必要的模型调用。
    - 让 Daily Notes 的前端显示更自然、更稳定，并避免把具体约束误判成主题。
    - 让顶部统计符合用户实际能看到和选择的记忆节点，减少内部中间层对前端理解的干扰。

- 🏠 去掉 Daily Notes 前端摘要里的标题复读
  - 改了什么：
    - 增加 Daily Notes 展示层去重规则：如果摘要已经以标题开头，就只展示后面的条件、状态或偏好细节。
    - 当标题已经承载主题时，摘要不再重复拼接主题，例如从“周末想看电影放松：不压抑、结局不虐”改为“不压抑、结局不虐”。
    - 调整偏好和待确认状态的优先级，让“从零开始学剪视频”这类条目优先展示具体偏好，而不是泛泛显示“偏好待确认”。
  - 为了什么：
    - 让前端记忆卡片更像“标题 + 补充说明”，减少重复文字带来的噪音。
    - 保持 Daily Notes 简短可扫读，同时不丢失用户真正关心的条件和偏好。

- 🏠 清理记忆抽取和展示中的样例硬编码
  - 改了什么：
    - 删除 Daily Notes 标题生成中的固定物品映射，不再把 `coat`、`shoe`、`cocktail`、`fruit` 等 token 直接翻译成固定前端标题。
    - 将 Daily Notes 摘要生成改成从自然描述中抽取“主题 + 条件”，例如保留生活主题，再展示约束条件。
    - 去掉 `快速（20分钟内）`、`酸的`、风衣/鞋子/鸡尾酒等样例驱动的精确替换和专门分支。
    - 收紧 project、workflow、skill、primary task type 的过滤逻辑，用“临时建议、一次性选项、过细对象、稳定任务模式”等通用信号替代具体领域词。
    - 将 `type_boundary_policy` 中的特定学科 marker 改成通用的“专业 / 领域 / 研究方向”边界词。
    - 泛化 daily_notes prompt 和 README 中的例子列表，避免模型把示例场景当作固定分类。
    - 修复扩展消息通道和 clipboard 捕获逻辑，避免前端异步响应通道关闭导致 console 报错，并让复制捕获只在需要提取回答时临时启用。
  - 为了什么：
    - 保证记忆系统不会针对当前测试素材过拟合，后续换成其他用户、其他生活主题或其他项目主题时仍能按同一套抽象规则工作。
    - 让前端 Daily Notes 能保留主题和短摘要，同时避免把后端 key、内部 context 或样例词暴露给用户。
    - 降低浏览器扩展在 ChatGPT 页面注入和提取回答时对页面自身交互的干扰。

- 🏠 收紧项目记忆的父子节点边界
  - 改了什么：
    - 停止 `SplitMergePolicy` 自动把 broad topic 拆成 `aggregation_schema`、`retrieval_schema`、`export_schema`、`product_direction` 等同级子 topic。
    - 新增保守 topic 合并规则：当子 topic 的 key 嵌套在父 topic 下，且 evidence 与父 topic 高度重叠时，合并回父项目节点。
    - 收紧 `PersistentBuilder` 内联 prompt，要求 topic/project 默认保留一个用户拥有的父项目；schema、工具、交付形态、实现轨道默认写进父项目 description，除非用户明确把它们作为独立长期工作推进。
    - 用前一轮 AI 输出做本地复算验证，persistent items 从 15 条收敛到 11 条，topic 从 6 条收敛到 2 条。
  - 为了什么：
    - 修复 LLM memory migration 这类项目被拆成多个重复 schema/product 同级节点的问题。
    - 让项目记忆更符合“父项目优先，子方向作为项目细节”的产品定位。
    - 减少前端 Projects 展示和后续注入中的重复节点。

- 🏠 保留 proposal 项目的具体主题实体
  - 改了什么：
    - 给 `EpisodeBuilder` 增加轻量关键词抽取，保留 `TCR-pMHC`、`ML proposal` 等实体和主题提示。
    - 调整 episode semantic connection，当跨 session episode 共享明确技术实体时，允许建立保守语义连接。
    - 在 `PersistentBuilder` 的 evidence 输入中加入 episode keywords。
    - 更新 persistent prompt，要求 proposal、benchmark、writing、guidance 类证据必须保留底层研究主题或项目对象，不能泛化成普通写作指导。
    - 增加 generic project topic 修正：当模型输出 `proposal_writing_guidance` 这类泛化项目时，回看 evidence 和 semantic neighbor，把它修正为带具体主题的 project。
    - 复跑测试后，`proposal_writing_guidance` 被修正为 `tcr_pmhc_binding_prediction_ml_proposal`，项目描述保留了 `TCR-pMHC binding prediction` 主题。
  - 为了什么：
    - 避免有明确研究对象的 proposal 项目被抽象成泛泛的写作指导。
    - 让 project 记忆更适合后续检索、展示和注入。
    - 用跨 session 主题连接补足单轮 episode 的上下文。

## 2026-05-01

- 🏠 压缩 Daily Notes 前端摘要
  - 改了什么：
    - 将 Daily Notes 的 `display_description` 改成约 20 字的短状态句。
    - 优先保留偏好、约束和待确认状态，例如“酸味偏好，低酒精浓度款式待确认”。
    - 保留后端完整 `description` 和注入证据，不用前端展示长度反向裁剪记忆内容。
    - 修复 popup 选择列表中 Daily Notes 小字摘要被前端清空的问题，让 checkbox 下方继续显示短摘要。
    - 新增 Daily Notes 证据重叠合并规则，将同一偏好延伸出的应用场景合并到同一节点，避免“酸味食物偏好”和“酸味鸡尾酒选择”拆成两张卡。
    - 调整 Daily Notes 前端摘要生成，输出完整短句，不再机械截断成半句话。
    - 精简精细注入 payload：memory 层只保留节点标题与短描述，episode 层只保留时间、topic、summary、open issues 和 turn refs，raw 层只保留每轮原始 user/assistant 消息。
    - 移除精细注入里的后端分析字段和重复字段，包括 connections、display、evidence_links、matched_reasons、turn_excerpt、message_ids 等。
    - 注入证据按历史记录先后排序；同一时间下按同一对话的 turn 顺序排列，并在注入 prompt 中明确说明这一点。
    - 后端 persistent 分析输入也改为按 episode 时间和 turn 顺序排序，避免同一时间的多轮对话被乱序分析。
  - 为了什么：
    - 让前端卡片更紧凑，避免日常记忆描述占用过多空间。
    - 保证用户查看时能快速扫到关键信息，同时不损失后续注入所需的完整上下文。
    - 让同一条个人偏好及其后续选择上下文保持在一个节点里，减少重复和割裂感。
    - 让精细注入保留完整原始回答过程，同时避免把同一证据在多个后端字段中反复注入。
    - 让模型在处理 current、previous、before、after 等时间关系时看到稳定的历史顺序。

- 🏠 复跑 raw 记忆整理并修正 Daily Notes 展示截断
  - 改了什么：
    - 将当前 `.state/wiki/raw` 复制到 `/tmp/memory_raw_eval_R6xBt3/wiki/raw`，用临时 wiki 跑完整 raw → episodes → persistent nodes → frontend display 流程。
    - 验证结果为 4 个 raw conversations、10 个 episodes、1 个 project、0 个 workflows、4 个 persistent nodes。
    - 抽查 compact 注入，确认普通注入不再携带 episode evidence 或 raw turn，只输出被选节点的有效字段。
    - 修正 Daily Notes 前端展示：识别 `fruits` 为“水果”，并在描述过长时优先截到完整分句，避免出现半截词或省略号。
  - 为了什么：
    - 给用户 review 当前整理结果提供最新样本输出。
    - 继续收紧前端显示的精炼度和可读性。
    - 确认项目 goal 中未确认的助手建议不会作为 compact 注入里的已确认目标。

- 🏠 泛化项目命名与 Daily Notes 展示规则
  - 改了什么：
    - 更新 `profile_system`，要求长期关注方向不要同时输出同一项目的项目名和描述性改写。
    - 更新 `episode_system`，要求保留用户启动长期项目的 turn，即使助手回复主要是建议。
    - 更新 `projects_system`，要求项目名优先来自用户明确提出的父项目，不被后续资料检索问题或会话标题覆盖。
    - 更新 `daily_notes_system`，要求 internal key 可以保留证据状态，但自然语言 description 不暴露 `context/candidate/memory/node` 这类内部标签。
    - 后端增加 project-aware focus 去重，把和稳定 project goal/name 重叠的 profile focus 合并到项目名。
    - 后端 Daily Notes 标题生成改为自然 UI 短语，不再把内部 `context` 显示成“上下文”。
    - 复跑 raw 测试后，Profile 只显示 `T2I统一评测项目`，Daily Notes 显示为 `风衣颜色选择` 和 `酸味水果偏好`。
  - 为了什么：
    - 避免项目描述和项目名重复污染用户画像。
    - 避免前端暴露内部存储术语。
    - 让 prompt 规则可泛化到其他项目和日常选择场景，而不是针对 T2I 或风衣样本写死。

- 🏠 调整普通注入与精细注入的证据边界
  - 改了什么：
    - 普通注入恢复轻量 `episode summary` evidence，只保留 episode id、topic、summary、时间范围、key decisions 和 open issues。
    - 普通注入继续排除 raw turn、原始 messages、related raw snippets 和存储元数据。
    - 精细注入保留完整 episode record，并继续带 raw turn / messages 证据。
    - Daily Notes 前端 description 改回完整摘要文本，不再只取第一句，也不使用省略号。
    - compact 注入层过滤“用户尚未回应助手/助理提议”这类助手主动 follow-up，避免写成用户待办。
  - 为了什么：
    - 让普通注入既有必要的 episode 摘要证据，又不会把 raw 对话塞进当前会话。
    - 让前端 daily note 摘要信息完整、可读，并避免半截截断。
    - 进一步防止助手主动建议污染用户记忆状态。

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

- 🏠 实现 episode_graph 与 memory_policy 第一版
  - 改了什么：
    - 给 `Episode` 增加 `connections` 和 `connection_group_ids`，并新增 `EpisodeConnection`、`EpisodeGroup` 模型。
    - 新增 `episode_graph/connection.py`、`connection_policy.py`、`grouping.py`、`validators.py`，实现同 conversation 相邻 turn 连接、跨 conversation mutual top-k semantic 连接、直接邻居 group 生成、group size 限制和非传递式扩张。
    - 新增 `memory_policy/upgrade_policy.py`、`temporal_policy.py`、`type_boundary_policy.py`、`split_merge_policy.py`、`persistent_policy.py`，实现 confidence / export priority 归一、profile/preference/topic 类型边界校验、workflow final check 拆分和宽泛 topic 子方向拆分。
    - 更新 `PersistentBuilder`，让 persistent 抽取接收 episode groups，并在 LLM 输出后经过 deterministic policy 后处理。
    - 更新 `EpisodeStore`，把 connection groups 随 session episode 文件一起落盘。
    - 更新最小样本 runner，改为 `raw -> episodes -> episode_graph -> persistent -> policy -> store`，并新增 `--graph-only` 离线验证模式。
    - 本地验证：最小样本生成 33 个 episodes、12 个 connection groups，其中 9 个 conversation groups、3 个 semantic groups，最大 group size 为 7。
    - 经用户允许后，用第三方模型跑通端到端样本；输出 14 条 persistent items，其中 workflow 被拆成主流程和 final check 两条，topic 子方向由 policy 进行可控拆分。
  - 为了什么：
    - 把 episode connection/grouping 从空骨架推进到可运行的 L3 基础设施。
    - 让 episode 先形成 connection group，再作为 persistent 抽取上下文，而不是完全依赖 prompt 自行判断。
    - 把容易不稳定的类型边界、workflow check 拆分和 topic 拆分从 prompt 中部分迁移到可测试的 deterministic policy。

- 🏠 新增前端展示 payload 导出层
  - 改了什么：
    - 新增 `memory_transferor/src/memory_transferor/memory_export/display.py`，把 persistent memory 派生成前端可展示的 display payload。
    - Profile / Preferences 展示为高层 checkbox 关键词，细粒度规则进入 `details` 和 `tooltip`。
    - 删除具体领域 family 的 hard-coded 词表，改为支持 `DisplayGroupHint`，高层 display taxonomy 后续由 policy、LLM 聚类归纳或用户前端编辑状态提供；当前仅保留通用相似度 fallback。
    - Projects / Workflows / Daily Notes / Skills 展示为短语加简要说明的 card payload。
    - display builder 支持 `auto`、`zh`、`en` 语言模式，`auto` 会根据记忆内容推断主展示语言。
    - 更新最小样本 runner，新增 `--display` 和 `--display-language`，可在 persistent build 后写出 `memory/display/payload.json`。
    - 更新 `REFACTOR_PLAN.md` 和 `PROJECT_KNOWLEDGE_BASE.md`，补充 display payload 的定位和当前状态。
  - 为了什么：
    - 给后续前端 review 提供稳定的数据契约。
    - 把前端展示逻辑从 canonical persistent memory 中分离，避免为 UI 需要污染权威存储结构。
    - 让细粒度偏好可以被保留，但不会在用户界面里过度碎片化。

- 🏠 清理 prompt 中的 hard-coded case 倾向
  - 改了什么：
    - 检查根目录 `prompts/`、`memory_transferor` 新主路径内嵌 prompt、`backend_service/app.py` 中的 UI 文案 prompt，并确认旧 `llm_memory_transferor` 非 eval 主路径会加载根目录 prompt。
    - 将 `episode_system`、`profile_system`、`preference_system`、`projects_system`、`workflows_system`、`persistent_node_distill_bg`、`cold_start` 中的具体 boundary example 改成通用 `Example policy`。
    - 删除或泛化容易被模型当成固定 case 的表达，例如具体格式示例、具体项目/评测对象、具体工作流短语。
    - 更新 `memory_transferor` 的 persistent builder prompt，明确不能复制 prompt、测试样本、项目名、工具名或评测对象作为固定类别标签。
    - 更新 backend 的双语 UI 文案 prompt，要求只根据输入生成展示文本，不根据字段名、示例或个别关键词推断固定领域分类。
  - 为了什么：
    - 避免模型在测试样本或早期讨论上 overfit。
    - 让 profile、preferences、projects、workflows、daily_notes 的分类和命名根据真实证据、已有记忆和用户编辑状态自适应生成。
    - 保留 examples 的边界说明价值，但明确它们不是 taxonomy，也不是要复制的文案。

- 🏠 收紧 preference policy 并修正前端展示适配
  - 改了什么：
    - 在 `backend_service/app.py` 中新增稳定任务类型过滤，只保留明确长期表达或跨 episode 稳定支持的 `primary_task_types`。
    - 停止把 profile 或单次 organize 推断出的临时任务类型直接合并成 preference checkbox。
    - 将前端实际读取的 Profile / Preferences items 改成字段级高层关键词展示，细节进入 description。
    - 将 `zh`、`en`、`response_granularity` 等内部值转成自然展示文案，例如“中文为主”“回答以中文为主”。
    - 将 Daily Notes 的前端标题从整段摘要改成短语标题，description 保留简要说明。
  - 为了什么：
    - 避免“搭配建议”“口味推荐”“技术调研”这类单次任务标签污染稳定偏好。
    - 让前端可见节点符合“Profile / Preferences 是高层 checkbox，Projects / Workflows / Daily Notes 是短语加简介”的产品要求。
    - 降低旧 display cache 中不自然文案对前端展示的影响。

- 🏠 落地前端展示基础 taxonomy
  - 改了什么：
    - 在 `backend_service/app.py` 中新增 `BASE_DISPLAY_TAXONOMY`，让后端明确知道前端高层 checkbox 与底层 memory fields 的映射。
    - Profile 基础组调整为“身份”“知识背景”“长期关注方向”。
    - Preferences 基础组调整为“语言”“表达风格”“主要任务类型”。
    - `memory_items_for_category()` 改为按 taxonomy group 聚合输出，例如 `profile:group:knowledge_background`、`preferences:group:language`。
    - `parse_selected_ids()` 支持解析 group id，并映射回具体字段，保证前端勾选高层组后导出/注入仍能拿到对应 memory。
  - 为了什么：
    - 保持前端 checkbox 简洁稳定，同时让后端保留可扩展字段映射。
    - 为后续模型提出动态展示组预留 registry 机制，但当前只启用人工确认过的 base taxonomy。

- 🏠 修正知识背景与任务类型稳定性规则
  - 改了什么：
    - 将 Profile 的“知识背景”来源收窄为 `domain_background`，不再把 `common_languages` 放入知识背景。
    - 保留语言相关信息在 Preferences 的“语言”组中展示。
    - 调整 `primary_task_types` 稳定性过滤，让规则同时考虑绝对支持数和小样本比例。
    - 改进中文短标签匹配，让“搭配建议”“推荐列表”“研究规划”这类标签可以通过首尾动作词和 episode 文本进行匹配。
  - 为了什么：
    - 避免“中文为主”误显示成用户知识储备。
    - 在样本数量较少时，允许占比明显的任务类型进入前端 checkbox，而不是只依赖固定绝对次数阈值。

- 🏠 同步 display taxonomy 与节点 prompt
  - 改了什么：
    - 新增 `memory_transferor/memory_export/display_taxonomy.py`，把前端 base taxonomy 从 backend 局部常量抽成共享模块。
    - backend 改为复用 `memory_transferor` 的 display taxonomy，避免两套映射漂移。
    - `MemoryDisplayBuilder` 默认使用 base taxonomy，同时仍支持外部传入 group hints。
    - 新增 `prompts/skills_system.txt`，补齐 skill persistent node 的抽取边界。
    - 新增 `prompts/display_taxonomy_proposal.txt`，规定模型只能提出 `suggested` 展示分组，由用户确认后才可激活。
    - 更新 `schema.txt`、`profile_system.txt`、`preference_system.txt`、`workflows_system.txt`，补充 base taxonomy、各节点 display 边界，以及 workflow 与 skill 的关系。
    - 更新旧路径和新路径的 prompt loader，确保 profile、preferences、projects、workflows、daily_notes、skills 和 display taxonomy proposal 都有可加载 prompt。
  - 为了什么：
    - 让 backend、`memory_transferor` 和 prompts 对同一套节点定义与前端展示结构达成一致。
    - 支持后续“模型建议新增展示组，用户确认是否添加”的扩展机制。

- 🏠 拆分 prompt 目录并修正主要任务类型展示
  - 改了什么：
    - 将根目录 prompt 按用途整理为 `episodes/`、`nodes/`、`platform/`、`display/` 四类子目录。
    - 将 daily notes 的 prompt 明确命名为 `prompts/nodes/daily_notes_system.txt`。
    - 更新 Python、backend 和 background prompt loader，确保新目录结构仍可加载。
    - 更新 README、开发文档和 schema prompt 中的旧路径说明。
    - 修正 Preferences 的“主要任务类型”前端输出，从一个合并 checkbox 拆成每个任务类型一个 checkbox。
  - 为了什么：
    - 让“一个节点一个 prompt”的结构更清楚，避免 daily_notes 继续藏在旧的 `persistent_node_distill_bg` 名字里。
    - 让前端可以单独勾选“搭配建议”“推荐列表”“研究规划”等稳定任务类型，同时后端仍按 `primary_task_types` 字段和值做过滤。

- 🏠 修复 raw 记忆整理中的节点路由问题
  - 改了什么：
    - 修复 daily_notes 维护时没有传入 support episode 对象，导致 LLM 返回的新节点全部被 support 校验丢弃的问题。
    - 在 backend organize 路径加入 episode 路由归一化，避免生活类日常上下文被误送进 profile / preferences。
    - 让 Preferences 在没有明确表达偏好证据时不再读取全量 episode 推断回答风格，只保留主语言和任务类型。
    - 给 `primary_task_types` 增加非 LLM 候选生成和稳定性过滤，fresh run 也能产出“搭配建议 / 推荐列表 / 研究规划”这类高层任务类型。
    - 将稳定项目补入 Profile 的“长期关注方向”，并把 Daily Notes 前端标题收短成短语。
  - 为了什么：
    - 让 raw → episode → persistent 的整理结果符合当前产品边界：Profile 是身份/背景/长期方向，Preferences 是语言/表达/任务类型，Daily Notes 承接生活选择和日常偏好。
    - 修复测试 raw 中 daily_notes 为空、任务类型为空、酸味水果误入 profile/preferences 的问题。

- 🏠 收紧节点 prompt 与 compact 注入粒度
  - 改了什么：
    - 更新 episodes、profile、preferences、projects、workflows、daily_notes、skills、delta prompt，统一要求区分用户事实、用户确认和助手建议。
    - 在 projects prompt 中明确 `project_goal` 只能来自用户已表达目标，助手提出的定位、场景、策略和约束必须先作为待确认内容。
    - 在 backend 注入路径新增 compact 适配层，普通注入只输出被选节点的有效字段，不再附带存储元数据、episode evidence 或 raw turn。
    - 将精细注入保留为证据模式，只有用户开启 detailed injection 时才带 episode / raw 追溯。
    - 对存量项目中的未确认定位做 compact 注入保护，避免把待确认的建议作为已确认 project goal 注入。
    - 修正 related raw turn 的字段名，从 `summary` 改为 `turn_excerpt`，避免把原文截取伪装成摘要。
    - 调整 Daily Notes 前端标题和描述生成，让标题保持短语化，描述优先取完整句子，不再出现省略号式截断。
    - 移除前端记忆选择列表和 skill 卡片上的强制 line-clamp 省略号。
  - 为了什么：
    - 避免助手建议污染用户画像、偏好、项目目标、workflow、daily_notes 或 skills。
    - 让普通注入更像“必要上下文”，而不是把大段存储结构和原始对话塞进当前会话。
    - 让前端展示保持简洁、自然，并减少半截文本和省略号带来的误读。
