/* Juritel — service worker : démarrage instantané et fonctionnement hors ligne.
   Stratégies :
   - navigation      : réseau d'abord, cache en secours (une nouvelle version
                       publiée est donc prise en compte dès le lancement suivant) ;
   - fichiers du site : cache d'abord, rafraîchi en arrière-plan ;
   - Supabase        : jamais mis en cache (données vivantes et authentification).   */
const VERSION = 'juritel-v3';
const COQUILLE = [
  './', './index.html', './manifest.json',
  './logo-balance-tel.svg', './icon-192.png', './icon-512.png',
  './icon-maskable-512.png', './apple-touch-icon.png'
];
// volumineux : mis en cache après l'installation, sans la retarder
const DONNEES = ['./officiel.json', './competences.json', './carte.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const noms = await caches.keys();
    await Promise.all(noms.filter(n => n !== VERSION).map(n => caches.delete(n)));
    await self.clients.claim();
    const c = await caches.open(VERSION);
    for(const u of DONNEES){ try{ await c.add(u); }catch(err){} }   // échec silencieux
  })());
});

const estSupabase = u => u.hostname.endsWith('.supabase.co');
const estPolice   = u => u.hostname === 'fonts.googleapis.com' || u.hostname === 'fonts.gstatic.com';

self.addEventListener('fetch', e => {
  const req = e.request;
  if(req.method !== 'GET') return;
  const url = new URL(req.url);
  if(estSupabase(url)) return;                       // toujours le réseau

  if(req.mode === 'navigate'){
    e.respondWith((async () => {
      try{
        const rep = await fetch(req);
        // On ne met a jour la coquille QUE pour la page de l application.
        // Toute autre page servie sous la meme portee (page d essai, etc.)
        // ecraserait sinon l application en cache.
        const racine = new URL('./', self.registration.scope).pathname;
        const estApp = url.pathname === racine || url.pathname === racine + 'index.html';
        if(estApp && rep && rep.ok){
          const c = await caches.open(VERSION);
          // les DEUX cles de navigation doivent suivre, sinon « ./ » reste fige
          // sur la version installee au premier jour
          const a = rep.clone(), b = rep.clone();
          await Promise.all([c.put('./index.html', a), c.put('./', b)]);
        }
        return rep;
      }catch(err){
        return (await caches.match('./index.html')) || (await caches.match('./')) || Response.error();
      }
    })());
    return;
  }

  if(url.origin !== location.origin && !estPolice(url)) return;

  e.respondWith((async () => {
    const c = await caches.open(VERSION);
    const enCache = await c.match(req);
    const reseau = fetch(req).then(rep => {
      if(rep && (rep.ok || rep.type === 'opaque')) c.put(req, rep.clone());
      return rep;
    }).catch(() => null);
    return enCache || (await reseau) || Response.error();
  })());
});
