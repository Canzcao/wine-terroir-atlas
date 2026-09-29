# coding: utf-8
"""为缺坐标的酒庄补全坐标（第二遍，宽严结合）。

与 collect-producer-geo.py 的区别 —— 那个脚本只用「名称+国家」且要求 OSM 要素是
winery-like POI；本脚本额外做三件事：

1. 用拉丁名（en 优先于 name）+ 地址，做多级查询变体（命中即停）；
2. **地理合理性校验**（这是必需的一条）：试跑发现 "Bollinger" 被匹配到 300km 外的
   斯特拉斯堡礼品店、"Domaine Huet" 被匹配到干邑区的 guest_house。
   校验顺序：
     a. 该 region 有边界（region-boundaries.geojson）→ **软约束**：记录点到边界的
        距离并分级（界内 / 界外 ≤80km / 界外 >80km），但**不再拒绝**。见下面「为什么软」。
     b. 该 region 已有 ≥3 个已知坐标 → 距中位数 < 自适应半径（P90 距离 × 1.5，下限 25km）；
     c. 该 region 无参照 → 距同国家已知坐标中位数 < 300km；
     d. 全无参照 → 只接受名称完全一致（normalize 后 token 集合相等）；
3. 输出带精度标注的结果，交合并脚本写回，不直接改 catalog-seed.json。

**为什么边界那一条改成软约束（2026-09-23 用户拍板）**
目录里酒庄的 `regionId` 记的是「所产法定产区」，**不是酒窖所在村**。实测 664 个
落在有边界产区的已定位酒庄里 **192 个（28.9%）点位在法定范围外**，而它们到边界的
距离分布是：中位 3.1km、P90 28.9km、**最大 55.8km，100% 落在 80km 内**。
最远那一批清一色是酒商行（Maison Vidal-Fleury、E. Guigal、Famille Pierre Gaillard…）——
它们做 Cornas / Saint-Joseph，但公司注册地在 Tain-l'Hermitage 或 Ampuis。
硬拒绝会把这批合法窖址整批清掉（`nuit-saint-georges` 更是 10/10 全在界外）。

**真正的质量闸门不在本脚本，在 `merge-geo-fill.py` 的第 4 道护栏
「同产区最近邻 30km」**（参照系是同产区既有坐标，不受本条影响，实测
95% 的正当点位都在 20km 内）。所以这里放开不会让误配流进库里：
Bollinger→斯特拉斯堡 那类 350km 的错配照样会被合并那一步拦住。

阈值 `SOFT_TOL_KM = 80` 是按上面 192 条实测分布定的（= 实测最大值 55.8km 的 1.43 倍）。
超过 80km 不拒绝，但 `geoLevel` 记成 `far`、`locationPrecision` 里带上距离，
便于 `audit-geo-fill.py` 与人工复核挑出来看。
想退回旧的硬拒绝口径：加 `--strict-geo`（不改代码）。

用法:
    python3 scripts/fill-missing-winery-geo.py <missing.json> <out.json> [--limit N]
    python3 scripts/fill-missing-winery-geo.py <missing.json> <out.json> --strict-geo
        # 退回硬拒绝：点落在法定范围外一律不采用（2026-09-23 之前的行为）
"""
import json, math, re, sys, time
from pathlib import Path
import importlib.util as ilu

ROOT = Path(__file__).resolve().parents[1]
_spec = ilu.spec_from_file_location('cgm', str(ROOT / 'scripts' / 'collect-producer-geo.py'))
_cgm = ilu.module_from_spec(_spec)
_spec.loader.exec_module(_cgm)
fetch, normalize = _cgm.fetch, _cgm.normalize

