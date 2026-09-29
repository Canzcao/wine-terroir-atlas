import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync('public/catalog-loader.js','utf8');
function setup({stored=null,age=0,failing=false}={}){
 let calls=0,saved=stored&&new Response(JSON.stringify(stored),{headers:{'x-atlas-cached-at':String(Date.now()-age)}});
 const ctx={window:{},Date,Response,console,caches:{open:async()=>({match:async()=>saved?.clone(),put:async(k,r)=>{saved=r}}),delete:async()=>{saved=null}},fetch:async()=>{calls++;return new Response(JSON.stringify({entities:[{id:'fresh'}]}),{status:failing?500:200})}};
 vm.runInNewContext(source,ctx);return {api:ctx.window.AtlasCatalog,calls:()=>calls};
}
test('reuses fresh public catalogue across page loads',async()=>{const x=setup({stored:{entities:[{id:'cached'}]}});assert.equal((await x.api.load()).entities[0].id,'cached');assert.equal(x.calls(),0)});
test('expired cache fetches fresh data and shares concurrent requests',async()=>{const x=setup({stored:{entities:[]},age:61000});await Promise.all([x.api.load(),x.api.load()]);assert.equal(x.calls(),1)});
test('successful writes invalidate public cache',async()=>{const x=setup({stored:{entities:[]}});await x.api.load();await x.api.invalidate();assert.equal((await x.api.load()).entities[0].id,'fresh');assert.equal(x.calls(),1)});
test('failed requests can be retried without using stale data',async()=>{const x=setup({failing:true});await assert.rejects(x.api.load());await assert.rejects(x.api.load());assert.equal(x.calls(),2)});
