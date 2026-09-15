# coding: utf-8
"""Build the 005期 Saint-Joseph collection bundle.

Inputs
  outputs/daily/2026-09-14/saint-joseph-官方名录-2026-09-14.json  (official directory)
  work/saint-joseph-geo-collected.json                            (OSM coordinates)
  work/saint-joseph-profiles.json                                 (slug / website / commune)
  work/saint-joseph/region-facts.json                             (verified region facts)
  outputs/collect/saint-joseph/images/wine-image-manifest.json    (per-producer images)
  outputs/collect/saint-joseph/images/region/region-media-manifest.json

Outputs under outputs/collect/saint-joseph/:
  catalog-additions.json, geo-collected.json, sources.json, region-context.json,
  events-additions.json, discrepancies.json, 知识库导入清单.json

Usage: python3 scripts/build-saint-joseph-bundle.py
"""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-14'
OUT = ROOT / 'outputs' / 'collect' / 'saint-joseph'
OUT.mkdir(parents=True, exist_ok=True)
LISTING_URL = 'https://www.aoc-saint-joseph.fr/producteurs-saint-joseph.html'
REGION_ID = 'saint-joseph'
REGION_NAME_ZH = '圣约瑟夫产区'

WINERY_POI = {('craft', 'winery'), ('shop', 'wine'), ('shop', 'alcohol'),
              ('landuse', 'vineyard'), ('building', 'yes'), ('building', 'farm'),
              ('office', 'company'), ('shop', 'farm'), ('amenity', 'restaurant'),
              ('shop', 'beverages'), ('building', 'industrial')}

# 北罗讷地理窗：Saint-Joseph 及同走廊（Chavanay / Tournon / Tain / Mauves / Guilherand）。
NORTH_RHONE = (44.5, 45.6, 4.4, 5.2)  # south, north, west, east

# 人工核过的重复判语补充：自动规则只能看「地址串是否逐字相同」，
# 看不出「RD 1086 就是 RN 86」这类法国公路改编号，故逐组留人工结论。
MANUAL_DUP_NOTES = {
    'www.domainesmourier.com':
        '人工复核补充：两条地址看似不同，实为同一处——「53 RD 1086 / Chavanay」与'
        '「53, RN 86 - Chanson / Chavanay」是同一门牌：法国国道降级为省道时 '
        'RN 86 在德龙/卢瓦尔段改编号为 RD 1086，Chanson 是 Chavanay 的旧写作。'
        '同镇（Chavanay 42410）+ 同门牌 + 同电话 + 同邮箱 + 同域名，'
        '两组差异只在名录录入写法。**仍未合并**——但这是三组里合并可能性最高的一组，'
        '建议人工优先裁定。',
    'www.famillepierregaillard.com':
        '人工复核补充：这一组是**展开短链后才浮现的**——`Domaine Jeanne Gaillard` 的官网在名录里'
        '是 urlr.me 短链，展开后指向 famillepierregaillard.com 下的子页，'
        '与 `Domaine Pierre Gaillard` 撞在同一域名上，故本期新增此候选。'
        '两条同为 42520 Malleval、同电话 04 74 87 13 10，邮箱不同'
        '（jeanne@gaillard.vin / vinsp.gaillard@wanadoo.fr）。'
        '**同村镇 + 同电话 + 同域名**，是「同一家族的两条品牌线」还是「同一家录了两条」，'
        '名录本身没有说明。**未合并**，建议人工向协会核实。',
}

# 短链域名：名录里出现过的，不能当官网域名参与「同域名疑似同一家」的判断。
SHORTENERS = ('urlr.me', 'bit.ly', 'tinyurl.com', 'cutt.ly', 'rebrand.ly')

# 名录只给短链、由本次跟随重定向展开为真实官网的记录（展开过程见 discrepancies.json）。
# 这里按生产者名称索引，供记录构建时替换 website 字段。
RESOLVED_SHORTLINKS = [
    {'name': 'Domaine Cluzel Vincent', 'shortlink': 'http://urlr.me/F5MKnr',
     'resolvedTo': 'https://www.cave-cluzel.fr/',
     'note': '名录登记的短链指向 cave-cluzel.fr；本环境抓图时 HTTP 已跟随重定向，'
             '故图片其实采到了，但标签需按真实域名更正。'},
    {'name': 'Domaine Jeanne Gaillard', 'shortlink': 'http://urlr.me/xnCQey',
     'resolvedTo': 'https://www.famillepierregaillard.com/domaine-jeanne-gaillard/',
     'note': '短链指向 famillepierregaillard.com 下的域名子页；'
             '与名录中另一家 Gaillard 同族但名录未标注关系。'},
]
SHORTLINK_RESOLUTION = {r['name']: r['resolvedTo'] for r in RESOLVED_SHORTLINKS}


