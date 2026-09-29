# coding: utf-8
"""把三条坐标补全通道的结果合并回 data/catalog-seed.json。

通道与优先级（高 → 低）：
  1. work/geo-fill-results.json      OSM/Nominatim 名称通道 —— 证据最强（OSM 里就是这座酒庄）
  2. work/geo-fill-web-results.json  酒庄官网地图嵌入坐标
  3. work/geo-fill-addr-results.json 登记地址解析 —— 分两档：
        precise（门牌级，不加 locationApproximate）
        approx （街道／城镇级，加 locationApproximate:true）

铁律：
  · **绝不覆盖已有坐标**。目标条目 data.lat 非空即跳过。
  · 只写 lat / lng / locationSourceURL / locationPrecision / locationApproximate，
    外加 checkedDate 与 verification 两个溯源字段。不碰名称、简介、别名、来源。
  · 顶层 version+1、updated 刷新；**origin 原样保留**（补坐标不改变条目出处）。
  · 落盘前先写带时间戳的备份，便于与并发的其他会话对账。

第 4 道护栏（本文件新增）—— **同产区最近邻距离**：
    新坐标必须落在「同产区已有坐标的某个酒庄」30km 以内。
    为什么前面三道拦不住、非要加这一道：
      · 250km 聚类半径封顶对大而稀疏的产区形同虚设（salta 的已知酒庄聚在
        Cafayate，半径 224km / mendoza 473km）。
      · 于是 salta 有 11 家企业把「萨尔塔省会的注册办公地址」当成酒庄位置填了进来，
        中位偏离 154km；EL ESTECO、QUEBRADA DE LAS FLECHAS 更是双双落到
        191km 外圣安东尼奥德洛斯科布雷斯一段 Ruta 40 上（地址只写「Ruta 40 y 60」）。
      · 反过来，cornas / condrieu / saint-péray 这类只有百来公顷的小产区，
        街道名重名会把点甩到 36–49km 外（已核实 9 条 cornas 全是误配）。
    阈值 30km 是实测标定出来的：已定位酒庄的「同产区最近邻」距离
    中位 1.3km / P90 8.2km / P95 20.2km，95% 的正当点位都在 20km 内。
    取 30km 会砍 15 条，其中 13 条已逐条核实为误配；代价是误伤 2 条正当点位
    （brunello 的 Argiano 57km、mosel 的露森酒庄 31km，两者都因所在产区
    已知点太稀疏而显得「孤立」）。这个交换判断是划算的 —— 被误伤的那两条
    会老实显示「位置待核对」，而误配的点位会把用户带到另一个城市。
    用 --keep-far 可关掉本护栏。

用法:
    python3 scripts/merge-geo-fill.py            # 只出报告，不改文件
    python3 scripts/merge-geo-fill.py --apply    # 落盘
    python3 scripts/merge-geo-fill.py --apply --no-approximate
        # 只落「门牌级／OSM 实体／官网地图」这三类强证据坐标，
        # 丢弃地址只解析到街道／城镇级的那些（locationApproximate:true）。
        # 采集包的交接红线写的正是「不要把行政村中心当酒庄位置」，
        # 所以这个开关是那条红线的执行口 —— 想退回严格口径时用它，不用改代码。
    python3 scripts/merge-geo-fill.py --keep-far
        # 关掉「同产区最近邻 30km」护栏（默认开启）
"""
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
SOURCES = [
    ('osm', ROOT / 'work' / 'geo-fill-results.json', 'geo-fill:osm'),
    ('web', ROOT / 'work' / 'geo-fill-web-results.json', 'geo-fill:website'),
    ('addr', ROOT / 'work' / 'geo-fill-addr-results.json', 'geo-fill:address'),
]

# 同产区最近邻闸门（见文件头说明）。改这个数之前先把 audit-geo-fill.py 跑一遍。
NEAREST_KM = 30.0


