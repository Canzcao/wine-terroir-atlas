#!/usr/bin/env python3
# coding: utf-8
"""下载各国**官方** GIS 快照到 /tmp，供 scripts/import-region-boundaries.py 读取。

为什么要有这个文件：导入脚本只读 /tmp 下的快照，快照怎么来的必须也能复现。
**只从这里下载官方公布的图形**，不接受第三方转载（转载常常丢属性、换投影、截边界）。

用法（**必须用装了 pyshp 的解释器**，它要读回 shapefile 做校验；
GIS 库通常不装在托管 Python 的 versions/* 下，而在某个 venv 里）：
    python scripts/fetch-national-boundaries.py            # 全下
    python scripts/fetch-national-boundaries.py US NZ      # 只下指定国家

落地位置（与 import 脚本里的常量一一对应）：
    /tmp/terroir-us/<region_id>.geojson       美国 TTB AVA（FeatureServer 精确查询）
    /tmp/terroir-us-county/<region_id>.geojson 美国人口普查局县界（行政边界，见下）
    /tmp/terroir-nz/<GI>-GI-boundary/         新西兰 IPONZ GI（zip 解压后的 shapefile）
法国 INAO 与澳洲 Wine Australia 的下载见 scripts/import-region-boundaries.py 顶部注释
（那两份是既有链路，快照已在 /tmp/terroir-inao、/tmp/aus-gi-regions.geojson）。
"""
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

US_DIR = Path('/tmp/terroir-us')
US_COUNTY_DIR = Path('/tmp/terroir-us-county')
NZ_DIR = Path('/tmp/terroir-nz')

# TTB AVA Map Explorer 的 FeatureServer。⚠️ 查 Name 必须同时限定 Status='Established'，
# 因为库里混着同名 Pending / Historic 条目（例如 Sonoma Coast 有 3 个 Pending 变体）。
US_AVA = {
    'Napa Valley': 'napa',
    'Paso Robles': 'paso-robles',
    'Willamette Valley': 'willamette',
}
US_QUERY = ('https://services7.arcgis.com/ykuAbKu9MbV93nAe/arcgis/rest/services/'
            'AVAs_Production/FeatureServer/0/query')

# 美国人口普查局 TIGERweb「州与县」服务，图层 1 = Counties（January 1, 2026 vintage，
# 该服务里最详细的一层）。**这是行政边界，不是法定葡萄酒产区范围**，
# 只给目录里「其实是县」的条目兜底用，boundaryType 与 AVA 严格区分。
# ⚠️ 该服务的 Counties 有十几层（不同比例尺/年份），别用 0/2/3…，要 1。
US_COUNTY_QUERY = ('https://tigerweb.geo.census.gov/arcgis/rest/services/'
                   'TIGERweb/State_County/MapServer/1/query')
# GEOID（州 FIPS + 县 FIPS）-> (region_id, 官方县名)
US_COUNTY = {
    '06097': ('sonoma', 'Sonoma County'),
}

# IPONZ GI 注册表的 geodata zip。路径里的数字是注册表条目号，改名时会变，
# 所以文件名同时留一份校验：下载后必须能在 shapefile 里读到期望的 GI_Name。
NZ_GI = {
    'Hawkes-Bay-GI-boundary':    ('1833/Hawkes-Bay-GI-boundary.zip',    'Hawkes_Bay',          "Hawke's Bay"),
    'Marlborough-GI-boundary':   ('1830/Marlborough-GI-boundary.zip',   'Marlborough',         'Marlborough'),
    'Central-Otago-GI-boundary': ('1839/Central-Otago-GI-boundary.zip', 'Central_Otago',       'Central Otago'),
    'Martinborough-GI-boundary': ('1848/Martinborough-GI-boundary.zip', 'Martinborough',       'Martinborough'),
}
NZ_BASE = 'https://www.iponz.govt.nz/assets/GIRegister/'

