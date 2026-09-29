# coding: utf-8
"""Regenerate only the image-provenance index, the ZIP bundle and the hand-off copy.

Used after HANDOFF.md or events-additions.json is edited, so the delivered archive
always matches the files on disk. Does NOT touch data/catalog-seed.json or
data/events.json — see merge-grillet-bundle.py for the merge.
"""
import json, os, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / 'chateau-grillet'
STUDIO = Path(os.environ.get('CONTENT_STUDIO', Path(__file__).resolve().parent.parent.parent / 'wine-content-studio')) \
    / 'outputs' / 'collect' / DATE

# ---- image provenance / takedown index --------------------------------------
manifest = json.loads((OUT / 'images' / 'wine-image-manifest.json').read_text())
images = manifest['producers'][0]['images']
lines = [
    '# 001期 格里叶堡 图片溯源与下架索引',
    '',
    '策略：官网公开图片可采集使用，站点将标注“均为合作上传，如侵权可联系删除”。',
    '收到下架请求时按本表定位文件并删除（本庄园图片集中在 `winery-chateau-grillet/`，可整目录下架）。',
    '',
    '共 %d 张，全部经逐张视觉复核（classificationMethod = agent-visual-review）。' % len(images),
    '',
    '| 文件 | 角色 | 归属 | 产区（读自画面） | 尺寸 | 来源页 | 直链 | 抓取日 | SHA-256（前16位）|',
    '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
]
for img in images:
    lines.append('| %s | %s | %s | %s | %dx%d | %s | %s | %s | %s |' % (
        img['relativePath'], img['role'], img['attribution'], img.get('appellation') or '—',
        img['width'], img['height'], img['sourcePage'], img['directURL'],
        img['retrievedAt'], img['sha256'][:16]))
lines += ['', '## 视觉复核说明', '']
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
events = json.loads((OUT / 'events-additions.json').read_text())
members = ['catalog-additions.json', 'events-additions.json', 'geo-collected.json',
           'sources.json', 'discrepancies.json', 'merge-report.json',
           '知识库导入清单.json', 'HANDOFF.md']
bundle = OUT / ('001期-格里叶堡-采集包-' + DATE + '.zip')
with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in members:
        path = OUT / name
        if path.exists():
            z.write(path, name)
    for path in sorted((OUT / 'images').rglob('*')):
        if path.is_file() and path.name != '.DS_Store':
            z.write(path, str(path.relative_to(OUT)))
    z.writestr('README-包内说明.txt',
               '001期 格里叶堡产区（Château-Grillet AOC）采集包　%s\n'
               '内容：1 条产区记录 + 1 条酒庄记录 + 3 条酒款记录 + 2 条年份记录 + %d 条事件，'
               '以及 %d 张逐张视觉复核过的图片（人物 / 庄园 / 酒款 / 酒标 / INAO 地图）。\n'
               '坐标：45.4501025, 4.7519914（OSM way/337680164，附带庄园官网作为 website 标签）。\n'
               '图片权限：来源酒庄官网公开图片；未标注许可。按站点方 2026-09-13 决定可下载使用，'
               '站点内容标注“均为合作上传，如侵权可联系删除”。\n'
               '分歧未定项见 discrepancies.json（面积 / 梯田级数 / AOC 月日 / 藤龄 / 年产量 / 副牌名）。\n'
               '一条人事事件因缺可核实的发生日期未登记为事件，原因见 events-additions.json 的 heldBack。\n'
               '用途：作为 terroir-atlas 站点的数据来源；科普内容转化在“葡萄酒引流图文”任务独立进行。\n'
               % (DATE, len(events['events']), len(images)))

STUDIO.mkdir(parents=True, exist_ok=True)
shutil.copy2(bundle, STUDIO / bundle.name)
for name in members:
    src = OUT / name
    if src.exists():
        shutil.copy2(src, STUDIO / name)

print('images indexed:', len(images))
print('events in bundle:', len(events['events']))
print('bundle:', bundle, bundle.stat().st_size)
print('delivered to:', STUDIO / bundle.name)
