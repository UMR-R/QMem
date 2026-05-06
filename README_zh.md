# QMem

<p align="center">
  <img src="docs/images/icon.png" alt="QMem logo" width="96">
</p>

[English](README.md)

QMem 是一个面向 AI 对话的浏览器扩展程序。它可以把你在 ChatGPT、Gemini、DeepSeek、豆包等平台上的对话保存到本地，整理成可查看、可勾选、可删除、可导出、可注入到新会话里的长期记忆。

它的使用方式很简单：加载扩展，配置本地后端和模型 API，在主页面点击“同步对话”，之后在“迁移”页整理和迁移记忆。设置页里的“同步记忆”开关可用于自动增量维护记忆。

## Quickstart

### 1. 下载并加载浏览器扩展

1. 下载本仓库源码，或下载 ZIP 后解压。
2. 打开浏览器扩展管理页。
   - Chrome / Arc / Brave：`chrome://extensions/`
   - Edge：`edge://extensions/`
3. 打开“开发者模式”。
4. 点击“加载已解压的扩展程序”。
5. 选择仓库根目录：

```text
QMem/
```

加载成功后，工具栏里会出现 QMem 扩展图标。


### 2. 认识三个主要页面

主页面用于开启同步、进入迁移、设置和 Skill 管理。

![QMem 主页面](docs/images/qmem-home.png)

设置页用于配置本地后端、模型 API、“本地目录”和高级开关。

![QMem 设置页](docs/images/qmem-settings.png)

迁移页用于整理记忆、勾选记忆、导出记忆包，或把记忆注入当前 AI 会话。

![QMem 迁移页](docs/images/qmem-organize.png)

<!-- 如果上面的图片没有显示，请把截图放到：

```text
docs/images/qmem-home.png
docs/images/qmem-settings.png
docs/images/qmem-organize.png
``` -->

### 3. 配置本地后端、模型和本地目录

QMem 的扩展界面会调用本机的 API 后端来保存文件、整理记忆和调用模型。首次使用时，在仓库根目录安装依赖：

```bash
pip install -r backend_service/requirements.txt
```



然后打开扩展的“设置”页，至少填写：

- `本地后端地址`：推荐 `http://127.0.0.1:8765`
- `API Key`：用于整理记忆的模型 API Key
- `本地目录`：本地记忆文件夹，建议选择一个可以长期保留的位置


当前后端默认使用 OpenAI-compatible 接口，默认模型配置为：

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

使用时启动本地后端：

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

### 4. 开启同步并整理记忆

1. 在主页面点击“同步对话”。设置页里的“同步记忆”开关用于控制是否在同步后进一步做增量记忆维护。
2. 在支持的平台继续聊天，QMem 会把原始对话保存到本地。
3. 进入“迁移”页，点击“整理记忆”。
4. 整理完成后，你可以勾选用户画像、偏好设置、项目记忆、工作流、日常记忆和 Skill。
5. 点击“导出”生成迁移包，或点击“注入”把选中的记忆写入当前 AI 会话。

## 三个核心模块

### 1. 浏览器扩展

扩展负责和用户交互，也负责从当前网页采集或注入内容。

主页面：

- 开启或暂停“同步对话”。
- 显示同步状态。
- 进入迁移、设置和 Skill 页面。

设置页：

- 配置“本地后端地址”。
- 配置“API Key”，并点击“测试连接”检查模型 API。
- 设置“本地目录”。
- 点击“导入对话”导入历史对话文件，支持 `json`、`jsonl`、`md`、`txt`。
- 打开或关闭“同步记忆”。
- 打开或关闭“详细注入”。
- 点击“清理所有记忆”或“清理缓存”管理本地数据。

迁移页：

- `加入当前对话`：把当前标签页的对话保存到本地 raw 记忆。
- `加入平台记忆`：让当前 AI 平台汇报它已经保存的 memory、custom instructions、agent config 和 skills，并保存为平台记忆快照。
- `整理记忆`：从 raw 对话和平台记忆中重建结构化长期记忆。
- `导出`：导出勾选的记忆包。
- `注入`：把勾选的记忆注入当前 AI 会话。

