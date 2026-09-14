# coding: utf-8
"""Build the 001期 Château-Grillet collection bundle.

Château-Grillet is a monopole: one appellation, one estate, one grape. So the
bundle is shaped differently from Condrieu's 90-producer directory — here the
value is depth on a single estate, and the two things that were missing before
are geography (lat/lng were null, so the estate never appeared on the map) and
images (there were none, for either the people or the wines).

Everything written here follows the 采集规格: coordinates only with evidence,
appellation read off the bottle, provenance on every image, per-language
localizations with a source and a verified status, and honest reporting of
figures that sources disagree on.

Usage: python3 scripts/build-grillet-bundle.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / 'chateau-grillet'
IMG = OUT / 'images'
MANIFEST = json.loads((IMG / 'wine-image-manifest.json').read_text())
IMAGES = {g['file']: g for g in MANIFEST['producers'][0]['images']}

# ---------------------------------------------------------------- geography
OSM_URL = 'https://www.openstreetmap.org/way/337680164'
LAT, LNG = 45.4501025, 4.7519914
GEO_PRECISION = ('OSM way/337680164（historic=castle，名称“Château Grillet”，'
                 'Vérin，Route de Jeanraude）附带 extratag website=chateau-grillet.com，'
                 '据此认定为本庄园建筑。该点为庄园建筑点，不是产区法定边界；'
                 '未取得 INAO 边界文件，故点位不代表 AOC 范围。')

SITE = 'https://chateau-grillet.com/'
SRC = {
    'estate_fr': (SITE + 'le-domaine/', 'Château-Grillet · Le domaine', 'fr'),
    'estate_en': (SITE + 'en/the-estate/', 'Château-Grillet · The estate', 'en'),
    'wines_fr': (SITE + 'les-vins/', 'Château-Grillet · Les vins', 'fr'),
    'engagements': (SITE + 'les-engagements/', 'Château-Grillet · Les engagements', 'fr'),
    'contact': (SITE + 'contact/', 'Château-Grillet · Contacts', 'fr'),
    'inao': ('https://www.inao.gouv.fr/produit/chateau-grillet-20028',
             'INAO · Château-Grillet（法国国家原产地命名管理局）', 'fr'),
    'decanter90': ('https://www.decanter.com/wine/northern-rhone/'
                   'meet-the-new-technical-manager-of-chateau-grillet-on-its-90th-anniversary/',
                   'Decanter · Château-Grillet: The legendary Rhône white steps into a new era'
                   '（Matt Walls，2026-03-24）', 'en'),
    'decanter_taste': ('https://www.decanter.com/premium/chateau-grillets-wines-rhone-viognier-429953',
                       'Decanter · Château-Grillet: How recent releases compare to other top '
                       'Rhône Viogniers（Andy Howard MW）', 'en'),
    'osm': (OSM_URL, 'OpenStreetMap · way/337680164 “Château Grillet”', 'en'),
    'baidu': ('https://baike.baidu.com/item/%E6%A0%BC%E9%87%8C%E5%8F%B6%E9%85%92%E5%BA%84',
              '百度百科 · 格里叶酒庄', 'zh'),
}


def img_block(files):
    out = []
    for f in files:
        g = IMAGES.get(f)
        if not g:
            continue
        out.append({
            'relativePath': g['relativePath'], 'file': g['file'],
            'role': g['role'], 'appellation': g.get('appellation'),
            'confidence': g['confidence'], 'attribution': g.get('attribution'),
            'width': g['width'], 'height': g['height'], 'bytes': g['bytes'],
            'sha256': g['sha256'], 'sourcePage': g['sourcePage'],
            'directURL': g['directURL'], 'retrievedAt': g['retrievedAt'],
            'classificationMethod': g.get('classificationMethod'),
            'reviewNote': g.get('reviewNote'), 'rights': g['rights'],
        })
    return out


PEOPLE = ['18-Frederic-Engerer_IG-20250319-0159-3-scaled.jpg', '22-Frederic-Engerer_IG-20250319-0159-3.jpg',
          '19-alois-houeto.jpg', '20-IG-chateau-Grillet_IG_3534-047-scaled.jpg',
          '23-IG-chateau-Grillet_IG_3534-047.jpg']
ESTATE = ['01-Grillet-scaled.jpg', '09-Grillet.jpg', '12-mineral-vegetal-scaled.jpg',
          '13-histoire-millenaire.jpg', '21-mineral-vegetal.jpg', '26-Grillet_03.jpg',
          '24-Grillet_04-scaled.jpg', '25-Grillet_02.jpg', '05-Grillet_03-1.jpg',
          '14-cave-vin.jpg', '17-cave-vignoble.jpg', '15-chateau-grillet.jpg']
MAP = ['04-Grillet_01-1.jpg']
W_GRAND = ['02-Grillet_Hero-scaled.jpg', '10-Grillet_Hero.jpg', '03-Grillet_02-1.jpg',
           '06-Grillet_04-1.jpg', '16-vignoble.jpg']
W_CDR = ['07-Cotes-du-Rhone-2023-scaled.jpeg', '11-Cotes-du-Rhone-2023.jpeg']
W_CARTHERY = ['08-Grillet_05.jpg']

# ---------------------------------------------------------------- records
region = {
    'id': 'chateau-grillet', 'kind': 'region', 'name': '格里叶堡产区',
    'data': {
        'name': '格里叶堡产区',
        'en': 'Château-Grillet AOC',
        'country': '法国',
        'regionId': 'rhone',
        'lat': LAT, 'lng': LNG,
        'locationSourceURL': SRC['osm'][0],
        'locationPrecision': GEO_PRECISION,
        'grapes': [{'id': 'grape-ab28e1d2953f', 'percent': 100}],
        'appellationCreated': '1936',
        'appellationCreatedNote': ('法定产区 1936 年获批，官方庄园自述“Since 1936”；'
                                   'Decanter 记为 1936 年，BottleofItaly 记 12 月 8 日，'
                                   'Decanter 另一篇记 12 月 11 日 —— 月日存在分歧，年份一致，故只登记年份。'),
        'areaHectares': None,
        'areaNote': ('面积各方给出 3.2 / 3.5 / 3.8 / 4 公顷不等：庄园官网英文页写'
                     '“four hectares in a single block”，Decanter 与多家进口商写 3.5 公顷。'
                     '口径未统一前不填单一数字。'),
        'terraceCount': None,
        'terraceNote': ('梯田级数官网写 102 级，Decanter 与 Vinispi 写 87 级。存在分歧，不填单一数字。'),
        'elevationMeters': [150, 250],
        'singleEstate': True,
        'originalLanguage': 'fr',
        'localizations': {
            'fr': {
                'name': 'Château-Grillet',
                'description': ('Appellation d’origine contrôlée depuis 1936, Château-Grillet est un '
                                'monopole : l’appellation, le domaine, le vignoble et le vin ne font qu’un. '
                                'Le vignoble, implanté entre Vérin et Saint-Michel-sur-Rhône sur des '
                                'coteaux aménagés en terrasses soutenues par des murs de pierres sèches '
                                '— les « chaillées » —, est planté exclusivement de viognier sur des sols '
                                'granitiques. L’appellation forme une enclave à l’intérieur de celle de '
                                'Condrieu.'),
                'sourceURL': SRC['estate_fr'][0], 'sourceTitle': SRC['estate_fr'][1],
                'checkedDate': DATE, 'status': 'verified',
            },
            'en': {
                'name': 'Château-Grillet',
                'description': ('An appellation d’origine contrôlée since 1936, Château-Grillet is a '
                                'monopole: appellation, estate, vineyard and wine are one and the same. '
                                'The vineyard sits between Vérin and Saint-Michel-sur-Rhône on terraces '
                                'held by dry-stone walls — locally ‘chaillées’ — planted exclusively to '
                                'Viognier on granite soils. The appellation forms an enclave within Condrieu.'),
                'sourceURL': SRC['estate_en'][0], 'sourceTitle': SRC['estate_en'][1],
                'checkedDate': DATE, 'status': 'verified',
            },
            'zh': {
                'name': '格里叶堡产区',
                'description': ('格里叶堡是法国最小的法定产区之一，1936 年获 AOC 认证。它是“独占园”'
                                '（monopole）产区：产区、酒庄、葡萄园与酒款是同一个主体，全产区仅一家'
                                '生产者。葡萄园位于 Vérin 与 Saint-Michel-sur-Rhône 之间的陡坡上，'
                                '以干砌石墙“chaillées”托起梯田，全部种植维欧尼（Viognier），'
                                '土壤为花岗岩。产区内嵌于康德里厄（Condrieu）产区之中。'),
                'sourceURL': SRC['baidu'][0], 'sourceTitle': SRC['baidu'][1],
                'checkedDate': DATE, 'status': 'verified',
                'note': ('中文名与“独占园、1936 年 AOC、内嵌于 Condrieu”等要点与庄园官网法文/英文页'
                         '一致。百度百科为可编辑来源，仅在其与官方口径一致处采用。'),
            },
        },
        'sourceTitle': SRC['estate_fr'][1],
        'sourceURL': SRC['estate_fr'][0],
        'checkedDate': DATE,
        'notes': ('全产区唯一生产者为本庄园。坐标此前为空，地图上完全不显示点位；'
                  '本次补入有据坐标。面积与梯田级数各方口径不一致，暂不填单一数值。'),
    },
    'version': 2, 'updated': '2026-09-13T15:20:00.000Z',
    'origin': '每日一产区 · 001期重采（地理与图片补齐）',
}

winery = {
    'id': 'winery-chateau-grillet', 'kind': 'winery', 'name': '格里叶堡',
    'data': {
        'name': '格里叶堡',
        'en': 'Château-Grillet',
        'aliases': ['Château Grillet', 'Domaine de Château Grillet', '格里叶酒庄'],
        'country': '法国',
        'regionId': 'chateau-grillet',
        'address': 'Château-Grillet, Route de Jeanraude, 42410 Vérin, France',
        'lat': LAT, 'lng': LNG,
        'website': SITE,
        'locationSourceURL': OSM_URL,
        'locationPrecision': ('OSM way/337680164 附带本庄园官网作为 website 标签，'
                             '据此认定该建筑即本庄园；具体到访门址以官网 contact 页为准。'),
        'contactSourceURL': SRC['contact'][0],
        'checkedDate': DATE,
        'owner': 'Artémis Domaines（Pinault 家族）',
        'ownerSince': '2011',
        'staff': [
            {'name': 'Frédéric Engerer', 'role': 'Artémis Domaines 首席执行官',
             'asOf': '2026', 'sourceURL': SRC['estate_fr'][0]},
            {'name': 'Aloïs Houeto', 'role': 'Château-Grillet 技术负责人',
             'asOf': '2026', 'sourceURL': SRC['decanter90'][0]},
        ],
        'staffNote': ('官网团队栏列出 Frédéric Engerer 与 Aloïs Houeto，并写明庄园由 4 人小组常年打理。'
                      '历史报道另提及 Alessandro Noli（2018 年报道的酿酒负责人）与 Cramette'
                      '（前任技术总监）；两者均未列为现任，故不写入 staff。'),
        'farming': ['生物动力法（2016 年获得认证）', '手工耕作', 'Guyot Poussard 修剪'],
        'productionBottlesPerYear': None,
        'productionNote': '年产量各方写 8,000–11,000 瓶，口径不一，不填单一数值。',
        'images': img_block(PEOPLE + ESTATE + MAP),
        'imageSummary': {
            'people': len(PEOPLE), 'estateAndTerroir': len(ESTATE), 'map': len(MAP),
            'note': '人物图为 Frédéric Engerer 肖像两张、Aloïs Houeto 肖像一张、团队合影两张。',
        },
        'originalLanguage': 'fr',
        'localizations': {
            'fr': {
                'name': 'Château-Grillet',
                'description': ('Le domaine est le monopole de l’appellation Château-Grillet. '
                                'Le vignoble occupe un amphithéâtre naturel exposé au sud, entre Vérin '
                                'et Saint-Michel-sur-Rhône, planté exclusivement de viognier sur des sols '
                                'granitiques pauvres, parfois enrichis de lœss. Une petite équipe de '
                                'quatre personnes, dirigée par Aloïs Houeto, travaille la vigne toute '
                                'l’année ; tout est fait à la main.'),
                'sourceURL': SRC['estate_fr'][0], 'sourceTitle': SRC['estate_fr'][1],
                'checkedDate': DATE, 'status': 'verified',
            },
            'en': {
                'name': 'Château-Grillet',
                'description': ('The estate is the sole proprietor of the Château-Grillet appellation '
                                'and the only producer within it. The vineyard forms a south-facing natural '
                                'amphitheatre between Vérin and Saint-Michel-sur-Rhône, planted entirely to '
                                'Viognier on poor granite soils sometimes enriched with loess. A team of four, '
                                'led by Aloïs Houeto, works the vines year-round; everything is done by hand.'),
                'sourceURL': SRC['estate_en'][0], 'sourceTitle': SRC['estate_en'][1],
                'checkedDate': DATE, 'status': 'verified',
            },
            'zh': {
                'name': '格里叶堡',
                'description': ('庄园是格里叶堡法定产区的唯一生产者，也是该产区内唯一酒庄。葡萄园位于'
                                'Vérin 与 Saint-Michel-sur-Rhône 之间一处朝南的天然半圆形坡地，'
                                '全部种植维欧尼，土壤为贫瘠花岗岩，局部夹风成黄土。由 Aloïs Houeto '
                                '带领的 4 人小组常年打理，田间作业几乎全靠手工。'),
                'sourceURL': SRC['baidu'][0], 'sourceTitle': SRC['baidu'][1],
                'checkedDate': DATE, 'status': 'verified',
                'note': '与庄园官网法文/英文页核对一致；4 人小组与负责人姓名来自官网 The estate 页。',
            },
        },
        'sourceTitle': SRC['estate_fr'][1],
        'sourceURL': SRC['estate_fr'][0],
        'checkedDate': DATE,
        'notes': ('2011 年由 Neyret-Gachet 家族售予 François Pinault 的 Artémis Domaines。'
                  '1976 年因其景观与古老葡萄园被列为法国国家遗产。2026 年为产区获批 90 周年。'),
    },
    'version': 2, 'updated': '2026-09-13T15:20:00.000Z',
    'origin': '每日一产区 · 001期重采（地理、人物与酒款图补齐）',
}

wines = [
    {
        'id': 'wine-chateau-grillet', 'kind': 'wine', 'name': 'Château-Grillet',
        'data': {
            'name': 'Château-Grillet',
            'country': '法国',
            'wineryId': 'winery-chateau-grillet',
            'regionId': 'chateau-grillet',
            'appellation': 'Château-Grillet',
            'isTargetAppellation': True,
            'colour': '白',
            'grapes': [{'id': 'grape-ab28e1d2953f', 'percent': 100}],
            'vinification': ('分地块采摘与压榨，控温发酵，在法国橡木桶中以细酒泥陈酿 18 个月，'
                             '新桶比例低（约 20%）。'),
            'images': img_block(W_GRAND),
            'imageSummary': {'bottles': len(W_GRAND),
                             'note': '五张均为庄园正牌酒瓶身图，其中两张为酒窖陈年场景、'
                                     '一张置于干砌石梯田壁龛、两张立于葡萄园中。'},
            'sourceTitle': SRC['wines_fr'][1], 'sourceURL': SRC['wines_fr'][0],
            'checkedDate': DATE,
            'notes': ('目标产区酒款。100% 维欧尼，为 AOC 规则要求，非本次核实的具体年份配方。'
                      '瓶身标签在 02/03/06/10/16 五张图中均可辨认庄园名。'),
        },
        'version': 2, 'updated': '2026-09-13T15:20:00.000Z',
        'origin': '每日一产区 · 001期重采（酒款图补齐）',
    },
    {
        'id': 'wine-chateau-grillet-cotes-du-rhone', 'kind': 'wine',
        'name': 'Château-Grillet Côtes-du-Rhône',
        'data': {
            'name': 'Château-Grillet Côtes-du-Rhône',
            'aliases': ['Pontcin'],
            'country': '法国',
            'wineryId': 'winery-chateau-grillet',
            'regionId': 'rhone',
            'appellation': 'Côtes-du-Rhône',
            'isTargetAppellation': False,
            'colour': '白',
            'grapes': [{'id': 'grape-ab28e1d2953f', 'percent': None}],
            'producedSince': '2011',
            'images': img_block(W_CDR),
            'imageSummary': {'bottles': len(W_CDR),
                             'note': '两张为同一构图的不同尺寸（原图 8256×5504 与缩放版），'
                                     '文件名标注 2023。'},
            'sourceTitle': SRC['wines_fr'][1], 'sourceURL': SRC['wines_fr'][0],
            'checkedDate': DATE,
            'notes': ('庄园其他产区酒款。官网称此 Côtes-du-Rhône 于 2011 年创建，'
                      '取自年轻藤与地块筛选。Decanter 与百度百科均称其别名为 “Pontcin”，'
                      '官网酒款页未使用该名，故仅登记为别名。'),
        },
        'version': 2, 'updated': '2026-09-13T15:20:00.000Z',
        'origin': '每日一产区 · 001期重采（酒款图与别名补齐）',
    },
    {
        'id': 'wine-chateau-grillet-condrieu-la-carthery', 'kind': 'wine',
        'name': 'Condrieu La Carthery',
        'data': {
            'name': 'Condrieu La Carthery',
            'country': '法国',
            'wineryId': 'winery-chateau-grillet',
            'regionId': 'rhone',
            'appellation': 'Condrieu',
            'isTargetAppellation': False,
            'colour': '白',
            'grapes': [{'id': 'grape-ab28e1d2953f', 'percent': None}],
            'producedSince': '2017',
            'vineyardAreaHectares': 0.25,
            'images': img_block(W_CARTHERY),
            'imageSummary': {'labels': len(W_CARTHERY),
                             'note': '标签特写，图上可读 “CONDRIEU / La Carthery / 2021”。'},
            'sourceTitle': SRC['wines_fr'][1], 'sourceURL': SRC['wines_fr'][0],
            'checkedDate': DATE,
            'notes': ('庄园其他产区酒款。官网写明自 2017 年起，来自与庄园相邻的 12 级梯田，'
                      '面积 0.25 公顷，花岗岩土壤。标签图可读年份 2021。'),
        },
        'version': 2, 'updated': '2026-09-13T15:20:00.000Z',
        'origin': '每日一产区 · 001期重采（酒款图与年份补齐）',
    },
]

vintages = [
    {
        'id': 'vintage-chateau-grillet-condrieu-la-carthery-2021', 'kind': 'vintage',
        'name': 'Condrieu La Carthery 2021',
        'data': {
            'name': 'Condrieu La Carthery 2021', 'year': 2021,
            'wineId': 'wine-chateau-grillet-condrieu-la-carthery',
            'wineryId': 'winery-chateau-grillet',
            'appellation': 'Condrieu', 'country': '法国',
            'images': img_block(W_CARTHERY),
            'evidenceLevel': 'label-readable',
            'checkedDate': DATE,
            'notes': ('年份依据为庄园官网酒款页的标签特写图，瓶标印有 “CONDRIEU La Carthery 2021”。'
                      '属“读瓶所得”，非年份表；未核实的年份一律不登记。'),
            'sourceTitle': SRC['wines_fr'][1], 'sourceURL': SRC['wines_fr'][0],
        },
        'version': 1, 'updated': '2026-09-13T15:20:00.000Z',
        'origin': '每日一产区 · 001期重采（年份来自瓶标签）',
    },
    {
        'id': 'vintage-chateau-grillet-cotes-du-rhone-2023', 'kind': 'vintage',
        'name': 'Château-Grillet Côtes-du-Rhône 2023',
        'data': {
            'name': 'Château-Grillet Côtes-du-Rhône 2023', 'year': 2023,
            'wineId': 'wine-chateau-grillet-cotes-du-rhone',
            'wineryId': 'winery-chateau-grillet',
            'appellation': 'Côtes-du-Rhône', 'country': '法国',
            'images': img_block(W_CDR),
            'evidenceLevel': 'official-filename',
            'checkedDate': DATE,
            'notes': ('年份依据为庄园官网酒款页图片文件名 “Cotes-du-Rhone-2023”。'
                      '文件名可佐证年份，但不是年份表，故单独标注证据等级。'),
            'sourceTitle': SRC['wines_fr'][1], 'sourceURL': SRC['wines_fr'][0],
        },
        'version': 1, 'updated': '2026-09-13T15:20:00.000Z',
        'origin': '每日一产区 · 001期重采（年份来自官网图片文件名）',
    },
]

events = [
    {
        'id': 'event-chateau-grillet-90ans-2026',
        'title': '格里叶堡法定产区成立 90 周年',
        'summary': ('Château-Grillet 法定产区 1936 年获批，2026 年满 90 年。'
                    'Decanter 记者 Matt Walls 于 2026 年 3 月实地走访，'
                    '记录庄园并未为此举办庆祝活动——没有气球，也没有横幅，'
                    '酿酒工作照常进行。'),
        'type': 'anniversary',
        'startDate': '2026-01-01', 'endDate': '2026-12-31',
        'dateNote': '周年年份为 2026 年，具体纪念日不在公开报道中，故按整年登记。',
        'publishedDate': '2026-03-24',
        'country': '法国', 'region': '格里叶堡产区',
        'lat': LAT, 'lng': LNG, 'precision': 'estate-building',
        'sourceName': SRC['decanter90'][1], 'sourceURL': SRC['decanter90'][0],
        'sourceLanguage': 'en',
        'verification': 'verified-media-report',
        'checkedDate': DATE,
        'notes': '发生日期（周年年份）与报道日期（2026-03-24）已区分登记。',
    },
    {
        'id': 'event-chateau-grillet-houeto-2026',
        'title': '格里叶堡新任技术负责人 Aloïs Houeto 上任',
        'summary': ('Aloïs Houeto 出任 Château-Grillet 技术负责人，29 岁，'
                    '农业工程背景，此前在勃艮第研究黑皮诺，并参与 Artémis Domaines 集团研发。'
                    '2024 年份是他的首个年份。他公开表示“咸感是格里叶堡的印记”，'
                    '目标是做出“独一无二、不同于康德里厄其他地块”的酒。'),
        'type': 'estate-appointment',
        'startDate': None, 'endDate': None,
        'dateNote': '任命具体日期未公开；报道称 2024 年份为其首个年份。',
        'publishedDate': '2026-03-24',
        'country': '法国', 'region': '格里叶堡产区',
        'lat': LAT, 'lng': LNG, 'precision': 'estate-building',
        'sourceName': SRC['decanter90'][1], 'sourceURL': SRC['decanter90'][0],
        'sourceLanguage': 'en',
        'verification': 'verified-media-report',
        'checkedDate': DATE,
        'notes': '对外公开报道，属庄园人事与酿造方向变动，非官方公告。',
    },
]

# ---------------------------------------------------------------- write
(OUT / 'catalog-additions.json').write_text(json.dumps({
    'date': DATE, 'regionId': 'chateau-grillet',
    'phase': '001期重采',
    'why': ('上一版 lat/lng 为空、图片为零。本次按采集规格重做，'
            '补齐有据坐标、人物图与酒款图、可核实年份与中文语种。'),
    'counts': {
        'regions': 1, 'wineries': 1, 'wines': len(wines), 'vintages': len(vintages),
        'imagesTotal': len(IMAGES),
        'imagesPeople': len(PEOPLE), 'imagesEstate': len(ESTATE), 'imagesMap': len(MAP),
        'imagesWine': len(W_GRAND) + len(W_CDR) + len(W_CARTHERY),
        'withCoordinates': 2,
    },
    'records': [region, winery] + wines + vintages,
}, ensure_ascii=False, indent=1) + '\n')

(OUT / 'events-additions.json').write_text(json.dumps({
    'date': DATE, 'regionId': 'chateau-grillet', 'events': events,
    'note': ('本期仅登记有公开报道来源的两条。采收、天气与灾害类消息未检索到可核实的'
             '2026 年记录，不写占位事件。发生日期与报道日期已分列。'),
}, ensure_ascii=False, indent=1) + '\n')

(OUT / 'geo-collected.json').write_text(json.dumps({
    'date': DATE, 'regionId': 'chateau-grillet',
    'method': ('OpenStreetMap Nominatim。只接受能证明是本主体的对象：'
               '该对象名为 “Château Grillet”，位于 Vérin 的 Route de Jeanraude，'
               '且其 extratag website 正是本庄园官网 chateau-grillet.com —— 三重吻合才采纳。'
               '同名的 Isère 省 localities、Moidieu-Détourbe 住宅、瑞士 Vich 建筑一律排除。'),
    'accepted': [{
        'id': 'winery-chateau-grillet', 'name': 'Château-Grillet',
        'lat': LAT, 'lng': LNG, 'osmType': 'way', 'osmId': 337680164,
        'osmClass': 'historic', 'osmTypeDetail': 'castle',
        'osmURL': OSM_URL, 'osmName': 'Château Grillet',
        'evidence': 'extratag website=http://chateau-grillet.com/fr/ 与庄园官网一致',
        'precision': GEO_PRECISION,
    }],
    'rejected': [
        {'name': 'Château Grillet', 'where': 'Les Côtes-d’Arey / Villeneuve-de-Marc / '
                                             'Moidieu-Détourbe / Estrablin (Isère)',
         'reason': '同名 locality 与公交站，与本庄园无关'},
        {'name': 'Château Grillet', 'where': 'Vich, Vaud, Suisse',
         'reason': '瑞士同名住宅建筑，超出法国范围'},
    ],
    'regionAnchor': {
        'id': 'chateau-grillet', 'lat': LAT, 'lng': LNG,
        'note': ('产区为独占园，地理上即本庄园所在的连续地块，故以庄园建筑点为产区锚点；'
                 '该点不代表 AOC 法定边界。'),
    },
}, ensure_ascii=False, indent=1) + '\n')

(OUT / 'sources.json').write_text(json.dumps({
    'date': DATE, 'regionId': 'chateau-grillet',
    'sources': [
        {'key': k, 'sourceURL': v[0], 'sourceTitle': v[1], 'sourceLanguage': v[2],
         'checkedDate': DATE}
        for k, v in SRC.items()
    ],
    'sourceQualityNote': ('庄园官网与 INAO 为一级来源；Decanter 为具名记者的专业媒体报道；'
                          '百度百科为可编辑来源，仅在其与一级来源一致处采用。'
                          '检索中出现的 AI 生成型聚合站（如 grokipedia）内容与已知事实冲突'
                          '（误称 Vidal-Fleury 持有本庄园），已弃用不采。'),
}, ensure_ascii=False, indent=1) + '\n')

discrepancies = {
    'date': DATE,
    'region': '格里叶堡产区',
    'items': [
        {'field': '葡萄园面积',
         'values': ['4 公顷（庄园官网英文页“four hectares in a single block”）',
                    '3.5 公顷（Decanter、多家进口商）',
                    '3.8 公顷（部分经销商资料）',
                    '3.2 公顷（AI 聚合站）'],
         'action': '不填单一数值，region.data.areaHectares 保持 null 并附说明。'},
        {'field': '梯田级数',
         'values': ['102 级（庄园官网）', '87 级（Decanter、Vinispi）'],
         'action': '不填单一数值，terraceCount 保持 null 并附说明。'},
        {'field': 'AOC 获批日期',
         'values': ['1936 年（官网与 Decanter 正文）', '12 月 8 日（BottleofItaly）',
                    '12 月 11 日（Decanter 另一篇）'],
         'action': '只登记年份 1936，月日留空。'},
        {'field': '藤龄',
         'values': ['平均 30 年', '35 年', '40–45 年', '45 年'],
         'action': '不登记藤龄，避免以偏概全。'},
        {'field': '年产量',
         'values': ['8,000–10,000 瓶', '10,000 瓶', '11,000 瓶'],
         'action': '不填单一数值，productionBottlesPerYear 保持 null。'},
        {'field': '副牌酒名称',
         'values': ['官网酒款页只写 “Côtes-du-Rhône”', 'Decanter 与百度百科称 “Pontcin”'],
         'action': '主名沿用官网 Côtes-du-Rhône，Pontcin 登记为别名。'},
    ],
}
(OUT / 'discrepancies.json').write_text(json.dumps(discrepancies, ensure_ascii=False, indent=1) + '\n')

print('region 1  winery 1  wines %d  vintages %d  events %d  images %d'
      % (len(wines), len(vintages), len(events), len(IMAGES)))
print('wrote to', OUT)
