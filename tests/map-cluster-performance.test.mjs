import {test} from 'node:test';
import assert from 'node:assert/strict';
import '../public/map-model.js';
test('spatial clustering preserves original greedy grouping across cell edges and zooms',()=>{
 let seed=17;const random=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
 const entries=Array.from({length:2000},(_,id)=>({id,point:[random()*160-80,random()*340-170]}));
 entries.push({...entries[0],id:'same'});
 for(const scale of [1,10,100]){
  const project=p=>({x:p[0]*scale,y:p[1]*scale}),baseline=[];
  for(const e of entries){const p=project(e.point);let g=baseline.find(g=>Math.hypot(g.p.x-p.x,g.p.y-p.y)<36);if(!g){g={p,ids:[]};baseline.push(g)}g.ids.push(e.id)}
  assert.deepEqual(WineMapModel.cluster(entries,project).map(g=>g.items.map(e=>e.id)),baseline.map(g=>g.ids));
 }
});
