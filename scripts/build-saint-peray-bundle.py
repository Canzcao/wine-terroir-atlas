# coding: utf-8
"""Build the 007期 Saint-Péray collection bundle.

Sources used
  * official producer directory  https://saint-peray.net/nos-vignerons/
    (37 profile pages; the association is the ODG-side body behind the AOC site)
  * per-producer images from that site's own #wng-portrait / #wng-packshot modules
    (role is authoritative from the module, NOT from a filename)
  * producers' own websites via collect-wine-images.py
  * coordinates via OSM: unbounded pass + bounded-viewbox second pass

The appellation's own site does NOT publish an area/production figure, so
`areaHectares` stays null and every third-party figure goes to discrepancies.json.

Usage: python3 scripts/build-saint-peray-bundle.py
"""
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-17'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
OUT = ROOT / 'outputs' / 'collect' / 'saint-peray'
WORK = ROOT / 'work' / 'saint-peray'
PROFILE_URL = 'https://saint-peray.net/nos-vignerons/'
APPELLATION_URL = 'https://saint-peray.net/appellation/'
SRC_TITLE = 'AOC Saint-Péray 产区协会官网 · Nos Vignerons（官方名录）'
SRC_TITLE_APP = 'AOC Saint-Péray 产区协会官网 · Appellation'

# northern Rhône acceptance window used for coordinates (same shape as 003期 Cornas)
BBOX = [44.35, 45.80, 4.40, 5.25]

# 22 of the 37 are already in the catalogue under another region's id
KNOWN_CROSS_REGION = {
    'winery-condrieu-cave-blanc-christophe', 'winery-saint-joseph-cave-de-tain',
    'winery-saint-joseph-cave-yves-cuilleron', 'winery-cornas-domaine-alain-voge',
    'winery-cornas-domaine-chaboud-cellier', 'winery-cornas-domaine-clape',
    'winery-cornas-domaine-courbis', 'winery-saint-joseph-domaine-cyril-courvoisier',
    'winery-saint-joseph-domaine-de-la-sarbeche', 'winery-cornas-domaine-de-lorient',
    'winery-saint-joseph-domaine-des-hauts-chassis', 'winery-cornas-domaine-du-coulet',
    'winery-saint-joseph-domaine-du-tunnel', 'winery-saint-joseph-domaine-durand',
    'winery-crozes-hermitage-domaine-laurent-fayolle', 'winery-cornas-domaine-verset-a-et-e',
    'winery-crozes-hermitage-cave-julien-cecillon', 'winery-cornas-ferraton-pere-fils',
    'winery-saint-joseph-j-denuziere', 'winery-condrieu-lemenicier',
    'winery-condrieu-les-vins-de-vienne', 'winery-crozes-hermitage-remy-nodin',
}


def slugify(name):
    t = unicodedata.normalize('NFKD', name or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^A-Za-z0-9]+', '-', t).strip('-').lower()
    return re.sub(r'-{2,}', '-', t)


def load(p, default=None):
    f = Path(p)
    return json.loads(f.read_text(encoding='utf-8')) if f.exists() else default


def in_bbox(lat, lng):
    s, n, w, e = BBOX
    return lat is not None and s <= lat <= n and w <= lng <= e


