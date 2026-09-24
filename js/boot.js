/* global Fluid */

Fluid.boot = {};

Fluid.boot.registerEvents = function() {
  Fluid.events.billboard();
  Fluid.events.registerNavbarEvent();
  Fluid.events.registerParallaxEvent();
  Fluid.events.registerScrollDownArrowEvent();
  Fluid.events.registerScrollTopArrowEvent();
  Fluid.events.registerImageLoadedEvent();
};

Fluid.boot.refresh = function() {
  Fluid.plugins.fancyBox();
  Fluid.plugins.codeWidget();
  Fluid.events.refresh();
};

document.addEventListener('DOMContentLoaded', function() {
  // Recent Hexo output can leave fenced code as plain <code> elements with
  // language-* classes. Highlight those locally; older pages already contain
  // Highlight.js markup and are left untouched.
  Fluid.utils.createScript('/js/highlight.min.js', function() {
    if (!window.hljs) {
      return;
    }
    document.querySelectorAll('pre code[class*="language-"]').forEach(function(code) {
      if (!code.classList.contains('hljs')) {
        window.hljs.highlightElement(code);
      }
    });
  });

  Fluid.boot.registerEvents();
});
