# coding: utf-8
"""Collect region-level imagery for Cornas from the appellation's own site.

The AOC Cornas site (aoc-cornas.fr) has no per-producer photos, but its
terroir / history / journal pages carry region imagery (slopes, stone walls,
harvest, events). Per-winery photos come later from collect-wine-images.py.

Usage: python3 scripts/collect-cornas-region-media.py <outdir>
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
# 协会官网只提供小图（terroir/aoc 图示 260–600px，无更大原图），因此门槛放宽到 240；
# 站点展示时按原始像素呈现，不用放大的图。
MIN_SIDE = 240

PAGES = [
    ('terroir', 'https://www.aoc-cornas.fr/terroir.html'),
    ('aoc', 'https://www.aoc-cornas.fr/aoc-cornas.html'),
    ('histoire', 'https://www.aoc-cornas.fr/histoire.html'),
    ('journal', 'https://www.aoc-cornas.fr/journal.html'),
    ('ac-unesco', 'https://www.aoc-cornas.fr/actualite-en-route-pour-lunesco-_21.html'),
    ('ac-lyon', 'https://www.aoc-cornas.fr/actualite-degustation-professionnelle-lyon_20.html'),
    ('ac-vignobles-en-scene',
     'https://www.aoc-cornas.fr/actualite-vignobles-en-scene-18-et-19-octobre-2025_19.html'),
    ('ac-journee-technique',
     'https://www.aoc-cornas.fr/actualite-retour-sur-la-journee-technique-des-vignerons-de-cornas--saint-peray_17.html'),
    ('ac-80ans', 'https://www.aoc-cornas.fr/actualite-80-ans-de-laoc--porter-haut-les-couleurs-de-cornas-_4.html'),
]

BUCKETS = [
    ('region-harvest', ('vendange', 'grappe', 'raisin', 'panier', 'pressoir', 'recolte')),
    ('region-vinework', ('taille', 'travail', 'palissage', 'effeuillage', 'liage',
                         'chai', 'cave', 'barrique', 'foudre')),
    ('region-weather', ('neige', 'gel', 'grele', 'orage', 'brume', 'pluie')),
    ('region-tasting', ('degustation', 'verre', 'sommelier', 'marche', 'salon',
                        'table', 'bouteille', 'masterclass', 'plaza')),
    ('region-landscape', ('coteau', 'paysage', 'panorama', 'vigne', 'granit',
                          'terrasse', 'rhone', 'fleuve', 'murette', 'sol', 'vallon')),
    ('region-grape', ('syrah', 'baie', 'maturite')),
    ('region-people', ('vigneron', 'portrait', 'equipe', 'famille', 'main', 'president')),
]

NEGATIVE = cwi.NEGATIVE_TOKENS | {'logo', 'favicon', 'burger', 'placeholder',
                                  'icone-prod', 'instagram', 'removebg', 'sprite'}


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
    for key, url in PAGES:
        page = PAGE_CACHE / ('cornas-' + key + '.html')
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
            if 'aoc-cornas.fr/upload' not in u:
                continue
            if any(n in urlparse(u).path.lower() for n in NEGATIVE):
                continue
            if u in seen:
                continue
            seen.add(u)
            cands.append((u, alt, url))
        # 官网把成组的图示放在生成的 CSS 里（url(/upload/...)），只扫 <img> 会漏掉整组
        for m in re.finditer(r'url\((["\']?)(/upload/[^)"\']+\.(?:jpe?g|png|webp|avif))\1\)',
                             html, re.I):
            rel = m.group(2)
            if any(n in rel.lower() for n in NEGATIVE):
                continue
            u = 'https://www.aoc-cornas.fr' + rel
            if u in seen:
                continue
            seen.add(u)
            cands.append((u, None, url))
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
                'sourcePage': src, 'directURL': u,
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'width': w, 'height': h, 'hasAlpha': alpha,
                'classificationMethod': 'heuristic-filename',
            })
            got += 1
            print('  %-22s %-46s %dx%d' % (role, name, w, h), flush=True)
            time.sleep(0.3)
        print('%s: %d images' % (key, got), flush=True)

    (outdir / 'region-media-manifest.json').write_text(
        json.dumps({'date': '2026-09-14', 'regionId': 'cornas',
                    'source': 'AOC Cornas 官网页面（terroir / aoc / histoire / journal / 活动页）',
                    'note': '产区级图片，不隶属单一酒庄；官网公开图片，站点标注“均为合作上传，如侵权可联系删除”。',
                    'images': manifest}, ensure_ascii=False, indent=1) + '\n')
    print('total:', len(manifest))


if __name__ == '__main__':
    main()
