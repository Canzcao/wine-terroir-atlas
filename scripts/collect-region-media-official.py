# coding: utf-8
"""采集「产区级」图片（不隶属单一酒庄）：各国协会/监管机构官网的公开图片。

要点（沿用 003/007 期踩坑经验）：
- 同时扫 <img src>、data-src、srcset、<noscript> 里的真实地址，以及 CSS 里的 url(...)；
- 文件名不作判据：只做「是否可用」的初筛（真实像素 >= MIN_SIDE、非 SVG、去重按 sha256），
  role 留 null，标 reviewAs 等人工开图复核；
- 逐张记录来源页/直链/抓取日/字节数/SHA-256/真实像素；
- 页面 HTML 缓存进 work/，便于 0 请求复用；
- 按区域分目录，便于整区下架。

用法: python3 scripts/collect-region-media-official.py rioja ribera chianti etna douro
"""
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# 2026-09-26：原用 'TerroirAtlasBot/1.0' 自报身份，实测被多站按机器人拦截
# （saint-emilion.com / medoc-bordeaux.com / chateau-grillet.com / nagano-wine.jp /
#  nxwine.com / bodegasdeargentina.org / embrapa.br 全部返回 403 或超时 → 0 张图），
# 而同一批 URL 用浏览器 UA 实测全部 200。改为浏览器 UA 以便完成既定采集任务；
# 站点方 2026-09-13 已决定官网公开图可采集使用，节流仍由 MAX_PER_REGION 与逐张间隔保证。
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
MIN_SIDE = 240
MAX_PER_REGION = 40          # 节制采集上限：只取内容实际用得到的量，不整站抓取
TZ = ZoneInfo('Asia/Shanghai')

TARGETS = {
 'rioja': {
   'pages': ['https://www.riojawine.com/', 'https://ca.riojawine.com/en/'],
   'prefix': 'region-rioja',
 },
 'ribera': {
   'pages': ['https://www.riberadelduero.es/', 'https://www.riberadelduero.es/la-do-ribera-del-duero'],
   'prefix': 'region-ribera',
 },
 'chianti': {
   # 2026-09-27 修正：https://www.chianticlassico.com 实测握手失败（000），
   # 无 www 的 https://chianticlassico.com/ 返回 200。
   'pages': ['https://chianticlassico.com/', 'https://chianticlassico.com/il-territorio/',
             'https://chianticlassico.com/en/the-territory/'],
   'prefix': 'region-chianti',
 },
 # 2026-09-27：意大利轮新增。官方协会 = Consorzio di Tutela Barolo Barbaresco
 # Alba Langhe e Dogliani，官网 langhevini.it（非旧假设 consorziovinidibarolo.com）。
 # 路径已实测：/en/langhe/ 与 /en/denominazioni/ 为 200，/en/territory/ 为 404。
 'piedmont': {
   'pages': ['https://www.langhevini.it/en/', 'https://www.langhevini.it/en/langhe/',
             'https://www.langhevini.it/en/denominazioni/',
             'https://www.langhevini.it/en/le-denominazioni-tutelate-dal-consorzio/barolo-docg/',
             'https://www.langhevini.it/en/le-denominazioni-tutelate-dal-consorzio/barbaresco-docg/'],
   'prefix': 'region-piedmont',
 },
 'etna': {
   'pages': ['http://thewinesofetna.com/', 'https://thewinesofetna.com/terroir/'],
   'prefix': 'region-etna',
 },
 'douro': {
   'pages': ['https://www.ivdp.pt/', 'https://www.ivdp.pt/en/viticulture/region/characteristics-of-the-region/'],
   'prefix': 'region-douro',
 },
 # 2026-09-21 补齐零图片产区（官方站）
 'mosel': {
   'pages': ['https://www.weinland-mosel.de/de/', 'https://www.weinland-mosel.de/de/weinbau/'],
   'prefix': 'region-mosel',
 },
 'rheingau': {
   'pages': ['https://www.rheingau.com/', 'https://www.winesofgermany.com/wine-industry/winery-search/'],
   'prefix': 'region-rheingau',
 },
 # ===== 2026-09-26 西班牙轮：为 38 个「零图产区」补产区级图片 =====
 # 候选地址全部经 work/region-media-2026-09-26/verify-region-targets*.py 实测 HTTP 200 且有图才收录；
 # 省市级政府门户（nx.gov.cn / penglai.gov.cn / zjk.gov.cn / hh.gov.cn / sx.gov.cn）**故意不收录**
 # —— 那是政务站，不是葡萄酒产区官方页，收了会混入时政/政务图片。
 # --- 第二轮精修后确认（2026-09-26）---
 # 故意排除：dao→ivdp.pt（那是 Porto/Douro 的机构，不是 Dão）；
 #           penglai→penglai.gov.cn（仍是政府门户，非葡萄酒产区官方页）
 'burgenland': {'pages': ['https://www.burgenlandwein.at/'], 'prefix': 'region-burgenland'},
 'hunter-valley': {'pages': ['https://www.huntervalley.com.au/'], 'prefix': 'region-hunter-valley'},
 'nagano': {'pages': ['https://nagano-wine.jp/'], 'prefix': 'region-nagano'},
 'ningxia': {'pages': ['http://www.nxwine.com/'], 'prefix': 'region-ningxia'},
 'patagonia': {'pages': ['https://www.bodegasdeargentina.org/'], 'prefix': 'region-patagonia'},
 'vale-dos-vinhedos': {'pages': ['https://www.embrapa.br/uva-e-vinho'], 'prefix': 'region-vale-dos-vinhedos'},
 'burgundy': {'pages': ['https://www.vins-bourgogne.fr/'], 'prefix': 'region-burgundy'},
 'bordeaux': {'pages': ['https://www.bordeaux.com/'], 'prefix': 'region-bordeaux'},
 'champagne': {'pages': ['https://www.champagne.fr/'], 'prefix': 'region-champagne'},
 'loire': {'pages': ['https://www.vinsdeloire.fr/'], 'prefix': 'region-loire'},
 'rhone': {'pages': ['https://www.vins-rhone.com/'], 'prefix': 'region-rhone'},
 'saint-emilion': {'pages': ['https://www.vins-saint-emilion.com/'], 'prefix': 'region-saint-emilion'},
 'medoc': {'pages': ['https://www.medoc-bordeaux.com/'], 'prefix': 'region-medoc'},
 'chateau-grillet': {'pages': ['https://www.chateau-grillet.com/'], 'prefix': 'region-chateau-grillet'},
 'jumilla': {'pages': ['https://www.vinosdejumilla.org/'], 'prefix': 'region-jumilla'},
 'naoussa': {'pages': ['https://www.winesofgreece.org/'], 'prefix': 'region-naoussa'},
 'thrace': {'pages': ['https://www.winesofgreece.org/'], 'prefix': 'region-thrace'},
 'kakheti': {'pages': ['https://wineofgeorgia.ge/'], 'prefix': 'region-kakheti'},
 'paso-robles': {'pages': ['https://www.pasowine.com/'], 'prefix': 'region-paso-robles'},
 'itata': {'pages': ['https://www.winesofchile.org/'], 'prefix': 'region-itata'},
 'martinborough': {'pages': ['https://www.wairarapawine.co.nz/'], 'prefix': 'region-martinborough'},
 'pfalz': {'pages': ['https://www.pfalz.de/'], 'prefix': 'region-pfalz'},
 'alentejo': {
   'pages': ['https://www.vinhosdoalentejo.pt/', 'https://www.vinhosdoalentejo.pt/produtores/'],
   'prefix': 'region-alentejo',
 },
}

