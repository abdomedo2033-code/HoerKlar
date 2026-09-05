/* Phase 4 — "＋ Add video" UI: paste URL -> job card with progress.
 *
 * HTML needed (paste into index.html near #filterBar):
 *   <button id="addVideoBtn">＋ Add video</button>
 *   <div id="addVideoModal" hidden>
 *     <input id="addVideoUrl" placeholder="Paste a YouTube URL…" inputmode="url">
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
      btn.onclick = () => { modal.hidden = false; document.getElementById('addVideoUrl').focus(); };
      document.getElementById('addVideoCancel').onclick = () => { modal.hidden = true; };
      document.getElementById('addVideoGo').onclick = () => this.submit();
      document.getElementById('addVideoUrl').addEventListener('keydown', (e) => { if (e.key === 'Enter') this.submit(); });
    },
    async submit() {
      const inp = document.getElementById('addVideoUrl');
      const err = document.getElementById('addVideoErr');
      err.textContent = '';
      const url = inp.value;
      const secInput = document.getElementById('addVideoSection');
      const section = (window.ClientIngest ? window.ClientIngest.slugSection(secInput && secInput.value) : 'myvideos') || 'myvideos';
      // Path A — Android app: device fetches subtitles natively, zero server.
      if (window.HKNative && window.ClientIngest) {
        const vid = window.ClientIngest.videoId(url);
        if (!vid) { err.textContent = 'could not find a YouTube video id in that URL'; return; }
        document.getElementById('addVideoModal').hidden = true;
        inp.value = ''; if (secInput) secInput.value = '';
        const card = this.card();
        try {
          const res = await window.ClientIngest.ingestNative(vid, (stage, p) => card.progress(stage, p), section);
          card.done('✅ ' + res.n + ' quizzes ready in ' + window.ClientIngest.prettySection(res.section) + ' — ' + res.title);
        } catch (e) { card.done('Failed: ' + e.message, true); }
        return;
      }
      // Path B — browser: hand off to the API backend (Deck/Render worker).
      try {
        const r = await fetch(this.api + '/api/ingest', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, user: this.user, section }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.error || ('http ' + r.status));
        document.getElementById('addVideoModal').hidden = true;
        inp.value = '';
        this.watch(j.job_id);
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
