# coding: utf-8
"""把官方 GIS 快照转成 public/region-boundaries.geojson 与 data/region-boundary-sources.json。

依赖 pyshp / pyproj / shapely。**必须用装了这三个包的解释器运行**
（托管 Python 常不带 GIS 库，请建 venv 后 pip install pyshp pyproj shapely）。

输入（只读；全部是官方公布的图形快照，不入库、不进版本库）：
  1. INAO SIQO «Délimitation des aires géographiques des SIQO»（data.gouv.fr）
     shapefile，投影 EPSG:2154。一份文件覆盖全部法国 AOC / IGP，不按产区拆分。
     取 /tmp/terroir-inao/ 下最新的 *delim-aire-geographique-shp.shp。
  2. Wine Australia «Wine Geographical Indications Australia»（ArcGIS FeatureServer）
     图层 1 = Regions（64 个），GeoJSON，EPSG:4326。取 /tmp/aus-gi-regions.geojson。
  3. 美国 TTB «AVA Map Explorer»（ArcGIS FeatureServer 图层 0 = AVA_Polygons_gen2pt5m_WMAS），
     按 Name=… AND Status='Established' 逐条精确查询，落到 /tmp/terroir-us/<region_id>.geojson。
  4. 新西兰 IPONZ GI 注册表，每个 GI 一个 geodata zip（内含 shapefile，EPSG:4167），
     解压到 /tmp/terroir-nz/<GI>-GI-boundary/。
  5. 美国人口普查局 TIGERweb「州与县」图层 1 = Counties，按 GEOID 逐县精确查询，
     落到 /tmp/terroir-us-county/<region_id>.geojson。**这是行政边界，只在
     「目录里其实是县、官方又没有对应 AVA」时兜底用**，boundaryType 与 AVA 严格区分，
     label 与 note 必须写明它不是法定葡萄酒产区范围。

以上 2~5 的快照都由 scripts/fetch-national-boundaries.py 下载（不许手工 curl）。

四条铁律（改这个文件之前先读 tests/region-boundaries.test.mjs）：
  §1 从不从酒庄点位、视口范围或行政区反推多边形。只接受官方公布的图形。
     （唯一的例外是 §4 的行政县界兜底：它不是反推来的，是官方公布的实体边界，
     但必须在 boundaryType / label / note 三处都标明它不是葡萄酒产区法定范围。）
  §2 大区不能悄悄变成更小的法定产区。官方只给得出更窄的 AOC 图形时，
     宁可不给边界，也不给一个会误导的边界——见 SKIP，理由必须写进 manifest。
  §3 输出一律 EPSG:4326；坐标四舍五入到 5 位小数（≈1 米）；简化在米制投影下
     按「顶点预算」自适应，不用一个固定容差硬套所有产区（Val de Loire IGP 有
     9.5 万 km²，15 米容差会留下近 2 万个顶点、单条就 750 KB）。
  §4 行政边界兜底（boundaryType = 'administrative_county'）只能用在
     「目录条目的主体是行政区、官方没有任何等价的法定产区几何」时；
     只要存在一个覆盖范围相当的 AVA/GI，就必须用它，不许拿县界图省事。
"""
import datetime
import glob
import hashlib
import json
import sys
from pathlib import Path

import shapefile
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parent.parent
INAO_DIR = Path('/tmp/terroir-inao')
AU_GI = Path('/tmp/aus-gi-regions.geojson')
US_DIR = Path('/tmp/terroir-us')          # 每个 AVA 一个 <region_id>.geojson
US_COUNTY_DIR = Path('/tmp/terroir-us-county')   # 每个行政县一个 <region_id>.geojson
NZ_DIR = Path('/tmp/terroir-nz')          # 每个 GI 一个 <name>-GI-boundary/ 目录
TODAY = datetime.date.today().isoformat()

FR_SOURCE_URL = 'https://www.data.gouv.fr/datasets/delimitation-des-aires-geographiques-des-siqo'
FR_LICENSE = ('Licence Ouverte 2.0', 'https://www.etalab.gouv.fr/licence-ouverte-open-licence/')
AU_SOURCE_URL = ('https://services6.arcgis.com/s8j6JbJJCqmhNgh7/arcgis/rest/services/'
                 'Wine_Geographical_Indications_Australia/FeatureServer/1')
AU_ITEM_URL = 'https://www.arcgis.com/home/item.html?id=2dd4c385f0ed4d109c2e18ae99e819e2'
AU_LICENSE = ('CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/')
US_SOURCE_URL = ('https://services7.arcgis.com/ykuAbKu9MbV93nAe/arcgis/rest/services/'
                 'AVAs_Production/FeatureServer/0')
US_ITEM_URL = 'https://www.ttb.gov/wine/ava-map-explorer'
# TTB 在 ArcGIS 条目上原文：「There is no fee for downloading the shapefiles and no
# restrictions on their use.」data.gov 目录把该数据集标为 CC0-1.0。
US_LICENSE = ('公共领域 / CC0 1.0（TTB 声明下载与使用无限制）',
              'https://creativecommons.org/publicdomain/zero/1.0/')
