// Background Service Worker

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "SAVE_DOCUMENT") {
    saveDocument(message.text, message.platform ?? "ai", message.isMemory ?? false);
  }
});

function saveDocument(rawText, platform, isMemory) {
  const now = new Date();
  const timestamp = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const prefix = isMemory ? `${platform}-记忆-` : `${platform}-`;

  // 去掉 AI 平台渲染产生的前缀噪声（如 "json\n复制\n下载\n"），取第一个 { 开始的内容
  const jsonStart = rawText.indexOf("{");
  const isJson = jsonStart !== -1 && (() => {
    try { JSON.parse(rawText.slice(jsonStart)); return true; } catch { return false; }
  })();

  if (isJson) {
    const content = rawText.slice(jsonStart);
    chrome.downloads.download({
      url: "data:application/json;charset=utf-8," + encodeURIComponent(content),
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

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Background] 插件已安装");
});
