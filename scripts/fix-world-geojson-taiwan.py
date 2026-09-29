"""把 world.geojson 里的台湾岛并入中国，并删除「中华民国」这一独立国家要素。

背景：public/assets/world.geojson 是从 Natural Earth 110m 精简出的中文版，
Natural Earth 原始数据把台湾单列为一个 admin-0 country（NAME_ZH=中华民国）。
但同一份 Natural Earth 数据里，台湾的 ADM0_A3_CN = 'CHN'、
FCLASS_CN = 'Admin-1 states provinces'——按中国口径台湾是省级行政单位。
该文件通过 /assets/world.geojson 公开可访问，必须按一个中国原则修正。

同时把要素名「中华人民共和国」改成「中国」：前端 map-drilldown.js 用
`countries.has(f.properties.name)` 过滤国家高亮，而 countries 集合来自
catalog 的国家名（'中国'）。原名对不上，导致点「中国」时整片不亮——
这是本次一并修掉的既有 bug。

跑法：python3 scripts/fix-world-geojson-taiwan.py
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import os as _os
BASE = Path(_os.environ.get('TERROIR_ROOT', Path(__file__).resolve().parent.parent))
WP = BASE / 'public/assets/world.geojson'

OLD_CN = '中华人民共和国'
TW = '中华民国'
NEW_CN = '中国'


def bbox_of(geom):
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for k in c:
                walk(k)
    walk(geom['coordinates'])
    return [min(xs), min(ys), max(xs), max(ys)]


def ring_contains(ring, x, y):
    """射线法：点 (x,y) 是否在 ring（[[lng,lat],...]）内部。"""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def verts(geom):
    out = []

    def walk(c):
        if isinstance(c[0], (int, float)):
            out.append((c[0], c[1]))
        else:
            for k in c:
                walk(k)
    walk(geom['coordinates'])
    return out


def exterior_rings(geom):
    """返回几何的各多边形外环。MultiPolygon: [[ring,...],...]；Polygon: [ring,...]。"""
    coords = geom['coordinates']
    if geom['type'] == 'Polygon':
        return [coords[0]]
    return [poly[0] for poly in coords]


def interiors_overlap(a, b):
    """两个几何的内部是否交叠：任一顶点落在对方内部即判交叠。

    台湾是离岸约 150km 的岛，与大陆多边形只有顶点级别的关系，
    没有顶点互含就意味着内部不交叠，MultiPolygon 直接拼接合法。
    """
    for (x, y) in verts(a):
        for ring in exterior_rings(b):
            if ring_contains(ring, x, y):
                return True
    for (x, y) in verts(b):
        for ring in exterior_rings(a):
            if ring_contains(ring, x, y):
                return True
    return False


def main():
    raw = WP.read_text(encoding='utf-8')
    gj = json.loads(raw)

    idx_cn = next(i for i, f in enumerate(gj['features']) if f['properties']['name'] == OLD_CN)
    idx_tw = next(i for i, f in enumerate(gj['features']) if f['properties']['name'] == TW)
    cn = gj['features'][idx_cn]
    tw = gj['features'][idx_tw]

    assert cn['geometry']['type'] == 'MultiPolygon', cn['geometry']['type']
    assert tw['geometry']['type'] == 'Polygon', tw['geometry']['type']
    before = len(cn['geometry']['coordinates'])
    tw_polys = [tw['geometry']['coordinates']]

    # 先确认两个几何内部不交叠，MultiPolygon 才能直接拼接
    assert not interiors_overlap(cn['geometry'], tw['geometry']), \
        '中国与台湾的多边形内部交叠，需改用真正的并集运算：cn=%s tw=%s' % (
            bbox_of(cn['geometry']), bbox_of(tw['geometry']))

    cn['geometry']['coordinates'] = cn['geometry']['coordinates'] + tw_polys
    cn['properties']['name'] = NEW_CN
    if 'bbox' in cn:
        cn['bbox'] = bbox_of(cn['geometry'])

    gj['features'].pop(idx_tw)

    # 备份必须写到 work/ 而不是 public/——public/ 下的任何文件都会随部署上线
    backup_dir = BASE / 'work'
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / ('world.geojson.bak-%s' % datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    shutil.copy2(WP, backup)

    WP.write_text(json.dumps(gj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    # ---- 落盘后自检 ----
    gj2 = json.loads(WP.read_text(encoding='utf-8'))
    names = [f['properties']['name'] for f in gj2['features']]
    assert TW not in names, '「%s」要素没删干净' % TW
    assert OLD_CN not in names, '「%s」要素没改名' % OLD_CN
    assert NEW_CN in names, '「%s」要素不存在' % NEW_CN
    cn2 = next(f for f in gj2['features'] if f['properties']['name'] == NEW_CN)
    print('feature 数 %d -> %d' % (len(gj['features']) + 1, len(gj2['features'])))
    print('中国 polygon 数 %d -> %d（新增台湾岛，bbox %s）'
          % (before, len(cn2['geometry']['coordinates']),
             [round(v, 3) for v in bbox_of(cn2['geometry'])]))
    print('「%s」是否还在: %s' % (TW, TW in names))
    print('文件大小 %.1f KB -> %.1f KB' % (len(raw.encode()) / 1024, len(WP.read_bytes()) / 1024))
    print('备份:', backup.name)


if __name__ == '__main__':
    main()
