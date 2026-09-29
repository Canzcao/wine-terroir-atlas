import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import '../public/language-core.js';
import {normalize,mergeLocalizedData,supportedLanguages} from '../worker/model.js';
const L=globalThis.WineLanguage;
const checked=(name,description='Verified description')=>({name,description,sourceURL:'https://example.com/official',sourceTitle:'Official winery',checkedDate:'2026-09-12',status:'verified'});

test('content uses the requested verified language, then the country language and English',()=>{
 const chinese={country:'中国',originalLanguage:'zh',localizations:{zh:checked('贺兰山','中文简介'),en:checked('Helan Mountain','English description')}};
 assert.deepEqual(L.priorities(chinese),['zh','en']);
 assert.equal(L.field(chinese,'description','en').text,'English description');
 const unsupported=L.field(chinese,'description','it');
 assert.equal(unsupported.text,'中文简介');assert.equal(unsupported.language,'zh');assert.equal(unsupported.fallback,true);
 const french={country:'法国',originalLanguage:'fr',localizations:{fr:checked('Domaine','Texte français'),en:checked('Estate','English text')}};
 assert.equal(L.field(french,'description','ja').language,'fr');
 delete french.localizations.fr;
 assert.equal(L.field(french,'description','ja').text,'English text');
});

test('draft translations never appear as confirmed content or search results',()=>{
 const d={country:'法国',originalLanguage:'fr',localizations:{fr:{...checked('Draft alias','Unconfirmed text'),status:'draft'},en:checked('Estate','Checked English')}};
 assert.equal(L.field(d,'name','fr').text,'Estate');
 assert.deepEqual(L.available(d),['en']);
 assert.equal(L.searchText(d).includes('Draft alias'),false);
 assert.equal(L.coverage(d).find(x=>x.language==='fr').complete,false);
});

test('legacy en names stay unverified and never establish an English translation',()=>{
 const d={name:'格里叶堡',en:'Château-Grillet',originalLanguage:'fr',country:'法国',notes:'中文旧简介'};
 const name=L.field(d,'name','en');
 assert.equal(name.text,'Château-Grillet');assert.notEqual(name.language,'en');assert.equal(name.verified,false);
 assert.equal(L.field(d,'description','de').text,'中文旧简介');
 assert.equal(L.field(d,'description','de').language,'zh');
 assert.deepEqual(L.available(d),[]);
 assert.deepEqual(normalize(d,'winery').localizations,{});
});

test('server and reader support the same fourteen languages without auto-verification',()=>{
 assert.equal(supportedLanguages.length,14);
 assert.deepEqual([...supportedLanguages].sort(),Object.keys(L.languages).sort());
 const normalized=normalize({originalLanguage:'zh',localizations:Object.fromEntries(supportedLanguages.map(lang=>[lang,{...checked(lang),status:undefined}]))},'winery');
 assert.equal(normalized.originalLanguage,'zh');
 for(const entry of Object.values(normalized.localizations))assert.equal(entry.status,'draft');
 assert.deepEqual(L.available(normalized),[]);
});

test('verified content requires a usable HTTP source, title and real calendar date',()=>{
 const record=entry=>({originalLanguage:'fr',localizations:{fr:entry}});
 const good=checked('Domaine');
 assert.equal(normalize(record({...good,checkedDate:'2024-02-29'}),'winery').localizations.fr.status,'verified');
 for(const bad of [{sourceURL:''},{sourceURL:'javascript:alert(1)'},{sourceURL:'ftp://example.com/wine'},{sourceURL:'https://user:password@example.com/'},{sourceTitle:'  '},{checkedDate:''},{checkedDate:'2025-02-29'},{checkedDate:'2026-04-31'},{checkedDate:'2026-09-12T00:00:00Z'},{status:'approved'}])assert.throws(()=>normalize(record({...good,...bad}),'winery'));
 for(const localizations of [[], 'fr', {xx:good},{fr:null}])assert.throws(()=>normalize({localizations},'winery'));
 assert.throws(()=>normalize({originalLanguage:'xx'},'winery'));
});

