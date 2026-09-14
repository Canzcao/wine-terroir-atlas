# coding: utf-8
"""Second-pass geo search for Condrieu producers that had no evidenced OSM point.

Improvements over the first pass:
  - bounded viewbox queries over the northern Rhône bbox (no same-name producers
    from Alsace/Loire can leak in);
  - query variants: full name, name without corporate prefixes, name + Condrieu.

Same acceptance rules as collect-producer-geo.py: the OSM feature must be a
winery-like POI AND its name must carry the producer's distinctive tokens.
"""
import json, sys, time
from pathlib import Path

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    'collect_producer_geo', str(Path(__file__).resolve().parent / 'collect-producer-geo.py'))
_cgm = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_cgm)
fetch, classify, normalize = _cgm.fetch, _cgm.classify, _cgm.normalize

BBOX = [44.9, 45.75, 4.5, 5.1]  # south, north, west, east (northern Rhône)
VIEWBOX = '4.5,45.75,5.1,44.9'  # left,top,right,bottom (lon,lat,lat,lon)


def variants(name):
    tokens = normalize(name)
    full = name
    core = ' '.join(tokens) if tokens else name
    return [full, core, '%s Condrieu' % core]


def main():
    geo_path = Path(sys.argv[1])
    profiles_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    geo = json.loads(geo_path.read_text())
    profiles = {p['slug']: p for p in json.loads(profiles_path.read_text())}
    accepted_names = set(geo['acceptedForCoordinates'])
    unmatched = [r for r in geo['raw'] if r['status'] == 'no_evidenced_location'
                 and r['name'] not in accepted_names]
    print('retrying %d producers' % len(unmatched))
    new_rows = []
    for index, item in enumerate(unmatched, 1):
        got = None
        rejected_all = []
        for q in variants(item['name']):
            rows = fetch({'q': q, 'format': 'json', 'limit': 8,
                          'addressdetails': 1, 'extratags': 1,
                          'viewbox': VIEWBOX, 'bounded': 1})
            if isinstance(rows, dict):
                time.sleep(1.1)
                continue
            accepted, rejected = classify(item['name'], rows, BBOX)
            rejected_all += [r.get('display_name') for r in rejected[:1]]
            if accepted:
                got = accepted[0]
                break
            time.sleep(1.1)
        if got:
            extra = got.get('extratags') or {}
            row = {
                'id': item['id'], 'name': item['name'], 'status': 'matched_retry',
                'lat': float(got['lat']), 'lng': float(got['lon']),
                'osmType': got.get('osm_type'), 'osmId': got.get('osm_id'),
                'osmClass': got.get('class'), 'osmTypeDetail': got.get('type'),
                'osmName': got.get('name'),
                'displayName': got.get('display_name'),
                'website': extra.get('website') or extra.get('contact:website'),
                'locationSourceURL': 'https://www.openstreetmap.org/%s/%s' % (
                    got.get('osm_type'), got.get('osm_id')),
                'locationPrecision': 'OSM 实体“%s”（%s/%s），视为酒庄/酒窖到访点位；非地块边界，未核实产权范围' % (
                    got.get('name'), got.get('class'), got.get('type')),
            }
            new_rows.append(row)
            print('%3d/%d %-40s RETRY-MATCH %s %s' % (index, len(unmatched),
                  item['name'], row['lat'], row['lng']), flush=True)
        else:
            new_rows.append({'id': item['id'], 'name': item['name'],
                             'status': 'no_evidenced_location',
                             'lat': None, 'lng': None,
                             'note': '第二轮带范围限定的变体查询仍未命中酒庄类 POI',
                             'rejectedExamples': rejected_all[:2]})
            print('%3d/%d %-40s none' % (index, len(unmatched), item['name']), flush=True)
    out_path.write_text(json.dumps({'date': '2026-09-14', 'regionId': 'condrieu',
                                    'rows': new_rows}, ensure_ascii=False, indent=1) + '\n')
    got = sum(1 for r in new_rows if r['status'] == 'matched_retry')
    print('retry matches: %d/%d -> %s' % (got, len(new_rows), out_path))


if __name__ == '__main__':
    main()
