# coding: utf-8
"""Collect the official Crozes-Hermitage producer directory (crozes-hermitage-vin.fr).

Why this script looks odd
-------------------------
The AOC's own site is Joomla + SP Page Builder and the producer listing is NOT
in the HTML: /fr/caves-maisons ships an empty shell and a Google-Maps widget.
The list is fetched at runtime by the `com_mymaplocations` component. Two calls
matter and both are POSTs against the page URL itself:

  1. task=getListname  -> [{"id":..,"name":..}, ...]   (name autocomplete)
  2. task=search       -> GeoJSON FeatureCollection    (the real directory)

`task=search` geocodes `searchzip` first and then applies `radius`. With an
empty `searchzip` it returns an empty collection, but any resolvable origin
plus `radius=-1` returns the whole directory regardless of the origin chosen
(Tain-l'Hermitage / 26600 / France all gave 136 features). So we post one
origin and take the lot; `limit=0` means "no page limit".

Each feature carries id / name / slug / [lon,lat] / street address / phone /
e-mail. The per-producer detail page (/fr/caves-maisons/<slug>) adds the fields
the directory listing never had:

  COORDONNÉES   street, postal code, commune, contact name, phone, e-mail
  INFORMATIONS  SITE WEB, SUPERFICIE VIGNOBLE, CAVEAU DE VENTE, HORAIRES

Coordinates: the GeoJSON point is the component's own geocode of the registered
address. A second point hides in `fulladdress` (the "Itinéraire" link) and the
two differ by up to ~2 km, so we keep BOTH and flag the disagreement instead of
pretending they are one measurement. Neither is treated as a vineyard location:
downstream geo still has to be established from OSM entities.

Output:
  work/crozes-hermitage/detail-raw/<id>.html        raw detail pages (cache)
  work/crozes-hermitage/directory-raw.json          geodata + audit
  outputs/daily/2026-09-15/crozes-hermitage-官方名录-2026-09-15.json
  work/crozes-hermitage-profiles.json               for geo + image collectors

Usage: python3 scripts/collect-crozes-hermitage-directory.py [--refetch]
"""
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work' / 'crozes-hermitage'
RAW = WORK / 'detail-raw'
DATE = os.environ.get('WINE_RUN_DATE') or __import__('datetime').date.today().isoformat()
REGION_ID = 'crozes-hermitage'
SITE = 'https://www.crozes-hermitage-vin.fr'
LISTING_URL = SITE + '/fr/caves-maisons'
OUT_DIR = ROOT / 'outputs' / 'daily' / DATE
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
    'X-Requested-With': 'XMLHttpRequest',
}

# The component's own vocabulary for "this producer is a shop/maison rather than
# a domaine" only exists implicitly (name prefixes), so we surface it instead of
# guessing: recorded per producer, never acted on.
NEGOCE_HINT = re.compile(r'\b(maison|négociant|negoce|sélections|selection|'
                         r'cave|caves|cellier|vins?)\b', re.I)

# Tain-l'Hermitage: inside the AOC, so the search origin never biases results.
SEARCH_ORIGIN = "Tain-l'Hermitage, France"


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


def strip_tags(s: str) -> str:
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def visible_text(html: str) -> str:
    """Page text with scripts/styles/entities collapsed — used for label:value fields."""
    b = re.sub(r'<(script|style)[\s\S]*?</\1>', ' ', html, flags=re.I)
    t = re.sub(r'<br\s*/?>', ' \n ', b)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = unescape(t).replace('\xa0', ' ')
    return re.sub(r'[ \t]+', ' ', t)


def post(url: str, data: dict, timeout: int = 60) -> bytes:
    body = '&'.join('%s=%s' % (k, v) for k, v in data.items()).encode()
    req = Request(url, data=body, headers={**HEADERS,
                                           'Content-Type': 'application/x-www-form-urlencoded'})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_geodata(refetch: bool = False) -> dict:
    cache = WORK / 'geodata-full.json'
    if cache.exists() and not refetch and cache.stat().st_size > 1000:
        return json.loads(cache.read_text(encoding='utf-8'))
    payload = {
        'searchname': '', 'searchzip': SEARCH_ORIGIN.replace(' ', '+').replace("'", '%27'),
        'task': 'search', 'radius': '-1', 'option': 'com_mymaplocations', 'limit': '0',
        'format': 'json', 'component': 'com_mymaplocations', 'Itemid': '264',
        'zoom': '12', 'limitstart': '0', 'geo': '', 'latitude': '', 'longitude': '',
    }
    raw = post(LISTING_URL, payload)
    d = json.loads(raw.decode('utf-8', 'replace'))
    if len(d.get('features', [])) < 50:
        raise SystemExit('search returned only %d features — API shape changed'
                         % len(d.get('features', [])))
    cache.write_text(raw.decode('utf-8', 'replace'), encoding='utf-8')
    return d


