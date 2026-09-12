import {test} from 'node:test';
import assert from 'node:assert/strict';
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
