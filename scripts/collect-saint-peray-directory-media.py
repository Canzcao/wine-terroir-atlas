# coding: utf-8
"""Download the AOC Saint-Péray association's own per-producer images.

saint-peray.net carries three Divi image modules on every profile page:

  #wng-logo      the estate logo
  #wng-portrait  a person / estate photo                     -> role producer-people
  #wng-packshot  a bottle of the estate's wine               -> role wine-bottle
  #wng-photo     (some pages) a second estate/scenery photo  -> role producer-estate

These come straight off the appellation's official site, so attribution is
`producer-official` and no filename heuristic is needed to decide the *kind* of
picture. The wine's **appellation is still read off the label by a human pass** —
being listed by the Saint-Péray association does not make every bottle on the
page a Saint-Péray (the same lesson as 003期 Cornas). Until that pass runs,
`appellation` stays null and `reviewAs` queues the image.

Everything is appended into the same `wine-image-manifest.json` written by
`collect-wine-images.py`, so contact sheets / apply-visual-review keep working.

Usage: python3 scripts/collect-saint-peray-directory-media.py [--refetch]
"""
import argparse
import hashlib
import json
import re
import ssl
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-17'
WORK = ROOT / 'work' / 'saint-peray'
RAW = WORK / 'producers'
OUTDIR = ROOT / 'outputs' / 'collect' / 'saint-peray' / 'images'
MANIFEST = OUTDIR / 'wine-image-manifest.json'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DELAY = 0.8
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

RIGHTS = ('来源 AOC Saint-Péray 产区协会官网公开图片；未标注单独许可。按站点方 2026-09-13 决定：'
          '官网图片可下载使用，站点内容将标注“均为合作上传，如侵权可联系删除”。')
WATERMARK = '未去水印；未放大；仅原尺寸保存'

# module id -> (role, attribution, kind label used in the filename)
MODULES = {
    'wng-portrait': ('producer-people', 'producer-official', 'portrait'),
    'wng-packshot': ('wine-bottle', 'likely-own', 'packshot'),
    'wng-photo': ('producer-estate', 'producer-official', 'estate'),
    'wng-logo': ('producer-logo', 'producer-official', 'logo'),
}


def slugify(name: str) -> str:
    import unicodedata
    t = unicodedata.normalize('NFKD', name or '')
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^A-Za-z0-9]+', '-', t).strip('-').lower()
    return re.sub(r'-{2,}', '-', t)


def module_url(html: str, mod: str):
    i = html.find(f'id="{mod}"')
    if i < 0:
        return None
    seg = html[i:i + 6000]
    m = re.search(r'data-src="(https://saint-peray\.net/wp-content/uploads/[^"]+)"', seg)
    if not m:
        m = re.search(r'<noscript><img[^>]+src="(https://saint-peray\.net/wp-content/uploads/[^"]+)"', seg)
    if not m:
        return None
    url = m.group(1)
    # prefer the largest srcset variant so we keep the real original
    ss = re.search(r'data-srcset="([^"]+)"', seg)
    if ss:
        cands = re.findall(r'(https://saint-peray\.net/wp-content/uploads/\S+?)\s+(\d+)w', ss.group(1))
        if cands:
            best = max(cands, key=lambda c: int(c[1]))
            if '_' not in best[0].rsplit('/', 1)[-1] or True:
                url = best[0]
    return url


def download(url: str, dest: Path, refetch: bool):
    if dest.exists() and not refetch and dest.stat().st_size > 500:
        b = dest.read_bytes()
        return b
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={'User-Agent': UA})
    try:
        with urlopen(req, timeout=60, context=SSL_CTX) as r:
            b = r.read()
        dest.write_bytes(b)
        time.sleep(DELAY)
        return b
    except (HTTPError, URLError, OSError) as exc:
        print(f'    !! {url} -> {type(exc).__name__}: {exc}')
        return None


def png_size(b: bytes):
    if b[:8] == b'\x89PNG\r\n\x1a\n':
        return int.from_bytes(b[16:20], 'big'), int.from_bytes(b[20:24], 'big')
    return None


def jpeg_size(b: bytes):
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
            return int.from_bytes(b[i + 7:i + 9], 'big'), int.from_bytes(b[i + 5:i + 7], 'big')
        if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        i += 2 + int.from_bytes(b[i + 2:i + 4], 'big')
    return None


