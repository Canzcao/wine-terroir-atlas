# coding: utf-8
"""Collect region-level imagery for Crozes-Hermitage from the appellation's own site.

crozes-hermitage-vin.fr ships no per-producer photo library, but its
Vignoble & Vin pages (terroir / vin / histoire / biodiversité) and the home page
carry genuine region imagery: rolling vignoble views, granite and galets soils,
grape close-ups, cellar work, the Rhône. Per-winery photos come separately from
collect-wine-images.py.

Asset roots on this site: /images/img-crozes-hermitage/{visuels,slideshow}. The
magazines/ subfolder holds press-magazine covers (publications about the
appellation, not imagery of it) and is deliberately excluded, as are icones/.

Usage: python3 scripts/collect-crozes-hermitage-region-media.py <outdir>
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
BASE = 'https://www.crozes-hermitage-vin.fr'
DATE = '2026-09-15'
# The site's card thumbnails are 501x197 (short side 197); MIN_SIDE 190 admits
# them while still rejecting icons and the 38x38 marker pins.
MIN_SIDE = 190
ASSET_PREFIXES = (BASE + '/images/img-crozes-hermitage/',)

PAGES = [
    ('home', '/fr/'),
    ('vignoble', '/fr/vignoble-et-vin'),
    ('terroir', '/fr/vignoble-et-vin/terroir'),
    ('vin', '/fr/vignoble-et-vin/vin'),
    ('histoire', '/fr/vignoble-et-vin/histoire'),
    ('biodiversite', '/fr/vignoble-et-vin/biodiversite'),
    ('vignerons', '/fr/vignerons'),
]

BUCKETS = [
    ('region-harvest', ('vendange', 'grappe', 'raisin', 'panier', 'pressoir', 'recolte')),
    ('region-vinework', ('taille', 'travail', 'palissage', 'effeuillage', 'liage',
                         'chai', 'cave', 'barrique', 'foudre', 'echalas', 'muret',
                         'main', 'mains')),
    ('region-weather', ('neige', 'gel', 'grele', 'orage', 'brume', 'pluie')),
    ('region-tasting', ('degustation', 'verre', 'sommelier', 'table', 'bouteille',
                        'blanc', 'rouge', 'tablee', 'fromage', 'accord')),
    ('region-landscape', ('coteau', 'paysage', 'panorama', 'vigne', 'vignes', 'vignoble',
                          'granit', 'sol', 'terrasse', 'rhone', 'fleuve', 'vallon',
                          'geograph', 'terroir', 'superficie', 'carte', 'ambiance',
                          'slideshow', 'site', 'couloir')),
    ('region-grape', ('syrah', 'marsanne', 'roussanne', 'cepage', 'baie', 'maturite')),
    ('region-people', ('vigneron', 'portrait', 'equipe', 'famille', 'president',
                       'hommes', 'femmes', 'green')),
]

NEGATIVE = cwi.NEGATIVE_TOKENS | {'logo', 'favicon', 'burger', 'placeholder',
                                  'picto', 'instagram', 'facebook', 'removebg',
                                  'sprite', 'play', 'capture', 'icone', 'pointer',
                                  'filigram', 'vignette'}


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
        page = PAGE_CACHE / ('crozes-hermitage-' + key + '.html')
        if not page.exists():
            try:
                html = cwi._read(url).decode('utf-8', 'ignore')
                page.write_text(html, encoding='utf-8')
                time.sleep(2)
            except Exception as err:  # noqa: BLE001
                print('x %s %s' % (url, err), flush=True)
                continue
        html = page.read_text(encoding='utf-8', errors='ignore')
        cands = list(cwi.page_images(html, url))
        # 该站把成组视觉图放在生成 CSS 的 url(...) 里，只扫 <img> 会漏掉整组。
        for m in re.finditer(r'url\((["\']?)([^)"\']+\.(?:jpe?g|png|webp|avif))\1\)',
                             html, re.I):
            rel = m.group(2)
            if rel.startswith('http'):
                u = rel
            else:
                u = BASE + '/' + rel.lstrip('/')
            cands.append((u, None))

        for u, alt in cands:
            u = re.sub(r'^(https?://[^/]+)//+', r'\1/', u)      # the site emits //images/... twice
            if not any(u.startswith(p) for p in ASSET_PREFIXES):
                continue
            low = urlparse(u).path.lower()
            if any(n in low for n in NEGATIVE) or low.endswith(('.svg', '.gif')):
                continue
            if '/magazines/' in low:
                continue      # press covers, not imagery of the appellation
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
                'sourcePage': url,
                'directURL': u,
                'bytes': len(raw),
                'width': w,
                'height': h,
                'alpha': alpha,
                'sha256': hashlib.sha256(raw).hexdigest(),
                'retrievedAt': DATE,
                'rights': '协会官网公开图片；用于产区资料库，如侵权可联系删除。',
            })
            print('  + %-22s %s (%dx%d)' % (role, name[:56], w, h), flush=True)
            time.sleep(0.3)

    (outdir / 'region-media-manifest.json').write_text(json.dumps({
        'date': DATE,
        'region': 'Crozes-Hermitage AOC',
        'source': 'crozes-hermitage-vin.fr',
        'checkedDate': DATE,
        'note': '仅取 /images/img-crozes-hermitage/{visuels,slideshow} 下的产区视觉图；'
                'magazines/（各国杂志封面）与 icones/ 已排除。'
                '站点既给 1920px 的 slideshow/ambiance 大图，也给 501x197 的板块卡片小图，'
                '两者都保留并在 width/height 里如实记录，展示时按原始像素、不做放大。',
        'images': manifest,
    }, ensure_ascii=False, indent=1) + '\n')
    from collections import Counter
    print('\nregion images=%d  buckets=%s'
          % (len(manifest), dict(Counter(m['role'] for m in manifest))))


if __name__ == '__main__':
    main()
