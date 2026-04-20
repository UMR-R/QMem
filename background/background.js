// Background Service Worker
// 职责：消息路由、对话捕获、LLM 增量处理（存入 chrome.storage.local）。
// 注意：File System Access API 写操作无法在 Service Worker 中执行，
//       文件同步由 popup.js 在打开时自动完成。

import { updateMemory, processConversationsBatch } from "./memory_engine.js";

// ── 消息监听 ──────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "SAVE_DOCUMENT") {
    saveDocument(message.text, message.platform ?? "ai", message.isMemory ?? false);

  } else if (message.type === "ROUND_CAPTURED") {
    handleRoundCaptured(message).catch(console.error);

  } else if (message.type === "FLUSH_NOW") {
    flushPending()
      .then(() => sendResponse({ ok: true }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;

  } else if (message.type === "PROCESS_ALL_RAW") {
    processAllRaw(message.limit ?? 10)
      .then(result => sendResponse({ ok: true, ...result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true;
  }
});

// ── 安装 / 启动 ───────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Background] 插件已安装");
  _ensureAlarm();
});

chrome.runtime.onStartup.addListener(() => {
  _ensureAlarm();
});

function _ensureAlarm() {
  chrome.alarms.get("flush", alarm => {
    if (!alarm) chrome.alarms.create("flush", { periodInMinutes: 15 });
  });
}

// ── Idle 检测 ─────────────────────────────────────────────────────────────────

chrome.idle.onStateChanged.addListener(state => {
  if (state === "idle") flushPending().catch(console.error);
});

// ── 定时 flush ────────────────────────────────────────────────────────────────

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "flush" || alarm.name === "flush_soon") {
    flushPending().catch(console.error);
  }
});

// ── 处理捕获到的对话轮次 ──────────────────────────────────────────────────────

async function handleRoundCaptured(message) {
  const { chatId, platform, url, userText, assistantText, timestamp } = message;
  const storageKey = `chat:${platform}:${chatId}`;
  const chatRef = `${platform}:${chatId}`;

  const data = await chrome.storage.local.get([storageKey, "pending_flush"]);
  const chatData = data[storageKey] ?? {
    platform, url,
    first_seen: timestamp,
    last_updated: timestamp,
    rounds: [],
  };

  // 去重：user+assistant 完全相同则跳过（防止 content.js 重复触发或页面刷新重捕获）
  const isDuplicate = chatData.rounds.some(r => r.user === userText && r.assistant === assistantText);
  if (isDuplicate) {
    console.log(`[Background] 跳过重复 round: ${chatRef}`);
    return;
  }
  chatData.rounds.push({ timestamp, user: userText, assistant: assistantText });
  chatData.last_updated = timestamp;

  const pending = data["pending_flush"] ?? [];
  if (!pending.includes(chatRef)) pending.push(chatRef);

  await chrome.storage.local.set({
    [storageKey]: chatData,
    pending_flush: pending,
  });

  // 立即触发 LLM 处理（fire and forget）
  flushPending().catch(console.error);
}

// ── Flush：LLM 增量处理，结果存入 chrome.storage.local ───────────────────────

async function flushPending() {
  const data = await chrome.storage.local.get(
    ["pending_flush", "keepUpdated", "realtimeUpdate", "deepseek_api_key"]
  );
  const pending = data["pending_flush"] ?? [];
  if (pending.length === 0 || !data["keepUpdated"]) return;

  const done = [];
  for (const chatRef of pending) {
    const [platform, ...rest] = chatRef.split(":");
    const chatId = rest.join(":");
    const storageKey = `chat:${platform}:${chatId}`;

    const chatResult = await chrome.storage.local.get(storageKey);
    const chatData = chatResult[storageKey];
    if (!chatData) { done.push(chatRef); continue; }

    // LLM 增量更新：只处理上次 flush 之后新增的 rounds，避免重复
    if (data["realtimeUpdate"] && data["deepseek_api_key"]) {
      const lastIdx = chatData.last_processed_idx ?? 0;
      const newRounds = chatData.rounds.slice(lastIdx);
      if (newRounds.length > 0) {
        try {
          await updateMemory(
            { platform: chatData.platform, url: chatData.url, rounds: newRounds },
            data["deepseek_api_key"]
          );
          // 更新已处理索引并写回 storage
          chatData.last_processed_idx = chatData.rounds.length;
          await chrome.storage.local.set({ [storageKey]: chatData });
          console.log(`[Background] 记忆已更新: ${chatRef}（处理了 ${newRounds.length} 条新 rounds）`);
        } catch (err) {
          console.error("[Background] memory_engine 更新失败:", err.message);
        }
      }
    }

    done.push(chatRef);
  }

  const remaining = pending.filter(ref => !done.includes(ref));
  await chrome.storage.local.set({ pending_flush: remaining });
}