Skill 页面：

- 查看后端推荐 Skill。
- 点击“加入我的 Skill”保存推荐 Skill。
- 点击“导出”或“注入当前会话”使用 Skill。
- 管理已经保存的 Skill。

### 2. 本地后端

本地后端位于 `backend_service/`，主要负责：

- 读写本地记忆文件。
- 维护设置项。
- 调用模型 API 整理记忆。
- 生成前端展示用的标题和摘要。
- 生成导出包和注入内容。
- 管理推荐 Skill 和已保存 Skill。


如果扩展提示后端不可用，先确认：

- 后端进程正在运行。
- 设置页里的“本地后端地址”与启动端口一致。
- 浏览器没有拦截本地请求。
- API Key 和模型配置可用。

### 3. 本地记忆文件

QMem 会把所有原始对话和结构化记忆写到你设置的本地目录。没有设置时，默认使用：

```text
backend_service/.state/wiki/
```

建议在设置页选择一个你能长期保留的本地文件夹。这个文件夹就是你的本地记忆库。

## 记忆层级

QMem 的记忆使用分层管理：

### Raw

原始对话层，保留从网页采集或文件导入的原始聊天内容。

对应目录：

```text
raw/
```

后续记忆都能追溯到 raw 对话。

### Platform Memory

平台记忆层，保存 AI 平台已经持有或生成的记忆信号，例如：

- saved memory
- conversation summary
- profile / preferences
- custom instructions
- agent config
- platform skills

对应目录：

```text
platform_memory/
```


### Episodes

episode 是从 raw 对话中提取出来的对话级记忆单元。当前实现以一轮对话为主要粒度，同时保留它所属的会话、时间、摘要、关键词、turn refs 和 episode connection。

对应目录：

```text
episodes/
```

episode 是后续 profile、preferences、projects、workflows、daily notes 和 skills 的基础证据。

### Persistent Memory

长期记忆层，把 episodes 和平台记忆整理成更稳定的结构：

- `profile/`：用户画像，例如身份、知识背景、长期关注方向。
- `preferences/`：偏好设置，例如语言偏好、表达风格、格式约束、主要任务类型。
- `projects/`：项目记忆，例如长期项目、当前阶段、目标、上下文和状态。
- `workflows/`：工作流 / SOP，例如用户反复使用的方法、流程和协作习惯。
- `daily_notes/`：日常记忆，例如生活偏好、选择习惯、非项目类上下文。
- `skills/`：用户保存或推荐的 Skill 资产。
- `metadata/`：索引、整理状态、展示文案和删除/忽略记录。

这些内容会在前端以可勾选条目展示。你可以删除不想保留的条目。删除后，QMem 会记录 ignore / lock，避免下次整理时把同一条记忆又自动生成回来。

## 注入和导出

整理完成后，可以在“迁移”页选择要迁移的记忆。

普通注入：

- 注入结构化记忆节点。
- 注入相关 episode summary。
- 不默认注入大段 raw 对话。

详细注入：

- 注入结构化记忆节点。
- 注入 episode summary。
- 额外注入相关 raw turns，用于需要完整上下文的场景。

导出：

- 生成可迁移的记忆包。
- 可用于备份、复制到其他设备，或迁移到其他 AI 平台。

## 同步机制

QMem 有两个相关开关：

- `同步对话`：主页面按钮，用于持续保存当前平台的新对话到本地 raw 层。
- `同步记忆`：设置页高级选项，用于控制同步后是否进一步做增量记忆维护。

常见使用方式：

1. 打开同步。
2. 正常和 AI 聊天。
3. 之后进入迁移页点击“整理记忆”。
4. 选择需要的记忆导出或注入。

## 仓库结构

- `popup/`：扩展弹窗页面。
- `content/`：页面侧采集与注入逻辑。
- `background/`：扩展后台逻辑和增量同步。
- `backend_service/`：本地 FastAPI 后端与推荐 Skill 目录。
- `prompts/`：运行时 prompt。
- `memory_transferor/`：Python 记忆流水线、存储模型、策略和导出工具。
