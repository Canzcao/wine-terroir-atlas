import {test} from 'node:test';import assert from 'node:assert/strict';import {local} from '../scripts/local.mjs';
test('shared catalogue, permissions, review, optimistic concurrency, imports and files',async t=>{const {mf,db}=await local();t.after(()=>mf.dispose());const identities={owner:['owner-id','owner@local.test'],alice:['alice-id','alice@example.com'],bob:['bob-id','bob@example.com'],reviewer:['reviewer-id','reviewer@example.com']};
async function req(path,data,who='owner',method){const hs={'content-type':'application/json',origin:'https://wine.test'};if(who){hs['oai-authenticated-user-id']=identities[who][0];hs['oai-authenticated-user-email']=identities[who][1]}let r=await mf.dispatchFetch('https://wine.test/api/'+path,{method:method||(data?'POST':'GET'),headers:hs,body:data?JSON.stringify(data):undefined});return {status:r.status,data:await r.json()}}
const reportReply=await req('reports',null,null);assert.equal(reportReply.status,200);assert.equal(reportReply.data.reports.find(r=>r.date==='2026-09-12').date,'2026-09-12');assert.equal(reportReply.data.reports.find(r=>r.date==='2026-09-12').added.wineryIds.length,1);assert.equal((await mf.dispatchFetch('https://wine.test/reports')).status,200);
const base={name:'Test vineyard',country:'法国',sourceTitle:'Evidence',sourceURL:'https://example.com/evidence',notes:'Initial'};
assert.equal((await req('me',null,null)).status,401);assert.equal((await req('me',null,'alice')).status,403);assert.equal((await req('me')).data.member.role,'admin');for(const name of ['alice','bob','reviewer']){assert.equal((await req('members',{email:identities[name][1],role:name==='reviewer'?'reviewer':'member'})).status,200);assert.equal((await req('me',null,name)).status,200)}
const create=async(who,opts={})=>req('submissions',{kind:'winery',data:base,submit:true,requestKey:crypto.randomUUID(),...opts},who);
let a=await create('alice');assert.equal(a.status,201);const sid=a.data.id,eid=a.data.entity_id;
assert.equal((await req('submissions/'+sid,null,'bob')).status,403);assert.equal((await req('review',null,'alice')).status,403);assert.equal((await req('submissions/'+sid+'/decision',{revision:1,action:'approve'},'alice')).status,403);
assert.equal((await req('submissions/'+sid,{revision:1,baseVersion:0,data:{...base,notes:'Changed'},submit:true},'alice','PATCH')).status,200);
assert.equal((await req('submissions/'+sid+'/decision',{revision:1,action:'approve'},'reviewer')).status,409);
assert.equal((await req('submissions/'+sid+'/decision',{revision:2,action:'approve'},'reviewer')).status,200);
let entity=(await req('catalog')).data.entities.find(e=>e.id===eid);assert.equal(entity.version,1);assert.equal(entity.data.notes,'Changed');
let a2=await create('alice',{entityId:eid,baseVersion:1,data:{...base,notes:'Alice edit'}}),b2=await create('bob',{entityId:eid,baseVersion:1,data:{...base,notes:'Bob edit'}});
assert.equal((await req('submissions/'+a2.data.id+'/decision',{revision:1,action:'approve'},'reviewer')).status,200);assert.equal((await req('submissions/'+b2.data.id+'/decision',{revision:1,action:'approve'},'reviewer')).status,409);
entity=(await req('catalog')).data.entities.find(e=>e.id===eid);assert.equal(entity.version,2);assert.equal(entity.data.notes,'Alice edit');assert.equal((await req('history/'+eid)).data.history.length,2);
const self=await create('reviewer');assert.equal((await req('submissions/'+self.data.id+'/decision',{revision:1,action:'approve',ownerPublish:true,reason:'Test'},'reviewer')).status,403);
const own=await create('owner');assert.equal((await req('submissions/'+own.data.id+'/decision',{revision:1,action:'approve'},'owner')).status,403);assert.equal((await req('submissions/'+own.data.id+'/decision',{revision:1,action:'approve',ownerPublish:true,reason:'Official source checked'},'owner')).status,200);
let importRows=[{kind:'winery',entityId:eid,data:{name:'Renamed',notes:''}}];let preview=(await req('imports/preview',{rows:importRows},'alice')).data;assert.equal(preview.rows[0].data.notes,'Alice edit');let key=crypto.randomUUID();assert.equal((await req('imports/submit',{rows:importRows,importKey:key},'alice')).data.submitted,1);assert.equal((await req('imports/submit',{rows:importRows,importKey:key},'alice')).data.submitted,0);
const bad=[{kind:'wine',data:{...base,wineryId:'missing'}}];assert.equal((await req('imports/preview',{rows:bad},'alice')).data.rows[0].status,'error');assert.equal((await req('imports/submit',{rows:bad,importKey:'bad'},'alice')).status,400);
const mk=(await req('members')).data.members.find(m=>m.email==='alice@example.com');await req('members/'+mk.id,{role:'member',status:'suspended'},'owner','PATCH');assert.equal((await create('alice')).status,403);await req('members/'+mk.id,{role:'member',status:'active'},'owner','PATCH');
let r=await mf.dispatchFetch('https://wine.test/api/attachments',{method:'POST',headers:{origin:'https://wine.test','oai-authenticated-user-id':'alice-id','oai-authenticated-user-email':'alice@example.com','x-file-name':'proof.pdf'},body:'%PDF-1.7\nTest proof file'});assert.equal(r.status,201);const file=await r.json();assert.equal((await req('attachments/'+file.id,null,'bob')).status,404);assert.equal((await mf.dispatchFetch('https://wine.test/api/attachments/'+file.id,{headers:{'oai-authenticated-user-id':'alice-id','oai-authenticated-user-email':'alice@example.com'}})).status,200);
assert.equal((await mf.dispatchFetch('https://wine.test/api/submissions',{method:'POST',headers:{origin:'https://evil.test','content-type':'application/json','oai-authenticated-user-id':'owner-id','oai-authenticated-user-email':'owner@local.test'},body:'{}'})).status,403);
assert.equal((await req('events')).data.events.length>=6,true);assert.equal((await db.prepare("SELECT count(*) n FROM submissions WHERE status='approving'").first()).n,0);
});