NZ_SOURCE_URL = 'https://www.iponz.govt.nz/get-ip/geographical-indications/register/'
NZ_LICENSE = ('新西兰官方 GI 注册地理数据（IPONZ 公布）',
              'https://www.iponz.govt.nz/about-ip/geographical-indications/')
CENSUS_SOURCE_URL = ('https://tigerweb.geo.census.gov/arcgis/rest/services/'
                     'TIGERweb/State_County/MapServer/1')
CENSUS_ITEM_URL = 'https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html'
# 美国人口普查局 TIGER/Line 与 TIGERweb 数据属美国联邦政府作品，无版权
# （17 U.S.C. §105），官方用语："The Census Bureau does not claim copyright on its data."
CENSUS_LICENSE = ('美国联邦政府作品 / 公共领域（美国人口普查局不主张数据版权）',
                  'https://www.census.gov/about/policies/terms_of_use.html')

COORD_DECIMALS = 5   # ≈1.1 米；原样输出全精度浮点会让单条 Margaret River 就占 31 万字节
POINT_BUDGET = 8000  # 单个几何的顶点上限，超了就成倍放大简化容差
MAX_TOL_M = 1000     # 简化容差封顶

# ---------------------------------------------------------------- 法国 AOC / IGP
# id_denom -> (region_id, 官方名称, parentId, 该产区专有的补充说明)
# parentId 只影响 public/region-boundaries.js 的 candidates()：选中父产区时，
# 自己和所有 parentId 指向自己的产区会一起显示并 fit 视野（既有 6 个北罗讷产区就是这个约定）。
FR = {
    # —— 2026-09-19 首批 ——
    1:    ('alsace',             'Alsace',             None,      ''),
    67:   ('bordeaux',           'Bordeaux',           None,      ''),
    362:  ('burgundy',           'Bourgogne',          None,
           '此处仅为 Bourgogne AOC（大区级法定产区），不代表整个勃艮第葡萄酒大区。'),
    55:   ('champagne',          'Champagne',          None,      ''),
    1335: ('chateau-grillet',    'Château-Grillet',    'rhone',   ''),
    1339: ('condrieu',           'Condrieu',           'rhone',   ''),
    1340: ('cornas',             'Cornas',             'rhone',   ''),
    1365: ('crozes-hermitage',   'Crozes-Hermitage',   'rhone',   ''),
    1369: ('saint-joseph',       'Saint-Joseph',       'rhone',   ''),
    1370: ('saint-peray',        'Saint-Péray',        'rhone',   ''),
    # —— 2026-09-23 新增 ——
    397:  ('chablis',            'Chablis',            'burgundy', ''),
    1336: ('chateauneuf-du-pape', 'Châteauneuf-du-Pape', 'rhone',  ''),
    182:  ('chinon',             'Chinon',             'loire',    ''),
    1341: ('cote-rotie',         'Côte Rôtie',         'rhone',
           'INAO 记录的官方名称为 «Côte Rôtie»（带长音符），与目录 id cote-rotie 对应。'),
    1366: ('gigondas',           'Gigondas',           'rhone',    ''),
    1367: ('hermitage',          'Hermitage',          'rhone',
           'INAO 该条目的官方名称写作 "Hermitage ou Ermitage ou l\'Hermitage ou l\'Ermitage"，'
           '即四个写法同属一个法定产区。'),
    112:  ('medoc',              'Médoc',              'bordeaux',
           '此处的 Médoc AOC 地理范围覆盖整个梅多克半岛，含 Saint-Estèphe / Pauillac / '
           'Saint-Julien / Moulis-en-Médoc / Listrac-Médoc / Margaux 六个村庄级产区所在的市镇；'
           'Haut-Médoc AOC（INAO id_denom 98，960 km²）是与之不同的另一条范围。'),
    974:  ('nuit-saint-georges', 'Nuits-Saint-Georges', 'burgundy',
           '覆盖 Nuits-Saint-Georges 与 Premeaux-Prissey 两个市镇。本产区目录里的显示参考点'
           '（酒庄实体点位）落在法定地块之外约 1.3 公里——酒庄建筑常不在自家地块上，'
           '不影响边界本身。'),
    162:  ('saint-emilion',      'Saint-Émilion',      'bordeaux',
           'Saint-Émilion 与 Saint-Émilion Grand Cru 两 AOC 地理上互相交织、范围一致，'
           '此处取前者（INAO id_denom 162）的地理范围。'),
    223:  ('sancerre',           'Sancerre',           'loire',    ''),
    235:  ('vouvray',            'Vouvray',            'loire',    ''),
    2142: ('loire',              'Val de Loire',       None,
           '这一条是 IGP 不是 AOC：INAO 数据库里没有「Loire」AOC，Val de Loire IGP'
           '（9.5 万 km²）是唯一带 Loire 之名的省级以上几何，覆盖整个卢瓦尔河流域，'
           '比卢瓦尔河谷各 AOC 的合计范围更广。用作该大区的范围示意，与 AOC 不是同一层级。'),
}
# loire 用的是 IGP 图形，boundaryType 要与 AOC 区分开
FR_IGP = {'loire'}

