# Memory Assistant

A Chrome extension for exporting and importing AI conversation memories across platforms (ChatGPT, Gemini, DeepSeek, Doubao).

## How it works

Memories are stored in two layers:
- **Episodic**: raw per-conversation exports saved to a local directory
- **Persistent**: cross-session patterns distilled by DeepSeek API, with confidence levels and supporting evidence

## Supported platforms

| Platform | Domain |
|---|---|
| ChatGPT | chatgpt.com / chat.openai.com |
| Google Gemini | gemini.google.com |
| DeepSeek | chat.deepseek.com |
| Doubao (豆包) | www.doubao.com |

## Installation

### 1. Get a DeepSeek API key

Sign up at [platform.deepseek.com](https://platform.deepseek.com) and create an API key.

### 2. Load the extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `memory_assistant` folder (the root of this repo)
5. The extension icon will appear in your toolbar

### 3. First-time setup

1. Click the extension icon to open the popup
2. Click **设置** next to "API Key: 未配置" and enter your DeepSeek API key, then click **保存**
3. Click **选择目录** to choose a local folder where memory files will be saved

## Usage

### Export memory from a conversation

1. Navigate to any supported AI platform and have a conversation
2. Click the extension icon
3. Click **导出并保存记忆**
4. The extension injects a structured extraction prompt into the chat, waits for the AI to respond, then automatically tags and saves the memory

### Consolidate similar nodes

After multiple exports, click **整理节点（合并相似）** to merge semantically similar persistent nodes (e.g., multiple sub-topics grouped under one subject area).

### Import memory into a new conversation

1. Start a new conversation on any supported platform
2. Click the extension icon → **按标签导入记忆**
3. Check the persistent nodes you want to load
4. Click **确认导入选中节点**
5. The extension uploads a memory package to the AI and sends a cold-start prompt

## Local data layout

```
<your chosen directory>/
├── index.json          # master index: episodic metadata + all persistent nodes
└── ep/
    ├── ep_0001.json    # raw episodic export
    └── ep_0002.json
```

## Troubleshooting

- **Buttons don't work / selectors broken**: AI platforms update their UI frequently. Open DevTools → Elements, find the input box or send button, and update the matching selectors in `content/content.js` under the relevant platform entry in `PLATFORMS`.
- **DeepSeek API error**: Check that your API key is valid and has sufficient balance.
- **Permission denied on directory**: Click the directory button again to re-authorize.
