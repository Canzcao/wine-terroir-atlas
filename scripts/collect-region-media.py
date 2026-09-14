# coding: utf-8
"""Collect region-level imagery that is not tied to a single estate.

The association's own pages carry the richest picture of what Condrieu looks
like and what is happening there: 126 gallery photos of pruning, tying, soil
work, harvest, drone views, snow, tasting. Per-winery photos come from
collect-wine-images.py; this script covers the region itself, so the Site has
material for the appellation story rather than only producer cards.

Usage: python3 scripts/collect-region-media.py <outdir>
"""
import hashlib, importlib.util, io, json, re, sys, time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]

# reuse the collector's fetch / dimension / token helpers
spec = importlib.util.spec_from_file_location(
    'cwi', str(ROOT / 'scripts' / 'collect-wine-images.py'))
cwi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cwi)

PAGE_CACHE = ROOT / 'work' / 'pagecache'
MIN_SIDE = 400

REGION_PAGES = [
    ('galerie', 'https://vincondrieu.fr/galerie/'),
    ('nos-condrieu', 'https://vincondrieu.fr/nos-condrieu/'),
    ('vignobles', 'https://vincondrieu.fr/vignobles/'),
    ('histoire', 'https://vincondrieu.fr/histoire-2/'),
    ('appellation', 'https://vincondrieu.fr/connaitre-notre-appellation/'),
]

# what the region photos show, so the downstream editor can pick by need
BUCKETS = [
    ('region-harvest', ('vendange', 'grappe', 'raisin', 'brouette', 'piochage',
                        'recolte', 'panier', 'pressoir', 'hotte')),
    ('region-vinework', ('taille', 'liage', 'attachage', 'debourrement', 'printemps',
                         'eclaircissage', 'effeuillage', 'palissage', 'travail')),
    ('region-weather', ('neige', 'gel', 'grele', 'orage', 'pluie', 'brume')),
    ('region-tasting', ('aperitif', 'degustation', 'verre', 'table', 'repas',
                        'bouteille', 'service', 'sommelier', 'caveau')),
    ('region-landscape', ('drone', 'paysage', 'panorama', 'coteau', 'clos', 'cep',
                          'granite', 'granit', 'murette', 'sol', 'chy', 'vue',
                          'cote', 'vallon', 'terrasse', 'fleuve', 'rhone')),
    ('region-grape', ('viognier', 'grappe', 'baie', 'maturite', 'vendange')),
    ('region-people', ('vigneron', 'portrait', 'equipe', 'famille', 'main')),
]

NEGATIVE = cwi.NEGATIVE_TOKENS | {'logo', 'favicon', 'burger', 'placeholder',
                                  'instagram', 'cdninstagram', 'removebg'}


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
    for key, url in REGION_PAGES:
        page = PAGE_CACHE / ('assoc-' + key + '.html')
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
            if 'vin-condrieu.fr/wp-content/uploads' not in u:
                continue
            if any(n in urlparse(u).path.lower() for n in NEGATIVE):
                continue
            base = re.sub(r'-\d{2,4}x\d{2,4}(?=\.)', '', u)
            if base in seen or u in seen:
                continue
            seen.add(base)
            cands.append((base, alt, url))
        got = 0
        for u, alt, src in cands:
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
            name = re.sub(r'[^A-Za-z0-9._-]', '_', Path(urlparse(u).path).name)
            target = outdir / ('%s-%02d-%s' % (role, got + 1, name))
            target.write_bytes(raw)
            manifest.append({
                'file': target.name, 'relativePath': str(target.relative_to(outdir)),
                'role': role, 'matchedKeywords': why, 'altText': alt or None,
                'sourceName': 'Condrieu 产区协会官网',
                'sourcePage': src, 'directURL': u,
                'width': w, 'height': h, 'aspect': round(h / w, 2), 'hasAlpha': alpha,
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'retrievedAt': '2026-09-13',
                'classificationMethod': 'heuristic-filename',
                'rights': ('来源 vin-condrieu.fr 公开页面；未标注许可。按站点方 2026-09-13 决定：'
                           '官网图片可下载使用，站点内容将标注“均为合作上传，如侵权可联系删除”。'),
                'watermark': '未去水印；未放大；仅原尺寸保存',
            })
            got += 1
            time.sleep(0.25)
        print('%-16s %d images' % (key, got), flush=True)

    (outdir / 'region-media-manifest.json').write_text(json.dumps({
        'date': '2026-09-13',
        'note': ('产区级图片，非单一酒庄所有。文件名分类仅供下游编辑按需取用，'
                 '不构成内容断言。'),
        'images': manifest,
    }, ensure_ascii=False, indent=1) + '\n')
    from collections import Counter
    print('\ntotal %d region images' % len(manifest))
    print(dict(Counter(i['role'] for i in manifest)))


if __name__ == '__main__':
    main()
