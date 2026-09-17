# coding: utf-8
"""Curl-based fallback collector for producer sites the stdlib fetcher cannot reach
(sandbox network policy resets python-urllib TLS on some hosts while curl works).

Collects up to MAX_PER_SITE images per producer (people/estate + wine), writes them
into outputs/collect/cornas/images/<slug>/ and appends manifest entries with the same
traceability fields as collect-wine-images.py (source page, direct URL, retrievedAt,
bytes, sha256, real dimensions). Classification is heuristic-only; images enter the
same visual-review queue as the rest of the bundle.

Usage: python3 scripts/collect-cornas-curl-images.py
"""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image
import io

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'cornas' / 'images'
MANIFEST = OUT / 'wine-image-manifest.json'
RUN_DATE = '2026-09-17'
MAX_PER_SITE = 26
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')

PRODUCERS = [
    {'slug': 'pilon-julien', 'name': 'PILON JULIEN',
     'wineryId': 'winery-cornas-pilon-julien', 'website': 'https://www.julienpilon.fr'},
    {'slug': 'gaec-du-lautaret', 'name': 'GAEC DU LAUTARET, Durand Eric et Joel',
     'wineryId': 'winery-cornas-gaec-du-lautaret-durand-eric-et-joel',
     'website': 'https://www.domaine-durand.fr'},
    {'slug': 'domaine-denuziere', 'name': 'Domaine Denuziere',
     'wineryId': 'winery-cornas-domaine-denuziere', 'website': 'https://www.jdenuziere.fr'},
]

RIGHTS = ('来源酒庄官网公开图片；未标注许可。按站点方 2026-09-13 决定：官网图片可下载使用，'
          '站点内容将标注“均为合作上传，如侵权可联系删除”。')

WINE_HINT = re.compile(
    r'bouteil|bottle|packshot|etiquet|label|magnum|flacon|coffret|millesim|vin|vins|'
    r'cuvee|gamme|boutique|nos|syrah|marsanne|roussanne|viognier|cornas|condrieu|'
    r'saint|st-|crozes|cote|hermitage|igp|rouge|blanc', re.I)
IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
CSS_BG = re.compile(r'url\((["\']?)([^)"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^)"\']*)?)\1\)', re.I)


def curl(url, referer=None, binary=False):
    cmd = ['curl', '-sL', '--max-time', '25', '-A', UA]
    if referer:
        cmd += ['-e', referer]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, timeout=40)
    if r.returncode != 0 or not r.stdout:
        return None
    return r.stdout if binary else r.stdout.decode('utf-8', 'replace')


def clean_url(u, base):
    u = urljoin(base, u.strip())
    if u.startswith('//'):
        u = 'https:' + u
    if u.startswith('data:'):
        return None
    return u


def dims(raw):
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        alpha = im.mode in ('RGBA', 'LA', 'PA') or (
            im.mode == 'P' and 'transparency' in im.info)
        return w, h, alpha
    except Exception:
        return None, None, False


def collect(item):
    slug, site = item['slug'], item['website']
    ddir = OUT / slug
    ddir.mkdir(parents=True, exist_ok=True)
    failures = []
    pages = {'/': site}
    home = curl(site)
    if not home:
        failures.append({'url': site, 'error': 'curl fetch failed'})
    else:
        for m in re.finditer(r'href=["\']([^"\']+)["\']', home):
            u = clean_url(m.group(1), site)
            if not u or urlparse(u).netloc != urlparse(site).netloc:
                continue
            path = urlparse(u).path.lower()
            if WINE_HINT.search(path) and u not in pages and len(pages) < 9:
                pages[u] = u
    cands, seen = [], set()
    for page_url in list(pages.values())[:9]:
        html = home if page_url == site else curl(page_url, referer=site)
        if not html:
            continue
        for m in IMG_SRC.finditer(html):
            u = clean_url(m.group(1), page_url)
            if u and re.search(r'\.(jpe?g|png|webp)(\?|$)', u, re.I):
                cands.append(u)
        for m in CSS_BG.finditer(html):
            u = clean_url(m.group(2), page_url)
            if u:
                cands.append(u)
    ordered = []
    for u in cands:
        key = re.sub(r'-\d{2,4}x\d{2,4}(?=\.)', '', u.lower())
        if key not in seen:
            seen.add(key)
            ordered.append(u)

    manifest = json.loads(MANIFEST.read_text())
    entry = None
    for e in manifest['producers']:
        if e['slug'] == slug:
            entry = e
            break
    if entry is None:
        entry = {'slug': slug, 'name': item['name'], 'wineryId': item['wineryId'],
                 'website': site, 'images': [], 'failures': failures,
                 'pagesVisited': list(pages.values())}
        manifest['producers'].append(entry)
    else:
        entry.setdefault('images', [])
        entry['failures'] = (entry.get('failures') or []) + failures
        entry['pagesVisited'] = sorted(set((entry.get('pagesVisited') or []) + list(pages.values())))

    got = 0
    for u in ordered:
        if got >= MAX_PER_SITE:
            break
        raw = curl(u, referer=site, binary=True)
        if not raw or len(raw) < 6000:
            continue
        w, h, alpha = dims(raw)
        if not w or min(w, h) < 250:
            continue
        name = re.sub(r'[^A-Za-z0-9._-]', '_', Path(urlparse(u).path).name)
        target = ddir / ('%02d-%s' % (len(entry['images']) + 1, name))
        target.write_bytes(raw)
        hint = WINE_HINT.search(u)
        role = 'wine-bottle' if (hint and (alpha or h / w > 1.4)) else (
            'wine-photo' if hint else 'producer-site')
        entry['images'].append({
            'file': target.name,
            'relativePath': str(target.relative_to(OUT)),
            'role': role, 'confidence': 'low', 'attribution': 'unverified',
            'appellation': None, 'reviewAs': 'possible-wine',
            'classificationMethod': 'heuristic',
            'reasons': ['curl 备用通道采集（主采集器网络重置）', '启发式初判，待人工视觉复核'],
            'altText': None, 'sourceName': '酒庄官网 ' + urlparse(site).netloc,
            'sourcePage': site, 'directURL': u, 'width': w, 'height': h,
            'aspect': round(h / w, 2), 'hasAlpha': alpha, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'retrievedAt': RUN_DATE,
            'rights': RIGHTS, 'watermark': '未去水印；未放大；仅原尺寸保存'})
        got += 1
        time.sleep(0.3)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    print('%-22s images_now=%d new=%d pages=%d failures=%d'
          % (slug, len(entry['images']), got, len(pages), len(failures)))


for item in PRODUCERS:
    try:
        collect(item)
    except Exception as err:  # noqa: BLE001
        print('%-22s ERROR %s' % (item['slug'], err))
