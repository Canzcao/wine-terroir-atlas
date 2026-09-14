# coding: utf-8
"""Collect wine catalogues (cuvée names) from Condrieu producers' official sites.

Conservative by design:
  - only names read off the producer's own site are recorded;
  - every product keeps its source page, confidence and detected appellation;
  - grapes/vintage percentages are NOT inferred (left empty downstream);
  - sites that fail are recorded with the reason, never fabricated.

Usage: python3 scripts/collect-wine-catalogues.py <profiles.json> <outdir.json>
"""
import json, re, sys, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work' / 'catalogcache'
CACHE.mkdir(parents=True, exist_ok=True)
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}
MAX_LISTING = 4          # wine category/listing pages per site
MAX_PRODUCT = 14         # individual product pages per site
DELAY = 1.6              # seconds between requests to the same host
TIMEOUT = 25

WINE_PAGE_PAT = re.compile(
    r'(nos-vins|nosvins|/vins?\b|nos-cuvees|cuvees|nos-bouteilles|boutique|shop|'
    r'produits|collection|gamme|acheter|catalogue|nos-appellations|e-shop|wines)',
    re.I)
PRODUCT_PAT = re.compile(r'(/product/|/produit/|/products?/|/product-page/|/vin/|/cuvee)', re.I)
JSONLD_PRODUCT = re.compile(
    r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
H1 = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S | re.I)
TITLE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)
WOOCOM_TITLE = re.compile(
    r'woocommerce-loop-product__title[^>]*>(.*?)</', re.S | re.I)
LINK = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)

EXCLUDE_PAT = re.compile(
    r'(bon cadeau|carte cadeau|gift card|gift|ticket|abonnement|panier|livraison|'
    r'visite|degustation|dégustation|sejour|séjour|event|evenement|événement|'
    r'coffret|carton|magnum offer|cart)', re.I)

APPELLATIONS = [
    (re.compile(r'condrieu', re.I), 'Condrieu'),
    (re.compile(r'ch[aâ]teau[- ]grillet|grillet', re.I), 'Château-Grillet'),
    (re.compile(r'c[oô]te[- ]r[oô]tie|cote rotie|la mouline|la landonne|la turque', re.I), 'Côte-Rôtie'),
    (re.compile(r'saint[- ]joseph|saint joseph|st[- ]joseph', re.I), 'Saint-Joseph'),
    (re.compile(r'cornas', re.I), 'Cornas'),
    (re.compile(r'saint[- ]p[eé]ray|st[- ]peray', re.I), 'Saint-Péray'),
    (re.compile(r'hermitage', re.I), 'Hermitage'),
    (re.compile(r'crozes[- ]hermitage|crozes', re.I), 'Crozes-Hermitage'),
    (re.compile(r'collines rhodaniennes|igp|vins de pays|vin de france', re.I), 'IGP/Vin de France'),
    (re.compile(r'chateauneuf|châteauneuf', re.I), 'Châteauneuf-du-Pape'),
    (re.compile(r'saint[- ]p[eé]ray', re.I), 'Saint-Péray'),
    (re.compile(r'tavel', re.I), 'Tavel'),
    (re.compile(r'ligonchin|rhodaniennes', re.I), 'IGP/Vin de France'),
]


def strip_tags(text):
    text = re.sub(r'<[^>]+>', ' ', text or '')
    text = re.sub(r'&nbsp;?', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&#8217;|&rsquo;', "'", text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def norm_name(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def detect_appellations(*texts):
    joined = ' | '.join(t for t in texts if t)
    found = []
    for pat, label in APPELLATIONS:
        if pat.search(joined) and label not in found:
            found.append(label)
    return found


def cache_key(url):
    return hashlib.sha1(url.encode('utf-8')).hexdigest()[:24]


def fetch(url, robots=None, use_cache=True):
    """Fetch a URL with disk cache. robots is a RobotFileParser or None."""
    key = cache_key(url)
    cached = CACHE / (key + '.html')
    meta = CACHE / (key + '.meta.json')
    if use_cache and cached.exists() and meta.exists():
        m = json.loads(meta.read_text())
        if m.get('status') == 200:
            return cached.read_text(errors='replace')
        return None
    try:
        if robots is not None and not robots.can_fetch(HEADERS['User-Agent'], url):
            return None
    except Exception:
        pass
    for attempt in range(3):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT) as r:
                data = r.read().decode('utf-8', errors='replace')
            cached.write_text(data)
            meta.write_text(json.dumps({'status': 200, 'url': url}))
            return data
        except HTTPError as e:
            meta.write_text(json.dumps({'status': e.code, 'url': url}))
            return None
        except Exception:
            if attempt == 2:
                meta.write_text(json.dumps({'status': 'error', 'url': url}))
                return None
            time.sleep(2 * (attempt + 1))
    return None


def get_robots(base):
    rp = RobotFileParser()
    try:
        req = Request(urljoin(base, '/robots.txt'), headers=HEADERS)
        with urlopen(req, timeout=15) as r:
            rp.parse(r.read().decode('utf-8', errors='replace').splitlines())
    except Exception:
        pass
    return rp


def clean_name(name):
    name = strip_tags(name)
    name = re.sub(r'\s*–\s*Les Vins .*$', '', name)
    name = re.sub(r'\s*\|\s*.*$', '', name)          # trailing site title
    name = re.sub(r'\s*[-–|]\s*(Domaine|Cave|Château|Maison|Vignobles|Vidal|Chapoutier).*$', '', name, flags=re.I)
    name = re.sub(r'^\d+\s*[clML]?\.?\s*[-–]\s*', '', name)  # leading volume
    name = re.sub(r'\s+', ' ', name).strip(' -–|·')
    return name.strip()


