/* Public catalogue only. A short cache avoids re-downloading between map and
 * catalogue pages; all authenticated writes invalidate it. */
(()=>{
 const CACHE='terroir-public-catalog-v1',URL='/api/catalog',TTL=60000;
 let pending;
 async function invalidate(){pending=null;try{await caches.delete(CACHE)}catch{}}
 async function load(){
  if(pending)return pending;
  pending=(async()=>{
   let cache;
   try{
    cache=await caches.open(CACHE);
    const saved=await cache.match(URL),stored=Number(saved?.headers.get('x-atlas-cached-at'));
    if(saved&&stored&&Date.now()-stored<TTL)return await saved.json();
   }catch{}
   const response=await fetch(URL,{cache:'no-store'});
   if(!response.ok)throw Error('Catalogue unavailable');
   const payload=await response.json();
   if(!Array.isArray(payload.entities))throw Error('Catalogue unavailable');
   if(cache){const headers={'content-type':'application/json','x-atlas-cached-at':String(Date.now())};cache.put(URL,new Response(JSON.stringify(payload),{headers})).catch(()=>{});}
   return payload;
  })().catch(error=>{pending=null;throw error});
  return pending;
 }
 window.AtlasCatalog={load,invalidate};
})();
