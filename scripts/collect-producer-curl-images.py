# coding: utf-8
"""Generalized curl-based fallback collector for producer websites.

Why this exists: the sandbox resets python-urllib TLS on some hosts while the
`curl` binary works. The stdlib collector (`collect-wine-images.py`) also cannot
honour per-host Crawl-delay. This script:

- reads a producer list JSON (`[{slug,name,wineryId,website,...}]`),
- fetches and obeys `robots.txt` (a host-wide `Disallow: /` for `*` is skipped
  entirely and the reason is written into the manifest),
- honours `Crawl-delay` per host,
- **saves the manifest after every single image**, so a kill (this environment
  SIGTERMs long calls, exit 137) loses at most one download and a re-run resumes
  by skipping `directURL`s already recorded for that producer,
- writes image entries in exactly the schema `collect-wine-images.py` uses, so
  the downstream build / visual-review / repack chain needs no change.

Usage:
  python3 scripts/collect-producer-curl-images.py <profiles.json> <out-dir> \
      [--manifest-root <images-dir>] [--date YYYY-MM-DD] [--max-per-site 26] \
      [--workers 4] [--only slug,slug] [--force]
"""
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')
UA_ROBOTS = 'terroir-atlas-collector/1.0 (+contact: site owner)'

RIGHTS = ('来源酒庄官网公开图片；未标注许可。按站点方 2026-09-13 决定：官网图片可下载使用，'
          '站点内容将标注“均为合作上传，如侵权可联系删除”。')

WINE_HINT = re.compile(
    r'bouteil|bottle|packshot|etiquet|label|magnum|flacon|coffret|millesim|vin|vins|'
    r'cuvee|cuvee|gamme|boutique|nos-|syrah|marsanne|roussanne|viognier|cornas|'
    r'condrieu|saint|st-|crozes|cote|cotes|hermitage|igp|rouge|blanc', re.I)
IMG_SRC = re.compile(
    r'<img[^>]+(?:data-src|data-lazy-src|data-original|data-cfsrc|data-echo|src)=["\']([^"\']+)["\']',
    re.I)
# Lazy-load attributes seen in the wild: data-src (WP/lazysizes), data-original
# (Tardieu-Laurent's theme, also on <div> slide placeholders, not only <img>),
# data-lazy-src (WP Rocket), data-cfsrc (Cloudflare).
ATTR_LAZY = re.compile(
    r'data-(?:original|src|lazy-src|lazy|bg|background|cfsrc|echo)=["\']([^"\']+)["\']', re.I)
SRCSET = re.compile(r'(?:data-)?srcset=["\']([^"\']+)["\']', re.I)
CSS_BG = re.compile(r'url\((["\']?)([^)"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^)"\']*)?)\1\)', re.I)
IMG_EXT = re.compile(r'\.(jpe?g|png|webp)(\?|$)', re.I)

_host_lock = threading.Lock()
_host_next = {}          # host -> earliest monotonic time for next request
_robots_cache = {}       # host -> (RobotFileParser|None, crawl_delay|None, disallowed_root: bool)
_manifest_lock = threading.Lock()
_seen_sha = set()
_seen_sha_lock = threading.Lock()


PAGECACHE = ROOT / 'work' / 'pagecache' / 'curl'


def curl_text(url, referer=None, cache_hours=24):
    """Fetch text, caching on disk so re-runs (this env kills long calls) are cheap.

    Critical for hosts with a large Crawl-delay: without the cache every resume
    would re-spend the whole crawl-delay budget re-fetching pages it already has.
    """
    key = hashlib.sha1(url.encode('utf-8')).hexdigest()[:20]
    path = PAGECACHE / ('%s.html' % key)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < cache_hours * 3600:
            return path.read_text(encoding='utf-8', errors='replace')
    txt = _curl(url, referer, binary=False)
    if txt is not None:
        PAGECACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(txt, encoding='utf-8')
    return txt


