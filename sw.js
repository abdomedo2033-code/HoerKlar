const CACHE='taalflex-v2';
const ASSETS=['./standalone.html','./style.css','./app.js','./manifest.json'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(async c=>{ for(let u of ASSETS){ try{ await c.add(u); }catch(e){} } })));
self.addEventListener('message',e=>{ if(e.ports && e.ports[0]) e.ports[0].postMessage({}); });
self.addEventListener('fetch',e=>e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))));