# 官方只有更窄的图形、故不导入的产区。理由写进 manifest，并在缺口报告里复用。
SKIP = {
    'beaune':
        '伯恩丘是 «région viticole»（目录 areaNote 已写明官方不给单一 AOC）。INAO 里只有 '
        '«Beaune» / «Côte de Beaune»（id_denom 307 / 551，同为 31.1 km²，只覆盖 Beaune 一个市镇）'
        '与 «Côte de Beaune-Villages»（552，172.6 km²，覆盖的是各村 AOC 之外的市镇）。'
        '套上 31.1 km² 会把一条南北 20 公里、含 Meursault/Puligny/Pommard/Volnay 等 18 个市镇的'
        '大区悄悄缩成一个镇 → 按 §2 不导入。',
    'rhone':
        'INAO 里只有 «Côtes du Rhône» AOC（id_denom 1344，2,734 km²），不含北罗讷的 '
        'Côte Rôtie / Hermitage / Cornas / Crozes-Hermitage / Saint-Joseph 等独立 AOC，'
        '套上去会把罗讷河谷缩成南罗讷的一部分 → 按 §2 不导入。'
        'tests/region-boundaries.test.mjs 已明确断言此产区不得有边界。',
}

# 为什么 sonoma 用不了 AVA（理由必须留着：将来 TTB 若真登记了覆盖全县的 AVA，
# 就要立刻改回 AVA，不许继续用县界顶着）。
SONOMA_NO_AVA = (
    '目录这一条的主体是**县**：id=sonoma、name=索诺玛县、en=Sonoma County。'
    'TTB 的 AVA 库里没有任何叫 «Sonoma County» 的 AVA（只有 Sonoma Valley / Coast / '
    'Mountain / Northern Sonoma / West Sonoma Coast / Moon Mountain District of Sonoma '
    'County 等），套任何一个都会把整个县缩成其中一块 → 按 §2 不能当 AVA 用。'
)

# 行政边界兜底：目录条目的主体是行政区、官方没有任何等价的法定产区几何时，
# 允许用官方公布的行政边界，但必须在 boundaryType / label / note 三处标明口径。
# GEOID（州 FIPS + 县 FIPS）-> (region_id, 官方县名, 该条兜底的理由)
US_COUNTY = {
    '06097': ('sonoma', 'Sonoma County', SONOMA_NO_AVA),
}

# 已按国家调研过、确实拿不到官方几何的产区。写入 manifest，缺口报告里单列，不算待办。
# 与 SKIP 的区别：SKIP 是「有官方几何但更窄，故意不用」；
# UNAVAILABLE 是「官方渠道没有可用几何」——将来官方补了数据就可以撤掉。
UNAVAILABLE = {
    '西班牙':
        '2026-09-23 实测：MAPA（农业渔业食品部）的 PDO/PGI 国家制图只提供 WMS '
        '（https://wms.mapama.gob.es/sig/Alimentacion/CDVinos/wms.aspx，实测返回 .NET '
        'NullReferenceException/InvalidFormat，服务本身故障）；同路径没有 WFS '
        '（wfs.aspx 回 "service is not WMS"）；INSPIRE ATOM 下载服务 '
        '（https://www.mapama.gob.es/ide/inspire/atom/CategAlimentacion/downloadservice.xml）'
        '是空 feed，零 entry。故目前取不到西班牙任何 DO 的多边形。'
        '后续可试：各 Consejo Regulador 自建 GIS（Rioja / Ribera del Duero / Jerez 各自有图，'
        '多为 PDF）、加泰罗尼亚 ICGC 开放数据（覆盖 Penedès / Priorat）。',
}

# ---------------------------------------------------------------- 澳大利亚 GI
# Wine Australia 图层 1 的 GI_NAME -> region_id
# ⚠️ 官方命名与目录 id 不一致的两处：Zone 层叫 «Hunter Valley»，Region 层叫 «Hunter»；
#    «McLaren Vale» 官方拼作 «Mclaren Vale»（小写 l）。按图层 1 的实际字符串取。
AU = {
    'Barossa Valley': 'barossa',
    'Coonawarra': 'coonawarra',
    'Margaret River': 'margaret',
    'Hunter': 'hunter-valley',
    'Mclaren Vale': 'mclaren-vale',
    'Yarra Valley': 'yarra-valley',
}

