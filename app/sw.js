const CACHE='taalflex-v8-nomyvideos';
const ASSETS=['./standalone.html','./style.css','./app.js','./manifest.json'];
self.addEventListener('install',e=>{ self.skipWaiting(); e.waitUntil(caches.open(CACHE).then(async c=>{ for(let u of ASSETS){ try{ await c.add(u); }catch(e){} } })); });
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('message',e=>{ if(e.ports && e.ports[0]) e.ports[0].postMessage({}); });
self.addEventListener('fetch',e=>{
  try{
    const url=new URL(e.request.url);
    if(e.request.method!=='GET' || url.origin!==self.location.origin) return;
  }catch(_){ return; }
  e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
