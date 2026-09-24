// Recovered articles contain unhighlighted code elements from the original site.
(function () {
  function highlightCode() {
    var codeBlocks = document.querySelectorAll('pre code[class*="language-"]:not(.hljs)');
    if (!codeBlocks.length) return;
    var script = document.createElement('script');
    script.src = '/js/highlight.min.js';
    script.onload = function () {
      if (!window.hljs) return;
      codeBlocks.forEach(function (code) {
        if (!code.classList.contains('hljs')) window.hljs.highlightElement(code);
      });
    };
    document.head.appendChild(script);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', highlightCode);
  } else {
    highlightCode();
  }
})();
