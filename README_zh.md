# QMem

[English](README.md)

QMem 是一个由 Chrome 插件、本地 FastAPI 后端和 Python 记忆整理流水线组成的项目，用来采集 AI 对话、整理结构化长期记忆，并把这些记忆迁移到其他平台。

当前仓库由三部分协同工作：

- `popup/`、`content/`、`background/`：Chrome 插件界面、页面侧采集与后台同步逻辑。
- `backend_service/`：插件调用的本地 HTTP 后端。
- `llm_memory_transferor/`：负责构建和更新结构化记忆的 Python 记忆流水线。

## 当前支持的能力

- 从 ChatGPT、Gemini、DeepSeek、豆包等已适配站点采集对话。
- 将当前会话导入本地记忆库。
- 让当前平台汇报它保存的 memory、custom instructions、agent config 和 skills，并将快照导入本地。
- 从 raw conversations 重建结构化记忆。
- 在开启“同步记忆”后，对新对话做增量更新。
- 导出勾选的记忆内容为迁移包。
- 将记忆包或 Skill 注入到当前会话。
- 管理“我的 Skill”和后端推荐 Skill。

## 快速开始

### 1. 启动本地后端

在仓库根目录执行：

```bash
pip install -r backend_service/requirements.txt
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

推荐后端地址：

```text
http://127.0.0.1:8765
```

`backend_service/requirements.txt` 是本地后端首次安装时建议使用的入口，
其中已经包含 `backend_service.app` 间接依赖的
`llm_memory_transferor` 运行时依赖。

### 2. 从这个仓库加载 Chrome 插件

1. 打开 Chrome，进入 `chrome://extensions/`
2. 打开右上角 `Developer mode`
3. 点击 `Load unpacked`
4. 选择仓库根目录：

```text
QMem/
```

不要只选 `popup/` 或 `background/`，因为插件清单位于仓库根目录的：

```text
manifest.json
```

加载成功后，你应该能在扩展列表里看到 `QMem`。

### 3. 固定插件并打开 popup

1. 点击 Chrome 工具栏中的扩展图标
2. 将 `QMem` 固定到工具栏
3. 点击插件图标打开 popup

如果 popup 打不开或显示异常，先回到 `chrome://extensions/` 检查该扩展的报错。

### 4. 配置 popup

在 `设置` 页面填写：

- `Backend URL`：通常是 `http://127.0.0.1:8765`
- `API Key`：你的模型服务密钥
- `Local storage directory`：本地记忆和原始对话的存储目录

当前后端默认值为：

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

默认情况下，`整理记忆` 和增量更新会使用后端的 LLM 配置；
平台记忆采集则主要依赖当前 AI 网页上的返回结果。

### 5. 先积累对话数据，再构建记忆

目前主要有两种方式把原始对话数据放进本地记忆库：

- `导入历史`：在 popup 的 `设置` 页面导入本地 `json`、`jsonl`、`md`、`txt` 聊天导出文件
- `同步对话`：在 popup 首页打开 `同步对话`，然后继续在支持的 AI 平台上聊天，由插件实时捕获新的对话轮次

当已经积累了原始对话之后，进入 `迁移` 页面，点击 `整理记忆`，系统会重建：

- episodes
- profile
- preferences
- projects
- workflows
- daily notes / persistent nodes

### 6. 导出或注入记忆

整理完成后：

1. 打开 `迁移`
2. 勾选需要的记忆内容
3. 点击 `导出` 生成迁移包，或点击 `注入` 注入到当前 AI 会话

### 7. 使用 Skill 页面

`Skill` 页面支持：

- 把推荐 Skill 保存到“我的 Skill”
- 导出 Skill
- 向当前会话注入 Skill
- 管理后端提供的 Skill 资产

## 当前运行流程

1. 插件采集原始对话，或手动导入会话。
2. 原始聊天记录写入本地记忆目录。
3. 点击 `整理记忆` 后调用 `POST /api/memory/organize`。
4. 后端使用 `MemoryBuilder` 重建：
   - episodes
   - profile
   - preferences
   - projects
   - workflows
5. 后端继续把长期 persistent nodes 蒸馏到 `interest_discoveries/`。
6. 如果开启实时记忆同步，新对话还会通过 `MemoryUpdater` 和 background memory engine 做增量维护。

## Popup 页面说明

### 首页

