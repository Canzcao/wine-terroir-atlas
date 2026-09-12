(()=>{
 if(!window.L||!map)return;
 const E=escapeHTML,geo=WineGeo,I=WineI18n,C=WineLanguage,T=text=>E(I.t(text));
 const layer=L.layerGroup().addTo(map);let items=[],markers=new Map();
 const field=(e,key='name')=>C.field(e,key,I.locale);
 const name=e=>I.name(e),lang=f=>f.language?` lang="${E(f.language)}"`:'';
 const nameHTML=e=>{const f=field(e);return `<span data-no-i18n${lang(f)}>${E(f.text)}</span>`};
 const notes=(...fields)=>{const seen=new Set();return fields.filter(f=>f.text&&f.fallback&&!seen.has(f.language)&&seen.add(f.language)).map(I.contentNote).join('')};
 const button=document.createElement('button');button.id='wineriesTab';button.textContent=I.t('酒庄与酒款');document.querySelector('.explore-tabs').append(button);
 const pane=document.createElement('section');pane.id='wineriesPane';pane.className='events-pane wineries-pane';pane.hidden=true;
 pane.innerHTML=`<div class="events-intro"><div class="eyebrow">WINERIES & THEIR WINES</div><h1>${T('一座酒庄，它的酒')}</h1><p>${T('每日发现与补充 · 酒款随酒庄位置展示')}</p></div><div class="winery-search"><label class="search"><span aria-hidden="true">⌕</span><input id="winerySearch" type="search" placeholder="${T('搜索酒庄、酒款、品种或国家')}" aria-label="${T('搜索酒庄与酒款')}"></label><div class="winery-options"><label><input type="checkbox" id="locatedOnly"> ${T('只看已定位')}</label><label><input type="checkbox" id="showWineryPins" checked> ${T('地图酒庄点')}</label></div></div><p class="winery-count" id="wineryCount" role="status">${T('正在载入酒庄…')}</p><div class="event-feed" id="wineryFeed"></div><div class="events-bottom">${T('找不到熟悉的酒庄？')} <a href="/community">${T('补充资料')} ↗</a><small>${T('标记为酒庄或已注明的到访位置；酒款位于生产者点位，不代表葡萄来源地块。')}</small></div>`;
 document.querySelector('.explorer').append(pane);button.onclick=()=>window.setExplorerMode('wineries');
 const href=e=>'/catalog?entity='+encodeURIComponent(e.id)+'&lang='+encodeURIComponent(I.locale);
 const vintageLabel=e=>e.data.yearType==='nv'?I.t('无年份（NV）'):e.data.yearType==='unknown'?I.t('年份未知'):e.data.year||I.t('年份待补');
 function grapeText(d){return(d.grapes||[]).map(g=>{const grape=items.find(e=>e.id===g.id);return(grape?name(grape):I.t('品种待核对'))+(g.percent==null?'':' '+g.percent+'%')}).join(' · ')}
 function grapeSearch(d){return(d.grapes||[]).map(g=>{const grape=items.find(e=>e.id===g.id);return grape?C.searchText(grape):''}).join(' ')}
 function descriptionHTML(e,tag='p',className=''){const f=I.description(e);return f.text?`<${tag} class="${className}" data-no-i18n${lang(f)}>${E(f.text)}</${tag}>`:''}
 function popup(w,highlight){
  const d=w.data,links=geo.winesFor(w.id,items),nf=field(w),df=I.description(w);
  return `<div class="winery-popup"><span class="event-type"><span data-no-i18n>${E(I.country(d.country))}</span> · ${T('酒庄')}${links.length?' · '+T('已收录')+' '+links.length+' '+T('酒款'):''}</span><h3>${nameHTML(w)}</h3>${d.en&&d.en!==nf.text?`<p class="winery-original" data-no-i18n>${E(d.en)}</p>`:''}${descriptionHTML(w)}${notes(nf,df)}<p><span data-no-i18n>${E(d.locationPrecision||I.t('已收录酒庄位置'))}</span>${d.address?'<br><span data-no-i18n>'+E(d.address)+'</span>':''}</p><div class="winery-wine-list">${links.length?links.map(({wine,vintages})=>{const wn=field(wine),wd=I.description(wine);return `<article class="wine-at-estate ${wine.id===highlight||vintages.some(v=>v.id===highlight)?'highlight':''}"><a class="wine-title" href="${href(wine)}">${nameHTML(wine)} ↗</a>${descriptionHTML(wine,'p','wine-description')}${notes(wn,wd)}${vintages.length?vintages.map(v=>`<div class="vintage-at-estate"><a href="${href(v)}"><span data-no-i18n>${E(vintageLabel(v))}</span> ↗</a><span data-no-i18n>${E(grapeText(v.data)||I.t('品种资料待补'))}</span></div>`).join(''):`<p data-no-i18n>${E(grapeText(wine.data)||I.t('年份与品种资料待补'))}</p>`}</article>`}).join(''):`<p>${T('尚未收录对应酒款，欢迎补充。')}</p>`}</div><div class="popup-links"><a href="${href(w)}">${T('酒庄资料与来源')} ↗</a>${d.locationSourceURL?`<a href="${E(d.locationSourceURL)}" target="_blank" rel="noopener">${T('位置依据')} ↗</a>`:''}${links.length?`<a href="/catalog?winery=${encodeURIComponent(w.id)}&lang=${encodeURIComponent(I.locale)}">${T('浏览酒款目录')} ↗</a>`:''}</div>${d.checkedDate?`<small>${T('资料核对')}：<span data-no-i18n>${E(d.checkedDate)}</span></small>`:''}</div>`;
 }
 function openWinery(w,highlight){
  const loc=geo.locationFor(w,items);$('detail').hidden=true;
  if(loc&&!loc.approximate){map.setView(loc.point,13);const marker=markers.get(w.id);if(marker){marker.setPopupContent(popup(w,highlight));if(!map.hasLayer(layer)){$('showWineryPins').checked=true;layer.addTo(map)}marker.openPopup()}}
  else if(loc){map.setView(loc.point,8);L.popup().setLatLng(loc.point).setContent(`<h3>${nameHTML(w)}</h3>${notes(field(w))}<p data-no-i18n>${E(loc.precision)}</p><a href="${href(w)}">${T('查看酒庄与对应酒款')} ↗</a>`).openOn(map)}
  else{location.href=href(w);return}
  document.querySelector('.explorer').classList.remove('open');$('mobileToggle').textContent=I.t('动态与产区');
 }
 function render(){
  const q=$('winerySearch').value.toLocaleLowerCase(I.locale).trim();
  const wineries=items.filter(e=>e.kind==='winery').filter(w=>{
   const loc=geo.locationFor(w,items);
   const search=[C.searchText(w),w.name,w.data.country,I.country(w.data.country),...geo.winesFor(w.id,items).flatMap(({wine,vintages})=>[C.searchText(wine),wine.name,grapeSearch(wine.data),...vintages.map(v=>C.searchText(v)+' '+grapeSearch(v.data))])].join(' ').toLocaleLowerCase(I.locale);
   return (!$('locatedOnly').checked||loc&&!loc.approximate)&&(!q||search.includes(q));
  }).sort((a,b)=>Number(!!geo.coordinates(b.data))-Number(!!geo.coordinates(a.data))||name(a).localeCompare(name(b),I.locale));
  const located=wineries.filter(w=>geo.coordinates(w.data));
  $('wineryCount').textContent=I.t('酒庄')+' '+wineries.length+' · '+I.t('已定位')+' '+located.length+' · '+I.t('酒款')+' '+wineries.reduce((n,w)=>n+geo.winesFor(w.id,items).length,0);
  $('wineryFeed').innerHTML=wineries.length?wineries.map(w=>{
   const links=geo.winesFor(w.id,items),point=geo.coordinates(w.data),nf=field(w),df=I.description(w);
   return `<button class="winery-card" data-winery="${E(w.id)}"><span class="event-card-meta"><span data-no-i18n>${E(I.country(w.data.country))}</span><b>${T(point?'已定位':'位置待核对')}</b></span><strong>${nameHTML(w)}</strong>${w.data.en&&w.data.en!==nf.text?`<span class="event-date" data-no-i18n>${E(w.data.en)}</span>`:''}${descriptionHTML(w,'span','event-summary')}${notes(nf,df)}<span class="event-summary">${links.length?links.slice(0,2).map(({wine})=>nameHTML(wine)+I.contentNote(field(wine))).join(' · ')+(links.length>2?' …':''):T('酒款资料待补充')}</span><span class="event-source">${T('酒款')} ${links.length} · ${T('年份资料')} ${links.reduce((n,w)=>n+w.vintages.length,0)} · ${T(point?'在地图查看':geo.locationFor(w,items)?'查看所属产区':'查看资料')} ↗</span></button>`;
  }).join(''):`<div class="empty">${T('没有匹配的酒庄或酒款。')}<br>${T('可以清空搜索，或补充新资料。')}</div>`;
  markers.clear();layer.clearLayers();
  for(const w of located){const wines=geo.winesFor(w.id,items);const marker=L.marker(geo.coordinates(w.data),{icon:L.divIcon({className:'estate-marker',html:'<span aria-hidden="true">'+(I.locale==='zh'?'庄':'W')+'</span>'+(wines.length?'<b>'+wines.length+'</b>':''),iconSize:[32,32],iconAnchor:[16,16]}),title:name(w)+' · '+I.t('酒款')+' '+wines.length,zIndexOffset:300}).addTo(layer).bindPopup(popup(w),{maxWidth:370,minWidth:260,maxHeight:430}).bindTooltip(nameHTML(w),{direction:'top',offset:[0,-15]});markers.set(w.id,marker)}
  document.querySelectorAll('[data-winery]').forEach(b=>b.onclick=()=>openWinery(items.find(w=>w.id===b.dataset.winery)));
 }
 $('winerySearch').oninput=render;$('locatedOnly').onchange=render;$('showWineryPins').onchange=e=>e.target.checked?layer.addTo(map):map.removeLayer(layer);
 window.wineCatalogueReady.then(entities=>{items=entities;render();const eid=new URLSearchParams(location.search).get('entity'),record=items.find(e=>e.id===eid);if(record&&['winery','wine','vintage'].includes(record.kind)){const winery=geo.wineryFor(record,items);window.setExplorerMode('wineries');if(winery)openWinery(winery,eid);else showStatus(I.t('这款酒暂未关联到已收录酒庄，请在资料库补充。'))}}).catch(()=>{$('wineryCount').textContent=I.t('酒庄资料暂时无法载入，请稍后刷新。')});
})();