# ---------------------------------------------------------------- events ----
EVENTS = [
    {
        'id': 'event-saint-peray-maison-des-vins-afterworks-2026',
        'title': '圣佩雷「葡萄酒之家」傍晚酒会：酒农×本地餐饮每周三配对开坛',
        'type': 'event',
        'subtype': 'wine-tourism',
        'startDate': '2026-07-29',
        'endDate': '2026-08-26',
        'dateNote': ('旅游局活动页逐场列出 2026 年 4 个周三场次（7/29、8/5、8/19、8/26，各 18:30-22:00）。'
                     'startDate/endDate 取页面上首末两场的日期，是**系列场次区间**，不是官方写的一段时间；'
                     '截至本期核对（2026-09-17）该页「There are no active availability」，列出场次均已过去，'
                     '不得当作即将举行的活动发布。'),
        'publishedDate': None,
        'lat': None,
        'lng': None,
        'precision': '法国阿尔代什省 Saint-Péray 2 rue de la République 的 Maison des Vins & du Tourisme（单一场地，露天悬铃木下）',
        'country': '法国',
        'region': 'Saint-Péray',
        'summary': ('产区自己的「葡萄酒之家」夏季傍晚酒会：每个周三由罗讷-克吕索尔产区的酒农与本地餐饮从业者结对，'
                    '在悬铃木树荫下做餐酒配对，16 € 一价。报名页显示当前无可订场次，本季场次已结束。'),
        'sourceName': 'Rhône Crussol Tourisme（罗讷-克吕索尔旅游局）活动详情页',
        'sourceURL': 'https://www.rhone-crussol-tourisme.com/en/see-do-calendar/calendar/detail/wines/saint-peray-6425837/afterworks-a-la-maison-des-vins-7296902/',
        'verification': '旅游局官方活动页，逐场写明日期、时间、地点与票价；页面上当前无可订场次（活动已过）。'
                        '单一官方一手来源，未在其他独立来源交叉核对。',
        'checkedDate': DATE,
    },
    {
        'id': 'event-northern-rhone-syrah-unesco-tasting-2026',
        'title': '北罗讷「西拉摇篮」公众品鉴：八大 AOP 品种集体亮相（申遗配套活动）',
        'type': 'event',
        'subtype': 'tasting',
        'startDate': '2026-09-19',
        'endDate': '2026-09-20',
        'dateNote': '旅游局日历页原文「From Saturday 19 to Sunday 20 September 2026 from 15 p.m. to 18 p.m.」。',
        'publishedDate': None,
        'lat': None,
        'lng': None,
        'precision': '法国罗讷省 Tupin-et-Semons（Côte-Rôtie 河段村镇）；该活动面向北罗讷八个 AOP，不在 Saint-Péray 村内',
        'country': '法国',
        'region': '北罗讷（Tupin-et-Semons，Côte-Rôtie 村镇；Saint-Péray 属同一批八个 AOP）',
        'summary': ('北罗讷申请联合国教科文组织世界遗产的配套公众活动：下午由侍酒师学生讲解北罗讷八个 AOP '
                    '（含 Saint-Péray）的西拉、维欧尼耶、玛珊、胡珊等品种特征，免费参加。'),
        'sourceName': 'Ardèche Grand Air Tourist Office（阿尔代什大 airs 旅游局）日历页',
        'sourceURL': 'https://en.ardechegrandair.com/calendar/7935100_northern-rhone-valley--cradle-of-Syrah',
        'verification': '旅游局官方日历页写明日期、时段、地点与免费；活动说明其属于北罗讷申遗流程。'
                        '单一官方一手来源，未在其他独立来源交叉核对。',
        'checkedDate': DATE,
    },
]

HELD_BACK = [
    {
        'id': 'heldback-saint-peray-200-ans-2026',
        'title': '「200 ans d’inspiration」：协会以 200 周年作站点点题，但无官方周年活动日期',
        'reason': ('协会官网全站以「200 ans d’inspiration」为口号，Appellation 页叙事锚在 1826 年 Alexandre Faure '
                   '起泡酒起点。1826+200=2026 是**推算**，协会页面没有给出任何一场官方周年活动的具体日期。'
                   '按采集规格，没有可核实发生日期就不登记为事件。'),
        'recordedIn': 'region-context.json 的 facts（anniversary200Note）与产区记录 data.appellationCreatedNote',
        'sourceURL': APPELLATION_URL,
        'sourceName': SRC_TITLE_APP,
        'checkedDate': DATE,
    },
    {
        'id': 'heldback-saint-peray-association-news-stale',
        'title': '协会官网「Actualités」最新文章停留在 2024 年，本期无新事件可录',
        'reason': ('协会官网文章 sitemap 共 21 篇，最新 lastmod 为 2024-12-09（Plaza Athénée / Journée technique '
                   'des vignerons），没有 2025-2026 年新文。未发现可核实新增即如实说明，不为凑数登记旧闻。'),
        'recordedIn': 'sources.json（文章清单）与 HANDOFF 的「明确没有的东西」',
        'sourceURL': 'https://saint-peray.net/post-sitemap.xml',
        'sourceName': 'AOC Saint-Péray 产区协会官网 · post sitemap',
        'checkedDate': DATE,
    },
    {
        'id': 'heldback-saint-peray-alain-voge-founder-death-2020',
        'title': 'Alain Voge 于 2020 年 9 月逝世（协会名录原文），人事事实非事件',
        'reason': ('协会名录 Domaine Alain Voge 页原文写「Alain Voge, disparu en septembre 2020」。这是已发生的人事事实，'
                   '只有月份、无具体发生日期，且距今已六年，不构成「产区正在发生的事」。'
                   '按规格记入该酒庄记录的 staff 字段，不登记为事件。'),
        'recordedIn': 'winery 记录（Domaine Alain Voge）的 data.staffNote',
        'sourceURL': 'https://saint-peray.net/producer/domaine-alain-voge/',
        'sourceName': SRC_TITLE,
        'checkedDate': DATE,
    },
    {
        'id': 'heldback-saint-peray-northern-rhone-harvest-2026-already-recorded',
        'title': '北罗讷 2026 极早采收已入库（rhone-harvest-20260811），本期不重复登记',
        'reason': ('2026-09-14 期已把北罗讷 8/11 开榨的采收事件并入 data/events.json。协会官网与旅游局页本期'
                   '没有给出 Saint-Péray 单独的采收进度报道，按「按事件主体、日期与地点去重，而非只按 URL 去重」'
                   '的规则不新增条目，避免同一事实出现两条。'),
        'recordedIn': 'data/events.json（既有条目 rhone-harvest-20260811）',
        'sourceURL': 'https://saint-peray.net/les-actualites/',
        'sourceName': SRC_TITLE,
        'checkedDate': DATE,
    },
]


