/* Client-side ingest: build quizzes IN the page, no backend.
 *
 * Path A (Android app): subtitles arrive via the HKNative JS bridge
 *   (MainActivity.HKBridge, NewPipeExtractor — native code has no CORS).
 * Path B (plain browser): POST to the API backend (Render/Deck), which
 *   returns when the Deck worker finishes. Needs HK_API_BASE configured.
 *
 * Finished clips are merged into the live `clips` array, persisted to
 * IndexedDB (ClipLoader cache, key clips_myvideos) and shown in ⭐ My videos.
 * Quiz construction mirrors server/pipeline_fastpath.py; cloze blanks and
 * translation fallbacks are already handled live by the page itself.
 */
(function () {
  'use strict';

  function videoId(url) {
    try {
      const u = new URL(url.trim());
      const host = u.hostname.toLowerCase();
      if (host === 'youtu.be') {
        const v = u.pathname.split('/').filter(Boolean)[0];
        if (/^[A-Za-z0-9_-]{11}$/.test(v || '')) return v;
      }
      if (host.endsWith('youtube.com')) {
        const v = u.searchParams.get('v');
        if (/^[A-Za-z0-9_-]{11}$/.test(v || '')) return v;
        const m = u.pathname.match(/^\/(shorts|embed|live)\/([A-Za-z0-9_-]{11})/);
        if (m) return m[2];
      }
    } catch (_) { /* fallthrough */ }
    return null;
  }

  function stripTags(s) { return s.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'"); }
  function ts2sec(x) {
    x = String(x).replace(',', '.').trim();
    const p = x.split(':');
    try {
      if (p.length === 3) return +p[0] * 3600 + +p[1] * 60 + parseFloat(p[2]);
      if (p.length === 2) return +p[0] * 60 + parseFloat(p[1]);
      return parseFloat(p[0]);
    } catch (_) { return NaN; }
  }
  function parseCues(text) {
    const cues = [];
    let s = null, e = null, buf = [];
    const flush = () => { if (s !== null && buf.length) cues.push([s, e, buf.join(' ')]); s = e = null; buf = []; };
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      const m = line.match(/(\d[\d:,.]*)\s*-->\s*(\d[\d:,.]*)/);
      if (m) { flush(); s = ts2sec(m[1]); e = ts2sec(m[2]); continue; }
      if (!line || /^(WEBVTT|NOTE|Kind:|Language:|\d+|STYLE|REGION)/.test(line)) continue;
      const t = stripTags(line).replace(/\s+/g, ' ').trim();
      if (t && buf[buf.length - 1] !== t) buf.push(t);
    }
    flush();
    return cues.filter((c) => isFinite(c[0]) && isFinite(c[1]) && c[2]);
  }
  function textFor(cues, a, b, cap) {
    let txt = cues.filter((c) => c[0] < b && c[1] > a).map((c) => c[2]).join(' ').replace(/\s+/g, ' ').trim();
    if (txt.length > (cap || 170)) {
      const cut = txt.slice(0, cap || 170);
      for (const pu of ['?', '!', '.']) { const i = cut.lastIndexOf(pu); if (i > 40) { txt = cut.slice(0, i + 1).trim(); break; } }
    }
    return txt;
  }
  function buildWindows(cues, maxClips) {
    const wins = [];
    let cur = [];
    for (const [s, e, t] of cues) {
      if (!cur.length) { cur = [[s, e, t]]; continue; }
      const joined = textFor(cur.concat([[s, e, t]]), cur[0][0], e);
      if (s - cur[cur.length - 1][1] > 1.2 || e - cur[0][0] > 8 || joined.length > 160) {
        wins.push(cur); cur = [[s, e, t]];
      } else cur.push([s, e, t]);
      if (wins.length >= (maxClips || 24)) break;
    }
    if (cur.length && wins.length < (maxClips || 24)) wins.push(cur);
    const out = [];
    for (const w of wins) {
      const txt = textFor(w, w[0][0], w[w.length - 1][1]);
      if (txt.length >= 15 && txt.length <= 170 && txt.split(/\s+/).length >= 3 &&
          (txt.slice(0, -1).match(/[.!?…]/g) || []).length <= 1) {
        out.push([Math.round(w[0][0] * 100) / 100,
                  Math.round(Math.min(w[w.length - 1][1], w[0][0] + 8) * 100) / 100, txt]);
      }
    }
    return out;
  }

  // Same-sound traps in the page's own style (simWord pool when present).
  const FUNC = { der: 'die', die: 'der', das: 'der', ein: 'eine', ist: 'war', und: 'oder', nicht: 'nie', ich: 'er' };
  function simPick(word, ex) {
    try {
      if (typeof simWord === 'function') {
        const r = simWord(word, ex || new Set());
        if (r) return r;
      }
    } catch (_) { /* fallthrough */ }
    const pool = window._dewords || window._wpool || ['Wasser', 'Zeit', 'Leute'];
    const c = pool.filter((x) => x.toLowerCase() !== word.toLowerCase() && !(ex && ex.has(x.toLowerCase())) && Math.abs(x.length - word.length) <= 2);
    return c.length ? c[Math.floor(Math.random() * Math.min(8, c.length))] : word + 'n';
  }
  function distractors(txt) {
    const words = txt.split(/\s+/);
    const outs = [], seen = new Set([txt]);
    const bare = (w) => w.replace(/[.,!?…:;«»()"']/g, '');
    for (let s = 0; s < 3; s++) {
      let t = txt;
      for (let a = 0; a < 8; a++) {
        const w2 = words.slice();
        const idxs = w2.map((w, i) => (bare(w).length >= 3 ? i : -1)).filter((i) => i >= 0);
        if (s === 0 && idxs.length) {
          let i = idxs[0]; for (const j of idxs) if (w2[j].length > w2[i].length) i = j;
          const b = bare(w2[i]);
          w2[i] = simPick(b, new Set([b.toLowerCase()])) + w2[i].slice(b.length);
        } else if (s === 1) {
          let done = false;
          for (let i = 0; i < w2.length; i++) {
            const b = bare(w2[i]).toLowerCase();
            if (FUNC[b]) { w2[i] = FUNC[b] + w2[i].slice(bare(w2[i]).length); done = true; break; }
          }
          if (!done && idxs.length) {
            const i = idxs[Math.floor(Math.random() * idxs.length)], b = bare(w2[i]);
            w2[i] = simPick(b, new Set([b.toLowerCase()])) + (w2[i].length > b.length ? w2[i].slice(b.length) : '');
          }
        } else if (w2.length > 3) {
          const i = Math.floor(Math.random() * (w2.length - 1));
          const tmp = w2[i]; w2[i] = w2[i + 1]; w2[i + 1] = tmp;
        }
        t = w2.join(' ');
        if (!seen.has(t) && Math.abs(t.length - txt.length) <= 8) break;
      }
      if (!seen.has(t)) { seen.add(t); outs.push(t); }
    }
    let fi = 0;
    while (outs.length < 3) {
      const t = txt.replace(' ', ' ' + ['ja', 'wohl', 'schon'][fi++ % 3] + ' ');
      if (!seen.has(t)) { seen.add(t); outs.push(t); }
    }
    return outs.slice(0, 3);
  }

  function makeClips(vid, title, wins, trCues) {
    return wins.map(([s, e, txt]) => {
      const c = {
        clip_id: 'yt_' + vid + '_' + s, provider: 'youtube', video_id: vid,
        embed_url: 'https://www.youtube.com/watch?v=' + vid,
        title: title + ' — ' + s + '-' + e + 's',
        start_time: s, end_time: e, dutch_text: txt, correct_answer: txt,
        wrong_answers: distractors(txt), cefr: 'A2', difficulty: 2,
        verified: false, section: 'myvideos',
        transcript_source: window.HKNative ? 'app_native_subs' : 'client_subs',
        rights_status: 'EMBED_ONLY',
      };
      if (trCues && trCues.length) {
        const en = textFor(trCues, s, e, 200);
        if (en.length >= 6) c.translations = { en };
      }
      return c;
    });
  }

  async function persistAndShow(newClips) {
    let mine = [];
    try {
      if (window.ClipLoader) mine = (await window.ClipLoader.cacheGet('clips_myvideos')) || [];
    } catch (_) { mine = []; }
    const have = new Set(mine.map((c) => c.clip_id));
    for (const c of newClips) if (!have.has(c.clip_id)) { mine.push(c); have.add(c.clip_id); }
    try { if (window.ClipLoader) await window.ClipLoader.cachePut('clips_myvideos', mine); } catch (_) {}
    try {
      const live = new Set(clips.map((c) => c.clip_id));
      for (const c of newClips) if (!live.has(c.clip_id)) clips.push(c);
      window._sec = 'myvideos';
      document.querySelectorAll('.secbtn').forEach((x) => x.classList.toggle('active', x.dataset.sec === 'myvideos'));
      if (typeof applyFilter === 'function') applyFilter();
    } catch (_) { /* page context differs — clips are still cached */ }
    try { window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: 'myvideos' } })); } catch (_) {}
    return newClips.length;
  }

  function pickTrack(tracks, want) {
    const norm = (tracks || []).map((t) => ({
      lang: String(t.lang || t.languageCode || '').toLowerCase().replace('_', '-'),
      auto: !!(t.auto || /auto/i.test(t.kind || '') || /auto/i.test(t.label || '')),
      url: t.url, fmt: String(t.format || t.fmt || 'vtt'),
    })).filter((t) => t.url);
    const match = (prefix) => norm.filter((t) => t.lang === prefix || t.lang.indexOf(prefix + '-') === 0);
    const pool = match(want).sort((a, b) => (a.auto ? 1 : 0) - (b.auto ? 1 : 0));
    return pool[0] || null;
  }

  // PATH A — Android app, native subtitles, zero server.
  async function ingestNative(vid, onStage) {
    onStage('Reading subtitles on device…', 0.15);
    const raw = window.HKNative.getSubtitles('https://www.youtube.com/watch?v=' + vid);
    const info = JSON.parse(raw);
    if (info.error) throw new Error('no subtitles: ' + info.error);
    const de = pickTrack(info.tracks, 'de');
    if (!de) throw new Error('this video has no German subtitles');
    onStage('Building clips…', 0.45);
    const vtt = window.HKNative.fetchText(de.url);
    if (!vtt || vtt.length < 50) throw new Error('subtitle download came back empty — try again');
    const cues = parseCues(vtt);
    if (cues.length < 2) throw new Error('subtitles unreadable — try another video');
    const wins = buildWindows(cues);
    if (!wins.length) throw new Error('no clip-length lines found');
    let trCues = [];
    const en = pickTrack(info.tracks, 'en');
    if (en && en.url !== de.url) {
      try { const t = window.HKNative.fetchText(en.url); if (t && t.length > 50) trCues = parseCues(t); } catch (_) {}
    }
    const title = info.title || 'YouTube video';
    onStage('Saving ' + wins.length + ' quizzes…', 0.8);
    const n = await persistAndShow(makeClips(vid, title, wins, trCues));
    return { n, title, source: 'device' };
  }

  window.ClientIngest = { videoId, ingestNative, parseCues, buildWindows, distractors };
})();
