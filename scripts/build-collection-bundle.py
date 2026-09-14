# coding: utf-8
"""Turn the Condrieu directory + OSM geo results into Site-shaped collection records.

Writes the collection bundle to outputs/collect/YYYY-MM-DD/:
 - catalog-additions.json    winery records matching the Site schema
 - geo-collected.json        full geo result incl. rejections and reasons
 - sources.json              per-record sources
 - events-additions.json     what is happening in the region now
 - HANDOFF.md                handoff note for the explainer conversation
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / DATE
OUT.mkdir(parents=True, exist_ok=True)

directory = json.loads(
    (ROOT / 'outputs' / 'daily' / DATE / 'condrieu-官方名录-90家-2026-09-13.json').read_text())
geo_rows = json.loads((ROOT / 'work' / 'condrieu-geo-collected.json').read_text())
geo_by_name = {r['name']: r for r in geo_rows}

# Matches whose OSM entity carries an extra distinguishing token, or which look
# like a corporate seat rather than the estate/visitor location, are held back
# for human review instead of being written as coordinates.
REVIEW = {
    'M.Chapoutier': 'OSM 命中的是 Tain-l’Hermitage 的 building/yes，可能是公司总部而非葡萄园/到访点',
    'Domaine Gérard': 'OSM 实体名为 “Domaine Goepp Gérard & Fils”，多了 Goepp，需确认是否同一生产者',
    'Domaine Merlin': 'OSM 实体名为 “Domaine Thierry Merlin-Cherrier”，需确认与名录 “Domaine Merlin” 是否同一家',
    'Francois Et Fils': 'OSM 实体名为 “François Edel et Fils”，需确认是否同一生产者',
}

WINERY_POI = {('craft', 'winery'), ('shop', 'wine'), ('shop', 'alcohol')}

records, sources, reviewed, accepted = [], [], [], []
for item in directory['producers']:
    slug = item['directoryURL'].rstrip('/').rsplit('/', 1)[-1]
    wid = 'winery-condrieu-' + slug
    name = item['name']
    geo = geo_by_name.get(name, {})
    data = {
        'name': name,
        'country': '法国',
        'regionId': 'condrieu',
        'aliases': [],
        'lat': None,
        'lng': None,
        'address': None,
        'website': None,
        'originalLanguage': 'fr',
        'localizations': {
            'fr': {
                'name': name,
                'sourceURL': item['directoryURL'],
                'sourceTitle': 'Syndicat des Vignerons de Condrieu · Winegrowers 名录',
                'checkedDate': DATE,
                'status': 'verified',
            }
        },
        'sourceTitle': 'Syndicat des Vignerons de Condrieu · Winegrowers 名录（第 %d 页）' % item['page'],
        'sourceURL': item['directoryURL'],
        'checkedDate': DATE,
        'notes': '产区官方名录收录的生产者条目。名称照录名录原文（法文），未做中文译名。'
                 '官网、地址、坐标与酒款资料按后续采集逐步补齐。',
    }
    sources.append({
        'id': slug,
        'recordId': wid,
        'kind': 'winery',
        'sourceName': 'Syndicat des Vignerons de Condrieu · Winegrowers 名录',
        'sourceURL': item['directoryURL'],
        'sourceLanguage': 'fr',
        'checkedDate': DATE,
        'hit': '官方协会名录',
    })

    if geo.get('status') == 'matched':
        poi = (geo.get('osmClass'), geo.get('osmTypeDetail'))
        if name in REVIEW:
            reviewed.append({
                'name': name, 'recordId': wid, 'reason': REVIEW[name],
                'osmName': geo.get('osmName'), 'osmURL': geo.get('locationSourceURL'),
                'lat': geo.get('lat'), 'lng': geo.get('lng'),
            })
        elif poi in WINERY_POI:
            data['lat'] = geo['lat']
            data['lng'] = geo['lng']
            data['locationSourceURL'] = geo['locationSourceURL']
            data['locationPrecision'] = geo['locationPrecision']
            data['address'] = None
            if geo.get('website'):
                data['website'] = geo['website']
                data['notes'] += ' 官网地址取自 OpenStreetMap 实体的 website 标签，待官网页面二次核对。'
            sources.append({
                'id': slug + '-geo',
                'recordId': wid,
                'kind': 'location',
                'sourceName': 'OpenStreetMap 实体 · %s' % (geo.get('osmName') or ''),
                'sourceURL': geo['locationSourceURL'],
                'sourceLanguage': 'fr',
                'checkedDate': DATE,
                'hit': 'OpenStreetMap Nominatim（%s/%s）' % poi,
            })
            accepted.append(name)
        else:
            reviewed.append({
                'name': name, 'recordId': wid,
                'reason': 'OSM 实体类型 %s/%s 不属于酒庄/酒窖类点位' % poi,
                'osmName': geo.get('osmName'), 'osmURL': geo.get('locationSourceURL'),
                'lat': geo.get('lat'), 'lng': geo.get('lng'),
            })

    records.append({'id': wid, 'kind': 'winery', 'name': name, 'data': data,
                    'version': 1, 'updated': '2026-09-13T11:05:00.000Z',
                    'origin': '每日采集 · 官方名录与开放地图点位'})

(OUT / 'catalog-additions.json').write_text(json.dumps({
    'date': DATE,
    'regionId': 'condrieu',
    'schemaNote': '字段与网站 public/wineries.js 读取的 winery 记录一致；可直接并入 data/catalog-seed.json',
    'counts': {
        'wineries': len(records),
        'withCoordinates': sum(1 for r in records if r['data']['lat'] is not None),
        'withWebsite': sum(1 for r in records if r['data']['website']),
        'heldForReview': len(reviewed),
        'noEvidencedLocation': sum(1 for r in records if r['data']['lat'] is None) - len(reviewed),
    },
    'records': records,
}, ensure_ascii=False, indent=1) + '\n')

(OUT / 'geo-collected.json').write_text(json.dumps({
    'date': DATE,
    'regionId': 'condrieu',
    'method': 'OpenStreetMap Nominatim，按生产者名称逐条查询，1 请求/秒；'
              '行政区划、公司总部、葡萄来源区一律不采纳为酒庄点位',
    'statusCounts': {
        'matched': sum(1 for r in geo_rows if r['status'] == 'matched'),
        'no_evidenced_location': sum(1 for r in geo_rows if r['status'] == 'no_evidenced_location'),
        'query_failed': sum(1 for r in geo_rows if r['status'] == 'query_failed'),
    },
    'acceptedForCoordinates': accepted,
    'heldForReview': reviewed,
    'raw': geo_rows,
}, ensure_ascii=False, indent=1) + '\n')

(OUT / 'sources.json').write_text(json.dumps({
    'date': DATE, 'regionId': 'condrieu', 'sources': sources,
}, ensure_ascii=False, indent=1) + '\n')

events_path = OUT / 'events-additions.json'
if not events_path.exists():
    events_path.write_text(json.dumps({
        'date': DATE, 'regionId': 'condrieu', 'events': [],
        'note': '本期未检索到可核实的 Condrieu / 北罗讷采收、天气灾害或近期活动消息；'
                '不写入占位事件。发生日期与报道日期未取得者不登记。',
    }, ensure_ascii=False, indent=1) + '\n')

print('wineries:', len(records))
print('with coordinates:', sum(1 for r in records if r['data']['lat'] is not None))
print('with website:', sum(1 for r in records if r['data']['website']))
print('held for review:', len(reviewed), [r['name'] for r in reviewed])
print('out dir:', OUT)
