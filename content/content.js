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
  },
};

function getConfig() {
  const h = location.hostname;
  if (h === "chat.openai.com") return PLATFORMS["chatgpt.com"];
  return PLATFORMS[h] ?? null;
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

  } else if (message.type === "INJECT_INPUT") {
    const result = injectInput(message.text, false, config);
    sendResponse(result);

  } else if (message.type === "SUBMIT_AND_WAIT") {
    const el = findInputElement(config);
    if (!el) { sendResponse({ ok: false, error: "未找到输入框" }); return; }
    // 立即应答，不持有 channel —— 防止 SPA 导航时 content script 被卸载导致 channel 断
    sendResponse({ ok: true });
    const jobId = message.jobId;
    submitWithRetry(el, config)
      .then(() => waitForResponse(config))
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

// 重试发送：每 500ms 点一次发送键，直到输入框被清空（说明发送成功）或超时
async function submitWithRetry(el, config, timeoutMs = 30000) {
  const getContent = () =>
    (el.value !== undefined ? el.value : el.textContent ?? "").trim();
  const originalContent = getContent();
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    submitInput(el, config);
    await new Promise(r => setTimeout(r, 500));
    if (getContent() !== originalContent || findStopButton(config)) return;
  }
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
        reject(new Error("等待回复超时（90s）"));
        return;
      }

      const stopBtn = findStopButton(config);

      if (phase === "wait-start") {
        if (stopBtn) {
          phase = "wait-end";
        } else if (Date.now() - phaseEnteredAt > 3000) {
          // 3s 内 stop 按钮未出现，选择器可能不匹配，切换为内容稳定性检测
          phase = "wait-stable";
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
