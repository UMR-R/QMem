// Offscreen Document — 代理 Service Worker 的所有文件系统写操作
// Service Worker 无法调用 File System Access API 的写方法（浏览器安全限制），
// 通过此文档上下文中转，background.js 用 chrome.runtime.sendMessage 调用此处。

import { updateMemory } from "../background/memory_engine.js";
import { getDirHandle } from "../background/l2_wiki.js";

// ── 消息监听 ──────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.target !== "offscreen") return false;

  if (message.type === "UPDATE_MEMORY") {
    updateMemory(message.chatData, message.apiKey)
      .then(() => sendResponse({ ok: true }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true; // 异步响应
  }

  if (message.type === "WRITE_RAW") {
    _writeRaw(message.platform, message.chatId, message.chatData)
      .then(() => sendResponse({ ok: true }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  return false;
});

// ── 写 raw 对话记录 ───────────────────────────────────────────────────────────

async function _writeRaw(platform, chatId, chatData) {
  const root = await getDirHandle();
  if (!root) return; // 未选择目录，静默跳过

  const rawDir      = await root.getDirectoryHandle("raw",      { create: true });
  const platformDir = await rawDir.getDirectoryHandle(platform, { create: true });
  const fileHandle  = await platformDir.getFileHandle(`${chatId}.jsonl`, { create: true });

  const existingText = await (await fileHandle.getFile()).text();
  const newLines = chatData.rounds.map(r => JSON.stringify(r)).join("\n");
  const combined = existingText ? existingText.trimEnd() + "\n" + newLines : newLines;

  const writable = await fileHandle.createWritable();
  await writable.write(combined);
  await writable.close();
}
