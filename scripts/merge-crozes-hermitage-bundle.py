# coding: utf-8
"""Merge the 006期 Crozes-Hermitage bundle into the catalogue and the events feed.

Merge rule (same as 003期 Cornas / 005期 Saint-Joseph, re-used verbatim because
it is idempotent)
 - exact `id` present  -> enrich that record in place (version +1);
 - otherwise a winery whose **normalised name** already exists as a winery ->
   keep the existing stable id and enrich it. A second record for the same
   producer is never created.
 - otherwise -> new record.

Never match on an empty normalised name: `norm()` drops everything outside
[a-z0-9], so a pure-CJK name normalises to "" and would match every other such
record. All region records share that empty key — guarded explicitly.

Cross-region producers
 - 006期 hits a LOT of them: 46 of the 136 directory entries are already in the
   catalogue under condrieu / cornas / saint-joseph (M. Chapoutier, Paul
   Jaboulet Aîné, Cave de Tain, Delas, Ogier, Vidal-Fleury, Les Vins de Vienne,
   Pierre Gaillard, Yves Cuilleron, …). A producer already filed under another
   region is NOT moved: the existing regionId is kept and the extra region is
   recorded additively in `data.alsoListedIn`; reported for a human decision.
 - Such a record also keeps its OWN `name`, `sourceTitle`, `sourceURL`,
   `checkedDate`, `notes` and the way its name is spelled; the bundle's source
   is appended to `data.additionalSources` instead.

Field conflicts keep the newer, sourced text and archive the superseded value
under `notesHistory`. `localizations` is merged per language; `images` unioned
by file name.

Writes: data/catalog-seed.json, data/events.json,
outputs/collect/crozes-hermitage/merge-report.json
(backup: work/_catalog-seed.before-crozes-hermitage-merge.json — written only
once, so re-running never overwrites the true pre-merge state).

Usage: python3 scripts/merge-crozes-hermitage-bundle.py
"""
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-15'
OUT = ROOT / 'outputs' / 'collect' / 'crozes-hermitage'
CATALOGUE = ROOT / 'data' / 'catalog-seed.json'
EVENTS = ROOT / 'data' / 'events.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-crozes-hermitage-merge.json'
EVENTS_BACKUP = ROOT / 'work' / '_events.before-crozes-hermitage-merge.json'
NEW_REGION = 'crozes-hermitage'
ORIGIN = '每日采集 · 006期（Crozes-Hermitage 官方名录／坐标／官网图片）'
EMPTY = (None, '', [], {})

NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def archive(data, field, superseded):
    """Keep a superseded field value under notesHistory instead of dropping it."""
    if superseded in EMPTY:
        return
    hist = data.setdefault('notesHistory', [])
    entry = {'field': field, 'supersededValue': superseded, 'supersededAt': NOW,
             'reason': '006期 Crozes-Hermitage 采集，以有来源的新值替换同字段旧值；原值保留备查。'}
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


