"""向 catalog-seed.json 追加「噶玛兰威士忌酒厂」实体，挂到中国台湾产区下。

需求（Canz 2026-09-22）："如果一定要挂的话台湾挂一个威士忌酒庄 KAVALAN"。

落点说明：
  · kind 仍用 'winery' —— 站点的生产者类型只有这一档，没有 distillery。
    因此 notes 与 localizations.zh.description 里都**显式写明这是威士忌蒸馏厂、不是葡萄酒庄**，
    避免图鉴口径被误读。葡萄品种 / 酒款字段一律留空，不为它虚构葡萄酒记录。
  · regionId='taiwan'，让「中国台湾」从 0 酒庄变成 1 家。
  · 坐标 24.7142 / 121.6896 来自 OSM way/340266525（craft=distillery），
    其地址「員山路二段 326／蓁巷村／員山鄉／宜蘭縣 264」与官方公布厂址逐字一致（已做正反双向核对）。
  · 中国台湾地区交通主管部门观光署那页给的经纬度 121.41322/24.42505 与厂址不符
    （落在宜兰大同乡南山村一带，距员山乡约 30 km），不采用，但要写进 additionalSources 备案。

跑法：python3 scripts/add-kavalan-winery.py
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import os as _os
BASE = Path(_os.environ.get('TERROIR_ROOT', Path(__file__).resolve().parent.parent))
SEED = BASE / 'data/catalog-seed.json'

CHECKED = '2026-09-22'
SRC_KEID = 'https://keid.nat.gov.tw/creativelife/information/enjoy_ct?id=172'
SRC_BRAND = 'https://www.kavalanwhisky.com/zh-tw/intro.php'
SRC_TOUR = 'https://www.taiwan.net.tw/m1.aspx?sNo=0001106&id=A12-00626'
SRC_OSM = 'https://www.openstreetmap.org/way/340266525'

NOTES = (
    '⚠️ 本条目是威士忌蒸馏厂（烈酒），**不是葡萄酒庄**。挂在中国台湾产区下是 Canz 2026-09-22 的明确要求'
    '——该产区原本是 0 酒庄的地图占位产区。本站生产者类型只有 kind:\'winery\' 一档，故沿用；'
    '葡萄品种与酒款字段一律留空，不为它虚构葡萄酒记录。'
    '规模与获奖（据中国台湾地区交通主管部门观光署景点页与产业发展署「想体验」页）：'
    '金车集团 2006 年自苏格兰引进二组蒸馏器（年产量 200 万瓶），2008 年再购德国设备，'
    '2016 年大幅扩厂、新建蒸馏二厂与熟成二厂并再引进 8 组苏格兰蒸馏器，目前年产量达 1,000 万瓶，'
    '称世界前十大威士忌酒厂；曾两度获 WWA 最佳人气酒厂奖、四度获 IWSC 亚太区年度蒸馏酒厂，'
    '2017 年获 IWSC「世界年度蒸馏酒厂冠军」，累计逾 900 面金牌。'
)

DESC_ZH = (
    '金车集团（King Car）在宜兰县员山乡设立的蒸馏厂，是中国台湾地区第一座威士忌蒸馏厂，'
    '品牌取宜兰旧称「噶玛兰」命名，2006 年开始生产。厂区邻近雪山山脉水源，'
    '设有从磨麦、糖化、发酵、蒸馏到熟成的完整产线，并对公众开放导览与品评。'
    '⚠️ 本条目是威士忌蒸馏厂，不是葡萄酒庄。'
)

RECORD = {
    'id': 'winery-kavalan-distillery',
    'kind': 'winery',
    'name': '噶玛兰威士忌酒厂',
    'data': {
        'name': '噶玛兰威士忌酒厂',
        'en': 'Kavalan Distillery',
        'aliases': ['KAVALAN', 'Kavalan', '金车噶玛兰威士忌酒厂', '金車噶瑪蘭威士忌酒廠',
                    'King Car Kavalan Distillery'],
        'country': '中国',
        'regionId': 'taiwan',
        'address': '宜兰县员山乡员山路二段326号（邮编 264），电话 +886 3 922 9000',
        'lat': 24.7142,
        'lng': 121.6896,
        'website': 'https://www.kavalanwhisky.com/',
        'sourceTitle': '中国台湾地区经济主管部门产业发展署 · MIT微笑标章「想体验 Enjoy」— 噶玛兰威士忌酒厂',
        'sourceURL': SRC_KEID,
        'additionalSources': [
            {'name': '噶玛兰威士忌官方品牌站 · 品牌沿革',
             'sourceURL': SRC_BRAND,
             'note': '官方站，用于核对厂名、产销规模与获奖叙述。'},
            {'name': '中国台湾地区交通主管部门观光署 · 宜兰县景点「噶玛兰酒厂」',
             'sourceURL': SRC_TOUR,
             'note': ('该页所列经纬度 121.41322/24.42505 与厂址不符'
                      '（落在宜兰大同乡南山村一带，距员山乡约 30 km），未采用其坐标；'
                      '地址与电话与其余来源一致，仅取其文字叙述。')},
        ],
        'locationSourceURL': SRC_OSM,
        'locationPrecision': ('OSM 实体「金車威士忌酒廠」（craft/distillery）代表点，'
                              '其地址「員山路二段 326／蓁巷村／員山鄉／宜蘭縣 264」'
                              '与官方公布厂址逐字一致；为该蒸馏厂园区代表点，非地块边界。'),
        'checkedDate': CHECKED,
        'notes': NOTES,
        'originalLanguage': 'zh',
        'localizations': {
            'zh': {
                'name': '噶玛兰威士忌酒厂',
                'description': DESC_ZH,
                'sourceURL': SRC_KEID,
                'sourceTitle': '中国台湾地区经济主管部门产业发展署 · MIT微笑标章「想体验 Enjoy」',
                'checkedDate': CHECKED,
                'status': 'verified',
            },
            'en': {
                'name': 'Kavalan Distillery',
                'description': ('King Car Group\'s distillery in Yuanshan, Yilan — the first whisky distillery '
                                'in the Taiwan region of China, named after Yilan\'s old name "Kavalan". '
                                'It has produced whisky since 2006 and offers guided tours. '
                                'Note: this is a whisky distillery, not a wine estate.'),
                'sourceURL': SRC_KEID,
                'sourceTitle': 'Industrial Development Administration, Taiwan region of China — MIT Smile',
                'checkedDate': CHECKED,
                'status': 'verified',
            },
        },
        'verification': {
            'method': 'auto:country-window+http',
            'checkedDate': CHECKED,
            'coordinateInCountryWindow': True,
            'status': 'ok',
        },
    },
    'version': 1,
    'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    'origin': 'Canz 指定挂载 · 中国台湾产区（2026-09-22）',
}


def main():
    seed = json.loads(SEED.read_text(encoding='utf-8'))
    ids = {e['id'] for e in seed}
    assert RECORD['id'] not in ids, 'id 已存在：' + RECORD['id']
    assert 'taiwan' in ids, 'regionId 指向的 taiwan 产区不存在，先跑 add-taiwan-region.py'
    assert RECORD['data']['regionId'] in ids, 'regionId 悬空'

    seed.append(RECORD)
    backup = BASE / 'work' / ('_catalog-seed.before-kavalan-%s.json'
                              % datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 落盘后自检 ----
    seed2 = json.loads(SEED.read_text(encoding='utf-8'))
    k = next(e for e in seed2 if e['id'] == RECORD['id'])
    d = k['data']
    print('记录数 ->', len(seed2))
    print('id=%s | name=%s | en=%s' % (k['id'], k['name'], d['en']))
    print('country=%s | regionId=%s | lat,lng=%s,%s' % (d['country'], d['regionId'], d['lat'], d['lng']))
    print('sourceURL:', d['sourceURL'])
    print('locationSourceURL:', d['locationSourceURL'])
    kids = [e['id'] for e in seed2
            if e['kind'] == 'winery' and e['data'].get('regionId') == 'taiwan']
    print('挂在中国台湾下的生产者:', kids)
    assert len(kids) == 1
    print('备份:', backup.name)


if __name__ == '__main__':
    main()
