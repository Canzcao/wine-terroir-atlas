# coding: utf-8
"""Download the directory producer photos, then clean the image set.

Adds a real quality gate: files whose shorter side is under 250 px (menu icons,
mail sprites that slip past name filters) are dropped from the library instead of
being presented as photos. Every kept image keeps a takedown-ready record.

Usage: python3 scripts/build-image-library.py
"""
import hashlib, json, re, sys, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / '2026-09-13'
IMAGES = OUT / 'images'
MIN_SIDE = 250
DELAY = 2.0
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'image/avif,image/webp,image/png,image/*,*/*;q=0.8',
    'Referer': 'https://vin-condrieu.fr/',
}
RIGHTS = ('来源网站公开图片；未标注许可。按站点方 2026-09-13 决定：官网与协会页面图片可采集使用，'
          '站点内容将标注“均为合作上传，如侵权可联系删除”。未去水印、未放大、仅原尺寸保存。')


def dims(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.width, im.height


def download(url, target):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=60) as response:
        raw = response.read()
    target.write_bytes(raw)
    return raw


def main():
    producers = json.loads((ROOT / 'work' / 'condrieu-directory-thumbnails.json').read_text())
    existing = {}
    manifest_path = IMAGES / 'media-manifest.json'
    if manifest_path.exists():
        for entry in json.loads(manifest_path.read_text())['producers']:
            existing[entry['name']] = entry

    records, fetched = [], 0
    for item in producers:
        entry = existing.get(item['name']) or {
            'wineryId': 'winery-condrieu-' + item['slug'],
            'name': item['name'], 'directoryURL': item['directoryURL'],
            'website': None, 'images': [], 'failures': [],
        }
        entry['slug'] = item['slug']
        entry.setdefault('wineryId', 'winery-condrieu-' + item['slug'])
        entry.setdefault('failures', [])
        entry['directoryDescription'] = entry.get('directoryDescription')
        urls = {i.get('directURL') for i in entry['images']}
        for img in entry['images']:
            if not img.get('role'):
                img['role'] = 'producer-site'
        if not item['thumbnailIsPlaceholder']:
            ddir = IMAGES / item['slug']
            ddir.mkdir(parents=True, exist_ok=True)
            name = 'directory-photo' + (Path(item['thumbnailURL']).suffix or '.webp')
            target = ddir / name
            if not target.exists():
                try:
                    raw = download(item['thumbnailURL'], target)
                    fetched += 1
                    time.sleep(DELAY)
                except Exception as err:  # noqa: BLE001
                    entry['failures'].append({'url': item['thumbnailURL'], 'error': str(err)})
                    records.append(entry)
                    continue
            if target.exists():
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                if not any(i['file'] == name for i in entry['images']):
                    entry['images'].append({
                        'file': name, 'bytes': target.stat().st_size, 'sha256': digest,
                        'directURL': item['thumbnailURL'], 'sourcePage': item['directoryURL'],
                        'role': 'producer-photo-directory', 'retrievedAt': '2026-09-13',
                    })
        records.append(entry)
    print('downloaded now:', fetched)

    # quality gate + provenance for every file on disk
    kept, dropped = [], []
    for entry in records:
        survivors = []
        for img in entry['images']:
            path = IMAGES / entry['slug'] / img['file']
            if not path.exists():
                img['missing'] = True
                continue
            try:
                w, h = dims(path)
            except Exception as err:  # noqa: BLE001
                dropped.append({'file': str(path.relative_to(IMAGES)), 'reason': 'unreadable: %s' % err})
                path.unlink()
                continue
            if min(w, h) < MIN_SIDE:
                dropped.append({'file': str(path.relative_to(IMAGES)),
                                'reason': '尺寸过小（%dx%d），判定为图标/装饰图，不作为照片收录' % (w, h)})
                path.unlink()
                continue
            img['width'], img['height'] = w, h
            img['relativePath'] = str(path.relative_to(IMAGES))
            img['rights'] = RIGHTS
            img['watermark'] = '未去水印；未放大；仅原尺寸保存'
            survivors.append(img)
        entry['images'] = survivors
        kept.append(entry)

    total = sum(len(e['images']) for e in kept)
    manifest = {
        'date': '2026-09-13',
        'regionId': 'condrieu',
        'policy': RIGHTS,
        'takedown': {
            'howToUse': '收到权利方要求时，按下表定位到具体文件与来源页，删除文件并从记录中移除引用。',
            'contactNote': '站点内容将标注“均为合作上传，如侵权可联系删除”。',
        },
        'stats': {
            'producersWithImages': sum(1 for e in kept if e['images']),
            'images': total,
            'dropped': len(dropped),
        },
        'producers': kept,
        'dropped': dropped,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')

    lines = ['| 酒庄 | 文件 | 尺寸 | 来源页 | 直链 | 抓取日 | SHA-256（前16位）|',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for entry in kept:
        for img in entry['images']:
            lines.append('| %s | %s | %sx%s | %s | %s | %s | %s |' % (
                entry['name'], img['relativePath'], img['width'], img['height'],
                img['sourcePage'], img['directURL'], img['retrievedAt'], img['sha256'][:16]))
    (IMAGES / '图片溯源与下架索引.md').write_text(
        '# Condrieu 图片溯源与下架索引\n\n'
        '策略：官网与协会页面公开图片可采集使用，站点将标注“均为合作上传，如侵权可联系删除”。\n'
        '收到下架请求时按本表定位文件并删除。\n\n'
        '共 %d 张，覆盖 %d 家酒庄。\n\n' % (total, sum(1 for e in kept if e['images']))
        + '\n'.join(lines) + '\n')

    print('producers with images:', sum(1 for e in kept if e['images']))
    print('images kept:', total, '| dropped as non-photos:', len(dropped))


if __name__ == '__main__':
    main()
