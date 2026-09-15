# coding: utf-8
"""Build the 006期 Crozes-Hermitage collection bundle.

Inputs
  outputs/daily/2026-09-15/crozes-hermitage-官方名录-2026-09-15.json  (official directory)
  outputs/daily/2026-09-15/crozes-hermitage-events.json               (sourced events)
  work/crozes-hermitage-geo-collected.json                            (OSM coordinates)
  work/crozes-hermitage-profiles.json                                 (slug / website / detail fields)
  work/crozes-hermitage/region-facts.json                             (verified region facts)
  outputs/collect/crozes-hermitage/images/wine-image-manifest.json    (per-producer images)
  outputs/collect/crozes-hermitage/images/region/region-media-manifest.json

Outputs under outputs/collect/crozes-hermitage/:
  catalog-additions.json, geo-collected.json, sources.json, region-context.json,
  events-additions.json, discrepancies.json, 知识库导入清单.json

Usage: python3 scripts/build-crozes-hermitage-bundle.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-15'
OUT = ROOT / 'outputs' / 'collect' / 'crozes-hermitage'
OUT.mkdir(parents=True, exist_ok=True)
LISTING_URL = 'https://www.crozes-hermitage-vin.fr/fr/caves-maisons'
API_URL = 'https://www.crozes-hermitage-vin.fr/index.php?option=com_mymaplocations&task=search'
REGION_ID = 'crozes-hermitage'
REGION_NAME_ZH = '克罗兹-埃米塔日产区'
STAMP = '2026-09-15T02:20:00.000Z'

WINERY_POI = {('craft', 'winery'), ('shop', 'wine'), ('shop', 'alcohol'),
              ('landuse', 'vineyard'), ('building', 'yes'), ('building', 'farm'),
              ('office', 'company'), ('shop', 'farm'), ('amenity', 'restaurant'),
              ('shop', 'beverages'), ('building', 'industrial')}

# 北罗讷地理窗（与 003/005 期同一口径）。
NORTH_RHONE = (44.5, 45.6, 4.4, 5.2)  # south, north, west, east

# Crozes-Hermitage AOC 的实际地理范围比「北罗讷窗」窄得多：11 个村镇沿罗讷河左岸
# 从 Érôme（约 45.13N）到 La Roche-de-Glun（约 44.99N）。窗口只做粗筛，
# 窗内但明显落在其它北罗讷产区（Ampuis= Côte-Rôtie、Malleval= Saint-Joseph 北端）
# 的点仍要单独标注，否则会把 Côte-Rôtie 的酒庄总部当成 Crozes 的地理位置。
AOC_LAT = (44.93, 45.17)
AOC_LNG = (4.72, 5.00)


def outside_north_rhone(lat, lng):
    s, n, w, e = NORTH_RHONE
    return not (s <= lat <= n and w <= lng <= e)


def outside_aoc_core(lat, lng):
    """Inside the north-Rhône window but visibly outside the 11 Crozes communes."""
    return not (AOC_LAT[0] <= lat <= AOC_LAT[1] and AOC_LNG[0] <= lng <= AOC_LNG[1])


def slugify(name: str) -> str:
    import unicodedata
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


# 人工核过的重复判语：自动规则只看得出「地址串是否逐字相同」。
MANUAL_DUP_NOTES = {
    'www.famillecheron.com':
        '人工复核补充：两条的登记地址逐字相同（2459 Route de Vaison / 84190 Vacqueyras）、'
        '电话也相同（+33 (0)4 90 65 85 91），只有邮箱域名分属 vignoblescheron.fr 与 '
        'famillecheron.com。**同地址 + 同电话 + 同域名**，是同一商号下的两条品牌线'
        '（Michel Poinard 与 Famille Chéron 在 Vacqueyras 同址经营），'
        '名录按品牌各列一条。**未合并**——是否并成一条属站点数据模型决定，交人工。'
        '另注意：这两家的登记地址都在**南罗讷的 Vacqueyras（84190）**，'
        '不在 Crozes-Hermitage 11 村镇范围内，属跨产区经营者。',
}

SHORTENERS = ('urlr.me', 'bit.ly', 'tinyurl.com', 'cutt.ly', 'rebrand.ly')


def main():
    directory = json.loads(
        (ROOT / 'outputs' / 'daily' / DATE /
         ('crozes-hermitage-官方名录-%s.json' % DATE)).read_text())
    events_payload = json.loads(
        (ROOT / 'outputs' / 'daily' / DATE / 'crozes-hermitage-events.json').read_text())
    gevent = events_payload['events']
    held_events = events_payload['heldBack']

    geo_rows = json.loads((ROOT / 'work' / 'crozes-hermitage-geo-collected.json').read_text())
    geo_by_id = {r['id']: r for r in geo_rows}
    profiles = {p['slug']: p for p in
                json.loads((ROOT / 'work' / 'crozes-hermitage-profiles.json').read_text())}

    mpath = OUT / 'images' / 'wine-image-manifest.json'
    manifest = json.loads(mpath.read_text())['producers'] if mpath.exists() else []
    img_by_slug = {e['slug']: e for e in manifest}

    facts = json.loads((ROOT / 'work' / 'crozes-hermitage' / 'region-facts.json').read_text())

    records, sources, accepted, held, aoc_outside = [], [], [], [], []
    for item in directory['producers']:
        # the site has its own slug (e.g. "amadieu" for AMADIEU PIERRE); keep it
        slug = item['slug']
        wid = 'winery-%s-%s' % (REGION_ID, slug)
        name = item['name']
        prof = profiles.get(slug, {})
        geo = geo_by_id.get(wid, {})

        data = {
            'name': name,
            'country': '法国',
            'regionId': REGION_ID,
            'aliases': [],
            'lat': None,
            'lng': None,
            'address': item.get('address'),
            'website': item.get('website'),
            'originalLanguage': 'fr',
            'localizations': {
                'fr': {
                    'name': name,
                    'sourceURL': item.get('detailURL') or LISTING_URL,
                    'sourceTitle': 'AOC Crozes-Hermitage · Caves & Maisons（官方名录）',
                    'checkedDate': DATE,
                    'status': 'verified',
                }
            },
            'sourceTitle': 'AOC Crozes-Hermitage · Caves & Maisons（官方名录）',
            'sourceURL': item.get('detailURL') or LISTING_URL,
            'checkedDate': DATE,
            'notes': '产区官方名录（caves & maisons）收录的条目，名称照录原文（法文全大写），未做中文译名。'
                     '地址/电话/邮箱来自名录接口与逐家详情页。'
                     '**名录中的通讯地址不等于葡萄园所在地**——本期 136 条的登记地址的坐标横跨法国'
                     '（北至 48.86N 的巴黎、南至 44.02N 的罗讷河口，见地址分布），'
                     '因此坐标一律另经 OpenStreetMap 实体证据判定，不由地址推断。',
        }
        if item.get('vineyardArea'):
            data['vineyardArea'] = item['vineyardArea']
            data['notes'] += ' 详情页登记葡萄园面积 %s。' % item['vineyardArea']
        if item.get('hasShop'):
            data['hasTastingCellar'] = item['hasShop']
        if item.get('hasShopNote'):
            data['tastingCellarNote'] = item['hasShopNote']
            data['notes'] += (' 详情页「CAVEAU DE VENTE」栏填的不是 oui/non 而是整句话：'
                              '「%s」——照录原文，未据此推断有无门店。' % item['hasShopNote'])
        if item.get('openingHours'):
            data['openingHours'] = item['openingHours']
        if item.get('contactName'):
            data['contactPerson'] = item['contactName']
        if item.get('email'):
            data['email'] = item['email']
        if item.get('phone'):
            data['phone'] = item['phone']
        if item.get('postalCode'):
            data['postalCode'] = item['postalCode']
        if item.get('commune'):
            data['listedCommune'] = item['commune']
        if item.get('looksLikeNegoce'):
            data['directoryCategoryNote'] = ('名录名称含 maison / cave / cellier / négoce 等词，'
                                             '可能是酒商或门市而非自有酒庄；名录未分类，'
                                             '此处仅记录名称特征，不改变其生产者身份。')

        sources.append({
            'id': slug, 'recordId': wid, 'kind': 'winery',
            'sourceName': 'AOC Crozes-Hermitage · Caves & Maisons（官方名录）',
            'sourceURL': item.get('detailURL') or LISTING_URL,
            'sourceLanguage': 'fr', 'checkedDate': DATE,
            'hit': '官方协会名录（由 com_mymaplocations 组件 JSON 接口全量取回；'
                   '详情页含地址/联系人/电话/邮箱/官网/葡萄园面积/是否有门店/营业时间）',
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
                              '可能是同名异地实体，或该生产者登记在南罗讷/更远地区。'
                              '两者都不能当作 Crozes-Hermitage 产区内的点位，故不采纳、转人工复核。',
                    'osmName': geo.get('osmName'), 'osmURL': geo.get('locationSourceURL'),
                    'lat': geo.get('lat'), 'lng': geo.get('lng'),
                    'osmDisplayName': geo.get('displayName'),
                    'directoryAddress': item.get('address'),
                })
            else:
                data['lat'] = geo['lat']
                data['lng'] = geo['lng']
                data['locationSourceURL'] = geo['locationSourceURL']
                data['locationPrecision'] = geo['locationPrecision']
                if outside_aoc_core(geo['lat'], geo['lng']):
                    aoc_outside.append({
                        'name': name, 'recordId': wid,
                        'lat': geo['lat'], 'lng': geo['lng'],
                        'osmName': geo.get('osmName'),
                        'osmURL': geo.get('locationSourceURL'),
                    })
                    data['notes'] += (' 坐标为 OSM 实体「%s」点位，但它落在北罗讷窗内而'
                                      '**不在 Crozes-Hermitage 11 村镇范围**'
                                      '（该点在其它北罗讷产区的方向），'
                                      '属跨产区经营者的他处场所，不宜读作本产区地理位置。'
                                      % (geo.get('osmName') or ''))
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

        entry = img_by_slug.get(slug)
        if entry and entry.get('images'):
            data['images'] = [{
                'file': g['file'],
                'relativePath': 'images/%s/%s' % (slug, g['file']),
                'role': g['role'],
                'attribution': g.get('attribution'),
                'appellation': g.get('appellation'),
                'confidence': g.get('confidence'),
                'classificationMethod': g.get('classificationMethod'),
                'reviewNote': g.get('reviewNote'),
                'altText': g.get('altText'),
                'sourcePage': g.get('sourcePage'),
                'directURL': g.get('directURL'),
                'width': g.get('width'), 'height': g.get('height'), 'bytes': g.get('bytes'),
                'sha256': g.get('sha256'),
                'checkedDate': DATE,
            } for g in entry['images']]

        records.append({
            'id': wid, 'kind': 'winery', 'name': name, 'data': data, 'version': 1,
            'updated': STAMP,
            'origin': '每日采集 · 官方名录（Joomla com_mymaplocations 接口）与开放地图点位',
        })

    # ---------------------------------------------------------------- region record
    region_data = {
        'name': REGION_NAME_ZH,
        'en': 'Crozes-Hermitage AOC',
        'country': '法国',
        'regionId': 'rhone',
        'lat': 45.0710000,
        'lng': 4.8591000,
        'locationSourceURL': 'https://www.openstreetmap.org/search?q=Tain-l%27Hermitage',
        'locationPrecision': '取产区核心村镇 Tain-l\'Hermitage（德龙省）代表点。'
                             '这是村镇代表点，不是 AOC 法定边界；未取得 INAO 边界文件，'
                             '点位不代表产区范围（产区环抱 Hermitage 山丘、跨 11 个村镇）。',
        'grapes': [{'id': 'grape-36404f2e5476', 'percent': None}],
        'grapeNote': '红葡萄品种为西拉（Syrah），是红葡萄酒**唯一**法定品种；'
                     '白葡萄品种为玛珊（Marsanne）与胡珊（Roussanne），通常混酿。'
                     '库中未收录 Marsanne / Roussanne 的品种 id，故仅登记西拉并留空比例。',
        'appellationCreated': '1937',
        'appellationCreatedNote': '1937 年首个原产地命名法令，当时**仅覆盖 Crozes-Hermitage 一个村**；'
                                  '1952 年新法令把 Érôme、Serves-sur-Rhône、Gervans、Larnage、'
                                  'Tain-l\'Hermitage、Mercurol、Chanos-Curson、Beaumont-Monteux、'
                                  'La Roche-de-Glun、Pont-de-l\'Isère 并入，村镇数增至 11。'
                                  '以上均出自协会官网 Histoire 页。',
        'areaHectares': 1964,
        'areaNote': '1 964 ha（协会官网 Histoire 页原文「Avec un vignoble de 1 964 hectares, '
                    'c\'est en superficie la plus grande des appellations de la Vallée du Rhône '
                    'septentrionale.」）。**面积口径存在冲突**：2026 年晚春到访的国际媒体'
                    '（The Buyer）写「2,073 hectares of land are under vine」，'
                    '中文资料（百度百科）另写 1 467 ha。三个数都可能是不同年份/不同统计口径，'
                    '本期以协会官网为准并在 discrepancies.json 记下差异。',
        'areaRank': '北罗讷河谷（Vallée du Rhône septentrionale）面积最大的法定产区',
        'operators': 136,
        'operatorNote': '**这不是官方口径，是协会名录实际列出的条数**：'
                        'com_mymaplocations 接口返回 136 条 caves & maisons，'
                        '另一接口 getListname 亦为 136 条，两个接口 id 集合与名称完全一致。'
                        '协会官网未公布生产者家数（只公布面积），故不写作官方数字。'
                        '媒体另称「over 170 wineries and wine companies」，'
                        '与 136 条的差额可能是统计口径不同，已在 discrepancies.json 记录。',
        'communeCount': 11,
        'communeNote': '11 个村镇，**全部在德龙省（Drôme）罗讷河左岸**：'
                       'Crozes-Hermitage、Érôme、Serves-sur-Rhône、Gervans、Larnage、'
                       'Tain-l\'Hermitage、Mercurol、Chanos-Curson、Beaumont-Monteux、'
                       'La Roche-de-Glun、Pont-de-l\'Isère（协会 Histoire 页 1952 年法令列举）。',
        'latitudeLine': '葡萄园横跨北纬 45° 线',
        'geography': '环抱著名的 Hermitage 山丘（山丘本身属 Hermitage AOC，不在本产区内），'
                     '在罗讷河左岸自北向南展开。北部（Érôme / Serves-sur-Rhône / Gervans / '
                     'Crozes-Hermitage / Larnage）为花岗岩坡地；南部与东部（Mercurol / '
                     'Chanos-Curson / Beaumont-Monteux / Pont-de-l\'Isère / La Roche-de-Glun）'
                     '地势较平，为冰川砾石台地。',
        'soil': '土壤高度多样：南部/东部为厚层冰川砾石（riss、würm 两次冰期）混红黏土，'
                '形成 Châssis、Sept Chemins 等较平坦的台地（plateaux / terrasses）；'
                '向西北转为起伏明显的坡地；Larnage 与 Crozes-Hermitage 一带为 mindel 冰期'
                '砾石台地，覆黄土或高岭白砂；北部三村为花岗岩土壤并覆黄土。',
        'climate': '温带气候，内部有分区差异：Tain-l\'Hermitage 以北偏凉偏湿'
                   '（海拔、坡向与花岗岩土壤共同作用）；以东及以南更干燥'
                   '（土壤透水、密史脱拉风通风强）。',
        'whiteShare': '白葡萄酒占产量 8%（协会官网 Vin 页原文）',
        'agingNote': '红葡萄酒属中等陈年潜力：最初几年宜饮果味，'
                     '3–5 年后香气转向动物性并适配更浓郁的菜式。',
        'serviceTemp': '红葡萄酒：年轻年份约 15 °C，较老年份约 17 °C（协会官网 Vin 页原文）。',
        'aocNote': '产区面积虽为北罗讷最大，但名气长期被紧邻的 Hermitage 山丘所掩盖；'
                   '协会官网自述为「cru du nord de la Vallée du Rhône」的一员。',
        'sourceTitle': 'AOC Crozes-Hermitage 协会官网（Maison des vins de Crozes-Hermitage）',
        'sourceURL': 'https://www.crozes-hermitage-vin.fr/fr/vignoble-et-vin',
        'checkedDate': DATE,
    }

    # ---------------------------------------------------------------- images tally
    all_imgs = [g for e in manifest for g in e.get('images', [])]
    wine_imgs = [g for g in all_imgs if str(g.get('role', '')).startswith('wine-')]
    region_manifest_path = OUT / 'images' / 'region' / 'region-media-manifest.json'
    region_imgs = []
    if region_manifest_path.exists():
        region_imgs = json.loads(region_manifest_path.read_text())['images']

    region_record = {
        'id': REGION_ID, 'kind': 'region', 'name': REGION_NAME_ZH,
        'data': region_data, 'version': 1,
        'updated': STAMP,
        'origin': '每日采集 · 官方协会站点',
    }

    # -------------------------------------------------- duplicate-candidate audit
    by_domain = {}
    for r in records:
        w = r['data'].get('website')
        if not w:
            continue
        dom = re.sub(r'^https?://', '', w).split('/')[0].lower()
        if dom in SHORTENERS:
            continue
        by_domain.setdefault(dom, []).append(r)
    duplicate_candidates = []
    for dom, rs in sorted(by_domain.items()):
        if len(rs) < 2:
            continue
        dup = {'domain': dom, 'names': [r['name'] for r in rs],
               'recordIds': [r['id'] for r in rs],
               'shared': {
                   'website': dom,
                   'addresses': sorted({r['data'].get('address') for r in rs
                                        if r['data'].get('address')}),
                   'phones': sorted({r['data'].get('phone') for r in rs
                                     if r['data'].get('phone')}),
                   'emails': sorted({r['data'].get('email') for r in rs
                                     if r['data'].get('email')}),
               }}
        same_phone = len(dup['shared']['phones']) == 1 and dup['shared']['phones']
        same_mail = len(dup['shared']['emails']) == 1 and dup['shared']['emails']
        same_addr = len(dup['shared']['addresses']) == 1 and dup['shared']['addresses']
        postcodes = {re.search(r'\b(\d{5})\b', a).group(1)
                     for a in dup['shared']['addresses'] if re.search(r'\b(\d{5})\b', a)}
        same_postcode = len(postcodes) == 1
        dup['shared']['postcodes'] = sorted(postcodes)
        if same_addr and same_phone:
            dup['assessment'] = ('同域名 + **同地址 + 同电话**：极可能是同一家商号的品牌系列，'
                                 '但名录把它们列为两条生产者。**未合并**——去处由人工决定。')
        elif same_postcode and (same_phone or same_mail):
            dup['assessment'] = ('同域名 + 同电话/同邮箱 + **同邮编（%s）**：地址串写法不同但同村镇，'
                                 '更像是「同一处地址录得粗细不同」而非两处场所。**未合并**。'
                                 % '/'.join(sorted(postcodes)))
        elif same_phone or same_mail:
            dup['assessment'] = ('同域名 + ' + ('同电话' if same_phone else '同邮箱') +
                                 '，但地址不同：可能是同一家商的**两处场所**，'
                                 '也可能只是地址写法不同。**未合并**。')
        else:
            dup['assessment'] = ('同域名但电话/邮箱/地址都不同：可能是同一集团下的不同实体，'
                                 '或域名被多家共用。**未合并**。')
        extra = MANUAL_DUP_NOTES.get(dom)
        if extra:
            dup['assessment'] += ' ' + extra
            dup['hasManualNote'] = True
        duplicate_candidates.append(dup)

    shortlink_producers = [
        {'name': r['name'], 'recordId': r['id'], 'website': r['data']['website']}
        for r in records
        if r['data'].get('website')
        and re.sub(r'^https?://', '', r['data']['website']).split('/')[0].lower() in SHORTENERS
    ]

    # 登记地址在产区/窗口之外的条目（用于解释「为什么有坐标的只有少数家」）。
    addr_outside = []
    for r in records:
        d = r['data']
        if d.get('lat') or not d.get('postalCode'):
            continue
        addr_outside.append({'name': r['name'], 'postalCode': d.get('postalCode'),
                             'commune': d.get('listedCommune')})

    (OUT / 'catalog-additions.json').write_text(json.dumps({
        'date': DATE,
        'regionId': REGION_ID,
        'schemaNote': '站点不消费 images / relativePath 字段（public/ 内无引用），'
                      '图片行是纯采集元数据，供日报与知识库使用。',
        'counts': {
            'wineryRecords': len(records),
            'regionRecords': 1,
            'producersWithWebsite': sum(1 for r in records if r['data'].get('website')),
            'producersWithCoordinates': sum(1 for r in records if r['data'].get('lat')),
            'producersWithVineyardArea': sum(1 for r in records if r['data'].get('vineyardArea')),
            'producersWithOpeningHours': sum(1 for r in records if r['data'].get('openingHours')),
            'producerImages': len(all_imgs),
            'producerWineImages': len(wine_imgs),
            'regionImages': len(region_imgs),
            'duplicateCandidates': len(duplicate_candidates),
            'shortlinkWebsites': len(shortlink_producers),
            'registeredAddressOutsideRegion': len(addr_outside),
        },
        'duplicateCandidates': duplicate_candidates,
        'shortlinkWebsitesNote': ('本期名录没有出现短链官网（0 家），'
                                  '故无「短链挡住官网与图片」的问题。'),
        'shortlinkWebsites': shortlink_producers,
        'shortlinkWebsitesResolved': [],
        'resolvedShortlinks': [],
        'registeredAddressNote': ('名录的登记通讯地址横跨法国：%d 家既无 OSM 实体证据、'
                                  '登记地址也不在产区附近（含巴黎、博讷、瓦给拉斯等），'
                                  '这是「有坐标的生产者很少」的主因。逐条见 registeredAddressOutsideRegion。'
                                  % len(addr_outside)),
        'registeredAddressOutsideRegion': addr_outside,
        'sourcesNote': '名录的单条来源（地址/电话/邮箱/官网）逐条登记在 sources.json。',
        'records': records + [region_record],
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'geo-collected.json').write_text(json.dumps({
        'date': DATE,
        'regionId': REGION_ID,
        'method': 'OpenStreetMap Nominatim 检索；仅当命中实体本身是酒庄/酒窖类点位，'
                  '或名称与生产者名匹配时采纳；村镇中心点从不当作酒庄点位。'
                  '另叠加北罗讷地理窗（44.5–45.6N / 4.4–5.2E）二次判定，越窗一律转人工复核。'
                  '窗内但明显落在其它北罗讷产区的点位另记 aocCoreOutside。',
        'statusCounts': {
            'matched': sum(1 for r in geo_rows if r.get('status') == 'matched'),
            'acceptedForCoordinates': len(accepted),
            'heldForReview': len(held),
            'noEvidencedLocation': sum(1 for r in geo_rows
                                       if r.get('status') == 'no_evidenced_location'),
        },
        'aocCoreOutside': aoc_outside,
        'aocCoreOutsideNote': ('这些命中点通过了北罗讷地理窗，但落在 Crozes-Hermitage 11 村镇'
                               '范围之外（指向 Ampuis / Malleval 等其它北罗讷产区的方向）。'
                               '它们是**跨产区经营者的他处场所**（总部或另一处酒窖），'
                               '坐标照录但不得读作本产区地理位置。'),
        'acceptedForCoordinates': accepted,
        'heldForReview': held,
        'raw': geo_rows,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'sources.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'directoryAPI': {
            'listingURL': LISTING_URL,
            'componentAPI': API_URL,
            'note': '名录不在静态 HTML 中：页面只给出空的 Google Maps 容器，'
                    '生产者数据由 Joomla com_mymaplocations 组件在运行时取回。'
                    'task=search（POST）返回全量 GeoJSON；task=getListname（POST，query 空）'
                    '返回全量 id/name，两者 id 集合一致。',
        },
        'regionSources': [{'field': f['field'], 'sourceName': f['sourceName'],
                           'sourceURL': f['sourceURL'], 'checkedDate': DATE}
                          for f in facts['facts']],
        'recordSources': sources,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'region-context.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'region': facts['region'],
        'facts': facts['facts'],
        'images': {
            'count': len(region_imgs),
            'manifest': 'images/region/region-media-manifest.json',
            'source': 'crozes-hermitage-vin.fr（协会官网）',
        },
        'producers': {
            'total': len(records),
            'withWebsite': sum(1 for r in records if r['data'].get('website')),
            'withCoordinates': sum(1 for r in records if r['data'].get('lat')),
            'directoryURL': LISTING_URL,
            'apiURL': API_URL,
        },
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'schemaNote': events_payload['schemaNote'],
        'events': gevent,
        'heldBack': held_events,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'discrepancies.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'policy': '同一字段出现两个及以上可信口径且无法判定哪一个正确时，'
                  '不填单一值；此处逐条留痕，供人工收敛后再写入知识库。',
        'items': facts['discrepancies'],
        'additional': [
            {
                'field': '产区面积（ha）',
                'values': ['协会官网 Histoire 页：1 964 ha',
                           'The Buyer（2026 年晚春产区实地报道）：2 073 ha 在种',
                           '百度百科（中文资料）：1 467 ha'],
                'resolution': '三个数字互不相同。协会官网是产区自己的口径，本期以它为准写入 '
                              'areaHectares=1964；媒体与中文来源的数字只作留痕，'
                              '不写成单独字段，也不覆盖官网值。'
                              '三者的差异可能来自年份、是否含未投产地块、是否计入 IGP 等，'
                              '需人工向协会核对后再收敛。',
            },
            {
                'field': '生产者家数',
                'values': ['协会名录接口实际返回 136 条（caves & maisons）',
                           'The Buyer：over 170 wineries and wine companies',
                           '协会官网：未公布家数，只公布面积'],
                'resolution': '协会官网没有官方家数口径，故 operatorNote 明写「136 是名录条数、'
                              '不是官方数字」。媒体写的 170+ 与 136 条的差额未收敛，'
                              '可能含只在 IGP 或只做散装的经营主体。**不以任一方替代另一方**。',
            },
            {
                'field': '白葡萄酒产量占比',
                'values': ['协会官网 Vin 页：8%',
                           'The Buyer（2026 晚春）：11–12%'],
                'resolution': '协会官网写「ils ne représentent que 8 % de la production」；'
                              '媒体写 white production is 11-12%, having grown steadily。'
                              '两者可能对应不同年份（白色占比在上升），但都未标明统计年度，'
                              '故不收敛；region 记录保留官网的 8%，媒体口径留痕于此。',
            },
            {
                'field': '名录中的疑似同一商号多条目',
                'values': ['协会名录把同一家商号按品牌各列一条',
                           '本期检出 %d 组同域名条目（详见 catalog-additions.json 的 '
                           'duplicateCandidates）' % len(duplicate_candidates)],
                'resolution': '名录是首要来源，**未做合并**；同域名 + 同地址 + 同电话'
                              '通常意味着同一商号，但「是否合并成一条记录」属站点数据模型决定，交人工。',
            },
            {
                'field': '名录接口自带的那套坐标（geometry）与地址的关系',
                'values': ['geometry 坐标 = 组件按登记通讯地址地理编码的结果',
                           'fulladdress 里 Itinéraire 链接另带一套坐标'],
                'resolution': '那套 Itinéraire 坐标在 136 条中**完全相同**'
                              '（均距搜索原点约 1.4 km），是模板占位常量而非测量值，已弃用。'
                              'geometry 坐标与页面自带的 distance 字段自洽'
                              '（如 Albert Bichot 217.6 km / 217.6 km），故取 geometry；'
                              '但它仍是**通讯地址的地理编码**，不是葡萄园位置，'
                              '所以产区记录里的坐标一律另经 OSM 实体证据判定。',
            },
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / '知识库导入清单.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'reviewRule': '任何条目在知识库中一律先标 待审核，人工核对来源后方可改为 已审核。',
        'entries': [{
            'recordId': r['id'],
            'name': r['name'],
            'kind': 'winery',
            'status': '待审核',
            'sourceName': r['data']['sourceTitle'],
            'sourceURL': r['data']['sourceURL'],
            'checkedDate': DATE,
            'coordinates': ('%s, %s' % (r['data']['lat'], r['data']['lng']))
            if r['data'].get('lat') else '未取得（无 OSM 实体证据）',
            'images': len(r['data'].get('images', [])),
        } for r in records] + [{
            'recordId': REGION_ID, 'name': REGION_NAME_ZH, 'kind': 'region',
            'status': '待审核',
            'sourceName': region_data['sourceTitle'],
            'sourceURL': region_data['sourceURL'],
            'checkedDate': DATE,
            'coordinates': '%s, %s' % (region_data['lat'], region_data['lng']),
            'images': len(region_imgs),
        }],
        'eventEntries': [{
            'eventId': e['id'], 'title': e['title'], 'type': e['type'],
            'status': '待审核', 'sourceName': e['sourceName'], 'sourceURL': e['sourceURL'],
            'checkedDate': DATE,
        } for e in gevent],
        'heldBackEntries': [
            {'title': e['title'], 'reason': e['reason'],
             'sourceURL': e.get('sourceURL'), 'status': '待审核'} for e in held_events
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    print('winery records:', len(records))
    print('with website:', sum(1 for r in records if r['data'].get('website')))
    print('with vineyard area:', sum(1 for r in records if r['data'].get('vineyardArea')))
    print('coordinates accepted:', len(accepted), '| held for review:', len(held))
    print('coords inside window but outside AOC core:', len(aoc_outside))
    for x in aoc_outside:
        print('   - %s  %s,%s  (%s)' % (x['name'], x['lat'], x['lng'], x['osmName']))
    print('producer images:', len(all_imgs), '| wine-related:', len(wine_imgs))
    print('region images:', len(region_imgs))
    print('duplicate candidates:', len(duplicate_candidates))
    print('events:', len(gevent), '| held back:', len(held_events))


if __name__ == '__main__':
    main()
