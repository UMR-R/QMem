<p align="center">
  <img src="docs/images/slogan.png" alt="QMem slogan" width="460">
</p>

<p align="center">
  <strong>Contributors:</strong> 徐锡楠、王浩然、胡心亭
</p>

<p align="center">
  <a href="README_en.md">English</a>
</p>

QMem 是一个面向 AI 对话的浏览器扩展程序。它可以把你在 ChatGPT、Gemini、DeepSeek、豆包等平台上的对话保存到本地，整理成可查看、可勾选、可删除、可导出、可注入到新会话里的长期记忆。

## 界面预览

<table>
  <tr>
    <td width="33%"><img src="docs/images/qmem-home.png" alt="QMem 主页面"></td>
    <td width="33%"><img src="docs/images/qmem-settings.png" alt="QMem 设置页"></td>
    <td width="33%"><img src="docs/images/qmem-organize.png" alt="QMem 迁移页"></td>
  </tr>
  <tr>
    <td align="center">主页面</td>
    <td align="center">设置页</td>
    <td align="center">迁移页</td>
  </tr>
</table>

## Quickstart

### 1. 加载扩展

1. 下载本仓库源码，或下载 ZIP 后解压。
2. 打开浏览器扩展管理页。
   - Chrome / Arc / Brave：`chrome://extensions/`
   - Edge：`edge://extensions/`
3. 打开“开发者模式”。
4. 点击“加载已解压的扩展程序”。
5. 选择仓库根目录 `QMem/`。

加载成功后，浏览器工具栏里会出现 QMem 扩展图标。

### 2. 启动本地后端

首次使用时，在仓库根目录安装依赖：

```bash
pip install -r backend_service/requirements.txt
```

使用时启动本地后端：

```bash
uvicorn backend_service.app:app --host 127.0.0.1 --port 8765 --reload
```

### 3. 配置设置页

打开扩展的“设置”页，填写：

- `本地后端地址`：推荐 `http://127.0.0.1:8765`
- `API Key`：用于整理记忆的模型 API Key
- `本地目录`：本地记忆文件夹，建议选择一个可以长期保留的位置

然后点击“保存”和“测试连接”。

当前后端默认使用 OpenAI-compatible 接口：

- `api_provider = openai_compat`
- `api_base_url = https://api.deepseek.com/v1`
- `api_model = deepseek-chat`

### 4. 同步、整理和迁移

1. 在主页面点击“同步对话”。
2. 按需在设置页打开“同步记忆”。
3. 继续在支持的平台聊天，或在迁移页点击“加入当前对话”“加入平台记忆”。
4. 进入“迁移”页，点击“整理记忆”。
5. 勾选需要的记忆，点击“导出”或“注入”。

## 页面功能

### 主页面

- `同步对话`：持续保存当前平台的新对话到本地 raw 层。
- `迁移`：进入记忆整理、勾选、导出和注入页面。
- `设置`：配置本地后端、API Key、本地目录和高级选项。
- `Skill`：管理“我的 Skill”和推荐 Skill。

### 设置页

- `本地后端地址`：本地 FastAPI 后端地址。
- `API Key`：模型服务密钥。
- `本地目录`：raw 对话和结构化记忆的保存目录。
- `导入对话`：导入 `json`、`jsonl`、`md`、`txt` 历史对话文件。
- `同步记忆`：同步对话后自动增量维护记忆。
- `详细注入`：注入时额外带上相关 raw turns。
- `清理所有记忆` / `清理缓存`：管理本地数据。

### 迁移页

- `加入当前对话`：把当前标签页的对话保存到本地 raw 记忆。
- `加入平台记忆`：保存当前 AI 平台汇报的 saved memory、custom instructions、agent config 和 platform skills。
- `整理记忆`：从 raw 对话和平台记忆中重建结构化长期记忆。
- `导出`：导出勾选的记忆包。
- `注入`：把勾选的记忆注入当前 AI 会话。

### Skill 页面

- `我的 Skill`：查看已保存 Skill。
- `为你推荐`：查看后端推荐 Skill。
- `加入我的 Skill`：保存推荐 Skill。
- `导出` / `注入当前会话`：迁移或使用 Skill。

## 本地记忆结构

默认记忆目录：

```text
backend_service/.state/wiki/
```

建议在设置页选择一个你能长期保留的本地文件夹。这个文件夹就是你的本地记忆库。

QMem 使用分层记忆：

- `raw/`：原始对话，保留网页采集或文件导入的聊天内容。
- `platform_memory/`：平台侧已经保存或生成的记忆信号。
- `episodes/`：从 raw 对话中提取的对话级记忆单元。
- `profile/`：用户画像，例如身份、知识背景、长期关注方向。
- `preferences/`：偏好设置，例如语言偏好、表达风格、格式约束、主要任务类型。
- `projects/`：项目记忆，例如长期项目、当前阶段、目标、上下文和状态。
- `workflows/`：工作流 / SOP，例如用户反复使用的方法、流程和协作习惯。
- `daily_notes/`：日常记忆，例如生活偏好、选择习惯、非项目类上下文。
- `skills/`：用户保存或推荐的 Skill 资产。
- `metadata/`：索引、整理状态、展示文案和删除 / 忽略记录。

删除不想保留的条目后，QMem 会记录 ignore / lock，避免下次整理时把同一条记忆又自动生成回来。

## 注入和导出

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

## 仓库结构

- `popup/`：扩展弹窗页面。
- `content/`：页面侧采集与注入逻辑。
- `background/`：扩展后台逻辑和增量同步。
- `backend_service/`：本地 FastAPI 后端与推荐 Skill 目录。
- `prompts/`：运行时 prompt。
- `memory_transferor/`：Python 记忆流水线、存储模型、策略和导出工具。
