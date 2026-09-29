"""向 catalog-seed.json 追加「中国台湾」产区实体（不挂任何酒庄）。

需求（Canz 2026-09-22）：
  给中国的产区地图增加「中国台湾」子产区选项，标签标在台湾岛上，不挂酒庄。

落点说明：
  · country='中国' + 不写 regionId → 自动成为中国下的第 4 个根级子产区
    （map-model.js 的 children('', '中国') 取 regionId 落空者）。
  · lat/lng 取台湾岛几何中心，已用 world.geojson 里的台湾岛多边形
    做过 point-in-polygon 实证（见 verify 段）。
  · 「不挂酒庄」是安全状态：库内 hermitage 就是 0 酒庄产区，前端
    region-wineries 会显示「0 家酒庄 · 0 款酒 · 0 张图片」；
    terroir-deploy/smoke_test.mjs 的产区断言只扫 public/data.js 的入口 id，
    不扫 catalog，因此不会因为空产区失败。

跑法：python3 scripts/add-taiwan-region.py
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import os as _os
BASE = Path(_os.environ.get('TERROIR_ROOT', Path(__file__).resolve().parent.parent))
SEED = BASE / 'data/catalog-seed.json'
WORLD = BASE / 'public/assets/world.geojson'

ANCHOR_AFTER = 'shangri-la'   # 插在现有中国产区之后
CHECKED = '2026-09-22'

SOURCE_MAIN = 'https://kmweb.moa.gov.tw/subject/subject.php?id=18148'
SOURCE_VIDEO = 'https://kmweb.moa.gov.tw/theme_data.php?theme=video&id=866'
SOURCE_TITLE_MAIN = ('中国台湾地区农业主管部门农业知识入口网 · 葡萄主题馆'
                     '《2010年彰化县葡萄酒新酒发表会暨产业概述》（发布 2011-01-12，更新 2024-09-30）')

RECORD = {
    'id': 'taiwan',
    'kind': 'region',
    'name': '中国台湾',
    'data': {
        'name': '中国台湾',
        'en': 'Taiwan, China',
        'country': '中国',
        'aliases': ['台湾', 'Taiwan'],
        'lat': 23.7,
        'lng': 120.96,
        'locationPrecision': '产区浏览中心',
        'locationNote': (
            '坐标取台湾岛几何中心（约 23.70°N / 120.96°E），用途是把地图上的「中国台湾」标签落在台湾岛上；'
            '这是岛屿中心点，不是葡萄园地块中心——本地区酿酒葡萄与酒庄集中在彰化县二林镇一带'
            '（约 23.90°N / 120.37°E），与标注点相距约 60 km。'
        ),
        'grapes': [{'id': 'grape-blackqueen', 'percent': None}],
        'grapeNote': (
            '本地称「黑后」（库内实体名为「黑皇后」Black Queen），是台湾地区酿造红酒的主要品种之一；'
            '另一主栽品种「金香」（Golden Muscat）本次未在库内匹配到实体，故未挂链。'
            '品种信息来自本次来源页对二林镇酿酒葡萄产业的叙述，未取得逐品种面积占比。'
        ),
        'appellationCreatedNote': (
            '本次未检索到该地区葡萄酒地理标志（原产地命名）制度的官方说明，故不填写命名年份。'
        ),
        'areaHectares': None,
        'areaNote': (
            '未取到官方发布的「全地区」葡萄种植面积。来源页给出的都是彰化县二林镇口径，且互不一致：'
            '农业知识入口网《2010年彰化县葡萄酒新酒发表会暨产业概述》写「民國80-85年，栽培面積曾高達1,800公頃……'
            '目前栽培面積維持在150公頃左右」；同一入口网影音《台灣酒窖》写「最大種植面積1848公頃」；'
            '联合新闻网 2025 年报道写「釀酒葡萄種植面積約50公頃」、另一篇写「全鎮釀酒葡萄種植減至約200公頃」。'
            '年份与统计范围均不同，按规矩置空并列出备选。'
        ),
        'areaAlternatives': [
            {'name': '农业知识入口网《2010年彰化縣葡萄酒新酒發表會暨產業概述》（二林鎮，歷史峰值）',
             'value': '1,800 公顷（民國80-85年，約 1991-1996）', 'sourceURL': SOURCE_MAIN},
            {'name': '农业知识入口网《2010年彰化縣葡萄酒新酒發表會暨產業概述》（二林鎮，現狀）',
             'value': '約 150 公頃', 'sourceURL': SOURCE_MAIN},
            {'name': '农业知识入口网影音《台灣酒窖》（二林鎮，歷史峰值）',
             'value': '1,848 公顷', 'sourceURL': SOURCE_VIDEO},
        ],
        'productionNote': '未取到官方发布的产量数字。',
        'producersNote': (
            '来源页对二林镇合法酒庄数给出多个互不一致的数字：农业知识入口网《2010年…產業概述》写'
            '「目前合格酒莊高達22家，是台灣地區成立合法酒莊最多之鄉鎮」；联合新闻网 2025 年稿写'
            '「二林鎮現有11家酒莊」、另一篇写「目前全台368鄉鎮市約有177家酒莊，二林鎮就有9家」。'
            '数字随年份递减，本图鉴本次未收录其中任何一家。'
        ),
        'subzones': [
            {'name': '彰化县二林镇', 'hectares': None,
             'note': ('来源页原文「二林鎮位於彰化縣西南方……該鎮數十年來以釀酒葡萄產業聞名全台，'
                      '種植面積為全台之冠」；早期公賣局契作区的核心，也是全地区合法酒庄最密集的乡镇。'
                      '本图鉴暂未收录该地区酒庄。')},
        ],
        'communes': ['二林镇'],
        'provinces': ['台湾省'],
        'soil': '来源页原文「該鎮因有濁水溪的灌溉，土壤豐腴富含礦物質」，未给出土壤类型学名称，故不补。',
        'climate': (
            '来源页未给出气候指标。二林镇地处浊水溪冲积扇、旧浊水溪下游与鱼寮溪之间，'
            '原文称其为「典型風頭水尾的鄉鎮」（风头水尾：风大、水源末端）。'
        ),
        'geography': (
            '来源页原文「二林鎮位於彰化縣西南方，地處舊濁水溪下游與魚寮溪之間之濁水溪沖積扇上」。'
            '全地区酿酒葡萄与酒庄以彰化县二林镇为中心，另有台中后里、南投等早期契作区（本次来源页未展开）。'
        ),
        'officialQuote': (
            '「二林鎮位於彰化縣西南方，地處舊濁水溪下游與魚寮溪之間之濁水溪沖積扇上……該鎮數十年來以釀酒葡萄產業聞名全台，'
            '種植面積為全台之冠，據統計於民國80-85年，栽培面積曾高達1,800公頃，但由於86年公賣局終止收購合約，'
            '使得此一產業陷入窘境，目前栽培面積維持在150公頃左右。」「2002後政府因應WTO政策，積極推動國內農業轉型及產業升級，'
            '該鎮部分農民在政策鼓勵下申請酒莊證照，目前合格酒莊高達22家，是台灣地區成立合法酒莊最多之鄉鎮。」'
            '（页面维护单位：農業部 臺中區農業改良場，地址 100212 臺北市中正區南海路 37 號）'
        ),
        'sourceTitle': SOURCE_TITLE_MAIN,
        'sourceURL': SOURCE_MAIN,
        'additionalSources': [
            {'name': '中国台湾地区农业主管部门农业知识入口网 · 影音专区《台湾酒窖》（刊登 2013-03-14）',
             'sourceURL': SOURCE_VIDEO,
             'note': ('同网站独立文档，给出「最大種植面積1848公頃」「二林成為酒莊密集度最高城鎮」，'
                      '与主来源 1,800 公顷口径不一致。')},
        ],
        'checkedDate': CHECKED,
        'notes': (
            '本条目为地图占位产区：按 Canz 的要求只登记「中国台湾」这一层级，暂不收录任何酒庄/酒款，'
            '故右侧面板显示 0 家酒庄 · 0 款酒 · 0 张图片（与库内 hermitage 同类状态）。'
            '坐标用岛屿几何中心而非产地中心，仅为把标签落在台湾岛上。'
            'CN 现有产区（ningxia / penglai / shangri-la）的 originalLanguage 均写作 "en"，'
            '本条按实际来源语种写 "zh"。'
        ),
        'originalLanguage': 'zh',
        'localizations': {
            'zh': {
                'name': '中国台湾',
                'description': (
                    '中国台湾的酿酒葡萄产区，以彰化县二林镇为核心。二林镇地处浊水溪冲积扇，数十年以酿酒葡萄闻名，'
                    '种植面积曾为全地区之冠（1990 年代峰值约 1,800 公顷）；1997 年公卖局终止收购契约后，'
                    '农户转向自设酒庄，使二林成为全地区合法酒庄最密集的乡镇。本图鉴暂未收录该地区的酒庄与酒款。'
                ),
                'sourceURL': SOURCE_MAIN,
                'sourceTitle': SOURCE_TITLE_MAIN,
                'checkedDate': CHECKED,
                'status': 'verified',
            },
            'en': {
                'name': 'Taiwan, China',
                'description': '',
                'sourceURL': '',
                'sourceTitle': '',
                'checkedDate': CHECKED,
                'status': 'draft',
            },
        },
        'verification': {
            'method': 'auto:source-count',
            'sourceCount': 2,
            'status': 'multi-source',
            'checkedDate': CHECKED,
            'note': ('来源数来自 sourceURL + additionalSources + producerDirectory；'
                     '多来源不等于数字一致，数字冲突见 discrepancies.json'),
        },
    },
    'version': 1,
    'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    'origin': '国家窗口采集 · 中国台湾地区农业主管部门农业知识入口网（葡萄主题馆 / 影音专区）',
}


def point_in_taiwan(lat, lng):
    """用 world.geojson 里中国要素的第 3 个多边形（台湾岛）做包含判定。"""
    gj = json.loads(WORLD.read_text(encoding='utf-8'))
    cn = next(f for f in gj['features'] if f['properties']['name'] == '中国')
    ring = cn['geometry']['coordinates'][2][0]
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            if lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def main():
    seed = json.loads(SEED.read_text(encoding='utf-8'))
    ids = {e['id'] for e in seed}
    assert 'taiwan' not in ids, 'id=taiwan 已存在，勿重复插入'
    assert RECORD['data']['country'] == '中国', 'country 必须是中国'

    lat, lng = RECORD['data']['lat'], RECORD['data']['lng']
    assert point_in_taiwan(lat, lng), \
        '标注点 (%.2f, %.2f) 不在台湾岛多边形内，标签会掉到海里' % (lat, lng)

    idx = next(i for i, e in enumerate(seed) if e['id'] == ANCHOR_AFTER)
    seed.insert(idx + 1, RECORD)

    backup = BASE / 'work' / ('_catalog-seed.before-taiwan-%s.json'
                              % datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 落盘后自检 ----
    seed2 = json.loads(SEED.read_text(encoding='utf-8'))
    tw = next(e for e in seed2 if e['id'] == 'taiwan')
    cn_regions = [e for e in seed2 if e['kind'] == 'region' and e['data'].get('country') == '中国']
    kids = [e['id'] for e in cn_regions if not e['data'].get('regionId')]
    wins = [e for e in seed2 if e['kind'] == 'winery' and e['data'].get('regionId') == 'taiwan']
    print('记录数 %d -> %d' % (len(seed) - 1 + 1, len(seed2)))
    print('中国的根级子产区:', kids)
    print('挂在中国台湾下的酒庄数:', len(wins), '(要求 0)')
    print('中文名 %s | en %s | lat/lng %s %s'
          % (tw['name'], tw['data']['en'], tw['data']['lat'], tw['data']['lng']))
    print('备份:', backup.name)
    assert len(wins) == 0, '不得挂酒庄'


if __name__ == '__main__':
    main()