COUNTRY_EN = {
    '法国': 'France', '阿根廷': 'Argentina', '智利': 'Chile', '乌拉圭': 'Uruguay',
    '意大利': 'Italy', '新西兰': 'New Zealand', '澳大利亚': 'Australia', '美国': 'United States',
    '西班牙': 'Spain', '南非': 'South Africa', '葡萄牙': 'Portugal', '德国': 'Germany',
    '奥地利': 'Austria', '匈牙利': 'Hungary', '希腊': 'Greece', '格鲁吉亚': 'Georgia',
    '中国': 'China', '日本': 'Japan', '加拿大': 'Canada', '罗马尼亚': 'Romania',
}
COUNTRY_ISO = {
    '法国': 'fr', '阿根廷': 'ar', '智利': 'cl', '乌拉圭': 'uy', '意大利': 'it',
    '新西兰': 'nz', '澳大利亚': 'au', '美国': 'us', '西班牙': 'es', '南非': 'za',
    '葡萄牙': 'pt', '德国': 'de', '奥地利': 'at', '匈牙利': 'hu', '希腊': 'gr',
    '格鲁吉亚': 'ge', '中国': 'cn', '日本': 'jp', '加拿大': 'ca', '罗马尼亚': 'ro',
}
# 接受的地点类型：真实到访点位，不含 boundary/place（行政区中心）
OK_CLASSES = {
    ('craft', 'winery'), ('shop', 'alcohol'), ('shop', 'wine'), ('shop', 'beverages'),
    ('shop', 'farm'), ('craft', 'brewery'), ('building', 'yes'), ('building', 'industrial'),
    ('building', 'farm'), ('landuse', 'vineyard'), ('amenity', 'restaurant'), ('amenity', 'cafe'),
    ('tourism', 'attraction'), ('tourism', 'museum'), ('office', 'company'), ('place', 'farm'),
}
OK_TYPES = {'winery', 'vineyard', 'wine', 'cellar'}

# 边界软约束的分级阈值（公里）。按 192 条界外实测点标定：最大值 55.8km，
# 取 80 = 1.43 倍。超过它不拒绝，只把 geoLevel 记成 'far' 供人工复核。
SOFT_TOL_KM = 80.0
# --strict-geo 时退回 2026-09-23 之前的硬拒绝口径（点必须在法定范围内）
STRICT_GEO = False


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def point_in_ring(pt, ring):
    x, y, inside = pt[1], pt[0], False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xint:
                inside = not inside
    return inside


def load_boundaries():
    path = ROOT / 'public' / 'region-boundaries.geojson'
    out = {}
    if not path.exists():
        return out
    gj = json.loads(path.read_text())
    for f in gj.get('features', []):
        rid = (f.get('properties') or {}).get('regionId')
        geom = f.get('geometry') or {}
        if not rid or not geom:
            continue
        polys = []
        if geom.get('type') == 'Polygon':
            polys = [geom['coordinates']]
        elif geom.get('type') == 'MultiPolygon':
            polys = geom['coordinates']
        rings = []
        for poly in polys:
            if poly:
                rings.append(poly[0])  # 只用外环
        if rings:
            out[rid] = rings
    return out