# ---------------------------------------------------------------- 美国 AVA
# TTB AVA_Polygons_gen2pt5m（图层 0）的 Name -> region_id
# ⚠️ 按 Name='…' AND Status='Established' 精确取，库里还混着 Pending / Historic 的同名条目。
US = {
    'Napa Valley': 'napa',
    'Paso Robles': 'paso-robles',
    'Willamette Valley': 'willamette',
}

# ---------------------------------------------------------------- 新西兰 GI
# IPONZ GI 注册表的地理数据目录名 -> (region_id, 官方 GI 名称)
# 每个 GI 一个 zip，内含 shapefile（CRS = NZGD2000 地理坐标，EPSG:4167）+ ESRI JSON + 静态图。
NZ = {
    'Hawkes-Bay-GI-boundary':   ('hawkes',        "Hawke's Bay / Hawkes Bay"),
    'Marlborough-GI-boundary':  ('marlborough',   'Marlborough'),
    'Central-Otago-GI-boundary': ('otago',        'Central Otago'),
    'Martinborough-GI-boundary': ('martinborough', 'Martinborough'),
}


def npoints(g):
    """顶点数（含内环），用来判断简化是否够。"""
    if g.geom_type == 'Polygon':
        return len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
    return sum(npoints(p) for p in g.geoms)


def round_coords(o, nd=COORD_DECIMALS):
    """坐标四舍五入。首尾点因为原值相同、舍完也相同，环闭合不会被破坏。"""
    if isinstance(o, (list, tuple)):
        if o and isinstance(o[0], (int, float)):
            return [round(o[0], nd), round(o[1], nd)]
        return [round_coords(x, nd) for x in o]
    return o


def metric_simplify(g, work_epsg, tol_m):
    """在 work_epsg（米制）下按顶点预算自适应简化，再回到 EPSG:4326。

    返回 (几何, 实际容差, 米制面积 km²)。输入几何必须是 EPSG:4326。
    每一轮都从原几何重新简化，不叠加，避免容差被反复套用。
    """
    fwd = Transformer.from_crs(4326, work_epsg, always_xy=True).transform
    back = Transformer.from_crs(work_epsg, 4326, always_xy=True).transform
    w0 = transform(fwd, g)
    tol = float(tol_m)
    while True:
        w = w0.simplify(tol, preserve_topology=True)
        if npoints(w) <= POINT_BUDGET or tol >= MAX_TOL_M:
            break
        tol = min(tol * 2, MAX_TOL_M)
    area_km2 = w.area / 1e6
    out = transform(back, w)
    if not out.is_valid:
        out = make_valid(out)
    assert out.geom_type in ('Polygon', 'MultiPolygon'), out.geom_type
    assert out.is_valid, '简化后几何无效'
    return out, tol, area_km2


def read_inao():
    files = sorted(INAO_DIR.glob('*delim-aire-geographique-shp.shp'))
    if not files:
        sys.exit('找不到 INAO shapefile：请先下载 data.gouv.fr 的 SIQO 快照到 %s' % INAO_DIR)
    shp = files[-1]                       # 文件名带日期，按字典序取最新
    return shp, shapefile.Reader(str(shp))


