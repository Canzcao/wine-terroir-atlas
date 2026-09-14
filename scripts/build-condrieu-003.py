# coding: utf-8
"""Build the 2026-09-14 Condrieu collection bundle (003期).

Combines:
  - wine catalogue finds from producers' official sites (work/condrieu-wine-catalogues.json)
  - second-pass OSM coordinates (work/condrieu-geo-retry.json)
  - held-for-review resolutions from the 2026-09-13 geo run

Nothing is inferred: wines only from names read on official pages, coordinates
only from OSM winery-like POIs, everything else stays null.
"""
import json, re, unicodedata, html as htmllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-14'
OUT = ROOT / 'outputs' / 'collect' / DATE
OUT.mkdir(parents=True, exist_ok=True)
NOW = '2026-09-14T09:40:00+08:00'

JUNK = re.compile(
    r'^(aller au contenu|passer au contenu|gerer|gérer|détails|details|effacer|'
    r'en savoir plus|stock épuisé|stock epuise|page load link|catégorie|categorie|'
    r'catégorie .+|categorie .+|'
    r'boutique|accueil|contact|panier|livraison|mentions légales|mentions legales|'
    r'nos vins|les vins|notre cave|notre boutique|la collection|les trésors|'
    r'yves cuilleron|acheter du vin|ce produit|rechercher|menu|réservable|'
    r'nos blanc|nos rouges|mon compte|connexion|s\'inscrire|rejoignez|'
    r'cgv|conditions générales|politique de confidentialité|nous contacter)$', re.I)
YEAR = re.compile(r'\b(19|20)\d{2}\b')
VOLUME = re.compile(r'\b\d+\s?(cl|ml|l)\b\.?', re.I)


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def clean(text):
    text = htmllib.unescape(text or '')
    text = re.sub(r'\s+', ' ', text).strip(' -–|·')
    return text.strip()