test('partial edits retain other languages and changed text needs an explicit verification choice',()=>{
 const old={originalLanguage:'fr',localizations:{fr:checked('Domaine','Français'),en:checked('Estate','English')}};
 const plain=normalize(mergeLocalizedData(old,{notes:'Other field changed'}),'winery');
 assert.equal(plain.originalLanguage,'fr');assert.deepEqual(plain.localizations.en,old.localizations.en);assert.deepEqual(plain.localizations.fr,old.localizations.fr);
 const edited=normalize(mergeLocalizedData(old,{localizations:{en:{description:'Revised English'}}}),'winery');
 assert.equal(edited.localizations.en.name,'Estate');assert.equal(edited.localizations.en.status,'draft');assert.deepEqual(edited.localizations.fr,old.localizations.fr);
 const explicit=normalize(mergeLocalizedData(old,{localizations:{en:{description:'Revised English',status:'verified'}}}),'winery');
 assert.equal(explicit.localizations.en.status,'verified');
});

test('unrecognized countries stay safe and use English as the remaining priority',()=>{
 for(const country of ['Unknown country','__proto__','constructor'])assert.deepEqual(L.priorities({country}),['en']);
 assert.equal(L.code('constructor'),'');
});

test('an explicit draft can retract an incorrect translation without deleting other languages',()=>{
 const old={originalLanguage:'fr',localizations:{fr:checked('Incorrect','Incorrect text'),en:checked('Estate','English')}};
 const revised=normalize(mergeLocalizedData(old,{originalLanguage:'',localizations:{fr:{name:'',description:'',sourceURL:'',sourceTitle:'',checkedDate:'',status:'draft'}}}),'winery');
 assert.equal(revised.originalLanguage,'');assert.equal(revised.localizations.fr.status,'draft');assert.equal(revised.localizations.fr.name,'');assert.deepEqual(revised.localizations.en,old.localizations.en);assert.deepEqual(L.available(revised),['en']);
 assert.throws(()=>normalize({localizations:{fr:{...checked(''),description:''}}},'winery'));
});

test('the requested language beats a verified translation in another language',()=>{
 // 目录自带的中文名不能被「已核实的外文本地语条目」盖掉 ——
 // 否则中文页会把勃艮第显示成 Bourgogne、纳帕谷显示成 Napa Valley（实测 91/109 个产区中招）
 const frOnly={name:'勃艮第',en:'Bourgogne',originalLanguage:'fr',country:'法国',notes:'中文简介',localizations:{fr:checked('Bourgogne')}};
 const zh=L.field(frOnly,'name','zh');
 assert.equal(zh.text,'勃艮第');assert.equal(zh.language,'zh');assert.equal(zh.fallback,false);assert.equal(zh.verified,false);
 assert.equal(L.field(frOnly,'description','zh').text,'中文简介');
 // 但切到别的语言时，那条已核实的外文条目必须照常生效
 assert.equal(L.field(frOnly,'name','en').text,'Bourgogne');
 assert.equal(L.field(frOnly,'name','fr').text,'Bourgogne');
 // 已核实的中文条目依然优先级最高
 const withZh={...frOnly,localizations:{fr:checked('Bourgogne'),zh:checked('勃艮第产区','中文简介（已核实）')}};
 const best=L.field(withZh,'name','zh');
 assert.equal(best.text,'勃艮第产区');assert.equal(best.verified,true);assert.equal(best.sourceURL,'https://example.com/official');
 // 目录本来就没有中文名时，外文条目该顶上就得顶上
 const noZhName={name:'Domaine X',en:'Domaine X',originalLanguage:'fr',country:'法国',localizations:{fr:checked('Domaine X')}};
 assert.equal(L.field(noZhName,'name','zh').text,'Domaine X');
});

test('no catalogue record hides an available Chinese name behind a foreign one',()=>{
 const catalogue=JSON.parse(fs.readFileSync('data/catalog-seed.json'));
 const cjk=/[\u3400-\u9fff]/;
 const hidden=[];
 for(const e of catalogue){
  const f=L.field(e,'name','zh'),own=(e.data||e).name||'';
  // d.name 里明明有中文，中文页却给了别的语言的串 → 就是被盖掉了
  if(cjk.test(own)&&f.language!=='zh')hidden.push(e.kind+'/'+e.id+'：'+own+' → '+f.text);
 }
 assert.deepEqual(hidden.slice(0,10),[],'中文页有中文名可用却显示了外文名的记录：'+hidden.length+' 条');
});