// ── 批量提取 episode：处理所有未经 LLM 处理的 RAW rounds ────────────────────
// 扫描所有 chat:* 条目，对 last_processed_idx 之后的 rounds 调用 memory_engine。
// 适用于 realtimeUpdate=false 期间捕获的对话，在同步时补充 episode 提取。

let _processAllRawRunning = false;

async function processAllRaw(limit = 10) {
  if (_processAllRawRunning) throw new Error("Episode extraction is already running, please wait");
  const settings = await chrome.storage.local.get(["deepseek_api_key"]);
  const apiKey = settings["deepseek_api_key"];
  if (!apiKey) throw new Error("DeepSeek API Key not configured");

  _processAllRawRunning = true;
  await chrome.storage.local.remove(["_raw_progress", "_sw_keepalive"]);

  const allData = await chrome.storage.local.get(null);
  const chatKeys = Object.keys(allData).filter(k => k.startsWith("chat:"));

  const pendingKeys = chatKeys.filter(k => {
    const d = allData[k];
    if (!d?.rounds?.length) return false;
    return (d.last_processed_idx ?? 0) < d.rounds.length;
  });

  const batchKeys = pendingKeys.slice(0, limit);
  const remaining = pendingKeys.length - batchKeys.length;

  const _keepaliveTimer = setInterval(
    () => chrome.storage.local.set({ _sw_keepalive: Date.now() }),
    20000
  );

  try {
    // Read fresh data for each key and build items array
    const items = (await Promise.all(
      batchKeys.map(async storageKey => {
        const res = await chrome.storage.local.get(storageKey);
        const chatData = res[storageKey];
        if (!chatData?.rounds?.length) return null;
        const lastIdx = chatData.last_processed_idx ?? 0;
        if (lastIdx >= chatData.rounds.length) return null;
        return {
          storageKey,
          originalRoundCount: chatData.rounds.length,
          chatData: { platform: chatData.platform, url: chatData.url, rounds: chatData.rounds.slice(lastIdx) },
        };
      })
    )).filter(Boolean);

    const skippedUpfront = batchKeys.length - items.length;
    if (!items.length) return { processed: 0, skipped: skippedUpfront, remaining };

    // Process all conversations in parallel (4 concurrent LLM calls)
    // @ts-ignore — TS can't infer async return type from plain JS module
    const { processed, skipped, succeededIndices } = await processConversationsBatch(items, apiKey, {
      concurrency: 4,
      onProgress: (done, total) => {
        chrome.storage.local.set({
          _raw_progress: { current: done, total, storageKey: items[Math.min(done, items.length - 1)].storageKey },
        }).catch(() => {});
      },
    });

    // Update last_processed_idx for succeeded conversations only
    if (succeededIndices.length) {
      const updates = {};
      await Promise.all(succeededIndices.map(async i => {
        const { storageKey, originalRoundCount } = items[i];
        const fresh = await chrome.storage.local.get(storageKey);
        if (fresh[storageKey]) {
          fresh[storageKey].last_processed_idx = originalRoundCount;
          updates[storageKey] = fresh[storageKey];
        }
      }));
      if (Object.keys(updates).length) await chrome.storage.local.set(updates);
    }

    console.log(`[Background] processAllRaw: processed=${processed} skipped=${skippedUpfront + skipped} remaining=${remaining}`);
    return { processed, skipped: skippedUpfront + skipped, remaining };

  } finally {
    _processAllRawRunning = false;
    clearInterval(_keepaliveTimer);
    await chrome.storage.local.remove(["_raw_progress", "_sw_keepalive"]);
  }
}

// ── 调试入口 ──────────────────────────────────────────────────────────────────
// Service Worker DevTools Console 中直接调用：flushNow()

self.flushNow = flushPending;

// ── 下载文件（保留原有功能）──────────────────────────────────────────────────

function saveDocument(rawText, platform, isMemory) {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const prefix = isMemory ? `${platform}-记忆-` : `${platform}-`;

  const jsonStart = rawText.indexOf("{");
  const isJson = jsonStart !== -1 && (() => {
    try { JSON.parse(rawText.slice(jsonStart)); return true; } catch { return false; }
  })();

  if (isJson) {
    chrome.downloads.download({
      url: "data:application/json;charset=utf-8," + encodeURIComponent(rawText.slice(jsonStart)),
      filename: `${prefix}${timestamp}.json`,
      saveAs: true,
    });
  } else {
    chrome.downloads.download({
      url: "data:text/markdown;charset=utf-8," + encodeURIComponent(rawText),
      filename: `${prefix}${timestamp}.md`,
      saveAs: true,
    });
  }
}
