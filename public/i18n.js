(function(){
 const core=globalThis.WineLanguage,labels=globalThis.WINE_UI_LABELS||{};
 let saved='';try{saved=localStorage.getItem('terroir-language')||''}catch{}
 const locale=core.code(new URLSearchParams(location.search).get('lang'))||core.code(saved)||'zh';
 try{localStorage.setItem('terroir-language',locale)}catch{}
 document.documentElement.lang=locale==='zh'?'zh-CN':locale;
 const t=text=>{text=String(text);if(locale==='zh')return text;const direct=labels[text]?.[locale]||labels[text]?.en;if(direct)return direct;const match=text.match(/^([←↗◎▱\s]*)(.*?)([+*↗\s]*)$/);const key=match?.[2],translated=labels[key]?.[locale]||labels[key]?.en;return translated?match[1]+translated+match[3]:text};
 const country=value=>{const r=core.rule(value);if(!r.length)return value;try{return new Intl.DisplayNames([locale==='zh'?'zh-Hans':locale],{type:'region'}).of(r[0])}catch{return value}};
 const name=e=>core.field(e,'name',locale).text;
 const description=e=>core.field(e,'description',locale);
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function contentNote(field){return field.text&&field.fallback?'<span class="content-language-note" data-no-i18n>'+esc(t('当前显示'))+' '+esc(core.languages[field.language]||t('原文'))+' · '+esc(t('该语种暂无已核对译文'))+'</span>':''}
 function status(data){const have=core.available(data),missing=core.coverage(data).filter(x=>!x.complete).map(x=>core.languages[x.language]);return '<div class="content-language-status" data-no-i18n>'+esc(t('已核对语种'))+'：'+esc(have.map(l=>core.languages[l]).join(' / ')||t('待完善'))+(missing.length?'<br>'+esc(t('优先完善'))+'：'+esc(missing.join(' / ')):'')+'</div>'}
 globalThis.WineI18n={locale,t,country,name,description,contentNote,status,esc};
 const textState=new WeakMap(),attrState=new WeakMap();
 function translateText(node){if(!node.parentElement||node.parentElement.closest('[data-no-i18n],script,style,textarea,[contenteditable=true]'))return;
  const value=node.nodeValue,prior=textState.get(node),original=prior&&prior.translated===value?prior.original:value;
  const bare=original.trim(),translated=core.rule(bare).length?country(bare):t(bare);
  const replacement=translated===bare?original:original.replace(bare,translated);
  if(replacement===value)return;
  if(node.parentElement.tagName==='OPTION'&&!node.parentElement.hasAttribute('value'))node.parentElement.setAttribute('value',original);
  textState.set(node,{original,translated:replacement});node.nodeValue=replacement;
 }
 function localLink(a){if(!a.matches('a[href]')||a.hasAttribute('download'))return;const url=new URL(a.href,location.href);if(url.origin===location.origin&&!url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/signin-')&&!url.searchParams.has('lang')){url.searchParams.set('lang',locale);a.href=url.href}}
 function translate(root){if(root.nodeType===3)return translateText(root);if(root.nodeType!==1)return;
  for(const a of [root,...root.querySelectorAll('a[href]')])localLink(a);
  if(root.closest('[data-no-i18n],script,style,textarea,[contenteditable=true]'))return;
  for(const el of [root,...root.querySelectorAll('[placeholder],[title],[aria-label]')]){
   if(el.closest('[data-no-i18n]'))continue;
   let state=attrState.get(el)||{};
   for(const key of ['placeholder','title','aria-label']){if(!el.hasAttribute(key))continue;const value=el.getAttribute(key),old=state[key],original=old&&old.translated===value?old.original:value,replacement=t(original);if(replacement!==value){state[key]={original,translated:replacement};el.setAttribute(key,replacement)}}attrState.set(el,state);
  }
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode())translateText(node);
 }
 function start(){
  const label=document.createElement('label');label.className='language-switch';label.dataset.noI18n='';label.innerHTML='<span aria-hidden="true">◎</span><select id="siteLanguage" aria-label="Language / 语言">'+Object.entries(core.languages).map(([id,title])=>'<option value="'+id+'" '+(id===locale?'selected':'')+'>'+title+'</option>').join('')+'</select>';
  const header=document.querySelector('.masthead');header?.append(label);if(header){const measure=()=>document.documentElement.style.setProperty('--masthead-height',header.getBoundingClientRect().height+'px');new ResizeObserver(measure).observe(header);measure()}
  label.querySelector('select').onchange=e=>{const value=e.target.value;try{localStorage.setItem('terroir-language',value)}catch{}const url=new URL(location.href);url.searchParams.set('lang',value);location.assign(url.href)};
  translate(document.body);
  const observer=new MutationObserver(mutations=>{const roots=new Set();for(const mutation of mutations){if(mutation.type==='characterData')roots.add(mutation.target);else for(const node of mutation.addedNodes)roots.add(node)}for(const node of roots)translate(node)});
  observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  document.addEventListener('click',event=>{const a=event.target.closest('a[href]');if(!a||a.hasAttribute('download'))return;const url=new URL(a.href,location.href);if(url.origin===location.origin&&!url.pathname.startsWith('/api/')&&!url.pathname.startsWith('/signin-')){if(!url.searchParams.has('lang'))url.searchParams.set('lang',locale);a.href=url.href}});
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
