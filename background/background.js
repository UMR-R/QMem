// Background Service Worker
// 职责：消息路由、对话捕获、LLM 增量处理（存入 chrome.storage.local）。
// 注意：File System Access API 写操作无法在 Service Worker 中执行，
//       文件同步由 popup.js 在打开时自动完成。

import { updateMemory } from "./memory_engine.js";

async function _forwardRoundToLocalBackend(message) {
  const settings = await chrome.storage.local.get(["backend_url"]);
  const backendUrl = (settings["backend_url"] || "http://127.0.0.1:8765").replace(/\/$/, "");

  try {
    await fetch(`${backendUrl}/api/conversations/append`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        platform: message.platform,
        chat_id: message.chatId,
        url: message.url,
        timestamp: message.timestamp,
        user_text: message.userText,
        assistant_text: message.assistantText,
      }),
    });
  } catch (err) {
    console.warn("[Background] 本地后端未连接，跳过 append:", err.message);
  }
}

// ── 消息监听 ──────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "SAVE_DOCUMENT") {
    saveDocument(message.text, message.platform ?? "ai", message.isMemory ?? false);
    sendResponse?.({ ok: true });

  } else if (message.type === "ROUND_CAPTURED") {
    sendResponse({ ok: true });
    handleRoundCaptured(message).catch(err => {
      console.error("[Background] ROUND_CAPTURED 处理失败:", err);
    });
    return false;

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

  } else if (message.type === "GET_CAPTURE_STATE") {
    chrome.storage.local.get(["keepUpdated", "realtimeUpdate", "deepseek_api_key"], data => {
      sendResponse({
        ok: true,
        keepUpdated: Boolean(data["keepUpdated"]),
        realtimeUpdate: Boolean(data["realtimeUpdate"]),
        apiKeyConfigured: Boolean(data["deepseek_api_key"]),
      });
    });
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

  _forwardRoundToLocalBackend(message).catch(console.error);

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
  if (_processAllRawRunning) throw new Error("episode 提取已在运行中，请稍候");
  const settings = await chrome.storage.local.get(["deepseek_api_key"]);
  const apiKey = settings["deepseek_api_key"];
  if (!apiKey) throw new Error("DeepSeek API Key 未配置");

  _processAllRawRunning = true;

  // 清除上次可能残留的进度（SW 被杀时 finally 未能执行）
  await chrome.storage.local.remove(["_raw_progress", "_sw_keepalive"]);

  const allData = await chrome.storage.local.get(null);
  const chatKeys = Object.keys(allData).filter(k => k.startsWith("chat:"));

  // 用缓存数据快速筛出有待处理 rounds 的 key，不做额外 storage 读取
  const pendingKeys = chatKeys.filter(k => {
    const d = allData[k];
    if (!d?.rounds?.length) return false;
    return (d.last_processed_idx ?? 0) < d.rounds.length;
  });

  const batchKeys  = pendingKeys.slice(0, limit);
  const remaining  = pendingKeys.length - batchKeys.length;
  const total      = batchKeys.length;

  let processed = 0, skipped = 0;

  // Chrome MV3 Service Worker 会在无活动约 30s 后休眠。
  // 每次 storage 写入会重置计时，但 API 调用耗时较长时额外加一个 keepalive ping。
  const _keepaliveTimer = setInterval(
    () => chrome.storage.local.set({ _sw_keepalive: Date.now() }),
    20000
  );

  try {
    for (let i = 0; i < batchKeys.length; i++) {
      const storageKey = batchKeys[i];

      // 写进度（popup 轮询读取）；total 是本批次大小，让进度条不超出
      await chrome.storage.local.set({
        _raw_progress: { current: i, total, storageKey },
      });

      // 重新读最新数据，防止并发写入导致索引过时
      const fresh = await chrome.storage.local.get(storageKey);
      const chatData = fresh[storageKey];
      if (!chatData?.rounds?.length) { skipped++; continue; }

      const lastIdx = chatData.last_processed_idx ?? 0;
      if (lastIdx >= chatData.rounds.length) { skipped++; continue; }

      const newRounds = chatData.rounds.slice(lastIdx);

      try {
        // batchMode: 整条对话一次 API 调用（比逐轮快 N 倍）
        await updateMemory(
          { platform: chatData.platform, url: chatData.url, rounds: newRounds },
          apiKey,
          { batchMode: true }
        );
        // 成功后更新索引（读最新，避免覆盖并发写入）
        const toUpdate = await chrome.storage.local.get(storageKey);
        if (toUpdate[storageKey]) {
          toUpdate[storageKey].last_processed_idx = chatData.rounds.length;
          await chrome.storage.local.set({ [storageKey]: toUpdate[storageKey] });
        }
        processed++;
        console.log(`[Background] processAllRaw: ${storageKey} 处理了 ${newRounds.length} 条 rounds → 1 个 episode`);
      } catch (err) {
        console.error(`[Background] processAllRaw 处理失败 (${storageKey}):`, err.message);
        skipped++;
      }
    }
  } finally {
    _processAllRawRunning = false;
    clearInterval(_keepaliveTimer);
    await chrome.storage.local.remove(["_raw_progress", "_sw_keepalive"]);
  }

  return { processed, skipped, remaining };
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
