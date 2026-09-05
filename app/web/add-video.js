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
      btn.onclick = () => { AddVideo.fillSections(); modal.hidden = false; const ta = document.getElementById('addVideoUrls'); if (ta) ta.focus(); };
      document.getElementById('addVideoCancel').onclick = () => { modal.hidden = true; };
      document.getElementById('addVideoGo').onclick = () => this.submit();
    },
    fillSections() {
      // Section picker: existing sections first, ⭐ My videos default.
      try {
        const sel = document.getElementById('addVideoSectionSel');
        if (!sel) return;
        const secs = [...new Set((typeof clips !== 'undefined' ? clips : []).map((c) => c.section || 'movies'))]
          .filter((s) => s !== 'all' && s !== 'playphrase');
        const order = ['myvideos', ...secs.filter((s) => s !== 'myvideos').sort()];
        const pretty = (window.ClientIngest && window.ClientIngest.prettySection)
          ? window.ClientIngest.prettySection : (s) => s;
        sel.innerHTML = '';
        for (const s of order) {
          const o = document.createElement('option');
          o.value = s; o.textContent = pretty(s);
          sel.appendChild(o);
        }
      } catch (_) { /* page context differs */ }
    },
    readSection() {
      try {
        const fresh = document.getElementById('addVideoSection');
        if (fresh && fresh.value.trim()) {
          return ((window.ClientIngest && window.ClientIngest.slugSection(fresh.value)) || 'myvideos');
        }
        const sel = document.getElementById('addVideoSectionSel');
        if (sel && sel.value) return sel.value;
      } catch (_) {}
      return 'myvideos';
    },
    async submit() {
      const inp = document.getElementById('addVideoUrls') || document.getElementById('addVideoUrl');
      const err = document.getElementById('addVideoErr');
      err.textContent = '';
      const lines = inp.value.split(/\n+/).map((s) => s.trim()).filter(Boolean).slice(0, 10);
      if (!lines.length) { err.textContent = 'paste at least one link'; return; }
      const section = this.readSection() || 'myvideos';
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
        } catch (e) { card.done(`Got ${total} quizzes, then failed: ` + e.message, total === 0); }
        return;
      }
      // Path B — browser: hand off to the API backend (Deck/Render worker).
      try {
        const r = await fetch(this.api + '/api/ingest', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls: lines, user: this.user, section }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || ('http ' + r.status));
        document.getElementById('addVideoModal').hidden = true;
        inp.value = '';
        for (const job of (j.jobs || [])) this.watch(job.job_id);
        if (j.skipped && j.skipped.length) {
          err.textContent = '';
          const card = this.card();
          card.done('Note: ' + j.skipped.map((s) => s.error).join('; '), true);
        }
      } catch (e) {
        err.textContent = (window.HKNative ? e.message :
          'no backend reachable — open this page in the HörKlar app, or set up the API backend');
      }
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
        done(msg, failed) {
          card.querySelector('.jc-title').textContent = failed ? '🎬 Build failed' : msg;
          stageEl.textContent = failed ? msg : '';
          progEl.style.width = failed ? '0%' : '100%';
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
          stageEl.textContent = (STAGE_LABEL[j.stage] || STAGE_LABEL[j.status] || j.status) + vtitle;
          progEl.style.width = Math.round((j.progress || 0) * 100) + '%';
          const n = (j.clips_ready || []).length;
          if (n > seen) {
            seen = n;
            stageEl.textContent += ` (${n} quizzes ready — tap My videos to play!)`;
            window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: 'myvideos' } }));
          }
          if (j.status === 'done' || j.status === 'error') {
            clearInterval(t);
            if (j.status === 'done') {
              const sec = (window.ClientIngest ? window.ClientIngest.prettySection(j.section) : null) || '⭐ My videos';
              card.querySelector('.jc-title').textContent = `✅ ${n} quizzes ready in ${sec}${j.title ? ' — ' + j.title : ''}`;
              window.dispatchEvent(new CustomEvent('hk:clips-updated', { detail: { section: 'myvideos' } }));
              setTimeout(() => card.remove(), 15000);
            } else { stageEl.textContent = 'Failed: ' + (j.error || 'unknown error'); }
          }
        } catch (_) { /* transient — keep polling */ }
      };
      const t = setInterval(tick, 3000);
      tick();
    },
  };
  window.AddVideo = AddVideo;
})();
