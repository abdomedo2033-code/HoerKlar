/* HörKlar importer — background worker.
 * Runs with youtube.com host permission, so unlike a web page it may:
 *  1. Ask YouTube's player API (Android client) for caption tracks + audio.
 *  2. Download subtitle text + short audio slices and relay them home.
 * Everything stays on the user's pc: nothing is uploaded anywhere.
 */
const YT_KEY = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'; // public embedded client key
const UA = 'com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip';

async function player(vid) {
  const r = await fetch('https://www.youtube.com/youtubei/v1/player?key=' + YT_KEY, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'User-Agent': UA },
    body: JSON.stringify({
      videoId: vid,
      context: { client: { clientName: 'ANDROID', clientVersion: '19.09.37', androidSdkVersion: 33 } },
    }),
  });
  if (!r.ok) throw new Error('player http ' + r.status);
  return r.json();
}

function normCaps(tracks) {
  return (tracks || []).map((t) => ({
    lang: String(t.languageCode || '').toLowerCase().replace('_', '-'),
    name: t.name && (t.name.runs ? t.name.runs.map((x) => x.text).join('') : t.name.simpleText) || '',
    url: t.baseUrl || '',
    auto: t.kind === 'asr' || /auto/i.test(t.name && t.name.simpleText || ''),
  })).filter((t) => t.url);
}

async function subtitles(vid) {
  const p = await player(vid);
  const tracks = (((p.captions || {}).playerCaptionsTracklistRenderer || {}).captionTracks) || [];
  const title = (((p.videoDetails || {}).title) || 'YouTube video');
  const dur = parseInt(((p.videoDetails || {}).lengthSeconds) || '0', 10) || 0;
  const out = [];
  for (const t of normCaps(tracks)) {
    // fetch text here (we have host permission) so the page never touches YouTube
    const r = await fetch(t.url + (t.url.indexOf('?') < 0 ? '?' : '&') + 'fmt=vtt');
    if (!r.ok) continue;
    const text = await r.text();
    if (text && text.length > 50) out.push({ lang: t.lang, name: t.name, auto: t.auto, text });
  }
  return { title, duration: dur, tracks: out };
}

async function audioSlice(vid, startSec, secs) {
  const p = await player(vid);
  const fmts = (((p.streamingData || {}).adaptiveFormats) || []).filter((f) =>
    (f.mimeType || '').indexOf('audio/') === 0 && f.url);
  if (!fmts.length) throw new Error('no audio stream');
  fmts.sort((a, b) => (a.bitrate || 9e9) - (b.bitrate || 9e9));
  const au = fmts[0];
  const br = au.bitrate || 48000;
  const from = Math.max(0, Math.floor(startSec * br / 8) - 60000);
  const to = from + Math.ceil((secs + 4) * br / 8) + 120000;
  const r = await fetch(au.url, { headers: { Range: `bytes=${from}-${to}`, 'User-Agent': UA } });
  if (!r.ok && r.status !== 206) throw new Error('audio http ' + r.status);
  const buf = new Uint8Array(await r.arrayBuffer());
  let bin = '';
  const CH = 8192;
  for (let i = 0; i < buf.length; i += CH) bin += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  return { b64: btoa(bin), mime: au.mimeType || 'audio/webm', from, to };
}

async function audioFile(vid) {
  // Whole low-bitrate audio track -> user's Downloads (page picks it up
  // with a file chooser, so message-size limits never bite).
  const p = await player(vid);
  const fmts = (((p.streamingData || {}).adaptiveFormats) || []).filter((f) =>
    (f.mimeType || '').indexOf('audio/') === 0 && f.url);
  if (!fmts.length) throw new Error('no audio stream');
  fmts.sort((a, b) => (a.bitrate || 9e9) - (b.bitrate || 9e9));
  const au = fmts[0];
  const r = await fetch(au.url, { headers: { 'User-Agent': UA } });
  if (!r.ok) throw new Error('audio http ' + r.status);
  const blob = await r.blob();
  if (!blob.size || blob.size > 25 * 1024 * 1024) throw new Error('audio too big/empty');
  const ext = (au.mimeType || '').indexOf('mp4') >= 0 ? 'm4a' : 'webm';
  const name = `hoerklar-${vid}.${ext}`;
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({ url, filename: name, saveAs: false });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  return { filename: name, bytes: blob.size };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg.type === 'HK_SUBS') sendResponse({ ok: true, data: await subtitles(msg.vid) });
    else if (msg.type === 'HK_AUDIO') sendResponse({ ok: true, data: await audioSlice(msg.vid, msg.start, msg.secs) });
    else if (msg.type === 'HK_AUDIO_FILE') sendResponse({ ok: true, data: await audioFile(msg.vid) });
    else if (msg.type === 'HK_SEND_TO_SITE') {
      // youtube-import.js: stash a link for the HörKlar tab to pick up
      await chrome.storage.local.set({ hk_pending: msg.url });
      sendResponse({ ok: true });
    } else sendResponse({ ok: false, error: '?' });
  })().catch((e) => { try { sendResponse({ ok: false, error: String((e && e.message) || e) }); } catch (_) {} });
  return true; // async response
});
