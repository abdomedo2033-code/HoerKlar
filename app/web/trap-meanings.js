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

  async function enrichWithGlossary(clips) {
    const g = await getGlossary();
    if (!g || !Object.keys(g).length) return 0;
    let n = 0;
    for (const c of clips) {
      const tr = c.translations || {};
      const td = (c.translation_distractors = c.translation_distractors || {});
      for (const lang of ['ar', 'en']) {
        if (!tr[lang] || (td[lang] && td[lang].length)) continue;
        const hol = [];
        for (const w of (c.wrong_answers || [])) {
          for (const dw of diffWords(c.correct_answer || '', w).slice(0, 2)) {
            const m = ((g[dw.toLowerCase()] || {})[lang] || '').trim();
            if (m && m.toLowerCase() !== String(tr[lang]).toLowerCase() && hol.indexOf(m) < 0 &&
                Math.abs(m.length - String(tr[lang]).length) <= 40) {
              hol.push(m);
              break;
            }
          }
          if (hol.length >= 3) break;
        }
        if (hol.length) { td[lang] = hol.slice(0, 3); n++; }
      }
    }
    return n;
  }

  window.TrapMeanings = { apply, enrichWithGlossary, getGlossary };
})();
