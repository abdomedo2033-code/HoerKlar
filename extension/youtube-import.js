/* HörKlar importer — one-click button on YouTube watch pages.
 * "＋ HörKlar" appears under the title; clicking stashes the URL for the
 * HörKlar tab (which picks it up automatically when opened/focused).
 */
(function () {
  'use strict';
  function addBtn() {
    if (document.getElementById('hk-import-btn')) return;
    const anchor = document.querySelector('#top-row, #title.ytd-watch-metadata, h1.ytd-watch-metadata');
    if (!anchor) return;
    const b = document.createElement('button');
    b.id = 'hk-import-btn';
    b.textContent = '＋ HörKlar';
    b.style.cssText = 'margin-left:12px;padding:6px 14px;border-radius:999px;border:1px solid #6c5cff;background:#14182e;color:#eef0ff;cursor:pointer;font-weight:700';
    b.onclick = () => {
      try {
        chrome.runtime.sendMessage({ type: 'HK_SEND_TO_SITE', url: location.href }, () => {
          b.textContent = '✓ Saved — open HörKlar';
          setTimeout(() => { b.textContent = '＋ HörKlar'; }, 4000);
        });
      } catch (_) {}
    };
    anchor.appendChild(b);
  }
  new MutationObserver(addBtn).observe(document.documentElement, { childList: true, subtree: true });
  addBtn();
})();