- `同步对话`：开启或关闭后台对话采集。
- `迁移`：进入记忆整理、勾选、导出、注入页面。
- `设置`：配置后端地址、API Key、本地目录和实时记忆更新。
- `Skill`：管理个人 Skill、推荐 Skill、导出和注入。

### 迁移页

- `整理记忆`：从本地 raw conversations 重建结构化记忆。
- `加入当前对话`：把当前标签页中的会话导入后端。
- `加入平台记忆`：采集当前平台已保存的 memory / custom instructions / agent config / skills，再导入后端。
- `导出`：导出勾选的记忆包。
- `注入`：将勾选的记忆内容注入到当前 AI 会话。

### 设置页

- 本地后端地址
- API Key
- 本地存储目录
- 实时记忆更新开关
- `json/jsonl/md/txt` 历史对话导入
- 临时缓存清理

## 本地后端

插件依赖 `backend_service/` 中的本地 FastAPI 后端。对于日常使用，
最关键的是保证后端已经启动，并且 popup 中配置的 backend URL 可访问。

## 默认 LLM 配置

后端默认值为：

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

默认情况下，`整理记忆` 和增量更新走后端 LLM；“加入平台记忆”主要依赖当前网页上的 AI 返回结果。

## 当前使用中的 Prompt

运行时 prompt 现在统一放在 `prompts/` 目录，由插件、后端和 Python 流水线共同使用。

| 文件 | 使用方 | 用途 |
|---|---|---|
| `prompts/cold_start.txt` | popup 注入流程 | 记忆迁移时的冷启动 prompt |
| `prompts/platform/platform_memory_collect.txt` | popup 平台记忆采集流程 | 采集当前平台保存的记忆和 agent 配置 |
| `prompts/episodes/episode_system.txt` | `MemoryBuilder` | 整理记忆时抽取 episode |
| `prompts/episodes/delta_system.txt` | `MemoryUpdater` 和 background engine | 增量记忆更新 |
| `prompts/nodes/profile_system.txt` | `MemoryBuilder` | 重建 profile |
| `prompts/nodes/preferences_system.txt` | `MemoryBuilder` | 重建 preferences |
| `prompts/nodes/projects_system.txt` | `MemoryBuilder` | 重建 projects |
| `prompts/nodes/workflows_system.txt` | `MemoryBuilder` | 重建 workflows |
| `prompts/nodes/daily_notes_system.txt` | backend 和 background engine | daily notes 持久节点蒸馏 |
| `prompts/nodes/skills_system.txt` | memory policy / 后续 skill 流程 | 保存和推荐的 skill 记忆 |
| `prompts/display/display_taxonomy_proposal.txt` | memory display policy | 可选的前端展示分类建议 |
| `prompts/schema.txt` | backend/background persistent-node 流程 | schema 上下文 |

## 记忆目录结构

当设置了 `storage_path` 时，后端会把数据写到该目录；否则默认写到 `backend_service/.state/wiki/`。

当前记忆根目录主要包含：

- `raw/`：原始对话
- `platform_memory/`：平台记忆快照
- `episodes/`：对话级 episodic 记忆
- `profile/`：用户画像
- `preferences/`：偏好设置
- `projects/`：项目记忆
- `workflows/`：工作流 / SOP
- `skills/`：已保存的 Skill
- `interest_discoveries/`：蒸馏出的 persistent nodes
- `metadata/`：索引、整理状态、展示文案

仓库里已提交了一份示例记忆库：`llm_mem4/`。

## 仓库结构

- `popup/`：插件弹窗页面
- `content/`：页面侧采集与注入逻辑
- `background/`：service worker 与增量记忆引擎
- `backend_service/`：本地 FastAPI 后端与推荐 Skill 目录
- `prompts/`：可直接编辑的运行时 prompt
- `llm_memory_transferor/`：Python 记忆库、CLI、导出器、测试与评测脚本
- `llm_mem4/`：系统生成的示例记忆存储目录

## 补充说明

- Popup 当前适配的 host 包括 `chatgpt.com`、`chat.openai.com`、`gemini.google.com`、`chat.deepseek.com`、`www.doubao.com`。
- 保存设置后，popup 会用可复制文本的弹窗提示启动后端命令，而不是原生 `alert`。
- 项目里已经补了一些面向 Windows 的 UTF-8 兼容修复。
- 如果 popup 动作失败，可以在 `chrome://extensions/` 中打开该扩展的 popup console 查看报错。
