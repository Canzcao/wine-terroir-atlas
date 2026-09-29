# coding: utf-8
"""Merge the 001期 Château-Grillet bundle into the catalogue, then finalise it.

Merge rule (re-collection, not first collection):
 - a record whose id already exists keeps its stable id and is ENRICHED in place
   (version +1); no duplicate is created;
 - a field the new bundle leaves empty never overwrites an existing value;
 - a field where both sides carry text and they differ is overwritten by the new
   (newer, sourced) value, and the superseded text is kept under notesHistory so
   nothing is silently dropped;
 - `localizations` is merged per language, not replaced wholesale;
 - `images` is unioned by file name.

Then writes merge-report.json, 知识库导入清单.json, the ZIP bundle, and copies
the whole bundle to the content-studio task.

After editing HANDOFF.md, re-run scripts/repack-grillet-bundle.py to regenerate the
image index and the archive without touching the catalogue again.
"""
import json, os, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / 'chateau-grillet'
NOW = '2026-09-13T15:30:00.000Z'
STUDIO = Path(os.environ.get('CONTENT_STUDIO', Path(__file__).resolve().parent.parent.parent / 'wine-content-studio')) \
    / 'outputs' / 'collect' / DATE

EMPTY = (None, '', [], {})

additions = json.loads((OUT / 'catalog-additions.json').read_text())
catalogue = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
by_id = {r['id']: r for r in catalogue}
pre_ids = set(by_id)


def archive(data, field, superseded):
    """Keep a superseded field value under notesHistory instead of dropping it."""
    if not superseded:
        return
    hist = data.setdefault('notesHistory', [])
    entry = {'field': field, 'supersededValue': superseded,
             'supersededAt': NOW, 'reason': '001期重采，以有来源的新值替换；原值保留备查。'}
    if entry not in hist:
        hist.append(entry)


def merge_localizations(data, new_locs):
    """Per-language, per-field merge so an existing en/fr page is never lost."""
    changes = []
    locs = data.setdefault('localizations', {})
    for lang, block in (new_locs or {}).items():
        cur = locs.setdefault(lang, {})
        for field, value in block.items():
            if value in EMPTY:
                continue
            if cur.get(field) in EMPTY:
                cur[field] = value
                changes.append('%s.%s' % (lang, field))
            elif cur.get(field) != value:
                archive(cur, '%s.%s' % (lang, field), cur[field])
                cur[field] = value
                changes.append('%s.%s(覆盖)' % (lang, field))
    return changes


merged_existing, merged_new = [], []
for record in additions['records']:
    existing = by_id.get(record['id'])
    if existing is None:
        record['updated'] = NOW
        catalogue.append(record)
        by_id[record['id']] = record
        merged_new.append(record['id'])
        continue

    data = existing['data']
    added, overwritten, images_added = [], [], []

    for field, value in record['data'].items():
        if field == 'localizations':
            continue
        if field == 'images':
            have = {i.get('file') for i in (data.get('images') or [])}
            for img in (value or []):
                if img.get('file') not in have:
                    data.setdefault('images', []).append(img)
                    images_added.append(img.get('file'))
            continue
        if value in EMPTY:
            continue
        cur = data.get(field)
        if cur in EMPTY:
            data[field] = value
            added.append(field)
        elif cur != value:
            archive(data, field, cur)
            data[field] = value
            overwritten.append(field)

    loc_changes = merge_localizations(data, record['data'].get('localizations'))

    # keep the new record's summary fields authoritative for this re-collection
    for field in ('sourceTitle', 'sourceURL', 'checkedDate'):
        if record['data'].get(field):
            data[field] = record['data'][field]

    existing['version'] = existing.get('version', 1) + (1 if (added or overwritten
                                                            or loc_changes or images_added) else 0)
    existing['updated'] = NOW
    existing['origin'] = '每日采集 · 001期重采（坐标／图片／语种补齐）'
    existing['name'] = record['name']

    merged_existing.append({
        'id': existing['id'],
        'kind': existing['kind'],
        'name': record['name'],
        'keptStableId': True,
        'newVersion': existing['version'],
        'fieldsFilled': sorted(added),
        'fieldsOverwritten': sorted(overwritten),
        'localizationFields': sorted(loc_changes),
        'imagesAttached': images_added,
    })

