# coding: utf-8
"""Collect region-level imagery for Saint-Joseph from the appellation's own site.

aoc-saint-joseph.fr publishes no per-producer photos, but its terroir / cepage /
millésime / photothèque pages carry region imagery (terraced slopes, granite
soils, harvest, the Rhône, cuisine pairings). Per-winery photos come separately
from collect-wine-images.py.

Site asset roots: /lib/picts/** (large photos) and /imgs/** (page banners).

Usage: python3 scripts/collect-saint-joseph-region-media.py <outdir>
"""
import hashlib
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'cwi', str(ROOT / 'scripts' / 'collect-wine-images.py'))
cwi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cwi)

PAGE_CACHE = ROOT / 'work' / 'pagecache'
BASE = 'https://www.aoc-saint-joseph.fr'
# 协会官网多为小图（260–600px），门槛放宽到 240；展示时按原始像素，不做放大。
MIN_SIDE = 240

PAGES = [
    ('home', '/'),
    ('terroir', '/terroir-saint-joseph.html'),
    ('vin', '/vin-saint-joseph.html'),
    ('cepages', '/syrah-marsanne-roussanne.html'),
    ('degustation', '/millesime-saint-joseph.html'),
    ('hommes', '/cave-domaine-saint-joseph.html'),
    ('phototheque', '/phototheque.aspx'),
    ('cuisine', '/conseils-cuisine-saint-joseph.html'),
    ('accords', '/saint-joseph-regale-partout.html'),
    ('magazines', '/magazines-aoc-saint-joseph.html'),
]

BUCKETS = [
    ('region-harvest', ('vendange', 'grappe', 'raisin', 'panier', 'pressoir', 'recolte')),
    ('region-vinework', ('taille', 'travail', 'palissage', 'effeuillage', 'liage',
                         'chai', 'cave', 'barrique', 'foudre', 'echalas', 'muret')),
    ('region-weather', ('neige', 'gel', 'grele', 'orage', 'brume', 'pluie')),
    ('region-tasting', ('degustation', 'verre', 'sommelier', 'table', 'bouteille',
                        'blanc', 'rouge', 'tartare', 'fromage', 'caillette', 'oeuf',
                        'viande', 'cousina', 'cuisin', 'accord')),
    ('region-landscape', ('coteau', 'paysage', 'panorama', 'vigne', 'granit', 'sol',
                          'terrasse', 'rhone', 'fleuve', 'vallon', 'geograph', 'terroir',
                          'superficie', 'encepagement', 'carte')),
    ('region-grape', ('syrah', 'marsanne', 'roussanne', 'cepage', 'baie', 'maturite')),
    ('region-people', ('vigneron', 'portrait', 'equipe', 'famille', 'main', 'president',
                       'hommes', 'femmes')),
]

NEGATIVE = cwi.NEGATIVE_TOKENS | {'logo', 'favicon', 'burger', 'placeholder',
                                  'picto', 'instagram', 'facebook', 'removebg',
                                  'sprite', 'play', 'capture'}


def bucket_for(tokens, alt):
    hay = ' '.join(tokens) + ' ' + cwi.strip_accents((alt or '').lower())
    for name, kws in BUCKETS:
        if any(k in hay for k in kws):
            return name, [k for k in kws if k in hay][:3]
    return 'region-context', []


def main():
    outdir = Path(sys.argv[1])
    outdir.mkdir(parents=True, exist_ok=True)
    manifest, seen = [], set()
    for key, path in PAGES:
        url = BASE + path
        page = PAGE_CACHE / ('saint-joseph-' + key + '.html')
        if not page.exists():
            try:
                html = cwi._read(url).decode('utf-8', 'ignore')
                page.write_text(html, encoding='utf-8')
                time.sleep(2)
            except Exception as err:  # noqa: BLE001
                print('x %s %s' % (url, err), flush=True)
                continue
        html = page.read_text(encoding='utf-8', errors='ignore')
        cands = []
        for u, alt in cwi.page_images(html, url):
            cands.append((u, alt, url))
        # 官网把成组图示放在生成 CSS 里（url(/lib/picts/...)），只扫 <img> 会漏掉整组
        for m in re.finditer(r'url\((["\']?)((?:\.\./)?/?(?:lib/)?picts/[^)"\']+'
                             r'\.(?:jpe?g|png|webp|avif))\1\)', html, re.I):
            rel = m.group(2)
            u = (BASE + '/' + rel.lstrip('./')) if rel.startswith('..') else \
                (BASE + '/' + rel.lstrip('/'))
            cands.append((u, None, url))
        for u, alt, src in cands:
            if not (u.startswith(BASE + '/lib/picts') or u.startswith(BASE + '/imgs')
                    or u.startswith(BASE + '/picts')):
                continue
            low = urlparse(u).path.lower()
            if any(n in low for n in NEGATIVE) or low.endswith(('.svg', '.gif')):
                continue
            if u in seen:
                continue
            seen.add(u)
            try:
                raw = cwi.fetch_bytes(u)
            except Exception:  # noqa: BLE001
                continue
            if len(raw) < 12000:
                continue
            try:
                w, h, alpha = cwi.dimensions_and_alpha(raw)
            except Exception:  # noqa: BLE001
                continue
            if not w or min(w, h) < MIN_SIDE:
                continue
            tokens = cwi.tokenize(urlparse(u).path)
            role, why = bucket_for(tokens, alt)
            name = urlparse(u).path.rsplit('/', 1)[-1]
            dest = outdir / role / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            manifest.append({
                'file': '%s/%s' % (role, name),
                'role': role,
                'matchedKeywords': why,
                'alt': alt,
                'sourcePage': src,
                'directURL': u,
                'bytes': len(raw),
                'width': w,
                'height': h,
                'alpha': alpha,
                'sha256': hashlib.sha256(raw).hexdigest(),
                'retrievedAt': time.strftime('%Y-%m-%d'),
                'rights': '协会官网公开图片；站点口径「均为合作上传，如侵权可联系删除」。',
            })
            print('  + %-22s %s (%dx%d)' % (role, name[:52], w, h), flush=True)
            time.sleep(0.3)

    (outdir / 'region-media-manifest.json').write_text(json.dumps({
        'date': '2026-09-14',
        'region': 'Saint-Joseph AOC',
        'source': 'aoc-saint-joseph.fr',
        'checkedDate': '2026-09-14',
        'images': manifest,
    }, ensure_ascii=False, indent=1) + '\n')
    from collections import Counter
    print('\nregion images=%d  buckets=%s'
          % (len(manifest), dict(Counter(m['role'] for m in manifest))))


if __name__ == '__main__':
    main()