def base_name(name):
    """Strip vintage year and bottle volume from a shop listing name."""
    n = clean(name)
    n = VOLUME.sub('', n)
    n = re.sub(r'\s*[-–]\s*(19|20)\d{2}\s*$', '', n)
    n = re.sub(r'\s+(19|20)\d{2}\s*$', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -–')


def year_of(name):
    m = re.search(r'\b(19|20)(\d{2})\b', name)
    return int(m.group(0)) if m else None


def slugify(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:80]


catalogue = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
by_id = {r['id']: r for r in catalogue}
condrieu_wineries = [r for r in catalogue if r['kind'] == 'winery'
                     and r.get('data', {}).get('regionId') == 'condrieu']
by_norm_name = {}
for w in condrieu_wineries:
    for key in {norm(w['name']), norm(w['data'].get('en') or '')} | \
               {norm(a) for a in (w['data'].get('aliases') or [])}:
        if key:
            by_norm_name.setdefault(key, w)

profiles = json.loads((ROOT / 'work' / 'condrieu-profiles.json').read_text())
profile_by_slug = {p['slug']: p for p in profiles}

existing_wines = {(r['data'].get('wineryId'), norm(r['name'])): r for r in catalogue
                  if r['kind'] == 'wine'}

wine_sites = json.loads((ROOT / 'work' / 'condrieu-wine-catalogues.json').read_text())

# ---------------------------------------------------------------- wine records
records, other_appellation, site_check = [], [], []
added_wines = {}
for site in wine_sites['sites']:
    prof = profile_by_slug.get(site['slug'], {})
    producer_name = prof.get('name') or site['producer']
    winery = (by_norm_name.get(norm(producer_name)) or
              by_norm_name.get(norm(site['producer'])))
    entry = {
        'slug': site['slug'], 'producer': producer_name,
        'website': site['website'], 'status': site['status'],
        'note': site.get('note'),
        'wineryId': winery['id'] if winery else None,
        'productsSeen': len(site.get('products') or []),
    }
    site_check.append(entry)
    if site['status'] != 'ok' or not winery:
        continue
    for prod in site['products']:
        name_raw = prod['name']
        if JUNK.match(name_raw.strip()):
            continue
        if len(name_raw) < 4:
            continue
        apps = prod.get('appellations') or []
        base = base_name(name_raw)
        if not base or JUNK.match(base):
            continue
        is_condrieu = any(a == 'Condrieu' for a in apps)
        is_grillet = any(a == 'Château-Grillet' for a in apps)
        if not (is_condrieu or is_grillet):
            if apps:
                other_appellation.append({
                    'wineryId': winery['id'], 'producer': producer_name,
                    'name': base, 'appellations': apps,
                    'confidence': prod['confidence'], 'how': prod['how'],
                    'sourceURL': prod.get('sourceURL') or site['website'],
                })
            continue
        # category-only page hits like "Condrieu" with no cuvée are not a wine
        if norm(base) == 'condrieu' and prod['confidence'] != 'high':
            continue
        if (winery['id'], norm(base)) in existing_wines:
            continue  # already catalogued for this producer
        if (winery['id'], norm(base)) in added_wines:
            continue
        region_id = 'chateau-grillet' if is_grillet and not is_condrieu else 'condrieu'
        wine_id = 'wine-%s-%s' % (winery['id'].replace('winery-condrieu-', '')
                                  .replace('winery-', ''), slugify(base))
        wine_id = re.sub(r'-+', '-', wine_id)
        rec = {
            'id': wine_id, 'kind': 'wine', 'name': base,
            'data': {
                'name': base, 'country': '法国', 'wineryId': winery['id'],
                'regionId': region_id, 'originalLanguage': 'fr',
                'grapes': [],  # 官方页面未逐款标注品种比例，留空不推断
                'sourceTitle': '%s · 官方网站酒款页' % producer_name,
                'sourceURL': prod.get('sourceURL') or site['website'],
                'checkedDate': DATE,
                'notes': '名称直接读自生产者官网（%s，%s）；页面未逐款标注品种比例，'
                         '比例留空。采收/年份信息仅在有明确年份标注时另立 vintage 记录。' % (
                             prod['how'], prod['confidence']),
            },
            'version': 1, 'updated': NOW,
            'origin': '每日一产区 · 官方酒款核对（003期）',
        }
        records.append(rec)
        added_wines[(winery['id'], norm(base))] = rec
        # vintage record when the listing itself shows a year
        yr = year_of(name_raw)
        if yr and not YEAR.search(base):
            vid = 'vintage-%s-%d' % (wine_id.replace('wine-', ''), yr)
            if vid not in by_id:
                records.append({
                    'id': vid, 'kind': 'vintage',
                    'name': '%s %d' % (base, yr),
                    'data': {
                        'name': '%s %d' % (base, yr), 'country': '法国',
                        'wineId': wine_id, 'yearType': 'vintage', 'year': yr,
                        'grapes': [],
                        'sourceTitle': '%s · 官方网站酒款页' % producer_name,
                        'sourceURL': prod.get('sourceURL') or site['website'],
                        'checkedDate': DATE,
                        'notes': '该年份由官网在售列表的名称标注读取（在售 ≠ 已售罄历史年份）；'
                                 '页面未给该年份单独的品种比例，留空。',
                    },
                    'version': 1, 'updated': NOW,
                    'origin': '每日一产区 · 官方酒款核对（003期）',
                })

# ------------------------------------------------------------------ geo merge
retry = json.loads((ROOT / 'work' / 'condrieu-geo-retry.json').read_text())
prev_geo = json.loads((ROOT / 'outputs' / 'collect' / '2026-09-13' / 'geo-collected.json').read_text())
ADOPT = {'winery-condrieu-domaines-jaboulet': False,   # OSM 命中为 Philippe et Vincent Jaboulet，疑似同名近邻不同实体
         }
adopted, held_new = [], []
for row in retry['rows']:
    if row['status'] != 'matched_retry':
        continue
    if row['id'] == 'winery-condrieu-domaines-jaboulet':
        held_new.append({
            'name': row['name'], 'recordId': row['id'],
            'reason': 'OSM 实体为 “Cave Philippe et Vincent Jaboulet”（Tain-l’Hermitage, '
                      'Route de la Négociale），与名录条目 “Domaines Jaboulet”（Paul Jaboulet Aîné 体系）'
                      '疑似不同经营者，宁缺毋滥，坐标不采纳',
            'osmURL': row['locationSourceURL'], 'lat': row['lat'], 'lng': row['lng'],
        })
        continue
    if row['id'] == 'winery-condrieu-a-paret' or row['osmName'] == 'Paret Louze':
        held_new.append({
            'name': row['name'], 'recordId': row['id'],
            'reason': 'OSM 实体名为 “Paret Louze”（office/company，Roussillon, Isère），'
                      '无法确认即名录中的 Domaine A. Paret，坐标暂不采纳，留待官网地址核实',
            'osmURL': row['locationSourceURL'], 'lat': row['lat'], 'lng': row['lng'],
        })
        continue
    adopted.append(row)

enrichments = []
for row in adopted:
    w = by_id.get(row['id'])
    if not w:
        continue
    d = w['data']
    filled = []
    if d.get('lat') is None:
        d['lat'], d['lng'] = row['lat'], row['lng']
        d['locationSourceURL'] = row['locationSourceURL']
        d['locationPrecision'] = row['locationPrecision']
        d['checkedDate'] = DATE
        filled += ['lat', 'lng', 'locationSourceURL', 'locationPrecision']
    if not d.get('website') and row.get('website'):
        d['website'] = row['website']
        filled.append('website')
    if not d.get('address') and row.get('displayName'):
        d['address'] = row['displayName']
        filled.append('address')
    if filled:
        w['version'] = w.get('version', 1) + 1
        w['updated'] = NOW
        enrichments.append({'id': w['id'], 'name': w['name'],
                            'enrichedFields': filled,
                            'locationSourceURL': d.get('locationSourceURL')})

# held-for-review resolutions carried over from 2026-09-13
prev_review_resolutions = [
    {'name': 'Francois Et Fils', 'recordId': 'winery-condrieu-francois-et-fils',
     'decision': 'rejected',
     'reason': 'OSM 实体 “François Edel et Fils”（48.147/7.323）位于阿尔萨斯，判定为同名异地实体；'
               '名录条目为 Côte-Rôtie Ampuis 的 “François et Fils”（官网 coterotie-francoisetfils.com），坐标留空'},
    {'name': 'M.Chapoutier', 'recordId': 'winery-condrieu-m-chapoutier',
     'decision': 'rejected',
     'reason': 'OSM 命中为 Tain-l’Hermitage 的公司总部 building（45.062/4.871）；按规则公司总部不得当作酒庄点位，'
               '其在 Condrieu 的酿造/到访点位无独立有据实体，坐标留空'},
    {'name': 'Domaine Merlin', 'recordId': 'winery-condrieu-domaine-merlin',
     'decision': 'rejected',
     'reason': 'OSM 实体 “Domaine Thierry Merlin-Cherrier”（47.308/2.794）位于卢瓦尔（桑塞尔一带），'
               '判定为同名异地实体，坐标留空'},
    {'name': 'Domaine Gérard', 'recordId': 'winery-condrieu-domaine-gerard',
     'decision': 'rejected',
     'reason': 'OSM 实体 “Domaine Goepp Gérard & Fils”（48.421/7.448）位于阿尔萨斯，'
               '判定为同名异地实体，坐标留空'},
    {'name': 'Domaine Richard', 'recordId': None,
     'decision': 'rejected',
     'reason': 'OSM 命中点位（46.730/5.593）位于汝拉一带，判定为同名异地实体，坐标留空'
               '（2026-09-13 已排除，本期复核维持）'},
]

geo_out = {
    'date': DATE,
    'regionId': 'condrieu',
    'method': '第二轮 Nominatim 检索：北罗讷 bbox（44.9,45.75,4.5,5.1）bounded 视图 + '
              '查询变体（全名/去前缀/加 Condrieu）；沿用第一轮采纳规则（酒庄类 POI + 名称词匹配 + 范围校验）',
    'newlyAdopted': adopted,
    'stillUnmatched': [r for r in retry['rows'] if r['status'] == 'no_evidenced_location'],
    'heldForReview': prev_review_resolutions + held_new,
    'carriedFrom2026_09_13': {
        'acceptedForCoordinates': prev_geo['acceptedForCoordinates'],
        'bbox': prev_geo['regionBBoxCheck']['bbox'],
    },
    'totals': {
        'adoptedTotal': len(prev_geo['acceptedForCoordinates']) + len(adopted),
        'newlyAdopted': len(adopted),
        'producersWithoutEvidencedPoint': len(retry['rows']) - len(
            [r for r in retry['rows'] if r['status'] == 'matched_retry']),
        'heldForReviewOpen': len(held_new),
    },
}

sources = [{
    'date': DATE, 'kind': 'osm',
    'name': 'OpenStreetMap / Nominatim（第二轮 bounded 检索，%d 条）' % len(retry['rows']),
    'url': 'https://nominatim.openstreetmap.org/', 'checkedDate': DATE,
}, {
    'date': DATE, 'kind': 'press',
    'name': 'Rhône Valley Vineyards（Inter Rhône）· 2026 采收新闻稿（2026-08-26）',
    'url': 'https://www.nombase.com/newswire/2026/08/26/2026-harvest-in-the-rhone-valley-vineyards-a-resilient-vineyard-facing-an-intense-growing-season',
    'checkedDate': DATE,
}, {
    'date': DATE, 'kind': 'press',
    'name': 'AP（经 Yahoo News UK）· Extreme heat forces Rhone winemakers to harvest early（2026-08-31）',
    'url': 'https://uk.news.yahoo.com/extreme-heat-forces-rhone-winemakers-102338329.html',
    'checkedDate': DATE,
}, {
    'date': DATE, 'kind': 'event',
    'name': 'Vallée du Rhône Nord · Côte-Rôtie Trail 2026-10-17 赛事页',
    'url': 'https://valleedurhonenord.com/en/events/detail/trail-en-cote-rotie-5883486/',
    'checkedDate': DATE,
}, {
    'date': DATE, 'kind': 'event',
    'name': 'Finishers.com · Trail in Côte-Rôtie 2026（Date confirmed）',
    'url': 'https://www.finishers.com/en/event/RdPzP', 'checkedDate': DATE,
}, {
    'date': DATE, 'kind': 'event',
    'name': 'Pilat Tourisme · Côte-Rôtie Trail（2026-10-17）',
    'url': 'https://www.pilat-tourisme.fr/en/all-the-events/cote-rotie-trail-3272551',
    'checkedDate': DATE,
}]
for site in wine_sites['sites']:
    if site['status'] == 'ok' and site['products']:
        sources.append({
            'date': DATE, 'kind': 'producer-site',
            'name': '%s · 官网酒款页（%d 个产品名）' % (site['producer'], len(site['products'])),
            'url': site['website'], 'checkedDate': DATE,
            'hitMethod': '官网爬取：JSON-LD Product / WooCommerce 标题 / 商品页 h1 / 商品链接锚文本',
        })

catalog_additions = {
    'date': DATE,
    'regionId': 'condrieu',
    'schemaNote': '本期为 003 期续收：官网酒款名（fr 原文）+ 第二轮 OSM 坐标。'
                  '品种比例与未标注年份一律留空；酒款挂生产酒庄既有点位，不单独造坐标。',
    'counts': {
        'wineRecords': sum(1 for r in records if r['kind'] == 'wine'),
        'vintageRecords': sum(1 for r in records if r['kind'] == 'vintage'),
        'wineryEnrichments': len(enrichments),
        'sitesChecked': len(site_check),
        'sitesWithProducts': sum(1 for s in site_check if s['status'] == 'ok' and s['productsSeen']),
        'sitesUnreachable': sum(1 for s in site_check if s['status'] == 'site_unreachable'),
        'sitesNoProductsDetected': sum(1 for s in site_check if s['status'] == 'no_products_detected'),
    },
    'records': records,
    'wineryEnrichments': enrichments,
    'otherAppellationWines': other_appellation,
    'siteCheck': site_check,
}

(OUT / 'catalog-additions.json').write_text(
    json.dumps(catalog_additions, ensure_ascii=False, indent=1) + '\n')
(OUT / 'geo-collected.json').write_text(
    json.dumps(geo_out, ensure_ascii=False, indent=1) + '\n')
(OUT / 'sources.json').write_text(
    json.dumps({'date': DATE, 'regionId': 'condrieu', 'sources': sources},
               ensure_ascii=False, indent=1) + '\n')

# ----------------------------------------------- merge into the live catalogue
merged_wines, merged_vintages = 0, 0
for rec in records:
    if rec['id'] in by_id:
        continue
    catalogue.append(rec)
    by_id[rec['id']] = rec
    if rec['kind'] == 'wine':
        merged_wines += 1
    else:
        merged_vintages += 1
(ROOT / 'data' / 'catalog-seed.json').write_text(
    json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n')

# ----------------------------------------------- merge events into events.json
ev_path = ROOT / 'data' / 'events.json'
events_doc = json.loads(ev_path.read_text())
existing_ev = {e['id'] for e in events_doc['events']}
events_add = json.loads((OUT / 'events-additions.json').read_text())
merged_events = 0
for e in events_add['events']:
    if e['id'] in existing_ev:
        continue
    events_doc['events'].append(e)
    merged_events += 1
events_doc['updatedAt'] = NOW
events_doc['checkedAt'] = events_add['checkedAt']
ev_path.write_text(json.dumps(events_doc, ensure_ascii=False, indent=1) + '\n')

# ------------------------------------------------- editorial plan progression
plan_path = ROOT / 'data' / 'editorial-plan.json'
plan = json.loads(plan_path.read_text())
for q in plan['queue']:
    if q['id'] == 'condrieu':
        q['checkedDate'] = DATE
        q['wineCatalogueChecked'] = (q.get('wineCatalogueChecked') or 2) + len(
            {s['wineryId'] for s in site_check
             if s['status'] == 'ok' and s['wineryId'] and s['productsSeen']
             and s['wineryId'] != 'winery-cave-yves-cuilleron'})
        q['note'] = ('官方名录 18 页 90 条；酒庄记录与坐标已入库。酒款目录核对：官网抓取 65 站，'
                     '%d 站返回产品名（%d 站不可达、%d 站无产品可提取），本期续收 Wine/Vintage 记录 '
                     '%d/%d 条。事件新增 %d 条。' % (
                         sum(1 for s in site_check if s['status'] == 'ok' and s['productsSeen']),
                         sum(1 for s in site_check if s['status'] == 'site_unreachable'),
                         sum(1 for s in site_check if s['status'] == 'no_products_detected'),
                         merged_wines, merged_vintages, merged_events))
plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + '\n')

print('wine records added:', merged_wines)
print('vintage records added:', merged_vintages)
print('winery enrichments:', len(enrichments))
print('other-appellation finds kept as raw:', len(other_appellation))
print('events merged:', merged_events)
print('catalogue size:', len(catalogue))