def outside_north_rhone(lat, lng):
    s, n, w, e = NORTH_RHONE
    return not (s <= lat <= n and w <= lng <= e)


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


EVENTS = [
    {
        'id': 'event-saint-joseph-la-belle-etoile-2026',
        'title': 'La Belle Étoile——产区 70 周年「葡萄园中的晚宴」',
        'type': 'event',
        'subtype': 'wine-tourism',
        'startDate': '2026-07-10',
        'endDate': '2026-07-12',
        'dateNote': '官方旅游机构原文写「From 10 to 12 July 2026」「Friday 10th, Saturday 11th '
                    'and Sunday 12th July 2026」，共三个晚上。',
        'publishedDate': '2026-06-15',
        'lat': None,
        'lng': None,
        'precision': '法国阿德什省 Mauves（07）产区坡地，非单一场地',
        'country': '法国',
        'region': 'Saint-Joseph',
        'summary': '为庆祝产区 70 周年，酒农在 Mauves 的葡萄园坡地连办三晚开放晚宴：'
                   '开胃酒田间漫步、葡萄行间长桌晚宴、本地食材配餐与坡地灯光秀。'
                   '每人 80 欧元（含导览漫步、正餐与全部品鉴），需预订。',
        'sourceName': 'Vallée du Rhône Nord（北罗讷河谷官方旅游推广机构）· Blog',
        'sourceURL': 'https://valleedurhonenord.com/en/blog/2026/06/15/The%2070th%20Anniversary'
                     '%20of%20the%20Saint%20Joseph%20Catholic%20School%20%E2%80%93%20Experience'
                     '%20this%20exceptional%20event,%20%E2%80%98La%20Belle%20%C3%89toile%E2%80%99'
                     ',%20in%20July%202026',
        'verification': '北罗讷河谷官方旅游推广机构博客原文写明日期（10–12 July 2026）、'
                        '地点（in Mauves (07)）、价格（€80 per person）与内容（晚宴/漫步/灯光秀），'
                        '并给出订票链接（yp.events）。**该机构是产区所在目的地的官方推广方，'
                        '但活动页未在 AOC 协会自有站点交叉出现**，故交叉核对仅限本来源。',
        'checkedDate': DATE,
    },
    {
        'id': 'event-saint-joseph-nantes-2026',
        'title': '产区首次登陆南特：Saint-Joseph 配餐品鉴日',
        'type': 'event',
        'subtype': 'tasting',
        'startDate': '2026-06-13',
        'endDate': None,
        'dateNote': '原文写「on Saturday, June 13」并标「Saturday, June 13, 2026」。'
                    '次日另有一场仅面向专业人士的品鉴午餐（餐厅 Roza），原文未给该场日期。',
        'publishedDate': None,
        'lat': None,
        'lng': None,
        'precision': '法国南特餐厅 Sepia（1 Quai Turenne, Nantes），单一场地',
        'country': '法国',
        'region': 'Saint-Joseph',
        'summary': '产区历史上首次在南特做推广：以六道式菜单搭配不限量品鉴红白圣约瑟夫，'
                   '并有协会代表现场讲解品种与风土。每人 50 欧元。'
                   '原文称此举属 70 周年系列（继里昂、巴黎之后）。',
        'sourceName': 'Le Bonbon Nantes（本地生活媒体）',
        'sourceURL': 'https://en.lebonbon.fr/nantes/leisure/great-wines-saint-joseph-nantes-feast-tasting-to-your-hearts',
        'verification': '原文写明日期（Saturday, June 13, 2026）、地点（餐厅 Sepia, '
                        '1 Quai Turenne - Nantes）、价格（€50 for a 6-course menu + unlimited '
                        'tasting）与「for the first time in its history」的首次性质。'
                        '**属媒体来源，非协会官方发布**；文中引用了协会官号 @aocsaintjoseph 的帖子，'
                        '但未能取得该帖原始链接，故仅按媒体口径登记。',
        'checkedDate': DATE,
    },
]

