(()=>{
 if(!window.L||!map)return;
 const E=escapeHTML,I=WineI18n,C=WineLanguage,geo=WineGeo,T=text=>E(I.t(text));
 const field=(e,key='name')=>C.field(e,key,I.locale);
 const name=e=>I.name(e);
 const langOf=f=>f.language?` lang="${E(f.language)}"`:'';
 const nameHTML=e=>{const f=field(e);return `<span data-no-i18n${langOf(f)}>${E(f.text)}</span>`};
 const href=e=>'/catalog?entity='+encodeURIComponent(e.id)+'&lang='+encodeURIComponent(I.locale);
 const vintageLabel=e=>e.data.yearType==='nv'?I.t('无年份（NV）'):e.data.yearType==='unknown'?I.t('年份未知'):e.data.year||I.t('年份待补');
 // 图片清单由 scripts/publish-entity-photos.py 产出，键为实体 id，值只含已发布的 /photos/ 路径
 const GROUP_ORDER=['estate','wine','region','people','document','uncertain'];
 const MAX_COMPACT=6;

 let items=[],byId=new Map(),children=new Map(),winesOf=new Map(),vintagesOf=new Map(),photoIndex={},current='',expanded=false,richLimit=6,galleries=[];

 let photosReady;
 function loadPhotos(){if(!photosReady)photosReady=fetch('/entity-photos.json').then(r=>{if(!r.ok)throw Error('photos');return r.json()}).then(d=>{photoIndex=d.entities||{};if(current)render()}).catch(()=>{photosReady=null});return photosReady}


 function prepare(){
  byId=new Map(items.map(e=>[e.id,e]));children=new Map();winesOf=new Map();vintagesOf=new Map();
  for(const e of items){
   if(e.kind==='region'){const p=e.data.regionId||'';if(!children.has(p))children.set(p,[]);children.get(p).push(e.id)}
   else if(e.kind==='wine'){const w=e.data.wineryId;if(w){if(!winesOf.has(w))winesOf.set(w,[]);winesOf.get(w).push(e)}}
   else if(e.kind==='vintage'){const w=e.data.wineId;if(w){if(!vintagesOf.has(w))vintagesOf.set(w,[]);vintagesOf.get(w).push(e)}}
  }
 }
 // 探索地图的产区 id 直接命中资料库产区；沿 regionId 向下递归展开子产区后取并集
 function scopeIds(rootId){
  const out=new Set(),queue=[rootId];
  while(queue.length){const id=queue.pop();if(out.has(id))continue;out.add(id);for(const kid of (children.get(id)||[]))queue.push(kid)}
  return out;
 }
 function winesFor(wineryId){return (winesOf.get(wineryId)||[]).map(wine=>({wine,vintages:(vintagesOf.get(wine.id)||[]).slice().sort((a,b)=>(b.data.year||0)-(a.data.year||0))}))}
 function photosFor(id){return (photoIndex[id]||[]).slice().sort((a,b)=>GROUP_ORDER.indexOf(a.group)-GROUP_ORDER.indexOf(b.group))}
 function photoCount(winery,links){return photosFor(winery.id).length+links.reduce((n,l)=>n+photosFor(l.wine.id).length,0)}
 // 品种名优先取已核对译文；其次用 data.js 的 GRAPE_EN 国际通用名；最后才回落中文原名
 function grapeLabel(grape,percent){const f=field(grape);const text=f.verified?f.text:(I.locale!=='zh'&&window.GRAPE_EN?.[f.text])||f.text;return E(text)+(percent!=null?' '+percent+'%':'')}
 function grapesText(d){return (d.grapes||[]).map(g=>{const ge=byId.get(g.id);return ge?grapeLabel(ge,g.percent):''}).filter(Boolean).join(' · ')}
 function regionField(id){const r=byId.get(id);return r&&r.kind==='region'?field(r):null}
 function regionHTML(id,tag='span'){const f=regionField(id);return f?`<${tag} data-no-i18n${langOf(f)}>${E(f.text)}</${tag}>`:''}
 function descriptionHTML(e){const f=I.description(e);return f.text?`<p class="collected-desc" data-no-i18n${langOf(f)}>${E(f.text)}</p>${I.contentNote(f)}`:''}

 function summary(regionId){
  const scope=scopeIds(regionId);
  const wineries=items.filter(e=>e.kind==='winery'&&scope.has(e.data.regionId));
  let wineTotal=0,photoTotal=0;const rich=[],plain=[];
  for(const winery of wineries){
   const links=winesFor(winery.id),photos=photosFor(winery.id),located=!!geo.coordinates(winery.data);
   wineTotal+=links.length;photoTotal+=photoCount(winery,links);
   const entry={winery,links,photos,located};
   if(links.length||photos.length)rich.push(entry);else plain.push(entry);
  }
  // 有酒款的最有价值，其次有图；其余按已定位优先、名称排序
  rich.sort((a,b)=>(b.links.length*4+b.photos.length)-(a.links.length*4+a.photos.length)||name(a.winery).localeCompare(name(b.winery),I.locale));
  // 排序：精确坐标(2) > 约略坐标(1) > 无坐标(0)，让「看得准的」排前面
 const rank=e=>!e.located?0:(e.winery.data.locationApproximate===true?1:2);
 plain.sort((a,b)=>rank(b)-rank(a)||name(a.winery).localeCompare(name(b.winery),I.locale));
  return {wineryTotal:wineries.length,wineTotal,photoTotal,rich,plain};
 }
const countCell=(key,n)=>`<span class="collected-count"><b>${Number(n).toLocaleString(I.locale)}</b> ${T(key)}</span>`;
function thumbHTML(photo,cls){
 if(!photo)return '';
 const size=photo.w&&photo.h?` width="${photo.w}" height="${photo.h}"`:'';
 return `<span class="${cls}"><img src="${E(photo.src)}" alt=""${size} loading="lazy" decoding="async"></span>`;
}
// 首次只生成前六张图片的节点，展开后再添加其余图片；原图链接保留。
const GALLERY_LIMIT=6;
function gridHTML(photos,limit){
 if(!photos.length)return '';
 const limited=photos.length>limit,galleryId=galleries.push(photos)-1;
 return `<div class="collected-gallery${limited?' is-limited':''}">`+
  photos.slice(0,limit).map(p=>`<a class="collected-shot" href="${E(p.src)}" target="_blank" rel="noopener"${p.note?` title="${E(p.note)}"`:''}><img src="${E(p.src)}" alt=""${p.w&&p.h?` width="${p.w}" height="${p.h}"`:''} loading="lazy" decoding="async"></a>`).join('')+
  `</div>`+(limited?`<button type="button" class="collected-gallery-more" data-gallery="${galleryId}">${T('展开全部')} ${photos.length} ${T('张图片')}</button>`:'');
}
function cardHTML({winery,links,photos,located}){
 const f=field(winery),original=winery.data.en;
 return `<article class="collected-winery">${thumbHTML(photos[0],'collected-thumb')}
<div class="collected-head"><h4>${nameHTML(winery)}</h4>${original&&original!==f.text?`<span class="collected-en" data-no-i18n>${E(original)}</span>`:''}</div>
<p class="collected-meta">${regionField(winery.data.regionId)?T('产地')+' · '+regionHTML(winery.data.regionId)+' · ':''}${T(!located?'位置待核对':(winery.data.locationApproximate===true?'约略位置':'已定位'))}${photos.length?' · '+photos.length+' '+T('张图片'):''}</p>
${gridHTML(photos.slice(1),GALLERY_LIMIT)}
${descriptionHTML(winery)}
${links.length?`<div class="collected-wines">${links.map(({wine,vintages})=>{const grapes=grapesText(wine.data),photo=photosFor(wine.id)[0];return `<div class="collected-wine">${thumbHTML(photo,'collected-wine-thumb')}<div class="collected-wine-body"><a class="collected-wine-name" href="${href(wine)}">${nameHTML(wine)} ↗</a><span class="collected-wine-tags">${wine.data.appellation?`<em data-no-i18n>${E(wine.data.appellation)}</em>`:''}${grapes?`<em data-no-i18n>${grapes}</em>`:''}${vintages.map(v=>`<b data-no-i18n>${E(vintageLabel(v))}</b>`).join('')}</span></div></div>`}).join('')}</div>`:''}
<div class="collected-links"><a href="${href(winery)}">${T('酒庄资料与来源')} ↗</a>${located?`<button type="button" class="collected-locate" data-locate="${E(winery.id)}">${T('在图上定位')}</button>`:''}</div></article>`;
}
 function rowHTML({winery,located}){
  return `<button type="button" class="collected-row" data-row="${E(winery.id)}" data-locate="${located?E(winery.id):''}"><span data-no-i18n>${E(name(winery))}</span>${regionHTML(winery.data.regionId,'span class="collected-row-meta"')}</button>`;
 }

 function render(){
  const body=$('detail')?.querySelector('.detail-body');
  if(!body)return;
  body.querySelector('#collectedWineries')?.remove();
  if(!current)return;
  galleries=[];
  const section=document.createElement('section');
  section.className='detail-section collected-wineries';section.id='collectedWineries';
  if(!items.length){
   section.innerHTML=`<div class="detail-label">${T('已收录酒庄与酒款')}</div><p class="collected-loading">${T('正在载入酒庄…')}</p>`;
  }else{
   const d=summary(current);
   const regionPhotos=photosFor(current);
   const rest=expanded?d.plain:d.plain.slice(0,MAX_COMPACT);
   section.innerHTML=`<div class="detail-label">${T('已收录酒庄与酒款')}</div>
<p class="collected-counts">${countCell('家酒庄',d.wineryTotal)}${countCell('款酒',d.wineTotal)}${countCell('张图片',d.photoTotal)}</p>
${regionPhotos.length?`<div class="collected-region-media"><div class="detail-label">${T('产区影像')}</div>${gridHTML(regionPhotos,GALLERY_LIMIT)}</div>`:''}
${d.rich.length?`<div class="collected-rich">${d.rich.slice(0,richLimit).map(cardHTML).join('')}</div>${d.rich.length>richLimit?`<button type="button" class="collected-more" id="collectedRichMore">${T('显示更多')} (${richLimit}/${d.rich.length})</button>`:''}`:''}
${d.plain.length?`<div class="collected-plain-wrap"><div class="detail-label">${T('其他公开记录中的酒庄')}</div><div class="collected-plain">${rest.map(rowHTML).join('')}</div>${d.plain.length>MAX_COMPACT?`<button type="button" class="collected-more" id="collectedMore">${expanded?T('收起'):T('显示全部')+' '+d.plain.length+' '+T('家酒庄')}</button>`:''}</div>`:''}
${!d.rich.length&&!d.plain.length?`<p class="detail-note">${T('该产区暂无已收录的酒庄资料')}</p>`:''}`;
  }
  const before=body.querySelector('#exploreParcels');
  if(before)body.insertBefore(section,before);else body.append(section);
  section.querySelectorAll('[data-locate]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();b.dataset.locate?locate(b.dataset.locate):null});
  section.querySelectorAll('[data-row]').forEach(b=>{if(!b.dataset.locate)b.onclick=()=>{location.href=href(byId.get(b.dataset.row))}});
  section.querySelectorAll('.collected-gallery-more').forEach(b=>b.onclick=()=>{const photos=galleries[Number(b.dataset.gallery)]||[];b.previousElementSibling.outerHTML=gridHTML(photos,photos.length);b.remove()});
  $('collectedRichMore')?.addEventListener('click',()=>{richLimit+=6;render()});
  $('collectedMore')?.addEventListener('click',()=>{expanded=!expanded;render()});
 }

 function popupHTML(winery,links){
  const d=I.description(winery);
  return `<div class="winery-popup"><span class="event-type">${T('酒庄')}${links.length?' · '+T('已收录')+' '+links.length+' '+T('款酒'):''}</span><h3>${nameHTML(winery)}</h3>${regionField(winery.data.regionId)?`<p>${regionHTML(winery.data.regionId)}</p>`:''}${d.text?`<p data-no-i18n${langOf(d)}>${E(d.text)}</p>`:''}${winery.data.address?`<p data-no-i18n>${E(winery.data.address)}</p>`:''}<div class="winery-wine-list">${links.length?links.map(({wine,vintages})=>`<article class="wine-at-estate"><a class="wine-title" href="${href(wine)}">${nameHTML(wine)} ↗</a>${vintages.length?`<p data-no-i18n>${vintages.map(v=>E(vintageLabel(v))).join(' · ')}</p>`:''}</article>`).join(''):`<p>${T('尚未收录对应酒款，欢迎补充。')}</p>`}</div><div class="popup-links"><a href="${href(winery)}">${T('酒庄资料与来源')} ↗</a></div></div>`;
 }
 // 复用酒庄页已有的定位交互：飞过去并用独立弹窗展示该酒庄与它的酒，不额外铺标记点
 function locate(id){
  const winery=byId.get(id);if(!winery)return;
  const point=geo.coordinates(winery.data);
  if(!point){location.href=href(winery);return}
  window.AtlasWineries?.open(id);
  document.querySelector('.explorer')?.classList.remove('open');
 }

 const previous=selectRegion;
 selectRegion=function(id){previous(id);current=id;expanded=false;richLimit=6;render();loadPhotos()};

 Promise.resolve(window.wineCatalogueReady).then(entities=>{items=entities||[];prepare();if(current)render()}).catch(()=>{});
})();
