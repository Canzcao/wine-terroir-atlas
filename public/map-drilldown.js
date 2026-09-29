(()=>{
 if(!window.L||!map)return;
 const E=escapeHTML,I=WineI18n,T=s=>E(I.t(s));
 let items=[],tree=WineMapModel.hierarchy([]),country='',region='',ready=false;
 const nav=document.createElement('nav');nav.className='atlas-breadcrumb';nav.setAttribute('aria-label',I.t('地图层级'));document.querySelector('.explore-tabs').after(nav);
 const originalRender=renderList,originalSelect=selectRegion;
 const navigationLayer=L.layerGroup().addTo(map);let navigationRows=[],countryShapes=null;
 function renderNavigation(){
  navigationLayer.clearLayers();$('atlasUnlocated')?.remove();const missing=navigationRows.filter(r=>!r.point);if(missing.length){const box=document.createElement('div');box.id='atlasUnlocated';box.innerHTML='<small>'+T('位置待核对')+'</small>'+missing.map(r=>'<button data-missing="'+E(r.id)+'" data-no-i18n>'+E(r.name)+' ›</button>').join('');document.querySelector('.map-shell').append(box);box.querySelectorAll('[data-missing]').forEach(b=>b.onclick=()=>go(b.dataset.missing))}const size=map.getSize(),placed=[];
  if(!country&&countryShapes){const countries=new Set(navigationRows.map(r=>r.id.slice(8)));L.geoJSON(countryShapes,{filter:f=>countries.has(f.properties.name),style:{color:'#753b59',weight:1,fillColor:'#753b59',fillOpacity:.09},onEachFeature:(f,l)=>{l.on('click',()=>go('country:'+f.properties.name));l.on('mouseover',()=>l.setStyle({fillOpacity:.22}));l.on('mouseout',()=>l.setStyle({fillOpacity:.09}));l.bindTooltip(E(I.country(f.properties.name)))}}).addTo(navigationLayer)}
 // 触摸端把层级导航胶囊加高到 40px（与 responsive.css 的 .atlas-navigation-marker>span 保持一致）
 const navH=window.matchMedia('(max-width:1100px)').matches?40:32;
  for(const r of navigationRows){if(!r.point)continue;const p=map.latLngToContainerPoint(r.point);if(p.x<0||p.x>size.x||p.y<0||p.y>size.y)continue;const width=Math.min(175,Math.max(66,Array.from(r.name).reduce((n,c)=>n+(c.charCodeAt(0)>255?14:8),24))),height=navH;let box;
   for(let step=0;step<240;step++){const ring=Math.ceil(step/8),angle=(step%8)*Math.PI/4;const x=Math.max(8,Math.min(size.x-width-8,p.x-width/2+Math.cos(angle)*ring*38)),y=Math.max(110,Math.min(size.y-height-65,p.y-height/2+Math.sin(angle)*ring*38));const candidate={x,y,width,height};if(!placed.some(b=>x<b.x+b.width+6&&x+width+6>b.x&&y<b.y+b.height+5&&y+height+5>b.y)){box=candidate;break}}
   box=box||{x:p.x-width/2,y:p.y-height/2,width,height};placed.push(box);const anchor=[p.x-box.x,p.y-box.y];const labelCenter=map.containerPointToLatLng([box.x+width/2,box.y+height/2]);if(Math.hypot(p.x-box.x-width/2,p.y-box.y-height/2)>24)L.polyline([r.point,labelCenter],{color:'#753b59',weight:1,opacity:.55,interactive:false}).addTo(navigationLayer);
   L.marker(r.point,{title:I.t('进入')+' '+r.name,keyboard:true,zIndexOffset:900,icon:L.divIcon({className:'atlas-navigation-marker',html:'<span data-no-i18n>'+E(r.name)+' <b aria-hidden="true">›</b></span>',iconSize:[width,height],iconAnchor:anchor})}).on('click',()=>{map.closePopup();go(r.id)}).addTo(navigationLayer);
  }
 }
 map.on('zoomend moveend resize',renderNavigation);
 fetch('/assets/world.geojson').then(r=>r.json()).then(data=>{countryShapes=data;renderNavigation()}).catch(()=>{});
 function scope(e){const d=e.data||e;if(country&&d.country&&d.country!==country)return false;if(!region)return true;const rid=e.kind==='region'?e.id:e.kind?d.regionId:tree.eventRegion(e);return tree.within(rid,region)}
 function notify(){window.dispatchEvent(new Event('atlas-scope-change'));AtlasPoints.refresh()}
 function title(){return region?I.name(tree.regions.get(region)):country?I.country(country):I.t('世界葡萄酒地图')}
 function crumbs(){const links=[{id:'',name:I.t('世界')}];if(country)links.push({id:'country:'+country,name:I.country(country)});if(region)for(const r of tree.ancestors(region))links.push({id:r.id,name:I.name(r)});
  nav.innerHTML=(links.length>1?`<button id="atlasBack" aria-label="${T('返回上一级')}">←</button>`:'')+links.map((l,i)=>`<button data-level="${E(l.id)}" ${i===links.length-1?'aria-current="page"':''} data-no-i18n>${E(l.name)}</button>`).join('<span aria-hidden="true">/</span>');nav.querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>go(b.dataset.level));$('atlasBack')?.addEventListener('click',()=>go(links[links.length-2].id));
 }
 function fit(points,zoom=10){const valid=points.filter(WineMapModel.valid);if(valid.length)map.flyToBounds(valid,{padding:[55,85],maxZoom:zoom,duration:.7})}
 function go(id){$('search').value='';$('grape').value='';$('detail').hidden=true;
  if(!id){country='';region='';selected=null;$('country').value='';map.flyToBounds([[-57,-174],[66,178]],{padding:[25,90],maxZoom:3,duration:.7})}
  else if(id.startsWith('country:')){country=id.slice(8);region='';selected=null;$('country').value=country;fit([...tree.regions.values()].filter(r=>r.data.country===country).map(r=>WineGeo.coordinates(r.data)),6)}
  else{selectRegion(id);return}
  $('mapTitle').textContent=title();$('mapSubtitle').textContent=I.t('选择国家或产区，逐级探索');render();notify();window.setExplorerMode('regions');
 }
 function cards(rows){return rows.map(r=>`<button class="region-card atlas-card" data-level="${E(r.id)}"><span class="region-copy"><span class="location" data-no-i18n>${E(r.label)}</span><h3 data-no-i18n>${E(r.name)}</h3><span class="card-grapes" data-no-i18n>${E(r.meta||'')}</span></span><span class="arrow">→</span></button>`).join('')}
 function regionRow(r){const children=tree.children(r.id),count=items.filter(e=>e.kind==='winery'&&tree.within(e.data.regionId,r.id)).length;return {id:r.id,name:I.name(r),label:I.country(r.data.country),meta:children.length+' '+I.t('子产区')+' · '+count+' '+I.t('家酒庄'),point:WineGeo.coordinates(r.data)}}
 function render(){if(!ready)return originalRender();crumbs();regionLayer.clearLayers();
  $('atlasMapNav')?.remove();if(country){const controls=document.createElement('div');controls.id='atlasMapNav';const chain=region?tree.ancestors(region):[],parent=chain.length>1?chain[chain.length-2].id:region?'country:'+country:'';controls.innerHTML=`<button id="atlasMapBack">← ${T('返回上一级')}</button>`+(region?`<button id="atlasMapOverview">${T('产区概览')}</button>`:'');document.querySelector('.map-heading').append(controls);$('atlasMapBack').onclick=()=>go(parent);$('atlasMapOverview')?.addEventListener('click',()=>{$('detail').hidden=!$('detail').hidden})}

  const q=normalizeSearchText($('search').value.trim()),grape=$('grape').value;let rows=[];
  if(q||grape){rows=[...tree.regions.values()].filter(r=>{const legacy=regions.find(x=>x.id===r.id);return (!grape||legacy?.grapes.includes(grape))&&(!q||q.split(/\s+/).every(w=>normalizeSearchText([WineLanguage.searchText(r),r.id,r.data.country,I.country(r.data.country),regionSearchIndex.get(r.id)||''].join(' ')).includes(w)))}).map(regionRow)}
  else if(!country){rows=[...new Set([...tree.regions.values()].map(r=>r.data.country).filter(Boolean))].map(c=>{const rs=[...tree.regions.values()].filter(r=>r.data.country===c),points=rs.map(r=>WineGeo.coordinates(r.data)).filter(Boolean);return{id:'country:'+c,name:I.country(c),label:I.t('国家'),meta:rs.length+' '+I.t('产区'),point:points[0]}})}
  else rows=tree.children(region,country).map(regionRow);
  $('resultCount').textContent=rows.length;
  let html=q?`<p class="atlas-hint">${T('全球产区搜索结果')}</p>`:'';html+=cards(rows);
  if(region&&!q&&!grape){const ws=items.filter(e=>e.kind==='winery'&&e.data.regionId===region);html+=`<div class="atlas-section">${T('本层酒庄')} · ${ws.length}</div>`;html+=ws.map(w=>`<button class="region-card atlas-card" data-estate="${E(w.id)}"><span class="region-copy"><h3 data-no-i18n>${E(I.name(w))}</h3><span class="card-grapes">${T(WineGeo.coordinates(w.data)?'已定位':'位置待核对')} · ${WineGeo.winesFor(w.id,items).length} ${T('款酒')}</span></span><span class="arrow">↗</span></button>`).join('');if(!rows.length)html+=`<p class="atlas-hint">${T('暂无已收录的下级产区。')}</p>`}
  if(q){const matches=items.filter(e=>['winery','wine'].includes(e.kind)&&q.split(/\s+/).every(w=>normalizeSearchText(WineLanguage.searchText(e)).includes(w)));html+=matches.map(e=>{const w=WineGeo.wineryFor(e,items);return `<button class="region-card atlas-card" ${w?'data-estate="'+E(w.id)+'"':'data-record="'+E(e.id)+'"'}><span class="region-copy"><span class="location">${T(e.kind==='wine'?'酒款':'酒庄')}</span><h3 data-no-i18n>${E(I.name(e))}</h3></span><span class="arrow">↗</span></button>`}).join('')}
  $('regionList').innerHTML=html||`<p class="empty">${T('没有找到匹配的产区。')}</p>`;
  $('regionList').querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>go(b.dataset.level));$('regionList').querySelectorAll('[data-estate]').forEach(b=>b.onclick=()=>window.AtlasWineries?.open(b.dataset.estate));
  $('regionList').querySelectorAll('[data-record]').forEach(b=>b.onclick=()=>location.href='/catalog?entity='+encodeURIComponent(b.dataset.record));
  AtlasPoints.set('navigation',[]);navigationRows=rows;renderNavigation();
 }
 renderList=function(){if(ready){const selectedCountry=$('country').value;if(selectedCountry!==country){country=selectedCountry;region='';selected=null;notify()}render()}else originalRender()};
 selectRegion=function(id){const r=tree.regions.get(id);if(!r){originalSelect(id);return}country=r.data.country||'';region=id;$('country').value=country;$('search').value='';originalSelect(id);if(!WineGeo.coordinates(r.data))fit(items.filter(e=>e.kind==='winery'&&tree.within(e.data.regionId,id)).map(e=>WineGeo.coordinates(e.data)),11);const children=tree.children(id);if(children.length)fit([WineGeo.coordinates(r.data),...children.map(c=>WineGeo.coordinates(c.data))],10);if(children.length){const section=document.createElement('section');section.className='atlas-children';section.innerHTML=`<div class="detail-label">${T('继续探索子产区')}</div>`+cards(children.map(regionRow));section.querySelectorAll('[data-level]').forEach(b=>b.onclick=()=>go(b.dataset.level));$('detail').querySelector('.detail-body')?.prepend(section)}if(children.length)$('detail').hidden=true;render();notify();window.setExplorerMode('regions')};
 $('worldButton').onclick=()=>{cancelParcelRequest();regionRequest++;go('')};$('reset').onclick=()=>go('');
 $('search').oninput=()=>renderList();$('grape').onchange=()=>renderList();
 $('country').onchange=()=>go($('country').value?'country:'+$('country').value:'');
 window.AtlasScope={matches:scope,get region(){return region},get country(){return country},go};
 window.wineCatalogueReady.then(entities=>{items=entities;tree=WineMapModel.hierarchy(items);
  for(const r of tree.regions.values()){if(!regions.some(x=>x.id===r.id)){const d=r.data;regions.push({...r,...d,continent:regions.find(x=>x.country===d.country)?.continent||'',desc:d.description||d.notes||'',source:d.sourceURL,zoom:11,grapes:(d.grapes||[]).map(g=>items.find(e=>e.id===g.id)?.name).filter(Boolean),wineries:[]})}}
  $('coverage').textContent=I.t('国家')+' '+new Set([...tree.regions.values()].map(r=>r.data.country)).size+' · '+I.t('产区')+' '+tree.regions.size;ready=true;const initial=selected;if(initial&&tree.regions.has(initial)){region=initial;country=tree.regions.get(initial).data.country;$('country').value=country}render();notify();if(!new URLSearchParams(location.search).has('entity'))window.setExplorerMode('regions');
 }).catch(()=>{nav.textContent=I.t('产区层级暂时无法载入，请刷新重试。')});
})();
