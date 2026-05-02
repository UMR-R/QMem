// 运行在主世界（MAIN world），只在 content.js 明确请求时临时拦截 clipboard API。
// 通过 postMessage 将捕获的文本传给隔离世界的 content.js。
(function () {
  const CONTROL_KEY = "__memassist_clipboard_capture__";
  let originalWriteText = null;
  let isPatched = false;
  let isActive = false;
  let disableTimer = null;

  function restore() {
    if (disableTimer) {
      clearTimeout(disableTimer);
      disableTimer = null;
    }
    isActive = false;
    if (isPatched && originalWriteText && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText = originalWriteText;
    }
    originalWriteText = null;
    isPatched = false;
  }

  function enable(timeoutMs) {
    if (!navigator.clipboard?.writeText) return;
    if (!isPatched) {
      originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
      navigator.clipboard.writeText = function (text) {
        if (isActive) window.postMessage({ __ext_clipboard__: true, text }, "*");
        return originalWriteText(text);
      };
      isPatched = true;
    }
    isActive = true;
    if (disableTimer) clearTimeout(disableTimer);
    disableTimer = setTimeout(restore, Math.max(500, Number(timeoutMs) || 1500));
  }

  window.addEventListener("message", event => {
    if (event.source !== window || !event.data?.[CONTROL_KEY]) return;
    if (event.data.action === "enable") enable(event.data.timeoutMs);
    if (event.data.action === "disable") restore();
  });
})();
