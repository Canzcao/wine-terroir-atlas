export const kinds={region:'产区',grape:'葡萄品种',parcel:'地块',winery:'酒庄',wine:'酒款',vintage:'年份酒',event:'世界动态'};
export const now=()=>new Date().toISOString();
export const id=()=>crypto.randomUUID();
export function fail(message,status=400){throw Object.assign(new Error(message),{status})}
export function cleanText(v,max=200){return String(v??'').trim().slice(0,max)}
export function safeURL(v){if(!v)return '';try{let u=new URL(v);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)throw 0;return u.href}catch{fail('资料链接须为完整的 http 或 https 地址。')}}
export function normalize(data,kind,complete=false){
 if(!kinds[kind]||!data||typeof data!=='object'||Array.isArray(data))fail('未知的资料类型。');
 const d={};for(const k of ['name','en','country','regionId','wineryId','wineId','yearType','sourceTitle','sourceType','locationPrecision','address','checkedDate','relationship','since','until','eventType','startDate','endDate','publishedDate','dateNote'])d[k]=cleanText(data[k]);
 d.notes=cleanText(data.notes,4000);d.aliases=Array.isArray(data.aliases)?data.aliases.map(v=>cleanText(v)).filter(Boolean).slice(0,30):[];
 d.sourceURL=safeURL(data.sourceURL);d.website=safeURL(data.website);d.locationSourceURL=safeURL(data.locationSourceURL);
 d.attachments=Array.isArray(data.attachments)?[...new Set(data.attachments.map(v=>cleanText(v,80)))].slice(0,5):[];
 d.grapes=Array.isArray(data.grapes)?data.grapes.slice(0,30).map(g=>({id:cleanText(g.id),percent:g.percent===''||g.percent==null?null:Number(g.percent)})):[];
 if(d.grapes.some(g=>!g.id||(g.percent!=null&&(!Number.isFinite(g.percent)||g.percent<0||g.percent>100))))fail('葡萄品种与比例格式不正确。');
 if(d.grapes.reduce((a,g)=>a+(g.percent??0),0)>100.01)fail('品种比例合计不能超过100%。');
 if(new Set(d.grapes.map(g=>g.id)).size!==d.grapes.length)fail('同一品种不能重复。');
 d.parcelIds=Array.isArray(data.parcelIds)?[...new Set(data.parcelIds.map(v=>cleanText(v)))].slice(0,30):[];
 d.lat=data.lat==null||data.lat===''?null:Number(data.lat);d.lng=data.lng==null||data.lng===''?null:Number(data.lng);
 if((d.lat==null)!==(d.lng==null)||d.lat!=null&&(!Number.isFinite(d.lat)||!Number.isFinite(d.lng)||Math.abs(d.lat)>90||Math.abs(d.lng)>180))fail('请同时填写有效的纬度和经度。');
 d.year=data.year==null||data.year===''?null:Number(data.year);if(d.year!==null&&(!Number.isInteger(d.year)||d.year<1800||d.year>new Date().getUTCFullYear()+1))fail('年份不在有效范围内。');
 d.geometry=null;if(data.geometry){const g=data.geometry.type==='Feature'?data.geometry.geometry:data.geometry;let count=0;const ring=r=>Array.isArray(r)&&r.length>=4&&r.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&Math.abs(p[0])<=180&&Math.abs(p[1])<=90&&++count<=5000)&&JSON.stringify(r[0])===JSON.stringify(r.at(-1));if(!g||g.type!=='Polygon'||!Array.isArray(g.coordinates)||!g.coordinates.length||!g.coordinates.every(ring))fail('地块轮廓请使用闭合的 GeoJSON Polygon，最多5000个点。');d.geometry={type:'Polygon',coordinates:g.coordinates}}
 if(complete){if(!d.name)fail('请填写名称。');if(!d.sourceURL&&!d.attachments.length)fail('请附原始资料链接或证明文件。');if(!d.sourceTitle)fail('请注明资料来源名称。');if(['winery','region','parcel'].includes(kind)&&!d.country)fail('请填写国家。');if(kind==='wine'&&!d.wineryId)fail('请选择对应酒庄。');if(kind==='vintage'){if(!d.wineId)fail('请选择对应酒款。');if(!['vintage','nv','unknown'].includes(d.yearType))fail('请选择年份类型。');if(d.yearType==='vintage'&&!d.year)fail('请填写年份。');if(d.yearType!=='vintage')d.year=null}if(kind==='parcel'&&(!d.regionId||(!d.geometry&&d.lat==null)))fail('地块需要产区和位置或轮廓。');if(d.lat!==null&&!d.locationPrecision)fail('请注明位置精度。')}
 if(kind==='event'&&complete){if(!['news','event','harvest','weather','disaster'].includes(d.eventType)||!d.startDate||d.lat===null||!d.country)fail('动态需要类型、发生日期、国家和已注明精度的位置。');for(const k of ['startDate','endDate','publishedDate'])if(d[k]&&(!/^\d{4}-\d{2}-\d{2}$/.test(d[k])||!Number.isFinite(Date.parse(d[k]))||new Date(d[k]).toISOString().slice(0,10)!==d[k]))fail('日期格式不正确。');if(d.endDate&&d.endDate<d.startDate)fail('结束日期不能早于开始日期。')}
 return d;
}
export function checkReferences(d,kind,catalog){const refs=[['regionId','region'],['wineryId','winery'],['wineId','wine']];for(const [key,type]of refs)if(d[key]&&!catalog.some(e=>e.id===d[key]&&e.kind===type))fail('关联的'+kinds[type]+'不存在，请先提交并收录该条目。');for(const g of d.grapes)if(!catalog.some(e=>e.id===g.id&&e.kind==='grape'))fail('关联葡萄品种不存在。');for(const p of d.parcelIds)if(!catalog.some(e=>e.id===p&&e.kind==='parcel'))fail('关联地块不存在。')}