def extract_products(html, page_url):
    """Return [{name, confidence, how}] found on one page."""
    out, seen = [], set()

    def add(name, conf, how):
        name = clean_name(name)
        if not name or len(name) < 3 or len(name) > 120:
            return
        if EXCLUDE_PAT.search(name):
            return
        key = norm_name(name)
        if not key or key in seen:
            return
        seen.add(key)
        out.append({'name': name, 'confidence': conf, 'how': how})

    # 1. JSON-LD Product entries (most reliable)
    for block in JSONLD_PRODUCT.findall(html):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for d in items:
            if not isinstance(d, dict):
                continue
            if d.get('@type') == 'Product' or (
                    isinstance(d.get('@type'), list) and 'Product' in d.get('@type')):
                name = d.get('name')
                if name:
                    add(name, 'high', 'json-ld Product')
            for g in (d.get('@graph') or []):
                if isinstance(g, dict) and 'Product' in str(g.get('@type', '')) and g.get('name'):
                    add(g['name'], 'high', 'json-ld @graph Product')
    # 2. WooCommerce loop titles on listing pages
    for t in WOOCOM_TITLE.findall(html):
        add(t, 'high', 'woocommerce-loop-title')
    # 3. h1 on product pages
    if PRODUCT_PAT.search(page_url) or WINE_PAGE_PAT.search(page_url):
        for t in H1.findall(html):
            add(t, 'medium', 'h1 on product/wine page')
    # 4. product links' anchor text on listing pages
    for href, text in LINK.findall(html):
        full = urljoin(page_url, href)
        if PRODUCT_PAT.search(full):
            add(text, 'medium', 'product-link anchor')
    return out


def main():
    profiles_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    profiles = json.loads(profiles_path.read_text())
    sites = [(p['slug'], p['name'], p['website']) for p in profiles if p.get('website')]
    results = []
    for i, (slug, pname, website) in enumerate(sites, 1):
        base = website.rstrip('/')
        host = urlparse(base).netloc
        rec = {'slug': slug, 'producer': pname, 'website': base, 'status': None,
               'pagesFetched': 0, 'products': [], 'note': None}
        print('%2d/%d %s' % (i, len(sites), host), flush=True)
        robots = get_robots(base)
        try:
            delay = max(robots.crawl_delay('*') or 0, 0)
        except Exception:
            delay = 0
        delay = max(delay, 1.0)
        html = fetch(base + '/', robots)
        rec['pagesFetched'] += 1
        if not html:
            rec['status'] = 'site_unreachable'
            rec['note'] = 'homepage not retrievable (robots/HTTP error)'
            results.append(rec)
            print('   unreachable', flush=True)
            time.sleep(delay)
            continue
        # gather candidate links from homepage
        listing, products = [], []
        seen_urls = {base + '/', base}
        for href, text in LINK.findall(html):
            full = urljoin(base + '/', href).split('#')[0]
            if not full.startswith(('http://', 'https://')):
                continue
            if urlparse(full).netloc != host:
                continue
            if full in seen_urls:
                continue
            anchor = strip_tags(text)
            if EXCLUDE_PAT.search(full) or EXCLUDE_PAT.search(anchor):
                continue
            if PRODUCT_PAT.search(full):
                products.append(full); seen_urls.add(full)
            elif WINE_PAGE_PAT.search(full) or WINE_PAGE_PAT.search(anchor):
                listing.append(full); seen_urls.add(full)
        listing, products = listing[:MAX_LISTING], products[:MAX_PRODUCT]
        # fetch listing pages, collect more product links from them
        listing_htmls = []
        for lp in listing:
            h = fetch(lp, robots)
            time.sleep(delay)
            rec['pagesFetched'] += 1
            if h:
                listing_htmls.append((lp, h))
                for href, text in LINK.findall(h):
                    full = urljoin(lp, href).split('#')[0]
                    if urlparse(full).netloc == host and full not in seen_urls \
                            and PRODUCT_PAT.search(full) and not EXCLUDE_PAT.search(full):
                        products.append(full); seen_urls.add(full)
        products = products[:MAX_PRODUCT + 6]
        found = []
        for lp, h in listing_htmls:
            found += extract_products(h, lp)
        for pp in products:
            h = fetch(pp, robots)
            time.sleep(delay)
            rec['pagesFetched'] += 1
            if h:
                found += extract_products(h, pp)
        # dedupe across pages, keep best confidence
        best = {}
        for item in found:
            key = norm_name(item['name'])
            if key not in best or item['confidence'] == 'high':
                best.setdefault(key, item)
                if item['confidence'] == 'high':
                    best[key] = item
        items = sorted(best.values(), key=lambda x: x['name'])
        for it in items:
            it['appellations'] = detect_appellations(it['name'], it['how'])
        rec['products'] = items
        rec['status'] = 'ok' if items else 'no_products_detected'
        if not items:
            rec['note'] = ('pages fetched but no product names extracted '
                           '(site may be Flash/JS-only or uses non-standard markup)')
        results.append(rec)
        print('   %d products' % len(items), flush=True)
    out_path.write_text(json.dumps({
        'date': '2026-09-14', 'regionId': 'condrieu',
        'method': 'producer official sites; JSON-LD Product / WooCommerce titles / '
                  'product-page h1 / product-link anchors; appellation read from '
                  'product name; nothing inferred beyond the page',
        'sites': results,
    }, ensure_ascii=False, indent=1) + '\n')
    ok = sum(1 for r in results if r['status'] == 'ok')
    print('sites ok: %d/%d -> %s' % (ok, len(results), out_path))


if __name__ == '__main__':
    main()
