# coding: utf-8
"""Build the 003期 Cornas collection bundle (region + wineries + events).

Inputs
  outputs/daily/2026-09-14/cornas-官方名录-2026-09-14.json   (official directory)
  work/cornas-geo-collected.json                            (OSM coordinates)

Outputs under outputs/collect/cornas/:
  catalog-additions.json, geo-collected.json, sources.json, region-context.json,
  events-additions.json, discrepancies.json, 知识库导入清单.json, HANDOFF.md

Usage: python3 scripts/build-cornas-bundle.py
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-14'
OUT = ROOT / 'outputs' / 'collect' / 'cornas'
OUT.mkdir(parents=True, exist_ok=True)
LISTING_URL = 'https://www.aoc-cornas.fr/cornas-producteurs.html'

WINERY_POI = {('craft', 'winery'), ('shop', 'wine'), ('shop', 'alcohol'),
              ('landuse', 'vineyard'), ('building', 'yes'), ('building', 'farm'),
              ('office', 'company'), ('shop', 'farm'), ('amenity', 'restaurant')}

# 北罗讷地理窗：Cornas 及同走廊（Tain / Saint-Péray / Malleval / Chavanay）。
# 越窗的命中一律转人工复核——南部酒商登记地址与同名异地实体都落在窗外。
NORTH_RHONE = (44.5, 45.6, 4.4, 5.2)  # south, north, west, east


def outside_north_rhone(lat, lng):
    s, n, w, e = NORTH_RHONE
    return not (s <= lat <= n and w <= lng <= e)


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


def main():
    directory = json.loads(
        (ROOT / 'outputs' / 'daily' / DATE / 'cornas-官方名录-2026-09-14.json').read_text())
    geo_rows = json.loads((ROOT / 'work' / 'cornas-geo-collected.json').read_text())
    geo_by_name = {r['name']: r for r in geo_rows}

    records, sources, accepted, held = [], [], [], []
    for item in directory['producers']:
        slug = slugify(item['name'])
        wid = 'winery-cornas-' + slug
        name = item['name']
        geo = geo_by_name.get(name, {})
        data = {
            'name': name,
            'country': '法国',
            'regionId': 'cornas',
            'aliases': [],
            'lat': None,
            'lng': None,
            'address': item.get('address'),
            'website': item.get('website'),
            'originalLanguage': 'fr',
            'localizations': {
                'fr': {
                    'name': name,
                    'sourceURL': LISTING_URL,
                    'sourceTitle': 'AOC Cornas · Domaines & Maisons（官方名录）',
                    'checkedDate': DATE,
                    'status': 'verified',
                }
            },
            'sourceTitle': 'AOC Cornas · Domaines & Maisons（官方名录）',
            'sourceURL': LISTING_URL,
            'checkedDate': DATE,
            'notes': '产区官方名录收录的生产者条目，名称照录名录原文（法文），未做中文译名。'
                     '地址/电话/邮箱来自名录；坐标按 OpenStreetMap 实体证据另行补齐。',
        }
        if item.get('contact'):
            data['contactPerson'] = item['contact']
        if item.get('phone'):
            data['phone'] = item['phone']
        if item.get('email'):
            data['email'] = item['email']

        sources.append({
            'id': slug, 'recordId': wid, 'kind': 'winery',
            'sourceName': 'AOC Cornas · Domaines & Maisons（官方名录）',
            'sourceURL': LISTING_URL, 'sourceLanguage': 'fr', 'checkedDate': DATE,
            'hit': '官方产区协会名录（单页列表）',
        })

        if geo.get('status') == 'matched':
            poi = (geo.get('osmClass'), geo.get('osmTypeDetail'))
            if poi not in WINERY_POI:
                held.append({
                    'name': name, 'recordId': wid,
                    'reason': 'OSM 实体类型 %s/%s 不属于酒庄/酒窖类点位' % poi,
                    'osmName': geo.get('osmName'), 'osmURL': geo.get('locationSourceURL'),
                    'lat': geo.get('lat'), 'lng': geo.get('lng'),
                })
            elif outside_north_rhone(geo['lat'], geo['lng']):
                held.append({
                    'name': name, 'recordId': wid,
                    'reason': '命中点在北罗讷地理窗（44.5–45.6N / 4.4–5.2E）之外：'
                              '可能是同名异地实体，或该生产者的登记经营地址在南罗讷。'
                              '两者都不能当作 Cornas 村内的酒庄点位，故不采纳、转人工复核。',
                    'osmName': geo.get('osmName'), 'osmURL': geo.get('locationSourceURL'),
                    'lat': geo.get('lat'), 'lng': geo.get('lng'),
                    'directoryAddress': item.get('address'),
                })
            else:
                data['lat'] = geo['lat']
                data['lng'] = geo['lng']
                data['locationSourceURL'] = geo['locationSourceURL']
                data['locationPrecision'] = geo['locationPrecision']
                if geo.get('website') and not data['website']:
                    data['website'] = geo['website']
                    data['notes'] += ' 官网地址取自 OpenStreetMap 实体的 website 标签，待官网二次核对。'
                sources.append({
                    'id': slug + '-geo', 'recordId': wid, 'kind': 'location',
                    'sourceName': 'OpenStreetMap 实体 · %s' % (geo.get('osmName') or ''),
                    'sourceURL': geo['locationSourceURL'], 'sourceLanguage': 'fr',
                    'checkedDate': DATE,
                    'hit': 'OpenStreetMap Nominatim（%s/%s）' % poi,
                })
                accepted.append(name)

        records.append({
            'id': wid, 'kind': 'winery', 'name': name, 'data': data, 'version': 1,
            'updated': '2026-09-14T01:20:00.000Z',
            'origin': '每日采集 · 官方名录与开放地图点位',
        })

    # 产区记录（坐标=Commune de Cornas 村镇代表点，非 AOC 边界）
    region_data = {
        'name': '科尔纳斯产区',
        'en': 'Cornas AOC',
        'country': '法国',
        'regionId': 'rhone',
        'lat': 44.9635210,
        'lng': 4.8475450,
        'locationSourceURL': 'https://www.openstreetmap.org/search?q=Cornas',
        'locationPrecision': 'Nominatim 命中的 “Cornas” 为阿尔代什省村镇（commune）代表点，'
                             '不是 AOC 法定边界；未取得 INAO 边界文件，点位不代表产区范围。',
        'grapes': [{'id': 'grape-36404f2e5476', 'percent': 100}],
        'appellationCreated': '1938',
        'appellationCreatedNote': 'AOC 1938 年获批（产区协会历史页、wein.plus、Wine-Searcher 一致）；'
                                 '现行技术规范由 2011-12-07 部令核定（winewithseth 引述）。',
        'areaHectares': None,
        'areaNote': '面积各方口径冲突：wein.plus 约 125 公顷、cluboenologique 称已种植 156 公顷、'
                    'Wine-Searcher 约 110 公顷、SoDivin 116 公顷。未统一前不填单一数字。',
        'elevationMeters': None,
        'singleCommune': True,
        'singleCommuneNote': '仅限 Cornas 单一市镇（阿尔代什省），只产静止红葡萄酒、100% 西拉；'
                             '无白葡萄酒与混酿（Wine-Searcher、winewithseth、产区协会 AOC 页）。',
        'originalLanguage': 'fr',
        'localizations': {
            'fr': {
                'name': 'Cornas',
                'description': 'Appellation d’origine contrôlée depuis 1938, Cornas est un cru de la '
                               'vallée du Rhône septentrionale situé sur la seule commune de Cornas '
                               '(Ardèche). Les vins sont exclusivement des rouges de syrah.',
                'sourceURL': 'https://www.aoc-cornas.fr/aoc-cornas.html',
                'sourceTitle': 'AOC Cornas · L’AOC',
                'checkedDate': DATE,
                'status': 'verified',
            },
            'zh': {
                'name': '科尔纳斯',
                'description': '1938 年获 AOC 认证的北罗讷河谷特级产区（cru），范围仅限'
                               '阿尔代什省科尔纳斯一个市镇，只产 100% 西拉红葡萄酒。',
                'sourceURL': 'https://www.aoc-cornas.fr/aoc-cornas.html',
                'sourceTitle': 'AOC Cornas · L’AOC（产区协会官方）',
                'checkedDate': DATE,
                'status': 'verified',
            },
        },
        'regulations': {
            'yieldMaxHlPerHa': 50,
            'minVineDensityPerHa': 4400,
            'pruning': ['Gobelet', 'Cordon de Royat', 'Guyot simple ou double'],
            'maxAlcoholAfterEnrichment': 13.5,
            'sourceURL': 'https://www.winewithseth.com/winewiki/cornas-aoc',
            'note': '产量上限 50 hl/ha（超标将整批失去 AOC 资格）、最低种植密度 4400 株/公顷、'
                    '限定修剪方式、加糖后酒精度上限 13.5%，均照录来源，未逐条回查部令原文。',
        },
        'lieuxDits': [
            'Les Arlettes', 'Le Coulet', 'Les Eygas', 'Jouvet', 'St Pierre', 'Peupliers',
            'Chaillot', 'Pied la Vigne', 'Reynards', 'Les Mazards', 'Sauman', 'Champelrose',
            'La Lègre', 'Sabarotte', 'Les Saveaux', 'Les Côtes', 'Patou', 'Combe',
        ],
        'lieuxDitsNote': '地名清单来自 wein.plus 条目；Reynards 一带另有 Tézier、La Geynale、'
                         'La Côte 等地块名。Cornas 没有官方的一级园/特级园分级，'
                         '这些地名是民间与市场惯用的地块名。',
        'producerCountNote': 'SoDivin 称“约五十家生产者”，而产区协会官方名录收录 71 条'
                             '（含产区外的酒商与合作社）。名录分母以协会名录为准。',
        'sourceTitle': 'AOC Cornas 产区协会 + wein.plus / Wine-Searcher / winewithseth 交叉核对',
        'sourceURL': 'https://www.aoc-cornas.fr/aoc-cornas.html',
        'checkedDate': DATE,
        'notes': '产区级记录。面积、海拔因口径冲突留空；未取得 INAO 边界文件，'
                 '坐标仅为村镇代表点。',
    }
    records.append({'id': 'cornas', 'kind': 'region', 'name': '科尔纳斯产区',
                    'data': region_data, 'version': 1,
                    'updated': '2026-09-14T01:20:00.000Z',
                    'origin': '每日采集 · 官方协会页与公开资料交叉核对'})

    # 产区级图片挂到产区记录（不隶属单一酒庄）
    region_manifest = OUT / 'images' / 'region' / 'region-media-manifest.json'
    region_images = []
    if region_manifest.exists():
        rmi = json.loads(region_manifest.read_text())
        for img in rmi['images']:
            region_images.append({
                'file': img['file'],
                'relativePath': 'images/region/' + img['file'],
                'role': img['role'],
                'attribution': 'producer-site',
                'appellation': None,
                'classificationMethod': img['classificationMethod'],
                'reviewNote': img.get('reviewNote'),
                'sourcePage': img['sourcePage'],
                'directURL': img['directURL'],
                'width': img['width'], 'height': img['height'],
                'bytes': img['bytes'], 'sha256': img['sha256'],
                'checkedDate': DATE,
            })
        region_data['images'] = region_images
        region_data['imageSummary'] = (
            '%d 张产区级图片，来自 AOC Cornas 官网（terroir / aoc / histoire / 活动页）。'
            '协会官网只提供 260–600px 小图，无更大原图，未做放大。' % len(region_images))

    # 酒庄图片：各家官网的人物/庄园照与酒款瓶标图，已逐张人工目视复核
    # （结论在 work/cornas/visual-review.json，回写后的 classificationMethod
    # 为 'agent-visual-review'，reviewNote 为中文读标结论）。
    prod_manifest = OUT / 'images' / 'wine-image-manifest.json'
    prod_by_slug = {}
    if prod_manifest.exists():
        pm = json.loads(prod_manifest.read_text())
        prod_by_slug = {p['slug']: p for p in pm['producers']}

    # 名录写法与官网检索名不一致的，按别名对齐（名录把这家写成 "MICHEL JOHANN"，
    # 官网/市场写法是 Domaine Johann Michel）。
    MANIFEST_SLUG_ALIASES = {'michel-johann': 'domaine-johann-michel'}

    producer_images, reviewed_images, unreached, partial = 0, 0, [], []
    producers_with_images = 0
    cornas_appellation = []
    appellation_tally = {}
    for rec in records:
        if rec['kind'] != 'winery':
            continue
        slug = rec['id'][len('winery-cornas-'):]
        entry = prod_by_slug.get(slug) or \
            prod_by_slug.get(MANIFEST_SLUG_ALIASES.get(slug, ''))
        if not entry:
            continue
        imgs = entry.get('images') or []
        fails = entry.get('failures') or []
        if fails:
            # 有失败 URL 不等于整站抓不到：只有"一张都没下来"才算站点未达。
            # 单个 URL 失败（空格未编码、重定向 /pages 缺 ID、老图 404、TLS 握手）很常见，
            # 只留计数与前 3 条样例，错误串截断，避免把爬虫日志原样塞进交付包。
            sample = []
            for f in fails[:3]:
                sample.append({
                    'url': (f.get('url') or '')[:160],
                    'error': str(f.get('error') or '')[:160],
                })
            item = {
                'producer': rec['name'], 'slug': slug,
                'website': entry.get('website'),
                'kind': 'site-unreached' if not imgs else 'partial-image-failures',
                'failureCount': len(fails),
                'sampleFailures': sample,
                'note': ('官网站点本次未能抓到任何图片（域名失效/403/502/超时等），'
                         '不是“该庄没有图”，下次优先重试。' if not imgs else
                         '多数图片已抓到，以下地址本次失败（空格未编码/老图 404/TLS 等），'
                         '不影响已入库的图。'),
            }
            if not imgs:
                unreached.append(item)
            else:
                partial.append(item)
        if not imgs:
            continue
        out_imgs = []
        for img in imgs:
            row = {
                'file': img['file'],
                'relativePath': 'images/%s/%s' % (slug, img['file']),
                'role': img.get('role'),
                'attribution': img.get('attribution'),
                'appellation': img.get('appellation'),
                'confidence': img.get('confidence'),
                'classificationMethod': img.get('classificationMethod'),
                'reviewNote': img.get('reviewNote'),
                'altText': img.get('altText'),
                'sourcePage': img.get('sourcePage'),
                'directURL': img.get('directURL'),
                'width': img.get('width'), 'height': img.get('height'),
                'bytes': img.get('bytes'), 'sha256': img.get('sha256'),
                'checkedDate': DATE,
            }
            out_imgs.append(row)
            if img.get('classificationMethod') == 'agent-visual-review':
                reviewed_images += 1
                if img.get('appellation'):
                    appellation_tally[img['appellation']] = \
                        appellation_tally.get(img['appellation'], 0) + 1
            if img.get('appellation') == 'Cornas':
                cornas_appellation.append({
                    'producer': rec['name'], 'slug': slug, 'file': img['file'],
                    'relativePath': row['relativePath'],
                })
        rec['data']['images'] = out_imgs
        rec['data']['imageSummary'] = (
            '%d 张官网图片（人物/庄园照 + 酒款瓶标图）；其中 %d 张经逐张目视复核，'
            '%d 张标面读得出 Cornas。' % (
                len(out_imgs),
                sum(1 for i in out_imgs
                    if i['classificationMethod'] == 'agent-visual-review'),
                sum(1 for i in out_imgs if i['appellation'] == 'Cornas')))
        producer_images += len(out_imgs)
        producers_with_images += 1

    (OUT / 'catalog-additions.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'schemaNote': '字段与网站 public/wineries.js 读取的 winery 记录一致；含 1 条 region 记录。',
        'counts': {
            'wineries': len([r for r in records if r['kind'] == 'winery']),
            'regionRecords': 1,
            'directoryProducers': len(directory['producers']),
            'withCoordinates': sum(1 for r in records
                                   if r['kind'] == 'winery' and r['data']['lat'] is not None),
            'withWebsite': sum(1 for r in records
                               if r['kind'] == 'winery' and r['data'].get('website')),
            'withImages': len(region_images) + producer_images,
            'heldForReview': len(held),
            'noEvidencedLocation': sum(1 for r in records if r['kind'] == 'winery'
                                       and r['data']['lat'] is None) - len(held),
            'regionImages': len(region_images),
            'producerImages': producer_images,
            'producersWithImages': producers_with_images,
            'reviewedImages': reviewed_images,
            'cornasAppellationImages': len(cornas_appellation),
        },
        'cornasAppellationImages': cornas_appellation,
        'producerImagesUnreached': unreached,
        'producerImagePartialFailures': partial,
        'appellationTallyFromReview': appellation_tally,
        'records': records,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'geo-collected.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'method': 'OpenStreetMap Nominatim，按生产者名录名称逐条查询（1 请求/秒），'
                  '姓名弱匹配 + POI 类型双重判定；用罗讷走廊 bbox（43.5,45.6,4.0,5.7）'
                  '排除同名异地实体。行政区划、公司总部一律不采纳为酒庄点位。',
        'statusCounts': {
            'matched': sum(1 for r in geo_rows if r['status'] == 'matched'),
            'no_evidenced_location': sum(1 for r in geo_rows
                                         if r['status'] == 'no_evidenced_location'),
            'query_failed': sum(1 for r in geo_rows if r['status'] == 'query_failed'),
        },
        'acceptedForCoordinates': accepted,
        'heldForReview': held,
        'raw': geo_rows,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'sources.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas', 'sources': sources,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'region-context.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'items': [
            {'topic': 'AOC 与范围',
             'claim': 'Cornas 1938 年获 AOC；范围仅限阿尔代什省 Cornas 一个市镇，'
                      '只产 100% 西拉的静止红葡萄酒。',
             'sourceURL': 'https://www.aoc-cornas.fr/aoc-cornas.html',
             'sourceTitle': 'AOC Cornas · L’AOC（产区协会官方）',
             'checkedDate': DATE},
            {'topic': '名称来源',
             'claim': '“Cornas” 源自凯尔特语，意为“烧焦/灼热的土地”，与朝向与日照有关。',
             'sourceURL': 'https://glossary.wein-plus.eu/cornas',
             'sourceTitle': 'wein.plus · Cornas',
             'checkedDate': DATE,
             'note': '词源说法照录单一来源，未做二次考证。'},
            {'topic': '地形',
             'claim': '葡萄园位于罗讷河右岸陡坡梯田上，园地之间有十一条溪流穿过，'
                      '多作为地块边界；坡地极陡。',
             'sourceURL': 'https://glossary.wein-plus.eu/cornas',
             'sourceTitle': 'wein.plus · Cornas',
             'checkedDate': DATE},
            {'topic': '土壤',
             'claim': None,
             'sourceURL': 'https://glossary.wein-plus.eu/cornas',
             'sourceTitle': 'wein.plus / yourwineiq 口径冲突（花岗岩+石灰岩 vs 花岗岩+白垩+黏土）',
             'checkedDate': DATE,
             'note': '两来源对底土描述互相矛盾，未取单一说法；详见 discrepancies.json。'},
            {'topic': '市场位置',
             'claim': '价格长期低于 Hermitage 与 Côte-Rôtie；近年地块名（Les Reynards、'
                      'Les Chaillots）在侍酒师与收藏者中知名度上升。',
             'sourceURL': 'https://cluboenologique.com/story/cornas-wine-producers-northern-rhone',
             'sourceTitle': 'Club Œnologique · Cornas: the Rhône less travelled',
             'checkedDate': DATE},
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    events = [
        {
            'id': 'event-cornas-vignobles-en-scene-2025',
            'title': 'Vignobles en Scène 2025（葡萄园开放日）',
            'type': 'event', 'subtype': 'open-days',
            'startDate': '2025-10-18', 'endDate': '2025-10-19',
            'dateNote': '标题即写明 18–19 Octobre 2025。',
            'publishedDate': None,
            'lat': 44.9635210, 'lng': 4.8475450,
            'precision': 'Cornas 村镇代表点（活动在产区各酒庄举行，非单一场地）',
            'country': '法国', 'region': 'Cornas',
            'summary': '受欧洲遗产日启发的年度酒庄开放活动，Cornas 与 Saint-Péray 的酒庄同时开门接待。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-vignobles-en-scene-18-et-19-octobre-2025_19.html',
            'verification': '协会官方期刊页面标题即写明「18 et 19 octobre 2025」，'
                            '正文说明 Cornas 与 Saint-Péray 酒庄同时开放。'
                            '**单一官方一手来源**，未在其他独立来源交叉核对。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-degustation-lyon-2025',
            'title': 'Cornas × Saint-Péray 里昂专业品鉴会',
            'type': 'event', 'subtype': 'trade-tasting',
            'startDate': '2025-11-17', 'endDate': None,
            'dateNote': '官方写「Lundi 17 novembre 2025, de 14h à 18h30」，单日活动。',
            'publishedDate': None,
            'lat': 45.7502072, 'lng': 4.8889974,
            'precision': 'Château de Montchat, Lyon 3e（OSM 实体 Château de Montchat）',
            'country': '法国', 'region': 'Lyon',
            'summary': '面向酒商、餐厅、侍酒师与买家的两产区联合专业品鉴会。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-degustation-professionnelle-lyon_20.html',
            'verification': '协会官方期刊页面正文写明「Lundi 17 novembre 2025, '
                            'de 14h à 18h30」，为单日专业场。场地 Château de Montchat '
                            '(Lyon 3e) 为页面对应地点，坐标取自 OSM 实体而非页面文字。'
                            '**单一官方一手来源**，未在其他独立来源交叉核对。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-masterclass-dvr-2025',
            'title': 'Découvertes en Vallée du Rhône 第 13 届 · Cornas & Saint-Péray 大师班',
            'type': 'event', 'subtype': 'masterclass',
            'startDate': '2025-03-31', 'endDate': '2025-04-03',
            'dateNote': '官方仅给出沙龙整体日期（31 mars au 3 avril 2025）；'
                        '大师班具体场次日期未公布，故按沙龙区间登记。',
            'publishedDate': None,
            'lat': 44.9635210, 'lng': 4.8475450,
            'precision': '巡回沙龙跨越南/北罗讷多个场地，未指定单一点位，取 Cornas 村镇代表点',
            'country': '法国', 'region': 'Vallée du Rhône',
            'summary': 'Inter-Rhône 主办的行业沙龙，Xavier Thuizat（2022 年法国最佳侍酒师）'
                       '主持「Cornas & Saint-Péray 双产区面对时代挑战」大师班。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-decouvertes-en-vallee-du-rhone-evenement-pro--ne-manquez-pas-la-masterclass-%3C%3C-cornas--saint-peray-%3E%3E-de-xavier-thuizat-_18.html',
            'verification': '协会官方期刊页面写明沙龙整体日期「31 mars au 3 avril 2025」，'
                            '并列出 Xavier Thuizat 主持的 Cornas & Saint-Péray 大师班。'
                            '**大师班的单场次日期页面未给出**，登记的 startDate/endDate 是'
                            '沙龙区间、不是大师班当天，勿当作大师班日期引用。'
                            '单一官方一手来源。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-journee-technique-2024',
            'title': 'Cornas & Saint-Péray 葡萄种植技术日',
            'type': 'event', 'subtype': 'technical-day',
            'startDate': '2024-11-15', 'endDate': None,
            'dateNote': '官方写「Le 15 novembre dernier」，同页图片文件名为 '
                        '“Journée technique 2024.png”，正文同时复盘 2024 年防治策略，'
                        '据此定为 2024-11-15（年份来自同年上下文与图片文件名，非正文直写）。',
            'publishedDate': None,
            'lat': 44.9460862, 'lng': 4.8464862,
            'precision': 'Maison des Vins et du Tourisme, Saint-Péray（OSM 实体）',
            'country': '法国', 'region': 'Saint-Péray',
            'summary': '两产区联合技术日：DEPHY 网络 2024 年防治策略复盘、ZNT/DSR 新规、'
                       '农户经验交流。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-retour-sur-la-journee-technique-des-vignerons-de-cornas--saint-peray_17.html',
            'verification': '协会官方期刊页面正文写「Le 15 novembre dernier」，'
                            '**未直写年份**；年份 2024 由同页上下文（2024 年防治策略复盘）'
                            '与页面图片文件名「Journée technique 2024.png」推定，属推定值。'
                            '日期（11-15）与地点（Maison des Vins et du Tourisme, '
                            'Saint-Péray）为页面所载。单一官方一手来源，年份为推定。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-marche-aux-vins-2024',
            'title': '第 68 届 Cornas Marché aux Vins（葡萄酒集市）',
            'type': 'event', 'subtype': 'wine-fair',
            'startDate': '2024-11-29', 'endDate': '2024-12-01',
            'dateNote': '官方写「Les 29, 30 novembre et 1er décembre 2024」。',
            'publishedDate': None,
            'lat': 44.9635210, 'lng': 4.8475450,
            'precision': 'Cornas 村镇代表点（集市在村内场地举行）',
            'country': '法国', 'region': 'Cornas',
            'summary': '产区年度葡萄酒集市，酒农直接对公众开瓶销售。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-68eme-marche-aux-vins-_15.html',
            'verification': '协会官方期刊页面写明「Les 29, 30 novembre et '
                            '1er décembre 2024」，并标明为第 68 届。'
                            '**单一官方一手来源**，未在其他独立来源交叉核对。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-plaza-athenee-2024',
            'title': 'Plaza Athénée 2024 双产区双年品鉴会',
            'type': 'event', 'subtype': 'trade-tasting',
            'startDate': '2024-11-07', 'endDate': None,
            'dateNote': '官方写「Le mardi 07 novembre 2024」。',
            'publishedDate': None,
            'lat': 48.8663815, 'lng': 2.3038926,
            'precision': 'Hôtel Plaza Athénée, Paris 8e（OSM 实体）',
            'country': '法国', 'region': 'Paris',
            'summary': '逾 500 名业内人参加的两产区双年品鉴会。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-plaza-athenee-2024_16.html',
            'verification': '协会官方期刊页面写明「Le mardi 07 novembre 2024」，'
                            '地点 Hôtel Plaza Athénée（Paris 8e）为页面对应场地，'
                            '坐标取自 OSM 实体。**单一官方一手来源**。',
            'checkedDate': DATE,
        },
        {
            'id': 'event-cornas-80ans-2018',
            'title': 'Cornas AOC 八十周年纪念晚会',
            'type': 'event', 'subtype': 'anniversary',
            'startDate': '2018-11-29', 'endDate': None,
            'dateNote': '官方写「Le 29 novembre dernier」并称当日为产区 80 周年；'
                        'AOC 1938 年获批，1938+80=2018，年份由此推定，日报未直写年份。',
            'publishedDate': None,
            'lat': 44.9635210, 'lng': 4.8475450,
            'precision': 'Cornas 村镇代表点',
            'country': '法国', 'region': 'Cornas',
            'summary': '产区协会在 Cornas 举办八十周年纪念晚会。',
            'sourceName': 'AOC Cornas · 官方期刊', 'sourceURL':
                'https://www.aoc-cornas.fr/actualite-80-ans-de-laoc--porter-haut-les-couleurs-de-cornas-_4.html',
            'verification': '协会官方期刊页面写「Le 29 novembre dernier」并称当日为产区 80 周年。'
                            '**年份 2018 为推定值**（AOC 1938 年获批，1938+80=2018），'
                            '页面未直写年份，日报也不得宣称直写了年份。'
                            '单一官方一手来源，年份含推定成分。',
            'checkedDate': DATE,
        },
    ]

    held_back = [
        {
            'title': '北罗讷葡萄园申报联合国教科文组织世界遗产（association '
                     '« De Rhône en vignes » 成立）',
            'reason': '协会成立与申报启动的具体发生日期在官方页面（期刊第 21 篇）未给出，'
                      '页面只说明“至少还需十年工作”。按“缺可核实的发生日期就不登记为事件”的规则，'
                      '本条不写入事件图层。',
            'whereItIsRecorded': 'region-context.json 未收录；如需写入，请先取得协会成立日期'
                                 '（如 RNE/Journal Officiel 公告或协会官网）。',
            'sourceURL': 'https://www.aoc-cornas.fr/actualite-en-route-pour-lunesco-_21.html',
            'checkedDate': DATE,
        },
        {
            'title': 'Cornas & Saint-Péray 产区主席名单（Cyril Courvoisier / Benoît Nodin）',
            'reason': '人物与职务可核实，但就任日期未公开，属人事信息而非事件；'
                      '且所属记录尚未建立（本期未采集协会层面人事）。',
            'whereItIsRecorded': '未入库，仅在此登记降级原因。',
            'sourceURL': 'https://www.aoc-cornas.fr/actualite-nos-deux-presidents_14.html',
            'checkedDate': DATE,
        },
    ]

    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'schemaNote': 'type 仅用站点枚举 news/event/harvest/weather/disaster；'
                      '更细语义放在 subtype（open-days / trade-tasting / masterclass / '
                      'technical-day / wine-fair / anniversary）。',
        'events': events,
        'heldBack': held_back,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'discrepancies.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'items': [
            {
                'field': 'areaHectares',
                'values': [
                    {'value': '约 125 公顷', 'source': 'wein.plus'},
                    {'value': '156 公顷（已种植）', 'source': 'Club Œnologique'},
                    {'value': '约 110 公顷', 'source': 'Wine-Searcher'},
                    {'value': '116 公顷', 'source': 'SoDivin'},
                ],
                'action': '保留 null，不取单一数字；四处口径连同来源记于此。',
            },
            {
                'field': '土壤',
                'values': [
                    {'value': '花岗岩底土 + 石灰岩', 'source': 'wein.plus'},
                    {'value': '花岗岩、白垩、黏土（与石灰岩、片岩相对）', 'source': 'yourwineiq'},
                ],
                'action': '互相矛盾，region-context 中土壤条目留 null，只登记冲突本身。',
            },
            {
                'field': '生产者家数',
                'values': [
                    {'value': '约五十家', 'source': 'SoDivin'},
                    {'value': '71 条（含产区外酒商与合作社）', 'source': 'AOC Cornas 官方名录（本次采集）'},
                ],
                'action': '名录分母以官方名录 71 条为准；不上图/简介时说明其中含非 Cornas 村实体。',
            },
            {
                'field': 'AOC 现行规范核定日期',
                'values': [
                    {'value': '2011-12-07 部令', 'source': 'winewithseth'},
                ],
                'action': '仅单一来源，未回查 Journal Officiel 原文；登记为“来源所载”而非定论。',
            },
            {
                'field': '名录生产者的出产区间',
                'values': [
                    {'value': '名录收录 71 条，其中含产区外酒商与合作社（官方名录）',
                     'source': 'AOC Cornas 官方名录'},
                    {'value': '官网图上实际读到 %d 个不同产区/级别：%s'
                              % (len(appellation_tally),
                                 '、'.join('%s %d 张' % (k, n) for k, n
                                           in sorted(appellation_tally.items(),
                                                     key=lambda x: -x[1]))),
                     'source': '本次逐张读标（agent-visual-review）'},
                ],
                'action': 'Cornas 名录里的生产者普遍同时出产 Saint-Joseph / Crozes-Hermitage / '
                          'Saint-Péray / Hermitage / Condrieu / Côtes du Rhône / IGP 等酒款。'
                          '只有标面明确写 CORNAS 的图登记为 Cornas 酒款图；其余原样保留但 '
                          'appellation 写明真实产区，配图时不得当作 Cornas 酒款使用。',
            },
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    kb_entries = []
    for r in records:
        kb_entries.append({
            'recordId': r['id'], 'kind': r['kind'], 'name': r['name'],
            'reviewStatus': '待审核', 'sourceURL': r['data'].get('sourceURL'),
            'checkedDate': DATE,
        })
    (OUT / '知识库导入清单.json').write_text(json.dumps({
        'date': DATE, 'regionId': 'cornas',
        'reviewRule': '任何条目在知识库中一律先标 待审核，人工核对来源后方可改为 已审核。',
        'entries': kb_entries,
        'eventEntries': [
            {'eventId': e['id'], 'title': e['title'], 'reviewStatus': '待审核',
             'sourceURL': e['sourceURL'], 'startDate': e['startDate']}
            for e in events
        ],
        'heldBackEntries': [
            {'title': h['title'], 'reviewStatus': '待审核', 'note': '未登记为事件，原因见 events-additions.json'} 
            for h in held_back
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    print('wineries:', len([r for r in records if r['kind'] == 'winery']))
    print('with coordinates:', sum(1 for r in records
                                   if r['kind'] == 'winery' and r['data']['lat'] is not None))
    print('with website:', sum(1 for r in records
                               if r['kind'] == 'winery' and r['data'].get('website')))
    print('region images:', len(region_images))
    print('producer images:', producer_images,
          '| producers with images:', producers_with_images,
          '| reviewed:', reviewed_images,
          '| read as Cornas:', len(cornas_appellation))
    print('producer sites unreached (0 images):', len(unreached),
          '| sites with partial URL failures:', len(partial))
    print('events:', len(events), 'heldBack:', len(held_back))
    print('out:', OUT)


if __name__ == '__main__':
    main()