def webp_size(b: bytes):
    if b[8:12] == b'WEBP' and b[12:16] == b'VP8X':
        w = int.from_bytes(b[24:27], 'little') + 1
        h = int.from_bytes(b[27:30], 'little') + 1
        return w, h
    return None


def true_size(b: bytes):
    """Read pixel dimensions from the file header only.

    Deliberately avoids decoding: the association serves multi-thousand-pixel
    originals (several MB each) and letting an image library decode them all
    made the collector get OOM-killed (exit 137).
    """
    return png_size(b) or jpeg_size(b) or webp_size(b) or (None, None)


def save_manifest(manifest: dict):
    OUTDIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(
        {'date': DATE, 'producers': sorted(manifest.values(), key=lambda e: e['slug']),
         'note': 'association-module images carry classificationMethod=official-module; '
                 'wine appellation still requires a label-reading pass.'},
        ensure_ascii=False, indent=1), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refetch', action='store_true')
    args = ap.parse_args()

    prof = json.loads((WORK / 'profiles.json').read_text(encoding='utf-8'))
    producers = prof['producers']
    OUTDIR.mkdir(parents=True, exist_ok=True)

    manifest = {}
    if MANIFEST.exists():
        old = json.loads(MANIFEST.read_text(encoding='utf-8'))
        manifest = {e['slug']: e for e in (old.get('producers') or [])}

    added = skipped = failed = 0
    for n, p in enumerate(producers, 1):
        slug = slugify(p.get('name') or p['slug'])
        html_path = RAW / f"{p['slug']}.html"
        if not html_path.exists():
            print(f'  [{n:2d}/{len(producers)}] {slug}: no cached profile page')
            continue
        html = html_path.read_text(encoding='utf-8', errors='replace')

        entry = manifest.get(slug) or {
            'slug': slug, 'name': p.get('name'), 'wineryId': None,
            'website': p.get('website'), 'images': [], 'failures': [],
            'pagesVisited': [],
        }
        entry.setdefault('images', [])
        have = {im['file'] for im in entry['images']}

        got = []
        for mod, (role, attrib, label) in MODULES.items():
            url = module_url(html, mod)
            if mod == 'wng-logo':
                continue  # logos are not editorial content; skip to keep the pack lean
            if not url:
                continue
            ext = Path(url.split('?')[0]).suffix.lower() or '.jpg'
            fname = f'{label}{ext}'
            dest = OUTDIR / slug / fname
            b = download(url, dest, args.refetch)
            if not b:
                failed += 1
                entry['failures'].append({'url': url, 'error': 'download failed'})
                continue
            if fname in have:
                skipped += 1
                continue
            size = true_size(b) or (None, None)
            entry['images'].append({
                'file': fname,
                'relativePath': f'{slug}/{fname}',
                'role': role,
                'confidence': 'high' if mod in ('wng-portrait', 'wng-packshot') else 'medium',
                'attribution': attrib,
                'appellation': None,   # read off the label in the visual pass
                'reviewAs': ('label-read-appellation' if mod == 'wng-packshot' else None),
                'classificationMethod': 'official-module',
                'reasons': [f'来自产区协会官网 #{mod} 模块，模块语义明确'],
                'altText': None,
                'sourceName': 'AOC Saint-Péray 产区协会官网 · Nos Vignerons 名录',
                'sourcePage': p.get('profileURL'),
                'directURL': url,
                'width': size[0], 'height': size[1],
                'aspect': round(size[0] / size[1], 3) if size[0] and size[1] else None,
                'hasAlpha': bool(b[:8] == b'\x89PNG\r\n\x1a\n'),
                'bytes': len(b),
                'sha256': hashlib.sha256(b).hexdigest(),
                'retrievedAt': DATE,
                'rights': RIGHTS,
                'watermark': WATERMARK,
            })
            added += 1
            got.append(label)

        manifest[slug] = entry
        print(f"  [{n:2d}/{len(producers)}] {slug:42s} +{len(got)} {','.join(got) or '-'}",
              flush=True)
        # save every few producers: this collector gets SIGTERM-killed on large
        # batches, and a manifest written only at the end loses all of it.
        if n % 4 == 0:
            save_manifest(manifest)

    save_manifest(manifest)

    print(f'\nadded {added} / skipped {skipped} / failed {failed}')
    print(f'manifest producers: {len(manifest)}')
    print(f'wrote {MANIFEST.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
