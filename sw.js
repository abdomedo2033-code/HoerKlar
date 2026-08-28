const CACHE='taalflix-v23';
const ASSETS=['./standalone.html','./style.css','./app.js','./manifest.json'];
self.addEventListener('install',e=>{ self.skipWaiting(); e.waitUntil(caches.open(CACHE).then(async c=>{ for(let u of ASSETS){ try{ await c.add(u); }catch(e){} } })); });
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('message',e=>{ if(e.ports && e.ports[0]) e.ports[0].postMessage({}); });
self.addEventListener('fetch',e=>{
  const url=new URL(e.request.url);
  if(e.request.mode==='navigate' || url.pathname.endsWith('.html') || url.pathname.endsWith('/') || url.pathname.includes('TaalFlix')){
    e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request).catch(()=>r)));
});
