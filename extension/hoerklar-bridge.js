/* HörKlar importer — bridge inside the HörKlar page.
 * Exposes window.HKExt = { subtitles(vid), audioSlice(vid, start, secs) }
 * backed by the extension (host permission), then hands results to the
 * page's own quiz builders. Replies time out rather than hanging.
 */
(function () {
  'use strict';
  if (window.HKExt) return;
  function call(type, payload, ms) {
    return new Promise((resolve, reject) => {
      let done = false;
      const to = setTimeout(() => { if (!done) { done = true; reject(new Error('extension timeout')); } }, ms || 60000);
      try {
        chrome.runtime.sendMessage(Object.assign({ type }, payload || {}), (res) => {
          if (done) return;
          done = true;
          clearTimeout(to);
          if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
          if (!res || !res.ok) return reject(new Error((res && res.error) || 'extension error'));
          resolve(res.data);
        });
      } catch (e) { clearTimeout(to); reject(e); }
    });
  }
  window.HKExt = {
    available: !!(window.chrome && chrome.runtime && chrome.runtime.sendMessage),
    subtitles: (vid) => call('HK_SUBS', { vid }, 45000),
    audioSlice: (vid, start, secs) => call('HK_AUDIO', { vid, start, secs }, 90000),
    audioFile: (vid) => call('HK_AUDIO_FILE', { vid }, 180000),
  };
})();
