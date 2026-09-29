#!/usr/bin/env node
/**
 * 风土图鉴 TERROIR ATLAS —— 腾讯云自托管运行层
 * ---------------------------------------------------------------
 * 站点原本跑在 ChatGPT Sites（Cloudflare Worker + D1 + R2）。
 * 这个文件不做任何业务逻辑改写，只补齐两件平台能力：
 *   1. D1  -> node:sqlite（本地 SQLite 文件）
 *   2. R2  -> 本地文件系统
 * 然后把 Node 的 http 请求转成标准 Request，交给原 Worker 的 fetch 处理。
 * 因此线上行为与 ChatGPT Sites 版本逐字节一致。
 *
 * 原本由 ChatGPT 平台注入的登录头（oai-authenticated-user-*），
 * 改由本站自己的站长登录会话注入；未登录时行为与现在完全一致
 * （community 页显示“当前采用人工投稿”）。
 */

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import worker from './dist/server/index.js';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3020);
const HOST = process.env.HOST || '127.0.0.1';
const DATA_DIR = process.env.DATA_DIR || path.join(ROOT, 'var');
const DB_FILE = path.join(DATA_DIR, 'terroir.sqlite');
const BUCKET_DIR = path.join(DATA_DIR, 'bucket');
const SESSION_FILE = path.join(DATA_DIR, 'session.key');
// 采集图片的网页缩略图：由 scripts/publish-entity-photos.py 生成到 <ROOT>/photos/，
// 随 deploy.sh 的 rsync 上服务器。故意不走 worker 的 base64 内嵌（那会把 7MB 产物继续撑大），
// 而是在这里直接从磁盘读，交给 Cloudflare 缓存。
const PHOTOS_DIR = path.resolve(process.env.PHOTOS_DIR || path.join(ROOT, 'photos'));

const OWNER_EMAIL = (process.env.OWNER_EMAIL || '').trim().toLowerCase();
const OWNER_NAME = (process.env.OWNER_NAME || '站长').trim();
const OWNER_PASSWORD = process.env.OWNER_PASSWORD || '';
const OWNER_PASSWORD_SHA256 = (process.env.OWNER_PASSWORD_SHA256 || '').trim().toLowerCase();

fs.mkdirSync(BUCKET_DIR, { recursive: true });

/* ------------------------------------------------------------------ *
 * 会话密钥：优先用环境变量，否则在 DATA_DIR 里生成并复用（chmod 600）
 * ------------------------------------------------------------------ */
const SESSION_SECRET = (() => {
  if (process.env.SESSION_SECRET) return process.env.SESSION_SECRET;
  if (fs.existsSync(SESSION_FILE)) return fs.readFileSync(SESSION_FILE, 'utf8').trim();
  const key = crypto.randomBytes(32).toString('hex');
  fs.writeFileSync(SESSION_FILE, key + '\n', { mode: 0o600 });
  return key;
})();

/* ------------------------------------------------------------------ *
 * D1 兼容层：prepare / bind / all / first / run / batch
 * ------------------------------------------------------------------ */
