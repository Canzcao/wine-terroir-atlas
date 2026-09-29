# coding: utf-8
"""Collect evidenced winery coordinates from OpenStreetMap (Nominatim).

Rule: only accept a match when the OSM feature is the producer itself
(accepted POI classes) or its name matches the producer name. A commune
centroid is never treated as a winery location; unmatched producers keep
null coordinates.

Usage: python3 scripts/collect-producer-geo.py <input.json> <output.json>

input.json: [{"id": "...", "name": "...", "country": "France"}, ...]
output.json: per producer match status, OSM object, coordinates, precision.
"""
import json, re, sys, time, unicodedata
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

UA = 'TerroirAtlas/1.0 (editorial data collection; contact: site owner)'
ENDPOINT = 'https://nominatim.openstreetmap.org/search'
CACHE_DIR = Path(__file__).resolve().parents[1] / 'work' / 'geocache'

# POI classes that represent a real estate/visitor location rather than an area.
POI_CLASSES = {
    ('shop', 'alcohol'), ('shop', 'wine'), ('shop', 'beverages'), ('shop', 'farm'),
    ('craft', 'winery'), ('craft', 'brewery'), ('amenity', 'restaurant'), ('amenity', 'cafe'),
    ('tourism', 'attraction'), ('tourism', 'museum'), ('office', 'company'), ('building', 'yes'),
    ('building', 'industrial'), ('building', 'farm'), ('landuse', 'vineyard'),
}
POI_TYPES = {'winery', 'vineyard', 'wine', 'cellar'}

STOPWORDS = {
    # 法语
    'domaine', 'domaines', 'cave', 'caves', 'vignoble', 'vignobles', 'maison', 'et', 'fils',
    'pere', 'père', 'freres', 'frères', 'sarl', 'eurl', 'scea', 'earl', 'les', 'du', 'de', 'la',
    'le', 'aux', 'des', 'sur', 'saint', 'sainte', 'st', 'a', 'and', 'the', 'wines', 'wine',
    # 西班牙语（2026-09-26 补：里奥哈/杜埃罗河岸用法定实体全名登记，
    # 若不去掉法律后缀与通用词，name_match 会因分母过大而拒掉正确匹配）
    'bodega', 'bodegas', 'bodegueros', 'vinedo', 'vinedos', 'viñedo', 'viñedos', 'vino', 'vinos',
    'vinicola', 'vitivinicola', 'agricola', 'agropecuaria', 'explotaciones', 'propiedad',
    'y', 'e', 'el', 'los', 'las', 'del', 'espanola', 'española', 'hermanos', 'hno', 'hnos',
    'familia', 'grupo', 'sociedad', 'limitada', 'anonima', 'unipersonal', 'responsabilidad',
    'sl', 'slu', 'sa', 'sc', 'scoop', 'sll', 'sau', 'srl', 'cb', 'sat',
}


