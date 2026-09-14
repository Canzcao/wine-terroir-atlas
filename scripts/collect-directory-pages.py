# coding: utf-8
"""Fetch the Condrieu producer directory with a real browser profile.

The association site blocks non-browser user agents (403) and its robots.txt asks
for Crawl-delay: 10, so every request to vin-condrieu.fr is spaced by 10 seconds
and pages are cached, which makes a long run resumable.

Modes
  listings : 18 paginated listing pages -> producer slug, name, thumbnail URL
  profiles : 90 producer pages          -> description, official website,
                                          banner image, hidden photo gallery

Each producer page carries three things the map/cards need:
  1. the original French description paragraphs
  2. the estate's own website, behind the "ACCÉDER AU SITE" button
  3. a lightbox gallery of up to six photos, whose URLs live only in the
     page's generated CSS (.wdcl_image_carousel_child_N_tb_body{background-image:url(...)})
     and therefore never show up in a plain <img> scan.

Usage: python3 scripts/collect-directory-pages.py listings|profiles [limit]
"""
import json, re, sys, time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work' / 'pagecache'
OUTDIR = ROOT / 'work'
BASE = 'https://vin-condrieu.fr/nos-vigneron/'
DELAY = 10.0  # robots.txt Crawl-delay
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}
IMG_RE = re.compile(
    r'<img[^>]+src="(https://vin-condrieu\.fr/wp-content/uploads/[^"]+)"[^>]*alt="([^"]*)"')
LINK_RE = re.compile(r'href="(https://vin-condrieu\.fr/nos-vigneron/([a-z0-9-]+)/)"')
# "ACCÉDER AU SITE" button -> the estate's own website
SITE_RE = re.compile(
    r'<a[^>]+href="(https?://[^"]+)"[^>]*>\s*ACC[ÉE]DER AU SITE\s*</a>', re.I)
# gallery images are declared in generated CSS, not in <img> tags
GALLERY_RE = re.compile(
    r'\.wdcl_image_carousel_child_\d+_tb_body\s*\{\s*background-image\s*:\s*url\(([^)]+)\)')
BANNER_RE = re.compile(
    r'(https://vin-condrieu\.fr/wp-content/uploads/[^"\')\s]+_banner(?:-\d+x\d+)?\.(?:webp|jpe?g|png))')
UPLOAD_RE = re.compile(
    r'(https://vin-condrieu\.fr/wp-content/uploads/[^"\')\s]+\.(?:webp|jpe?g|png|avif))')
SITE_NOISE = ('vincondrieu.fr', 'vin-condrieu.fr', 'instagram.com', 'facebook.com',
              'google.com', 'gstatic.com', 'unpkg.com', 'youtube.com', 'twitter.com',
              'linkedin.com', 'tiktok.com', 'pinterest.')
SITE_NOISE_EXT = ('.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.ico', '.pdf')


def own_website(html):
    """The estate's own site, skipping the association's own pages and socials."""
    for m in SITE_RE.finditer(html):
        url = m.group(1).strip().rstrip('/')
        low = url.lower()
        if any(noise in low for noise in SITE_NOISE):
            continue
        if any(low.endswith(ext) for ext in SITE_NOISE_EXT):
            continue
        return url
    return None


def gallery_images(html):
    """Lightbox photos, de-duplicated, original size only."""
    out, seen = [], set()
    for m in GALLERY_RE.finditer(html):
        url = m.group(1).strip().strip('\'"')
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def banner_image(html):
    m = BANNER_RE.search(html)
    if m:
        return re.sub(r'-\d{2,4}x\d{2,4}(?=\.)', '', m.group(1))
    return None


def fetch(url, key):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (key + '.html')
    if path.exists():
        return path.read_text(encoding='utf-8', errors='ignore'), True
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=45) as response:
        html = response.read().decode('utf-8', errors='ignore')
    path.write_text(html, encoding='utf-8')
    return html, False


def paragraphs(html):
    body = re.sub(r'(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', html)
    out = []
    for raw in re.findall(r'(?is)<p[^>]*>(.*?)</p>', body):
        text = re.sub(r'(?s)<[^>]+>', ' ', raw)
        text = (text.replace('&nbsp;', ' ').replace('&rsquo;', "'").replace('&amp;', '&')
                    .replace('&#8217;', "'").replace('&laquo;', '«').replace('&raquo;', '»'))
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) >= 90 and not text.lower().startswith(
                ('notre site utilise', 'en poursuivant', 'gérer', 'accepter', 'ce site')):
            out.append(text)
    return out


