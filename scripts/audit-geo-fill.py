# coding: utf-8
"""坐标补全落盘后的抽查工具：把新写进去的坐标逐条摆出来，附「离目标产区多远」。

为什么需要它：
  约略档（locationApproximate:true）踩在采集包交接红线的边上 ——
  红线写着「不要把行政村中心当酒庄位置」。光看「命中 386 条」判断不了这件事，
  必须看到「这条坐标落在哪个产区、离产区边界/中心多少公里」才好判。
  这个脚本就是那条红线的量尺。

用法:
    python3 scripts/audit-geo-fill.py              # 汇总 + 最远的 25 条
    python3 scripts/audit-geo-fill.py --all        # 全部明细
    python3 scripts/audit-geo-fill.py --far 100    # 只看离产区 >100km 的
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def haversine(a, b, c, d):
    r = 6371.0088
    p1, p2 = math.radians(a), math.radians(c)
    dp = p2 - p1
    dl = math.radians(d - b)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def main():
    show_all = '--all' in sys.argv
    far_gate = None
    if '--far' in sys.argv:
        far_gate = float(sys.argv[sys.argv.index('--far') + 1])

    cat = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
    by_id = {e['id']: e for e in cat}

    # 产区代表点：用已有坐标的 region 条目；没有则退到该产区已定位酒庄的中位数
    regions, winery_pts = {}, {}
    for e in cat:
        d = e.get('data') or {}
        if d.get('lat') is None:
            continue
        if e.get('kind') == 'region':
            regions[e['id']] = (float(d['lat']), float(d['lng']))
        elif e.get('kind') == 'winery':
            winery_pts.setdefault(d.get('regionId'), []).append((float(d['lat']), float(d['lng'])))

    def region_center(rid):
        if rid in regions:
            return regions[rid]
        pts = winery_pts.get(rid) or []
        if not pts:
            return None
        lat = sorted(p[0] for p in pts)[len(pts) // 2]
        lng = sorted(p[1] for p in pts)[len(pts) // 2]
        return (lat, lng)

    log = json.loads((ROOT / 'work' / 'geo-fill-merge-log.json').read_text())
    entries = log.get('entries') or []
    print('=== 本轮新写入坐标 %d 条（channel / tier 拆分）===' % len(entries))
    from collections import Counter
    print('  按通道:', dict(Counter(e['channel'] for e in entries)))
    print('  按精度:', dict(Counter(e['tier'] for e in entries)))

    rows = []
    for e in entries:
        ent = by_id.get(e['id'])
        if not ent:
            continue
        d = ent.get('data') or {}
        rid = d.get('regionId')
        rc = region_center(rid)
        dist = None
        if rc and d.get('lat') is not None:
            dist = haversine(rc[0], rc[1], float(d['lat']), float(d['lng']))
        rows.append((dist if dist is not None else -1, e, rid, d))

    if far_gate is not None:
        rows = [r for r in rows if r[0] > far_gate]
        print('\n=== 离产区中心 >%.0fkm 的 %d 条 ===' % (far_gate, len(rows)))

    rows.sort(key=lambda r: -r[0])
    limit = len(rows) if show_all else 25
    print('\n%-7s %-9s %-30s %-14s %8s  %s' % ('通道', '精度', '酒庄', '产区', '离产区km', '坐标'))
    for dist, e, rid, d in rows[:limit]:
        print('%-7s %-9s %-30s %-14s %8s  %s,%s' % (
            e['channel'], e['tier'],
            (e.get('name') or '')[:30], (rid or '-')[:14],
            ('%.0f' % dist) if dist >= 0 else '?',
            round(float(d['lat']), 4), round(float(d['lng']), 4)))

    if rows:
        ds = [r[0] for r in rows if r[0] >= 0]
        if ds:
            ds.sort()
            n = len(ds)
            print('\n离产区中心距离：中位数 %.0fkm，P90 %.0fkm，最大 %.0fkm'
                  % (ds[n // 2], ds[int(n * 0.9)], ds[-1]))
            over = len([x for x in ds if x > 60])
            print('  其中 >60km 的 %d 条（%.1f%%）—— 这部分看得最紧' % (over, 100.0 * over / n))


if __name__ == '__main__':
    main()