def normalize(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return [t for t in text.split() if t and t not in STOPWORDS]


def name_match(producer, candidate):
    """Return True when the OSM name carries the producer's distinctive tokens."""
    p, c = normalize(producer), set(normalize(candidate))
    if not p:
        return False
    hits = sum(1 for t in p if t in c)
    if len(p) == 1:
        return p[0] in c
    return hits / len(p) >= 0.75


def fetch(params, retries=3):
    qs = urlencode(params)
    digest = re.sub(r'[^A-Za-z0-9]+', '_', params.get('q', ''))[:120]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / (digest + '.json')
    if cached.exists():
        return json.loads(cached.read_text())
    url = ENDPOINT + '?' + qs
    for attempt in range(retries):
        try:
            req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fr,en'})
            with urlopen(req, timeout=40) as response:
                data = json.loads(response.read().decode('utf-8'))
            cached.write_text(json.dumps(data, ensure_ascii=False))
            return data
        except Exception as err:  # noqa: BLE001 - network failures are recorded, not fatal
            if attempt == retries - 1:
                return {'error': str(err)}
            time.sleep(3 * (attempt + 1))
    return {'error': 'unreachable'}


def classify(producer_name, rows, bbox=None):
    accepted, rejected = [], []
    for row in rows:
        cls, typ = row.get('class'), row.get('type')
        is_poi = (cls, typ) in POI_CLASSES or typ in POI_TYPES
        matched = name_match(producer_name, row.get('name') or '')
        if matched and is_poi:
            if bbox and not inside(row, bbox):
                row['_reject'] = 'outside_region_bbox'
                rejected.append(row)
                continue
            accepted.append(row)
        else:
            rejected.append(row)
    return accepted, rejected


def inside(row, bbox):
    """bbox = [south, north, west, east]; guards against same-name producers elsewhere."""
    try:
        lat, lng = float(row['lat']), float(row['lon'])
    except (KeyError, TypeError, ValueError):
        return False
    south, north, west, east = bbox
    return south <= lat <= north and west <= lng <= east


def main():
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    producers = json.loads(source.read_text())
    bbox = None
    if len(sys.argv) > 3:
        bbox = [float(x) for x in sys.argv[3].split(',')]
    results = []
    done = set()
    if target.exists() and '--fresh' not in sys.argv:
        try:
            prev = json.loads(target.read_text())
            results = [r for r in prev if r.get('id') in {p['id'] for p in producers}]
            done = {r['id'] for r in results}
            if done:
                print('resuming: %d/%d already collected' % (len(done), len(producers)), flush=True)
        except Exception:
            results, done = [], set()
    for index, item in enumerate(producers, 1):
        if item['id'] in done:
            continue
        # queryName 可选：官方名录常用法定实体全名，直接检索召回差；
        # 允许调用方给一个「干净名」只用于检索，name_match 仍比对原 name。
        query = '%s, %s' % (item.get('queryName') or item['name'],
                             item.get('country', 'France'))
        rows = fetch({'q': query, 'format': 'json', 'limit': 5,
                      'addressdetails': 1, 'extratags': 1})
        if isinstance(rows, dict) and rows.get('error'):
            results.append({'id': item['id'], 'name': item['name'], 'status': 'query_failed',
                            'error': rows['error'], 'lat': None, 'lng': None})
            print('%3d/%d  %-42s QUERY FAILED' % (index, len(producers), item['name']), flush=True)
            continue
        accepted, rejected = classify(item['name'], rows, bbox)
        if accepted:
            row = accepted[0]
            extra = row.get('extratags') or {}
            results.append({
                'id': item['id'],
                'name': item['name'],
                'status': 'matched',
                'lat': float(row['lat']),
                'lng': float(row['lon']),
                'osmType': row.get('osm_type'),
                'osmId': row.get('osm_id'),
                'osmClass': row.get('class'),
                'osmTypeDetail': row.get('type'),
                'osmName': row.get('name'),
                'displayName': row.get('display_name'),
                'boundingbox': row.get('boundingbox'),
                'website': extra.get('website') or extra.get('contact:website'),
                'phone': extra.get('phone') or extra.get('contact:phone'),
                'operator': extra.get('operator'),
                'locationSourceURL': 'https://www.openstreetmap.org/%s/%s' % (
                    row.get('osm_type'), row.get('osm_id')),
                'locationPrecision': 'OSM 实体“%s”（%s/%s），视为酒庄/酒窖到访点位；非地块边界，未核实产权范围' % (
                    row.get('name'), row.get('class'), row.get('type')),
            })
            print('%3d/%d  %-42s MATCH %s %s' % (index, len(producers), item['name'],
                                                row['lat'], row['lon']), flush=True)
        else:
            results.append({
                'id': item['id'],
                'name': item['name'],
                'status': 'no_evidenced_location',
                'lat': None, 'lng': None,
                'candidatesSeen': len(rows),
                'rejectedExamples': [r.get('display_name') for r in rejected[:2]],
            })
            print('%3d/%d  %-42s none (%d rows seen)' % (index, len(producers), item['name'],
                                                         len(rows)), flush=True)
        time.sleep(1.1)  # Nominatim usage policy: max 1 request per second
        # Save progressively: a run of ~40 producers takes longer than the
        # execution window in some environments and used to lose everything.
        target.write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n')
    target.write_text(json.dumps(results, ensure_ascii=False, indent=1) + '\n')
    matched = sum(1 for r in results if r['status'] == 'matched')
    print('\nwrote %s\nmatched %d/%d' % (target, matched, len(results)))


if __name__ == '__main__':
    main()
