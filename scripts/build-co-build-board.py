# coding: utf-8
"""生成「待共建看板」数据：把整个资料库的收集状态摊平成一张大表。

三类（对应 Canz 的三个诉求）：
  1. 已收集  —— 按国家/产区聚合的覆盖情况（有多少、密度如何、能点到哪看）
  2. 需补充  —— 已入库但字段缺失（产区级 + 酒庄级明细，可直接拿去索要）
  3. 未收集  —— 19 国轮转队列里还没做的产区 + 候选产区 + 库内 0 酒庄的产区

产出：
  public/co-build-data.json                  线上看板数据（随部署上线）
  outputs/collect/_co-build/待共建总表.csv      明细（UTF-8 BOM，Excel 直接开）
  outputs/collect/_co-build/待共建总表.md       可读版
  outputs/collect/_co-build/看板摘要.json       机读摘要（给自动化读）

跑法：
  python3 scripts/build-co-build-board.py
幂等，可重复跑；只读 catalog，不写 catalog。
"""
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
ROTATION = ROOT / 'data' / 'country-rotation.json'
PROGRESS = ROOT / 'data' / 'collection-progress.json'
PHOTOS = ROOT / 'public' / 'entity-photos.json'
BOUNDARIES = ROOT / 'public' / 'region-boundaries.geojson'
BOUNDARY_SOURCES = ROOT / 'data' / 'region-boundary-sources.json'
OUT_JSON = ROOT / 'public' / 'co-build-data.json'
OUT_DIR = ROOT / 'outputs' / 'collect' / '_co-build'

# 缺失项排序：越靠前越该先动手（影响面 × 可执行性）
ORDER = ['坐标', '酒庄', '酒款', '图片', '面积', '边界文件',
         '邮箱', '联系人', '电话', '官网', '地址', '别名', '本地语资料', '来源']
# 每项的优先级归类
PRIORITY_OF = {
    '坐标': 'P0', '酒庄': 'P0',
    '酒款': 'P1', '图片': 'P1',
    '面积': 'P2', '边界文件': 'P2',
    '邮箱': 'P2', '联系人': 'P2', '电话': 'P2',
    '官网': 'P3', '地址': 'P3', '别名': 'P3', '本地语资料': 'P3', '来源': 'P3',
}
PRIORITY_LABEL = {
    'P0': 'P0 地图上不了（缺坐标/缺酒庄）',
    'P1': 'P1 内容空壳（缺酒款/缺图片）',
    'P2': 'P2 联系与边界（缺邮箱/电话/联系人/面积/边界）',
    'P3': 'P3 锦上添花（缺官网/地址/别名/多语言/来源）',
}


def load_json(p, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding='utf-8'))


