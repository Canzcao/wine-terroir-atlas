(function(root){
 // 坐标分两档，字段语义固定，别混用：
 //   · 精确（无 locationApproximate 字段）—— OSM 里就是这座酒庄的要素、官网地图、官方登记门牌地址。
 //   · 约略（locationApproximate:true）—— 只解析到街道／城镇／产区级，位置上「对的城市、错的点」。
 // 消费方约定：`approximate` 只用来「区分精度」，不用来「判断有没有坐标」；
 // 判断有没有坐标一律看 coordinates(data)，否则地图会把约略点位整批丢掉（2026-09-21 修）。
 // Catalogues are replaced on refresh; cache indexes by snapshot identity.
 const snapshots=new WeakMap();
 function indexes(items){let result=snapshots.get(items);if(result)return result;
  const byId=new Map(),wines=new Map(),vintages=new Map();
  for(const e of items){byId.set(e.id,e);if(e.kind==='vintage'){const id=e.data.wineId;if(!vintages.has(id))vintages.set(id,[]);vintages.get(id).push(e)}}
  for(const rows of vintages.values())rows.sort((a,b)=>(b.data.year||0)-(a.data.year||0));
  for(const e of items)if(e.kind==='wine'){const id=e.data.wineryId;if(!wines.has(id))wines.set(id,[]);wines.get(id).push({wine:e,vintages:vintages.get(e.id)||[]})}
  for(const rows of wines.values())rows.sort((a,b)=>a.wine.name.localeCompare(b.wine.name,'zh-CN'));
  result={byId,wines};snapshots.set(items,result);return result;
 }
 const indexed=items=>indexes(items).byId;
 const coordinates=d=>d&&typeof d.lat==='number'&&typeof d.lng==='number'&&Number.isFinite(d.lat)&&Number.isFinite(d.lng)&&Math.abs(d.lat)<=90&&Math.abs(d.lng)<=180?[d.lat,d.lng]:null;
 function wineryFor(record,items){const byId=indexed(items);let e=record,seen=new Set();while(e&&!seen.has(e.id)){seen.add(e.id);if(e.kind==='winery')return e;e=byId.get(e.kind==='vintage'?e.data.wineId:e.kind==='wine'?e.data.wineryId:null)}return null}
 function locationFor(record,items){if(!record)return null;const byId=indexed(items),winery=wineryFor(record,items);if(winery){const point=coordinates(winery.data);if(point)return {point,anchorId:winery.id,precision:winery.data.locationPrecision||'已收录酒庄位置',approximate:winery.data.locationApproximate===true,kind:'winery'}}
  if(!['wine','vintage'].includes(record.kind)){const point=coordinates(record.data);if(point)return {point,anchorId:record.id,precision:record.data.locationPrecision||'记录位置',approximate:false,kind:record.kind};const g=record.data.geometry;if(g?.type==='Polygon'&&g.coordinates?.[0]?.length){const ring=g.coordinates[0];return {point:[(Math.min(...ring.map(p=>p[1]))+Math.max(...ring.map(p=>p[1])))/2,(Math.min(...ring.map(p=>p[0]))+Math.max(...ring.map(p=>p[0])))/2],anchorId:record.id,precision:record.data.locationPrecision||'地块轮廓中心',approximate:false,kind:record.kind}}}
  const wine=record.kind==='vintage'?byId.get(record.data.wineId):null;const candidates=[record.data.regionId,wine?.data.regionId,winery?.data.regionId];for(const candidate of candidates){let rid=candidate,seen=new Set();while(rid&&!seen.has(rid)){seen.add(rid);const region=byId.get(rid);if(region?.kind!=='region')break;const point=coordinates(region.data);if(point)return {point,anchorId:region.id,precision:'仅为'+region.name+'产区代表点，酒庄具体位置待核对',approximate:true,kind:'region'};rid=region.data.regionId}}return null;
 }
 function winesFor(wineryId,items){return indexes(items).wines.get(wineryId)||[]}

 root.WineGeo={coordinates,wineryFor,locationFor,winesFor};
})(globalThis);
