(function(root){
 if(root.WINE_UI_LABELS)Object.assign(root.WINE_UI_LABELS,Object.fromEntries(Object.entries({
  '地图层级':'Map navigation','返回上一级':'Back one level','世界':'World','选择国家或产区，逐级探索':'Choose a country or region to explore','子产区':'Subregions','本层酒庄':'Wineries in this region','全球产区搜索结果':'Global search results','暂无已收录的下级产区。':'No subregions have been recorded yet.','继续探索子产区':'Explore subregions','同一地图位置':'At this map location','附近内容':'Nearby places','逐条查看内容；位置精度以各条资料为准。':'Open each entry; location precision is stated in its details.','这些地点在当前比例下靠近；放大可分开查看。':'These places are close at this scale. Zoom in to separate them.','放大查看':'Zoom in','进入':'Explore','查看此处内容':'View entries here','标记为浏览中心，不表示法定边界。':'A browsing reference point, not a legal boundary.','酒款随酒庄位置展示':'Wines are shown at their producer location','产区层级暂时无法载入，请刷新重试。':'Region navigation could not load. Please refresh.'
 }).map(([k,v])=>[k,{en:v}])));
 const norm=s=>String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
 const valid=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180;
 function hierarchy(records){
  const regions=new Map(records.filter(e=>e.kind==='region').map(e=>[e.id,e]));
  function ancestors(id){const out=[],seen=new Set();while(regions.has(id)&&!seen.has(id)){seen.add(id);out.unshift(regions.get(id));id=regions.get(id).data.regionId}return out}
  function within(id,parent){return !parent||ancestors(id).some(e=>e.id===parent)}
  function children(id,country){return [...regions.values()].filter(e=>(!country||e.data.country===country)&&(id?e.data.regionId===id:!regions.has(e.data.regionId)))}
  // Match declared region names only, never infer membership from proximity.
  function eventRegion(e){if(regions.has(e.regionId))return e.regionId;const text=norm(e.region);return [...regions.values()].filter(r=>r.data.country===e.country).sort((a,b)=>norm(b.data.en||b.name).length-norm(a.data.en||a.name).length).find(r=>[r.name,r.data.en,...Object.values(r.data.localizations||{}).filter(l=>l.status==='verified').map(l=>l.name)].filter(Boolean).some(n=>text===norm(n)||text.split(/[·（(]/)[0].trim()===norm(n)))?.id||null}
  return {regions,ancestors,within,children,eventRegion};
 }
 function cluster(entries,project,radius=36){
  const groups=[],cells=new Map(),cellSize=radius>0?radius:1;
  for(const item of entries){
   if(!valid(item.point))continue;
   const p=project(item.point),x=Math.floor(p.x/cellSize),y=Math.floor(p.y/cellSize);
   let group,first=Infinity;
   for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){
    for(const index of cells.get(`${x+dx},${y+dy}`)||[]){
     const g=groups[index];
     if(index<first&&Math.hypot(g.pixel.x-p.x,g.pixel.y-p.y)<radius){group=g;first=index}
    }
   }
   if(!group){const key=`${x},${y}`;if(!cells.has(key))cells.set(key,[]);cells.get(key).push(groups.length);group={point:item.point,pixel:p,items:[]};groups.push(group)}
   group.items.push(item);
  }
  for(const g of groups)g.samePoint=g.items.every(e=>Math.abs(e.point[0]-g.point[0])<0.00001&&Math.abs(e.point[1]-g.point[1])<0.00001);
  return groups;
 }
 root.WineMapModel={hierarchy,cluster,valid};
})(globalThis);