def fetch_names() -> list:
    """task=getListname with an empty query returns every record, not a sample."""
    raw = post(SITE + '/index.php?option=com_mymaplocations&task=getListname',
               {'query': ''})
    return json.loads(raw.decode('utf-8', 'replace'))


def fetch_detail(fid: int, slug: str, refetch: bool = False) -> str:
    path = RAW / ('%d-%s.html' % (fid, slug))
    if path.exists() and not refetch and path.stat().st_size > 50000:
        return path.read_text(encoding='utf-8', errors='replace')
    url = '%s/fr/caves-maisons/%s' % (SITE, slug)
    # plain document request: drop the AJAX header so the full page renders
    req = Request(url, headers={k: v for k, v in HEADERS.items()
                                if k != 'X-Requested-With'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=45) as r:
                html = r.read().decode('utf-8', 'replace')
            path.write_text(html, encoding='utf-8')
            time.sleep(0.6)
            return html
        except (HTTPError, URLError, TimeoutError) as e:
            if attempt == 2:
                print('  ! detail failed %s: %s' % (slug, e))
                return ''
            time.sleep(2.0 * (attempt + 1))
    return ''


# The site spells the same field several ways, including one outright typo in
# its own template ("UPERFICIE VIGNOBLE", missing the S). Canonicalise instead
# of silently dropping those producers from the field's coverage.
LABEL_CANON = {
    'SUPERFICIE DU VIGNOBLE': 'SUPERFICIE VIGNOBLE',
    'UPERFICIE VIGNOBLE': 'SUPERFICIE VIGNOBLE',
    'SITE INTERNET': 'SITE WEB',
}


def canon_label(label: str) -> str:
    lab = re.sub(r'\s+', ' ', label).strip().upper()
    return LABEL_CANON.get(lab, lab)


def parse_listing_address(props: dict) -> dict:
    """Address / phone / e-mail as the map widget itself writes them.

    The listing's `description` block is the only place carrying a phone number
    (the detail pages dropped `tel:` links entirely), and it is also the most
    uniform address: `<span class='locationaddress'>street<br/>POSTAL Commune<br/>
    France<br/><a href="tel:...">...</a></span>`. Parsing it here keeps phone
    coverage from collapsing to zero.
    """
    out = {'street': None, 'postalCode': None, 'commune': None,
           'phone': None, 'email': None}
    raw = props.get('description') or props.get('fulladdress') or ''
    m = re.search(r"class='locationaddress'>(.*?)</span>", raw, re.S) or \
        re.search(r'class="locationaddress">(.*?)</span>', raw, re.S)
    block = m.group(1) if m else raw
    parts = [strip_tags(x) for x in re.split(r'<br\s*/?>', block)]
    parts = [p for p in parts if p]
    if parts and not re.match(r'^(\d{5})\b', parts[0]):
        out['street'] = parts[0]
    for p in parts:
        pm = re.match(r'^(\d{5})\s+(.+)$', p)
        if pm:
            out['postalCode'], out['commune'] = pm.group(1), pm.group(2).strip()
    m = re.search(r'href="tel:([^"]+)"', raw)
    if m:
        tel = re.sub(r'\s+', ' ', unescape(m.group(1))).strip()
        # " + 33 (0)4 75 07 00 82" -> "+33 (0)4 75 07 00 82"
        out['phone'] = re.sub(r'^\+\s*', '+', tel) or None
    m = re.search(r'href="mailto:([^"?]+)', raw)
    if m:
        out['email'] = unescape(m.group(1)).strip()
    return out


def parse_detail(html: str) -> dict:
    """Pull COORDONNÉES + INFORMATIONS out of a detail page.

    Two address layouts coexist on the same site, so both are handled:
      A) <div class="address">123 rue X</div><div class="cp">26600 COMMUNE</div>
      B) <div class="thoroughfare">..</div><span class="postal-code">..
         </span><span class="locality">..
    """
    out = {k: None for k in ('street', 'postalCode', 'commune', 'contactName',
                             'phone', 'email', 'website', 'vineyardArea',
                             'hasShop', 'hasShopNote', 'openingHours')}
    if not html:
        return out

    # --- layout B (structured spans)
    m = re.search(r'<div class="thoroughfare">([\s\S]*?)</div>', html)
    if m:
        out['street'] = strip_tags(m.group(1)) or None
    m = re.search(r'<span class="postal-code">([\s\S]*?)</span>', html)
    if m:
        out['postalCode'] = strip_tags(m.group(1)) or None
    m = re.search(r'<span class="locality">([\s\S]*?)</span>', html)
    if m:
        out['commune'] = strip_tags(m.group(1)) or None
    # --- layout A (free divs); innermost .address wins, .cp holds "POSTAL COMMUNE"
    if not out['street']:
        m = re.search(r'<div class="address">([^<]{3,120})</div>', html)
        if m:
            out['street'] = strip_tags(m.group(1)) or None
    if not out['postalCode']:
        m = re.search(r'<div class="cp">([\s\S]*?)</div>', html)
        if m:
            cp = strip_tags(m.group(1))
            pm = re.match(r'^(\d{5})\s+(.+)$', cp)
            if pm:
                out['postalCode'], out['commune'] = pm.group(1), pm.group(2).strip()
            elif cp:
                out['postalCode'] = cp

    m = re.search(r'href="mailto:([^"?]+)', html)
    if m:
        out['email'] = unescape(m.group(1)).strip()
    m = re.search(r'href="tel:([^"]+)"', html)
    if m:
        out['phone'] = re.sub(r'\s+', ' ', unescape(m.group(1))).strip()

    # --- INFORMATIONS. The site is not consistent: most rows are
    # "<strong>LABEL -</strong>value" but ~16 use a colon ("SITE WEB : url")
    # and a few are plain text. <br> becomes a newline in visible_text, so the
    # line-oriented pass catches every variant; the <strong> pass runs first
    # because it survives values that themselves wrap onto a second line.
    fields = {}
    for m in re.finditer(r'<strong>\s*([A-ZÉÈÀÂÎÔÛ][A-ZÉÈÀÂÎÔÛ \'-]{2,34}?)\s*[-–:]\s*'
                         r'</strong>([\s\S]*?)(?=<strong>|</p>|$)', html):
        fields[canon_label(m.group(1))] = strip_tags(m.group(2)).strip(' .-') or None
    for line in visible_text(html).split('\n'):
        line = line.strip()
        m = re.match(r"^([A-ZÉÈÀÂÎÔÛ][A-ZÉÈÀÂÎÔÛ '\-]{2,34}?)\s*[-–:]\s+(.+)$", line)
        if m:
            fields.setdefault(canon_label(m.group(1)),
                              m.group(2).strip(' .-') or None)

    out['website'] = fields.get('SITE WEB')
    out['vineyardArea'] = fields.get('SUPERFICIE VIGNOBLE')
    out['openingHours'] = fields.get('HORAIRES')
    # CAVEAU DE VENTE is meant to be oui/non, but two producers wrote prose
    # there instead. Keep the raw text as a note rather than reading "has a
    # sales cellar" out of a sentence that says the opposite.
    shop = fields.get('CAVEAU DE VENTE')
    if shop and re.match(r'^(oui|yes)\b', shop, re.I):
        out['hasShop'] = 'oui'
    elif shop and re.match(r'^(non|no)\b', shop, re.I):
        out['hasShop'] = 'non'
    elif shop:
        out['hasShop'] = None
        out['hasShopNote'] = shop

    # the site links the website both as bare text and as an anchor; prefer text
    if out['website']:
        w = re.sub(r'\s+', ' ', out['website']).strip().rstrip('/.')
        if not re.match(r'^https?://', w, re.I):
            w = 'https://' + re.sub(r'^/+', '', w)
        out['website'] = w

    # contact name = short digit-free paragraph next to the address block
    m = re.search(r'sppb-addon-content\s*"?>\s*<p>([\s\S]*?)</p>', html)
    if m:
        cand = strip_tags(m.group(1))
        if (cand and len(cand) < 120 and not re.search(r'\d', cand)
                and not cand.lower().startswith(('sélectionnez', 'veuillez',
                                                 'vous aimez', 'merci', 'la cave bleue'))):
            out['contactName'] = cand
    return out


def main():
    refetch = '--refetch' in sys.argv
    geo = fetch_geodata(refetch)
    feats = geo['features']
    names = fetch_names()
    print('geodata features: %d | getListname records: %d' % (len(feats), len(names)))

    # ---- audit: the two endpoints must describe the same directory
    name_by_id = {n['id']: n['name'] for n in names}
    only_geo = [f['id'] for f in feats if f['id'] not in name_by_id]
    only_names = [i for i in name_by_id if i not in {f['id'] for f in feats}]
    name_diff = [f['id'] for f in feats
                 if f['id'] in name_by_id and name_by_id[f['id']].strip() !=
                 re.sub(r'\s+', ' ', f['properties'].get('name', '')).strip()]
    print('  id only in geodata: %s' % only_geo)
    print('  id only in getListname: %s' % only_names)
    print('  same id, different name: %s' % name_diff)

    # ---- detail pages
    todo = []
    for f in feats:
        url = f['properties'].get('url') or ''
        slug = url.rsplit('/', 1)[-1] if url else slugify(f['properties']['name'])
        todo.append((f['id'], slug))
    print('fetching %d detail pages …' % len(todo))
    details = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_detail, i, s, refetch): (i, s) for i, s in todo}
        for n, fut in enumerate(as_completed(futs), 1):
            i, s = futs[fut]
            details[i] = fut.result()
            if n % 25 == 0:
                print('  %d/%d' % (n, len(todo)))

    producers, coord_gap = [], []
    for f in feats:
        p = f['properties']
        det = parse_detail(details.get(f['id'], ''))
        lst = parse_listing_address(p)
        # listing address is the uniform one; the detail page fills the gaps
        street = lst['street'] or det['street']
        postal = lst['postalCode'] or det['postalCode']
        commune = lst['commune'] or det['commune']
        phone = lst['phone'] or det['phone']
        email = lst['email'] or det['email']
        lon, lat = f['geometry']['coordinates']
        name = re.sub(r'\s+', ' ', p['name']).strip()
        slug = (p.get('url') or '').rsplit('/', 1)[-1] or slugify(name)
        producers.append({
            'slug': slug,
            'name': name,
            'wineryId': 'winery-%s-%s' % (REGION_ID, slug),
            'directoryId': f['id'],
            'regionId': REGION_ID,
            'address': ' / '.join(x for x in (street, postal, commune) if x) or None,
            'street': street,
            'postalCode': postal,
            'commune': commune,
            'contactName': det['contactName'],
            'phone': phone,
            'email': email,
            'website': det['website'],
            'vineyardArea': det['vineyardArea'],
            'hasShop': det['hasShop'],
            'hasShopNote': det['hasShopNote'],
            'openingHours': det['openingHours'],
            'directoryURL': LISTING_URL,
            'detailURL': '%s/fr/caves-maisons/%s' % (SITE, slug),
            'coordinates': {
                'lon': lon, 'lat': lat,
                'source': 'com_mymaplocations geocode of the registered address',
                'listingDistanceKm': p.get('distance'),
            },
            'looksLikeNegoce': bool(NEGOCE_HINT.search(name.replace('Domaine', ''))),
        })

        # The map widget also emits a second point next to its itinerary link.
        # It is the SAME point (~1.4 km from the search origin) for every single
        # record, i.e. a template placeholder, not a measurement — so it is
        # recorded as such and must never be used as an address coordinate.
        m = re.search(r'getUIDirection_side\(\d+,"([-\d.]+),([-\d.]+)"\)',
                      p.get('fulladdress', ''))
        if m:
            coord_gap.append((float(m.group(2)), float(m.group(1))))

    producers.sort(key=lambda p: unicodedata.normalize('NFKD', p['name']).lower())

    (WORK / 'directory-raw.json').write_text(json.dumps({
        'date': DATE, 'sourceURL': LISTING_URL, 'features': len(feats),
        'getListnameRecords': len(names), 'audit': {
            'idOnlyInGeodata': only_geo, 'idOnlyInGetListname': only_names,
            'sameIdDifferentName': name_diff},
        'apiNote': ('com_mymaplocations 组件：POST task=search（searchzip=产区中心点，'
                    'radius=-1，limit=0）返回全量 GeoJSON；POST task=getListname（query 空）'
                    '返回全量 id/name。两个接口在本期描述同一份名录（id 集合与名称全部一致）。'),
        'placeholderPointNote': ('每条 fulladdress 里 Itinéraire 链接带的坐标在 136 条中'
                                 '完全相同（均距搜索原点约 1.4 km），是模板占位常量，'
                                 '已弃用；地址坐标一律取 geometry（与页面自带的 distance '
                                 '字段自洽：如 Albert Bichot 217.6 km / 217.6 km）。'),
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    (OUT_DIR / ('crozes-hermitage-官方名录-%s.json' % DATE)).write_text(json.dumps({
        'date': DATE,
        'source': 'AOC Crozes-Hermitage · Caves & Maisons (annuaire officiel)',
        'sourceURL': LISTING_URL,
        'apiSourceURL': SITE + '/index.php?option=com_mymaplocations&task=search',
        'checkedDate': DATE,
        'sourceLanguage': 'fr',
        'notes': ('名录由 Joomla com_mymaplocations 组件在页面加载时以 JSON 取回，'
                  '静态 HTML 中没有任何生产者列表；本文件由该接口全量取回，'
                  '并逐家抓取详情页补齐 SITE WEB / 葡萄园面积 / CAVEAU DE VENTE / HORAIRES。'
                  '名录混含酒庄（domaine）与酒商/门市（maison、cave、négoce），照录不删。'
                  '坐标为组件按登记通讯地址自行地理编码所得，非葡萄园位置；'
                  'OSM 实体判定另见 geo-collected，两者不得互相顶替。'),
        'producers': producers,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    geo_input = [{'id': p['wineryId'], 'name': p['name'], 'country': 'France',
                  'commune': p['commune'], 'postalCode': p['postalCode']}
                 for p in producers]
    (ROOT / 'work' / 'crozes-hermitage-profiles.json').write_text(
        json.dumps(producers, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (ROOT / 'work' / 'crozes-hermitage-geo-input.json').write_text(
        json.dumps(geo_input, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    print('producers: %d' % len(producers))
    print('  with website: %d' % sum(1 for p in producers if p['website']))
    print('  with email: %d' % sum(1 for p in producers if p['email']))
    print('  with phone: %d' % sum(1 for p in producers if p['phone']))
    print('  with postal code: %d' % sum(1 for p in producers if p['postalCode']))
    print('  with commune: %d' % sum(1 for p in producers if p['commune']))
    print('  with vineyard area: %d' % sum(1 for p in producers if p['vineyardArea']))
    print('  with has-shop flag: %d' % sum(1 for p in producers if p['hasShop']))
    print('  negoce-looking names: %d' % sum(1 for p in producers if p['looksLikeNegoce']))

    # placeholder-point sanity: must collapse to a single distinct location
    uniq = {(round(a, 4), round(b, 4)) for a, b in coord_gap}
    print('  itinerary placeholder points: %d records, %d distinct location(s)'
          % (len(coord_gap), len(uniq)))

    # how many registered addresses actually sit inside the growing window
    inwin = [p for p in producers if 44.5 <= p['coordinates']['lat'] <= 45.6
             and 4.4 <= p['coordinates']['lon'] <= 5.2]
    print('  registered address inside north-Rhône window: %d / %d'
          % (len(inwin), len(producers)))
    outside = sorted((p['name'], p['postalCode'], p['commune'])
                     for p in producers if p not in inwin)
    (WORK / 'address-outside-window.json').write_text(
        json.dumps([{'name': n, 'postalCode': c, 'commune': cm}
                    for n, c, cm in outside], ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8')
    print('  outside-window addresses written to work/crozes-hermitage/'
          'address-outside-window.json (%d)' % len(outside))


if __name__ == '__main__':
    main()
