# coding: utf-8
"""第二通道：从酒庄官网（首页 + /contact）直接提取地图坐标。

为什么需要它：OSM 对「几公顷的家族酒庄」覆盖极差，那些 Domaine 根本没有 POI。
官网嵌的 Google Maps 链接里往往直接带经纬度，不需要 geocode。

与 OSM 通道共用同一套地理合理性校验（geo_ok），因为试跑发现官网坐标也不总是对的：
Guigal 官网给的 45.636 与 OSM 的 45.489 相差 16.5km（官网常定位到办公室或城市中心）。

注意：只抓公开页面、只读、不做任何写入；TLS 校验放宽是因为部分酒庄站证书过期/自签，
抓取的是公开 HTML，风险可接受。

用法: python3 scripts/fill-missing-winery-geo-web.py <missing.json> <out.json> [--limit N] [--only-missing]
"""
import json, re, ssl, sys, urllib.request
from pathlib import Path
import importlib.util as ilu

ROOT = Path(__file__).resolve().parents[1]
_spec = ilu.spec_from_file_location('fg', str(ROOT / 'scripts' / 'fill-missing-winery-geo.py'))
_fg = ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fg)

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PATS = [
    ('gmap_embed', re.compile(r'!2d(-?\d{1,3}\.\d{3,})!3d(-?\d{1,3}\.\d{3,})'), 'lng,lat'),
    ('gmap_at', re.compile(r'@(-?\d{1,3}\.\d{4,}),(-?\d{1,3}\.\d{4,}),\d+'), 'lat,lng'),
    ('gmap_q', re.compile(r'[?&](?:q|query|ll|center|daddr)=(-?\d{1,3}\.\d{3,})[,%\s]+(-?\d{1,3}\.\d{3,})'), 'lat,lng'),
    ('schema', re.compile(r'"latitude"\s*:\s*"?(-?\d{1,3}\.\d{3,})"?\s*[,}][\s\S]{0,200}?"longitude"\s*:\s*"?(-?\d{1,3}\.\d{3,})"?'), 'lat,lng'),
    ('osm_marker', re.compile(r'marker=(-?\d{1,3}\.\d{3,})(?:%2C|,)(-?\d{1,3}\.\d{3,})'), 'lat,lng'),
    ('plain', re.compile(r'lat(?:itude)?\D{0,12}(-?\d{1,3}\.\d{4,})\D{1,24}lon(?:gitude)?\D{0,12}(-?\d{1,3}\.\d{4,})', re.I), 'lat,lng'),
]


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fr,en'})
    with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
        raw = r.read(700000)
        return raw.decode(r.headers.get_content_charset() or 'utf-8', 'replace')


def candidates(html):
    out = []
    for tag, pat, order in PATS:
        for m in pat.finditer(html):
            try:
                a, b = float(m.group(1)), float(m.group(2))
            except (TypeError, ValueError):
                continue
            lat, lng = (a, b) if order == 'lat,lng' else (b, a)
            if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0):
                out.append((tag, round(lat, 5), round(lng, 5)))
    return out


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    only_missing = '--only-missing' in sys.argv
    items = json.loads(src.read_text())
    if only_missing:
        osm = ROOT / 'work' / 'geo-fill-results.json'
        if osm.exists():
            hit = {r['id'] for r in json.loads(osm.read_text()) if r.get('status') == 'matched'}
            items = [i for i in items if i['id'] not in hit]
            print('OSM 已命中的跳过，剩 %d 条' % len(items), flush=True)
    items = [i for i in items if (i.get('website') or '').strip()]
    if limit:
        items = items[:limit]
    boundaries = _fg.load_boundaries()
    anchors, _rp, country_pts = _fg.load_anchors()
    print('待抓 %d 个官网；边界 %d、聚类 %d' % (len(items), len(boundaries), len(anchors)), flush=True)

    results, done = [], set()
    if dst.exists():
        try:
            prev = json.loads(dst.read_text())
            ids = {i['id'] for i in items}
            results = [r for r in prev if r.get('id') in ids]
            done = {r['id'] for r in results}
            print('续跑：已完成 %d' % len(done), flush=True)
        except Exception:
            results, done = [], set()

    for idx, it in enumerate(items, 1):
        if it['id'] in done:
            continue
        site = (it['website'] or '').strip()
        if not site.startswith('http'):
            site = 'https://' + site
        base = site.rstrip('/')
        hit, notes = None, []
        for url in [site, base + '/contact', base + '/nous-contacter']:
            try:
                html = fetch(url)
            except Exception as e:
                notes.append('%s:%s' % (url[:40], type(e).__name__))
                continue
            for tag, lat, lng in candidates(html):
                ok, why = _fg.geo_ok(it.get('regionId') or '', it.get('country') or '',
                                     lat, lng, boundaries, anchors, country_pts)
                if ok:
                    hit = {
                        'id': it['id'], 'name': it['name'], 'status': 'matched',
                        'matchedBy': 'website:' + tag, 'query': url,
                        'lat': lat, 'lng': lng,
                        'displayName': '%s 官网地图嵌入' % site[:60],
                        'geoCheck': why,
                        'locationSourceURL': url,
                        'locationPrecision': '酒庄官网地图嵌入坐标（%s），经地理校验（%s）；非地块边界' % (tag, why),
                    }
                    break
                notes.append('geo_reject(%s)' % why)
            if hit:
                break
        if not hit:
            hit = {'id': it['id'], 'name': it['name'], 'status': 'not_found',
                   'lat': None, 'lng': None, 'notes': notes[:3]}
        results.append(hit)
        print('%3d/%d  %-38s %s' % (idx, len(items), it['name'][:38],
                                    hit['status'] + ('  ' + str((hit['lat'], hit['lng']))
                                                     if hit['status'] == 'matched' else '')), flush=True)
        if len(results) % 5 == 0:
            dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    m = sum(1 for r in results if r.get('status') == 'matched')
    print('\n完成：%d 条，命中 %d（%.0f%%）-> %s' % (len(results), m, 100.0 * m / max(1, len(results)), dst))


if __name__ == '__main__':
    main()