HELD_BACK_EVENTS = [
    {
        'title': '产区 70 周年纪念特刊《L\'Illustré #10 — 1956-2026 : 70 ans de passion》出版',
        'reason': '协会官网期刊页把这一期标为「Edition anniversaire ! 1956 - 2026」，'
                  '并写「Pour célébrer les 70 ans de l\'appellation」；'
                  '首页事件页标题也写「événements 2026 et 70 ans de l\'appellation」。'
                  '**但官网没有给出这一期的出版日期**。'
                  '按本项目「缺可核实的发生日期就不登记为事件」的规则（与 003 期一致），'
                  '本条不写入事件图层。'
                  '注意：产区 1956-06-15 获 AOC，2026-06-15 才是第 70 个周年日，'
                  '但那是从已知日期**推算**出来的，不是来源直写，故也不拿它当事件日期。'
                  '70 周年这一主题已由 La Belle Étoile（有明确日期）代表。',
        'whereItIsRecorded': '未写入 events-additions.json；'
                             '该期特刊的存在已记入 region-context.json 的来源表与'
                             '知识库待审核清单（作为产区级事实而非事件）。',
        'sourceURL': 'https://www.aoc-saint-joseph.fr/magazines-aoc-saint-joseph.html',
        'checkedDate': DATE,
    },
    {
        'title': '协会官网事件栏目「Évenements」所列 2026 年活动',
        'reason': '该栏目页（actualites-evenement.aspx）抓取后正文为空——只有页头与页脚，'
                  '没有任何可读的事件条目，判断为内容尚未发布或由脚本另行加载。'
                  '在页面上取不到任何事件文本，故不据它登记事件。',
        'whereItIsRecorded': '未写入 events-additions.json；'
                             '工作留痕见 work/saint-joseph/ 与 region-context.json 的来源表。',
        'sourceURL': 'https://www.aoc-saint-joseph.fr/actualites-evenement.aspx',
        'checkedDate': DATE,
    },
    {
        'title': '「Chaleys 干砌石墙梯田自 2018 年起列入联合国教科文组织」',
        'reason': '该说法出自北罗讷河谷目的地推广机构页面（route-vins-hermitage-saint-joseph.com），'
                  '写着 «listed by UNESCO since 2018»。2018 年被 UNESCO 列入的是**「干砌石墙技艺」'
                  '（Art of dry stone walling, knowledge and techniques，人类非物质文化遗产代表作名录）**，'
                  '属于**技艺**而非本产区的某处地块本身。该页面未区分二者，'
                  '且 AOC 协会自有站点未提及此项。按「口径不清就不写入」处理。',
        'whereItIsRecorded': '未写入 region-context.json 的已核事实；'
                             '已按待核实项放入 discrepancies.json 与知识库待审核清单。',
        'sourceURL': 'https://route-vins-hermitage-saint-joseph.com/en/our-appellations/saint-joseph-appellation',
        'checkedDate': DATE,
    },
]