(ROOT / 'data' / 'catalog-seed.json').write_text(
    json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n')

winery_imgs = sum(len(r['data'].get('images') or []) for r in catalogue
                  if r['id'] == 'winery-chateau-grillet')
wine_imgs = sum(len(r['data'].get('images') or []) for r in catalogue
                if r['kind'] in ('wine', 'vintage') and 'grillet' in r['id'])
distinct = {i.get('sha256') or i.get('file')
            for r in catalogue if 'grillet' in r['id']
            for i in (r['data'].get('images') or [])}

summary = {
    'date': DATE,
    'phase': '001期重采（Château-Grillet）',
    'newRecords': [r['id'] for r in additions['records'] if r['id'] not in pre_ids],
    'enrichedExistingRecords': merged_existing,
    'catalogueTotal': len(catalogue),
    'imageCounts': {'wineryAttachments': winery_imgs, 'wineAndVintageAttachments': wine_imgs,
                    'attachmentTotal': winery_imgs + wine_imgs, 'distinctImages': len(distinct)},
    'note': '旧记录 lat/lng 为空、images 为 0；本期在原 stable id 上补齐，未新建重复记录。'
            '被覆盖的旧文本已移入各记录的 notesHistory，可回溯。'
            '同一张图可能同时挂在酒款与其年份上（年份沿用酒款图），故 attachmentTotal > distinctImages。',
}
(OUT / 'merge-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')

# ---- events layer: idempotent append ---------------------------------------
events_add = json.loads((OUT / 'events-additions.json').read_text())
events_path = ROOT / 'data' / 'events.json'
store = json.loads(events_path.read_text())
have = {e['id'] for e in store['events']}
added_events, skipped_events = [], []
for ev in events_add['events']:
    if ev['id'] in have:
        skipped_events.append(ev['id'])
        continue
    store['events'].append(ev)
    added_events.append(ev['id'])
store['updatedAt'] = NOW
store['checkedAt'] = NOW
events_path.write_text(json.dumps(store, ensure_ascii=False, indent=1) + '\n')
summary['eventsAdded'] = added_events
summary['eventsAlreadyPresent'] = skipped_events
summary['eventsTotal'] = len(store['events'])
(OUT / 'merge-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')

# Knowledge-base import list, review-gated. Derived from the bundle itself (not from
# the merge deltas) so the list is identical whether or not this script has run before.
kb_entries = []
for record in additions['records']:
    change = next((r for r in merged_existing if r['id'] == record['id']), None)
    is_new = record['id'] in merged_new
    kb_entries.append({
        'catalogueId': record['id'],
        'kind': record['kind'],
        'name': record['name'],
        'reviewStatus': '待审核',
        'reviewNote': ('001期重采新增记录。' if is_new else '001期重采更新（稳定 ID 保留）。')
                      + '需知识库审核流程核对后方可标为已审核。',
        'changedFields': (change['fieldsFilled'] + change['fieldsOverwritten']
                          + change['localizationFields']) if change else [],
    })

kb = {
    'generatedFor': '知识库导入',
    'date': DATE,
    'regionId': 'chateau-grillet',
    'phase': '001期重采',
    'policy': '所有条目初始为“待审核”；审核通过后才可标“已审核”。本清单本身不构成审核结论。',
    'entries': kb_entries,
    'eventEntries': [{
        'eventId': ev['id'],
        'title': ev['title'],
        'reviewStatus': '待审核',
        'reviewNote': '001期重采新增事件。报道日期 %s，需审核后方可标为已审核。' % ev.get('publishedDate'),
    } for ev in events_add['events']],
}
(OUT / '知识库导入清单.json').write_text(json.dumps(kb, ensure_ascii=False, indent=1) + '\n')

# ---- image provenance / takedown index --------------------------------------
manifest = json.loads((OUT / 'images' / 'wine-image-manifest.json').read_text())
lines = [
    '# 001期 格里叶堡 图片溯源与下架索引',
    '',
    '策略：官网公开图片可采集使用，站点将标注“均为合作上传，如侵权可联系删除”。',
    '收到下架请求时按本表定位文件并删除（本庄园图片集中在 `winery-chateau-grillet/`，可整目录下架）。',
    '',
    '共 %d 张，全部经逐张视觉复核（classificationMethod = agent-visual-review）。' % len(manifest['producers'][0]['images']),
    '',
    '| 文件 | 角色 | 归属 | 产区（读自画面） | 尺寸 | 来源页 | 直链 | 抓取日 | SHA-256（前16位）|',
    '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
]
for img in manifest['producers'][0]['images']:
    lines.append('| %s | %s | %s | %s | %dx%d | %s | %s | %s | %s |' % (
        img['relativePath'], img['role'], img['attribution'], img.get('appellation') or '—',
        img['width'], img['height'], img['sourcePage'], img['directURL'],
        img['retrievedAt'], img['sha256'][:16]))
lines += [
    '',
    '## 视觉复核说明',
    '',
]
for note in manifest.get('visualReviewNotes') or []:
    lines.append('- %s' % note)
lines += [
    '',
    '复核要点：文件名不作判据——庄园官网把酒款图命名为 `Grillet_01-1.jpg`、`Grillet_05.jpg`，',
    '无任何酒款关键词，全部靠看图定类。`04-Grillet_01-1.jpg` 实为 INAO 法定产区地图，',
    '`08-Grillet_05.jpg` 的酒标上读得出 “CONDRIEU / La Carthery / 2021”。',
    '',
]
(OUT / 'images' / '图片溯源与下架索引.md').write_text('\n'.join(lines))

# ---- ZIP bundle -------------------------------------------------------------
members = ['catalog-additions.json', 'events-additions.json', 'geo-collected.json',
           'sources.json', 'discrepancies.json', 'merge-report.json',
           '知识库导入清单.json', 'HANDOFF.md']
bundle = OUT / ('001期-格里叶堡-采集包-' + DATE + '.zip')
with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in members:
        path = OUT / name
        if path.exists():
            z.write(path, name)
    # images + provenance index travel inside the same package
    img_root = OUT / 'images'
    for path in sorted(img_root.rglob('*')):
        if path.is_file() and path.name != '.DS_Store':
            z.write(path, str(path.relative_to(OUT)))
    z.writestr('README-包内说明.txt',
               '001期 格里叶堡产区（Château-Grillet AOC）采集包　%s\n'
               '内容：1 条产区记录 + 1 条酒庄记录 + 3 条酒款记录 + 2 条年份记录 + 2 条事件，'
               '以及 26 张逐张视觉复核过的图片（人物 / 庄园 / 酒款 / 酒标 / INAO 地图）。\n'
               '坐标：45.4501025, 4.7519914（OSM way/337680164，附带庄园官网作为 website 标签）。\n'
               '图片权限：来源酒庄官网公开图片；未标注许可。按站点方 2026-09-13 决定可下载使用，'
               '站点内容标注“均为合作上传，如侵权可联系删除”。\n'
               '分歧未定项见 discrepancies.json（面积 / 梯田级数 / AOC 月日 / 藤龄 / 年产量 / 副牌名）。\n'
               '用途：作为 terroir-atlas 站点的数据来源；科普内容转化在“葡萄酒引流图文”任务独立进行。\n' % DATE)

print(json.dumps(summary, ensure_ascii=False, indent=1))
print('bundle:', bundle, bundle.stat().st_size)

# ---- hand the bundle to the content-studio task -----------------------------
STUDIO.mkdir(parents=True, exist_ok=True)
dest = STUDIO / bundle.name
shutil.copy2(bundle, dest)
for name in members:
    src = OUT / name
    if src.exists():
        shutil.copy2(src, STUDIO / name)
print('delivered to:', dest)