# 本机有透明代理，必须显式绕开，否则会拿到代理的 502/000
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url, timeout=180, attempts=3):
    """带重试的下载。Cloudflare 偶发断连，单次失败不代表源不可用。"""
    last = None
    for i in range(attempts):
        try:
            with OPENER.open(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:                                # noqa: BLE001
            last = e
            print('    重试 %d/%d：%s' % (i + 1, attempts, e))
            time.sleep(2 * (i + 1))
    raise SystemExit('下载失败：%s（%s）' % (url, last))


def do_us():
    US_DIR.mkdir(parents=True, exist_ok=True)
    for name, rid in sorted(US_AVA.items(), key=lambda kv: kv[1]):
        params = {
            'where': "Name='%s' AND Status='Established'" % name,
            'outFields': 'Name,Established,CFR_Section,States,Counties,Status',
            'returnGeometry': 'true',
            'outSR': '4326',
            'f': 'geojson',
        }
        raw = fetch(US_QUERY + '?' + urllib.parse.urlencode(params))
        d = json.loads(raw)
        n = len(d.get('features') or [])
        # 单要素断言放在这里，坏数据别流到下游
        if n != 1:
            raise SystemExit('TTB 查询 %r 期望 1 个要素，实际 %d' % (name, n))
        got = d['features'][0]['properties'].get('Name')
        if got != name:
            raise SystemExit('TTB 返回的名称 %r 与请求 %r 不一致' % (got, name))
        (US_DIR / ('%s.geojson' % rid)).write_bytes(raw)
        print('  US  %-18s -> %s.geojson  %s bytes' % (name, rid, format(len(raw), ',')))


def do_us_county():
    """美国县界（行政边界兜底）。按 GEOID 精确取单县，不做任何形状处理。"""
    US_COUNTY_DIR.mkdir(parents=True, exist_ok=True)
    for geoid, (rid, county_name) in sorted(US_COUNTY.items(), key=lambda kv: kv[1][0]):
        params = {
            'where': "GEOID='%s'" % geoid,
            'outFields': 'GEOID,NAME,STATE,COUNTY,BASENAME,MTFCC,FUNCSTAT,AREALAND,AREAWATER,'
                         'INTPTLAT,INTPTLON',
            'returnGeometry': 'true',
            'outSR': '4326',
            'f': 'geojson',
        }
        raw = fetch(US_COUNTY_QUERY + '?' + urllib.parse.urlencode(params))
        d = json.loads(raw)
        feats = d.get('features') or []
        # 单要素断言放在这里，坏数据别流到下游
        if len(feats) != 1:
            raise SystemExit('Census 县查询 %s 期望 1 个要素，实际 %d' % (geoid, len(feats)))
        p = feats[0]['properties']
        # 反查：GEOID 与县名都要对上，防止官方改了编号或返回了同名别州县
        if str(p.get('GEOID')) != geoid:
            raise SystemExit('Census 返回 GEOID=%r，与请求 %r 不一致' % (p.get('GEOID'), geoid))
        if str(p.get('NAME')) != county_name:
            raise SystemExit('Census 返回 NAME=%r，与期望 %r 不一致' % (p.get('NAME'), county_name))
        (US_COUNTY_DIR / ('%s.geojson' % rid)).write_bytes(raw)
        land_km2 = (p.get('AREALAND') or 0) / 1e6
        print('  US-县 %-16s -> %s.geojson  %s bytes  陆地面积 %.0f km²'
              % ('%s (%s)' % (county_name, geoid), rid, format(len(raw), ','), land_km2))


def do_nz():
    NZ_DIR.mkdir(parents=True, exist_ok=True)
    for dirname, (rel, shp_stem, expect_name) in sorted(NZ_GI.items()):
        dest = NZ_DIR / dirname
        dest.mkdir(parents=True, exist_ok=True)
        zpath = NZ_DIR / Path(rel).name
        raw = fetch(NZ_BASE + rel)
        zpath.write_bytes(raw)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
        shp = dest / ('%s.shp' % shp_stem)
        if not shp.exists():
            raise SystemExit('解压后找不到 %s' % shp)
        # 用属性里的 GI_Name 反查，防止官方换了文件内容却没换文件名
        import shapefile                                     # 延迟导入：只有 NZ 需要
        recs = shapefile.Reader(str(shp)).shapeRecords()
        if len(recs) != 1:
            raise SystemExit('%s 期望 1 个要素，实际 %d' % (shp, len(recs)))
        got = str(recs[0].record.as_dict().get('GI_Name') or '')
        if expect_name.lower() not in got.lower():
            raise SystemExit('%s 里的 GI_Name=%r 不含期望的 %r' % (shp, got, expect_name))
        print('  NZ  %-18s -> %s/  GI_Name=%r' % (dirname, dirname, got))


def main():
    which = [a.upper() for a in sys.argv[1:]] or ['US', 'US-COUNTY', 'NZ']
    if 'US' in which:
        print('== 美国 TTB AVA ==')
        do_us()
    if 'US-COUNTY' in which:
        print('== 美国人口普查局县界（行政边界兜底）==')
        do_us_county()
    if 'NZ' in which:
        print('== 新西兰 IPONZ GI ==')
        do_nz()
    print('完成。')


if __name__ == '__main__':
    main()