def main():
    additions = json.loads((OUT / 'catalog-additions.json').read_text())
    catalogue = json.loads(CATALOGUE.read_text())
    if not BACKUP.exists():
        shutil.copy2(CATALOGUE, BACKUP)
    if not EVENTS_BACKUP.exists():
        shutil.copy2(EVENTS, EVENTS_BACKUP)

    by_id = {r['id']: r for r in catalogue}
    winery_by_name = {}
    for r in catalogue:
        if r['kind'] != 'winery':
            continue
        key = norm(r.get('name'))
        if key:
            winery_by_name.setdefault(key, r)

    merged_new, merged_existing, cross_region = [], [], []

    for record in additions['records']:
        target = by_id.get(record['id'])
        matched_by_name = False
        if target is None and record['kind'] == 'winery':
            key = norm(record.get('name'))
            if key:
                target = winery_by_name.get(key)
                matched_by_name = target is not None

        if target is None:
            record['updated'] = NOW
            catalogue.append(record)
            by_id[record['id']] = record
            if record['kind'] == 'winery' and norm(record.get('name')):
                winery_by_name[norm(record['name'])] = record
            merged_new.append(record['id'])
            continue

        data = target['data']
        added, overwritten, images_added = [], [], []

        cross = matched_by_name and data.get('regionId') not in EMPTY \
            and data.get('regionId') != NEW_REGION
        keep_own = ('name', 'sourceTitle', 'sourceURL', 'checkedDate', 'notes') \
            if cross else ()

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
            if field == 'regionId':
                cur = data.get('regionId')
                if cur in EMPTY:
                    data['regionId'] = value
                    added.append('regionId')
                elif cur != value:
                    also = data.setdefault('alsoListedIn', [])
                    for extra in ([value] if isinstance(value, str) else value):
                        if extra and extra != cur and extra not in also:
                            also.append(extra)
                    cross_region.append({'id': target['id'], 'name': target['name'],
                                         'keptRegionId': cur, 'alsoListedIn': sorted(also),
                                         'bundleRegionId': value})
                continue
            if value in EMPTY:
                continue
            cur = data.get(field)
            if cur in EMPTY:
                data[field] = value
                added.append(field)
            elif cur != value and field not in keep_own:
                archive(data, field, cur)
                data[field] = value
                overwritten.append(field)

        loc_changes = merge_localizations(data, record['data'].get('localizations'))

        if cross:
            extra = {
                'sourceTitle': record['data'].get('sourceTitle'),
                'sourceURL': record['data'].get('sourceURL'),
                'checkedDate': record['data'].get('checkedDate'),
                'listedIn': NEW_REGION,
                'note': '该生产者同时出现在 AOC Crozes-Hermitage 官方名录中；'
                        '本记录主来源保留原产区（%s）不变，此处追加新增来源备查。'
                        % data.get('regionId'),
            }
            sources = data.setdefault('additionalSources', [])
            if extra not in sources:
                sources.append(extra)
        else:
            for field in ('sourceTitle', 'sourceURL', 'checkedDate'):
                if record['data'].get(field):
                    data[field] = record['data'][field]

        target['version'] = target.get('version', 1) + (
            1 if (added or overwritten or loc_changes or images_added) else 0)
        target['updated'] = NOW
        target['origin'] = ORIGIN
        if not matched_by_name:
            target['name'] = record['name']

        merged_existing.append({
            'id': target['id'], 'kind': target['kind'], 'name': target['name'],
            'bundleId': record['id'], 'matchedBy': 'name' if matched_by_name else 'id',
            'keptStableId': True, 'newVersion': target['version'],
            'fieldsFilled': sorted(added), 'fieldsOverwritten': sorted(overwritten),
            'localizationFields': sorted(loc_changes), 'imagesAttached': images_added,
        })

    CATALOGUE.write_text(json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n')

    # ---- events layer: idempotent append, and repair a half-written event ----
    REQUIRED_EVENT_FIELDS = ('title', 'summary', 'type', 'startDate', 'country',
                             'region', 'precision', 'sourceName', 'sourceURL',
                             'verification', 'checkedDate')
    events_add = json.loads((OUT / 'events-additions.json').read_text())
    store = json.loads(EVENTS.read_text())
    by_event_id = {e['id']: e for e in store['events']}
    added_events, repaired_events, skipped_events = [], [], []
    for ev in events_add['events']:
        stored = by_event_id.get(ev['id'])
        if stored is None:
            store['events'].append(ev)
            by_event_id[ev['id']] = ev
            added_events.append(ev['id'])
            continue
        filled = [f for f in REQUIRED_EVENT_FIELDS
                  if stored.get(f) in EMPTY and ev.get(f) not in EMPTY]
        for f in filled:
            stored[f] = ev[f]
        if filled:
            repaired_events.append({'id': ev['id'], 'fieldsFilled': sorted(filled)})
        else:
            skipped_events.append(ev['id'])
    store['updatedAt'] = NOW
    store['checkedAt'] = NOW
    EVENTS.write_text(json.dumps(store, ensure_ascii=False, indent=1) + '\n')

    ch_imgs = sum(len(r['data'].get('images') or []) for r in catalogue
                  if r['kind'] == 'winery' and str(r['id']).startswith('winery-crozes-hermitage-'))
    distinct = {i.get('sha256') or i.get('file')
                for r in catalogue if str(r['id']).startswith('winery-crozes-hermitage-')
                for i in (r['data'].get('images') or [])}

    summary = {
        'date': DATE,
        'phase': '006期采集（Crozes-Hermitage AOC）',
        'mergedAt': NOW,
        'catalogueBackup': str(BACKUP.relative_to(ROOT)),
        'eventsBackup': str(EVENTS_BACKUP.relative_to(ROOT)),
        'newRecords': merged_new,
        'enrichedExistingRecords': merged_existing,
        'crossRegionProducers': cross_region,
        'catalogueTotal': len(catalogue),
        'imageCounts': {'wineryAttachments': ch_imgs, 'distinctImages': len(distinct)},
        'eventsAdded': added_events,
        'eventsRepaired': repaired_events,
        'eventsAlreadyPresent': skipped_events,
        'eventsTotal': len(store['events']),
        'note': ('Crozes-Hermitage 首次采集，但目录并非首次收录：名录 136 条里有一批同时出现在 '
                 'Condrieu / Cornas / Saint-Joseph 名录中（M. Chapoutier、Paul Jaboulet Aîné、'
                 'Cave de Tain、Delas Frères、Ogier、Vidal-Fleury、Les Vins de Vienne、'
                 'Domaine Pierre Gaillard、Domaine Yves Cuilleron 等）。这些按规范化的酒庄名匹配后'
                 '**保留原稳定 ID 并在原记录上补齐**，没有新建重复记录。'
                 '`data.regionId` 是单值且站点按它归组，因此已在别的产区名下的生产者**未被搬走**，'
                 '额外产区记在 `data.alsoListedIn`（见 crossRegionProducers），'
                 '是否把某家提升到 crozes-hermitage 需人工决定。'
                 '这些记录的原有 name/sourceTitle/sourceURL/checkedDate/notes **一律保留**，'
                 '本期新增来源追加在 `data.additionalSources`；其余字段照常补齐。'
                 '被覆盖的旧文本已移入各记录的 notesHistory，可回溯。'
                 '名称匹配显式跳过归一化为空串的键（纯中文名），否则中文名酒庄会互相误匹配。'),
    }
    (OUT / 'merge-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')

    print(json.dumps({
        'newRecords': len(merged_new),
        'enrichedExistingRecords': len(merged_existing),
        'crossRegionProducers': len(cross_region),
        'catalogueTotal': len(catalogue),
        'eventsAdded': len(added_events),
        'eventsRepaired': len(repaired_events),
        'eventsAlreadyPresent': len(skipped_events),
        'eventsTotal': len(store['events']),
        'crozesImages': ch_imgs,
        'distinctImages': len(distinct),
    }, ensure_ascii=False, indent=1))
    print('backup:', BACKUP)
    print('report:', OUT / 'merge-report.json')


if __name__ == '__main__':
    main()