def haversine(lat1, lng1, lat2, lng2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def known_points_by_region(cat):
    """种子库里**已经有坐标**的酒庄，按产区归堆 —— 这就是闸门的参照系。"""
    pts = {}
    for e in cat:
        d = e.get('data') or {}
        if e.get('kind') == 'winery' and d.get('lat') is not None:
            pts.setdefault(d.get('regionId'), []).append(
                (float(d['lat']), float(d['lng'])))
    return pts


def nearest_km(pts, rid, lat, lng):
    """到同产区最近一个已知酒庄的距离。产区里一个已知点都没有时返回 None（无法判断）。"""
    group = pts.get(rid) or []
    if not group:
        return None
    return min(haversine(lat, lng, a, b) for a, b in group)


def load(path):
    if not path.exists():
        print('  （跳过，文件不存在：%s）' % path.name)
        return []
    try:
        data = json.loads(path.read_text())
    except Exception as err:  # noqa: BLE001
        print('  （跳过，解析失败：%s：%s）' % (path.name, err))
        return []
    return data if isinstance(data, list) else []


def main():
    apply = '--apply' in sys.argv
    allow_approx = '--no-approximate' not in sys.argv
    keep_far = '--keep-far' in sys.argv
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    today = datetime.now().astimezone().strftime('%Y-%m-%d')

    cat = json.loads(SEED.read_text())
    by_id = {e['id']: e for e in cat}
    known_pts = known_points_by_region(cat)
    before_with = sum(1 for e in cat if e.get('kind') == 'winery'
                      and (e.get('data') or {}).get('lat') is not None)

    stats = {}
    # 记录每个被改成什么，方便打印与逐条复核
    log = []
    claimed = {}  # id -> channel，用于统计「谁最终拿到这条」
    far_cut = []  # 被最近邻闸门挡下的

    for name, path, method in SOURCES:
        rows = load(path)
        hit = skip_existing = miss = 0
        for r in rows:
            if r.get('status') != 'matched' or r.get('lat') is None:
                miss += 1
                continue
            e = by_id.get(r.get('id'))
            if e is None or e.get('kind') != 'winery':
                continue
            d = e.setdefault('data', {})
            if d.get('lat') is not None:
                skip_existing += 1
                continue
            if r['id'] in claimed:
                # 高优先级通道已经写过了，本轮不再覆盖
                skip_existing += 1
                continue
            if not (-90 <= float(r['lat']) <= 90 and -180 <= float(r['lng']) <= 180):
                continue
            tier = r.get('tier') or ''
            if r.get('locationApproximate') is True and not allow_approx:
                stats.setdefault(name, {}).setdefault('dropped_approx', 0)
                stats[name]['dropped_approx'] = stats[name].get('dropped_approx', 0) + 1
                continue
            # 第 4 道护栏：同产区最近邻（见文件头）。参照系是「落盘前」已知的酒庄坐标，
            # 本轮新写入的点不参与 —— 否则先写进去的错点会把附近的错点一起「洗白」。
            if not keep_far:
                rid = d.get('regionId')
                nn = nearest_km(known_pts, rid, float(r['lat']), float(r['lng']))
                if nn is not None and nn > NEAREST_KM:
                    far_cut.append((nn, name, rid, r.get('id'), r.get('name')))
                    continue
            d['lat'] = float(r['lat'])
            d['lng'] = float(r['lng'])
            if r.get('locationSourceURL'):
                d['locationSourceURL'] = r['locationSourceURL']
            if r.get('locationPrecision'):
                d['locationPrecision'] = r['locationPrecision']
            if r.get('locationApproximate') is True:
                d['locationApproximate'] = True
            elif name == 'addr' and tier == 'precise':
                d.pop('locationApproximate', None)
            if r.get('website') and not d.get('website'):
                d['website'] = r['website']
            d['checkedDate'] = today
            v = d.get('verification')
            v = v if isinstance(v, dict) else {}
            v['method'] = method
            v['checkedDate'] = today
            v.setdefault('status', 'ok')
            d['verification'] = v
            e['version'] = int(e.get('version') or 1) + 1
            e['updated'] = now
            claimed[r['id']] = name
            hit += 1
            log.append((name, tier or '-', r['id'], r.get('name'),
                        round(float(r['lat']), 5), round(float(r['lng']), 5),
                        (r.get('geoCheck') or '')[:46]))
        stats[name] = {'hit': hit, 'skip_existing': skip_existing,
                       'not_matched': miss, 'total': len(rows)}

    after_with = sum(1 for e in cat if e.get('kind') == 'winery'
                     and (e.get('data') or {}).get('lat') is not None)
    total_winery = sum(1 for e in cat if e.get('kind') == 'winery')

    print('\n=== 通道命中与写入 ===')
    for name, path, method in SOURCES:
        s = stats.get(name) or {}
        print('  %-5s 结果 %4d 条 | 未命中 %4d | 新增坐标 %4d | 已有坐标跳过 %4d%s'
              % (name, s.get('total', 0), s.get('not_matched', 0),
                 s.get('hit', 0), s.get('skip_existing', 0),
                 (' | 按严格口径丢弃约略坐标 %d' % s['dropped_approx'])
                 if s.get('dropped_approx') else ''))
    print('\n=== 覆盖率 ===')
    print('  酒庄总数 %d' % total_winery)
    print('  有坐标  %d -> %d（%.1f%% -> %.1f%%）'
          % (before_with, after_with, 100.0 * before_with / total_winery,
             100.0 * after_with / total_winery))
    ap = sum(1 for e in cat if e.get('kind') == 'winery'
             and (e.get('data') or {}).get('locationApproximate') is True)
    print('  其中标为「约略位置」 %d 条，精确 %d 条' % (ap, after_with - ap))

    if far_cut and not keep_far:
        far_cut.sort(key=lambda x: -x[0])
        print('\n=== 同产区最近邻闸门（>%.0fkm）挡下 %d 条 ===' % (NEAREST_KM, len(far_cut)))
        for nn, name, rid, rid_e, nm in far_cut:
            print('  %-5s %-18s %-34s 离同产区最近酒庄 %5.0fkm' % (
                name, (rid or '-')[:18], (nm or '')[:34], nn))

    logfile = ROOT / 'work' / 'geo-fill-merge-log.json'
    logfile.write_text(json.dumps(
        {'generated': now, 'applied': apply, 'stats': stats,
         'winery_total': total_winery, 'with_coords_before': before_with,
         'with_coords_after': after_with, 'approximate': ap,
         'nearest_km_gate': None if keep_far else NEAREST_KM,
         'far_cut': [{'channel': c, 'regionId': rid, 'id': i, 'name': nm,
                      'nearestKm': round(nn, 1)} for nn, c, rid, i, nm in far_cut],
         'entries': [dict(zip(['channel', 'tier', 'id', 'name', 'lat', 'lng', 'geoCheck'], r))
                     for r in log]},
        ensure_ascii=False, indent=1))
    print('  明细已写 work/%s（%d 条）' % (logfile.name, len(log)))

    if not apply:
        print('\n（未落盘。加 --apply 才会写回 %s）' % SEED.name)
        print('\n=== 前 20 条明细 ===')
        for row in log[:20]:
            print('  %-5s %-7s %-32s %-22s %s,%s  %s' % row)
        return

    backup = ROOT / 'work' / ('_catalog-seed.before-geo-fill-%s.json' % today)
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(cat, ensure_ascii=False, indent=1))
    print('\n已落盘。备份：%s' % backup.relative_to(ROOT))


if __name__ == '__main__':
    main()
