# coding: utf-8
"""Emit the knowledge-base import list (all entries 待审核) for 007期.

Everything here is a *candidate* for the knowledge base. Nothing is marked
已审核 — that decision belongs to the review flow, not to the collector.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'saint-peray'
DATE = '2026-09-17'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

cat = json.loads((OUT / 'catalog-additions.json').read_text(encoding='utf-8'))
geo = json.loads((OUT / 'geo-collected.json').read_text(encoding='utf-8'))
events = json.loads((OUT / 'events-additions.json').read_text(encoding='utf-8'))
merge = json.loads((OUT / 'merge-report.json').read_text(encoding='utf-8'))

acc = {r['slug']: r for r in geo['accepted'] if r['status'] == 'accepted'}

entries = []
for r in cat['records']:
    if r['kind'] == 'region':
        entries.append({
            'entryType': 'region', 'refId': r['id'], 'title': r['name'],
            'status': '待审核',
            'summary': 'Saint-Péray AOC 产区记录（地理／品种／历史仅取协会官网可核对原文，面积与产量留空）。',
            'sourceURL': r['data'].get('sourceURL'), 'checkedDate': DATE,
            'notes': '新增（目录此前无 saint-peray 产区记录）。',
        })
        continue
    g = acc.get(r['name'] and __import__('re').sub(r'[^a-z0-9]+', '',
        __import__('unicodedata').normalize('NFKD', r['name']).encode('ascii', 'ignore').decode()) or '')
    # simpler: look the coordinate up by the bundle id
    is_new = r['id'] in merge['newRecords']
    imgs = r['data'].get('images') or []
    reviewed = [i for i in imgs if i.get('classificationMethod') == 'agent-visual-review']
    sp_labels = [i for i in reviewed if i.get('appellation') == 'SAINT-PÉRAY']
    entries.append({
        'entryType': 'winery', 'refId': r['id'], 'title': r['name'],
        'status': '待审核',
        'summary': ('Saint-Péray 协会名录条目：官网=%s，坐标=%s，图片 %d 张（其中 %d 张人工读标复核，'
                    '%d 张标面确认 Saint-Péray）。' % (
                        '有' if r['data'].get('website') else '名录未提供',
                        ('%.4f,%.4f' % (r['data']['lat'], r['data']['lng'])) if r['data'].get('lat') else '无可靠点位',
                        len(imgs), len(reviewed), len(sp_labels))),
        'sourceURL': r['data'].get('sourceURL'), 'checkedDate': DATE,
        'notes': ('本次新增记录。' if is_new else
                  '该生产者已以其他产区稳定 ID 在库（%s），本期按规范化名称匹配、就地补齐，'
                  'regionId 未改动。' % ', '.join(
                      e['id'] for e in merge['enrichedExistingRecords'] if e['bundleId'] == r['id'])),
    })

event_entries = []
for ev in events['events']:
    event_entries.append({
        'entryType': 'event', 'refId': ev['id'], 'title': ev['title'],
        'status': '待审核', 'startDate': ev['startDate'], 'endDate': ev.get('endDate'),
        'type': ev['type'], 'sourceURL': ev['sourceURL'], 'checkedDate': ev['checkedDate'],
        'notes': '事件条目，字段齐备，等待审核确认后方可展示。',
    })

held = []
for hb in events['heldBack']:
    held.append({
        'entryType': 'heldBack', 'refId': hb['id'], 'title': hb['title'],
        'status': '待审核', 'sourceURL': hb['sourceURL'], 'checkedDate': hb['checkedDate'],
        'notes': hb['reason'],
    })

payload = {
    'date': DATE,
    'regionId': 'saint-peray',
    'phase': '007期 Saint-Péray 采集',
    'generatedAt': NOW,
    'reviewPolicy': '知识库条目一律先标「待审核」；只有审核流程核对通过后才可标「已审核」。',
    'counts': {'entries': len(entries), 'eventEntries': len(event_entries), 'heldBack': len(held)},
    'entries': entries,
    'eventEntries': event_entries,
    'heldBack': held,
}
(OUT / '知识库导入清单.json').write_text(
    json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print('知识库条目:', len(entries), '| 事件:', len(event_entries), '| heldBack:', len(held))
