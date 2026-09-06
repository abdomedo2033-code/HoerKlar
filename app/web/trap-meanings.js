/* Trap-meaning sidecars (all clips, old + new, same style).
 *
 * web/trap-meanings.json : {clip_id: {ar:[...], en:[...]}} — Arabic/English
 *   wrong options that are the TRUE meanings of German sound-alikes
 *   (Tische->Teppich/Tasche model). Generated offline by
 *   scripts/build_trap_sidecar.py from web/de-glossary.json.
 * web/de-glossary.json   : {german_lower: {ar, en}} — word meanings used
 *   live by ClientIngest for app-built clips (offline after first fetch).
 *
 * TrapMeanings.apply(clips): overwrite translation_distractors.{ar,en}
 *   wherever the sidecar has entries. Called at boot before load().
 * ClientIngest.enrichWithGlossary(clips): same style for freshly built
 *   clips, from the local glossary (no network at quiz time).
 */
(function () {
  'use strict';
  let sidecar = null, gloss = null;

  async function getSidecar() {
    if (sidecar) return sidecar;
    try {
      const r = await fetch('web/trap-meanings.json');
      sidecar = r.ok ? await r.json() : {};
    } catch (_) { sidecar = {}; }
    return sidecar;
  }
  async function getGlossary() {
    if (gloss) return gloss;
    try {
      if (window.ClipLoader) gloss = await window.ClipLoader.cacheGet('de_glossary');
      if (!gloss || !Object.keys(gloss).length) {
        const r = await fetch('web/de-glossary.json');
        gloss = r.ok ? await r.json() : {};
        if (gloss && Object.keys(gloss).length && window.ClipLoader) {
          try { await window.ClipLoader.cachePut('de_glossary', gloss); } catch (_) {}
        }
      }
    } catch (_) { gloss = gloss || {}; }
    return gloss;
  }

  function diffWords(correct, wrong) {
    const strip = (w) => w.replace(/[.,!?…:;«»()"']/g, '');
    const have = new Set(correct.toLowerCase().split(/\s+/).map(strip));
    const out = [];
    for (const w of wrong.split(/\s+/)) {
      const b = strip(w);
      if (b.length >= 3 && !have.has(b.toLowerCase()) && out.indexOf(b) < 0) out.push(b);
    }
    return out.sort((a, b) => b.length - a.length);
  }

  async function apply(clips) {
    const sc = await getSidecar();
    if (!sc || !Object.keys(sc).length) return 0;
    let n = 0;
    for (const c of clips) {
      const e = sc[c.clip_id];
      if (!e) continue;
      c.translation_distractors = c.translation_distractors || {};
      if (e.ar && e.ar.length) { c.translation_distractors.ar = e.ar; n++; }
      if (e.en && e.en.length) { c.translation_distractors.en = e.en; n++; }
    }
    return n;
  }

  // Live dictionary lookup from the visitor's own browser (CORS-open API,
  // no key). Fills whatever the offline glossary missed. Never throws.
  async function mmLookup(words, pair) {
    const out = {};
    const queue = [...new Set((words || []).map((w) => String(w || '').trim()).filter((w) => w.length >= 3))].slice(0, 24);
    for (const q of queue) {
      try {
        const r = await fetch('https://api.mymemory.translated.net/get?q=' +
          encodeURIComponent(q.slice(0, 60)) + '&langpair=' + pair);
        if (!r.ok) continue;
        const d = await r.json();
        let best = (((d.responseData || {}).translatedText) || '').trim();
        if (/MYMEMORY WARNING|QUERY LENGTH LIMIT|429/i.test(best)) continue;
        const wantAr = pair.slice(-2) === 'ar';
        best = best.replace(/\s*\(.*?\)\s*/g, ' ').replace(/[.،;!؟?]+$/, '').replace(/\s+/g, ' ').trim();
        const ok = wantar_check(best, wantAr);
        if (ok && best.toLowerCase() !== q.toLowerCase()) out[q.toLowerCase()] = best;
      } catch (_) {}
      await new Promise((res) => setTimeout(res, 350));
    }
    return out;
  }
  function wantar_check(s, wantAr) {
    if (!s || s.length < 1 || s.length > 40) return false;
    return wantAr ? /[ء-غف-ي]/.test(s) : /^[A-Za-z][A-Za-z '’\-]*$/.test(s);
  }

  async function enrichWithGlossary(clips) {
    // Offline glossary first, live dictionary for the gaps — all on-device.
    const g = await getGlossary();
    let n = 0;
    const needAr = clips.filter((c) => !((c.translations || {}).ar) && ((c.dutch_text || '').trim().length >= 10));
    if (needAr.length) {
      const got = await mmLookup(needAr.map((c) => c.dutch_text.trim()), 'de|ar');
      for (const c of needAr) {
        const key = c.dutch_text.trim();
        const a = got[key.toLowerCase()] || got[key];
        if (a) { (c.translations = c.translations || {}).ar = a; n++; }
      }
    }
    for (const c of clips) {
      const tr = c.translations || {};
      const td = (c.translation_distractors = c.translation_distractors || {});
      for (const lang of ['ar', 'en']) {
        if (!tr[lang] || (td[lang] && td[lang].length)) continue;
        const hol = [];
        const missing = [];
        for (const w of (c.wrong_answers || [])) {
          for (const dw of diffWords(c.correct_answer || '', w).slice(0, 2)) {
            const m = ((((g || {})[dw.toLowerCase()] || {})[lang]) || '').trim();
            if (m && m.toLowerCase() !== String(tr[lang]).toLowerCase() && hol.indexOf(m) < 0 &&
                Math.abs(m.length - String(tr[lang]).length) <= 40) {
              hol.push(m);
              break;
            } else if (!m) {
              missing.push(dw);
            }
          }
          if (hol.length >= 3) break;
        }
        if (hol.length < 2 && missing.length) {
          const got = await mmLookup(missing, lang === 'ar' ? 'de|ar' : 'de|en');
          for (const dw of missing) {
            const m = (got[dw.toLowerCase()] || '').trim();
            if (m && m.toLowerCase() !== String(tr[lang]).toLowerCase() && hol.indexOf(m) < 0 &&
                Math.abs(m.length - String(tr[lang]).length) <= 40) hol.push(m);
            if (hol.length >= 3) break;
          }
        }
        if (hol.length) { td[lang] = hol.slice(0, 3); n++; }
      }
    }
    return n;
  }
  window.TrapMeanings = { apply, enrichWithGlossary, getGlossary };
})();
