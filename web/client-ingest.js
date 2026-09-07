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
  // Kolner Phonetik (compact): same code = sounds alike in German
  // (seit/seid, Meer/mehr, Stadt/statt). Used to rank trap words by SOUND.
  function koelner(word) {
    const s = String(word || '').toLowerCase().replace(/ä/g, 'a').replace(/ö/g, 'o').replace(/ü/g, 'u').replace(/ß/g, 'ss');
    let out = '';
    for (let i = 0; i < s.length; i++) {
      const ch = s[i], prev = i ? s[i - 1] : '', nxt = s[i + 1] || '';
      if ('aeioujy'.indexOf(ch) >= 0) out += '0';
      else if (ch === 'h') continue;
      else if (ch === 'b') out += '1';
      else if (ch === 'p') out += (nxt === 'h' ? '3' : '1');
      else if (ch === 'd' || ch === 't') out += ('csz'.indexOf(nxt) >= 0 ? '8' : '2');
      else if ('fvw'.indexOf(ch) >= 0) out += '3';
      else if ('gkq'.indexOf(ch) >= 0) out += '4';
      else if (ch === 'c') out += (i === 0 ? ('ahkloqrux'.indexOf(nxt) >= 0 ? '4' : '8') : ('sz'.indexOf(prev) >= 0 ? '8' : ('ahkloqru'.indexOf(nxt) >= 0 ? '4' : '8')));
      else if (ch === 'x') out += ('ckqz'.indexOf(prev) >= 0 ? '8' : '48');
      else if (ch === 's' || ch === 'z') out += '8';
      else if (ch === 'm' || ch === 'n') out += '6';
      else if (ch === 'l') out += '5';
      else if (ch === 'r') out += '7';
    }
    out = out.replace(/(.)\1+/g, '$1');
    out = out.charAt(0) === '0' ? '0' + out.slice(1).replace(/0/g, '') : out.replace(/0/g, '');
    return out;
  }
  function simPick(word, ex) {
    try {
      if (typeof simWord === 'function') {
        const r = simWord(word, ex || new Set());
        if (r) return r;
      }
    } catch (_) { /* fallthrough */ }
    const pool = window._dewords || window._wpool || ['Wasser', 'Zeit', 'Leute'];
    const wl = word.toLowerCase();
    const code = koelner(wl);
    const c = pool.filter((x) => x.toLowerCase() !== wl && !(ex && ex.has(x.toLowerCase())) && Math.abs(x.length - word.length) <= 2);
    const same = c.filter((x) => code && koelner(x.toLowerCase()) === code);
    const pick = same.length ? same : c;
    return pick.length ? pick[Math.floor(Math.random() * Math.min(8, pick.length))] : word + 'n';
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

  function makeClips(vid, title, wins, trCues, section) {
    section = slugSection(section);
    return wins.map(([s, e, txt]) => {
      const c = {
        clip_id: 'yt_' + vid + '_' + s, provider: 'youtube', video_id: vid,
        embed_url: 'https://www.youtube.com/watch?v=' + vid,
        title: title + ' — ' + s + '-' + e + 's',
        start_time: s, end_time: e, dutch_text: txt, correct_answer: txt,
        wrong_answers: distractors(txt), cefr: 'A2', difficulty: 2,
        verified: false, section: section,
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
    try { if (window.TrapMeanings) await window.TrapMeanings.enrichWithGlossary(newClips); } catch (_) {}
    try { if (window.ClipLoader) await window.ClipLoader.cachePut('clips_myvideos', mine); } catch (_) {}
    try {
      const live = new Set(clips.map((c) => c.clip_id));
      for (const c of newClips) if (!live.has(c.clip_id)) clips.push(c);
      const sec = (newClips[0] && newClips[0].section) || 'general';
      window._sec = sec;
      document.querySelectorAll('.secbtn').forEach((x) => x.classList.toggle('active', x.dataset.sec === sec));
      if (typeof applyFilter === 'function') applyFilter();
    } catch (_) { /* page context differs — clips are still cached */ }
    try { window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: (newClips[0] && newClips[0].section) || 'general' } })); } catch (_) {}
    try { if (typeof refreshSections === 'function') refreshSections(); } catch (_) {}
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

  // PATH B — plain browser: public subtitle mirrors, zero server, zero Deck.
  // Tries several mirrors with short timeouts; any one success is enough.
  // (Availability varies by network/day — caller falls back to the backend.)
  // Mirror sources: the OFFICIAL live instance directory (self-healing —
  // dead mirrors disappear by themselves) plus two hardcoded fallbacks.
  const INVIDIOUS_FALLBACK = ['https://inv.nadeko.net', 'https://inv.tux.pizza'];
  let invCache = null, invCacheAt = 0;
  async function invidiousBases() {
    if (invCache && Date.now() - invCacheAt < 3600000) return invCache;
    try {
      const raw = await getJSON('https://api.invidious.io/instances.json', 10000);
      const list = (Array.isArray(raw) ? raw : []).map((e) => Array.isArray(e) ? { uri: e[0], info: e[1] } : e)
        .filter((e) => e && e.uri && e.uri.indexOf('https://') === 0 && e.info && e.info.api === true)
        .map((e) => ({ uri: e.uri.replace(/\/$/, ''), up: (e.info.monitor && e.info.monitor.uptime) || 0 }))
        .sort((a, b) => b.up - a.up)
        .slice(0, 6)
        .map((e) => e.uri);
      if (list.length) { invCache = list; invCacheAt = Date.now(); return list; }
    } catch (_) {}
    return INVIDIOUS_FALLBACK;
  }

  async function getJSON(url, ms) {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), ms || 9000);
    try {
      const r = await fetch(url, { signal: ctl.signal });
      if (!r.ok) throw new Error('http ' + r.status);
      return await r.json();
    } finally { clearTimeout(to); }
  }
  async function getText(url, ms) {
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), ms || 12000);
    try {
      const r = await fetch(url, { signal: ctl.signal });
      if (!r.ok) throw new Error('http ' + r.status);
      return await r.text();
    } finally { clearTimeout(to); }
  }
  function pickSub(list, want) {
    // entries shaped {code|languageCode, name|label, url, autoGenerated|auto|kind}
    const norm = (list || []).map((s) => ({
      code: String(s.code || s.languageCode || '').toLowerCase().replace('_', '-'),
      name: s.name || s.label || '',
      url: s.url || '',
      auto: !!(s.autoGenerated || s.auto || /auto/i.test(s.kind || '') || /auto/i.test(s.name || '')),
    })).filter((s) => s.url && (s.code === want || s.code.indexOf(want + '-') === 0));
    norm.sort((a, b) => (a.auto ? 1 : 0) - (b.auto ? 1 : 0));
    return norm[0] || null;
  }

  async function ingestViaMirrors(vid, onStage, section) {
    section = slugSection(section);
    const errs = [];
    onStage('Finding a live mirror…', 0.08);
    const bases = await invidiousBases();
    // Invidious instances (captions list, then track text).
    for (const base of bases) {
      try {
        onStage('Asking a subtitle mirror…', 0.12);
        const caps = await getJSON(base + '/api/v1/captions/' + vid, 9000);
        const list = Array.isArray(caps) ? caps : (caps.captions || []);
        const de = pickSub(list, 'de');
        if (!de) { errs.push(base + ': no German track'); continue; }
        onStage('Reading subtitles on your device…', 0.35);
        const vtt = await getText(de.url.indexOf('http') === 0 ? de.url : base + de.url, 15000);
        const cues = parseCues(vtt);
        if (cues.length < 2) { errs.push(base + ': unreadable track'); continue; }
        const wins = buildWindows(cues);
        if (!wins.length) { errs.push(base + ': no clip-length lines'); continue; }
        let title = 'YouTube video';
        try {
          const v = await getJSON(base + '/api/v1/videos/' + vid + '?fields=title', 8000);
          if (v && v.title) title = v.title;
        } catch (_) {}
        const clips = makeClips(vid, title, wins, [], section);
        clips.forEach((c) => { c.transcript_source = 'public_mirror_subs'; });
        const n = await persistAndShow(clips);
        return { n, title, section, source: 'mirrors' };
      } catch (e) { errs.push(base + ': ' + (e.message || e)); }
    }
    throw new Error('no mirror answered (' + errs.slice(0, 3).join('; ') + (errs.length > 3 ? '; …' : '') + ')');
  }

  // PATH A — Android app, native subtitles, zero server.
  async function ingestNative(vid, onStage, section) {
    section = slugSection(section);
    onStage('Reading subtitles on device…', 0.15);
    const raw = window.HKNative.getSubtitles('https://www.youtube.com/watch?v=' + vid);
    const info = JSON.parse(raw);
    if (info.error) throw new Error('no subtitles: ' + info.error);
    const de = pickTrack(info.tracks, 'de');
    if (!de) {
      // No subtitles anywhere: fall back to the on-device ear (slow, offline).
      if (!window.HKNative.fetchAudioB64) throw new Error('this video has no German subtitles');
      onStage('No subtitles — switching to on-device ear…', 0.12);
      return ingestWhisperOnDevice(vid, info.title || 'YouTube video', onStage, section, info.duration || 0);
    }
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
    const n = await persistAndShow(makeClips(vid, title, wins, trCues, section));
    return { n, title, section, source: 'device' };
  }

  // PATH A2 — Android app, on-device Whisper (no subtitles anywhere).
  // Audio arrives via the native bridge (base64 opus); decode + slice with
  // Web Audio, transcribe each window with an in-page Whisper model.
  // Slow (minutes on phones) but 100% on-device. Needs internet once for
  // the ~40MB model, then cached by the browser.
  let _whisperPipe = null, _whisperLoading = null;
  async function whisperPipe(onStage) {
    if (_whisperPipe) return _whisperPipe;
    if (!_whisperLoading) {
      _whisperLoading = (async () => {
        if (!window.transformers) {
          onStage && onStage('Loading on-device ear (~40MB, once)…', 0.05);
          await new Promise((res, rej) => {
            const s = document.createElement('script');
            s.src = 'https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2';
            s.onload = res; s.onerror = () => rej(new Error('could not load AI ear'));
            document.head.appendChild(s);
          });
        }
        const { pipeline, env } = window.transformers;
        if (env && env.allowLocalModels !== undefined) env.allowLocalModels = false;
        onStage && onStage('Warming up on-device ear…', 0.1);
        _whisperPipe = await pipeline('automatic-speech-recognition', 'Xenova/whisper-tiny', {
          progress_callback: (p) => {
            if (p && p.status === 'progress' && onStage) {
              onStage('Loading on-device ear (~40MB, once) ' + Math.round((p.progress || 0)) + '%…', 0.05);
            }
          },
        });
        return _whisperPipe;
      })();
    }
    return _whisperLoading;
  }
  function b64ToBytes(b64) {
    const bin = atob(b64);
    const u8 = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return u8;
  }
  async function decodeAudio(u8) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) throw new Error('no Web Audio on this device');
    const ac = new AC({ sampleRate: 16000 });
    const buf = await ac.decodeAudioData(u8.buffer.slice(0));
    const ch0 = buf.getChannelData(0);
    let mono = ch0;
    if (buf.numberOfChannels > 1) {
      mono = new Float32Array(ch0.length);
      for (let c = 0; c < buf.numberOfChannels; c++) {
        const ch = buf.getChannelData(c);
        for (let i = 0; i < ch.length; i++) mono[i] += ch[i] / buf.numberOfChannels;
      }
    }
    // resample to 16k if needed
    if (Math.abs(buf.sampleRate - 16000) > 1) {
      const ratio = buf.sampleRate / 16000;
      const out = new Float32Array(Math.floor(mono.length / ratio));
      for (let i = 0; i < out.length; i++) out[i] = mono[Math.floor(i * ratio)];
      mono = out;
    }
    try { await ac.close(); } catch (_) {}
    return mono;
  }
  const WH_BAD = ['Copyright', 'Untertitel', 'B.K.', 'G.M.', 'Applaus'];
  function okSpoken(t) {
    if (!t) return false;
    const toks = t.split(/\s+/);
    if (toks.length < 4 || t.length < 15 || t.length > 160) return false;
    if (WH_BAD.some((b) => t.indexOf(b) >= 0)) return false;
    if ((t.slice(0, -1).match(/[.!?…]/g) || []).length > 1) return false;
    return true;
  }
  function planTimes(dur) {
    dur = dur || 240;
    const tss = [];
    const lo = Math.max(30, Math.floor(dur * 0.05)), hi = Math.min(Math.floor(dur * 0.95), 2400);
    for (let t = lo; t < hi && tss.length < 9; t += 45) tss.push(t);
    if (!tss.length) tss.push(30);
    return tss;
  }
  // Shared core: transcribe 8s windows of 16kHz mono PCM in-page.
  async function transcribeWindows(pcm, durSec, onStage) {
    const tss = planTimes(durSec || Math.floor(pcm.length / 16000) || 240);
    const pipe = await whisperPipe(onStage);
    const wins = [];
    for (let i = 0; i < tss.length; i++) {
      const t = tss[i];
      onStage(`Listening on device ${i + 1}/${tss.length}…`, 0.15 + 0.6 * (i / tss.length));
      const slice = pcm.slice(t * 16000, (t + 8) * 16000);
      if (!slice.length) continue;
      let txt = '';
      try {
        const out = await pipe(slice, { language: 'german', task: 'transcribe' });
        txt = ((out && out.text) || '').trim();
      } catch (_) {}
      if (okSpoken(txt)) wins.push([t, t + 8, txt]);
      if (wins.length >= 12) break;
    }
    return wins;
  }
  async function ingestWhisperOnDevice(vid, title, onStage, section, durationSec) {
    section = slugSection(section);
    const b64 = window.HKNative.fetchAudioB64('https://www.youtube.com/watch?v=' + vid);
    if (!b64 || b64.length < 30000) throw new Error('could not grab audio on device');
    onStage('Decoding audio on device…', 0.15);
    const pcm = await decodeAudio(b64ToBytes(b64));
    const wins = await transcribeWindows(pcm, durationSec, onStage);
    if (!wins.length) throw new Error('on-device ear heard nothing usable');
    onStage('Saving ' + wins.length + ' quizzes…', 0.85);
    const clips = makeClips(vid, title || 'YouTube video', wins, [], section);
    clips.forEach((c) => { c.transcript_source = 'app_ondevice_whisper'; });
    await enrichWithGlossary(clips);
    const n = await persistAndShow(clips);
    return { n, title, section, source: 'device-whisper' };
  }
  // PATH D — desktop Chrome + HörKlar importer extension (user's pc, no server).
  // Subtitles come straight through the extension; if none exist, the
  // extension drops the audio track in Downloads and the user picks it
  // (one click) for fully local in-page transcription.
  function pickExtTrack(tracks, want) {
    const norm = (tracks || []).map((t) => ({
      lang: String(t.lang || '').toLowerCase().replace('_', '-'),
      text: t.text || '', auto: !!t.auto,
    })).filter((t) => t.text && t.text.length > 50 &&
      (t.lang === want || t.lang.indexOf(want + '-') === 0));
    norm.sort((a, b) => (a.auto ? 1 : 0) - (b.auto ? 1 : 0));
    return norm[0] || null;
  }
  async function ingestViaExtension(vid, onStage, section, askFile) {
    section = slugSection(section);
    onStage('Reading via extension…', 0.08);
    const info = await window.HKExt.subtitles(vid);
    const de = pickExtTrack(info.tracks, 'de');
    if (de) {
      const cues = parseCues(de.text);
      if (cues.length >= 2) {
        const wins = buildWindows(cues);
        if (wins.length) {
          const enT = pickExtTrack(info.tracks, 'en');
          const trCues = enT ? parseCues(enT.text) : [];
          const title = info.title || 'YouTube video';
          onStage('Saving ' + wins.length + ' quizzes…', 0.8);
          const clips = makeClips(vid, title, wins, trCues, section);
          clips.forEach((c) => { c.transcript_source = 'ext_subs'; });
          await enrichWithGlossary(clips);
          const n = await persistAndShow(clips);
          return { n, title, section, source: 'extension' };
        }
      }
    }
    // No usable subtitles: local ear via a picked audio file.
    onStage('No subtitles — saving audio to Downloads…', 0.12);
    const dl = await window.HKExt.audioFile(vid);
    onStage('Pick the audio file to transcribe on your pc…', 0.16);
    const file = await askFile(dl.filename);
    onStage('Decoding audio on your pc…', 0.2);
    const ab = await file.arrayBuffer();
    const pcm = await decodeAudio(new Uint8Array(ab));
    const wins = await transcribeWindows(pcm, info.duration || 0, onStage);
    if (!wins.length) throw new Error('on-device ear heard nothing usable');
    onStage('Saving ' + wins.length + ' quizzes…', 0.85);
    const clips = makeClips(vid, info.title || 'YouTube video', wins, [], section);
    clips.forEach((c) => { c.transcript_source = 'ext_whisper'; });
    await enrichWithGlossary(clips);
    const n = await persistAndShow(clips);
    return { n, title: info.title, section, source: 'extension-whisper' };
  }
  function slugSection(s) {
    s = String(s || '').toLowerCase().replace(/[^a-z0-9 _-]/g, '').trim().replace(/[\s-]+/g, '_').slice(0, 24);
    return s || 'general';
  }
  function prettySection(s) {
    return '📁 ' + String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // One-time migration: the retired 'myvideos' bucket becomes a normal
  // 'general' section (deletable like any other). Nothing hidden or lost.
  function migrateLegacyBucket() {
    try {
      if (typeof clips === 'undefined') return;
      let moved = false;
      for (const c of clips) {
        if ((c.section || '') === 'myvideos') { c.section = 'general'; moved = true; }
      }
      if (moved && window.ClipLoader) {
        window.ClipLoader.cachePut('clips_myvideos',
          clips.filter((c) => !CURATED.has(c.section || ''))).catch(() => {});
      }
    } catch (_) {}
  }

  // Personal-section management: list + delete (browser-private data only).
  const CURATED = new Set(['movies', 'series', 'songs', 'nicos', 'all', 'playphrase', '']);
  function listCustomSections() {
    try {
      if (typeof clips === 'undefined') return [];
      return [...new Set(clips.map((c) => c.section || ''))].filter((s) => !CURATED.has(s)).sort();
    } catch (_) { return []; }
  }
  async function deleteSection(sec) {
    if (CURATED.has(sec)) return 0;
    if (!window.confirm || !window.confirm(`Delete section "${prettySection(sec)}" and all its quizzes on this device?`)) return -1;
    let n = 0;
    try {
      for (let i = clips.length - 1; i >= 0; i--) {
        if ((clips[i].section || '') === sec) { clips.splice(i, 1); n++; }
      }
      if (window.ClipLoader) {
        const mine = ((await window.ClipLoader.cacheGet('clips_myvideos')) || [])
          .filter((c) => (c.section || '') !== sec);
        await window.ClipLoader.cachePut('clips_myvideos', mine);
      }
      try {
        document.querySelectorAll('.secbtn').forEach((b) => { if (b.dataset.sec === sec) b.remove(); });
      } catch (_) {}
      if ((window._sec || '') === sec) {
        window._sec = 'movies';
        try {
          document.querySelectorAll('.secbtn').forEach((x) => x.classList.toggle('active', x.dataset.sec === 'movies'));
        } catch (_) {}
        if (typeof applyFilter === 'function') applyFilter();
      }
    } catch (_) {}
    return n;
  }
  function refreshSections() {
    migrateLegacyBucket();
    try {
      const bar = document.getElementById('filters');
      if (!bar || typeof clips === 'undefined') return;
      const known = new Set();
      bar.querySelectorAll('.secbtn').forEach((b) => known.add(b.dataset.sec));
      const secs = [...new Set(clips.map((c) => c.section || 'movies'))]
        .filter((s) => !known.has(s) && s !== 'all' && s !== 'playphrase');
      for (const s of secs) {
        const b = document.createElement('button');
        b.className = 'secbtn'; b.dataset.sec = s; b.textContent = prettySection(s);
        b.onclick = () => {
          window._sec = s;
          bar.querySelectorAll('.secbtn').forEach((x) => x.classList.toggle('active', x === b));
          if (typeof applyFilter === 'function') applyFilter();
        };
        bar.appendChild(b);
      }
    } catch (_) { /* page context differs */ }
  }

  window.ClientIngest = { videoId, ingestNative, ingestViaMirrors, ingestViaExtension, parseCues, buildWindows, distractors, refreshSections, slugSection, prettySection, listCustomSections, deleteSection };
})();
