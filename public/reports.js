const byId=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let issues=[];
const reportI18n=WineI18n,reportT=text=>esc(reportI18n.t(text));
const coverageLabel={directory_checked:'本期官方名录核对完成',partial:'持续收录中',open_ended:'公开资料持续补充'};
const entityLink=id=>'/catalog?entity='+encodeURIComponent(id)+'&lang='+encodeURIComponent(reportI18n.locale);
const photoFigure=m=>`<figure class="report-photo"><a href="${esc(m.originalURL)}" target="_blank" rel="noopener"><img src="${esc(m.previewURL)}" data-original="${esc(m.originalURL)}" width="${m.width}" height="${m.height}" alt="${esc(m.caption)}" loading="lazy" referrerpolicy="no-referrer" data-no-i18n></a><figcaption><span data-no-i18n lang="zh"><strong>[${esc(m.id)}] ${esc(m.title)}</strong><br>${esc(m.caption)}</span><br><span data-no-i18n>${esc(m.author)} / <a href="${esc(m.sourceURL)}" target="_blank" rel="noopener">${esc(m.sourceName)}</a> · <a href="${esc(m.licenseURL)}" target="_blank" rel="noopener">${esc(m.license)}</a></span><br><a href="${esc(m.originalURL)}" target="_blank" rel="noopener">${reportT('查看原尺寸')} ${m.width} × ${m.height} ↗</a></figcaption></figure>`;
const pictures=(r,anchor)=>(r.media||[]).filter(m=>m.anchor===anchor).map(photoFigure).join('');
const mediaCount=r=>(r.media||[]).length;
const reportTf=(key,vars)=>esc(String(reportI18n.t(key)).replace(/\{(\w+)\}/g,(m,k)=>Object.hasOwn(vars,k)?esc(String(vars[k])):m));
// 本期 media 为空时，在 hero 位渲染一块明确的「本期无配图」说明，并给出跳转到最近一期有配图简报的入口。
// mediaGap 是编辑侧的中文说明（与正文同源），保持中文并标 lang，不回落到英文。
const mediaGapNotice=r=>{
 if(mediaCount(r))return '';
 const donor=issues.find(x=>mediaCount(x));
 const jump=donor?`<button class="button secondary" id="jumpToPhotos" data-date="${esc(donor.date)}">${reportT('查看最近一期有配图的简报')} · ${esc(donor.date)}</button>`:'';
 return `<div class="report-media-gap"><span class="report-media-gap-badge">${reportT('本期无配图')}</span>${r.mediaGap?`<p data-no-i18n lang="zh">${esc(r.mediaGap)}</p>`:''}${jump}</div>`;
};
function showReport(date){
 const r=issues.find(r=>r.date===date)||issues[0];if(!r)return;
 document.querySelectorAll('[data-date]').forEach(b=>b.classList.toggle('active',b.dataset.date===r.date));
 const stat=(n,label)=>`<div class="report-stat"><strong>${n}</strong><span>${reportT(label)}</span></div>`;
 const bodyNote=reportI18n.contentNote({text:r.summary||r.title,language:'zh',fallback:reportI18n.locale!=='zh'})||`<span class="content-language-note" data-no-i18n>${reportT('正文语言')}：<span lang="zh">中文</span></span>`;
 // Report text and downloadable copy retain the language of the editorial source.
 byId('reportBody').dataset.noI18n='';
 byId('reportBody').innerHTML=`<div class="eyebrow">${esc(r.date)} · ISSUE ${esc(r.issue)}</div>${bodyNote}<h1 data-no-i18n lang="zh">${esc(r.title)}</h1><p class="report-lead" data-no-i18n lang="zh">${esc(r.summary)}</p>${pictures(r,'hero')||mediaGapNotice(r)}<div class="report-stats">${stat(r.added.wineryIds.length,'本期新增酒庄')}${stat(r.added.wineIds.length,'本期新增酒款')}${stat(r.news.length,'收录新闻 / 采收')}${stat(r.activities.length,'近期活动')}</div><div class="report-coverage"><strong>${reportT(coverageLabel[r.region.status])}</strong><br><span data-no-i18n lang="zh">${esc(r.region.scope)}</span><br>${reportT('酒庄核对')} ${r.region.producersChecked}/${r.region.producerBaseline??reportT('未知')} · ${reportT('官网公开酒款')} ${r.region.winesRecorded}/${r.region.winesListed??reportT('未知')}<br><span data-no-i18n lang="zh">${esc(r.region.completionNote)}</span></div>
 <section class="report-section"><h2>${reportT('本期产区与酒庄')}</h2><p data-no-i18n lang="zh">${esc(r.region.introduction)}</p>${pictures(r,'grape')}${r.wineries.map(w=>`<h3><a data-no-i18n href="${entityLink(w.id)}">${esc(w.name)} ↗</a></h3><p data-no-i18n lang="zh">${esc(w.summary)}</p>${pictures(r,w.id)}<ul>${w.wines.map(wine=>`<li><a data-no-i18n href="${entityLink(wine.id)}">${esc(wine.name)} ↗</a> · <span data-no-i18n>${esc(wine.appellation)}</span><br><span data-no-i18n lang="zh">${esc(wine.summary)}</span>${pictures(r,wine.id)}</li>`).join('')}</ul>`).join('')}<h3>${reportT('仍待补充')}</h3><ul>${r.region.gaps.map(g=>`<li data-no-i18n lang="zh">${esc(g)}</li>`).join('')}</ul><p class="note" data-no-i18n lang="zh">${esc(r.countingNote)}</p></section>
 <section class="report-section"><h2>${reportT('葡萄酒新闻与采收')}</h2>${r.news.length?r.news.map(n=>`<div class="report-update"><h3 data-no-i18n lang="zh">${esc(n.title)}</h3><p data-no-i18n lang="zh">${esc(n.summary)}</p>${pictures(r,n.id)}<p class="note">${reportT('发生/数据日期')}：${esc(n.occurrenceDate)} · ${reportT('报道')}：${esc(n.publishedDate||reportI18n.t('未注明'))} · <span data-no-i18n lang="zh">${esc(n.freshness)}</span></p><p class="report-source"><a data-no-i18n href="${esc(n.sourceURL)}" target="_blank" rel="noopener">${esc(n.sourceName)} ↗</a></p></div>`).join(''):`<p>${reportT('本期未发现可核实的新增消息。')}</p>`}</section>
 <section class="report-section"><h2>${reportT('近期活动')}</h2>${r.activities.length?r.activities.map(a=>`<h3 data-no-i18n lang="zh">${esc(a.title)}</h3><p data-no-i18n>${esc(a.dates)} · ${esc(a.location)}</p><p data-no-i18n lang="zh">${esc(a.summary)}</p>${pictures(r,a.id)}<a class="report-source" href="${esc(a.sourceURL)}" target="_blank" rel="noopener">${reportT('主办方安排')} ↗</a>`).join(''):`<p>${reportT('本期无新增的已核实活动。')}</p>`}</section>
 <section class="report-section"><h2>${reportT('来源与核对范围')}</h2><ol class="report-source-list">${r.sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener" data-no-i18n>[${esc(s.id)}] ${esc(s.label)} ↗</a><br><span class="note"><span data-no-i18n lang="zh">${esc(s.note||'')}</span> · ${reportT('核对')} ${esc(s.checkedDate)}</span></li>`).join('')}</ol><p class="note" data-no-i18n lang="zh">${esc(r.nextStep)}</p></section>`;
 document.querySelectorAll('.report-photo img').forEach(img=>img.onerror=()=>{if(img.dataset.retried)return;img.dataset.retried='true';img.src=img.dataset.original});
 const jumpButton=byId('jumpToPhotos');if(jumpButton)jumpButton.onclick=()=>showReport(jumpButton.dataset.date);
}
fetch('/api/reports').then(r=>{if(!r.ok)throw Error();return r.json()}).then(data=>{
 issues=data.reports;if(!issues.length){byId('issueList').textContent=reportI18n.t('首期正在采编');byId('reportBody').textContent=reportI18n.t('首期报告完成后将在这里归档。');return}
 byId('issueList').innerHTML=issues.map(r=>{const n=mediaCount(r);return `<button class="issue-button" data-date="${esc(r.date)}"><small>${esc(r.date)} · ${reportT(coverageLabel[r.region.status])}</small><strong data-no-i18n>${esc(r.region.name)}</strong><small>${reportT('酒庄')} ${r.added.wineryIds.length} / ${reportT('酒款')} ${r.added.wineIds.length}<span class="issue-media-badge${n?' has':' none'}">${n?reportTf('配图 {n} 张',{n:n}):reportT('本期无配图')}</span></small></button>`}).join('');
 document.querySelectorAll('[data-date]').forEach(b=>b.onclick=()=>showReport(b.dataset.date));showReport(new URLSearchParams(location.search).get('date'));
}).catch(()=>{byId('reportBody').innerHTML=`<h1>${reportT('日报暂时无法载入')}</h1><p>${reportT('请稍后刷新重试。')}</p>`;byId('issueList').textContent=reportI18n.t('暂时不可用')});
