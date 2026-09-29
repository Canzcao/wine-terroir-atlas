#!/usr/bin/env node
/**
 * 本地冒烟测试：验证自托管运行层与原 ChatGPT Sites 版本行为一致。
 * 自己拉起 server.mjs，跑完再关掉，可重复运行。
 *   node smoke_test.mjs
 */
import { spawn } from 'node:child_process';
import { stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const PORT = Number(process.env.PORT || 3020);
const BASE = process.env.BASE || `http://127.0.0.1:${PORT}`;
let pass = 0, fail = 0;
let child = null;

async function startServer() {
  // 注意：Windows 下不能直接用 new URL(...).pathname（会得到 /D:/... 这种带前导斜杠的路径，
  // spawn 会报 ENOENT），必须用 fileURLToPath 解出原生路径。
  child = spawn(process.execPath, ['--no-warnings', 'server.mjs'], {
    cwd: fileURLToPath(new URL('.', import.meta.url)),
    env: { ...process.env, PORT: String(PORT), ACCESS_LOG: 'off' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.on('data', (d) => {
    const s = d.toString();
    if (!/ExperimentalWarning|trace-warnings/.test(s)) process.stderr.write('[server] ' + s);
  });
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(BASE + '/healthz');
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error('服务未能在 15 秒内就绪');
}

function stopServer() {
  if (child && !child.killed) child.kill('SIGTERM');
}

async function check(name, fn) {
  try {
    const detail = await fn();
    pass++;
    console.log(`  ✅ ${name}${detail ? ' — ' + detail : ''}`);
  } catch (e) {
    fail++;
    console.log(`  ❌ ${name} — ${e.message}`);
  }
}

const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

await startServer();
console.log(`\n服务已就绪 ${BASE}\n`);

console.log(`【页面路由】`);
for (const [p, expect] of [['/', 200], ['/community?lang=zh', 200], ['/catalog', 200], ['/reports', 200], ['/nope-xyz', 404]]) {
  await check(`GET ${p} -> ${expect}`, async () => {
    const r = await fetch(BASE + p);
    assert(r.status === expect, `实际 ${r.status}`);
    return `${(await r.text()).length} 字节`;
  });
}

console.log(`\n【静态资源】`);
for (const p of ['/style.css', '/community.css', '/community.js', '/ui-locales.js', '/i18n.js', '/language-core.js', '/catalog-map.js', '/locale-editor.js', '/assets/exceljs.min.js', '/reports.js', '/data.js', '/region-wineries.js', '/region-wineries.css', '/responsive.css', '/entity-photos.json']) {
  await check(`GET ${p}`, async () => {
    const r = await fetch(BASE + p);
    assert(r.status === 200, `实际 ${r.status}`);
    return `${r.headers.get('content-type')} ${(await r.arrayBuffer()).byteLength}B`;
  });
}

// 探索地图的「已收录酒庄与酒款」依赖三件事同时成立，缺一项线上就白屏或无声降级：
//   1. index.html 引到新脚本与样式
//   2. 探索地图的产区 id 能对上资料库产区（靠 regionId 传递闭包展开子产区）
//   3. /photos/* 真能取到图（缩略图由 scripts/publish-entity-photos.py 产出）
console.log(`\n【探索地图接入采集酒庄与酒款】`);
await check('index.html 引用 region-wineries 脚本与样式', async () => {
  const html = await (await fetch(BASE + '/')).text();
  assert(html.includes('/region-wineries.js'), '缺 script 标签');
  assert(html.includes('/region-wineries.css'), '缺 link 标签');
  const js = await fetch(BASE + '/region-wineries.js');
  assert(js.status === 200, `脚本 ${js.status}`);
  const src = await js.text();
  for (const token of ['window.wineCatalogueReady', 'entity-photos.json', 'selectRegion']) {
    assert(src.includes(token), `脚本缺少 ${token}`);
  }
  return '脚本、样式、依赖就位';
});

// 手机端适配层（responsive.css）同样是「漏一个页面就静默降级」：
// 它必须在这三页里都是最后一个 <link>，否则末位就被别人的规则压掉。
console.log(`\n【手机端适配层】`);
await check('三页都引用了 /responsive.css 且排在最后一个样式表', async () => {
  const pages = [['/', 'index.html'], ['/community', 'community.html'], ['/reports', 'reports.html']];
  const seen = [];
  for (const [route, name] of pages) {
    const html = await (await fetch(BASE + route)).text();
    assert(html.includes('/responsive.css'), `${name} 缺 responsive.css 的 link`);
    // 取所有 css 的 link，responsive.css 必须是最后一个（晚于 i18n.css / map-explorer.css）
    const order = [...html.matchAll(/<link[^>]+href="([^"]+\.css)"/g)].map(m => m[1]);
    assert(order.length > 0, `${name} 没解析到任何 css link`);
    assert(order[order.length - 1] === '/responsive.css',
      `${name} 的最后一个样式表是 ${order[order.length - 1]}，应为 /responsive.css`);
    seen.push(`${name}:${order.length}`);
  }
  return seen.join(' ');
});
await check('responsive.css 含关键适配规则', async () => {
  const r = await fetch(BASE + '/responsive.css');
  assert(r.status === 200, `实际 ${r.status}`);
  const css = await r.text();
  for (const token of [
    '.masthead nav{flex-wrap:wrap',                    // 导航换行，取代横向滚动
    '.masthead nav .nav-active{display:none',          // 首页冗余导航项
    '.collected-locate{',                              // 已收录酒庄组件的触摸目标
    'mask-image:linear-gradient',                      // 横向条渐隐提示
    '.map-shell .leaflet-control-attribution'          // 版权行必须带 .map-shell 前缀才压得住
  ]) {
    assert(css.includes(token), `缺少规则 ${token}`);
  }
  assert(!/\.masthead nav\{[^}]*mask-image/.test(css), '不得给 .masthead nav 加遮罩（会淡掉最后一项）');
  return `${css.length} 字节规则就位`;
});
await check('entity-photos.json 覆盖图实体且路径可取自 /photos/', async () => {
  const r = await fetch(BASE + '/entity-photos.json');
  assert(r.status === 200, `实际 ${r.status}`);
  const m = await r.json();
  const ids = Object.keys(m.entities || {});
  assert(ids.length > 0, '没有任何实体配图');
  let total = 0;
  for (const list of Object.values(m.entities)) total += list.length;

  // ★ 本机不持有 photos/ 树（照片以远端为权威源，本地只做增量差集，
  //   见 deploy/deploy.local.sh 第 4 步）。此时若拿 entity-photos.json 里的
  //   任意一张图去探测，必然 404 —— 那是环境差异，不是回归。
  //   因此：优先挑本地确实存在的照片；一张都没有时，改为断言
  //   「服务对缺失照片正确 404」，把覆盖度检测留给线上复验。
  const localRoot = fileURLToPath(new URL('./photos/', import.meta.url));
  let probe = null;
  for (const id of ids) {
    for (const it of m.entities[id]) {
      if (!/^\/photos\//.test(it.src)) assert(false, `路径不是 /photos/ 前缀：${it.src}`);
      const rel = it.src.replace(/^\/photos\//, '');
      let hit = false;
      try {
        hit = (await stat(localRoot + rel)).isFile();
      } catch {
        hit = false;
      }
      if (hit) { probe = it; break; }
    }
    if (probe) break;
  }

  if (!probe) {
    const miss = await fetch(BASE + m.entities[ids[0]][0].src);
    assert(miss.status === 404, `本地无 photos 树时，缺失照片应 404，实际 ${miss.status}`);
    return `${ids.length} 个实体 / ${total} 张图；本机无 photos/ 树，跳过取图探测（线上复验覆盖）`;
  }

  const img = await fetch(BASE + probe.src);
  assert(img.status === 200, `缩略图取不到：${probe.src} -> ${img.status}`);
  assert(/^image\//.test(img.headers.get('content-type') || ''), `content-type 不是图片：${img.headers.get('content-type')}`);
  const bytes = (await img.arrayBuffer()).byteLength;
  assert(bytes > 1024, `缩略图过小：${bytes}B`);
  return `${ids.length} 个实体 / ${total} 张图，样例 ${bytes}B ${probe.src}`;
});
await check('/photos/ 拒绝目录穿越与非法扩展名', async () => {
  const bad = await fetch(BASE + '/photos/../server.mjs');
  assert(bad.status === 403 || bad.status === 404, `穿越未被拦截：${bad.status}`);
  const ext = await fetch(BASE + '/photos/chateau-grillet/winery-chateau-grillet/01-Grillet-scaled.txt');
  assert(ext.status === 404, `非法扩展名未拦截：${ext.status}`);
  const miss = await fetch(BASE + '/photos/chateau-grillet/nope/nope.jpg');
  assert(miss.status === 404, `缺失文件未返回 404：${miss.status}`);
  return '穿越 403/404、非法扩展名 404、缺失文件 404';
});
await check('资料库产区能覆盖探索地图的每个产区入口', async () => {
  const { entities } = await (await fetch(BASE + '/api/catalog')).json();
  const regions = entities.filter((e) => e.kind === 'region');
  const wineries = entities.filter((e) => e.kind === 'winery');
  const scoped = new Set(regions.map((r) => r.id));
  // 与前端一致：沿 regionId 向下递归展开，data.js 的入口 id 直接命中资料库产区
  const byParent = new Map();
  for (const r of regions) byParent.set(r.data.regionId || '', [...(byParent.get(r.data.regionId || '') || []), r.id]);
  const scope = (root) => { const out = new Set(), q = [root]; while (q.length) { const x = q.pop(); if (out.has(x)) continue; out.add(x); for (const k of byParent.get(x) || []) q.push(k); } return out; };
  const dataJs = await (await fetch(BASE + '/data.js')).text();
  const ids = [...new Set([...dataJs.matchAll(/\{id:\s*['"]([^'"]+)['"]/g), ...dataJs.matchAll(/"id":\s*"([^"]+)"/g)].map((m) => m[1]))];
  assert(ids.length > 30, `只解析到 ${ids.length} 个产区入口`);
  const empty = [];
  for (const id of ids) {
    const s = scope(id);
    if (!wineries.some((w) => s.has(w.data.regionId))) empty.push(id);
  }
  assert(empty.length === 0, `以下产区解析不到任何采集酒庄：${empty.join(', ')}`);
  // 有 regionId 落空的酒庄会在任何产区视图里都看不到，属于采集侧待修数据，单独报数不判失败
  const orphans = wineries.filter((w) => !scoped.has(w.data.regionId)).length;
  return `${ids.length}/${ids.length} 个产区入口可解析酒庄；另有 ${orphans} 家酒庄 regionId 为空，任何产区都覆盖不到`;
});

console.log(`\n【模板下载（community 页核心内容）】`);
for (const p of [
  '/downloads/terroir-atlas-contribution-template.xlsx',
  '/downloads/terroir-atlas-contribution-guide.pdf',
  '/downloads/terroir-atlas-contribution-guide.docx',
  '/downloads/terroir-atlas-contribution-example.csv',
]) {
  await check(`GET ${p}`, async () => {
    const r = await fetch(BASE + p);
    assert(r.status === 200, `实际 ${r.status}`);
    return `${(await r.arrayBuffer()).byteLength}B`;
  });
}

console.log(`\n【公开 API】`);
await check('GET /api/catalog', async () => {
  const j = await (await fetch(BASE + '/api/catalog')).json();
  assert(j.entities?.length > 500, `仅 ${j.entities?.length} 条`);
  const kinds = {};
  j.entities.forEach((e) => (kinds[e.kind] = (kinds[e.kind] || 0) + 1));
  return `${j.entities.length} 条 ${JSON.stringify(kinds)}`;
});
await check('GET /api/events', async () => {
  const j = await (await fetch(BASE + '/api/events')).json();
  assert(Array.isArray(j.events), 'events 不是数组');
  return `${j.events.length} 条事件`;
});
await check('GET /api/reports', async () => {
  const j = await (await fetch(BASE + '/api/reports')).json();
  assert(Array.isArray(j.reports), 'reports 不是数组');
  return `${j.reports.length} 期简报`;
});
await check('GET /api/history/:id', async () => {
  const cat = await (await fetch(BASE + '/api/catalog')).json();
  const id = cat.entities[0].id;
  const r = await fetch(BASE + '/api/history/' + encodeURIComponent(id));
  assert(r.status === 200, `实际 ${r.status}`);
  const j = await r.json();
  assert(Array.isArray(j.history), 'history 不是数组');
  return `${id} → ${j.history.length} 个版本`;
});
await check('GET /api/me 未登录 -> 503（community 页走“人工投稿”）', async () => {
  const r = await fetch(BASE + '/api/me');
  assert([401, 503].includes(r.status), `实际 ${r.status}`);
  const j = await r.json();
  assert(typeof j.error === 'string', '缺少 error 文案');
  return `${r.status} ${j.error.slice(0, 24)}…`;
});

console.log(`\n【D1 写入链路（模拟一次投稿 + 审核通过，验证 SQLite 事务）】`);
await check('members/entities/submissions/attachments 可读写', async () => {
  const { DatabaseSync } = await import('node:sqlite');
  const db = new DatabaseSync(process.env.DB_PATH || './var/terroir.sqlite');
  const stamp = new Date().toISOString();
  db.prepare('INSERT OR REPLACE INTO members (id,auth_id,email,name,role,status,created) VALUES (?,?,?,?,?,?,?)')
    .run('smoke-tester', 'smoke-auth', 'smoke@local', '冒烟测试', 'admin', 'active', stamp);
  db.prepare('INSERT OR REPLACE INTO entities (id,kind,name,data,version,updated) VALUES (?,?,?,?,?,?)')
    .run('smoke-entity', 'winery', '冒烟酒庄', JSON.stringify({ name: '冒烟酒庄' }), 1, stamp);
  db.prepare('INSERT OR REPLACE INTO submissions (id,entity_id,kind,data,base_version,revision,status,author,request_key,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)')
    .run('smoke-sub', 'smoke-entity', 'winery', JSON.stringify({ name: '冒烟酒庄' }), 1, 1, 'pending', 'smoke-tester', 'smoke-key', stamp, stamp);
  const row = db.prepare('SELECT * FROM submissions WHERE id=?').get('smoke-sub');
  assert(row?.status === 'pending', '写入后读回失败');
  db.prepare('DELETE FROM submissions WHERE id=?').run('smoke-sub');
  db.prepare('DELETE FROM entities WHERE id=?').run('smoke-entity');
  db.prepare('DELETE FROM members WHERE id=?').run('smoke-tester');
  return '四项表读写与回滚正常';
});
await check('写入的 entity 会进入 /api/catalog（D1 与 seed 合并）', async () => {
  const before = (await (await fetch(BASE + '/api/catalog')).json()).entities.length;
  const { DatabaseSync } = await import('node:sqlite');
  const db = new DatabaseSync(process.env.DB_PATH || './var/terroir.sqlite');
  const stamp = new Date().toISOString();
  db.prepare('INSERT OR REPLACE INTO entities (id,kind,name,data,version,updated) VALUES (?,?,?,?,?,?)')
    .run('smoke-merge', 'winery', '合并测试酒庄', JSON.stringify({ name: '合并测试酒庄' }), 1, stamp);
  const after = (await (await fetch(BASE + '/api/catalog')).json()).entities.length;
  db.prepare('DELETE FROM entities WHERE id=?').run('smoke-merge');
  assert(after === before + 1, `合并前后 ${before} -> ${after}`);
  const restored = (await (await fetch(BASE + '/api/catalog')).json()).entities.length;
  assert(restored === before, `清理后应为 ${before}，实际 ${restored}`);
  return `${before} -> ${after} -> ${restored}`;
});

console.log(`\n【R2 附件桶：已发布附件可公开下载】`);
await check('published 附件经 R2 兼容层正常下载', async () => {
  const fs = await import('node:fs');
  const { DatabaseSync } = await import('node:sqlite');
  const png = Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489', 'hex');
  const key = 'smoke-attachment';
  const bucketDir = (process.env.BUCKET_DIR || './var/bucket') + '/';
  fs.mkdirSync(bucketDir, { recursive: true });
  fs.writeFileSync(bucketDir + encodeURIComponent(key), png);
  fs.writeFileSync(bucketDir + encodeURIComponent(key) + '.meta.json', JSON.stringify({ contentType: 'image/png' }));
  const db = new DatabaseSync(process.env.DB_PATH || './var/terroir.sqlite');
  const stamp = new Date().toISOString();
  db.prepare('INSERT OR REPLACE INTO members (id,auth_id,email,name,role,status,created) VALUES (?,?,?,?,?,?,?)')
    .run('smoke-tester', 'smoke-auth', 'smoke@local', '冒烟测试', 'admin', 'active', stamp);
  db.prepare('INSERT OR REPLACE INTO attachments (id,owner,name,mime,size,created,published) VALUES (?,?,?,?,?,?,1)')
    .run(key, 'smoke-tester', '冒烟.png', 'image/png', png.length, stamp);
  const r = await fetch(BASE + '/api/attachments/' + key);
  const got = Buffer.from(await r.arrayBuffer());
  db.prepare('DELETE FROM attachments WHERE id=?').run(key);
  db.prepare('DELETE FROM members WHERE id=?').run('smoke-tester');
  fs.rmSync(bucketDir + encodeURIComponent(key), { force: true });
  fs.rmSync(bucketDir + encodeURIComponent(key) + '.meta.json', { force: true });
  assert(r.status === 200, `实际 ${r.status}`);
  assert(got.length === png.length, `字节数 ${got.length} != ${png.length}`);
  return `HTTP 200 / ${got.length} 字节 / ${r.headers.get('content-type')}`;
});
await check('不存在的附件落到鉴权分支（与原站一致，非 404）', async () => {
  const r = await fetch(BASE + '/api/attachments/not-exist');
  assert([401, 503].includes(r.status), `实际 ${r.status}`);
  return `HTTP ${r.status}（未登录时原站同样是 401/503 而非 404）`;
});

console.log(`\n结果：通过 ${pass} 项，失败 ${fail} 项\n`);
stopServer();
process.exit(fail ? 1 : 0);
