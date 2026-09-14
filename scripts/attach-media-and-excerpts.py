# coding: utf-8
"""Extract directory excerpts from the cached listing pages and attach images.

Free step: the 18 listing pages are already cached, so each producer's original
French excerpt costs no extra request. Names are HTML-decoded here (some alt
attributes carried &#038;). Images collected by build-image-library.py are written
onto the matching winery records so the Site can render them.
"""
import html as htmlmod
import json, re, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-13'
OUT = ROOT / 'outputs' / 'collect' / DATE
IMAGES = OUT / 'images'

# --- 1. excerpts from cached listing pages --------------------------------
excerpts = {}
for page in range(1, 19):
    path = ROOT / 'work' / 'pagecache' / ('list-%02d.html' % page)
    if not path.exists():
        continue
    raw = path.read_text(encoding='utf-8', errors='ignore')
    for block in raw.split('<article')[1:]:
        slug_match = re.search(r'nos-vigneron/([a-z0-9-]+)/', block)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        title = re.search(r'(?is)<h2[^>]*class="entry-title"[^>]*>\s*<a[^>]*>(.*?)</a>', block)
        meta = re.search(r'(?is)<p class="post-meta">.*?</p>(.*?)(?:</article>|$)', block)
        text = re.sub(r'(?s)<[^>]+>', ' ', meta.group(1)) if meta else ''
        text = htmlmod.unescape(re.sub(r'\s+', ' ', text)).strip()
        if text and len(text) > 60:
            excerpts[slug] = {
                'name': htmlmod.unescape(re.sub(r'(?s)<[^>]+>', '', title.group(1)).strip()) if title else None,
                'excerpt': text,
                'truncated': text.rstrip().endswith('...'),
                'sourceURL': 'https://vin-condrieu.fr/nos-vigneron/%s/' % slug,
                'language': 'fr',
                'checkedDate': DATE,
            }
print('excerpts extracted:', len(excerpts))

# --- 2. images per winery -------------------------------------------------
library = json.loads((IMAGES / 'media-manifest.json').read_text())
by_slug = {e['slug']: e for e in library['producers']}

# --- 3. rewrite the addition records -------------------------------------
additions = json.loads((OUT / 'catalog-additions.json').read_text())
site_images, dir_images = 0, 0
for record in additions['records']:
    slug = record['id'].replace('winery-condrieu-', '')
    name = htmlmod.unescape(record['name'])
    record['name'] = name
    record['data']['name'] = name
    record['data']['localizations']['fr']['name'] = name
    info = excerpts.get(slug)
    if info:
        record['data']['directoryExcerpt'] = info['excerpt']
        record['data']['directoryExcerptTruncated'] = info['truncated']
        record['data']['directoryExcerptSource'] = info['sourceURL']
        record['data']['notes'] += (' 名录页已抓取原文摘录（法文，%s）。'
                                    % ('截断至...，完整简介待逐页采集' if info['truncated'] else '完整'))
    entry = by_slug.get(slug)
    if entry and entry['images']:
        record['data']['images'] = [
            {
                'file': img['relativePath'],
                'role': img['role'],
                'width': img['width'], 'height': img['height'],
                'bytes': img['bytes'], 'sha256': img['sha256'],
                'sourcePage': img['sourcePage'], 'directURL': img['directURL'],
                'retrievedAt': img['retrievedAt'], 'rights': img['rights'],
            }
            for img in entry['images']
        ]
        site_images += sum(1 for i in entry['images'] if i['role'] == 'producer-site')
        dir_images += sum(1 for i in entry['images'] if i['role'] == 'producer-photo-directory')
additions['counts']['withImages'] = sum(1 for r in additions['records'] if r['data'].get('images'))
additions['counts']['images'] = dir_images + site_images
additions['counts']['withDirectoryExcerpt'] = len(excerpts)
(OUT / 'catalog-additions.json').write_text(json.dumps(additions, ensure_ascii=False, indent=1) + '\n')

# --- 4. merge into the catalogue (update existing, add new) ---------------
catalogue = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
by_id = {r['id']: r for r in catalogue}
updated = 0
for record in additions['records']:
    if record['id'] in by_id:
        target = by_id[record['id']]
        for key in ('images', 'directoryExcerpt', 'directoryExcerptTruncated',
                    'directoryExcerptSource'):
            if record['data'].get(key) not in (None, '', [], {}):
                target['data'][key] = record['data'][key]
        target['version'] = target.get('version', 1) + 1
        target['updated'] = '2026-09-13T12:30:00.000Z'
        updated += 1

# an existing AI-named record ("Yves Cuilleron 酒窖") also needs its images
alias = by_id.get('winery-cave-yves-cuilleron')
cuil = by_slug.get('cave-yves-cuilleron')
if alias is not None and cuil and cuil['images']:
    alias['data']['images'] = [
        {'file': i['relativePath'], 'role': i['role'], 'width': i['width'], 'height': i['height'],
         'bytes': i['bytes'], 'sha256': i['sha256'], 'sourcePage': i['sourcePage'],
         'directURL': i['directURL'], 'retrievedAt': i['retrievedAt'], 'rights': i['rights']}
        for i in cuil['images']
    ]
    alias['version'] = alias.get('version', 1) + 1
    alias['updated'] = '2026-09-13T12:30:00.000Z'
    updated += 1

(ROOT / 'data' / 'catalog-seed.json').write_text(
    json.dumps(catalogue, ensure_ascii=False, indent=1) + '\n')

# --- 5. rebuild the bundle with images -----------------------------------
bundle = OUT / ('condrieu-采集包-' + DATE + '.zip')
meta = ['catalog-additions.json', 'events-additions.json', 'geo-collected.json', 'sources.json',
        'region-context.json', 'merge-report.json', '知识库导入清单.json', 'HANDOFF.md',
        'images/media-manifest.json', 'images/图片溯源与下架索引.md']
with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in meta:
        path = OUT / name
        if path.exists():
            z.write(path, name)
    for path in sorted(IMAGES.rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.avif'):
            z.write(path, str(path.relative_to(OUT)))
    z.writestr('README-包内说明.txt',
               'Condrieu 采集包（2026-09-13）\n'
               '记录：90 家官方名录酒庄（89 条新建 + 1 条并入既有记录），其中 13 家有据可查坐标。\n'
               '图片：%d 张，覆盖 %d 家酒庄（协会名录照 %d 张 + 官方站 %d 张），'
               '全部带来源页、直链、抓取日、SHA-256 与真实尺寸，见 images/图片溯源与下架索引.md。\n'
               '简介：%d 家已抓法文原文摘录。\n'
               '图片策略：官网与协会页面公开图片可采集使用，站点标注“均为合作上传，如侵权可联系删除”。\n'
               % (library['stats']['images'], library['stats']['producersWithImages'],
                  dir_images, site_images, len(excerpts)))

(OUT / 'merge-report.json').write_text(json.dumps({
    **json.loads((OUT / 'merge-report.json').read_text()),
    'recordsUpdatedWithImagesOrExcerpts': updated,
    'catalogueTotal': len(catalogue),
}, ensure_ascii=False, indent=1) + '\n')

print('images: %d (directory %d + official site %d) across %d producers'
      % (library['stats']['images'], dir_images, site_images, library['stats']['producersWithImages']))
print('records updated in catalogue:', updated)
print('bundle bytes:', bundle.stat().st_size)
