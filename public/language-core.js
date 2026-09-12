(function(root){
 const languages={zh:'中文',en:'English',fr:'Français',it:'Italiano',es:'Español',pt:'Português',de:'Deutsch',ro:'Română',hu:'Magyar',el:'Ελληνικά',ka:'ქართული',ru:'Русский',ja:'日本語',af:'Afrikaans'};
 const countryRules={中国:['CN','zh'],法国:['FR','fr'],意大利:['IT','it'],西班牙:['ES','es'],葡萄牙:['PT','pt'],德国:['DE','de'],奥地利:['AT','de'],美国:['US','en'],澳大利亚:['AU','en'],新西兰:['NZ','en'],南非:['ZA','en','af'],智利:['CL','es'],阿根廷:['AR','es'],巴西:['BR','pt'],乌拉圭:['UY','es'],罗马尼亚:['RO','ro'],匈牙利:['HU','hu'],希腊:['GR','el'],格鲁吉亚:['GE','ka'],俄罗斯:['RU','ru'],日本:['JP','ja'],加拿大:['CA','en','fr'],瑞士:['CH','de','fr','it'],英国:['GB','en']};
 const alias={China:'中国',France:'法国',Italy:'意大利',Spain:'西班牙',Portugal:'葡萄牙',Germany:'德国',Austria:'奥地利','United States':'美国',USA:'美国',Australia:'澳大利亚','New Zealand':'新西兰','South Africa':'南非',Chile:'智利',Argentina:'阿根廷',Brazil:'巴西',Uruguay:'乌拉圭',Romania:'罗马尼亚',Hungary:'匈牙利',Greece:'希腊',Georgia:'格鲁吉亚',Russia:'俄罗斯',Japan:'日本',Canada:'加拿大',Switzerland:'瑞士','United Kingdom':'英国'};
 const code=value=>{let s=String(value||'').toLowerCase().split('-')[0];return Object.hasOwn(languages,s)?s:''};
 const rule=country=>(Object.hasOwn(countryRules,country)?countryRules[country]:null)||(Object.hasOwn(alias,country)?countryRules[alias[country]]:null)||Object.values(countryRules).find(r=>r[0]===country)||[];
 function priorities(data={}){return [...new Set([code(data.originalLanguage),...rule(data.country).slice(1),'en'].filter(Boolean))]}
 function confirmed(entry){return !!(entry&&entry.status==='verified'&&entry.sourceURL&&entry.sourceTitle&&entry.checkedDate)}
 function available(data={}){return Object.entries(data.localizations||{}).filter(([lang,e])=>Object.hasOwn(languages,lang)&&confirmed(e)).map(([lang])=>lang)}
 function field(record,which,requested='zh'){
  const d=record?.data||record||{},current=code(requested)||'zh';
  const order=[...new Set([current,...priorities(d)])];
  for(const lang of order){const entry=d.localizations?.[lang];if(confirmed(entry)&&entry[which])return {text:entry[which],language:lang,fallback:lang!==current,verified:true,sourceURL:entry.sourceURL,sourceTitle:entry.sourceTitle,checkedDate:entry.checkedDate}}
  // Existing descriptions remain in their actual language; never silently invent translations.
  const text=which==='name'?(current==='zh'?d.name||record?.name:d.en||d.name||record?.name):d.notes||d.desc||'';
  const language=which==='name'&&current!=='zh'&&d.en?'':/[\u3400-\u9fff]/.test(text)?'zh':code(d.originalLanguage);
  return {text:text||'',language,fallback:!!text&&language!==current,verified:false,sourceURL:d.sourceURL||d.source||'',sourceTitle:d.sourceTitle||''};
 }
 function searchText(record){const d=record.data||record;return [d.name,d.en,...d.aliases||[],...Object.values(d.localizations||{}).filter(confirmed).flatMap(e=>[e.name,e.description])].filter(Boolean).join(' ')}
 function coverage(data={}){const langs=priorities(data);return langs.map(language=>{const e=data.localizations?.[language];return {language,complete:confirmed(e)&&!!e.name&&!!e.description,name:confirmed(e)&&!!e.name,description:confirmed(e)&&!!e.description}})}
 root.WineLanguage={languages,code,rule,priorities,confirmed,available,field,searchText,coverage};
})(globalThis);
