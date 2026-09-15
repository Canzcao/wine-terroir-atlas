# coding: utf-8
"""Parse the official AOC Saint-Joseph producer directory (aoc-saint-joseph.fr).

The listing is a single static page (no per-producer profile pages, no images):
repeated <div class="vigneron vigneronN"> blocks holding
  <h2 class="h22">NAME</h2>
  <p class="coords"> ADDRESS<br>POSTAL COMMUNE<br>Tél : ...<br>Mail : <a>..</a>
                    <br>Web : <a href="..">..</a> </p>
The site's own baseline is "190 metteurs en marché"; the page lists 182 blocks.

Output: outputs/daily/2026-09-14/saint-joseph-官方名录-2026-09-14.json
        work/saint-joseph-geo-input.json  (for collect-producer-geo.py)

Usage: python3 scripts/parse-saint-joseph-directory.py
"""
import json
import re
import unicodedata
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-14'
SRC = ROOT / 'work' / 'saint-joseph' / 'directory-raw.html'
OUT_DIR = ROOT / 'outputs' / 'daily' / DATE
OUT_DIR.mkdir(parents=True, exist_ok=True)
LISTING_URL = 'https://www.aoc-saint-joseph.fr/producteurs-saint-joseph.html'

# 26 communes of the AOC (Ardèche + Loire), lower-cased, accent-stripped for lookup.
KNOWN_COMMUNES = {
    'andance', 'annonay', 'arlebosc', 'ardesche', 'bozas', 'bogy', 'boucieu-le-roi',
    'champagne', 'charnas', 'cheminas', 'colombier-le-cardinal', 'colombier-le-jeune',
    'etables', 'felines', 'gilhoc-sur-ormeze', 'glun', 'lamastre', 'le-crest',
    'lemps', 'limony', 'mauves', 'nozieres', 'ose, rhone', 'peyraud', 'saint-jean-de-muzols',
    'saint-peray', 'sarras', 'savas', 'serrieres', 'toulaud', 'tournon-sur-rhone',
    'veaunes', 'vion', 'chateaubourg', 'saint-barthelemy-le-plain', 'saint-victor',
    'malleval', 'sales', 'saint-pierre-de-boeuf', 'verin', 'chavanay', 'saint-michel-sur-rhone',
    'ampuis', 'tain-l-hermitage', 'lemps',
}


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


def strip_tags(s: str) -> str:
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def norm_commune(s: str) -> str:
    t = unicodedata.normalize('NFKD', s)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', t.lower()).strip()


def main():
    html = SRC.read_text(encoding='utf-8')
    blocks = re.findall(r'<div class="vigneron[^"]*">([\s\S]*?)</div>', html)

    producers, seen = [], set()
    for b in blocks:
        h2 = re.search(r'<h2 class="h22">([\s\S]*?)</h2>', b)
        if not h2:
            continue
        name = strip_tags(h2.group(1))
        if not name:
            continue
        slug = slugify(name)
        if slug in seen:          # the site repeats a few blocks verbatim
            continue
        seen.add(slug)

        coord = re.search(r'<p class="coords">([\s\S]*?)</p>', b)
        raw = coord.group(1) if coord else ''
        # keep <br> as line breaks so we can split address / phone / mail / web
        text = unescape(re.sub(r'<br\s*/?>', '\n', raw))
        text = unescape(re.sub(r'<[^>]+>', ' ', text))
        lines = [re.sub(r'[ \t]+', ' ', l).strip() for l in text.split('\n')]
        lines = [l for l in lines if l]

        website = email = phone = None
        addr_lines = []
        for l in lines:
            low = l.lower()
            if low.startswith('web'):
                m = re.search(r'https?://\S+', l)
                if m:
                    website = m.group(0).rstrip('/').rstrip('.')
                continue
            if low.startswith('mail'):
                m = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', l)
                if m:
                    email = m.group(0)
                continue
            if low.startswith('tél') or low.startswith('tel') or low.startswith('tèl'):
                m = re.search(r'(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}', l)
                if m:
                    phone = re.sub(r'\s+', ' ', m.group(0))
                continue
            addr_lines.append(l)

        # mailto/web anchors sometimes live inside the last address line
        if not email:
            m = re.search(r'mailto:([\w.+-]+@[\w-]+\.[\w.-]+)', raw)
            if m:
                email = m.group(1)
        if not website:
            m = re.search(r'<a[^>]+href="(https?://[^"]+)"', raw)
            if m:
                website = m.group(1).rstrip('/')
        if not phone:
            m = re.search(r'(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}', strip_tags(raw))
            if m:
                phone = re.sub(r'\s+', ' ', m.group(0))

        address = ' / '.join(addr_lines) or None
        # postal code + commune, e.g. "07610 Lemps"
        postal = commune = None
        m = re.search(r'\b(\d{5})\s+([A-Za-zÀ-ÿ\-\'’ ]{2,40})', address or '')
        if m:
            postal = m.group(1)
            commune = m.group(2).strip(' -')
        producers.append({
            'name': name,
            'address': address,
            'postalCode': postal,
            'commune': commune,
            'phone': phone,
            'email': email,
            'website': website,
            'directoryURL': LISTING_URL,
        })

    # same-name-different-spelling audit (recorded, never silently merged)
    by_key = {}
    for p in producers:
        k = re.sub(r'[^a-z]', '', slugify(p['name']))
        by_key.setdefault(k, []).append(p['name'])
    variants = {k: v for k, v in by_key.items() if len(v) > 1}

    in_window = [p for p in producers
                 if p['commune'] and norm_commune(p['commune']).replace(' ', '')
                 in {norm_commune(c).replace(' ', '') for c in KNOWN_COMMUNES}]

    (OUT_DIR / 'saint-joseph-官方名录-2026-09-14.json').write_text(json.dumps({
        'date': DATE,
        'source': 'AOC Saint-Joseph · Liste des producteurs par ordre alphabétique',
        'sourceURL': LISTING_URL,
        'checkedDate': DATE,
        'sourceLanguage': 'fr',
        'officialBaseline': ('协会官网首页写“190 metteurs en marché”；'
                             '本页按字母序列出生产者（含酒庄与酒商）182 条。'),
        'notes': '官方名录单页列表，无逐家详情页与图片；每家为名称/地址/电话/邮箱/官网。'
                 '名录混含酒商（maisons/négociants）与产区外登记地址，照录不删；'
                 '通讯地址不等于葡萄园所在地，坐标一律另经 OSM 判定。',
        'producers': producers,
    }, ensure_ascii=False, indent=1) + '\n')

    geo_input = [{'id': 'saint-joseph-' + slugify(p['name']), 'name': p['name'],
                  'country': 'France'} for p in producers]
    (ROOT / 'work' / 'saint-joseph-geo-input.json').write_text(
        json.dumps(geo_input, ensure_ascii=False, indent=1) + '\n')

    print('producers:', len(producers))
    print('with website:', sum(1 for p in producers if p['website']))
    print('with email:', sum(1 for p in producers if p['email']))
    print('with phone:', sum(1 for p in producers if p['phone']))
    print('with postal code:', sum(1 for p in producers if p['postalCode']))
    print('commune inside 26-commune window:', len(in_window))
    print('possible same-name variants:', variants)


if __name__ == '__main__':
    main()