def page_name(html):
    """The estate's real name, from its own profile page.

    The listing page pairs a thumbnail's alt text with the nearest preceding
    link, which drifts out of sync on a carousel: slug "domaines-jaboulet" came
    back named "Clos de la Bonnette". The h1 of the profile page is authoritative.
    """
    from html import unescape
    m = re.search(r'(?is)<h1[^>]*>(.*?)</h1>', html)
    if m:
        t = re.sub(r'(?s)<[^>]+>', ' ', m.group(1))
        t = re.sub(r'\s+', ' ', unescape(t).replace('\xa0', ' ')).strip()
        if 2 <= len(t) <= 90:
            return t
    m = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
    if m:
        t = re.sub(r'\s+', ' ', unescape(m.group(1))).strip()
        t = re.sub(r'\s*[-–|]\s*CONDRIEU\s*$', '', t, flags=re.I).strip()
        if 2 <= len(t) <= 90:
            return t
    return None


def run_listings():
    producers, seen = [], set()
    for page in range(1, 19):
        url = BASE + 'page/%d/' % page if page > 1 else BASE
        html, cached = fetch(url, 'list-%02d' % page)
        for m in IMG_RE.finditer(html):
            img, alt = m.group(1), m.group(2).strip()
            head = html[:m.start()]
            links = LINK_RE.findall(head)
            if not links:
                continue
            page_url, slug = links[-1]
            if slug in seen:
                continue
            seen.add(slug)
            producers.append({'slug': slug, 'name': alt or slug, 'directoryURL': page_url,
                              'thumbnailURL': img, 'directoryPage': page,
                              'thumbnailIsPlaceholder': 'placeholder' in img.lower()})
        print('page %2d -> %d producers (%s)' % (page, len(producers),
                                                 'cached' if cached else 'fetched'), flush=True)
        if not cached:
            time.sleep(DELAY)
    (OUTDIR / 'condrieu-directory-thumbnails.json').write_text(
        json.dumps(producers, ensure_ascii=False, indent=1) + '\n')
    print('\ntotal producers with thumbnail info:', len(producers))
    print('real photos:', sum(1 for p in producers if not p['thumbnailIsPlaceholder']))
    print('placeholders:', sum(1 for p in producers if p['thumbnailIsPlaceholder']))


def run_profiles():
    source = json.loads((OUTDIR / 'condrieu-directory-thumbnails.json').read_text())
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else len(source)
    path = OUTDIR / 'condrieu-profiles.json'
    known = {p['slug']: p for p in json.loads(path.read_text())} if path.exists() else {}
    profiles = dict(known)
    fetched = 0
    for i, item in enumerate(source[:limit], 1):
        old = known.get(item['slug'])
        html, cached = '', False
        try:
            html, cached = fetch(item['directoryURL'], 'dir-' + item['slug'])
        except Exception as err:  # noqa: BLE001
            if old:                      # keep whatever we already had
                print('  x %s (kept cached profile) %s' % (item['slug'], err), flush=True)
                continue
            profiles[item['slug']] = {**item, 'error': str(err)}
            print('  x %s %s' % (item['slug'], err), flush=True)
            continue
        paras = paragraphs(html)
        site = own_website(html)
        gallery = gallery_images(html)
        banner = banner_image(html)
        real = page_name(html)
        profiles[item['slug']] = {
            **item,
            'name': real or item['name'],
            'nameFromListing': item['name'],
            'nameSource': item['directoryURL'] if real else None,
            'description': paras[0] if paras else (old or {}).get('description'),
            'descriptionExtra': paras[1:3] or (old or {}).get('descriptionExtra', []),
            'descriptionLanguage': 'fr',
            'descriptionSource': item['directoryURL'],
            'checkedDate': '2026-09-13',
            'website': site or (old or {}).get('website'),
            'websiteSource': item['directoryURL'] if site else (old or {}).get('websiteSource'),
            'bannerImageURL': banner or (old or {}).get('bannerImageURL'),
            'galleryImageURLs': gallery or (old or {}).get('galleryImageURLs', []),
        }
        if not paras:
            print('  ! no paragraph %s' % item['slug'], flush=True)
        # write after every page so a killed run is not lost
        path.write_text(json.dumps(list(profiles.values()), ensure_ascii=False, indent=1) + '\n')
        if not cached:
            fetched += 1
            time.sleep(DELAY)
        if i % 10 == 0:
            w = sum(1 for p in profiles.values() if p.get('website'))
            g = sum(len(p.get('galleryImageURLs') or []) for p in profiles.values())
            print('  .. %d/%d processed, websites=%d, gallery images=%d'
                  % (i, len(source[:limit]), w, g), flush=True)

    allp = list(profiles.values())
    got = sum(1 for p in allp if p.get('description'))
    sites = sum(1 for p in allp if p.get('website'))
    gal = sum(len(p.get('galleryImageURLs') or []) for p in allp)
    print('\nprofiles collected: %d/%d (fetched %d now)' % (got, len(source), fetched))
    print('official websites: %d/%d' % (sites, len(source)))
    print('gallery image URLs: %d' % gal)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'listings'
    run_listings() if mode == 'listings' else run_profiles()
