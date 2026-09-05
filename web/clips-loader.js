/* Phase 1 — per-section clip loader with IndexedDB offline cache.
 *
 * Drop-in replacement for the baked `let clips=[...]` blob:
 *   1. Cache-first: read section JSON from IndexedDB (works offline in APK).
 *   2. Network: fetch /api/clips?section=<sec>, refresh cache in background.
 *   3. Fallback: window.__SEED_CLIPS (tiny baked sample, ~20 clips) so the
 *      app boots even with no cache and no network.
 *
 * Backend contract (see server/api_server.py):
 *   GET /api/manifest            -> {movies:{count,sha1,bytes}, ...}
 *   GET /api/clips?section=movies -> JSON array of clips
 *
 * Usage in index.html (replaces `let clips=[...]` line region):
 *   <script src="web/clips-loader.js"></script>
 *   <script>ClipLoader.loadAll(['movies','series','songs','nicos']).then(clips => {
 *     window.clips = clips; load(); // existing boot function
 *   });</script>
 */
(function () {
  'use strict';
  const DB = 'hoerklar', STORE = 'clips', DBVER = 1;
  // Same-origin by default; override for dev (e.g. Deck worker / Render URL).
  const API = (window.HK_API_BASE || '').replace(/\/$/, '');

  function idb() {
    return new Promise((resolve, reject) => {
      const r = indexedDB.open(DB, DBVER);
      r.onupgradeneeded = () => r.result.createObjectStore(STORE);
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
  }
  async function cacheGet(key) {
    try {
      const db = await idb();
      return await new Promise((res) => {
        const tx = db.transaction(STORE, 'readonly').objectStore(STORE).get(key);
        tx.onsuccess = () => res(tx.result || null);
        tx.onerror = () => res(null);
      });
    } catch (_) { return null; }
  }
  async function cachePut(key, val) {
    try {
      const db = await idb();
      await new Promise((res) => {
        const tx = db.transaction(STORE, 'readwrite').objectStore(STORE).put(val, key);
        tx.onsuccess = () => res(); tx.onerror = () => res();
      });
    } catch (_) { /* private mode etc. — network still works */ }
  }

  async function fetchSection(sec) {
    const cached = await cacheGet('clips_' + sec);
    // Fire network refresh in parallel; return cache immediately if present.
    const net = fetch(API + '/api/clips?section=' + encodeURIComponent(sec),
      { headers: { Accept: 'application/json' } })
      .then((r) => { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then((arr) => { cachePut('clips_' + sec, arr); return arr; })
      .catch(() => null);
    if (cached && cached.length) { net.then((a) => { if (a) window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: sec } })); }); return cached; }
    const fresh = await net;
    if (fresh) return fresh;
    return [];
  }

  async function loadAll(sections) {
    const secs = sections || ['movies', 'series', 'songs', 'nicos', 'myvideos'];
    const parts = await Promise.all(secs.map(fetchSection));
    let clips = parts.flat();
    if (!clips.length && Array.isArray(window.__SEED_CLIPS)) clips = window.__SEED_CLIPS.slice();
    return clips;
  }

  window.ClipLoader = { loadAll, fetchSection, cacheGet, cachePut };
})();