def main():
    directory = json.loads(
        (ROOT / 'outputs' / 'daily' / DATE / 'saint-joseph-官方名录-2026-09-14.json').read_text())
    geo_rows = json.loads((ROOT / 'work' / 'saint-joseph-geo-collected.json').read_text())
    geo_by_id = {r['id']: r for r in geo_rows}
    profiles = {p['slug']: p for p in
                json.loads((ROOT / 'work' / 'saint-joseph-profiles.json').read_text())}

    mpath = OUT / 'images' / 'wine-image-manifest.json'
    manifest = json.loads(mpath.read_text())['producers'] if mpath.exists() else []
    img_by_slug = {e['slug']: e for e in manifest}

    facts = json.loads((ROOT / 'work' / 'saint-joseph' / 'region-facts.json').read_text())

    records, sources, accepted, held = [], [], [], []
    for item in directory['producers']:
        slug = slugify(item['name'])
        wid = 'winery-saint-joseph-' + slug
        name = item['name']
        geo = geo_by_id.get('saint-joseph-' + slug, {})
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
                    'sourceURL': LISTING_URL,
                    'sourceTitle': 'AOC Saint-Joseph · Liste des producteurs（官方名录）',
                    'checkedDate': DATE,
                    'status': 'verified',
                }
            },
            'sourceTitle': 'AOC Saint-Joseph · Liste des producteurs（官方名录）',
            'sourceURL': LISTING_URL,
            'checkedDate': DATE,
            'notes': '产区官方名录收录的生产者条目，名称照录名录原文（法文），未做中文译名。'
                     '地址/电话/邮箱来自名录；**名录中的通讯地址不等于葡萄园所在地**——'
                     '本期名录的登记地址横跨 8 个省（含沃克吕兹的南罗讷酒商），'
                     '因此坐标一律另经 OpenStreetMap 实体证据判定，不由地址推断。',
        }
        for src, dst in (('contact', 'contactPerson'), ('phone', 'phone'), ('email', 'email'),
                         ('postalCode', 'postalCode'), ('commune', 'listedCommune')):
            if item.get(src):
                data[dst] = item[src]

        # 名录把这两家的官网登记成 urlr.me 短链。名录原文照录，但包产物给出可用的真实地址，
        # 并把原始短链留在 websiteAsListed 里，便于人工回溯。
        listed = data.get('website')
        if listed and re.sub(r'^https?://', '', listed).split('/')[0].lower() in SHORTENERS:
            resolved = SHORTLINK_RESOLUTION.get(name)
            if resolved:
                data['websiteAsListed'] = listed
                data['website'] = resolved
                data['notes'] += (' 名录登记的官网是短链 %s，本期已展开为 %s（跟随重定向取得）。'
                                  % (listed, resolved))

        sources.append({
            'id': slug, 'recordId': wid, 'kind': 'winery',
            'sourceName': 'AOC Saint-Joseph · Liste des producteurs（官方名录）',
            'sourceURL': LISTING_URL, 'sourceLanguage': 'fr', 'checkedDate': DATE,
            'hit': '官方产区协会名录（单页字母序列表，含地址/电话/邮箱/官网）',
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
                              '两者都不能当作 Saint-Joseph 产区内的点位，故不采纳、转人工复核。',
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
            'updated': '2026-09-14T14:55:00.000Z',
            'origin': '每日采集 · 官方名录与开放地图点位',
        })

    # ---------------------------------------------------------------- region record
    region_data = {
        'name': REGION_NAME_ZH,
        'en': 'Saint-Joseph AOC',
        'country': '法国',
        'regionId': 'rhone',
        'lat': 45.0715000,
        'lng': 4.8086000,
        'locationSourceURL': 'https://www.openstreetmap.org/search?q=Mauves+Ard%C3%A8che',
        'locationPrecision': '取名录中最集中的历史核心村镇 Mauves（阿德什省）代表点。'
                             '这是村镇代表点，不是 AOC 法定边界；未取得 INAO 边界文件，'
                             '点位不代表产区范围（产区实际沿河绵延约 60 km）。',
        'grapes': [{'id': 'grape-36404f2e5476', 'percent': None}],
        'grapeNote': '红葡萄品种为西拉（Syrah）；白葡萄品种为玛珊（Marsanne）与胡珊（Roussanne）。'
                     '库中未收录 Marsanne / Roussanne 的品种 id，故仅登记西拉并留空比例。'
                     '红白面积比见 areaRedHa / areaWhiteHa。',
        'appellationCreated': '1956',
        'appellationCreatedNote': '1956-06-15 获原产地命名承认，当时仅覆盖 6 个阿德什省村镇、约 90 公顷；'
                                  '1938-12-24 产区保护协会已在 Tournon-sur-Rhône 副省府注册；'
                                  '1969 年新增 20 个村镇；1994 年起按 INAO 评估修订、2021 年完成。'
                                  '以上均出自协会 2025 年官方新闻稿。',
        'areaHectares': 1375,
        'areaNote': '1 375 ha（协会 2025 年官方新闻稿「MÉMO appellation」，'
                    '来源 Inter Rhône 经济服务部 2023/2024 年度）。'
                    '官网风土页另写「花岗岩覆盖 1400 公顷」为概数；'
                    '3 400 ha 是 1994 年修订后的**划界地块面积**（aire délimitée），'
                    '与种植面积不是同一概念，不可混用。详见 discrepancies.json。',
        'areaRedHa': 1183,
        'areaWhiteHa': 192,
        'areaWhiteNote': '白葡萄 192 ha = 玛珊 131 ha + 胡珊 61 ha（同一份官方新闻稿的身份卡）。'
                         '同一份新闻稿第 7 页叙述文字另写「201 hectares」，两者冲突未收敛，'
                         '故 areaWhiteHa 取身份卡值并在此记录差异。',
        'harvestHectolitres': 50583,
        'harvestNote': '50 583 hl（2025 官方新闻稿「MÉMO appellation」· Inter Rhône 2023/2024）。',
        'operators': 190,
        'operatorNote': '协会官方口径「190 metteurs en marché / 190 opérateurs」；'
                        '协会名录页实际列出 182 条（本期照录 181 条，'
                        '其中「Domaine Alain Graillot」在原页重复出现一次，已去重）。'
                        '差额属未列名或合并主体，不以名录条目数替代官方口径。',
        'redShare': '86%',
        'communeCount': 26,
        'communeNote': '26 个村镇，其中阿德什省 23 个、卢瓦尔省 3 个（协会官网原文）。'
                       '协会未在任一页面逐条列出这 26 个村镇名；'
                       '1956 年的「历史核心」6 村为 Saint-Jean-de-Muzols、Vion、Lemps、'
                       'Tournon、Mauves、Glun（协会新闻稿引产区规范）。'
                       '名单未取得，故不在此处罗列省域归属不明的村镇。',
        'elevationMeters': 350,
        'elevationNote': '协会官网写葡萄园最高约 350 m（「jusqu\'à 350 mètres d\'altitude」）。'
                         '第三方资料另有 150–400 m 或 150–500 m 的说法，未采用。',
        'geography': '罗讷河右岸，沿河绵延约 60 km，北起卢瓦尔省 Chavanay、'
                     '南至阿德什省 Guilherand-Granges；葡萄园位于朝南至东南的陡坡（adret）上。',
        'soil': '以花岗岩为主；高处有黏土—石灰岩飞地，坡脚有较厚黄土（loess）。'
                '北部为软片麻岩与花岗岩，Tournon-sur-Rhône 一带为泥灰岩与贫瘠的酸性复合花岗岩。',
        'climate': '受大陆性与地中海双重影响；沿岸河谷风有利于葡萄园通风与卫生状况。',
        'heroicVineyard': '经 CERVIM（山地葡萄栽培研究与保护中心）认定为「英雄葡萄园」：'
                          '坡度大于 30%、梯田/台地式栽培；全欧洲仅约 5% 的葡萄园符合这些特征。',
        'blendRule': '红葡萄酒按技术规范最多可并调 10% 的两种白葡萄（玛珊、胡珊）；1979 年起允许。',
        'whiteAromas': '玛珊：金合欢、蜜桃、蜂蜜、柑橘；胡珊：杏、忍冬、鸢尾、山楂。'
                       '红（西拉）：黑加仑、桑葚、甜香料、胡椒。',
        'serviceTemp': '白 12–14 °C；红 16–18 °C。陈年潜力 3–10 年（视风土与年份）。',
        'nameHistory': '中世纪称「Vin de Mauves」（摩弗之酒，因阿德什省小村 Mauves 得名）；'
                       '17 世纪中叶前葡萄园按地块与园主命名；'
                       '1668 年出现首份写有 Saint-Joseph 之名的已知文书，'
                       '出自 Tournon 学院（耶稣会士）的葡萄园。',
        'maisonDesVins': '485 Avenue des Lots, 26600 Tain-l\'Hermitage；电话 04 75 07 88 81。',
        'presidents': 'Michel Chapoutier 与 Joël Durand（协会 2025 年新闻稿 ÉDITO 署名）。',
        'sourceTitle': 'AOC Saint-Joseph 协会官网 + 2025 年官方新闻稿（Dossier de presse）',
        'sourceURL': 'https://www.aoc-saint-joseph.fr/',
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
        'id': 'saint-joseph', 'kind': 'region', 'name': REGION_NAME_ZH,
        'data': region_data, 'version': 1,
        'updated': '2026-09-14T14:55:00.000Z',
        'origin': '每日采集 · 官方协会站点与官方新闻稿',
    }

    # -------------------------------------------------- duplicate-candidate audit
    # The directory lists a few houses under two brand names. They are NOT
    # silently merged (the directory is the primary source and two brands may be
    # intentional), but a shared non-shortener domain is a strong signal and is
    # reported so a human can decide.
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
        # 名称录的地址写法常常不同，但邮编相同就意味着同村镇。
        # 这不是「两处场所」的证据，反而是「同一处、录得粗细不同」的强提示。
        postcodes = {re.search(r'\b(\d{5})\b', a).group(1)
                     for a in dup['shared']['addresses'] if re.search(r'\b(\d{5})\b', a)}
        same_postcode = len(postcodes) == 1
        dup['shared']['postcodes'] = sorted(postcodes)
        if same_addr and same_phone:
            dup['assessment'] = ('同域名 + 同地址 + 同电话：极可能是同一家商号的两个品牌系列，'
                                 '但名录把它们列为两条生产者。**未合并**——去处由人工决定。')
        elif same_postcode and (same_phone or same_mail):
            dup['assessment'] = ('同域名 + 同电话/同邮箱 + **同邮编（%s）**：地址串写法不同但同村镇，'
                                 '更像是「同一处地址录得粗细不同」而非两处场所。'
                                 '**未合并**，但这是四组里合并可能性最高的一类，建议人工优先裁定。'
                                 % '/'.join(sorted(postcodes)))
        elif same_phone or same_mail:
            dup['assessment'] = ('同域名 + ' + ('同电话' if same_phone else '同邮箱') +
                                 '，但地址不同：可能是同一家商的**两处场所**'
                                 '（如门店 + 酒庄），也可能只是地址写法不同。名录按条目各列一条。**未合并**。')
        else:
            dup['assessment'] = ('同域名但电话/邮箱/地址都不同：可能是同一集团下的不同实体，'
                                 '或域名被多家共用。**未合并**。')
        extra = MANUAL_DUP_NOTES.get(dom)
        if extra:
            dup['assessment'] += ' ' + extra
            dup['hasManualNote'] = True
        duplicate_candidates.append(dup)

    # 仍以短链结尾的生产者：应为空（本期两家都已展开）。非空即表示有没被展开的短链漏网。
    shortlink_producers = [
        {'name': r['name'], 'recordId': r['id'], 'website': r['data']['website']}
        for r in records
        if r['data'].get('website')
        and re.sub(r'^https?://', '', r['data']['website']).split('/')[0].lower() in SHORTENERS
    ]
    # 已按短链展开、包内给出真实地址的生产者。
    resolved_producers = [
        {'name': r['name'], 'recordId': r['id'],
         'websiteAsListed': r['data']['websiteAsListed'], 'website': r['data']['website']}
        for r in records if r['data'].get('websiteAsListed')
    ]

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
            'producerImages': len(all_imgs),
            'producerWineImages': len(wine_imgs),
            'regionImages': len(region_imgs),
            'duplicateCandidates': len(duplicate_candidates),
            'shortlinkWebsites': len(shortlink_producers),
            'resolvedShortlinkWebsites': len(resolved_producers),
        },
        'duplicateCandidates': duplicate_candidates,
        'shortlinkWebsitesNote': ('名录里 %d 家给的官网是 urlr.me 短链，本期已跟随重定向展开为真实域名'
                                  '（见 resolvedShortlinks 与 shortlinkWebsitesResolved），'
                                  '记录里的 website 字段给的是真实地址，原始短链留在 websiteAsListed。'
                                  '注意：短链并没有挡住图片采集——抓图时的 HTTP 客户端本来就跟随重定向。'
                                  % len(resolved_producers)
                                  if resolved_producers and not shortlink_producers else
                                  '这批生产者名录里给的是短链（urlr.me），真实官网被短链包住，'
                                  '本期未展开短链，故没有抓取它们的官网图片。'),
        'shortlinkWebsites': shortlink_producers,
        'shortlinkWebsitesResolved': resolved_producers,
        'resolvedShortlinks': RESOLVED_SHORTLINKS,
        'sourcesNote': '名录的单条来源（地址/电话/邮箱/官网）逐条登记在 sources.json。',
        'records': records + [region_record],
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'geo-collected.json').write_text(json.dumps({
        'date': DATE,
        'regionId': REGION_ID,
        'method': 'OpenStreetMap Nominatim 检索；仅当命中实体本身是酒庄/酒窖类点位，'
                  '或名称与生产者名匹配时采纳；村镇中心点从不当作酒庄点位。'
                  '另叠加北罗讷地理窗（44.5–45.6N / 4.4–5.2E）二次判定，越窗一律转人工复核。',
        'statusCounts': {
            'matched': sum(1 for r in geo_rows if r.get('status') == 'matched'),
            'acceptedForCoordinates': len(accepted),
            'heldForReview': len(held),
            'noEvidencedLocation': sum(1 for r in geo_rows
                                       if r.get('status') == 'no_evidenced_location'),
        },
        'acceptedForCoordinates': accepted,
        'heldForReview': held,
        'raw': geo_rows,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'sources.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
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
            'source': 'aoc-saint-joseph.fr（协会官网风土 / 品种 / 年份 / 图片库 / 配餐页）',
            'note': '协会官网只提供中小尺寸图（多为 800px 级），没有更大原图；'
                    '展示按原始像素，不做放大。',
        },
        'producers': {
            'total': len(records),
            'withWebsite': sum(1 for r in records if r['data'].get('website')),
            'withCoordinates': sum(1 for r in records if r['data'].get('lat')),
            'directoryURL': LISTING_URL,
        },
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'schemaNote': 'type 取自闭集 news / event / harvest / weather / disaster；'
                      '必填 12 字段齐备（id/title/summary/type/startDate/country/region/'
                      'precision/sourceName/sourceURL/verification/checkedDate）。',
        'events': EVENTS,
        'heldBack': HELD_BACK_EVENTS,
    }, ensure_ascii=False, indent=1) + '\n')

    (OUT / 'discrepancies.json').write_text(json.dumps({
        'date': DATE, 'regionId': REGION_ID,
        'policy': '同一字段出现两个及以上可信口径且无法判定哪一个正确时，'
                  '不填单一值；此处逐条留痕，供人工收敛后再写入知识库。',
        'items': facts['discrepancies'],
        'additional': [
            {
                'field': '名录中的疑似同一商号多条目',
                'values': ['协会名录把同一家商号按品牌/场所各列一条',
                           '本期检出 %d 组同域名条目（详见 catalog-additions.json 的 '
                           'duplicateCandidates）' % len(duplicate_candidates)],
                'resolution': '名录是首要来源，**未做合并**；同域名 + 同电话通常意味着同一商号，'
                              '但「是否合并成一条记录」属站点数据模型决定，交人工。',
            },
            {
                'field': 'Chaleys 干砌石墙梯田与联合国教科文组织',
                'values': ['北罗讷目的地推广机构页面写 chaleys「listed by UNESCO since 2018」',
                           '协会自有站点未提及 UNESCO，只提 CERVIM 的「英雄葡萄园」认定'],
                'resolution': '2018 年被 UNESCO 列入的是「干砌石墙技艺」本身'
                              '（人类非物质文化遗产代表作名录），属**技艺**而非本产区地块；'
                              '推广页面的表述容易读成「本产区地块是世界遗产」。'
                              '按口径不清处理，不写入已核事实，转知识库待审核。',
            },
            {
                'field': '名录把两家生产者的官网登记为短链（urlr.me）',
                'values': ['Domaine Cluzel Vincent → http://urlr.me/F5MKnr',
                           'Domaine Jeanne Gaillard → http://urlr.me/xnCQey'],
                'resolution': '本期逐条跟随重定向展开为真实官网：'
                              'Cluzel → https://www.cave-cluzel.fr/ ；'
                              'Jeanne Gaillard → https://www.famillepierregaillard.com/domaine-jeanne-gaillard/ '
                              '。profiles 的 website 字段已改回真实地址，'
                              'catalog-additions.json 的 resolvedShortlinks 留有对照表。'
                              '注意：抓图时 HTTP 客户端本已跟随重定向，'
                              '所以短链并没有挡住图片采集，只是来源标签一度写作 urlr.me。',
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
            'recordId': 'saint-joseph', 'name': REGION_NAME_ZH, 'kind': 'region',
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
        } for e in EVENTS],
        'heldBackEntries': [
            {'title': e['title'], 'reason': e['reason'],
             'sourceURL': e.get('sourceURL'), 'status': '待审核'} for e in HELD_BACK_EVENTS
        ],
    }, ensure_ascii=False, indent=1) + '\n')

    print('winery records:', len(records))
    print('with website:', sum(1 for r in records if r['data'].get('website')))
    print('coordinates accepted:', len(accepted), '| held for review:', len(held))
    print('producer images:', len(all_imgs), '| wine-related:', len(wine_imgs))
    print('region images:', len(region_imgs))
    print('events:', len(EVENTS), '| held back:', len(HELD_BACK_EVENTS))


if __name__ == '__main__':
    main()
