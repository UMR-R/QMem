// 运行在主世界（MAIN world），可直接覆盖页面的 clipboard API。
// 通过 postMessage 将捕获的文本传给隔离世界的 content.js。
(function () {
  const _orig = navigator.clipboard.writeText.bind(navigator.clipboard);
  navigator.clipboard.writeText = function (text) {
    window.postMessage({ __ext_clipboard__: true, text }, "*");
    return _orig(text);
  };
})();
