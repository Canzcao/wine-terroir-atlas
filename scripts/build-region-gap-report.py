# coding: utf-8
"""产出「产区字段缺口清单」—— 每个产区还缺哪几列、每列的性质与可补路径。

为什么单独做一份
----------------
共建看板的 `regionGaps` 已经按优先级排好了序，但**看不出「这一列缺口的性质」**：
「别名 108 个」和「面积 61 个」在表格里长得一模一样，实际前者能从记录里派生、
后者里有 54 个是**采集时故意留的 null**（口径冲突/官网没给数字）。
凭看板直接派人去补，就会把「有意留空」当成「漏采」去做无用工，甚至为了凑数字编一个。

这份清单把每一列标上 **性质**：
  · 派生  —— 记录内已有已核实字段，脚本可补，零采集
  · 采集  —— 必须新抓数据（图/酒款/酒庄）
  · 调研  —— 必须找到具名权威来源 + 判口径（面积、大区边界）
  · 数据源 —— 需要整套 GIS 数据（非法国产区的边界）

用法
----
    python3 scripts/build-region-gap-report.py
产物：work/产区字段缺口清单.md
"""

import collections
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
PHOTOS = ROOT / 'public' / 'entity-photos.json'
BOUNDARIES = ROOT / 'public' / 'region-boundaries.geojson'
BOUNDARY_SOURCES = ROOT / 'data' / 'region-boundary-sources.json'
OUT = ROOT / 'work' / '产区字段缺口清单.md'

COLUMNS = ['坐标', '酒庄', '酒款', '图片', '面积', '边界文件', '来源', '别名', '本地语资料']
NATURE = {
    '坐标':   ('派生', '记录已有 lat/lng，缺了说明是采集遗漏'),
    '酒庄':   ('采集', '该产区名下 0 家酒庄 —— 要么补采，要么确认它本身不挂酒庄'),
    '酒款':   ('采集', '有酒庄但 0 款酒 —— 从酒庄官网/产品页补采'),
    '图片':   ('采集', '产区级与旗下酒庄合计 0 张 —— 需要走图片采集（用户已定为不着急）'),
    '面积':   ('调研', '⚠️ **只计真缺的**：有 areaNote 说明「口径冲突/官网未给」的按采集契约留 null，不算缺口'),
    '边界文件': ('数据源', '法国续用 INAO SIQO shapefile，澳洲用 Wine Australia GI；'
                 '⚠️ **只计真缺的**：官方只有比该产区更窄的几何时按铁律 §2 故意留白，不算缺口'),
    '来源':   ('派生', '记录已有 sourceURL'),
    '别名':   ('派生', '已由 scripts/fill-region-aliases.py 清零'),
    '本地语资料': ('派生', '已由 scripts/fill-region-localizations.py 清零'),
}