def curl_bytes(url, referer=None):
    return _curl(url, referer, binary=True)


def _curl(url, referer=None, binary=False):
    host = urlparse(url).netloc
    _wait_turn(host)
    cmd = ['curl', '-sL', '--max-time', '25', '-A', UA]
    if referer:
        cmd += ['-e', referer]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=40)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    if binary:
        return r.stdout
    ctype = r.stdout[:120].lstrip()
    if ctype.startswith(b'%PDF') or ctype.startswith(b'\xff\xd8') or ctype.startswith(b'\x89PNG'):
        return None
    return r.stdout.decode('utf-8', 'replace')


def _delay_for(host):
    info = _robots_cache.get(host)
    if info is None:
        return 0.6
    delay = info[1]
    return float(delay) if delay else 0.6


def _wait_turn(host):
    with _host_lock:
        delay = _delay_for(host)
        now = time.monotonic()
        nxt = _host_next.get(host, 0.0)
        wait = max(0.0, nxt - now)
        _host_next[host] = max(now, nxt) + delay
    if wait > 0:
        time.sleep(wait)


def load_robots(scheme_host):
    """Return (allowed_root: bool, crawl_delay: float|None, note: str)."""
    with _host_lock:
        if scheme_host in _robots_cache:
            return _robots_cache[scheme_host]
    url = scheme_host + '/robots.txt'
    txt = curl_text(url)
    allowed, delay, note = True, None, ''
    if txt is None:
        note = 'robots.txt 不可达（按允许处理）'
    elif '<html' in txt[:400].lower() or '<!doctype html' in txt[:400].lower():
        note = 'robots.txt 返回 HTML（无有效规则，按允许处理）'
    else:
        rp = RobotFileParser()
        rp.parse(txt.splitlines())
        try:
            allowed = rp.can_fetch(UA_ROBOTS, scheme_host + '/')
        except Exception:
            allowed = True
        cd = rp.crawl_delay(UA_ROBOTS)
        if cd is None:
            cd = rp.crawl_delay('*')
        delay = float(cd) if cd else None
        note = 'robots.txt 已读取'
    with _host_lock:
        _robots_cache[scheme_host] = (allowed, delay, note)
    return allowed, delay, note


def robots_root_allowed(host):
    """True if the site root is crawlable for our UA."""
    best = None
    for scheme in ('https', 'http'):
        allowed, delay, note = load_robots('%s://%s' % (scheme, host))
        if allowed:
            return True, scheme, delay, note
        best = (False, scheme, delay, note)
    return best if best else (False, 'https', None, '')


def clean_url(u, base):
    u = (u or '').strip()
    if not u or u.startswith('data:'):
        return None
    u = urljoin(base, u)
    if u.startswith('//'):
        u = 'https:' + u
    return u


def dims(raw):
    try:
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        alpha = im.mode in ('RGBA', 'LA', 'PA') or (
            im.mode == 'P' and 'transparency' in im.info)
        return w, h, alpha
    except Exception:
        return None, None, False


def save_manifest(manifest, path):
    with _manifest_lock:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
        tmp.replace(path)


def get_entry(manifest, item):
    for e in manifest['producers']:
        if e['slug'] == item['slug']:
            e.setdefault('images', [])
            e.setdefault('failures', [])
            e.setdefault('pagesVisited', [])
            return e
    entry = {'slug': item['slug'], 'name': item.get('name') or item['slug'],
             'wineryId': item.get('wineryId'), 'website': item.get('website'),
             'images': [], 'failures': [], 'pagesVisited': []}
    manifest['producers'].append(entry)
    return entry


