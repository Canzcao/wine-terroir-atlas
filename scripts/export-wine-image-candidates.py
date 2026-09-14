# coding: utf-8
"""Turn the raw image manifest into the two things downstream actually needs.

1. `wine-images.json` — for every estate, its collected pictures split into
   "people and place" and "wines", with the appellation read off each bottle.
   The content conversation consumes this to write region explainers; it is a
   source list, not prose.
2. Concrete attachment of `own-wine` Condrieu images to the catalogue's `wine`
   records where such a record already exists (`data.images`), so the Site can
   render them at the winery's pin. Where no wine record exists yet the image
   stays a candidate with a suggested cuvée name instead of being invented.

Usage:
  python3 scripts/export-wine-image-candidates.py <manifest.json> <outdir> [--write-catalog]
"""
import json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_APPELLATION = 'Condrieu'


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', (s or '').lower())


def suggest_name(slug, g):
    """A readable label for a bottle image, taken only from real evidence."""
    url = g['directURL']
    fname = Path(url.split('?')[0]).name
    stem = re.sub(r'\.(jpe?g|png|webp|avif)$', '', fname, flags=re.I)
    stem = re.sub(r'^\d+-', '', stem)
    stem = re.sub(r'-(scaled|\d+x\d+)$', '', stem, flags=re.I)
    stem = re.sub(r'[_]+', ' ', stem).strip()
    if g.get('altText') and len(g['altText']) > 2 and g['altText'].lower() != slug:
        return g['altText'][:70]
    return stem[:70]


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text())
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    # The manifest may have been collected before the association's listing-page
    # names were corrected against each profile page's own h1, so reconcile.
    if '--fix-names' in sys.argv:
        pf = Path(sys.argv[sys.argv.index('--fix-names') + 1])
        if pf.exists():
            by_slug = {p['slug']: p for p in json.loads(pf.read_text())}
            fixed = 0
            for e in manifest.get('producers') or []:
                p = by_slug.get(e['slug'])
                if p and p.get('name') and p['name'] != e.get('name'):
                    e['nameFromListing'] = e.get('name')
                    e['name'] = p['name']
                    fixed += 1
            print('names reconciled: %d' % fixed)
            if fixed:
                Path(sys.argv[1]).write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')

    by_winery = []
    for e in manifest.get('producers') or []:
        imgs = e.get('images') or []
        people = [g for g in imgs if g['role'] in
                  ('producer-people', 'producer-estate', 'producer-site')]
        wines = [g for g in imgs if g['role'] in ('wine-bottle', 'wine-label')]
        scenes = [g for g in imgs if g['role'] == 'wine-photo']
        if not imgs:
            continue

        def pack(g):
            return {
                'file': g['file'], 'relativePath': g['relativePath'],
                'role': g['role'], 'confidence': g['confidence'],
                'attribution': g.get('attribution'),
                'appellation': g.get('appellation'),
                'suggestedName': suggest_name(e['slug'], g),
                'width': g['width'], 'height': g['height'],
                'sourceName': g.get('sourceName'), 'sourcePage': g['sourcePage'],
                'directURL': g['directURL'], 'sha256': g['sha256'],
                'rights': g['rights'],
                'classificationMethod': g.get('classificationMethod'),
                'reasons': g.get('reasons'),
                'reviewNote': g.get('reviewNote'),
            }

        condrieu = [g for g in wines if (g.get('appellation') or TARGET_APPELLATION) == TARGET_APPELLATION]
        other = [g for g in wines if (g.get('appellation') or TARGET_APPELLATION) != TARGET_APPELLATION]
        by_winery.append({
            'slug': e['slug'], 'name': e['name'],
            'wineryId': e.get('wineryId'), 'website': e.get('websiteLive') or e.get('website'),
            'note': e.get('note'),
            'counts': {'peopleAndPlace': len(people), 'wineCondrieu': len(condrieu),
                       'wineOtherAppellation': len(other), 'wineSceneStock': len(scenes)},
            'peopleAndPlace': [pack(g) for g in people],
            'wineCondrieu': [pack(g) for g in condrieu],
            'wineOtherAppellation': [pack(g) for g in other],
            'wineSceneStock': [pack(g) for g in scenes],
            'failures': (e.get('failures') or [])[:8],
        })

    by_winery.sort(key=lambda w: (-w['counts']['wineCondrieu'], -w['counts']['peopleAndPlace']))
    totals = {
        'producers': len(by_winery),
        'peopleAndPlace': sum(w['counts']['peopleAndPlace'] for w in by_winery),
        'wineCondrieu': sum(w['counts']['wineCondrieu'] for w in by_winery),
        'wineOtherAppellation': sum(w['counts']['wineOtherAppellation'] for w in by_winery),
        'wineSceneStock': sum(w['counts']['wineSceneStock'] for w in by_winery),
        'withWebsite': sum(1 for w in by_winery if w['website']),
    }
    (outdir / 'wine-images.json').write_text(json.dumps({
        'date': manifest.get('date', '2026-09-13'),
        'region': 'Condrieu',
        'purpose': ('供网页与图文使用的图片来源清单：人物/风土图 + 酒庄出产的酒图。'
                    '本文件是素材索引，不是成稿内容。'),
        'rules': {
            'targetAppellation': TARGET_APPELLATION,
            'appellationSource': '以瓶身/文件名证据判定；未判定者不计入目标产区酒款',
            'classificationMethod': ('heuristic 为文件名与页面语境推断；'
                                     'agent-visual-review 为看过图后的核判'),
            'rights': '官网公开图片；未标注许可。站点内容标注“均为合作上传，如侵权可联系删除”。',
        },
        'totals': totals,
        'producers': by_winery,
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- attach to catalogue wine records that already exist
    catalog_path = ROOT / 'data' / 'catalog-seed.json'
    catalog = json.loads(catalog_path.read_text())
    records = catalog if isinstance(catalog, list) else catalog.get('records', [])
    wines = {r['id']: r for r in records if r.get('kind') == 'wine'}
    attached = defaultdict(list)
    for w in by_winery:
        wid = w.get('wineryId')
        if not wid:
            continue
        for r in wines.values():
            if r.get('data', {}).get('wineryId') != wid:
                continue
            for g in w['wineCondrieu']:
                if g['attribution'] not in ('own-wine', 'likely-own'):
                    continue
                attached[r['id']].append({
                    'relativePath': g['relativePath'], 'role': g['role'],
                    'appellation': g['appellation'], 'confidence': g['confidence'],
                    'attribution': g['attribution'],
                    'classificationMethod': g['classificationMethod'],
                    'sourcePage': g['sourcePage'], 'directURL': g['directURL'],
                    'rights': g['rights'],
                })

    report = {'wineRecordsMatched': len(attached),
              'imagesAttached': sum(len(v) for v in attached.values()),
              'wineRecordsWithoutImage': [r['id'] for r in wines.values()
                                          if r['id'] not in attached]}
    if '--write-catalog' in sys.argv:
        for wid, imgs in attached.items():
            r = wines[wid]
            data = r.setdefault('data', {})
            existing = {i.get('directURL') for i in (data.get('images') or [])}
            data['images'] = (data.get('images') or []) + \
                [i for i in imgs if i['directURL'] not in existing]
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + '\n')
        report['catalogWritten'] = True

    (outdir / 'wine-image-attach-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n')

    print('producers with images : %d' % totals['producers'])
    print('people/place images   : %d' % totals['peopleAndPlace'])
    print('wine images (Condrieu): %d' % totals['wineCondrieu'])
    print('wine images (其他产区) : %d' % totals['wineOtherAppellation'])
    print('stock wine scenes     : %d' % totals['wineSceneStock'])
    print('wine records matched  : %d (%d images)'
          % (report['wineRecordsMatched'], report['imagesAttached']))
    print('catalog written       : %s' % report.get('catalogWritten', False))


if __name__ == '__main__':
    main()