def main():
    shp_path, reader = read_inao()
    src_date = shp_path.name.split('_')[0]      # 例：2026-09-21
    out = []
    diag = {}                                   # regionId -> (tol, area_km2)

    # ---- 法国 ----
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        rid_denom = rec.get('id_denom')
        if rid_denom not in FR:
            continue
        rid, official, parent, extra = FR[rid_denom]
        g = shape(sr.shape.__geo_interface__)      # EPSG:2154
        if not g.is_valid:
            g = make_valid(g)
        g = transform(Transformer.from_crs(2154, 4326, always_xy=True).transform, g)
        g, tol, area_km2 = metric_simplify(g, 2154, 15)
        diag[rid] = (tol, area_km2)
        is_igp = rid in FR_IGP
        note = ('INAO 公布的 %s 地理范围，在原始投影下简化约 %d 米用于显示；'
                '不是实际种植地块，法律定义以产区规范的市镇清单为准。'
                % ('IGP' if is_igp else 'AOC', round(tol)))
        if extra:
            note += ' ' + extra
        out.append({
            'type': 'Feature',
            'geometry': {'type': g.geom_type, 'coordinates': round_coords(mapping(g)['coordinates'])},
            'properties': {
                'regionId': rid,
                'parentId': parent,
                'country': '法国',
                'label': '%s %s · 地理范围' % (official, 'IGP' if is_igp else 'AOC'),
                'boundaryType': 'geographical_indication' if is_igp else 'appellation_geographical_area',
                'note': note,
                'sourceName': 'INAO',
                'sourceURL': FR_SOURCE_URL,
                'sourceDate': src_date,
                'checkedDate': TODAY,
                'license': FR_LICENSE[0],
                'licenseURL': FR_LICENSE[1],
                'sourceRecordId': rid_denom,
            },
        })
    seen = {f['properties']['regionId'] for f in out}
    assert not (seen & set(SKIP)), 'SKIP 里的产区不该出现在输出里：%s' % (seen & set(SKIP))

    # ---- 澳大利亚 ----
    if not AU_GI.exists():
        sys.exit('找不到 Wine Australia GI 快照：%s' % AU_GI)
    au = json.loads(AU_GI.read_text())
    au_found = set()
    for f in au['features']:
        name = f['properties']['GI_NAME']
        if name not in AU:
            continue
        rid = AU[name]
        au_found.add(name)
        g = shape(f['geometry'])                   # EPSG:4326
        if not g.is_valid:
            g = make_valid(g)
        g, tol, area_km2 = metric_simplify(g, 3577, 15)      # GDA94 / Australian Albers
        diag[rid] = (tol, area_km2)
        out.append({
            'type': 'Feature',
            'geometry': {'type': g.geom_type, 'coordinates': round_coords(mapping(g)['coordinates'])},
            'properties': {
                'regionId': rid,
                'parentId': None,
                'country': '澳大利亚',
                'label': '%s GI · 地理范围' % f['properties'].get('GI_NAME'),
                'boundaryType': 'geographical_indication',
                'note': ('© Wine Australia，CC BY 4.0。官方 GI 图示范围，在 Australian Albers 投影下'
                         '简化约 %d 米用于显示；法律定义以 Wine Australia 的 GI 注册文本为准。'
                         '数据取自 ArcGIS FeatureServer 图层 1（Regions），条目页 %s。'
                         % (round(tol), AU_ITEM_URL)),
                'sourceName': 'Wine Australia',
                'sourceURL': AU_SOURCE_URL,
                'sourceDate': f['properties'].get('YEAR_REGISTERED'),
                'checkedDate': TODAY,
                'license': AU_LICENSE[0],
                'licenseURL': AU_LICENSE[1],
                'sourceRecordId': name,
            },
        })
    missing = sorted(set(AU) - au_found)
    if missing:
        sys.exit('Wine Australia GI 快照里找不到这些 GI_NAME：%s' % missing)

    # ---- 美国 AVA（TTB）----
    # 快照由 scripts/fetch-national-boundaries.py 落到 /tmp/terroir-us/<region_id>.geojson，
    # 每个文件是官方 FeatureServer 精确查询 Name='…' AND Status='Established' 的结果。
    us_inputs = []
    for ava_name, rid in sorted(US.items(), key=lambda kv: kv[1]):
        f_us = US_DIR / ('%s.geojson' % rid)
        if not f_us.exists():
            sys.exit('找不到 TTB AVA 快照 %s（应含 %s）' % (f_us, ava_name))
        d_us = json.loads(f_us.read_text())
        feats = d_us.get('features') or []
        if len(feats) != 1:
            sys.exit('TTB 快照 %s 期望 1 个要素，实际 %d' % (f_us, len(feats)))
        attrs = feats[0].get('properties') or {}
        g = shape(feats[0]['geometry'])
        if not g.is_valid:
            g = make_valid(g)
        g, tol, area_km2 = metric_simplify(g, 5070, 15)   # NAD83 / Conus Albers
        diag[rid] = (tol, area_km2)
        us_inputs.append(f_us)
        cfr = attrs.get('CFR_Section') or ''
        out.append({
            'type': 'Feature',
            'geometry': {'type': g.geom_type, 'coordinates': round_coords(mapping(g)['coordinates'])},
            'properties': {
                'regionId': rid,
                'parentId': None,
                'country': '美国',
                'label': '%s AVA · 地理范围' % ava_name,
                'boundaryType': 'american_viticultural_area',
                'note': ('美国财政部 TTB 公布的 American Viticultural Area 边界（%s），'
                         '在 Conus Albers 投影下简化约 %d 米用于显示。'
                         'TTB 原文：「图中的边界仅供示意，法律认可的边界是 27 CFR part 9 成文描述；'
                         '两者不一致时以成文描述为准」，本图层亦按此口径使用。'
                         'TTB 声明下载与使用无限制。数据取自 AVA Map Explorer 的 '
                         'FeatureServer 图层 0，条目页 %s。'
                         % (cfr or 'CFR 章节见 TTB 条目', round(tol), US_ITEM_URL)),
                'sourceName': 'TTB（美国酒精烟草税务贸易局）',
                'sourceURL': US_SOURCE_URL,
                'sourceDate': str(attrs.get('Established') or ''),
                'checkedDate': TODAY,
                'license': US_LICENSE[0],
                'licenseURL': US_LICENSE[1],
                'sourceRecordId': ava_name,
            },
        })

    # ---- 美国行政县界（人口普查局 TIGERweb）----
    # §4 兜底：只在「条目主体是行政区、官方没有等价法定产区几何」时使用。
    # 快照由 scripts/fetch-national-boundaries.py US-COUNTY 落到
    # /tmp/terroir-us-county/<region_id>.geojson。
    us_county_inputs = []
    for geoid, (rid, county_name, why) in sorted(US_COUNTY.items(), key=lambda kv: kv[1][0]):
        f_ct = US_COUNTY_DIR / ('%s.geojson' % rid)
        if not f_ct.exists():
            sys.exit('找不到 Census 县界快照 %s（应含 %s / GEOID %s）' % (f_ct, county_name, geoid))
        d_ct = json.loads(f_ct.read_text())
        feats = d_ct.get('features') or []
        if len(feats) != 1:
            sys.exit('Census 快照 %s 期望 1 个要素，实际 %d' % (f_ct, len(feats)))
        attrs = feats[0].get('properties') or {}
        if str(attrs.get('GEOID')) != geoid or str(attrs.get('NAME')) != county_name:
            sys.exit('Census 快照 %s 的 GEOID/NAME 与期望不符：%r / %r'
                     % (f_ct, attrs.get('GEOID'), attrs.get('NAME')))
        g = shape(feats[0]['geometry'])
        if not g.is_valid:
            g = make_valid(g)
        g, tol, area_km2 = metric_simplify(g, 5070, 15)   # NAD83 / Conus Albers
        # 用官方公布的 AREALAND + AREAWATER 交叉验证几何：形状没被处理坏，面积就不该跑偏。
        # ⚠️ 不能只比 AREALAND —— TIGER 的县界多边形**含水域**（沿海县含 3 海里领海），
        #    只比陆域会得到 12% 的假差异（Sonoma：陆 4,080 + 水 497 = 4,577 km²）。
        land_km2 = (attrs.get('AREALAND') or 0) / 1e6
        water_km2 = (attrs.get('AREAWATER') or 0) / 1e6
        official_km2 = land_km2 + water_km2
        if official_km2:
            drift = abs(area_km2 - official_km2) / official_km2
            assert drift < 0.03, ('%s 几何面积 %.0f km² 与官方 陆%.0f+水%.0f=%.0f km² 差 %.1f%%'
                                  % (rid, area_km2, land_km2, water_km2, official_km2, drift * 100))
        diag[rid] = (tol, area_km2)
        us_county_inputs.append(f_ct)
        out.append({
            'type': 'Feature',
            'geometry': {'type': g.geom_type, 'coordinates': round_coords(mapping(g)['coordinates'])},
            'properties': {
                'regionId': rid,
                'parentId': None,
                'country': '美国',
                'label': '%s（行政县界）· 地理范围' % county_name,
                'boundaryType': 'administrative_county',
                'note': ('⚠️ 这是「行政县界，不是法定葡萄酒产区范围」。本条目在目录里的主体是'
                         '「%s」这一行政区，美国财政部 TTB 的 American Viticultural Area 库中'
                         '没有与之等价的 AVA，因此以美国人口普查局 TIGERweb 的官方县界作为范围示意'
                         '（GEOID %s，TIGERweb State_County 图层 1，2026-01-01 vintage），'
                         '在 Conus Albers 投影下简化约 %d 米用于显示。'
                         '该县境内另有若干各自独立的 AVA（如 Sonoma Valley、Sonoma Coast、'
                         'Northern Sonoma 等），它们的法定范围与本图无关，本图也不代表其中任何一个。'
                         '⚠️ 县界多边形按官方定义含水域（陆地 %.0f km² ＋ 水面 %.0f km²，'
                         '沿海部分含领海），所以西侧看上去会伸进太平洋。'
                         'TIGER/Line 属美国联邦政府作品，美国人口普查局不主张数据版权。'
                         % (county_name, geoid, round(tol), land_km2, water_km2)),
                'sourceName': '美国人口普查局（U.S. Census Bureau）',
                'sourceURL': CENSUS_SOURCE_URL,
                'sourceDate': '2026-01-01',
                'checkedDate': TODAY,
                'license': CENSUS_LICENSE[0],
                'licenseURL': CENSUS_LICENSE[1],
                'sourceRecordId': geoid,
            },
        })

    # ---- 新西兰 GI（IPONZ）----
    nz_inputs = []
    for dirname, (rid, gi_name) in sorted(NZ.items(), key=lambda kv: kv[1][0]):
        d_nz = NZ_DIR / dirname
        shps = sorted(d_nz.glob('*.shp')) if d_nz.is_dir() else []
        if not shps:
            sys.exit('找不到 IPONZ GI 快照 %s/*.shp（应含 %s）' % (d_nz, gi_name))
        shp_nz = shps[0]
        recs = shapefile.Reader(str(shp_nz)).shapeRecords()
        if len(recs) != 1:
            sys.exit('IPONZ 快照 %s 期望 1 个要素，实际 %d' % (shp_nz, len(recs)))
        rec = recs[0].record.as_dict()
        g = shape(recs[0].shape.__geo_interface__)       # NZGD2000 地理坐标 EPSG:4167
        if not g.is_valid:
            g = make_valid(g)
        g = transform(Transformer.from_crs(4167, 4326, always_xy=True).transform, g)
        g, tol, area_km2 = metric_simplify(g, 2193, 15)  # NZGD2000 / NZTM2000
        diag[rid] = (tol, area_km2)
        nz_inputs += [shp_nz, shp_nz.with_suffix('.dbf'), shp_nz.with_suffix('.prj')]
        ip = rec.get('IP_Number') or ''
        out.append({
            'type': 'Feature',
            'geometry': {'type': g.geom_type, 'coordinates': round_coords(mapping(g)['coordinates'])},
            'properties': {
                'regionId': rid,
                'parentId': None,
                'country': '新西兰',
                'label': '%s GI · 地理范围' % gi_name,
                'boundaryType': 'geographical_indication',
                'note': ('新西兰知识产权局 IPONZ 公布的 GI 注册地理数据（GI 编号 %s），'
                         '在 NZTM2000 投影下简化约 %d 米用于显示；法律定义以 IPONZ 注册文本为准。'
                         '⚠️ 面积远大于实际种植区：IPONZ 的边界指南允许并常见以「地方行政区界」'
                         '（territorial authority）为基础申报，所以这里看到的是整个区/县的范围'
                         '（例如 Central Otago 覆盖 Central Otago 与 Queenstown-Lakes 两区），'
                         '不是葡萄园地块。原始数据由申请方提交、经 IPONZ 审查（要求 NZGD2000/'
                         'EPSG:4167 未投影经纬度、2D Polygon/MultiPolygon、环必须闭合）。'
                         '注册页 %s。'
                         % (ip or '—', round(tol), rec.get('Registerli') or NZ_SOURCE_URL)),
                'sourceName': 'IPONZ（新西兰知识产权局）',
                'sourceURL': rec.get('Registerli') or NZ_SOURCE_URL,
                'sourceDate': '',
                'checkedDate': TODAY,
                'license': NZ_LICENSE[0],
                'licenseURL': NZ_LICENSE[1],
                'sourceRecordId': ip or gi_name,
            },
        })

    # 每条来源都必须真的落进了输出，防止改了字典却忘了改循环
    for label, expected in (('美国 AVA', set(US.values())),
                            ('美国县界', {v[0] for v in US_COUNTY.values()}),
                            ('新西兰', {v[0] for v in NZ.values()})):
        got = {f['properties']['regionId'] for f in out}
        assert expected <= got, '%s 缺了：%s' % (label, expected - got)
    seen = {f['properties']['regionId'] for f in out}
    assert not (seen & set(SKIP)), 'SKIP 里的产区不该出现在输出里：%s' % (seen & set(SKIP))
    # 行政县界必须与法定产区在类型上分得开，否则前端会把它当 AOC 展示
    admin = {f['properties']['regionId'] for f in out
             if f['properties']['boundaryType'] == 'administrative_county'}
    assert admin == {v[0] for v in US_COUNTY.values()}, \
        '行政县界集合与 US_COUNTY 不一致：%s' % admin
    for f in out:
        p = f['properties']
        if p['boundaryType'] == 'administrative_county':
            for token in ('行政县界', '不是法定葡萄酒产区范围'):
                assert token in p['note'], '%s 的 note 缺披露：%s' % (p['regionId'], token)
            assert 'AVA' not in p['label'], '行政县界的 label 不许出现 AVA：%s' % p['label']
    # note / label 是**纯文本**（前端只做 escapeHTML，不渲染 Markdown），
    # 写进去的 '**' 会原样显示成星号。想强调就用「」。
    for f in out:
        p = f['properties']
        for key in ('note', 'label'):
            assert '**' not in (p.get(key) or ''), \
                '%s 的 %s 含 Markdown 星号，页面上会原样显示：%s' % (p['regionId'], key, p[key][:60])

    # ---- 输出 ----
    fc = {'type': 'FeatureCollection', 'features': out}
    geo_path = ROOT / 'public' / 'region-boundaries.geojson'
    geo_path.write_text(json.dumps(fc, ensure_ascii=False, separators=(',', ':')) + '\n')

    inputs = [shp_path, shp_path.with_suffix('.dbf'), shp_path.with_suffix('.prj'), AU_GI]
    manifest = {
        'checkedDate': TODAY,
        'count': len(out),
        'regionIds': [f['properties']['regionId'] for f in out],
        'inputs': [{'file': str(p), 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                   for p in inputs + us_inputs + us_county_inputs + sorted(set(nz_inputs))],
        'sources': [
            {'name': 'INAO — Délimitation des aires géographiques des SIQO',
             'url': FR_SOURCE_URL, 'snapshot': src_date, 'crs': 'EPSG:2154',
             'note': '2026-09-14 与 2026-09-21 两版 .shp 字节完全相同，既有法国边界不会因换版漂移。'},
            {'name': 'Wine Australia — Wine Geographical Indications Australia',
             'url': AU_SOURCE_URL, 'itemPage': AU_ITEM_URL, 'layer': 1, 'crs': 'EPSG:4326',
             'note': '图层 1 = Regions（64 个）；Zone 层 (2) 与 Subregion 层 (0) 未使用。'},
            {'name': 'TTB — American Viticultural Areas（AVA Map Explorer）',
             'url': US_SOURCE_URL, 'itemPage': US_ITEM_URL, 'layer': 0, 'crs': 'EPSG:4326',
             'note': '查询条件 Name=… AND Status=\'Established\'（库里混有 Pending / Historic 同名条目）。'
                     'TTB 声明下载与使用无限制。法律边界以 27 CFR part 9 成文描述为准。'},
            {'name': 'U.S. Census Bureau — TIGERweb State_County（Counties, layer 1）',
             'url': CENSUS_SOURCE_URL, 'itemPage': CENSUS_ITEM_URL, 'layer': 1, 'crs': 'EPSG:4326',
             'vintage': 'January 1, 2026',
             'note': '**行政边界，非葡萄酒产区法定范围**，仅用于 boundaryType='
                     '\'administrative_county\' 的兜底条目。按 GEOID 精确查询单县；'
                     '导入时用官方 AREALAND 交叉验证几何面积（容差 3%）。'
                     'TIGER/Line 属美国联邦政府作品，人口普查局不主张版权。'},
            {'name': 'IPONZ — New Zealand Geographical Indications register',
             'url': NZ_SOURCE_URL, 'crs': 'EPSG:4167',
             'note': '每个 GI 一个 Geodata ZIP（shapefile + ESRI JSON + 静态图）。'
                     '申请方按 IPONZ 要求提交：NZGD2000 未投影经纬度、2D Polygon/MultiPolygon、环闭合。'},
        ],
        'skipped': {k: v for k, v in SKIP.items()},
        # 与 skipped 的区别：skipped 是「宁可不给边界」；administrativeFallbacks 是
        # 「法定产区几何确实没有，但用官方行政边界兜底，并已三处标明口径」。
        'administrativeFallbacks': {
            rid: {'boundaryType': 'administrative_county',
                  'sourceRecordId': geoid,
                  'officialName': county_name,
                  'whyNotAProtectedArea': why}
            for geoid, (rid, county_name, why) in US_COUNTY.items()
        },
        'unavailable': {k: v for k, v in UNAVAILABLE.items()},
        'note': ('No inferred polygons: every geometry comes from an official published source. '
                 'French polygons are AOC/IGP geographical areas, not planted parcels or necessarily '
                 'entire broader wine regions. Regions whose only official geometry is a narrower '
                 'appellation are deliberately left without a boundary (see skipped). Regions whose '
                 'subject is an administrative district and which have no equivalent protected-area '
                 'geometry use an official administrative boundary instead, always flagged with '
                 'boundaryType=administrative_county and disclosed in label/note '
                 '(see administrativeFallbacks). Countries whose official channels yielded no usable '
                 'geometry are recorded in unavailable. '
                 'Remaining catalogue regions have no imported boundaries yet. '
                 'Coordinates rounded to 5 decimals; simplification tolerance is adaptive '
                 '(<=%d points per geometry).' % POINT_BUDGET),
    }
    (ROOT / 'data' / 'region-boundary-sources.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')

    # ---- 打印 ----
    KIND = {'appellation_geographical_area': 'AOC',
            'geographical_indication': 'GI',
            'american_viticultural_area': 'AVA',
            'administrative_county': '县界'}
    print('Imported %d boundaries -> %s (%s bytes)' % (
        len(out), geo_path.relative_to(ROOT), format(geo_path.stat().st_size, ',')))
    print('%-20s %-4s %-9s %7s %10s %9s' % ('regionId', 'kind', 'tol(m)', 'points', 'area km2', 'bytes'))
    for f in out:
        p = f['properties']
        tol, area = diag[p['regionId']]
        print('%-20s %-4s %-9s %7d %10.1f %9s' % (
            p['regionId'], KIND.get(p['boundaryType'], p['boundaryType']),
            '%d' % round(tol), npoints(shape(f['geometry'])), area,
            format(len(json.dumps(f, ensure_ascii=False, separators=(',', ':'))), ',')))
    known = {f['properties']['regionId'] for f in out}
    print('skipped（官方只有更窄/对不上的图形，宁缺勿误导）: %s' % ', '.join(sorted(SKIP)))
    print('administrativeFallbacks（无等价法定产区几何，用官方行政边界兜底）: %s'
          % ', '.join('%s=%s' % (rid, v['officialName'])
                      for rid, v in sorted(manifest['administrativeFallbacks'].items())))
    print('unavailable（已调研，官方渠道无可用几何）: %s' % ', '.join(sorted(UNAVAILABLE)))
    print('本轮共 %d 个产区有边界：%s' % (len(known), ', '.join(sorted(known))))


if __name__ == '__main__':
    main()