test('ordinary edits and partial language imports preserve published languages',async t=>{
 const {mf}=await local();t.after(()=>mf.dispose());
 const headers={'content-type':'application/json',origin:'https://wine.test','oai-authenticated-user-id':'owner-id','oai-authenticated-user-email':'owner@local.test'};
 async function request(path,data,method=data?'POST':'GET'){const response=await mf.dispatchFetch('https://wine.test/api/'+path,{method,headers,body:data?JSON.stringify(data):undefined});return {status:response.status,data:await response.json()}}
 const locale=(name,description)=>({name,description,sourceURL:'https://example.com/official',sourceTitle:'Winery official website',checkedDate:'2026-09-12',status:'verified'});
 const base={name:'语言测试酒庄',country:'中国',sourceTitle:'Official website',sourceURL:'https://example.com/official',originalLanguage:'zh',localizations:{zh:locale('语言测试酒庄','已核对中文'),en:locale('Language Test Winery','Verified English')}};
 const submit=(data,opts={})=>request('submissions',{kind:'winery',data,submit:true,requestKey:crypto.randomUUID(),...opts});
 const approve=(id,revision=1)=>request('submissions/'+id+'/decision',{revision,action:'approve',ownerPublish:true,reason:'Checked the official language sources'});
 const initial=await submit(base);assert.equal(initial.status,201);assert.equal((await approve(initial.data.id)).status,200);const entityId=initial.data.entity_id;
 const ordinary={name:base.name,country:base.country,sourceTitle:base.sourceTitle,sourceURL:base.sourceURL,notes:'Edited by a form without language fields'};
 const edit=await submit(ordinary,{entityId,baseVersion:1});assert.equal(edit.status,201);assert.equal(edit.data.data.originalLanguage,'zh');assert.deepEqual(edit.data.data.localizations,base.localizations);
 const patch=await request('submissions/'+edit.data.id,{revision:1,baseVersion:1,data:{...ordinary,notes:'Draft updated without language fields'},submit:true},'PATCH');assert.equal(patch.status,200);
 const draft=await request('submissions/'+edit.data.id);assert.deepEqual(draft.data.data.localizations,base.localizations);
 assert.equal((await approve(edit.data.id,2)).status,200);
 const importRows=[{kind:'winery',entityId,data:{localizations:{en:{description:'Updated English evidence'}}}}];
 const preview=await request('imports/preview',{rows:importRows});assert.equal(preview.status,200);const row=preview.data.rows[0];assert.equal(row.status,'update');assert.equal(row.data.originalLanguage,'zh');assert.deepEqual(row.data.localizations.zh,base.localizations.zh);assert.equal(row.data.localizations.en.name,'Language Test Winery');assert.equal(row.data.localizations.en.status,'draft');
 const key=crypto.randomUUID();assert.equal((await request('imports/submit',{rows:importRows,importKey:key})).data.submitted,1);
 const pending=(await request('submissions')).data.submissions.find(s=>s.request_key===key+':2');assert.ok(pending);assert.equal((await approve(pending.id)).status,200);
 const entity=(await request('catalog')).data.entities.find(e=>e.id===entityId);assert.deepEqual(entity.data.localizations.zh,base.localizations.zh);assert.equal(entity.data.localizations.en.description,'Updated English evidence');assert.equal(entity.data.localizations.en.status,'draft');
 assert.equal((await request('imports/preview',{rows:importRows})).data.rows[0].status,'unchanged');
 const invalidRows=[{kind:'winery',entityId,data:{localizations:{fr:{...locale('Domaine','Texte'),checkedDate:'2026-02-30'}}}}];
 assert.equal((await request('imports/preview',{rows:invalidRows})).data.rows[0].status,'error');
 assert.equal((await request('imports/submit',{rows:invalidRows,importKey:crypto.randomUUID()})).status,400);
 assert.equal((await submit({...ordinary,localizations:{en:{...locale('Invalid','Invalid'),sourceURL:'javascript:alert(1)'}}})).status,400);
});
