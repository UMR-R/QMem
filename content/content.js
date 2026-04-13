// Content Script - 运行在目标网页中，可访问 DOM

// ═══════════════════════════════════════════════════════════════════════════════
//  平台配置
//  每个平台的选择器集中在此处，便于维护。
//  注意：各平台前端随时可能更新 DOM，若功能失效请在此处更新对应选择器。
// ═══════════════════════════════════════════════════════════════════════════════

const PLATFORMS = {
  "gemini.google.com": {
    name: "gemini",
    inputSelectors: [
      "rich-textarea [contenteditable='true']",
      "[contenteditable='true']",
    ],
    sendSelectors: [
      "button[aria-label='Send message']",
      "button[data-test-id='send-button']",
      "button[aria-label='提交']",
      "button[aria-label='发送消息']",
    ],
    stopSelectors: [
      "button[aria-label='Stop response']",
      "button[aria-label='停止生成']",
      "button[aria-label='Stop generating']",
    ],
    useClipboardPaste: true,
    getCopyButton() {
      const icons = document.querySelectorAll(
        'mat-icon[fonticon="content_copy"].embedded-copy-icon, mat-icon[fonticon="content_copy"]'
      );
      if (!icons.length) return null;
      const last = icons[icons.length - 1];
      return last.tagName === "BUTTON" ? last : last.closest("button");
    },
    responseSelectors: [
      "model-response",
      "message-content[data-author='model']",
      ".model-response-text",
      ".response-content",
    ],
    userSelectors: [
      "user-query .query-text",
      "user-query",
      "message-content[data-author='user']",
    ],
    getChatId: () => location.href.match(/\/app\/([^/?#]+)/)?.[1] ?? null,
  },

  "chatgpt.com": {
    name: "chatgpt",
    inputSelectors: [
      "#prompt-textarea",
      "div[contenteditable='true']",
    ],
    sendSelectors: [
      "button[data-testid='send-button']",
      "button[aria-label='Send prompt']",
      "button[aria-label='发送提示']",
    ],
    stopSelectors: [
      "button[aria-label='Stop streaming']",
      "button[data-testid='stop-button']",
    ],
    fileInputSelectors: ["input[type='file']"],
    attachmentButtonSelectors: [
      "button[aria-label='Attach files']",
      "button[aria-label='添加附件']",
      "button[data-testid='fruitjuice-attachment-button']",
    ],
    getCopyButton() {
      const btns = document.querySelectorAll(
        "button[aria-label='Copy'], button[data-testid='copy-turn-action-button']"
      );
      return btns[btns.length - 1] ?? null;
    },
    responseSelectors: [
      "[data-message-author-role='assistant'] .markdown",
      "[data-message-author-role='assistant']",
    ],
    userSelectors: [
      "[data-message-author-role='user'] .whitespace-pre-wrap",
      "[data-message-author-role='user']",
    ],
    getChatId: () => location.pathname.match(/\/c\/([^/?#]+)/)?.[1] ?? null,
  },

  "chat.deepseek.com": {
    name: "deepseek",
    inputSelectors: [
      "textarea#chat-input",
      "[contenteditable='true']",
      "textarea",
    ],
    sendSelectors: [
      "button[aria-label='发送']",
      "button.send-button",
      "button[type='submit']",
    ],
    stopSelectors: [
      "button[aria-label='停止响应']",
      "button[aria-label='停止生成']",
      "button.stop-button",
    ],
    fileInputSelectors: ["input[type='file']"],
    attachmentButtonSelectors: [
      "button[aria-label='上传文件']",
      "button[aria-label='附件']",
      "label[class*='upload']",
    ],
    getCopyButton() {
      const btns = document.querySelectorAll("button[class*='copy']");
      return btns[btns.length - 1] ?? null;
    },
    responseSelectors: [
      ".ds-markdown",
      ".markdown-body",
      "[class*='markdown']",
    ],
    userSelectors: [
      ".fbb737a4",           // DeepSeek user bubble class（可能随版本变化）
      "[class*='user-message']",
      "[class*='human']",
    ],
    getChatId: () => {
      // 新格式 /a/chat/s/{uuid}，旧格式 /chat/{uuid}
      // 取 /chat/ 之后的所有路径段并拼接为唯一 key
      const m = location.pathname.match(/\/chat\/(.+)/);
      if (m?.[1]) return m[1].replace(/\//g, "-");
      return location.href.match(/id=([^&]+)/)?.[1] ?? null;
    },
  },

  "www.doubao.com": {
    name: "doubao",
    inputSelectors: [
      "[contenteditable='true']",
      "textarea",
    ],
    sendSelectors: [
      "button[aria-label='发送']",
      "button[type='button'][class*='send']",
    ],
    stopSelectors: [
      "button[aria-label='停止生成']",
      "button[aria-label='Stop']",
    ],
    fileInputSelectors: ["input[type='file']"],
    attachmentButtonSelectors: [
      "button[aria-label='上传文件']",
      "button[aria-label='附件']",
      "button[class*='upload']",
    ],
    getCopyButton() {
      const btns = document.querySelectorAll(
        "button[aria-label='复制'], button[class*='copy']"
      );
      return btns[btns.length - 1] ?? null;
    },
    responseSelectors: [
      "[data-role='assistant']",
      "[class*='chat-message'][class*='assistant']",
      "[class*='message'][class*='bot']",
    ],
    userSelectors: [
      "[data-role='user']",
      "[class*='chat-message'][class*='user']",
      "[class*='message'][class*='human']",
    ],
    getChatId: () => location.pathname.match(/\/chat\/([^/?#]+)/)?.[1] ?? null,
  },
};

function getConfig() {
  const h = location.hostname;
  if (h === "chat.openai.com") return PLATFORMS["chatgpt.com"];
  return PLATFORMS[h] ?? null;
}

// ═══════════════════════════════════════════════════════════════════════════════
//  全对话抓取
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 按 DOM 顺序收集当前对话的所有消息，返回 [{role, text}, ...] 数组。
 */
function scrapeFullConversation(config) {
  const messages = [];

  // 收集用户消息
  for (const sel of (config?.userSelectors ?? [])) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) {
      els.forEach(el => {
        const text = el.innerText?.trim();
        if (text) messages.push({ role: "user", text, el });
      });
      break;
    }
  }

  // 收集 AI 回复
  for (const sel of (config?.responseSelectors ?? [])) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) {
      els.forEach(el => {
        const text = el.innerText?.trim();
        if (text) messages.push({ role: "assistant", text, el });
      });
      break;
    }
  }

  // 按 DOM 位置排序，恢复对话顺序
  messages.sort((a, b) => {
    const pos = a.el.compareDocumentPosition(b.el);
    return pos & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });

  return messages.map(({ role, text }) => ({ role, text }));
}

// ═══════════════════════════════════════════════════════════════════════════════
//  剪贴板拦截（平台通用）
//  clipboard_interceptor.js 运行在 MAIN world，覆盖页面的 clipboard API，
//  通过 postMessage 把写入内容传到这里。
// ═══════════════════════════════════════════════════════════════════════════════

let _lastClipboardText = null;

window.addEventListener("message", (e) => {
  if (e.source === window && e.data?.__ext_clipboard__) {
    _lastClipboardText = e.data.text;
  }
});

// ═══════════════════════════════════════════════════════════════════════════════
//  消息监听
// ═══════════════════════════════════════════════════════════════════════════════

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const config = getConfig();

  if (message.type === "SCRAPE") {
    sendResponse({ data: scrapePage() });

  } else if (message.type === "TOGGLE_CAPTURE") {
    if (message.enabled) startCapture();
    else stopCapture();
    sendResponse({ ok: true });

  } else if (message.type === "INJECT_INPUT") {
    const result = injectInput(message.text, false, config);
    sendResponse(result);

  } else if (message.type === "SUBMIT_AND_WAIT") {
    const el = findInputElement(config);
    if (!el) { sendResponse({ ok: false, error: "未找到输入框" }); return; }
    // 立即应答，不持有 channel —— 防止 SPA 导航时 content script 被卸载导致 channel 断
    sendResponse({ ok: true });
    const jobId = message.jobId;
    const waitTimeout = message.timeoutMs ?? 90000;
    submitWithRetry(el, config)
      .then(submitted => {
        if (!submitted) throw new Error("发送失败：未能触发发送按钮，请确认页面已加载完成");
        return waitForResponse(config, waitTimeout);
      })
      .then(({ text, source }) => {
        if (message.prompt && !message.skipDownload) {
          chrome.runtime.sendMessage({ type: "SAVE_DOCUMENT", text, platform: config?.name ?? "ai", isMemory: message.isMemory ?? false });
        }
        chrome.storage.local.set({ [jobId]: { ok: true, source, text } });
      })
      .catch(err => {
        chrome.storage.local.set({ [jobId]: { ok: false, error: err.message } });
      });

  } else if (message.type === "UPLOAD_FILE") {
    uploadFile(message.fileBuffer, message.fileName, message.promptText, config)
      .then(result => sendResponse(result))
      .catch(err => sendResponse({ ok: false, error: err.message }));

  }

  return true;
});

// ═══════════════════════════════════════════════════════════════════════════════
//  输入注入
// ═══════════════════════════════════════════════════════════════════════════════

function injectInput(text, shouldSubmit, config) {
  const el = findInputElement(config);
  if (!el) return { ok: false, error: "未找到输入框" };

  try {
    el.focus();

    if (el.isContentEditable) {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
    } else {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        el.tagName === "TEXTAREA"
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype,
        "value"
      ).set;
      nativeSetter.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }

    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

function findInputElement(config) {
  const selectors = config?.inputSelectors ?? [
    "[contenteditable='true']",
    "textarea:not([readonly]):not([disabled])",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

// 重试发送：每 500ms 点一次发送键，直到输入框内容明显缩短（被清空）或出现停止按钮。
// 返回 true 表示发送成功，false 表示超时未成功。
// 注意：不能用"内容变了"作为成功标志——DeepSeek 等平台按 Enter 只会加换行，
// 内容变长不等于发送，需要内容长度明显缩短（< 原始的一半）才认为被清空。
async function submitWithRetry(el, config, timeoutMs = 30000) {
  const getContent = () =>
    (el.value !== undefined ? el.value : el.textContent ?? "").trim();
  const originalLen = getContent().length;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    submitInput(el, config);
    await new Promise(r => setTimeout(r, 500));
    if (getContent().length < originalLen * 0.5 || findStopButton(config)) return true;
  }
  return false;
}

function submitInput(el, config) {
  const selectors = config?.sendSelectors ?? [
    "button[aria-label='Send message']",
    "button[aria-label='发送']",
    "button[type='submit']",
  ];
  for (const sel of selectors) {
    const btn = document.querySelector(sel);
    if (btn && !btn.disabled && btn.getAttribute("aria-disabled") !== "true") { btn.click(); return; }
  }
  // 找不到发送按钮时降级用 Enter 键
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup",   { key: "Enter", keyCode: 13, bubbles: true }));
}

// ═══════════════════════════════════════════════════════════════════════════════
//  等待回复
// ═══════════════════════════════════════════════════════════════════════════════

function waitForResponse(config, timeoutMs = 90000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    let phase = "wait-start";      // wait-start → wait-end | wait-stable
    let phaseEnteredAt = Date.now();
    let lastContent = null;
    let stableCount = 0;
    const STABLE_NEEDED = 6;       // 6 × 500ms = 3s 内容不变则判定完成

    const finish = () => {
      clearInterval(timer);
      extractLastResponse(config).then(({ text, source }) => {
        if (text) resolve({ text, source });
        else reject(new Error("未能提取到回复内容"));
      });
    };

    const timer = setInterval(() => {
      if (Date.now() > deadline) {
        clearInterval(timer);
        reject(new Error(`等待回复超时（${Math.round(timeoutMs / 1000)}s）`));
        return;
      }

      const stopBtn = findStopButton(config);

      if (phase === "wait-start") {
        if (stopBtn) {
          phase = "wait-end";
        } else if (Date.now() - phaseEnteredAt > 3000) {
          // 3s 内 stop 按钮未出现，选择器可能不匹配，切换为内容稳定性检测
          phase = "wait-stable";
          phaseEnteredAt = Date.now();
          lastContent = getLastResponseText(config);
        }
      } else if (phase === "wait-end") {
        if (!stopBtn) finish();
      } else if (phase === "wait-stable") {
        if (stopBtn) {
          // stop 按钮迟到了，切回按钮检测
          phase = "wait-end";
          stableCount = 0;
          return;
        }
        const current = getLastResponseText(config);
        if (!current) {
          // 内容还没出现，继续等
          stableCount = 0;
          lastContent = null;
          return;
        }
        if (current === lastContent) {
          stableCount++;
          if (stableCount >= STABLE_NEEDED) finish();
        } else {
          lastContent = current;
          stableCount = 0;
          // AI 回复后页面可能持续更新（评分、推荐问题等），30s 后强制结束
          if (Date.now() - phaseEnteredAt > 30000) finish();
        }
      }
    }, 500);
  });
}

function getLastResponseText(config) {
  const selectors = config?.responseSelectors ?? [];
  for (const sel of selectors) {
    const items = document.querySelectorAll(sel);
    if (items.length > 0) return items[items.length - 1].innerText;
  }
  return null;
}

function findStopButton(config) {
  const selectors = config?.stopSelectors ?? [
    "button[aria-label='Stop response']",
    "button[aria-label='停止生成']",
    "button[aria-label='Stop generating']",
    "button.stop-button",
  ];
  return document.querySelector(selectors.join(", "));
}

// ═══════════════════════════════════════════════════════════════════════════════
//  提取最后一条回复
// ═══════════════════════════════════════════════════════════════════════════════

async function extractLastResponse(config) {
  // 优先：点复制按钮 → 通过剪贴板拦截读取原始文本（保留 LaTeX/Markdown）
  if (config?.getCopyButton) {
    _lastClipboardText = null;
    const btn = config.getCopyButton();
    if (btn) {
      const orig = btn.style.cssText;
      btn.style.cssText += ";opacity:1!important;visibility:visible!important;pointer-events:auto!important";
      btn.click();
      await new Promise(r => setTimeout(r, 400));
      btn.style.cssText = orig;
      if (_lastClipboardText?.trim()) {
        return { text: _lastClipboardText.trim(), source: "clipboard" };
      }
    }
  }

  // 降级：直接读 innerText（LaTeX 可能失真）
  const selectors = config?.responseSelectors ?? [
    "model-response",
    "[data-message-author-role='assistant']",
    ".markdown-body",
  ];
  for (const sel of selectors) {
    const items = document.querySelectorAll(sel);
    if (items.length > 0) {
      return { text: items[items.length - 1].innerText.trim(), source: "innerText" };
    }
  }
  return { text: "", source: "innerText" };
}

// ═══════════════════════════════════════════════════════════════════════════════
//  文件上传
// ═══════════════════════════════════════════════════════════════════════════════

async function uploadFile(fileBuffer, fileName, promptText, config) {
  const file = new File([fileBuffer], fileName, { type: "application/json" });

  // Gemini 等平台支持直接粘贴文件，用合成 paste 事件代替点按钮，更可靠
  if (config?.useClipboardPaste) {
    const el = findInputElement(config);
    if (!el) throw new Error("未找到输入框");
    el.click();
    el.focus();
    await new Promise(r => setTimeout(r, 150));

    const dt = new DataTransfer();
    dt.items.add(file);
    el.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, cancelable: true, clipboardData: dt }));

    // 等待平台处理文件
    await new Promise(r => setTimeout(r, 2000));

    el.click();
    el.focus();
    await new Promise(r => setTimeout(r, 150));

    const result = injectInput(promptText, false, config);
    if (!result.ok) throw new Error("注入失败：" + result.error);

    await new Promise(r => setTimeout(r, 300));
    await submitWithRetry(el, config);
    return { ok: true };
  }
  const inputSelectors = config?.fileInputSelectors ?? ["input[type='file']"];

  // 找隐藏的文件 input
  let fileInput = null;
  for (const sel of inputSelectors) {
    fileInput = document.querySelector(sel);
    if (fileInput) break;
  }

  // 找不到时先点附件按钮，等待 input 出现
  if (!fileInput) {
    const btnSelectors = config?.attachmentButtonSelectors ?? [];
    for (const sel of btnSelectors) {
      const btn = document.querySelector(sel);
      if (btn) {
        btn.click();
        await new Promise(r => setTimeout(r, 600));
        for (const sel2 of inputSelectors) {
          fileInput = document.querySelector(sel2);
          if (fileInput) break;
        }
        break;
      }
    }
  }

  if (!fileInput) {
    throw new Error("未找到文件上传入口，该平台可能不支持文件上传或选择器需要更新");
  }

  // 通过 DataTransfer 把文件挂到 input 上（绕过只读限制）
  const dt = new DataTransfer();
  dt.items.add(file);
  fileInput.files = dt.files;
  fileInput.dispatchEvent(new Event("change", { bubbles: true }));
  fileInput.dispatchEvent(new Event("input", { bubbles: true }));

  // 等待平台处理文件（显示预览缩略图等）
  await new Promise(r => setTimeout(r, 2000));

  // 重新聚焦输入框（文件上传后焦点可能丢失）
  const el = findInputElement(config);
  if (!el) throw new Error("文件上传后未找到输入框");
  el.click();
  el.focus();
  await new Promise(r => setTimeout(r, 150));

  // 注入 prompt 文字（不在 injectInput 内部触发发送）
  const result = injectInput(promptText, false, config);
  if (!result.ok) throw new Error("注入失败：" + result.error);

  // 等文字注册到框架后再发送
  await new Promise(r => setTimeout(r, 300));
  await submitWithRetry(el, config);
  return { ok: true };
}

// ═══════════════════════════════════════════════════════════════════════════════
//  抓取页面
// ═══════════════════════════════════════════════════════════════════════════════

function scrapePage() {
  return {
    title: document.title,
    url: location.href,
    headings: Array.from(document.querySelectorAll("h1, h2, h3"))
      .map((el) => el.innerText.trim())
      .filter(Boolean)
      .slice(0, 10),
    metaDescription:
      document.querySelector('meta[name="description"]')?.content ?? "",
    bodyTextPreview: document.body.innerText.slice(0, 500).trim(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
//  有机对话捕获（轮询）
//  检测用户正常聊天（非插件触发），在每轮 AI 回复完成时自动保存。
// ═══════════════════════════════════════════════════════════════════════════════

let _captureObserver = null;
let _capturePhase = "idle";   // idle → wait-stop | wait-stable → idle
let _prevMsgCount = 0;        // 上次捕获时的消息数，用于识别新增消息
let _stableCount = 0;         // 内容连续稳定的轮次
let _lastStableContent = null;// 稳定性检测用的上一次内容快照

const STABLE_TICKS = 5;       // 5 × 600ms = 3s 内容不变则判定完成

function startCapture() {
  if (_captureObserver) return;

  const config = getConfig();
  if (!config) {
    console.log("[MemAssist] 不支持当前平台，跳过捕获:", location.hostname);
    return;
  }

  _capturePhase = "idle";
  _prevMsgCount = _countMessages(config);
  _stableCount = 0;
  _lastStableContent = null;
  console.log("[MemAssist] 开始捕获，平台:", config.name, "，初始消息数:", _prevMsgCount);

  // 用轮询替代 MutationObserver，复用 findStopButton 的逻辑
  _captureObserver = setInterval(() => _captureStep(config), 600);
}

function stopCapture() {
  if (_captureObserver) {
    clearInterval(_captureObserver);
    _captureObserver = null;
  }
  _capturePhase = "idle";
  console.log("[MemAssist] 已停止捕获");
}

function _captureStep(config) {
  const stopBtn = findStopButton(config);
  const currentCount = _countMessages(config);

  if (_capturePhase === "idle") {
    if (stopBtn) {
      // 主路径：检测到 stop 按钮出现，等它消失
      _capturePhase = "wait-stop";
      console.log("[MemAssist] 检测到 stop 按钮，等待响应完成...");
    } else if (currentCount > _prevMsgCount) {
      // 备用路径：消息数增加但没看到 stop 按钮（快速响应 或 选择器不匹配）
      _capturePhase = "wait-stable";
      _stableCount = 0;
      _lastStableContent = _getLastMessage(config.responseSelectors);
      console.log("[MemAssist] 消息数增加（无 stop 按钮），切换稳定性检测...");
    }

  } else if (_capturePhase === "wait-stop") {
    if (!stopBtn) {
      _capturePhase = "idle";
      console.log("[MemAssist] stop 按钮消失，本轮响应完成");
      _onRoundComplete(config);
    }

  } else if (_capturePhase === "wait-stable") {
    if (stopBtn) {
      // stop 按钮迟到了，切回按钮检测
      _capturePhase = "wait-stop";
      _stableCount = 0;
      return;
    }
    const current = _getLastMessage(config.responseSelectors);
    if (current && current === _lastStableContent) {
      _stableCount++;
      if (_stableCount >= STABLE_TICKS) {
        _capturePhase = "idle";
        _stableCount = 0;
        console.log("[MemAssist] 内容稳定，本轮响应完成（稳定性检测）");
        _onRoundComplete(config);
      }
    } else {
      _stableCount = 0;
      _lastStableContent = current;
    }
  }
}

function _countMessages(config) {
  for (const sel of (config?.responseSelectors ?? [])) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) return els.length;
  }
  return 0;
}

async function _onRoundComplete(config) {
  const chatId = config.getChatId?.();
  if (!chatId) {
    console.log("[MemAssist] 无法获取 chatId，跳过（URL:", location.pathname, "）");
    return;
  }

  const currentCount = _countMessages(config);
  if (currentCount <= _prevMsgCount) {
    console.log("[MemAssist] 消息数未增加，跳过（当前:", currentCount, "，上次:", _prevMsgCount, "）");
    return;
  }
  _prevMsgCount = currentCount;

  // 提取最新 user + assistant pair
  const userText = _getLastMessage(config.userSelectors);
  const assistantText = _getLastMessage(config.responseSelectors);
  if (!userText || !assistantText) {
    console.log("[MemAssist] 未提取到消息内容，跳过（user:", !!userText, "，assistant:", !!assistantText, "）");
    return;
  }
  console.log("[MemAssist] 发送 ROUND_CAPTURED，chatId:", chatId, "，用户消息前50字:", userText.slice(0, 50));

  chrome.runtime.sendMessage({
    type: "ROUND_CAPTURED",
    chatId,
    platform: config.name,
    url: location.href,
    userText,
    assistantText,
    timestamp: new Date().toISOString(),
  });
}

function _getLastMessage(selectors) {
  for (const sel of (selectors ?? [])) {
    const els = document.querySelectorAll(sel);
    if (els.length > 0) return els[els.length - 1].innerText?.trim() ?? "";
  }
  return "";
}

// ── 页面加载时根据开关状态决定是否自动启动捕获 ────────────────────────────────

console.log("[MemAssist] content.js 已加载，平台:", location.hostname);
chrome.storage.local.get("keepUpdated", ({ keepUpdated }) => {
  console.log("[MemAssist] keepUpdated =", keepUpdated);
  if (keepUpdated) startCapture();
});
