/* Phase 4 — "＋ Add video" UI: paste URL -> job card with progress.
 *
 * HTML needed (paste into index.html near #filterBar):
 *   <button id="addVideoBtn">＋ Add video</button>
 *   <div id="addVideoModal" hidden>
 *     <textarea id="addVideoUrls" rows="3"></textarea>
 *     <select id="addVideoSectionSel"></select>
 *     <input id="addVideoSection" placeholder="…or a new section name">
 *     <button id="addVideoGo">Build quizzes</button>
 *     <button id="addVideoCancel">Cancel</button>
 *     <div id="addVideoErr"></div>
 *   </div>
 *   <div id="jobCards"></div>
 *
 * Wiring: AddVideo.init({apiBase, section:'myvideos'}) renders job cards that
 * poll GET /api/jobs/<id> every 3s: stages queued/fetching_subs/aligning/
 * transcribing/distractors/translating/done/error + progress bar. When
 * clips_ready grows, it fires hk:clips-updated so ClipLoader refetches
 * `myvideos` and the first quizzes stream in as ready. New clips appear in
 * the personal "My videos" section flagged unverified (see Phase 5).
 */
(function () {
  'use strict';
  const STAGE_LABEL = {
    queued: 'Waiting in queue…', fetching_subs: 'Fetching subtitles…',
    aligning: 'Aligning clips…', transcribing: 'Transcribing audio (Whisper)…',
    distractors: 'Building quiz traps…', translating: 'Adding translations…',
    streaming: 'First quizzes ready — finishing…', done: 'Done ✓', error: 'Failed',
  };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  const AddVideo = {
    api: '', user: 'local',
    init(opts) {
      this.api = ((opts && opts.apiBase) || window.HK_API_BASE || '').replace(/\/$/, '');
      try { this.user = localStorage.hk_uid || (localStorage.hk_uid = 'u' + Math.random().toString(36).slice(2, 10)); }
      catch (_) { this.user = 'local'; }
      const btn = document.getElementById('addVideoBtn');
      const modal = document.getElementById('addVideoModal');
      if (!btn || !modal) return; // HTML not yet pasted — loader stays inert.
      btn.onclick = () => { AddVideo.fillSections(); AddVideo.renderManage(); modal.hidden = false; const ta = document.getElementById('addVideoUrls'); if (ta) ta.focus(); };
      document.getElementById('addVideoCancel').onclick = () => { modal.hidden = true; };
      document.getElementById('addVideoGo').onclick = () => this.submit();
    },
    fillSections() {
      // Section picker: your existing sections only — no default bucket.
      // Pick one, or type a brand-new name beside it.
      try {
        const sel = document.getElementById('addVideoSectionSel');
        if (!sel) return;
        const secs = [...new Set((typeof clips !== 'undefined' ? clips : []).map((c) => c.section || ''))]
          .filter((s) => s && s !== 'all' && s !== 'playphrase' && s !== 'myvideos' &&
            !['movies', 'series', 'songs', 'nicos'].includes(s)).sort();
        const pretty = (window.ClientIngest && window.ClientIngest.prettySection)
          ? window.ClientIngest.prettySection : (s) => s;
        sel.innerHTML = '';
        const ph = document.createElement('option');
        ph.value = ''; ph.textContent = secs.length ? 'Choose a section…' : 'No sections yet — name one →';
        sel.appendChild(ph);
        for (const s of secs) {
          const o = document.createElement('option');
          o.value = s; o.textContent = pretty(s);
          sel.appendChild(o);
        }
      } catch (_) { /* page context differs */ }
    },
    renderManage() {
      // "Your sections" list with delete buttons (browser-private data only).
      try {
        const host = document.getElementById('addVideoManage');
        if (!host || !window.ClientIngest) return;
        host.innerHTML = '';
        const secs = window.ClientIngest.listCustomSections();
        if (!secs.length) return;
        const title = document.createElement('div');
        title.style.cssText = 'font-size:12px;color:#9aa3c7;margin:6px 0 4px';
        title.textContent = 'Your sections (tap Delete to remove with all its quizzes):';
        host.appendChild(title);
        for (const s of secs) {
          const row = document.createElement('div');
          row.className = 'secrow';
          const name = document.createElement('span');
          name.textContent = window.ClientIngest.prettySection(s);
          const del = document.createElement('button');
          del.className = 'secdel'; del.textContent = '✕ Delete';
          del.onclick = async () => {
            const n = await window.ClientIngest.deleteSection(s);
            if (n >= 0) { AddVideo.fillSections(); AddVideo.renderManage(); }
          };
          row.appendChild(name); row.appendChild(del);
          host.appendChild(row);
        }
      } catch (_) {}
    },
    readSection() {
      try {
        const fresh = document.getElementById('addVideoSection');
        if (fresh && fresh.value.trim()) {
          return ((window.ClientIngest && window.ClientIngest.slugSection(fresh.value)) || '');
        }
        const sel = document.getElementById('addVideoSectionSel');
        if (sel && sel.value) return sel.value;
      } catch (_) {}
      return '';
    },
    async submit() {
      const inp = document.getElementById('addVideoUrls') || document.getElementById('addVideoUrl');
      const err = document.getElementById('addVideoErr');
      err.textContent = '';
      const lines = inp.value.split(/\n+/).map((s) => s.trim()).filter(Boolean).slice(0, 10);
      if (!lines.length) { err.textContent = 'paste at least one link'; return; }
      const section = this.readSection();
      if (!section) { err.textContent = 'pick a section above, or type a new name'; return; }
      const isPlaylist = (u) => /[?&]list=([A-Za-z0-9_-]{8,64})/.test(u);
      // Path A — Android app: device fetches natively, one video at a time.
      if (window.HKNative && window.ClientIngest && !lines.some(isPlaylist)) {
        const vids = [];
        for (const u of lines) {
          const v = window.ClientIngest.videoId(u);
          if (!v) { err.textContent = 'could not find a video id in: ' + u.slice(0, 60); return; }
          vids.push(v);
        }
        document.getElementById('addVideoModal').hidden = true;
        inp.value = '';
        const card = this.card();
        let total = 0;
        try {
          for (let i = 0; i < vids.length; i++) {
            const res = await window.ClientIngest.ingestNative(
              vids[i], (stage, p) => card.progress(`Video ${i + 1}/${vids.length}: ${stage}`, (i + p) / vids.length), section);
            total += res.n;
          }
          card.done(`✅ ${total} quizzes ready in ${window.ClientIngest.prettySection(section)}`);
        } catch (e) { card.done(e.message && !/^Failed:/.test(e.message) ? 'Failed: ' + String(e.message).slice(0, 160) : String(e.message).slice(0, 180), e.message); }
        return;
      }
      // Path B2 — desktop Chrome + HörKlar importer extension (user's pc).
      if (window.HKExt && window.HKExt.available && window.ClientIngest && !lines.some(isPlaylist)) {
        const vids = [];
        let bad = null;
        for (const u of lines) {
          const v = window.ClientIngest.videoId(u);
          if (!v) { bad = u; break; }
          vids.push(v);
        }
        if (!bad) {
          document.getElementById('addVideoModal').hidden = true;
          inp.value = '';
          const card = this.card();
          const askFile = (filename) => new Promise((resolve, reject) => {
            card.filePick(filename, resolve, reject);
          });
          let total = 0, extFailed = null;
          try {
            for (let i = 0; i < vids.length; i++) {
              const res = await window.ClientIngest.ingestViaExtension(
                vids[i], (stage, p) => card.progress(`Video ${i + 1}/${vids.length}: ${stage}`, (i + p) / vids.length), section, askFile);
              total += res.n;
            }
            card.done(`✅ ${total} quizzes ready in ${window.ClientIngest.prettySection(section)} (built on your pc)`);
          } catch (e) { extFailed = e.message; }
          if (!extFailed) return;
          card.done('Extension could not finish (' + String(extFailed).slice(0, 120) + ') — trying mirrors…', true);
        } else if (!window.HKNative) {
          err.textContent = 'could not find a video id in: ' + bad.slice(0, 60);
          return;
        }
      }
      // Path B — plain browser: mirrors on YOUR device, zero Deck, zero server.
      if (window.ClientIngest && !lines.some(isPlaylist)) {
        const vids = [];
        let bad = null;
        for (const u of lines) {
          const v = window.ClientIngest.videoId(u);
          if (!v) { bad = u; break; }
          vids.push(v);
        }
        if (!bad) {
          document.getElementById('addVideoModal').hidden = true;
          inp.value = '';
          const card = this.card();
          let total = 0, mirrorFailed = null;
          try {
            for (let i = 0; i < vids.length; i++) {
              const res = await window.ClientIngest.ingestViaMirrors(
                vids[i], (stage, p) => card.progress(`Video ${i + 1}/${vids.length}: ${stage}`, (i + p) / vids.length), section);
              total += res.n;
            }
            card.done(`✅ ${total} quizzes ready in ${window.ClientIngest.prettySection(section)} (built on your device)`);
          } catch (e) { mirrorFailed = e.message; }
          if (!mirrorFailed) return;
          // Mirrors failed — fall through to the backend below (needs Deck).
          card.done('Mirrors busy (' + String(mirrorFailed).slice(0, 120) + ') — trying backend…', true);
        } else {
          err.textContent = 'could not find a video id in: ' + bad.slice(0, 60);
          return;
        }
      }
      // Path C — browser via API backend (Deck worker builds it).
      const DEFAULT_API = 'https://hoerklar-api.onrender.com';
      const tryIngest = (base) => fetch(base + '/api/ingest', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ urls: lines, user: this.user, section }),
      });
      try {
        let r = null, used = this.api;
        try {
          r = await tryIngest(this.api);
        } catch (e1) {
          if (this.api !== DEFAULT_API) { used = DEFAULT_API; r = await tryIngest(DEFAULT_API); }
          else throw e1;
        }
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || ('http ' + r.status));
        document.getElementById('addVideoModal').hidden = true;
        inp.value = '';
        const ids = (j.jobs || []).map((job) => job.job_id);
        try {
          const prev = JSON.parse(localStorage.hk_jobs || '[]');
          localStorage.hk_jobs = JSON.stringify([...new Set([...prev, ...ids])].slice(-20));
        } catch (_) {}
        for (const job of (j.jobs || [])) this.watch(job.job_id);
        if (j.skipped && j.skipped.length) {
          err.textContent = '';
          const card = this.card();
          card.done('Note: ' + j.skipped.map((s) => s.error).join('; '), true);
        }
      } catch (e) {
        err.textContent = 'backend not reachable (' + (typeof used !== 'undefined' ? used : this.api) + '). ' +
          (window.HKNative ? e.message :
          'Check connection/ad-blocker, or open this page in the HörKlar app.');
      }
    },
    forgetJob(jobId) {
      try {
        const prev = JSON.parse(localStorage.hk_jobs || '[]');
        localStorage.hk_jobs = JSON.stringify(prev.filter((id) => id !== jobId));
      } catch (_) {}
    },
    card() {
      const host = document.getElementById('jobCards') || document.body;
      const card = el('div', 'jobcard');
      card.innerHTML = '<div class="jc-title">🎬 Building quizzes…</div>' +
        '<div class="jc-stage"></div><div class="jc-bar"><div class="jc-prog"></div></div>';
      host.prepend(card);
      const stageEl = card.querySelector('.jc-stage');
      const progEl = card.querySelector('.jc-prog');
      return {
        progress(stage, p) { stageEl.textContent = stage; progEl.style.width = Math.round(p * 100) + '%'; },
        filePick(filename, resolve, reject) {
          stageEl.innerHTML = '';
          const note = document.createElement('div');
          note.style.cssText = 'font-size:13px;color:#9aa3c7;margin:6px 0';
          note.textContent = 'Saved audio as ' + filename + ' — pick it to transcribe on your pc:';
          const inp2 = document.createElement('input');
          inp2.type = 'file'; inp2.accept = 'audio/*,.webm,.m4a,.mp3,.opus';
          inp2.style.cssText = 'margin:4px 0;color:#eef0ff';
          const cancel = document.createElement('button');
          cancel.textContent = 'Skip';
          cancel.className = 'secdel';
          cancel.style.marginLeft = '8px';
          cancel.onclick = () => reject(new Error('skipped by user'));
          inp2.onchange = () => {
            if (inp2.files && inp2.files[0]) resolve(inp2.files[0]);
            else reject(new Error('no file picked'));
          };
          stageEl.appendChild(note); stageEl.appendChild(inp2); stageEl.appendChild(cancel);
        },
        done(msg, failed) {
          card.querySelector('.jc-title').textContent = msg;
          if (failed) { stageEl.textContent = failed === true ? '' : String(failed).slice(0, 200); progEl.style.width = '0%'; }
          else { stageEl.textContent = ''; progEl.style.width = '100%'; }
          if (!failed) setTimeout(() => card.remove(), 15000);
        },
      };
    },
    watch(jobId) {
      const host = document.getElementById('jobCards') || document.body;
      const card = el('div', 'jobcard');
      card.innerHTML = '<div class="jc-title">🎬 Building quizzes…</div>' +
        '<div class="jc-stage"></div><div class="jc-bar"><div class="jc-prog"></div></div>';
      host.prepend(card);
      const stageEl = card.querySelector('.jc-stage');
      const progEl = card.querySelector('.jc-prog');
      let seen = 0;
      const tick = async () => {
        try {
          const j = await (await fetch(this.api + '/api/jobs/' + jobId)).json();
          const vtitle = j.title ? ' — ' + j.title : '';
          stageEl.textContent = (STAGE_LABEL[j.stage] || STAGE_LABEL[j.status] || j.status) + vtitle + ' ' + Math.round((j.progress || 0) * 100) + '%';
          progEl.style.width = Math.round((j.progress || 0) * 100) + '%';
          const n = (j.clips_ready || []).length;
          if (n > seen) {
            seen = n;
            stageEl.textContent += ` (${n} quizzes ready — tap My videos to play!)`;
            window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: 'myvideos' } }));
          }
          if (j.status === 'done' || j.status === 'error') {
            clearInterval(t);
            AddVideo.forgetJob(jobId);
            if (j.status === 'error') {
              const why = j.error ? String(j.error).slice(0, 220) : 'unknown error';
              stageEl.textContent = 'Failed: ' + why + (j.progress ? ' (' + Math.round(j.progress * 100) + '%)' : '');
            } else if (j.status === 'done') {
              const sec = (window.ClientIngest ? window.ClientIngest.prettySection(j.section) : null) || '📁 General';
              card.querySelector('.jc-title').textContent = `✅ ${n} quizzes ready in ${sec}${j.title ? ' — ' + j.title : ''}`;
              // Browser-private: keep these clips on THIS device only.
              (async () => {
                try {
                  const fresh = j.clips_ready || [];
                  const mine = (await window.ClipLoader.cacheGet('clips_myvideos')) || [];
                  const have = new Set(mine.map((c) => c.clip_id));
                  for (const c of fresh) if (c.clip_id && !have.has(c.clip_id)) { mine.push(c); have.add(c.clip_id); }
                  try { if (window.TrapMeanings) await window.TrapMeanings.enrichWithGlossary(fresh); } catch (_) {}
                  await window.ClipLoader.cachePut('clips_myvideos', mine);
                  const live = new Set(clips.map((c) => c.clip_id));
                  for (const c of (j.clips_ready || [])) if (c.clip_id && !live.has(c.clip_id)) clips.push(c);
                  if (window.ClientIngest && window.ClientIngest.refreshSections) window.ClientIngest.refreshSections();
                } catch (_) {}
              })();
              window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: 'myvideos' } }));
              setTimeout(() => card.remove(), 15000);
            } else { stageEl.textContent = 'Failed: ' + (j.error || 'no details — try again, or send me the video link and I will build it by hand'); }
          }
        } catch (_) { /* transient — keep polling */ }
      };
      const t = setInterval(tick, 3000);
      tick();
    },
  };
  window.AddVideo = AddVideo;
})();