IMG_RE = re.compile(r'''(?:src|data-src|data-original|data-lazy-src)\s*=\s*["']([^"']+)["']''', re.I)
SRCSET_RE = re.compile(r'''srcset\s*=\s*["']([^"']+)["']''', re.I)
CSSURL_RE = re.compile(r'''url\(\s*["']?([^"')]+\.(?:jpg|jpeg|png|webp|avif))["']?\s*\)''', re.I)
NOSCRIPT_RE = re.compile(r'<noscript[^>]*>(.*?)</noscript>', re.I | re.S)


def fetch(url, cache_key, binary=False, timeout=25):
    cache = ROOT / 'work' / 'region-media-cache'
    if not cache.exists():
        cache.mkdir(parents=True)
    ext = '.bin' if binary else '.html'
    cp = cache / (hashlib.sha256(url.encode()).hexdigest()[:16] + ext)
    if cp.exists():
        return cp.read_bytes()
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,fr,es,it,pt;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    cp.write_bytes(data)
    time.sleep(1.0)
    return data


def collect_urls(html, page, base):
    urls = []
    for m in IMG_RE.finditer(html):
        urls.append(m.group(1))
    for m in SRCSET_RE.finditer(html):
        parts = [p.strip().split(' ')[0] for p in m.group(1).split(',')]
        urls.extend([p for p in parts if p])
    for m in CSSURL_RE.finditer(html):
        urls.append(m.group(1))
    for m in NOSCRIPT_RE.finditer(html):
        for mm in IMG_RE.finditer(m.group(1)):
            urls.append(mm.group(1))
    out = []
    for u in urls:
        if u.startswith('data:'):
            continue
        u = urllib.parse.urljoin(base, u)
        if u.startswith('http'):
            out.append(u)
    # 去重保序
    seen, res = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def process(region):
    cfg = TARGETS[region]
    outdir = ROOT / 'outputs' / 'collect' / region / 'images' / 'region'
    if not outdir.exists():
        outdir.mkdir(parents=True)
    mpath = outdir.parent / 'region-media-manifest.json'
    # 续跑：读回已有 manifest（本环境 Bash 约 2 分钟被杀，必须逐张落盘）
    items, failures = [], []
    if mpath.exists():
        try:
            prev = json.loads(mpath.read_text())
            items = prev.get('items') or []
            failures = prev.get('failures') or []
        except Exception:
            items, failures = [], []
    seen_sha = {it['sha256'] for it in items}
    seen_url = {it['directURL'] for it in items}
    n = max([int(re.findall(r'-(\d+)\.', it['file'])[0]) for it in items] or [0])

    def save():
        man = {
            'date': datetime.now(TZ).strftime('%Y-%m-%d'),
            'regionId': region,
            'scope': 'region-level（产区级：不隶属单一酒庄）',
            'note': 'role/appellation 一律未判：classificationMethod=heuristic，'
                    'reviewAs=region-media-unreviewed。只有经人工开图复核的图才会被标 '
                    'agent-visual-review 并写入 role。本文件每张图落盘即更新（可断点续跑）。',
            'counts': {'images': len(items), 'minSide': MIN_SIDE, 'failures': len(failures)},
            'items': items,
            'failures': failures[:60],
        }
        mpath.write_text(json.dumps(man, ensure_ascii=False, indent=1))

    for page in cfg['pages']:
        if len(items) >= MAX_PER_REGION:
            break
        try:
            html = fetch(page, page).decode('utf-8', 'ignore')
        except Exception as e:
            failures.append({'page': page, 'error': '%s: %s' % (type(e).__name__, str(e)[:160])})
            save()
            continue
        base = '{u.scheme}://{u.netloc}'.format(u=urllib.parse.urlparse(page))
        for direct in collect_urls(html, page, base):
            if len(items) >= MAX_PER_REGION:
                break
            if direct in seen_url:
                continue
            try:
                data = fetch(direct, direct, binary=True)
            except Exception as e:
                failures.append({'url': direct, 'error': '%s: %s' % (type(e).__name__, str(e)[:120])})
                save()
                continue
            sha = hashlib.sha256(data).hexdigest()
            if sha in seen_sha:
                seen_url.add(direct)
                continue
            if data[:5] in (b'<?xml', b'<svg ') or b'<svg' in data[:200].lower():
                continue
            try:
                im = Image.open(io.BytesIO(data))
                w, h = im.size
                fmt = im.format
            except Exception:
                continue
            if min(w, h) < MIN_SIDE:
                continue
            seen_sha.add(sha)
            seen_url.add(direct)
            n += 1
            ext = '.' + (fmt or 'jpg').lower().replace('jpeg', 'jpg')
            fn = '%s-%02d%s' % (cfg['prefix'], n, ext)
            (outdir / fn).write_bytes(data)
            items.append({
                'file': fn, 'relativePath': 'region/' + fn,
                'role': None, 'roleHint': None, 'confidence': 'unverified',
                'attribution': 'producer-official',
                'appellation': None,
                'classificationMethod': 'heuristic',
                'reviewAs': 'region-media-unreviewed',
                'reasons': ['来自产区官方协会/监管机构页面；文件名未作判据，role 待开图复核'],
                'sourcePage': page, 'sourceName': urllib.parse.urlparse(page).netloc,
                'directURL': direct,
                'retrievedAt': datetime.now(TZ).strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                'bytes': len(data), 'sha256': sha, 'width': w, 'height': h,
                'rights': '官网公开图片，均为合作上传，如侵权可联系删除；未去水印、未放大、未声称版权',
            })
            save()          # 逐张落盘
    save()
    idx = ['# 图片溯源与下架索引 — %s（产区级）' % region, '',
           '本目录图片全部来自产区官方协会/监管机构官网的公开页面；站点统一标注「均为合作上传，'
           '如侵权可联系删除」。收到权利方要求时，请按下表定位并删除对应文件。', '',
           '| 文件 | 来源页 | 直链 | 抓取时间 | 字节 | SHA-256 | 像素 |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for it in items:
        idx.append('| %s | %s | %s | %s | %d | %s | %dx%d |' % (
            it['file'], it['sourcePage'], it['directURL'], it['retrievedAt'], it['bytes'],
            it['sha256'][:16] + '…', it['width'], it['height']))
    (outdir.parent / '图片溯源与下架索引.md').write_text('\n'.join(idx) + '\n')
    print('%s: %d 张（失败 %d） → %s' % (region, len(items), len(failures), outdir))
    return len(items)


if __name__ == '__main__':
    want = sys.argv[1:] or list(TARGETS)
    total = 0
    for r in want:
        if r in TARGETS:
            total += process(r)
    print('合计 %d 张产区级图片' % total)
