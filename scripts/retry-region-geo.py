# coding: utf-8
"""Second-pass, viewbox-bounded OSM geo search for producers still at null.

Pass 1 (collect-producer-geo.py) queries "NAME, France" unbounded, so it only
finds producers whose OSM entity carries the producer name and which happens to
rank in the top 5 worldwide. This pass instead:

  * queries inside a bounded viewbox over the appellation's region, so a
    same-name producer in another département/region cannot leak in at all;
  * tries query variants: full name, name stripped of corporate prefixes,
    name + appellation, name + commune;
  * keeps the *same* acceptance rule as pass 1 (winery-like POI **and** the
    feature name carries the producer's distinctive tokens).

Resumable and saves after every producer: a full retry run is longer than the
execution window in some environments.

Usage:
  python3 scripts/retry-region-geo.py <geo-raw.json> <profiles-flat.json> <out.json> \
      [--bbox south,north,west,east] [--appellation "Saint-Péray"]
Default bbox is the northern Rhône.
"""
import argparse
import importlib.util as _ilu
import json
import re
import ssl
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
_spec = _ilu.spec_from_file_location(
    'collect_producer_geo', str(Path(__file__).resolve().parent / 'collect-producer-geo.py'))
_cgm = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_cgm)
classify, normalize = _cgm.classify, _cgm.normalize

UA = 'TerroirAtlas/1.0 (editorial data collection; contact: site owner)'
ENDPOINT = 'https://nominatim.openstreetmap.org/search'
CACHE = ROOT / 'work' / 'geocache-bounded'
SSL_CTX = ssl.create_default_context()
NORTHERN_RHONE = [44.35, 45.80, 4.40, 5.25]   # south, north, west, east


def fetch(params: dict, retries: int = 3):
    """Cached Nominatim call. Cache key includes the viewbox, unlike pass 1."""
    key = re.sub(r'[^A-Za-z0-9]+', '_', params.get('q', '') + '|' + str(params.get('viewbox', '')))[:150]
    CACHE.mkdir(parents=True, exist_ok=True)
    c = CACHE / (key + '.json')
    if c.exists():
        return json.loads(c.read_text())
    url = ENDPOINT + '?' + urlencode(params)
    for attempt in range(retries):
        try:
            req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fr,en'})
            with urlopen(req, timeout=40, context=SSL_CTX) as r:
                data = json.loads(r.read().decode('utf-8'))
            c.write_text(json.dumps(data, ensure_ascii=False))
            return data
        except (URLError, OSError, ValueError) as err:
            if attempt == retries - 1:
                return {'error': str(err)}
            time.sleep(3 * (attempt + 1))
    return {'error': 'unreachable'}


def variants(name: str, commune, appellation):
    toks = normalize(name)
    core = ' '.join(toks) if toks else name
    out = [name]
    if core and core.lower() != name.lower():
        out.append(core)
    for suffix in (appellation, commune):
        if suffix:
            out.append('%s %s' % (core or name, suffix))
    seen, uniq = set(), []
    for v in out:
        if v.lower() not in seen:
            seen.add(v.lower())
            uniq.append(v)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('geo')
    ap.add_argument('profiles')
    ap.add_argument('out')
    ap.add_argument('--bbox', default=','.join(str(x) for x in NORTHERN_RHONE))
    ap.add_argument('--appellation', default=None)
    args = ap.parse_args()

    bbox = [float(x) for x in args.bbox.split(',')]
    viewbox = '%s,%s,%s,%s' % (bbox[2], bbox[1], bbox[3], bbox[0])  # left,top,right,bottom
    geo = json.loads(Path(args.geo).read_text(encoding='utf-8'))
    plist = json.loads(Path(args.profiles).read_text(encoding='utf-8'))
    # match by name (region-slug in the id is not portable across regions)
    by_name = {p['name']: p for p in plist}
    by_slug_tail = {}
    for p in plist:
        by_slug_tail[p['slug']] = p
    out_path = Path(args.out)

    retries = {}
    if out_path.exists():
        retries = {r['id']: r for r in json.loads(out_path.read_text(encoding='utf-8'))}
        print('resuming: %d already retried' % len(retries), flush=True)

    # work on producers that pass 1 could not place, plus any that were only
    # rejected for being outside the (narrower) pass-1 filter
    todo = []
    for r in geo:
        if r['status'] == 'matched':
            continue
        if r['id'] in retries:
            continue
        todo.append(r)

    print('to retry: %d' % len(todo), flush=True)
    for n, item in enumerate(todo, 1):
        name = item['name']
        prof = by_name.get(name)
        if prof is None:
            tail = item['id'].rsplit('-', 1)[-1]
            prof = by_slug_tail.get(tail, {})
        commune = prof.get('commune')
        accepted = rejected_count = 0
        hit = None
        for v in variants(name, commune, args.appellation):
            rows = fetch({'q': v + ', France', 'format': 'json', 'limit': 8,
                          'addressdetails': 1, 'extratags': 1,
                          'viewbox': viewbox, 'bounded': 1})
            if isinstance(rows, dict):
                continue
            rejected_count += len(rows)
            acc, _rej = classify(name, rows, bbox)
            if acc:
                hit = acc[0]
                break
            time.sleep(1.1)
        if hit:
            extra = hit.get('extratags') or {}
            retries[item['id']] = {
                'id': item['id'], 'name': name, 'status': 'matched',
                'lat': float(hit['lat']), 'lng': float(hit['lon']),
                'osmType': hit.get('osm_type'), 'osmId': hit.get('osm_id'),
                'osmClass': hit.get('class'), 'osmTypeDetail': hit.get('type'),
                'osmName': hit.get('name'), 'displayName': hit.get('display_name'),
                'boundingbox': hit.get('boundingbox'),
                'website': extra.get('website') or extra.get('contact:website'),
                'locationSourceURL': 'https://www.openstreetmap.org/%s/%s' % (
                    hit.get('osm_type'), hit.get('osm_id')),
                'locationPrecision': 'OSM 实体“%s”（%s/%s），视为酒庄/酒窖到访点位；非地块边界，未核实产权范围'
                                     % (hit.get('name'), hit.get('class'), hit.get('type')),
                'searchPass': 'bounded-viewbox',
            }
            print('%2d/%d %-40s MATCH %s %s' % (n, len(todo), name[:40], hit['lat'], hit['lon']), flush=True)
        else:
            retries[item['id']] = {
                'id': item['id'], 'name': name, 'status': 'no_evidenced_location',
                'lat': None, 'lng': None, 'rowsSeenBounded': rejected_count,
                'searchPass': 'bounded-viewbox',
            }
            print('%2d/%d %-40s none (rows seen %d)' % (n, len(todo), name[:40], rejected_count), flush=True)
        accent = sum(1 for r in retries.values() if r['status'] == 'matched')
        out_path.write_text(json.dumps(sorted(retries.values(), key=lambda r: r['id']),
                                       ensure_ascii=False, indent=1), encoding='utf-8')
        time.sleep(1.1)

    matched = sum(1 for r in retries.values() if r['status'] == 'matched')
    print('\nwrote %s\nbounded pass matched %d / %d retried' % (out_path, matched, len(retries)))


if __name__ == '__main__':
    main()