# ------------------------------------------------------------------ main ----
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    prof = load(WORK / 'profiles.json')['producers']
    geo1 = load(ROOT / 'work' / 'saint-peray-geo-raw.json', [])
    geo2 = load(ROOT / 'work' / 'saint-peray-geo-retry.json', [])
    manifest = load(OUT / 'images' / 'wine-image-manifest.json', {'producers': []})
    region_manifest = load(OUT / 'images' / 'region' / 'region-media-manifest.json', {'images': []})
    imgs_by_slug = {e['slug']: {i['file']: i for i in e.get('images') or []}
                    for e in manifest.get('producers', [])}

    # ---- coordinates: accepted / heldForReview ---------------------------
    geo_raw_by_id = {g['id']: g for g in geo1}
    # pass 2 (bounded viewbox) overrides pass 1 where it actually matched:
    # pass 1 ran unbounded and legitimately missed producers that only rank
    # inside a regional window.
    geo_by_name = {}
    for g in geo1 + geo2:
        cur = geo_by_name.get(g['name'])
        if cur is None or (g.get('status') == 'matched' and cur.get('status') != 'matched'):
            geo_by_name[g['name']] = g
    accepted, held = [], []
    for p in prof:
        name = p.get('name') or p['slug']
        slug = slugify(name)
        g = geo_by_name.get(name)
        rec = {'slug': slug, 'name': name, 'profileURL': p.get('profileURL'),
               'commune': p.get('commune'), 'website': p.get('website')}
        if not g:
            rec.update({'status': 'no_evidenced_location', 'lat': None, 'lng': None,
                        'note': '两轮 OSM 检索（无界 + 北罗讷有界 viewbox）均未命中酒庄类实体；坐标留空，不推断。'})
            accepted.append(rec)
            continue
        if g['status'] != 'matched':
            rec.update({'status': 'no_evidenced_location', 'lat': None, 'lng': None,
                        'rowsSeenBounded': g.get('rowsSeenBounded'),
                        'note': 'OSM 有界检索未命中酒庄类 POI；坐标留空。'})
            accepted.append(rec)
            continue
        lat, lng = g['lat'], g['lng']
        if not in_bbox(lat, lng):
            rec.update({'status': 'heldForReview', 'lat': lat, 'lng': lng,
                        'osmName': g.get('osmName'), 'osmClass': g.get('osmClass'),
                        'osmTypeDetail': g.get('osmTypeDetail'),
                        'locationSourceURL': g.get('locationSourceURL'),
                        'rejectReason': '同名异地：OSM 命中实体在北罗讷地理窗（44.35-45.80N / 4.40-5.25E）之外，'
                                        '且实体名与酒庄名相同但主体不同（详见 osmName/displayName），不采纳、不写进站点坐标。'})
            held.append(rec)
            continue
        cls = g.get('osmClass') or ''
        typ = g.get('osmTypeDetail') or ''
        if (cls, typ) == ('office', 'company') and 'colombo' in slug:
            rec.update({'status': 'heldForReview', 'lat': lat, 'lng': lng,
                        'osmName': g.get('osmName'), 'osmClass': cls, 'osmTypeDetail': typ,
                        'locationSourceURL': g.get('locationSourceURL'),
                        'rejectReason': 'OSM 实体为 office/company，extratags 官网指向 colombo-coating.com（涂料企业），'
                                        '与本酒庄无关；同类名异地，不采纳。'})
            held.append(rec)
            continue
        rec.update({'status': 'accepted', 'lat': lat, 'lng': lng,
                    'osmType': g.get('osmType'), 'osmId': g.get('osmId'),
                    'osmClass': cls, 'osmTypeDetail': typ, 'osmName': g.get('osmName'),
                    'displayName': g.get('displayName'),
                    'locationSourceURL': g.get('locationSourceURL'),
                    'locationPrecision': 'OSM 实体“%s”（%s/%s），视为酒庄/酒窖到访点位；非地块边界，未核实产权范围'
                                         % (g.get('osmName'), cls, typ),
                    'searchPass': g.get('searchPass', 'unbounded')})
        accepted.append(rec)

    acc_by_slug = {r['slug']: r for r in accepted}

    # ---- winery records --------------------------------------------------
    records = [{
        'id': 'saint-peray',
        'kind': 'region',
        'name': '圣佩雷产区',
        'data': {
            'name': '圣佩雷产区',
            'en': 'Saint-Péray AOC',
            'country': '法国',
            'regionId': 'rhone',
            'lat': 44.9453,
            'lng': 4.8450,
            'locationSourceURL': 'https://www.openstreetmap.org/search?q=Saint-P%C3%A9ray',
            'locationPrecision': ('取产区核心村镇 Saint-Péray（阿尔代什省）代表点。这是村镇代表点，不是 AOC 法定边界；'
                                  '未取得 INAO 边界文件，点位不代表产区范围。'),
            'grapes': [],
            'grapeNote': ('法定品种只有两个白葡萄品种：玛珊（Marsanne）与胡珊（Roussanne），'
                          '既做静态白也做传统法起泡（Saint-Péray mousseux）。'
                          '品种 id 未在库中收录对应条目，故 grapes 留空、比例一律不填。'),
            'appellationCreated': '1936',
            'appellationCreatedNote': ('协会官网原文「En 1936, il devient l’une des 9 premières Appellation '
                                       'd’Origine Contrôlée (AOC)」——1936 年成为法国最早的一批 AOC 之一。'),
            'areaHectares': None,
            'areaNote': ('产区协会官网未公布葡萄园面积，本期不填。第三方口径互相矛盾：wein.plus 写 60 ha，'
                         'SommSelect 写约 90 ha（220 acres），winewithseth 写约 90 ha；均非官方，'
                         '详见 discrepancies.json，宁空勿猜。'),
            'communeCount': None,
            'communeNote': ('协会官网未逐条列出法定村镇。第三方（wein.plus）写「the communes of Saint-Pérey and '
                            'Toulaud in the Département of Ardèche」，即圣佩雷与图洛两个村镇；属第三方口径，'
                            '故 communeCount 留空，仅在此备注。'),
            'geography': ('北罗讷最南端的法定产区（协会原文「Le plus méridional des Côtes du Rhône septentrionales」），'
                          '位于罗讷河右岸、瓦朗斯（Valence）以西约 5 公里，围绕克吕索尔山（colline de Crussol）的缓坡展开，'
                          '米亚朗河（Mialan）流经其间。'),
            'soil': ('协会官网强调「extraordinaire géodiversité」：石灰岩、黏土-石灰岩与花岗岩沉积并存。'
                     '页面按四个地质年代解释成因——古生代中央高原花岗岩带来硅质、中生代克吕索尔山的侏罗纪石灰岩带来钙质、'
                     '新生代海侵沉积形成黏土-石灰岩、第四纪冰川与风成黄土（loess）覆盖，罗讷河再加冲积物。'),
            'operators': None,
            'operatorNote': ('协会官网名录实际列出 37 家（本期逐页核对），但该站没有说明这是否等于官方生产者总数，'
                             '因此 operators 留空，仅备注 37 为名录实列条数。'),
            'sourceTitle': SRC_TITLE_APP,
            'sourceURL': APPELLATION_URL,
            'checkedDate': DATE,
            'notes': ('本产区记录的地理与历史表述只使用产区协会官网可核对的原文；面积、产量、村镇数、生产者总数'
                      '协会未公布，一律留空。名录中的生产者登记地址横跨北罗讷多个村镇（Cornas、Tain-l\'Hermitage、'
                      'Chavanay、Tournon 等），**不等于都在圣佩雷村内**，见 HANDOFF。'),
            'originalLanguage': 'fr',
            'localizations': {
                'fr': {'name': 'Saint-Péray AOC', 'sourceURL': APPELLATION_URL,
                       'sourceTitle': 'AOC Saint-Péray · Appellation', 'checkedDate': DATE,
                       'status': 'verified'},
            },
        },
        'version': 1,
        'updated': NOW,
        'origin': '每日采集 · 007期（Saint-Péray 官方名录／坐标／官网图片）',
    }]

    for p in prof:
        name = p.get('name') or p['slug']
        slug = slugify(name)
        g = acc_by_slug.get(slug, {})
        images = [dict(v) for v in (imgs_by_slug.get(slug) or {}).values()]
        data = {
            'name': name,
            'country': '法国',
            'regionId': 'saint-peray',
            'aliases': [],
            'lat': g.get('lat'), 'lng': g.get('lng'),
            'address': p.get('address'),
            'website': p.get('website'),
            'locationPrecision': g.get('locationPrecision'),
            'locationSourceURL': g.get('locationSourceURL'),
            'originalLanguage': 'fr',
            'localizations': {
                'fr': {'name': name, 'sourceURL': p.get('profileURL'),
                       'sourceTitle': SRC_TITLE, 'checkedDate': DATE, 'status': 'verified'},
            },
            'sourceTitle': SRC_TITLE,
            'sourceURL': p.get('profileURL'),
            'checkedDate': DATE,
            'notes': ('产区协会官方名录逐页核对的条目，名称照录原文（法文，大小写照录），未做中文译名。'
                      '**名录登记地址横跨北罗讷多个村镇，不等于葡萄园或酒窖在 Saint-Péray 村内**；'
                      '坐标另经 OpenStreetMap 实体证据判定，不由地址推断。'),
            'contactPerson': p.get('contactPerson'),
            'email': p.get('email'),
            'phone': p.get('phone'),
            'postalCode': p.get('postcode'),
            'listedCommune': p.get('commune'),
        }
        if p.get('openingHours'):
            data['hasTastingCellar'] = 'oui'
            data['openingHours'] = p.get('openingHours')
        if p.get('description'):
            data['descriptionFr'] = p['description']
        if p['slug'] == 'domaine-alain-voge':
            data['staff'] = 'Lionel Fraisse（ contactPerson，协会名录页写明；庄主 Alain Voge 于 2020 年 9 月逝世）'
            data['staffNote'] = ('协会名录原文「Riche de son patrimoine viticole et de la notoriété de ses vins, '
                                 'Alain Voge, disparu en septembre 2020 ... Lionel Fraisse ... et les 10 membres de '
                                 'l’équipe du Domaine ...」。这是人事事实记录，不作为事件登记（见 heldBack）。')
        rec = {'id': f'winery-saint-peray-{slug}', 'kind': 'winery', 'name': name,
               'data': data, 'version': 1, 'updated': NOW,
               'origin': '每日采集 · 007期（Saint-Péray 官方名录／坐标／官网图片）'}
        if images:
            data['images'] = images
        records.append(rec)

    n_cross = sum(1 for r in records if r['kind'] == 'winery' and slugify(r['name']) and r['id'] not in KNOWN_CROSS_REGION)
    # duplicateCandidates: producers this bundle would create a *second* record
    # for, because the catalogue already holds them under another region's id.
    cat = load(ROOT / 'data' / 'catalog-seed.json', [])
    def _norm(t):
        t = unicodedata.normalize('NFKD', t or '')
        t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
        return re.sub(r'[^a-z0-9]+', '', t)
    existing_winery_names = {_norm(r.get('name')) for r in cat if r.get('kind') == 'winery'}
    dup_slugs, dup_names = [], []
    for r in records:
        if r['kind'] != 'winery':
            continue
        if _norm(r['name']) in existing_winery_names:
            dup_slugs.append(slugify(r['name']))
            dup_names.append(r['name'])

    counts = {
        'wineryRecords': sum(1 for r in records if r['kind'] == 'winery'),
        'regionRecords': 1,
        'producersWithWebsite': sum(1 for p in prof if p.get('website')),
        'producersWithCoordinates': sum(1 for r in accepted if r['status'] == 'accepted'),
        'coordinatesHeldForReview': len(held),
        'producerImages': sum(len(i['data'].get('images') or []) for i in records if i['kind'] == 'winery'),
        'producerWineImages': sum(1 for i in records if i['kind'] == 'winery'
                                  for im in (i['data'].get('images') or [])
                                  if im.get('role') in ('wine-bottle', 'wine-label', 'wine-photo')),
        'regionImages': len(region_manifest.get('images') or []),
        'events': len(EVENTS),
        'heldBack': len(HELD_BACK),
        'duplicateCandidates': len(dup_names),
    }

    (OUT / 'catalog-additions.json').write_text(json.dumps({
        'date': DATE,
        'regionId': 'saint-peray',
        'schemaNote': '站点不消费 images / relativePath 字段；图片行是纯采集元数据，供日报与知识库使用。',
        'counts': counts,
        'duplicateCandidates': dup_names,
        'duplicateCandidatesNote': ('以下 %d 家已以其他产区的稳定 ID 在库中（condrieu / cornas / saint-joseph / '
                                    'crozes-hermitage），并库时按规范化名称匹配、保留原 ID 就地补齐，不新建重复记录，'
                                    '也不把它们的 regionId 从原产区改成 saint-peray。' % len(dup_names)),
        'registeredAddressNote': ('协会名录的登记地址横跨北罗讷：37 家里仅一部分登记在 Saint-Péray / Cornas，'
                                  '其余在 Tain-l\'Hermitage、Chavanay、Tournon-sur-Rhône、Malleval、Condrieu 等。'
                                  '这是「分母含非本村实体」的名录，不要把 37 读成「圣佩雷村里 37 家」。'),
        'sourcesNote': '名录单条来源（地址/电话/邮箱/官网）逐条登记在 sources.json。',
        'records': records,
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- events ----------------------------------------------------------
    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': DATE,
        'regionId': 'saint-peray',
        'schemaNote': 'type 取自闭集 news / event / harvest / weather / disaster；必填 12 字段齐备；'
                      '发生日期与报道日期分列；无可核实发生日期的进 heldBack。',
        'events': EVENTS,
        'heldBack': HELD_BACK,
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- geo -------------------------------------------------------------
    (OUT / 'geo-collected.json').write_text(json.dumps({
        'date': DATE,
        'regionId': 'saint-peray',
        'method': ('OpenStreetMap/Nominatim 两轮：第一轮无界「名 + France」，第二轮北罗讷有界 viewbox '
                   '(44.35-45.80N / 4.40-5.25E, bounded=1) + 名称变体。采纳需同时满足：OSM 实体名含酒庄专名、'
                   'POI 类别为酒庄/商铺/建筑类、且落在产区地理窗内。'),
        'accepted': [r for r in accepted if r['status'] == 'accepted'],
        'noEvidencedLocation': [r for r in accepted if r['status'] == 'no_evidencedLocation' or r['status'] == 'no_evidenced_location'],
        'heldForReview': held,
        'window': {'bbox': BBOX, 'note': '北罗讷窗；越窗一律不采纳，宁可地图点少也不要钉错。'},
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- region context --------------------------------------------------
    (OUT / 'region-context.json').write_text(json.dumps({
        'date': DATE,
        'regionId': 'saint-peray',
        'region': {'id': 'saint-peray', 'name': '圣佩雷', 'en': 'Saint-Péray AOC', 'country': '法国',
                   'parentRegionId': 'rhone', 'sourceName': SRC_TITLE_APP,
                   'sourceURL': APPELLATION_URL, 'checkedDate': DATE},
        'facts': [
            {'field': 'appellationCreated', 'value': '1936',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': 'En 1936, il devient l’une des 9 premières Appellation d’Origine Contrôlée (AOC)'},
            {'field': 'sparklingOrigin', 'value': '1826（Alexandre Faure 使产区转向起泡酒）',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': 'En 1826, Saint-Péray se distingue : de tranquille il se fait effervescent, grâce à Alexandre Faure'},
            {'field': 'anniversary200Note', 'value': '协会全站口号「200 ans d’inspiration」，无官方周年活动日期',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': '200 ans d’inspiration'},
            {'field': 'grapes', 'value': 'Marsanne + Roussanne（仅此两个白葡萄品种）',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': 'Le Saint-Péray est le fruit de deux cépages, Marsanne et Roussanne.'},
            {'field': 'position', 'value': '北罗讷最南端的法定产区',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': 'Le plus méridional des Côtes du Rhône septentrionales surgit d’un sol de dépôts calcaires, argilo-calcaires et granitiques.'},
            {'field': 'soil', 'value': '石灰岩、黏土-石灰岩与花岗岩并存；克吕索尔山（colline de Crussol）石灰岩带来钙质',
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': 'La montagne de Crussol expose ses calcaires du Jurassique qui contribuent à l’apport en calcium du terroir.'},
            {'field': 'areaHa', 'value': None,
             'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL,
             'quote': '（协会官网未公布面积；第三方口径 60/90 ha 互相矛盾，见 discrepancies.json）'},
            {'field': 'producerDirectorySize', 'value': '37（协会名录实列条数，非官方生产者总数）',
             'sourceName': SRC_TITLE, 'sourceURL': PROFILE_URL, 'quote': '名录页逐页核对 37 个 producer 详情页'},
        ],
        'images': {'count': len(region_manifest.get('images') or []),
                   'manifest': 'images/region/region-media-manifest.json',
                   'source': 'saint-peray.net（产区协会官网）'},
        'producers': {'total': len(prof),
                      'withWebsite': counts['producersWithWebsite'],
                      'withCoordinates': counts['producersWithCoordinates'],
                      'directoryURL': PROFILE_URL,
                      'note': '名录含登记地址在北罗讷其他村镇的生产者，分母非「村里 37 家」。'},
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- discrepancies ---------------------------------------------------
    (OUT / 'discrepancies.json').write_text(json.dumps({
        'date': DATE,
        'regionId': 'saint-peray',
        'items': [
            {'field': 'areaHectares', 'topic': '葡萄园面积',
             'claims': [
                 {'source': 'wein.plus Wine Guide', 'value': '60 ha', 'url': 'https://wineguide.wein.plus/wine-regions/saint-peray-aoc'},
                 {'source': 'SommSelect', 'value': '约 90 ha（~220 acres）', 'url': 'https://sommselect.com/blogs/tasting-notes/rhone-valley-wine-guide-history-regions-and-top-wines'},
                 {'source': 'winewithseth.com', 'value': '约 90 ha', 'url': 'https://www.winewithseth.com/winewiki/saint-peray-aoc'},
                 {'source': 'AOC Saint-Péray 产区协会官网', 'value': '未公布', 'url': APPELLATION_URL},
             ],
             'action': '协会官网未公布，第三方口径不一致 → areaHectares 保持 null，不采用任何一方；'
                       '中文简介里不得出现「最小的 AOC」这类没有来源的排序论断。'},
            {'field': 'producerCount', 'topic': '生产者数量',
             'claims': [
                 {'source': 'winewithseth.com', 'value': '约 35 vignerons', 'url': 'https://www.winewithseth.com/winewiki/saint-peray-aoc'},
                 {'source': 'AOC Saint-Péray 协会名录', 'value': '名录实列 37 个 producer 详情页', 'url': PROFILE_URL},
             ],
             'action': '37 是本期逐页核对的实际条数，但协会未说明它等于官方生产者总数 → operators 留空，'
                       '仅把 37 写进名录说明；「约 35」不采用。'},
            {'field': 'sparklingShare', 'topic': '起泡酒占比',
             'claims': [
                 {'source': 'TasteAtlas', 'value': '约 15% 为起泡（Saint-Péray mousseux）', 'url': 'https://www.tasteatlas.com/best-rated-wines-in-ardeche'},
                 {'source': 'winewithseth.com', 'value': '约 90% 静态 / 10% 起泡', 'url': 'https://www.winewithseth.com/winewiki/saint-peray-aoc'},
                 {'source': 'AOC Saint-Péray 产区协会官网', 'value': '未公布', 'url': APPELLATION_URL},
             ],
             'action': '两个第三方数字（15% vs 10%）以及表述口径不同，协会未公布 → 不采用，产量结构留空。'},
            {'field': 'yield', 'topic': '单产上限',
             'claims': [
                 {'source': 'winewithseth.com', 'value': '静态 45 hl/ha、起泡 52 hl/ha', 'url': 'https://www.winewithseth.com/winewiki/saint-peray-aoc'},
                 {'source': 'AOC Saint-Péray 产区协会官网', 'value': '未公布', 'url': APPELLATION_URL},
             ],
             'action': '法定单产应以 INAO 原始法令为准，本期未取得 → 不采用，留空。'},
            {'field': 'producerWebsite', 'topic': '协会名录里的官网指向',
             'claims': [
                 {'source': 'AOC Saint-Péray 协会名录', 'value': 'Domaine des Hauts Chassis 的官网栏写 https://www.domainecyrilcourvoisier.fr/', 'url': 'https://saint-peray.net/producer/domaine-des-hauts-chassis/'},
                 {'source': '同名录', 'value': 'Domaine Cyril Courvoisier 的官网栏也是 https://www.domainecyrilcourvoisier.fr/', 'url': 'https://saint-peray.net/producer/domaine-cyril-courvoisier/'},
             ],
             'action': '两家不同酒庄指向同一域名，疑似协会数据录入错误或两家同属一主体 → 本期不把该域名当作 '
                       'Hauts Chassis 的官网写进记录（website 留空），留待人工确认后补。'},
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    # ---- sources ---------------------------------------------------------
    src = [{'sourceName': SRC_TITLE, 'sourceURL': PROFILE_URL, 'checkedDate': DATE,
            'hitMethod': '协会官网名录（多页 profile 站，每家一个 /producer/<slug>/ 详情页）',
            'note': '名录 37 条，含地址/电话/邮箱/官网；官网栏 31 家有效、6 家空白。'},
           {'sourceName': SRC_TITLE_APP, 'sourceURL': APPELLATION_URL, 'checkedDate': DATE,
            'hitMethod': '协会官网产区介绍页（地质、品种、历史）',
            'note': '面积、产量、村镇数、生产者总数该页均未公布。'},
           {'sourceName': 'Rhône Crussol Tourisme', 'sourceURL': EVENTS[0]['sourceURL'],
            'checkedDate': DATE, 'hitMethod': '旅游局活动日历', 'note': 'Afterworks à la Maison des Vins 各场次日期。'},
           {'sourceName': 'Ardèche Grand Air Tourist Office', 'sourceURL': EVENTS[1]['sourceURL'],
            'checkedDate': DATE, 'hitMethod': '旅游局活动日历', 'note': '北罗讷申遗配套品鉴活动。'},
           {'sourceName': 'OpenStreetMap / Nominatim', 'sourceURL': 'https://nominatim.openstreetmap.org/',
            'checkedDate': DATE, 'hitMethod': '两轮坐标检索（无界 + 北罗讷有界 viewbox）',
            'note': '采纳 7 家、同名异地/窗外 3 家转人工复核、27 家无实体证据。'}]
    for p in prof:
        src.append({'sourceName': f'{SRC_TITLE} · {p.get("name")}',
                    'sourceURL': p.get('profileURL'), 'checkedDate': DATE,
                    'hitMethod': '酒庄详情页（地址/电话/邮箱/官网/人物照/酒款照）',
                    'note': f"官网={'有' if p.get('website') else '名录未提供'}；"
                            f"portrait={'有' if p.get('hasPortrait') else '无'}、"
                            f"packshot={'有' if p.get('hasPackshot') else '无'}"})
    (OUT / 'sources.json').write_text(json.dumps(src, ensure_ascii=False, indent=1) + '\n')

    print('catalog records:', len(records), '| winery:', counts['wineryRecords'],
          '| cross-region in catalog:', counts['duplicateCandidates'])
    print('geo accepted:', counts['producersWithCoordinates'], '| held:', len(held))
    print('producer images:', counts['producerImages'], '| wine images:', counts['producerWineImages'],
          '| region images:', counts['regionImages'])
    print('events:', len(EVENTS), '| heldBack:', len(HELD_BACK))


if __name__ == '__main__':
    main()