def load_anchors():
    """每个 region 已有坐标的中位数 + 自适应半径；同时返回按国家分组的坐标。"""
    cat = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
    pts, cpts = {}, {}
    for x in cat:
        if (x.get('type') or x.get('kind')) != 'winery':
            continue
        d = x.get('data') or {}
        lat, lng = d.get('lat'), d.get('lng')
        if lat is None or lng is None:
            continue
        coords = (float(lat), float(lng))
        pts.setdefault(d.get('regionId') or '', []).append(coords)
        cpts.setdefault(d.get('country') or '', []).append(coords)
    out = {}
    for rid, arr in pts.items():
        if len(arr) < 3:
            continue
        mlat = sorted(p[0] for p in arr)[len(arr) // 2]
        mlng = sorted(p[1] for p in arr)[len(arr) // 2]
        c = (mlat, mlng)
        ds = sorted(haversine(c, p) for p in arr)
        p90 = ds[int(len(ds) * 0.9)]
        out[rid] = {'center': c, 'radius': max(25.0, p90 * 1.5), 'n': len(arr)}
    return out, pts, cpts


def clean_addr(a):
    a = re.sub(r'[/|].*?(fax|t[eé]l|phone|mobile)\s*[:：].*$', '', a, flags=re.I)
    a = re.sub(r'(fax|t[eé]l|phone)\s*[:：]\s*[\d\s+().-]+', ' ', a, flags=re.I)
    a = re.sub(r'[\r\n\t]+', ' ', a)
    return re.sub(r'\s{2,}', ' ', a).strip(' ,/-')


def is_latin(s):
    return bool(s) and bool(re.fullmatch(r'[\x20-\x7E\u00C0-\u024F]+', s))


def region_name(rid):
    return (rid or '').replace('-', ' ').replace('_', ' ').strip().title()


def strong_name_match(producer, candidate):
    p, c = set(normalize(producer)), set(normalize(candidate))
    return bool(p) and p == c


def distance_to_rings_km(pt, rings):
    """点到边界（只用外环）的最近距离，单位公里。pt = (lat, lng)，ring 元素是 [lng, lat]。

    做法：先按 haversine 找最近顶点（O(n)），再对它两侧的线段做精确的点到线段距离。
    平面取以查询点为原点的等距圆柱近似 —— 以 pt 为中心时几百公里内的畸变 <0.15%，
    用来分级绰绰有余。**不引入 shapely/pyproj 依赖**，本脚本保持零 GIS 依赖可直接跑。
    """
    lat0, lng0 = pt
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    best = None
    for ring in rings:
        if len(ring) < 2:
            continue
        P = [((p[0] - lng0) * kx, (p[1] - lat0) * ky) for p in ring]   # p = [lng, lat]
        # 最近顶点：haversine 与欧氏在同一平面上单调等价，直接用欧氏挑
        i = min(range(len(P)), key=lambda j: P[j][0] ** 2 + P[j][1] ** 2)
        for j in (i, (i - 1) % len(P)):
            a, b = P[j], P[(j + 1) % len(P)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, (-a[0] * dx - a[1] * dy) / L2))
            d = math.hypot(a[0] + t * dx, a[1] + t * dy)
            if best is None or d < best:
                best = d
    return (best / 1000.0) if best is not None else float('inf')


def geo_ok(rid, country, lat, lng, boundaries, anchors, country_pts):
    """返回 (是否采用, 理由, 分级, 到边界距离km或None)。

    分级 geoLevel ∈ {'inside','soft','far','cluster','country','none'}。
    ⚠️ 有边界时**永远返回 True**（软约束，除非 --strict-geo）——原因见文件头。
    """
    if rid in boundaries:
        for ring in boundaries[rid]:
            if point_in_ring((lat, lng), ring):
                return True, 'inside_region_boundary', 'inside', 0.0
        d = distance_to_rings_km((lat, lng), boundaries[rid])
        if STRICT_GEO:
            return False, 'outside_region_boundary(%.1fkm)' % d, 'far', d
        # 界外：量距离、分级，但不拒绝。真正的闸门在 merge-geo-fill.py 的 30km 最近邻。
        if d <= SOFT_TOL_KM:
            return True, 'outside_region_boundary_soft(%.1fkm<=%.0fkm)' % (d, SOFT_TOL_KM), 'soft', d
        return True, 'outside_region_boundary_far(%.1fkm>%.0fkm)' % (d, SOFT_TOL_KM), 'far', d
    if rid in anchors:
        a = anchors[rid]
        d = haversine(a['center'], (lat, lng))
        if d <= a['radius']:
            return True, 'within_region_cluster(%.0fkm<=%.0fkm, n=%d)' % (d, a['radius'], a['n']), 'cluster', None
        return False, 'too_far_from_region(%.0fkm>%.0fkm)' % (d, a['radius']), 'none', None
    pts = country_pts.get(country) or []
    if len(pts) >= 3:
        mlat = sorted(p[0] for p in pts)[len(pts) // 2]
        mlng = sorted(p[1] for p in pts)[len(pts) // 2]
        d = haversine((mlat, mlng), (lat, lng))
        if d <= 300:
            return True, 'within_country_spread(%.0fkm)' % d, 'country', None
        return False, 'far_from_country(%.0fkm)' % d, 'none', None
    return False, 'no_reference', 'none', None


def main():
    global STRICT_GEO
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    if '--strict-geo' in sys.argv:
        STRICT_GEO = True
    items = json.loads(src.read_text())
    if limit:
        items = items[:limit]
    boundaries = load_boundaries()
    anchors, region_pts, country_pts = load_anchors()
    print('边界覆盖 %d 个 region（口径：%s，界外阈值 %.0fkm）；聚类参照 %d 个 region、%d 个国家' % (
        len(boundaries), '硬拒绝' if STRICT_GEO else '软约束', SOFT_TOL_KM,
        len(anchors), len(country_pts)), flush=True)

    results, done = [], set()
    if dst.exists():
        try:
            prev = json.loads(dst.read_text())
            ids = {i['id'] for i in items}
            results = [r for r in prev if r.get('id') in ids]
            done = {r['id'] for r in results}
            print('续跑：已完成 %d 条' % len(done), flush=True)
        except Exception:
            results, done = [], set()

    for idx, it in enumerate(items, 1):
        if it['id'] in done:
            continue
        addr = clean_addr(it.get('address') or '')
        nm = it['en'] if is_latin(it.get('en')) else it.get('name', '')
        ccn = COUNTRY_EN.get(it.get('country'), '')
        iso = COUNTRY_ISO.get(it.get('country'), '')
        rn = region_name(it.get('regionId'))
        rid = it.get('regionId') or ''
        variants = []
        if nm:
            variants.append(('name+region+country', ', '.join(x for x in [nm, rn, ccn] if x)))
            variants.append(('name+country', ', '.join(x for x in [nm, ccn] if x)))
        if len(addr) > 8:
            variants.append(('addr+region+country', ', '.join(x for x in [addr, rn, ccn] if x)))
            variants.append(('addr+country', ', '.join(x for x in [addr, ccn] if x)))

        hit, notes = None, []
        for tag, q in variants:
            params = {'q': q, 'format': 'json', 'limit': 5, 'addressdetails': 1, 'extratags': 1}
            if iso:
                params['countrycodes'] = iso
            rows = fetch(params)
            if isinstance(rows, dict) and rows.get('error'):
                notes.append('%s:ERR' % tag)
                continue
            for r in rows:
                cls, typ = r.get('class'), r.get('type')
                if not ((cls, typ) in OK_CLASSES or typ in OK_TYPES):
                    continue
                osmn = r.get('name') or ''
                if not (_cgm.name_match(nm, osmn) or _cgm.name_match(it.get('name', ''), osmn)):
                    continue
                ok, why, level, dist_km = geo_ok(rid, it.get('country') or '', float(r['lat']),
                                                 float(r['lon']), boundaries, anchors, country_pts)
                if not ok:
                    notes.append('%s:geo_reject(%s)' % (tag, why))
                    continue
                extra = r.get('extratags') or {}
                precision = 'OSM 实体「%s」（%s/%s），经地理校验（%s）；非地块边界' % (osmn, cls, typ, why)
                if level == 'far':
                    precision += '。⚠️ 该点落在法定范围外 %(d).1f 公里，超过软约束阈值 %(t).0f 公里，' \
                                 '位置待人工复核（酒商行的注册地常不在自家地块上）' % {'d': dist_km, 't': SOFT_TOL_KM}
                elif level == 'soft':
                    precision += '。注意：该点落在法定范围外 %(d).1f 公里（酒庄常注册在产区之外），' \
                                 '这是允许的，实测同产区 28.9%% 的已知点位都在界外' % {'d': dist_km}
                hit = {
                    'id': it['id'], 'name': it['name'], 'status': 'matched',
                    'matchedBy': tag, 'query': q,
                    'lat': float(r['lat']), 'lng': float(r['lon']),
                    'osmName': osmn, 'osmClass': cls, 'osmTypeDetail': typ,
                    'displayName': r.get('display_name'),
                    'geoCheck': why,
                    'geoLevel': level,
                    'geoDistanceToBoundaryKm': (round(dist_km, 2) if dist_km is not None else None),
                    'needsReview': level == 'far',
                    'website': extra.get('website') or extra.get('contact:website') or '',
                    'phone': extra.get('phone') or extra.get('contact:phone') or '',
                    'locationSourceURL': 'https://www.openstreetmap.org/%s/%s' % (
                        r.get('osm_type'), r.get('osm_id')),
                    'locationPrecision': precision,
                }
                break
            if hit:
                break
        if not hit:
            hit = {'id': it['id'], 'name': it['name'], 'status': 'not_found',
                   'lat': None, 'lng': None, 'notes': notes[:4]}
        results.append(hit)
        print('%3d/%d  %-40s %s' % (idx, len(items), (nm or it['name'])[:40],
                                    hit['status'] + ('  ' + str((round(hit['lat'], 5), round(hit['lng'], 5)))
                                                     if hit['status'] == 'matched' else '')), flush=True)
        if len(results) % 5 == 0:
            dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        time.sleep(1.1)
    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    matched = sum(1 for r in results if r.get('status') == 'matched')
    print('\n完成：%d 条，命中 %d（%.0f%%）-> %s' % (len(results), matched,
                                               100.0 * matched / max(1, len(results)), dst))
    # 按 geoLevel 分级播报：'far' 那批要人工看一眼，别混在正常命中里
    lv = {}
    for r in results:
        if r.get('status') == 'matched':
            lv[r.get('geoLevel') or 'n/a'] = lv.get(r.get('geoLevel') or 'n/a', 0) + 1
    if lv:
        print('地理分级：' + '，'.join('%s %d' % (k, v) for k, v in sorted(lv.items())))
        far = [r for r in results if r.get('needsReview')]
        if far:
            print('⚠️ 以下 %d 条落在法定范围外超过 %.0f 公里，标了 needsReview，落盘前请人工过一眼：'
                  % (len(far), SOFT_TOL_KM))
            for r in sorted(far, key=lambda x: -(x.get('geoDistanceToBoundaryKm') or 0))[:15]:
                print('   %-26s %-38s %6.1f km  %s' % (
                    (r.get('id') or '')[:26], (r.get('name') or '')[:38],
                    r.get('geoDistanceToBoundaryKm') or 0, r.get('matchedBy') or ''))


if __name__ == '__main__':
    main()