def main():
    recs = json.loads(SEED.read_text(encoding='utf-8'))
    recs = recs if isinstance(recs, list) else recs['records']
    regions = [r for r in recs if r.get('kind') == 'region']
    by_id = {r['id']: r for r in regions}
    wineries = [r for r in recs if r.get('kind') == 'winery']
    wines = [r for r in recs if r.get('kind') == 'wine']
    photos = (json.loads(PHOTOS.read_text(encoding='utf-8')).get('entities') or {})
    bounds = json.loads(BOUNDARIES.read_text(encoding='utf-8'))
    bounded = {(f.get('properties') or {}).get('regionId') or (f.get('properties') or {}).get('id')
               for f in (bounds.get('features') or [])}
    # 官方数据源里只有比该产区更窄的几何 → 按 import-region-boundaries.py 铁律 §2 故意留白。
    # 理由逐条记在 manifest 里，报告要把它抄出来，否则下一个人会把它们当漏采重复调研。
    _bnd = json.loads(BOUNDARY_SOURCES.read_text(encoding='utf-8'))
    abstained = _bnd.get('skipped') or {}                      # 按 region_id
    # unavailable 按国家键（官方渠道整体不可用），展开成该国全部 region_id
    unavailable_countries = _bnd.get('unavailable') or {}
    unavailable = {rid for rid, c in
                   ((r.get('id'), ((r.get('data') or {}).get('country') or '')) for r in regions)
                   if c in unavailable_countries}

    per_region_wineries = collections.Counter()
    for w in wineries:
        rid = (w.get('data') or {}).get('regionId')
        if rid:
            per_region_wineries[rid] += 1
    per_region_wines = collections.Counter()
    winery_region = {w['id']: (w.get('data') or {}).get('regionId') for w in wineries}
    for w in wines:
        d = w.get('data') or {}
        rid = d.get('regionId') or winery_region.get(d.get('wineryId'))
        if rid:
            per_region_wines[rid] += 1
    per_region_photos = collections.Counter()
    for w in wineries:
        rid = (w.get('data') or {}).get('regionId')
        n = len(photos.get(w['id'], []) or [])
        if rid and n:
            per_region_photos[rid] += n
    total_photos = lambda rid: len(photos.get(rid, []) or []) + per_region_photos.get(rid, 0)

    rows, gaps = [], collections.defaultdict(list)
    for r in regions:
        rid = r['id']
        d = r.get('data') or {}
        miss = []
        if d.get('lat') is None or d.get('lng') is None:
            miss.append('坐标')
        if per_region_wineries.get(rid, 0) == 0:
            miss.append('酒庄')
        if per_region_wines.get(rid, 0) == 0:
            miss.append('酒款')
        if total_photos(rid) == 0:
            miss.append('图片')
        if d.get('areaHectares') is None and not d.get('areaNote'):
            miss.append('面积')
        if rid not in bounded and rid not in abstained and rid not in unavailable:
            miss.append('边界文件')
        if not d.get('sourceURL'):
            miss.append('来源')
        if not d.get('aliases'):
            miss.append('别名')
        if not d.get('localizations'):
            miss.append('本地语资料')
        rows.append((rid, d.get('name'), d.get('country'), d.get('areaNote'), miss))
        for m in miss:
            gaps[m].append(rid)

    lines = ['# 产区字段缺口清单', '',
             f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}　·　产区 {len(regions)} 个', '',
             '## 一、按列汇总', '',
             '| 列 | 缺多少产区 | 性质 | 说明 |', '|---|---|---|---|']
    for c in COLUMNS:
        nature, note = NATURE[c]
        lines.append(f'| {c} | {len(gaps[c])} | {nature} | {note} |')
    full = [r for r in rows if not r[4]]
    lines += ['', f'**完全齐备的产区：{len(full)} 个**' + (f'　（{"、".join(r[0] for r in full)}）' if full else ''),
              '', '## 二、还缺「面积」的产区（只列真正没采的）', '',
              '口径：`areaHectares` 为空**且没有 `areaNote`** 才算缺口。',
              '有 areaNote 写明「各来源冲突 / 官网未给出公顷数」的，是采集契约下**有意的 null**，',
              '不是漏采 —— 拿它当待办会派出一堆完不成的活。', '',
              '| 产区 | 名称 | 官方名 | 国家 | 建议来源 |', '|---|---|---|---|---|']
    for rid, name, country, _n, miss in rows:
        if '面积' in miss and rid in by_id:
            d = by_id[rid].get('data') or {}
            lines.append(f'| {rid} | {name} | {d.get("en") or ""} | {country} | '
                         f'{d.get("sourceURL") or "（连 sourceURL 都没有）"} |')
    lines += ['', '## 三、还缺「边界文件」的产区', '',
              f'共 {len(gaps["边界文件"])} 个。已接入的**官方**来源：',
              '- 法国：INAO SIQO 地理范围 shapefile（EPSG:2154）',
              '- 澳大利亚：Wine Australia GI FeatureServer 图层 1',
              '- 美国：TTB AVA Map Explorer FeatureServer 图层 0（查询须带 `Status=\'Established\'`）',
              '- 新西兰：IPONZ GI 注册表 geodata ZIP（EPSG:4167）',
              '- 美国行政区：人口普查局 TIGERweb State_County 图层 1（**行政县界**，'
              '只用于 `boundaryType=administrative_county` 的兜底条目，不是法定葡萄酒产区范围）',
              '',
              '下载与导入：'
              '`scripts/fetch-national-boundaries.py`（下到 /tmp）→ '
              '`scripts/import-region-boundaries.py`（落 public/region-boundaries.geojson）。',
              '其余国家需要各自官方 GIS。', '']
    by_country = collections.defaultdict(list)
    for rid, name, country, _n, miss in rows:
        if '边界文件' in miss:
            by_country[country].append(rid)
    lines.append('| 国家 | 缺边界产区数 | 产区 |')
    lines.append('|---|---|---|')
    for c, ids in sorted(by_country.items(), key=lambda x: -len(x[1])):
        lines.append(f'| {c} | {len(ids)} | {"、".join(sorted(ids))} |')
    if abstained:
        lines += ['', f'### 已评估、**故意留白**的 {len(abstained)} 个（不算缺口，不必再找）', '',
                  '官方数据源里只有比该产区**更窄**或**对不上**的几何。套上去会把大区悄悄缩成一个法定产区，'
                  '所以按 `scripts/import-region-boundaries.py` 的铁律 §2 不导入。理由原文见 '
                  '`data/region-boundary-sources.json` 的 `skipped`：', '']
        for rid in sorted(abstained):
            lines.append(f'- **{rid}**：{abstained[rid]}')
    if unavailable:
        lines += ['', f'### 已调研、**官方渠道拿不到几何**的 {len(unavailable)} 个（不算缺口，先别重复调研）', '',
                  '| 国家 | 产区 | 调研结论 |', '|---|---|---|']
        for c in sorted(unavailable_countries):
            ids = sorted(rid for rid in unavailable
                         if ((by_id[rid].get('data') or {}).get('country') or '') == c)
            lines.append(f'| {c} | {len(ids)} 个：{"、".join(ids)} | {unavailable_countries[c]} |')
    admin = _bnd.get('administrativeFallbacks') or {}
    if admin:
        lines += ['', f'### 有边界、但用的是**官方行政县界**兜底的 {len(admin)} 个（不算「法定范围」，'
                      '也不算缺口）', '',
                  '这些条目在目录里的主体是**行政区**，官方没有任何等价的法定产区几何，'
                  '所以用美国人口普查局的官方县界兜底。已在 `boundaryType`（`administrative_county`）、'
                  '`label`（带「行政县界」字样）、`note`（写明「不是法定葡萄酒产区范围」）三处标明口径，'
                  '前端也画成**虚线**与法定产区区分。', '',
                  '| 产区 | 官方名称 | GEOID | 为什么不能用 AVA |', '|---|---|---|---|']
        for rid, v in sorted(admin.items()):
            why = (v.get('whyNotAProtectedArea') or '').replace('|', '\\|')
            lines.append(f'| {rid} | {v.get("officialName") or ""} | {v.get("sourceRecordId") or ""} | {why} |')
    lines += ['', '## 四、还缺「图片 / 酒款 / 酒庄」的产区', '',
              '| 产区 | 名称 | 国家 | 缺什么 |', '|---|---|---|---|']
    for rid, name, country, _n, miss in rows:
        need = [m for m in miss if m in ('图片', '酒款', '酒庄')]
        if need:
            lines.append(f'| {rid} | {name} | {country} | {"、".join(need)} |')
    lines.append('')

    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print('产区缺口清单 →', OUT)
    print(f'  完全齐备 {len(full)}/{len(regions)} 个产区')
    for c in COLUMNS:
        print(f'  缺 {c:8s} {len(gaps[c]):4d}')


if __name__ == '__main__':
    main()
