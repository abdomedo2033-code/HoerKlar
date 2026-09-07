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
  // sent=true switches validation to full-sentence mode (up to 200 chars,
  // longer query budget) for translating whole trap sentences.
  async function mmLookup(words, pair, isRefused, setRefused, sent) {
    const out = {};
    const queue = [...new Set((words || []).map((w) => String(w || '').trim()).filter((w) => w.length >= 3))].slice(0, 24);
    for (const q of queue) {
      if (isRefused && isRefused()) break;
      try {
        const r = await fetch('https://api.mymemory.translated.net/get?q=' +
          encodeURIComponent(q.slice(0, sent ? 500 : 60)) + '&langpair=' + pair);
        if (r.status === 429) { if (setRefused) setRefused(true); break; }
        if (!r.ok) continue;
        const d = await r.json();
        let best = (((d.responseData || {}).translatedText) || '').trim();
        if (/MYMEMORY WARNING|QUERY LENGTH LIMIT|429/i.test(best)) continue;
        const wantAr = pair.slice(-2) === 'ar';
        best = best.replace(/\s*\(.*?\)\s*/g, ' ').replace(/[.،;!؟?]+$/, '').replace(/\s+/g, ' ').trim();
        const ok = sent ? wantsent_check(best, wantAr) : wantar_check(best, wantAr);
        if (ok && best.toLowerCase() !== q.toLowerCase()) out[q.toLowerCase()] = best;
      } catch (_) {}
      await new Promise((res) => setTimeout(res, 350));
    }
    return out;
  }
  function wantsent_check(s, wantAr) {
    if (!s || s.length < 6 || s.length > 200) return false;
    if (wantAr) return /[ء-غف-ي]/.test(s);
    const letters = (s.match(/[A-Za-z]/g) || []).length;
    return letters >= s.length * 0.6;
  }
  function wantar_check(s, wantAr) {
    if (!s || s.length < 1 || s.length > 40) return false;
    return wantAr ? /[ء-غف-ي]/.test(s) : /^[A-Za-z][A-Za-z '’\-]*$/.test(s);
  }

  // Looks-German gate: only translate text that is plausibly German.
  // (Song lyrics in French etc. must never be sent to the de->ar endpoint.)
  const DE_HINT = /\b(der|die|das|den|dem|und|ist|nicht|ich|du|er|sie|wir|mit|für|auf|ein|eine|einer|auch|nur|schon|noch|wie|was|wo|wenn|dass|weil|sich|uns|euch|ihnen|kein|keine|mein|meine|dein|deine|sein|seine|ihr|ihre|unser|euer|wird|werden|bin|bist|sind|war|waren|hat|haben|wird|kann|muss|soll|will|darf|mag|möchte|vom|zum|beim|nach|über|unter|zwischen|durch|gegen|ohne|gegenüber|heute|morgen|jetzt|hier|dort|sehr|mehr|alle|viele|jede|jeder|jedes|welche|dieser|diese|dieses|jener|alle|beide)\b/i;
  function looksGerman(t) {
    t = String(t || '');
    if (t.length < 10 || t.length > 170) return false;
    if (/[äöüß]/.test(t)) return true;
    const words = t.toLowerCase().replace(/[^a-zäöüß ]/g, ' ').split(/\s+/).filter(Boolean);
    if (words.length < 3) return false;
    let hits = 0;
    for (const w of words) { DE_HINT.lastIndex = 0; if (DE_HINT.test(' ' + w + ' ')) hits++; }
    return hits >= 2 || (hits >= 1 && /[äöüß]/.test(t));
  }

  // Sentence-level trap meanings: translate each German WRONG answer as a
  // WHOLE sentence. German traps are same-sound swaps, so their translations
  // are full-sentence, pronunciation-linked distractors — never lone words.
  // Topped up with sibling sentences from the same batch (same video =
  // topical, real sentences). Returns number of clips enriched.
  async function trapSentences(clips, lang, isRefused, setRefused) {
    const pair = lang === 'ar' ? 'de|ar' : 'de|en';
    const jobs = [];
    for (const c of clips) {
      const tr = String((c.translations || {})[lang] || '');
      if (!tr || !/\s/.test(tr.trim())) continue; // words handled by glossary
      const td = c.translation_distractors || {};
      if (td[lang] && td[lang].length) continue;
      if (!looksGerman(c.correct_answer || c.dutch_text || '')) continue;
      for (const w of (c.wrong_answers || []).slice(0, 3)) {
        if (w && w !== c.correct_answer && jobs.length < 12) jobs.push({ c, w });
      }
      if (jobs.length >= 12) break;
    }
    if (!jobs.length) return 0;
    const got = await mmLookup(jobs.map((j) => j.w), pair, isRefused, setRefused, true);
    const byClip = new Map();
    for (const j of jobs) {
      const m = (got[j.w.toLowerCase()] || got[j.w] || '').trim();
      const tr = String((j.c.translations || {})[lang] || '');
      if (!m || m.toLowerCase() === tr.toLowerCase()) continue;
      if (Math.abs(m.length - tr.length) > 40) continue;
      if (!byClip.has(j.c)) byClip.set(j.c, []);
      const hol = byClip.get(j.c);
      if (hol.indexOf(m) < 0 && hol.length < 3) hol.push(m);
    }
    let n = 0;
    for (const [c, hol] of byClip) {
      if (hol.length < 3) {
        const tr = String((c.translations || {})[lang] || '');
        for (const s of clips) {
          if (hol.length >= 3) break;
          if (s === c) continue;
          const t = (s.translations || {})[lang];
          if (!t || t === tr || hol.indexOf(t) >= 0) continue;
          if (Math.abs(t.length - tr.length) > 60) continue;
          hol.push(t);
        }
      }
      if (hol.length) {
        (c.translation_distractors = c.translation_distractors || {})[lang] = hol.slice(0, 3);
        n++;
      }
    }
    return n;
  }

  async function enrichWithGlossary(clips) {
    // Offline glossary first, live dictionary for the gaps — all on-device.
    const g = await getGlossary();
    let n = 0;
    // 429 circuit breaker shared across this call: first refusal stops the batch.
    let refused = false;
    const needAr = clips.filter((c) => !((c.translations || {}).ar) && looksGerman(c.dutch_text)).slice(0, 6);
    if (needAr.length) {
      const got = await mmLookup(needAr.map((c) => c.dutch_text.trim()), 'de|ar', () => refused, (v) => { refused = v; }, true);
      for (const c of needAr) {
        const key = c.dutch_text.trim();
        const a = got[key.toLowerCase()] || got[key];
        if (a) { (c.translations = c.translations || {}).ar = a; n++; }
      }
    }
    const needEn = clips.filter((c) => !((c.translations || {}).en) && looksGerman(c.dutch_text)).slice(0, 6);
    if (needEn.length && !refused) {
      const got = await mmLookup(needEn.map((c) => c.dutch_text.trim()), 'de|en', () => refused, (v) => { refused = v; }, true);
      for (const c of needEn) {
        const key = c.dutch_text.trim();
        const a = got[key.toLowerCase()] || got[key];
        if (a) { (c.translations = c.translations || {}).en = a; n++; }
      }
    }
    // Full-sentence, pronunciation-linked traps first (both languages).
    if (!refused) n += await trapSentences(clips, 'ar', () => refused, (v) => { refused = v; });
    if (!refused) n += await trapSentences(clips, 'en', () => refused, (v) => { refused = v; });
    for (const c of clips) {
      const tr = c.translations || {};
      const td = (c.translation_distractors = c.translation_distractors || {});
      for (const lang of ['ar', 'en']) {
        if (!tr[lang] || (td[lang] && td[lang].length)) continue;
        if (/\s/.test(String(tr[lang]).trim())) continue; // sentences done above
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
        if (hol.length < 2 && missing.length && !refused) {
          const got = await mmLookup(missing, lang === 'ar' ? 'de|ar' : 'de|en', () => refused, (v) => { refused = v; });
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