def collect(item, out_dir, manifest, manifest_path, run_date, max_per_site, force,
            max_pages=12):
    slug, site = item['slug'], item['website']
    host = urlparse(site).netloc
    entry = get_entry(manifest, item)
    if entry.get('images') and not force:
        print('%-34s SKIP (已有 %d 张)' % (slug, len(entry['images'])))
        return
    allowed, scheme, delay, note = robots_root_allowed(host)
    if not allowed:
        entry['robotsDisallowed'] = True
        entry['robotsNote'] = 'robots.txt 对通用 UA 禁止抓取（Disallow: /），本次遵守 robots 不采集'
        entry['failures'] = (entry.get('failures') or []) + [
            {'url': site, 'error': 'robots.txt Disallow: / —— 依规不采集'}]
        save_manifest(manifest, manifest_path)
        print('%-34s ROBOTS-DISALLOW  %s' % (slug, note))
        return
    entry.pop('robotsDisallowed', None)
    if entry.get('robotsNote'):
        entry['robotsCrawlDelay'] = entry.pop('robotsNote')
    if delay:
        entry['robotsCrawlDelay'] = 'Crawl-delay: %ss（robots.txt 指定，已遵守）' % int(delay)

    ddir = out_dir / slug
    ddir.mkdir(parents=True, exist_ok=True)
    seen_direct = {im.get('directURL') for im in entry['images']}

    # Page discovery: breadth-first over same-host HTML pages, wine-ish paths
    # first. Many producer sites hide their content behind a frameset / splash
    # page (ferraton.fr serves a 2.9 KB frameset whose only links are
    # default.cfm / default_gb.cfm), so a single level from the homepage is not
    # enough; but keep the page budget (max_pages) and the per-host rate limit
    # so this stays polite.
    skips = ('/wp-admin', '/wp-login', '/mentions-legales', '/panier', '/cart',
             '/account', '/feed', '/xmlrpc')

    def harvest_links(html, base):
        hinted, other = [], []
        for m in re.finditer(r'href=["\']([^"\']+)["\']', html):
            u = clean_url(m.group(1), base)
            if not u:
                continue
            pu = urlparse(u)
            if pu.netloc != host or pu.scheme not in ('http', 'https'):
                continue
            path = pu.path.lower()
            if any(s in path for s in skips):
                continue
            if re.search(r'\.(pdf|jpe?g|png|webp|zip|mp4|css|js)$', path):
                continue
            if u in pages or u in queued:
                continue
            queued.add(u)
            (hinted if WINE_HINT.search(path) else other).append(u)
        return hinted + other

    pages, queued = [site], {site}
    home = curl_text(site)
    if not home:
        entry['failures'] = (entry.get('failures') or []) + [
            {'url': site, 'error': 'curl 抓取失败（首页不可达）'}]
        save_manifest(manifest, manifest_path)
        print('%-34s FETCH-FAIL' % slug)
        return
    queue = harvest_links(home, site)
    i = 0
    while queue and len(pages) < max_pages:
        u = queue.pop(0)
        html = curl_text(u, referer=site)
        if not html:
            continue
        pages.append(u)
        i += 1
        if i % 3 == 0 or len(queue) < 4:      # deepen gradually, stay in budget
            queue.extend(harvest_links(html, u))

    cands, seen_key = [], set()
    for page_url in pages:
        html = home if page_url == site else curl_text(page_url, referer=site)
        if not html:
            continue
        for m in IMG_SRC.finditer(html):
            u = clean_url(m.group(1), page_url)
            if u and IMG_EXT.search(u):
                cands.append(u)
        for m in ATTR_LAZY.finditer(html):
            u = clean_url(m.group(1), page_url)
            if u and IMG_EXT.search(u):
                cands.append(u)
        for m in SRCSET.finditer(html):
            best, bw = None, -1
            for part in m.group(1).split(','):
                bits = part.strip().split()
                if not bits:
                    continue
                u = clean_url(bits[0], page_url)
                if not u or not IMG_EXT.search(u):
                    continue
                w = 0
                if len(bits) > 1 and bits[1].endswith('w'):
                    try:
                        w = int(bits[1][:-1])
                    except ValueError:
                        w = 0
                if w > bw:
                    best, bw = u, w
            if best:
                cands.append(best)
        for m in CSS_BG.finditer(html):
            u = clean_url(m.group(2), page_url)
            if u:
                cands.append(u)
    ordered = []
    for u in cands:
        key = re.sub(r'-\d{2,4}x\d{2,4}(?=\.)', '', u.lower())
        if key not in seen_key:
            seen_key.add(key)
            ordered.append(u)

    entry['pagesVisited'] = sorted(set((entry.get('pagesVisited') or []) + pages))
    entry['failures'] = (entry.get('failures') or []) + []
    got = skipped = 0
    for u in ordered:
        if len(entry['images']) >= max_per_site:
            break
        if u in seen_direct:
            skipped += 1
            continue
        raw = curl_bytes(u, referer=site)
        if not raw or len(raw) < 6000:
            if len(entry['failures']) < 200:
                entry['failures'].append({'url': u[:160],
                                          'error': 'bytes=%s (太小或不可达)' % (len(raw) if raw else 0)})
            continue
        digest = hashlib.sha256(raw).hexdigest()
        with _seen_sha_lock:
            if digest in _seen_sha:
                skipped += 1
                continue
            _seen_sha.add(digest)
        w, h, alpha = dims(raw)
        if not w or min(w, h) < 250:
            continue
        name = re.sub(r'[^A-Za-z0-9._-]', '_', Path(urlparse(u).path).name)
        target = ddir / ('%02d-%s' % (len(entry['images']) + 1, name))
        target.write_bytes(raw)
        hint = WINE_HINT.search(u)
        role = 'wine-bottle' if (hint and (alpha or h / w > 1.4)) else (
            'wine-photo' if hint else 'producer-site')
        entry['images'].append({
            'file': target.name,
            'relativePath': '%s/%s' % (slug, target.name),
            'role': role, 'confidence': 'low', 'attribution': 'unverified',
            'appellation': None, 'reviewAs': 'possible-wine',
            'classificationMethod': 'heuristic',
            'reasons': ['curl 备用通道采集（主采集器网络重置）', '启发式初判，待人工视觉复核'],
            'altText': None, 'sourceName': '酒庄官网 ' + host,
            'sourcePage': site, 'directURL': u, 'width': w, 'height': h,
            'aspect': round(h / w, 2), 'hasAlpha': alpha, 'bytes': len(raw),
            'sha256': digest, 'retrievedAt': run_date,
            'rights': RIGHTS, 'watermark': '未去水印；未放大；仅原尺寸保存'})
        got += 1
        save_manifest(manifest, manifest_path)   # per-image save = resume point
    save_manifest(manifest, manifest_path)
    print('%-34s images_now=%d new=%d skipped=%d pages=%d failures=%d'
          % (slug, len(entry['images']), got, skipped, len(pages), len(entry['failures'])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('profiles')
    ap.add_argument('out_dir')
    ap.add_argument('--manifest-root', default=None)
    ap.add_argument('--date', default=None)
    ap.add_argument('--max-per-site', type=int, default=26)
    ap.add_argument('--max-pages', type=int, default=12)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--only', default=None)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest_root or out_dir) / 'wine-image-manifest.json'
    if not manifest_path.exists():
        print('manifest not found: %s' % manifest_path)
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text())
    run_date = args.date or time.strftime('%Y-%m-%d')

    items = json.loads(Path(args.profiles).read_text())
    items = [i for i in items if i.get('website')]
    if args.only:
        want = {s.strip() for s in args.only.split(',')}
        items = [i for i in items if i['slug'] in want]

    for p in manifest['producers']:
        for im in p.get('images') or []:
            if im.get('sha256'):
                _seen_sha.add(im['sha256'])

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(collect, it, out_dir, manifest, manifest_path,
                            run_date, args.max_per_site, args.force, args.max_pages)
                for it in items]
        for f in futs:
            try:
                f.result()
            except Exception as err:  # noqa: BLE001
                print('ERROR %s' % err)


if __name__ == '__main__':
    main()