const SCHEMA = `
CREATE TABLE IF NOT EXISTS members (
  id text PRIMARY KEY NOT NULL, auth_id text, email text NOT NULL, name text NOT NULL,
  role text NOT NULL, status text NOT NULL, created text NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS members_auth ON members (auth_id);
CREATE UNIQUE INDEX IF NOT EXISTS members_email ON members (email);
CREATE TABLE IF NOT EXISTS entities (
  id text PRIMARY KEY NOT NULL, kind text NOT NULL, name text NOT NULL, data text NOT NULL,
  version integer NOT NULL, updated text NOT NULL, submission_id text);
CREATE TABLE IF NOT EXISTS history (
  id text PRIMARY KEY NOT NULL, entity_id text NOT NULL, version integer NOT NULL,
  data text NOT NULL, actor text NOT NULL, action text NOT NULL, reason text, created text NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS history_entity_version ON history (entity_id, version);
CREATE TABLE IF NOT EXISTS submissions (
  id text PRIMARY KEY NOT NULL, entity_id text NOT NULL, kind text NOT NULL, data text NOT NULL,
  base_version integer NOT NULL, revision integer NOT NULL, status text NOT NULL,
  author text NOT NULL, reviewer text, reason text, token text, request_key text NOT NULL,
  created text NOT NULL, updated text NOT NULL);
CREATE INDEX IF NOT EXISTS submissions_author ON submissions (author, updated);
CREATE INDEX IF NOT EXISTS submissions_status ON submissions (status, updated);
CREATE UNIQUE INDEX IF NOT EXISTS submissions_request ON submissions (author, request_key);
CREATE TABLE IF NOT EXISTS attachments (
  id text PRIMARY KEY NOT NULL, owner text NOT NULL, name text NOT NULL, mime text NOT NULL,
  size integer NOT NULL, created text NOT NULL, published integer DEFAULT 0 NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id text PRIMARY KEY NOT NULL, target text NOT NULL, actor text NOT NULL,
  action text NOT NULL, detail text NOT NULL, created text NOT NULL);
CREATE INDEX IF NOT EXISTS audit_target ON audit (target, created);
`;

/** SQLite 只接受 null / number / bigint / string / Uint8Array */
function normArgs(args) {
  return args.map((v) => {
    if (v === undefined) return null;
    if (typeof v === 'boolean') return v ? 1 : 0;
    if (v instanceof Date) return v.toISOString();
    if (v instanceof Uint8Array) return v;
    if (v === null || typeof v === 'number' || typeof v === 'string' || typeof v === 'bigint') return v;
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  });
}

class D1Statement {
  constructor(db, sql, args = []) {
    this.db = db;
    this.sql = sql;
    this.args = args;
  }
  bind(...args) {
    return new D1Statement(this.db, this.sql, args);
  }
  async all() {
    return { results: this.db.prepare(this.sql).all(...normArgs(this.args)), success: true, meta: {} };
  }
  async first() {
    const row = this.db.prepare(this.sql).get(...normArgs(this.args));
    return row === undefined ? null : row;
  }
  async run() {
    const r = this.db.prepare(this.sql).run(...normArgs(this.args));
    return {
      success: true,
      results: [],
      meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid ?? 0), duration: 0 },
    };
  }
}

class D1Database {
  constructor(file) {
    this.db = new DatabaseSync(file);
    this.db.exec('PRAGMA journal_mode = WAL;');
    this.db.exec('PRAGMA foreign_keys = ON;');
    this.db.exec(SCHEMA);
  }
  prepare(sql) {
    return new D1Statement(this.db, sql);
  }
  /** D1 的 batch 是事务语义 */
  async batch(statements) {
    const out = [];
    this.db.exec('BEGIN');
    try {
      for (const s of statements) out.push(await s.run());
      this.db.exec('COMMIT');
    } catch (e) {
      try { this.db.exec('ROLLBACK'); } catch {}
      throw e;
    }
    return out;
  }
  async exec(sql) {
    this.db.exec(sql);
    return { count: 0, duration: 0 };
  }
}

/* ------------------------------------------------------------------ *
 * R2 兼容层：put / get / delete，落在本地目录
 * ------------------------------------------------------------------ */