def build():
    seed = load_json(SEED, [])
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    rotation = load_json(ROTATION, {}) or {}
    progress = load_json(PROGRESS, {}) or {}
    photos = (load_json(PHOTOS, {}) or {}).get('entities', {}) or {}

    regions = [r for r in recs if r.get('kind') == 'region']
    wineries = [r for r in recs if r.get('kind') == 'winery']
    wines = [r for r in recs if r.get('kind') == 'wine']
    vintages = [r for r in recs if r.get('kind') == 'vintage']
    grapes = [r for r in recs if r.get('kind') == 'grape']
    parcels = [r for r in recs if r.get('kind') == 'parcel']

    region_name = {r['id']: (r.get('data') or {}).get('name') or r.get('name') for r in regions}
    region_country = {r['id']: (r.get('data') or {}).get('country') or '' for r in regions}

    # 产区有边界文件的 id 集合
    bounds = load_json(BOUNDARIES, {}) or {}
    bounded = set()
    for f in (bounds.get('features') or []):
        rid = ((f.get('properties') or {}).get('regionId')) or ((f.get('properties') or {}).get('id'))
        if rid:
            bounded.add(rid)

    # ⚠️ 「边界文件」也不能只看有没有几何。
    # 2026-09-23：官方数据源里只有比该产区**更窄**的几何时（伯恩丘、罗讷河谷、索诺玛），
    # 按 scripts/import-region-boundaries.py 的铁律 §2「大区不能悄悄变成更小的法定产区」
    # 是**故意留白**的，理由逐条写在 data/region-boundary-sources.json 的 skipped 里。
    # 另有 unavailable：官方渠道（WMS 故障 / 无 WFS / ATOM 空 feed）确实拿不到几何的国家。
    # 拿这两类当待办会派出一堆无法完成的活——志愿者再找也找不到官方几何。所以真正缺的才计。
    _bnd_src = load_json(BOUNDARY_SOURCES, {}) or {}
    abstained = set(_bnd_src.get('skipped') or {})            # 按 region_id
    # unavailable 按**国家**键（官方渠道整体不可用，例如西班牙 MAPA 的 WMS 故障 + 无 WFS +
    # ATOM 空 feed），所以要展开成该国的全部 region_id 才能比对。
    unavailable_countries = set(_bnd_src.get('unavailable') or {})
    no_geometry = abstained | {rid for rid, c in region_country.items() if c in unavailable_countries}

    # 每个酒庄的酒款数 / 图片数
    wines_by_winery = Counter()
    for w in wines:
        wid = (w.get('data') or {}).get('wineryId')
        if wid:
            wines_by_winery[wid] += 1
    wines_by_region = Counter()
    wineries_by_region = Counter()
    for w in wineries:
        rid = (w.get('data') or {}).get('regionId')
        if rid:
            wineries_by_region[rid] += 1
    for w in wines:
        rid = (w.get('data') or {}).get('regionId')
        wid = (w.get('data') or {}).get('wineryId')
        if not rid and wid:
            rid = ((next((x for x in wineries if x['id'] == wid), {}) or {}).get('data') or {}).get('regionId')
        if rid:
            wines_by_region[rid] += 1
    photos_by_entity = {k: len(v) for k, v in photos.items() if isinstance(v, list)}
    # 图片实际挂在酒庄/酒款 id 上，产区自身的照片极少 —— 产区口径要累加其下所有酒庄，
    # 否则 97 个产区里会被误判 96 个「缺图片」。
    photos_by_region = Counter()
    for w in wineries:
        rid = (w.get('data') or {}).get('regionId')
        n = photos_by_entity.get(w['id'], 0)
        if rid and n:
            photos_by_region[rid] += n

    def region_photos(rid):
        return photos_by_entity.get(rid, 0) + photos_by_region.get(rid, 0)

    # ---------------- 1) 已收集：按国家聚合 ----------------
    countries = sorted({region_country[r['id']] for r in regions if region_country[r['id']]})
    collected = []
    for c in countries:
        rids = [r['id'] for r in regions if region_country[r['id']] == c]
        n_win = sum(wineries_by_region.get(x, 0) for x in rids)
        n_wine = sum(wines_by_region.get(x, 0) for x in rids)
        n_photo = sum(region_photos(x) for x in rids)
        n_coord = sum(1 for r in regions if region_country[r['id']] == c
                      and (r.get('data') or {}).get('lat') is not None)
        collected.append({
            'country': c, 'regions': len(rids), 'regionsWithCoord': n_coord,
            'wineries': n_win, 'wines': n_wine, 'photos': n_photo,
            'wineriesWithCoord': sum(
                1 for w in wineries
                if (w.get('data') or {}).get('regionId') in rids
                and (w.get('data') or {}).get('lat') is not None),
        })
    collected.sort(key=lambda x: -x['wineries'])

    # ---------------- 2) 需补充：产区级 ----------------
    region_rows = []
    for r in regions:
        rid = r['id']
        d = r.get('data') or {}
        missing = []
        if d.get('lat') is None or d.get('lng') is None:
            missing.append('坐标')
        if wineries_by_region.get(rid, 0) == 0:
            missing.append('酒庄')
        if wines_by_region.get(rid, 0) == 0:
            missing.append('酒款')
        if region_photos(rid) == 0:
            missing.append('图片')
        # ⚠️ 「面积」不能只看 areaHectares 是否为空。
        # 2026-09-23 实测：61 个缺 areaHectares 的产区里，**54 个的 areaNote 已写明**
        # 「各来源冲突 / 官网未给出公顷数 → 按契约留 null」，只有 7 个是真的没采。
        # 采集契约本来就是「宁可留 null 也不编数字」，所以**有 areaNote 说明的 null 不是缺口**，
        # 拿它当待办会派出一堆无法完成的活。真正缺的（无 areaNote）才计。
        if d.get('areaHectares') is None and not d.get('areaNote'):
            missing.append('面积')
        if rid not in bounded and rid not in no_geometry:
            missing.append('边界文件')
        if not (d.get('localizations') or {}):
            missing.append('本地语资料')
        if not d.get('sourceURL'):
            missing.append('来源')
        if not d.get('aliases'):
            missing.append('别名')
        if not missing:
            continue
        missing.sort(key=lambda x: ORDER.index(x) if x in ORDER else 99)
        prio = min((PRIORITY_OF.get(m, 'P3') for m in missing), default='P3')
        region_rows.append({
            'id': rid, 'name': d.get('name') or r.get('name'),
            'country': d.get('country') or '', 'missing': missing,
            'missingCount': len(missing), 'priority': prio,
            'wineries': wineries_by_region.get(rid, 0),
            'wines': wines_by_region.get(rid, 0),
            'photos': region_photos(rid),
            'hasCoord': d.get('lat') is not None,
        })
    region_rows.sort(key=lambda x: (x['priority'], -x['missingCount'], x['country'], x['name']))

    # ---------------- 2) 需补充：酒庄级 ----------------
    winery_rows = []
    for w in wineries:
        d = w.get('data') or {}
        rid = d.get('regionId')
        missing = []
        if d.get('lat') is None or d.get('lng') is None:
            missing.append('坐标')
        if wines_by_winery.get(w['id'], 0) == 0:
            missing.append('酒款')
        if photos_by_entity.get(w['id'], 0) == 0:
            missing.append('图片')
        if not d.get('email'):
            missing.append('邮箱')
        if not d.get('contactPerson'):
            missing.append('联系人')
        if not d.get('phone'):
            missing.append('电话')
        if not d.get('website'):
            missing.append('官网')
        if not d.get('address'):
            missing.append('地址')
        if not (d.get('localizations') or {}):
            missing.append('本地语资料')
        if not d.get('sourceURL'):
            missing.append('来源')
        if not missing:
            continue
        missing.sort(key=lambda x: ORDER.index(x) if x in ORDER else 99)
        prio = min((PRIORITY_OF.get(m, 'P3') for m in missing), default='P3')
        reachable = bool(d.get('website') or d.get('email'))
        if reachable and len(missing) <= 2:
            group = 'C 仅缺少量'
        elif reachable:
            group = 'A 可直接联系'
        else:
            group = 'B 需先找联系人'
        winery_rows.append({
            'id': w['id'], 'name': d.get('name') or w.get('name'),
            'country': d.get('country') or region_country.get(rid) or '',
            'region': region_name.get(rid, rid or ''),
            'missing': missing, 'missingCount': len(missing),
            'priority': prio, 'group': group,
            'wines': wines_by_winery.get(w['id'], 0),
            'images': photos_by_entity.get(w['id'], 0),
            'website': d.get('website') or '', 'email': d.get('email') or '',
        })
    winery_rows.sort(key=lambda x: (x['priority'], x['country'], -x['missingCount'], x['name']))

    # ---------------- 3) 未收集 ----------------
    pending_regions = []
    for c in rotation.get('queue', []):
        for r in c.get('regions', []):
            if r.get('status') in ('todo', 'recon-done', 'queued', 'partial'):
                pending_regions.append({
                    'country': c.get('country'), 'code': c.get('code'),
                    'id': r.get('id'), 'name': r.get('name'),
                    'status': r.get('status'), 'note': r.get('note') or '',
                    'languages': c.get('languages') or [],
                })
    todo_count = sum(1 for x in pending_regions if x['status'] == 'todo')

    candidates = []
    for c in rotation.get('queue', []):
        for r in c.get('candidateRegions', []) or []:
            candidates.append({
                'country': c.get('country'), 'code': c.get('code'),
                'id': r.get('id') if isinstance(r, dict) else str(r),
                'name': (r.get('name') if isinstance(r, dict) else str(r)),
                'note': (r.get('note') or '') if isinstance(r, dict) else '',
            })

    empty_regions = [x for x in region_rows if x['wineries'] == 0]
    # 队列顺序（下一轮优先）
    queue_rounds = []
    for c in rotation.get('queue', []):
        rs = [r for r in c.get('regions', []) if r.get('status') == 'todo']
        queue_rounds.append({
            'code': c.get('code'), 'country': c.get('country'),
            'todoRegions': [r.get('name') for r in rs],
            'candidates': len(c.get('candidateRegions', []) or []),
            'languages': c.get('languages') or [],
        })

    # ---------------- 汇总 ----------------
    total_photos = sum(photos_by_entity.values())
    totals = {
        'records': len(recs), 'region': len(regions), 'winery': len(wineries),
        'wine': len(wines), 'vintage': len(vintages), 'grape': len(grapes), 'parcel': len(parcels),
        'photos': total_photos, 'countries': len(countries),
        'regionsWithCoord': sum(1 for r in regions if (r.get('data') or {}).get('lat') is not None),
        'wineriesWithCoord': sum(1 for w in wineries if (w.get('data') or {}).get('lat') is not None),
        'regionsWithBoundary': len(bounded),
        'regionsBoundaryAbstained': sorted(abstained),
        'regionsBoundaryUnavailableCountries': sorted(unavailable_countries),
        # 有边界、但那条几何是**官方行政县界**（不是法定葡萄酒产区范围）的产区。
        # 它们**不算缺口**（边界文件那一列是有的），但要在看板上说明口径，
        # 否则志愿者会以为索诺玛县已经是 AVA 了。
        'regionsBoundaryAdministrative': sorted(_bnd_src.get('administrativeFallbacks') or {}),
        'needWork': len(region_rows) + len(winery_rows),
        'pendingRegions': len(pending_regions),
        'candidateRegions': len(candidates),
        'emptyRegions': len(empty_regions),
    }
    gap_counter = Counter(m for r in winery_rows for m in r['missing'])
    region_gap_counter = Counter(m for r in region_rows for m in r['missing'])

    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    payload = {
        'generatedAt': now.isoformat(timespec='seconds'),
        'generatedDate': now.strftime('%Y-%m-%d'),
        'generatedDisplay': now.strftime('%Y-%m-%d %H:%M'),
        'sources': {
            'catalog': 'data/catalog-seed.json',
            'rotation': 'data/country-rotation.json',
            'progress': 'data/collection-progress.json',
            'photos': 'public/entity-photos.json',
        },
        'progress': {
            'phase': (progress.get('current') or {}).get('phase') or '',
            'country': (progress.get('current') or {}).get('country') or '',
            'updatedAt': (progress.get('current') or {}).get('updatedAt') or '',
        },
        'columns': {
            'winery': ['id', 'name', 'country', 'region', 'missing', 'priority', 'group',
                       'wines', 'images', 'website', 'email'],
            'region': ['id', 'name', 'country', 'missing', 'priority',
                       'wineries', 'wines', 'photos', 'hasCoord'],
        },
        'totals': totals,
        'missingTotals': dict(gap_counter.most_common()),
        'regionMissingTotals': dict(region_gap_counter.most_common()),
        'priorityTotals': dict(Counter(r['priority'] for r in winery_rows)),
        'groupTotals': dict(Counter(r['group'] for r in winery_rows)),
        'priorityLabels': PRIORITY_LABEL,
        'collected': collected,
        'regionGaps': [[r[c] for c in ['id', 'name', 'country', 'missing', 'priority',
                                       'wineries', 'wines', 'photos', 'hasCoord']] for r in region_rows],
        'wineryGaps': [[r[c] for c in ['id', 'name', 'country', 'region', 'missing', 'priority',
                                       'group', 'wines', 'images', 'website', 'email']]
                       for r in winery_rows],
        'pendingRegions': pending_regions,
        'queueRounds': queue_rounds,
        'candidates': candidates,
        'emptyRegions': [[x['id'], x['name'], x['country']] for x in empty_regions],
        'todoCount': todo_count,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                        encoding='utf-8')

    # ---------------- 明细导出 ----------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prio_rank = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
    csv_path = OUT_DIR / '待共建总表.csv'
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        wr = csv.writer(f)
        wr.writerow(['类型', '优先级', '国家', '产区', '名称', '缺失项', '缺几项',
                     '分组', '酒款数', '图片数', '官网', '邮箱', '记录ID'])
        for r in sorted(region_rows, key=lambda x: (prio_rank[x['priority']], -x['missingCount'])):
            wr.writerow(['产区', r['priority'], r['country'], r['name'], r['name'],
                         '、'.join(r['missing']), r['missingCount'], '', r['wines'],
                         r['photos'], '', '', r['id']])
        for r in sorted(winery_rows, key=lambda x: (prio_rank[x['priority']], x['country'], -x['missingCount'])):
            wr.writerow(['酒庄', r['priority'], r['country'], r['region'], r['name'],
                         '、'.join(r['missing']), r['missingCount'], r['group'],
                         r['wines'], r['images'], r['website'], r['email'], r['id']])
        for p in pending_regions:
            wr.writerow(['未收集产区', 'P0', p['country'], p['name'], p['name'],
                         '整条资料未采集', '', '', '', '', '', '', p['id'] or ''])
        for c in candidates:
            wr.writerow(['候选产区', 'P1', c['country'], c['name'], c['name'],
                         '整条资料未采集', '', '', '', '', '', '', c['id']])

    md = ['# 待共建总表（风土图鉴）', '',
          '> 生成时间：%s ｜ 数据源：`data/catalog-seed.json`（%d 条记录）'
          % (payload['generatedDisplay'], len(recs)), '',
          '## 总览', '',
          '| 指标 | 数量 |', '| --- | --- |',
          '| 已收录记录 | %d |' % totals['records'],
          '| 产区 | %d（有坐标 %d / 有边界 %d） |' % (totals['region'], totals['regionsWithCoord'], totals['regionsWithBoundary']),
          '| 酒庄 | %d（有坐标 %d） |' % (totals['winery'], totals['wineriesWithCoord']),
          '| 酒款 | %d |' % totals['wine'],
          '| 年份酒 | %d |' % totals['vintage'],
          '| 葡萄品种 | %d |' % totals['grape'],
          '| 图片 | %d |' % totals['photos'],
          '| 覆盖国家 | %d |' % totals['countries'],
          '| **待补产区** | **%d** |' % len(region_rows),
          '| **待补酒庄** | **%d** |' % len(winery_rows),
          '| **未采集产区（队列）** | **%d**（其中 todo %d） |' % (len(pending_regions), todo_count),
          '| 候选产区 | %d |' % len(candidates),
          '', '## 优先级分布（酒庄）', '',
          '| 优先级 | 酒庄数 | 含义 |', '| --- | --- | --- |']
    for k in ('P0', 'P1', 'P2', 'P3'):
        md.append('| %s | %d | %s |' % (k, payload['priorityTotals'].get(k, 0), PRIORITY_LABEL[k]))
    md += ['', '## 缺失项分布（酒庄）', '', '| 缺失项 | 涉及酒庄数 |', '| --- | --- |']
    for k, v in sorted(gap_counter.items(), key=lambda x: -x[1]):
        md.append('| %s | %d |' % (k, v))
    md += ['', '## 缺失项分布（产区）', '', '| 缺失项 | 涉及产区数 |', '| --- | --- |']
    for k, v in sorted(region_gap_counter.items(), key=lambda x: -x[1]):
        md.append('| %s | %d |' % (k, v))
    md += ['', '## 按国家（已收集密度）', '',
           '| 国家 | 产区 | 产区有坐标 | 酒庄 | 酒庄有坐标 | 酒款 | 图片 |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for c in collected:
        md.append('| %s | %d | %d | %d | %d | %d | %d |' % (
            c['country'], c['regions'], c['regionsWithCoord'], c['wineries'],
            c['wineriesWithCoord'], c['wines'], c['photos']))
    md += ['', '## 下一轮队列（19 国轮转）', '', '| 顺序 | 国家 | 本次待做产区 | 候选产区 |', '| --- | --- | --- | --- |']
    for i, q in enumerate(queue_rounds, 1):
        md.append('| %d | %s | %s | %d |' % (i, q['country'], '、'.join(q['todoRegions']) or '—', q['candidates']))
    md += ['', '> 明细见同目录 `待共建总表.csv`（Excel 直接开）；线上看板见 https://terroir.vincode.chat/community →「待共建清单」。']
    (OUT_DIR / '待共建总表.md').write_text('\n'.join(md) + '\n', encoding='utf-8')

    (OUT_DIR / '看板摘要.json').write_text(json.dumps({
        'generatedAt': payload['generatedAt'], 'totals': totals,
        'priorityTotals': payload['priorityTotals'], 'groupTotals': payload['groupTotals'],
        'missingTotals': payload['missingTotals'],
        'regionMissingTotals': payload['regionMissingTotals'],
        'todoRegions': todo_count,
    }, ensure_ascii=False, indent=1), encoding='utf-8')

    print('记录 %d 条 ｜ 待补产区 %d ｜ 待补酒庄 %d ｜ 未采集产区 %d（todo %d）｜ 候选 %d'
          % (len(recs), len(region_rows), len(winery_rows), len(pending_regions), todo_count, len(candidates)))
    documented_null = sum(1 for r in regions
                          if (r.get('data') or {}).get('areaHectares') is None
                          and (r.get('data') or {}).get('areaNote'))
    if documented_null:
        print('面积：另有 %d 个产区 areaNote 已说明口径冲突/官网未给，按采集契约留 null，不计缺口'
              % documented_null)
    if abstained:
        print('边界：另有 %d 个产区（%s）官方只有更窄的几何，按铁律 §2 故意留白，不计缺口'
              % (len(abstained), '、'.join(sorted(abstained))))
    if unavailable_countries:
        n_un = len(no_geometry) - len(abstained)
        print('边界：另有 %d 个产区因所在国（%s）官方渠道拿不到几何，已记录原因，不计缺口'
              % (n_un, '、'.join(sorted(unavailable_countries))))
    _admin = sorted(_bnd_src.get('administrativeFallbacks') or {})
    if _admin:
        print('边界：另有 %d 个产区（%s）用**官方行政县界**兜底（目录主体是行政区，无等价法定产区几何），'
              '已标注 boundaryType=administrative_county，不计缺口' % (len(_admin), '、'.join(_admin)))
    print('优先级：', payload['priorityTotals'])
    print('产出：%s' % OUT_JSON)
    print('产出：%s' % OUT_DIR)


if __name__ == '__main__':
    build()
