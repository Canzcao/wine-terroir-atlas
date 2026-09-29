(()=>{
 if(!window.L||!map)return;
 const sources=new Map(),layer=L.layerGroup().addTo(map),E=escapeHTML,I=WineI18n;
 let groups=[],pending=false;
 function content(group,focus){
  const box=document.createElement('div');box.className='shared-location';
  if(group.items.length>1){const title=document.createElement('h3');title.textContent=I.t(group.samePoint?'同一地图位置':'附近内容')+' · '+group.items.length;box.append(title);const hint=document.createElement('p');hint.className='location-hint';hint.textContent=I.t(group.samePoint?'逐条查看内容；位置精度以各条资料为准。':'这些地点在当前比例下靠近；放大可分开查看。');box.append(hint)}
  if(group.items.length>1&&!group.samePoint){const zoom=document.createElement('button');zoom.className='primary';zoom.textContent=I.t('放大查看');zoom.onclick=()=>map.fitBounds(group.items.map(e=>e.point),{padding:[55,55],maxZoom:Math.min(map.getZoom()+3,18)});box.append(zoom)}
  const sorted=[...group.items].sort((a,b)=>Number(b.id===focus)-Number(a.id===focus));
  for(const e of sorted){const section=document.createElement('div');section.className='location-entry';
   if(group.items.length>1){const button=document.createElement(e.href?'a':'button');button.className='location-choice';button.textContent=e.label+' · '+e.title+' →';if(e.href)button.href=e.href;else button.onclick=()=>showEntry(e,group);section.append(button)}
   else{const body=document.createElement('div');body.className='location-entry-body';body.innerHTML=typeof e.html==='function'?e.html():e.html||'';section.append(body);const link=document.createElement(e.href?'a':'button');link.className='primary';link.textContent=I.t('查看完整资料')+' →';if(e.href)link.href=e.href;else link.onclick=()=>showEntry(e,group);section.append(link)}
   box.append(section)
  }return box;
 }
 function showEntry(e,group){
  map.closePopup();const detail=$('detail');detail.hidden=false;detail.setAttribute('aria-label',e.title);detail.innerHTML='<div class="detail-body"><button class="detail-close" id="closeLocationEntry" aria-label="'+E(I.t('关闭'))+'">×</button><button class="location-back" id="backToLocation">← '+E(I.t('返回此位置的全部内容'))+'</button><div class="location-entry-detail">'+(typeof e.html==='function'?e.html():e.html||'')+'</div></div>';
  $('closeLocationEntry').onclick=()=>{detail.hidden=true};$('backToLocation').onclick=()=>{detail.hidden=true;open(e.id)};document.querySelector('.explorer')?.classList.remove('open');

 }
 function render(){pending=false;layer.clearLayers();let entries=[...sources.values()].flat().filter(e=>!e.visible||e.visible());groups=WineMapModel.cluster(entries,p=>map.latLngToLayerPoint(p));
  // 触摸端把点位圆标放大到 44px（与 responsive.css 的 .atlas-point>span 保持一致）
  const S=window.matchMedia('(max-width:1100px)').matches?44:34;
  // className 由调用方给（酒庄列表用 'atlas-point-approx' 标记「约略坐标」的点）。
  for(const g of groups){const first=g.items[0],multi=g.items.length>1;const marker=L.marker(g.point,{title:multi?I.t('查看此处内容')+' · '+g.items.length:first.title,icon:L.divIcon({className:'atlas-point '+(multi?'atlas-group':'')+(first.className?' '+first.className:''),html:'<span>'+E(multi?g.items.length:first.symbol||'●')+'</span>',iconSize:[S,S],iconAnchor:[S/2,S/2]}),zIndexOffset:400}).addTo(layer);g.marker=marker;marker.bindPopup(()=>content(g),{maxWidth:390,minWidth:260,maxHeight:430});marker.bindTooltip(E(multi?I.t(g.samePoint?'同一地图位置':'附近内容')+' · '+g.items.length:first.title));}
 }
 function schedule(){if(!pending){pending=true;queueMicrotask(()=>{if(pending)render()})}}
 function open(id){if(pending)render();const g=groups.find(g=>g.items.some(e=>e.id===id));if(!g)return false;g.marker.setPopupContent(content(g,id)).openPopup();return true}
 window.AtlasPoints={set:(key,items)=>{sources.set(key,items);schedule()},refresh:schedule,open};map.on('zoomend resize',schedule);
})();