class R2Bucket {
  constructor(dir) {
    this.dir = dir;
  }
  #file(key) {
    return path.join(this.dir, encodeURIComponent(String(key)));
  }
  async put(key, value, options) {
    const buf = Buffer.isBuffer(value)
      ? value
      : value instanceof ArrayBuffer
        ? Buffer.from(value)
        : value instanceof Uint8Array
          ? Buffer.from(value)
          : Buffer.from(String(value), 'utf8');
    await fs.promises.writeFile(this.#file(key), buf);
    await fs.promises.writeFile(
      this.#file(key) + '.meta.json',
      JSON.stringify({ key, size: buf.length, contentType: options?.httpMetadata?.contentType || 'application/octet-stream' })
    );
    return { key, size: buf.length };
  }
  async get(key) {
    try {
      const buf = await fs.promises.readFile(this.#file(key));
      let contentType = 'application/octet-stream';
      try {
        contentType = JSON.parse(await fs.promises.readFile(this.#file(key) + '.meta.json', 'utf8')).contentType;
      } catch {}
      return {
        key,
        size: buf.length,
        httpMetadata: { contentType },
        body: new Blob([buf]).stream(),
        arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength),
        text: async () => buf.toString('utf8'),
      };
    } catch {
      return null;
    }
  }
  async delete(key) {
    await fs.promises.rm(this.#file(key), { force: true });
    await fs.promises.rm(this.#file(key) + '.meta.json', { force: true });
  }
}

/* ------------------------------------------------------------------ *
 * env 绑定
 * ------------------------------------------------------------------ */
const DB = new D1Database(DB_FILE);
const BUCKET = new R2Bucket(BUCKET_DIR);
const ENV = {
  DB,
  BUCKET,
  // 为空 => 与 ChatGPT 版本现状一致：线上共建关闭，页面走“人工投稿”
  OWNER_EMAIL,
};

/* ------------------------------------------------------------------ *
 * 站长登录（替代 ChatGPT 平台身份注入）
 * ------------------------------------------------------------------ */
const AUTH_ENABLED = Boolean(OWNER_EMAIL && (OWNER_PASSWORD || OWNER_PASSWORD_SHA256));
const COOKIE = 'terroir_session';
const b64u = (b) => Buffer.from(b).toString('base64url');
const unb64u = (s) => Buffer.from(s, 'base64url').toString('utf8');

function passwordOK(input) {
  if (!AUTH_ENABLED) return false;
  const given = crypto.createHash('sha256').update(String(input), 'utf8').digest('hex');
  const want = OWNER_PASSWORD_SHA256 || crypto.createHash('sha256').update(OWNER_PASSWORD, 'utf8').digest('hex');
  const a = Buffer.from(given, 'hex');
  const b = Buffer.from(want, 'hex');
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function sign(payload) {
  return crypto.createHmac('sha256', SESSION_SECRET).update(payload).digest('base64url');
}

function issueToken(email, name) {
  const payload = b64u(JSON.stringify({ e: email, n: name, exp: Date.now() + 14 * 864e5 }));
  return payload + '.' + sign(payload);
}

function readToken(token) {
  if (!token || !token.includes('.')) return null;
  const [payload, sig] = token.split('.');
  const expect = sign(payload);
  if (sig.length !== expect.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expect))) return null;
  try {
    const data = JSON.parse(unb64u(payload));
    if (!data.exp || data.exp < Date.now()) return null;
    if (!AUTH_ENABLED || String(data.e).toLowerCase() !== OWNER_EMAIL) return null;
    return { email: String(data.e), name: String(data.n || data.e) };
  } catch {
    return null;
  }
}

function parseCookies(header = '') {
  const out = {};
  for (const part of header.split(';')) {
    const i = part.indexOf('=');
    if (i > 0) out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

/** 把会话转换成 Worker 认识的平台身份头 */
function identityHeaders(session, headers) {
  if (!session) return;
  headers['oai-authenticated-user-id'] = crypto
    .createHash('sha256')
    .update('terroir-atlas:' + session.email)
    .digest('hex');
  headers['oai-authenticated-user-email'] = session.email;
  headers['oai-authenticated-user-full-name'] = encodeURIComponent(session.name);
  headers['oai-authenticated-user-full-name-encoding'] = 'percent-encoded-utf-8';
}

const LOGIN_PAGE = (msg = '') => `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>站长登录 · 风土图鉴</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f6f4f1;color:#241d20;
font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif}
form{background:#fff;padding:32px;border-radius:16px;box-shadow:0 18px 50px -24px rgba(60,20,40,.3);width:min(360px,90vw)}
h1{margin:0 0 6px;font-size:20px}p.sub{margin:0 0 20px;color:#7a6c72;font-size:13px}
label{display:block;font-size:13px;margin:14px 0 6px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #ded6d9;border-radius:9px;font-size:15px}
button{margin-top:20px;width:100%;padding:11px;border:0;border-radius:9px;background:#592a42;color:#fff;font-size:15px;cursor:pointer}
.err{background:#fdecef;color:#96223f;padding:9px 11px;border-radius:8px;font-size:13px;margin-bottom:6px}</style></head>
<body><form method="POST" action="/__auth/login"><h1>风土图鉴 · 站长登录</h1>
<p class="sub">登录后可在线补充资料、审核投稿与批量导入。</p>
${msg ? `<div class="err">${msg}</div>` : ''}
<label for="email">邮箱</label><input id="email" name="email" type="email" autocomplete="username" required>
<label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<button type="submit">登录</button></form></body></html>`;

async function readBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks);
}

const DROP_HEADERS = new Set([
  'content-length', 'connection', 'keep-alive', 'transfer-encoding',
  'upgrade', 'expect', 'accept-encoding', 'host',
]);

/* ------------------------------------------------------------------ *
 * HTTP 服务
 * ------------------------------------------------------------------ */
let inflight = 0;

const server = http.createServer(async (req, res) => {
  const started = Date.now();
  try {
    const host = req.headers['host'] || `127.0.0.1:${PORT}`;
    const url = new URL(req.url || '/', `${proto(req)}://${host}`);

    /* --- 站点自管的登录入口 --- */
    if (url.pathname === '/__auth/login' || url.pathname === '/__auth/logout') {
      return handleAuthRoute(req, res, url);
    }
    if (url.pathname === '/healthz') {
      return send(res, 200, 'text/plain; charset=utf-8', Buffer.from('ok\n'));
    }

    /* --- 采集图片缩略图（磁盘直读，不进 worker 产物） --- */
    if (url.pathname.startsWith('/photos/')) {
      return servePhoto(req, res, url);
    }

    /* --- 转发给原 Worker --- */
    const headers = {};
    for (const [k, v] of Object.entries(req.headers)) {
      if (DROP_HEADERS.has(k.toLowerCase())) continue;
      headers[k] = Array.isArray(v) ? v.join(', ') : v;
    }
    const session = readToken(parseCookies(req.headers.cookie || '')[COOKIE]);
    identityHeaders(session, headers);

    const hasBody = !['GET', 'HEAD'].includes(req.method);
    const body = hasBody ? await readBody(req) : undefined;

    const request = new Request(url, { method: req.method, headers, body });
    inflight++;
    const response = await worker.fetch(request, ENV);
    inflight--;

    const outHeaders = {};
    response.headers.forEach((v, k) => {
      outHeaders[k] = v;
    });
    const buf = req.method === 'HEAD' ? Buffer.alloc(0) : Buffer.from(await response.arrayBuffer());
    res.writeHead(response.status, outHeaders);
    res.end(buf);

    if (process.env.ACCESS_LOG !== 'off') {
      console.log(`${new Date().toISOString()} ${req.method} ${url.pathname}${url.search} -> ${response.status} ${Date.now() - started}ms`);
    }
  } catch (err) {
    inflight--;
    console.error('请求处理失败:', err);
    if (!res.headersSent) {
      res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' });
    }
    res.end(JSON.stringify({ error: '资料服务暂时不可用，请稍后重试。' }));
  }
});

function proto(req) {
  const xf = String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim();
  if (xf === 'https' || xf === 'http') return xf;
  return req.socket?.encrypted ? 'https' : 'http';
}

function send(res, status, type, buf, extra = {}) {
  res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store', ...extra });
  res.end(buf);
}

const PHOTO_TYPES = {
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
  '.webp': 'image/webp', '.avif': 'image/avif', '.gif': 'image/gif',
};

async function servePhoto(req, res, url) {
  if (!['GET', 'HEAD'].includes(req.method)) {
    return send(res, 405, 'text/plain; charset=utf-8', Buffer.from('method not allowed\n'), { allow: 'GET, HEAD' });
  }
  let rel;
  try {
    rel = decodeURIComponent(url.pathname.slice('/photos/'.length));
  } catch {
    return send(res, 400, 'text/plain; charset=utf-8', Buffer.from('bad path\n'));
  }
  // 目录穿越防护：解析后的绝对路径必须仍在 PHOTOS_DIR 之内。
  const abs = path.resolve(PHOTOS_DIR, rel);
  if (abs !== PHOTOS_DIR && !abs.startsWith(PHOTOS_DIR + path.sep)) {
    return send(res, 403, 'text/plain; charset=utf-8', Buffer.from('forbidden\n'));
  }
  const type = PHOTO_TYPES[path.extname(abs).toLowerCase()];
  if (!type) {
    return send(res, 404, 'text/plain; charset=utf-8', Buffer.from('not found\n'));
  }
  let buf;
  try {
    buf = await fs.promises.readFile(abs);
  } catch {
    return send(res, 404, 'text/plain; charset=utf-8', Buffer.from('not found\n'));
  }
  return send(res, 200, type, req.method === 'HEAD' ? Buffer.alloc(0) : buf, {
    'cache-control': 'public, max-age=604800',
    'content-length': String(buf.length),
    'x-content-type-options': 'nosniff',
  });
}

async function handleAuthRoute(req, res, url) {
  if (url.pathname === '/__auth/logout') {
    return send(res, 302, 'text/plain; charset=utf-8', Buffer.alloc(0), {
      location: '/',
      'set-cookie': `${COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`,
    });
  }
  if (!AUTH_ENABLED) {
    return send(res, 200, 'text/html; charset=utf-8',
      Buffer.from(LOGIN_PAGE('服务器尚未配置站长账号：请在 .env 里设置 OWNER_EMAIL 与 OWNER_PASSWORD 后重启。')));
  }
  if (req.method === 'GET') {
    return send(res, 200, 'text/html; charset=utf-8', Buffer.from(LOGIN_PAGE()));
  }
  if (req.method !== 'POST') {
    return send(res, 405, 'text/plain; charset=utf-8', Buffer.from('Method Not Allowed\n'));
  }
  const raw = (await readBody(req)).toString('utf8');
  const form = new URLSearchParams(raw);
  const email = (form.get('email') || '').trim().toLowerCase();
  const password = form.get('password') || '';
  if (email !== OWNER_EMAIL || !passwordOK(password)) {
    // 失败也放慢一点，避免暴力尝试
    await new Promise((r) => setTimeout(r, 400));
    return send(res, 401, 'text/html; charset=utf-8', Buffer.from(LOGIN_PAGE('邮箱或密码不正确。')));
  }
  const token = issueToken(email, OWNER_NAME);
  return send(res, 302, 'text/plain; charset=utf-8', Buffer.alloc(0), {
    location: '/community',
    'set-cookie': `${COOKIE}=${token}; Path=/; Max-Age=1209600; HttpOnly; SameSite=Lax`,
  });
}

server.listen(PORT, HOST, () => {
  console.log(`风土图鉴已启动: http://${HOST}:${PORT}`);
  console.log(`  数据库: ${DB_FILE}`);
  console.log(`  附件桶: ${BUCKET_DIR}`);
  console.log(`  站长登录: ${AUTH_ENABLED ? `已启用（${OWNER_EMAIL}）` : '未配置 —— 线上共建保持关闭，页面走“人工投稿”'}`);
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    console.log(`收到 ${sig}，正在关闭…`);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 3000);
  });
}

process.on('unhandledRejection', (e) => console.error('未处理的 Promise 拒绝:', e));
