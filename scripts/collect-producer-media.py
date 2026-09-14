# coding: utf-8
"""Collect each Condrieu producer's directory profile: French description + images.

Sources:
  * vin-condrieu.fr producer page  -> original French description + thumbnail
  * the producer's own website     -> candidate images (when a site URL is known)

Image policy (user decision, 2026-09-13): official-site images may be downloaded
even without a commercial licence because the Site will carry a
"合作上传，如侵权可联系删除" notice. This script therefore never removes
watermarks, never upscales, and records full provenance (source page, direct
file URL, retrieval time, byte size, SHA-256, real dimensions) so a takedown
request can be actioned per image.

Usage: python3 scripts/collect-producer-media.py <producers.json> <outdir>
"""
import hashlib, io, json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) TerroirAtlasCollector/1.0')
ROOT = Path(__file__).resolve().parents[1]
PAGE_CACHE = ROOT / 'work' / 'pagecache'
IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.avif')


def get(url, timeout=45):
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fr,en'})
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def get_cached(url, key):
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    path = PAGE_CACHE / (key + '.html')
    if path.exists():
        return path.read_text(encoding='utf-8', errors='ignore')
    html = get(url).decode('utf-8', errors='ignore')
    path.write_text(html, encoding='utf-8')
    return html


def meta(html, prop):
    m = re.search(r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)' % prop, html, re.I)
    return m.group(1) if m else None


def og_image(html):
    return meta(html, 'og:image')


def directory_description(html):
    """First real paragraph of the producer page, in the site's own language."""
    body = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', html)
    for raw in re.findall(r'(?is)<p[^>]*>(.*?)</p>', body):
        text = re.sub(r'(?s)<[^>]+>', ' ', raw)
        text = re.sub(r'&nbsp;|&#8217;|&#039;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) < 120:
            continue
        if text.lower().startswith(('notre histoire', 'gérer', 'accepter')):
            continue
        return text
    return None


def candidate_images(html, base):
    """Image URLs worth downloading, best guess first. No upscaling is invented."""
    found = []
    for url in re.findall(r'(?is)(?:src|data-src|data-lazy-src)=["\']([^"\']+\.(?:jpe?g|png|webp|avif))', html):
        found.append(urljoin(base, url))
    for srcset in re.findall(r'(?is)srcset=["\']([^"\']+)["\']', html):
        for part in srcset.split(','):
            url = part.strip().split(' ')[0]
            if url.lower().endswith(IMG_EXT):
                found.append(urljoin(base, url))
    og = og_image(html)
    if og:
        found.insert(0, urljoin(base, og))
    out, seen = [], set()
    for url in found:
        cleaned = urlunparse(urlparse(url)._replace(query=''))
        if cleaned in seen:
            continue
        seen.add(cleaned)
        lowered = cleaned.lower()
        if any(skip in lowered for skip in ('logo', 'favicon', 'placeholder', 'sprite', 'icon')):
            continue
        out.append(cleaned)
    return out


def derive_full_size(url):
    """WordPress style thumbnails: strip the -WxH suffix to reach the original."""
    stem, dot, ext = url.rpartition('.')
    stripped = re.sub(r'-\d{2,4}x\d{2,4}$', '', stem)
    if stripped != stem:
        return stripped + dot + ext
    return None


def download(url, dest_dir, index):
    parsed = urlparse(url)
    name = Path(parsed.path).name or ('image-%d' % index)
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)
    target = dest_dir / ('%02d-%s' % (index, name))
    raw = get(url)
    if len(raw) < 8000:            # placeholder / tracking pixel
        return None
    target.write_bytes(raw)
    return {'file': target.name, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(), 'directURL': url}


def dimensions(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None, None


def main():
    producers = json.loads(Path(sys.argv[1]).read_text())
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for i, item in enumerate(producers, 1):
        entry = {'wineryId': item['id'], 'name': item['name'],
                 'directoryURL': item.get('directoryURL'), 'website': item.get('website'),
                 'directoryDescription': None, 'images': [], 'failures': []}
        ddir = outdir / item['slug']
        ddir.mkdir(parents=True, exist_ok=True)

        # 1. official association profile: French description + thumbnail
        if item.get('directoryURL'):
            try:
                html = get_cached(item['directoryURL'], 'dir-' + item['slug'])
                entry['directoryDescription'] = directory_description(html)
                entry['directoryDescriptionSource'] = item['directoryURL']
                entry['directoryDescriptionChecked'] = '2026-09-13'
                urls = candidate_images(html, item['directoryURL'])
                best = []
                for url in urls[:1]:
                    full = derive_full_size(url)
                    best.append(full or url)
                for url in best:
                    try:
                        got = download(url, ddir, len(entry['images']) + 1)
                        if got:
                            got['sourcePage'] = item['directoryURL']
                            got['role'] = 'producer-photo-directory'
                            entry['images'].append(got)
                    except Exception as err:  # noqa: BLE001
                        entry['failures'].append({'url': url, 'error': str(err)})
                    time.sleep(0.4)
            except Exception as err:  # noqa: BLE001
                entry['failures'].append({'url': item.get('directoryURL'), 'error': str(err)})

        # 2. the producer's own site
        if item.get('website'):
            try:
                html = get_cached(item['website'], 'site-' + item['slug'])
                urls = candidate_images(html, item['website'])
                for url in urls[:6]:
                    try:
                        got = download(url, ddir, len(entry['images']) + 1)
                        if got:
                            got['sourcePage'] = item['website']
                            got['role'] = 'producer-site'
                            entry['images'].append(got)
                            if len([g for g in entry['images'] if g['role'] == 'producer-site']) >= 3:
                                break
                    except Exception as err:  # noqa: BLE001
                        entry['failures'].append({'url': url, 'error': str(err)})
                    time.sleep(0.4)
            except Exception as err:  # noqa: BLE001
                entry['failures'].append({'url': item.get('website'), 'error': str(err)})

        # 3. real dimensions, never upscaled
        for img in entry['images']:
            path = ddir / img['file']
            w, h = dimensions(path)
            img['width'], img['height'] = w, h
            img['relativePath'] = str(path.relative_to(outdir))
            img['retrievedAt'] = '2026-09-13'
            img['rights'] = ('来源网站公开图片；未标注许可。按站点方 2026-09-13 决定：'
                             '官网图片可下载使用，站点内容将标注“均为合作上传，如侵权可联系删除”。')
            img['watermark'] = '未去水印；未放大；仅原尺寸保存'
        manifest.append(entry)
        kept = len(entry['images'])
        print('%3d/%d %-40s images=%d desc=%s' % (i, len(producers), item['name'][:40], kept,
                                                  'yes' if entry['directoryDescription'] else 'no'),
              flush=True)
        time.sleep(1.1)

    (outdir / 'media-manifest.json').write_text(json.dumps({
        'date': '2026-09-13',
        'policy': '官网图片按站点方决定采集使用（合作上传，侵权可联系删除）；'
                  '每张保留来源页、直链、抓取时间、字节数、SHA-256 与真实尺寸，便于逐张下架。',
        'producers': manifest,
    }, ensure_ascii=False, indent=1) + '\n')
    total_images = sum(len(e['images']) for e in manifest)
    with_desc = sum(1 for e in manifest if e['directoryDescription'])
    print('\nimages=%d  descriptions=%d/%d' % (total_images, with_desc, len(manifest)))


if __name__ == '__main__':
    main()
