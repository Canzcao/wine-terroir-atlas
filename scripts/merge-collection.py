# coding: utf-8
"""Merge collected winery records into the catalogue, then finalise the bundle.

Dedupe rule: an existing winery record with a matching normalised name keeps its
stable ID and is enriched instead of duplicated.
"""
import json, re, unicodedata, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / DATE
NOW = '2026-09-13T11:20:00.000Z'


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


additions = json.loads((OUT / 'catalog-additions.json').read_text())
catalogue = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
by_id = {r['id']: r for r in catalogue}
existing_winery_by_name = {norm(r['name']): r for r in catalogue
                           if r['kind'] == 'winery' and r.get('name')}

merged_new, merged_existing, renamed = [], [], []
for record in additions['records']:
    key = norm(record['name'])
    existing = existing_winery_by_name.get(key)
    if existing and existing['id'] != record['id']:
        data = existing['data']
        enriched = []
        for field, value in record['data'].items():
            if value in (None, '', [], {}):
                continue
            if data.get(field) in (None, '', [], {}):
                data[field] = value
                enriched.append(field)
        if record['data'].get('lat') is not None:
            data['lat'] = record['data']['lat']
            data['lng'] = record['data']['lng']
            data['locationSourceURL'] = record['data']['locationSourceURL']
            data['locationPrecision'] = record['data']['locationPrecision']
            data['checkedDate'] = DATE
            enriched += ['lat', 'lng', 'locationSourceURL', 'locationPrecision']
        existing['version'] = existing.get('version', 1) + 1
        existing['updated'] = NOW
        merged_existing.append({'keptId': existing['id'], 'directoryName': record['name'],
                                'enrichedFields': sorted(set(enriched))})
        continue
    if record['id'] in by_id:
        continue
    record['updated'] = NOW
    catalogue.append(record)
    by_id[record['id']] = record
    merged_new.append(record['id'])

(ROOT / 'data' / 'catalog-seed.json').write_text(
    json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n')

summary = {
    'date': DATE,
    'newWineryRecords': len(merged_new),
    'dedupedIntoExisting': merged_existing,
    'catalogueTotal': len(catalogue),
    'withCoordinates': sum(1 for r in catalogue
                           if r['kind'] == 'winery' and r['data'].get('lat') is not None),
}
(OUT / 'merge-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n')

# Region-level context that is verified but has no evidenced occurrence date, so it
# is deliberately NOT registered as an event (the events schema requires startDate).
context = {
    'date': DATE,
    'registeredAsEvent': False,
    'reason': '已核实的全国性产量预估缺少可核实的事件发生日期，'
              '事件图层要求 startDate，故不登记为事件，仅作为产区背景资料保存。',
    'items': [
        {
            'title': '法国2026年葡萄产量预估为1957年以来最低',
            'summary': '法国农业部统计服务 Agreste 预估2026年全国葡萄酒产量低于3400万百升，'
                       '同比减少约6%，为近30年最小收成之一、按 OIV 口径为1957年以来最低。'
                       '大区层面差异明显：东南部产区预计与2025年接近、可能高约2%，但仍低于五年均值。'
                       '该预估为大区层面，未单列罗讷河谷或 Condrieu。',
            'type': 'harvest-context',
            'publishedDate': '2026-09-09',
            'country': '法国',
            'region': '法国（全国）',
            'sourceName': 'The Connexion（引述法国农业部 Agreste 与 OIV）',
            'sourceURL': 'https://beta.connexionfrance.com/news/french-wine-production-set-for-70-year-low-following-devastating-summer/813477',
            'verification': '已打开原文核对：发布时间 2026-09-09（2026-09-10 修改）',
            'checkedDate': DATE,
        }
    ],
}
(OUT / 'region-context.json').write_text(json.dumps(context, ensure_ascii=False, indent=1) + '\n')

# Knowledge-base import list, review-gated.
kb = {
    'generatedFor': '知识库导入',
    'date': DATE,
    'regionId': 'condrieu',
    'policy': '所有条目初始为“待审核”；审核通过后才可标“已审核”。',
    'entries': [
        {'catalogueId': rid, 'reviewStatus': '待审核',
         'reviewNote': '需知识库审核流程核对后方可标为已审核。'}
        for rid in merged_new
    ] + [
        {'catalogueId': e['keptId'], 'reviewStatus': '待审核',
         'reviewNote': '既有记录被本期采集补充（%s），需审核后标记。' % ','.join(e['enrichedFields'])}
        for e in merged_existing
    ],
}
(OUT / '知识库导入清单.json').write_text(json.dumps(kb, ensure_ascii=False, indent=1) + '\n')

bundle = OUT / ('condrieu-采集包-' + DATE + '.zip')
members = ['catalog-additions.json', 'events-additions.json', 'geo-collected.json',
           'sources.json', 'region-context.json', 'merge-report.json',
           '知识库导入清单.json', 'HANDOFF.md']
with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in members:
        path = OUT / name
        if path.exists():
            z.write(path, name)
    z.writestr('README-包内说明.txt',
               'Condrieu 采集包（2026-09-13）\n'
               '内容：90 家官方名录酒庄记录（含 15 家有据可查坐标）、坐标采集原始结果（含未采纳原因）、'
               '逐条来源、产区背景资料、知识库导入清单（待审核）。\n'
               '未包含：本期无可核实事件、无有许可的实景图片。\n'
               '用途：作为 terroir-atlas 站点的数据来源；科普内容转化另在独立对话框进行。\n')

print(json.dumps(summary, ensure_ascii=False, indent=1))
print('bundle:', bundle, bundle.stat().st_size)
