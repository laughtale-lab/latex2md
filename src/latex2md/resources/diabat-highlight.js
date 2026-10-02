/* Diabat script syntax support. Runs after mdBook's own highlighter.
 * If hljs is available, register the grammar; independently apply spans
 * to unhighlighted Diabat code blocks so offline builds are also readable.
 * All transformed code is created using text nodes, never innerHTML.
 */
(function () {
  "use strict";
  const jobs = /^(?:diabat-fphd|diabat-gmh|diabat-fcd|diabat-fed|diabat-fedfcd|diabat-utils-phasefix|postorb|postwfn|statepack|stateset|mopack|statepack-ref|statepack-target|statepack-1|statepack-2|statepack-3|frag)\b/i;
  function register() {
    if (!window.hljs || !window.hljs.registerLanguage) return;
    try {
      window.hljs.registerLanguage("diabat", function () {
        return { name: "Diabat input", contains: [
          { scope: "comment", begin: /#/, end: /$/ },
          { scope: "string", begin: /"/, end: /"/ },
          { scope: "diabat-block-mark", begin: /\$+/ },
          { scope: "diabat-job", begin: /\b(?:diabat-fphd|diabat-gmh|diabat-fcd|diabat-fed|diabat-fedfcd|diabat-utils-phasefix|postorb|postwfn|statepack|stateset|mopack|statepack-ref|statepack-target|statepack-1|statepack-2|statepack-3|frag)\b/ }
        ]};
      });
    } catch (_) { /* Existing mdBook hljs versions vary; fallback follows. */ }
  }
  function paint(element) {
    if (element.querySelector("span")) return; // Don't clobber mdBook's existing highlighting.
    const text = element.textContent;
    const fragment = document.createDocumentFragment();
    const regexp = /(#[^\n]*|"(?:\\.|[^"\\])*"|\$+|(?:diabat-fphd|diabat-gmh|diabat-fcd|diabat-fed|diabat-fedfcd|diabat-utils-phasefix|postorb|postwfn|statepack|stateset|mopack|statepack-ref|statepack-target|statepack-1|statepack-2|statepack-3|frag)\b)/g;
    let last = 0; let m;
    while ((m = regexp.exec(text)) !== null) {
      if (m.index > last) fragment.appendChild(document.createTextNode(text.slice(last, m.index)));
      const span = document.createElement("span");
      const token = m[0];
      span.className = token[0] === "#" ? "diabat-comment" : token[0] === '"' ? "diabat-string" : token[0] === "$" ? "diabat-block-mark" : "diabat-job";
      span.textContent = token;
      fragment.appendChild(span);
      last = regexp.lastIndex;
    }
    fragment.appendChild(document.createTextNode(text.slice(last)));
    element.replaceChildren(fragment);
  }
  function run() {
    register();
    document.querySelectorAll('pre code.language-diabat, pre code.hljs.language-diabat, pre code.diabat').forEach(paint);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
