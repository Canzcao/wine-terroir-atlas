# coding: utf-8
"""Collect the images the Site actually needs: winery people AND the wines they make.

User instruction (2026-09-13): "抓取图片时，除了人物之外，还需将酒庄出产的酒作为
抓取目标一并纳入采集范围。" So a producer's official site is crawled for two roles:

  people / estate  ->  vineyard, cellar, team, portrait, landscape photos
  wine             ->  bottle packshots, label artwork, cuvées, magnums

Classification is deliberately conservative and always recorded per image, because
a wrong "this is the bottle of X" claim is worse than an empty field:

  1. url / filename keywords      (bouteille, packshot, etiquette, cuvée, ...)
  2. <img alt> keywords           (the strongest human-supplied signal)
  3. the page it was found on     (/nos-vins, /boutique, /cuvees ... )
  4. geometry after download      (bottle packshots are portrait, ratio >= 1.8)
  5. alpha channel               (product cut-outs are transparent PNG/WebP)

No watermark is ever removed, nothing is upscaled, and every image keeps source
page, direct URL, retrieval time, byte size, SHA-256, real dimensions and the
reason it was classified the way it was, so any takedown request is actionable
per image.

Usage:
  python3 scripts/collect-wine-images.py <profiles.json> <outdir> [--only slug,slug]
"""
import hashlib
import html as html_lib, io, json, os, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, quote
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
PAGE_CACHE = ROOT / 'work' / 'pagecache'
IMGDIR_CACHE = ROOT / 'work' / 'imgcache'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}
IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.avif')
MIN_SIDE = 250          # reject menu icons, bullets, tracking pixels
# Per-site image budget. Default 26 keeps the bundle reviewable; override with
# WINE_MAX_PER_SITE when a period covers many more producers than usual and the
# downstream visual-review bandwidth is the binding constraint.
MAX_PER_SITE = int(os.environ.get('WINE_MAX_PER_SITE', '26'))
PER_DOMAIN_DELAY = 2.0  # slower when robots.txt does not state a crawl delay

# Date stamped on each image's retrievedAt and on the manifest header.
# This used to be the literal '2026-09-13', which silently back-dated every
# later run (and every visual review hung off the manifest header). Read the
# clock instead; override with WINE_RUN_DATE for a re-run of a past period.
RUN_DATE = os.environ.get('WINE_RUN_DATE') or date.today().isoformat()

# ---------------------------------------------------------------- vocabularies
# Tokens are matched as whole words (or explicit prefixes), never as raw
# substrings: "coterotielevet" must not be read as the word "eleve".
WINE_TOKEN_EXACT = {
    'bouteille', 'bouteilles', 'bottle', 'bottles', 'packshot', 'packshots',
    'flacon', 'flacons', 'magnum', 'magnums', 'jeroboam', 'mathusalem',
    'etiquette', 'etiquettes', 'label', 'labels', 'habillage', 'bouchon',
    'capsule', 'millesime', 'millesimes', 'vintage', 'caisse', 'coffret',
    'coffrets', 'carton', 'cuvaison', 'grandcru', 'grands', 'cru',
}
WINE_TOKEN_PREFIX = ('bouteil', 'packshot', 'etiquet', 'millesim', 'magnum',
                     'flacon', 'habillage', 'coffret', 'jeroboam')
# words that only say "this page is about wine", never "this is a bottle"
WINE_CONTEXT = {
    'vin', 'vins', 'wine', 'wines', 'cuvee', 'cuvees', 'condrieu', 'viognier',
    'rouge', 'blanc', 'blancs', 'rouges', 'rose', 'roses', 'degustation',
    'degustations', 'tasting', 'boutique', 'shop', 'produit', 'produits',
    'product', 'products', 'collection', 'gamme', 'acheter', 'commande',
    'panier', 'catalogue', 'verre', 'verres', 'glass', 'glasses', 'barrique',
    'barriques', 'tonneau', 'tonneaux', 'foudre', 'chai', 'chais', 'cave',
    'caveau', 'vendange', 'vendanges', 'grappe', 'grappes', 'raisin', 'raisins',
    'terroir', 'terroirs', 'vigne', 'vignes', 'vignoble', 'vignobles', 'coteau',
    'coteaux', 'sol', 'sols', 'granite', 'granit', 'murette', 'murettes',
    'clos', 'chateau', 'domaine', 'panorama', 'paysage', 'drone', 'aerial',
}
WINE_PAGES = (
    'nos-vins', 'nosvins', 'vins', 'wine', 'wines', 'cuvees', 'boutique', 'shop',
    'produits', 'collection', 'gamme', 'condrieu', 'viognier', 'appellation',
    'chais', 'cave', 'acheter', 'catalogue', 'fiche-produit', 'nos-produits',
)
NEGATIVE_TOKENS = {
    'logo', 'logos', 'favicon', 'sprite', 'placeholder', 'avatar', 'drapeau',
    'flag', 'panier', 'cart', 'visa', 'mastercard', 'paypal', 'arrow', 'fleche',
    'chevron', 'burger', 'menu', 'search', 'loupe', 'loading', 'spinner',
    'spacer', 'blank', 'pixel', 'tracker', 'badge', 'icone', 'icon', 'icons',
    'facebook', 'instagram', 'twitter', 'linkedin', 'youtube', 'tiktok',
    'pinterest', 'whatsapp', 'google', 'apple', 'cookie', 'rgpd', 'cnil',
    'captcha', 'recaptcha', 'webfont', 'font', 'swiper', 'bandeau', 'footer',
    'header', 'breadcrumb', 'preloader', 'loader',
}
PEOPLE_TOKENS = {
    'portrait', 'portraits', 'equipe', 'team', 'vigneron', 'vignerons',
    'viticulteur', 'famille', 'family', 'generation', 'visage', 'staff',
    'people', 'humain', 'main', 'mains', 'hand', 'hands', 'person', 'personne',
}
# stock-photo library naming: long descriptive hyphenated English slugs
STOCK_MARKERS = {
    'background', 'front', 'close', 'flat', 'lay', 'mockup', 'holding',
    'overturned', 'wooden', 'board', 'walnut', 'cheese', 'dark', 'copy',
    'space', 'isolated', 'shutterstock', 'adobe', 'stock', 'freepik',
    'pexels', 'unsplash', 'istock', 'depositphotos', 'gettyimages',
}
# appellation words so a Côte-Rôtie bottle is never filed as a Condrieu one
APPELLATION_WORDS = {
    'condrieu': 'Condrieu',
    'coterotie': 'Côte-Rôtie', 'cote': 'Côte-Rôtie', 'rotie': 'Côte-Rôtie',
    'côte': 'Côte-Rôtie', 'rôtie': 'Côte-Rôtie', 'brune': 'Côte-Rôtie',
    'blonde': 'Côte-Rôtie',
    'saintjoseph': 'Saint-Joseph', 'joseph': 'Saint-Joseph',
    'crozes': 'Crozes-Hermitage', 'hermitage': 'Hermitage',
    'saintperay': 'Saint-Péray', 'peray': 'Saint-Péray',
    'cornas': 'Cornas', 'chateaugrillet': 'Château-Grillet',
    'grillet': 'Château-Grillet',
    'vdp': 'Vin de Pays', 'igp': 'IGP', 'vins': None,
}
APPELLATION_HEADS = ('coterotie', 'côte-rôtie', 'cote-rotie', 'condrieu',
                     'saint-joseph', 'crozes', 'hermitage', 'cornas', 'grillet',
                     'saint-peray', 'saintperay')


def strip_accents(text):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', text or '')
                   if unicodedata.category(c) != 'Mn')


def tokenize(*texts):
    """Split urls / filenames / alt text into lowercase accent-free word tokens."""
    joined = ' '.join(t or '' for t in texts)
    joined = joined.replace('%20', ' ').replace('_', ' ').replace('+', ' ')
    joined = strip_accents(joined.lower())
    return [t for t in re.split(r'[^0-9a-z]+', joined) if t]


def has_token(tokens, exact=(), prefix=()):
    for t in tokens:
        if t in exact:
            return t
        for p in prefix:
            if t.startswith(p) and len(t) >= len(p):
                return t
    return None


def brand_tokens(item):
    """The estate's own name is never a wine keyword."""
    out = set()
    for src in (item.get('name') or '', item.get('slug') or '',
                urlparse(item.get('website') or '').netloc):
        for t in re.split(r'[^0-9a-zà-ÿ]+', src.lower()):
            if len(t) >= 3:
                out.add(t)
    return out


def looks_like_stock(tokens, alt):
    """Long descriptive English stock slugs, e.g.
    front-view-wine-glasses-fresh-grapes-walnuts-yellow-cheese-..."""
    if alt and len(alt.split()) >= 4:
        return True
    if len(tokens) >= 5 and not any(c in tokens for c in ('condrieu', 'viognier')):
        hits = sum(1 for t in tokens if t in STOCK_MARKERS)
        if hits >= 2:
            return True
    return False


def appellation_of(tokens, alt):
    hay = ' '.join(tokens) + ' ' + (alt or '').lower()
    for head in APPELLATION_HEADS:
        if head.replace('-', ' ') in hay.replace('-', ' ') or head in hay:
            for k, v in APPELLATION_WORDS.items():
                if v and (k in hay.replace('-', ' ')):
                    return v
            return head.title()
    return None


def log(*a):
    print(*a, flush=True)


# --------------------------------------------------------------------- fetch
_ROBOTS = {}
_LOCK = threading.RLock()      # guards the robots cache and the manifest file


def _atomic_write(path, data):
    """Write via a temp file so a concurrent reader never sees a half file."""
    tmp = path.with_suffix(path.suffix + '.tmp%d' % os.getpid())
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
    os.replace(tmp, path)


def robots_for(base):
    """(allowed, crawl_delay) for a domain, honouring robots.txt."""
    host = urlparse(base).netloc
    with _LOCK:
        if host in _ROBOTS:
            return _ROBOTS[host]
    rp, delay = RobotFileParser(), None
    try:
        raw = _read(base.rstrip('/') + '/robots.txt', timeout=20).decode('utf-8', 'ignore')
        rp.parse(raw.splitlines())
        m = re.search(r'(?im)^\s*crawl-delay\s*:\s*(\d+(?:\.\d+)?)', raw)
        if m:
            delay = float(m.group(1))
    except Exception:                                    # no robots.txt -> allow
        rp = None
    with _LOCK:
        _ROBOTS[host] = (rp, delay)
    return rp, delay


# A candidate that still holds a template token or markup junk is not a URL.
# These come from Shopify/Liquid templates (`/pages/{{img}}`), srcset strings
# that were not split (`a.png 720w, b.png 960w`), and lazy-load placeholders.
JUNK_IN_URL = ('{{', '}}', '{%', '%7B%7B', '{width}', '{height}', '{size}',
               '<', '>', '"', "'", '\\', '`')

# Narrow-in on the failure modes seen on real estate sites: unencoded spaces
# (Gardine), accented filenames (Cuilleron/Villard/Pierre Amadieu), and
# `image, image` pairs left over from srcset.
def safe_url(url):
    """Percent-encode the parts of a URL that urllib refuses to send."""
    if not url:
        return url
    url = url.strip()
    try:
        pu = urlparse(url)
    except ValueError:
        return None
    if not pu.scheme or not pu.netloc:
        return None
    # quote with a safe set that keeps path separators and existing escapes
    path = quote(pu.path, safe="/%:@&=+$,-_.!~*'()")
    query = quote(pu.query, safe="=&%:@+$,;/?-_.!~*'()")
    return urlunparse((pu.scheme, pu.netloc, path, pu.params, query, pu.fragment))


def is_fetchable_url(u):
    """Reject template placeholders, markup junk and multi-URL strings."""
    if not u:
        return False
    low = u.lower()
    if any(j.lower() in low for j in JUNK_IN_URL):
        return False
    if ' ' in u or '\n' in u or '\t' in u:
        return False
    if not low.split('?')[0].endswith(IMG_EXT):
        return False
    try:
        pu = urlparse(safe_url(u) or '')
    except ValueError:
        return False
    return bool(pu.netloc) and pu.scheme in ('http', 'https')


def _read(url, timeout=40, referer=None):
    """Fetch bytes, repairing spaces/accents and retrying http->https.

    Real-world estate sites fail here for boring reasons: a path with a literal
    space, an accented filename, or a broken `http://` vhost. All three are
    recoverable, so they are retried instead of being recorded as "no image".
    """
    urls, seen = [], set()
    for cand in (url, safe_url(url)):
        if cand and cand not in seen:
            seen.add(cand)
            urls.append(cand)
    if url.lower().startswith('http://'):
        https = 'https://' + url[len('http://'):]
        if https not in seen:
            urls.append(https)
    last = None
    for cand in urls:
        headers = dict(HEADERS)
        if referer:
            headers['Referer'] = referer
        try:
            req = Request(cand, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as err:  # noqa: BLE001
            last = err
    raise last


def fetch_html(url, key, delay=None, referer=None):
    """Cached HTML fetch; returns (html, from_cache)."""
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    path = PAGE_CACHE / (key + '.html')
    if path.exists():
        return path.read_text(encoding='utf-8', errors='ignore'), True
    html = _read(url, referer=referer).decode('utf-8', errors='ignore')
    _atomic_write(path, html)
    if delay:
        time.sleep(delay)
    return html, False


def fetch_bytes(url, referer=None):
    IMGDIR_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest() + Path(urlparse(url).path).suffix
    path = IMGDIR_CACHE / key
    if path.exists():
        return path.read_bytes()
    raw = _read(url, referer=referer)
    _atomic_write(path, raw)
    return raw


# ------------------------------------------------------------ page discovery
def _core_host(host):
    """`www.famillepierregaillard.com:80` -> `famillepierregaillard.com`"""
    return (host or '').lower().split('@')[-1].split(':')[0].replace('www.', '')


def _lcs_suffix(a, b):
    """(longest common substring length, whether it ends both strings)."""
    best, best_end_a, best_end_b = 0, 0, 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best, best_end_a, best_end_b = cur[j], i, j
        prev = cur
    suffix = (best and best_end_a == len(a) and best_end_b == len(b))
    return best, suffix


def hosts_related(a, b):
    """Do two hostnames look like the same estate's old and new domain?

    Domain migrations are common and they break naive "same netloc" link
    filtering: `domainespierregaillard.com` now serves a shell while the content
    lives on `famillepierregaillard.com`, and `domainecheze.com` points at
    `louischeze.com`. Sharing a long brand word is the signal.

    Guard rails: the shared run must be reasonably long, and a short run only
    counts when it ends both names (the brand word is the tail in these cases).
    """
    ca, cb = _core_host(a), _core_host(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    flat_a, flat_b = ca.replace('.', ''), cb.replace('.', '')
    n, suffix = _lcs_suffix(flat_a, flat_b)
    if n >= 6:
        return True
    return n >= 4 and suffix


def wine_page_links(html, base):
    """Internal links whose URL or anchor text suggests a wines/products page."""
    base_host = urlparse(base).netloc
    out, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href, text = html_lib.unescape(m.group(1)), re.sub(r'<[^>]+>', ' ', m.group(2))
        text = re.sub(r'\s+', ' ', text).strip().lower()
        url = urljoin(base, href)
        pu = urlparse(url)
        if _core_host(pu.netloc) != _core_host(base_host) \
                and not hosts_related(base_host, pu.netloc):
            continue
        if any(url.lower().endswith(e) for e in IMG_EXT + ('.pdf', '.zip')):
            continue
        hay = (pu.path + ' ' + text).lower()
        if not any(k in hay for k in WINE_PAGES):
            continue
        clean = urlunparse(pu._replace(query='', fragment='')).rstrip('/')
        if clean in seen or clean.rstrip('/') == base.rstrip('/'):
            continue
        seen.add(clean)
        out.append(clean)
    return out[:4]


def page_images(html, base):
    """[(url, alt, srcset)] candidates from <img>, srcset, og:image and CSS urls."""
    found = []

    def add(u, alt=''):
        u = html_lib.unescape((u or '').strip())
        if not u:
            return
        # A srcset-like string that never got split ("a.png 720w, b.png 960w")
        # used to be queued as one bogus URL; split it and keep the first token
        # of each part ("Tradition-278x540.png 720w" -> "Tradition-278x540.png").
        parts = [u] if ',' not in u else [p for p in u.split(',')]
        for part in parts:
            p = part.strip().split(' ')[0].split('\t')[0]
            if not p:
                continue
            cand = urljoin(base, p)
            if is_fetchable_url(cand):
                found.append((cand, alt))

    for m in re.finditer(r'<img\b[^>]*>', html, re.I):
        tag = m.group(0)
        alt = ''
        am = re.search(r'alt=["\']([^"\']*)["\']', tag, re.I)
        if am:
            alt = am.group(1).strip()
        srcs = re.findall(r'(?:data-)?(?:src|lazy-src|data-lazy-src|data-original)=["\']([^"\']+)["\']',
                          tag, re.I)
        for s in srcs:
            add(s, alt)
    for m in re.finditer(r'srcset=["\']([^"\']+)["\']', html, re.I):
        for part in m.group(1).split(','):
            u = part.strip().split(' ')[0]
            if u.lower().split('?')[0].endswith(IMG_EXT):
                add(u)
    for m in re.finditer(r'content=["\'](https?://[^"\']+\.(?:jpe?g|png|webp|avif))["\']', html, re.I):
        add(m.group(1))
    for m in re.finditer(r'url\(\s*["\']?(https?://[^"\')\s]+\.(?:jpe?g|png|webp|avif))["\']?\s*\)',
                         html, re.I):
        add(m.group(1))

    out, seen = [], set()
    for url, alt in found:
        clean = urlunparse(urlparse(url)._replace(query=''))
        if clean in seen:
            continue
        seen.add(clean)
        low = clean.lower()
        if low.split('?')[0].endswith('.svg'):
            continue
        if has_token(tokenize(urlparse(clean).path), NEGATIVE_TOKENS):
            continue
        out.append((clean, alt))
    return out


def derive_full_size(url):
    """WordPress/Shopify style -WxH thumbnails -> the original file."""
    stem, dot, ext = url.rpartition('.')
    stripped = re.sub(r'-\d{2,4}x\d{2,4}$', '', stem)
    if stripped != stem:
        return stripped + dot + ext
    stripped = re.sub(r'_\d{2,4}x\d{2,4}$', '', stem)
    if stripped != stem:
        return stripped + dot + ext
    return None


# ------------------------------------------------------------- classification
def score_image(url, alt, page, w, h, alpha, brand, wine_names):
    """Return (role, confidence, attribution, appellation, reasons[]).

    Nothing is overclaimed: a generic stock bottle on a producer's site stays
    `wine-photo / stock-or-generic`, and a bottle whose label reads Côte-Rôtie
    is tagged with that appellation instead of being filed as a Condrieu wine.
    """
    path_tokens = tokenize(urlparse(url).path)
    alt_tokens = tokenize(alt)
    page_tokens = tokenize(urlparse(page).path)
    tokens = [t for t in path_tokens if t not in brand]
    reasons = []

    strong = has_token(tokens, WINE_TOKEN_EXACT, WINE_TOKEN_PREFIX)
    alt_strong = has_token(alt_tokens, WINE_TOKEN_EXACT, WINE_TOKEN_PREFIX)
    context = has_token(tokens + page_tokens, WINE_CONTEXT)
    named = [n for n in wine_names if n and n in ' '.join(tokens + alt_tokens)]
    appellation = appellation_of(tokens + alt_tokens, alt)
    stock = looks_like_stock(tokens, alt)

    if strong:
        reasons.append('文件名含酒瓶/标签词“%s”' % strong)
    if alt_strong:
        reasons.append('alt 文本含酒瓶/标签词“%s”' % alt_strong)
    if named:
        reasons.append('文件名或 alt 命中站点酒款名：%s' % ', '.join(sorted(set(named))[:3]))
    if context:
        reasons.append('出现在含“%s”的页面/路径' % context)
    if alpha:
        reasons.append('带透明通道，符合去底产品图')
    ratio = (h / w) if (w and h) else 0
    if ratio >= 1.8:
        reasons.append('竖构图比例 %.2f' % ratio)
    if appellation:
        reasons.append('出现产区词，判定为 %s' % appellation)
    if stock:
        reasons.append('文件名/alt 符合图库套图命名，疑为通用素材')

    bottle_shape = strong or alt_strong or (named and (alpha or ratio >= 1.4))
    label_word = has_token(tokens + alt_tokens, ('label', 'labels', 'etiquette',
                                                 'etiquettes', 'habillage'))

    # 1. the filename or alt names a cuvée of this estate -> it is their wine
    if named and (bottle_shape or appellation or alpha):
        reasons.append('命中本站酒款名，归为本庄酒款')
        return ('wine-label' if label_word else 'wine-bottle', 'high',
                'own-wine', appellation, reasons)

    # 2. a stock slug such as front-view-wine-glasses-... is never their bottle
    if stock and not (strong or alt_strong):
        reasons.append('判为通用素材，不作为本庄酒款图')
        return ('wine-photo', 'medium', 'stock-or-generic', appellation, reasons)

    # 3. explicit bottle / label wording anywhere -> a bottle, owner unproven
    if strong or alt_strong:
        reasons.append('关键词指向酒瓶，但未命中具体酒款名，所有权待核')
        return ('wine-label' if label_word else 'wine-bottle',
                'high' if appellation else 'medium',
                'likely-own' if appellation else 'unverified', appellation, reasons)

    # 4. transparent cut-out with only the estate name as alt: could be the
    #    logo, could be the packshot. Hand it to the visual pass, never guess.
    if alpha and not strong and not alt_strong:
        if alt and all(t in brand or len(t) <= 2 for t in alt_tokens):
            reasons.append('透明底、alt 仅含酒庄名：logo 与去底酒瓶无法靠文件名区分，转人工复核')
        else:
            reasons.append('透明底去背图，疑为产品图，转人工复核')
        return ('producer-logo-or-product', 'low', 'unverified', appellation, reasons)

    people = has_token(tokens, PEOPLE_TOKENS)
    if people:
        reasons.append('人物/团队关键词“%s”' % people)
        return ('producer-people', 'high', 'not-a-wine', None, reasons)
    if context:
        reasons.append('庄园/风土语境')
        return ('producer-estate', 'medium' if not appellation else 'high',
                'not-a-wine', appellation, reasons)
    return ('producer-site', 'low', 'not-a-wine', appellation, reasons)


def needs_review(url, alt, page, w, h, alpha, role):
    """A real bottle can hide behind a name with no keyword at all
    (`Vignobles-Levet1.png` is exactly that), so product-shaped images on a
    wines page are queued for an agent visual pass instead of being dropped."""
    if role.startswith('wine-') and role != 'wine-photo':
        return False
    if role in ('producer-logo-or-product',):
        return True
    if role == 'producer-logo':
        return False
    page_tokens = set(tokenize(urlparse(page).path))
    on_wine_page = bool(page_tokens & WINE_PAGE_TOKENS)
    shape = alpha or ((h / w) >= 1.35 if w else False)
    appellation_hit = bool(appellation_of(tokenize(urlparse(url).path), alt))
    return bool(on_wine_page and (shape or appellation_hit))


WINE_PAGE_TOKENS = {t for p in WINE_PAGES for t in tokenize(p)}


def site_variants(url):
    """Some estates have a broken HTTPS or www host; try the usual siblings."""
    pu = urlparse(url)
    host = pu.netloc
    bare = host.replace('www.', '')
    out = [url]
    for h in (bare, 'www.' + bare):
        for scheme in ('https', 'http'):
            cand = urlunparse((scheme, h, pu.path or '/', '', '', ''))
            if cand not in out:
                out.append(cand)
    return out


def open_site(url, key, delay):
    """Fetch the estate's homepage, falling back across scheme/www variants."""
    last = None
    for cand in site_variants(url):
        try:
            return fetch_html(cand, key, delay, referer=cand), cand
        except Exception as err:  # noqa: BLE001
            last = err
    raise last


def dimensions_and_alpha(raw):
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        w, h = im.width, im.height
        alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        if im.mode == 'RGBA':
            alpha = im.getextrema()[3][0] < 255
    return w, h, alpha


def strip_accents(text):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', text or '')
                   if unicodedata.category(c) != 'Mn')


GENERIC_NAME_TOKENS = {
    # page chrome and navigation
    'accueil', 'bienvenue', 'actualite', 'actualites', 'contact', 'mentions',
    'legales', 'legal', 'confidentialite', 'cookies', 'plan', 'site', 'page',
    'home', 'menu', 'plus', 'tous', 'toutes', 'tout', 'voir', 'lire', 'suite',
    'partager', 'partage', 'retour', 'next', 'prev', 'suivant', 'precedent',
    'newsletter', 'abonnement', 'inscription', 'connexion',
    # estate talk that is not a cuvée name
    'vigneron', 'vignerons', 'viticulteur', 'viticulteurs', 'exploitant',
    'producteur', 'producteurs', 'domaine', 'domaines', 'famille', 'equipe',
    'histoire', 'savoir', 'faire', 'terroir', 'terroirs', 'vignoble',
    'vignobles', 'appellation', 'appellations', 'degustation', 'degustations',
    'cuvee', 'cuvees', 'gamme', 'gammes', 'collection', 'produit', 'produits',
    'boutique', 'acheter', 'commande', 'livraison', 'contactez', 'decouvrir',
    'decouvrez', 'decouverte', 'notre', 'notres', 'nos', 'philosophie',
    'methode', 'methodes', 'travail', 'travaux', 'vendange', 'vendanges',
    'millesime', 'millesimes', 'vin', 'vins', 'wine', 'wines', 'rouge',
    'rouges', 'blanc', 'blancs', 'rose', 'roses', 'sec', 'doux', 'moelleux',
    'brut', 'douceur', 'exception', 'exceptionnel', 'experience', 'guide',
    'faites', 'explorez', 'prestigieux', 'inoubliable', 'unique', 'uniques',
    'purete', 'heritage', 'generation', 'generations', 'transmis', 'trois',
    'travers', 'rsquo', 'raisonnee', 'viticulture', 'vinicole', 'quelques',
    'autres', 'nouvel', 'historique', 'chiffres', 'valeurs', 'passion',
    'culture', 'excellence', 'essort', 'collines', 'terrasses', 'bouquet',
    'portrait', 'galerie', 'video', 'photos', 'album', 'presse', 'espace',
    'professionnels', 'particuliers', 'conditions', 'generales', 'vente',
    # place names in the appellation that are not cuvée names
    'ampuis', 'chavanay', 'verin', 'verlieu', 'michel', 'malleval',
    'peaugres', 'limony', 'serrieres', 'condrieu', 'viognier', 'cote',
    'cotes', 'rotie', 'rhone', 'vallee', 'granit', 'granite', 'granits',
    'gneiss', 'micaschiste', 'archean', 'region', 'regions', 'france',
    'francais', 'francaise', 'rhodaniennes', 'rhodanien', 'vania',
}


def wine_name_tokens(html, brand):
    """Distinctive words from headings / product titles, i.e. cuvée names.

    Used to decide whether a filename refers to a specific wine of the estate
    (`own-wine`) rather than an unattributed bottle shot (`likely-own`).
    A token only qualifies when it survives the generic stoplist, so page
    chrome such as "Vigneron à Condrieu" can never masquerade as a cuvée.
    """
    names = set()
    for m in re.finditer(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.I | re.S):
        t = re.sub(r'<[^>]+>', ' ', m.group(1))
        t = re.sub(r'\s+', ' ', t).strip()
        if 3 <= len(t) <= 80:
            names.add(t)
    for m in re.finditer(r'<title[^>]*>(.*?)</title>', html, re.I | re.S):
        names.add(re.sub(r'\s+', ' ', m.group(1)).strip())
    for m in re.finditer(r'class="[^"]*(?:product|produit|cuvee|cuv)[^"]*"[^>]*>([^<]{3,80})<',
                         html, re.I):
        names.add(m.group(1).strip())

    out = set()
    for n in names:
        parts = [strip_accents(t) for t in re.split(r'[^0-9A-Za-zà-ÿ]+', n.lower()) if t]
        # a cuvée title is a short label, not a marketing sentence
        if len(parts) > 4:
            continue
        for t in parts:
            if len(t) < 5 or len(t) > 22:
                continue
            if t in brand or t in GENERIC_NAME_TOKENS or t in NEGATIVE_TOKENS:
                continue
            if t in WINE_CONTEXT or t in PEOPLE_TOKENS:
                continue
            out.add(t)
    return out


def cuvee_tokens_from_paths(urls, brand):
    """Cuvée names are also readable from product-detail URLs, e.g.
    /portfolio-item/condrieu-grain-d-emotion -> grain, emotion."""
    out = set()
    for u in urls:
        path = urlparse(u).path.lower()
        if not any(k in path for k in ('portfolio', 'produit', 'product', 'cuvee',
                                       'nos-vins', 'boutique', 'shop')):
            continue
        for t in re.split(r'[^0-9a-zà-ÿ]+', path):
            t = strip_accents(t)
            if 5 <= len(t) <= 22 and t not in brand and t not in GENERIC_NAME_TOKENS \
                    and t not in NEGATIVE_TOKENS and t not in WINE_CONTEXT:
                out.add(t)
    return out


# --------------------------------------------------------------------- main
def process(item, i, total):
    """Collect one producer: directory gallery first, then its own website.

    Runs in a worker thread; one producer is one unit of work so a slow or dead
    site never blocks the others.
    """
    slug, site = item['slug'], item.get('website')
    entry = manifest.get(slug) or {
        'slug': slug, 'name': item['name'], 'wineryId': item.get('wineryId'),
        'website': site, 'images': [], 'failures': [], 'pagesVisited': [],
    }
    entry['website'] = site or entry.get('website')
    entry['images'] = entry.get('images') or []
    entry['failures'] = entry.get('failures') or []
    entry['pagesVisited'] = entry.get('pagesVisited') or []
    ddir = outdir / slug
    ddir.mkdir(parents=True, exist_ok=True)
    brand = brand_tokens(item)
    wine_tokens = set()

    def record(url, alt, page, raw, w, h, alpha, source_name, rights):
        role, conf, attr, appel, reasons = score_image(
            url, alt, page, w, h, alpha, brand, wine_tokens)
        review = needs_review(url, alt, page, w, h, alpha, role)
        if review:
            reasons.append('产品形状或去底图，列入人工视觉复核候选')
        name = re.sub(r'[^A-Za-z0-9._-]', '_', Path(urlparse(url).path).name)
        target = ddir / ('%02d-%s' % (len(entry['images']) + 1, name))
        target.write_bytes(raw)
        entry['images'].append({
            'file': target.name, 'relativePath': str(target.relative_to(outdir)),
            'role': role, 'confidence': conf, 'attribution': attr,
            'appellation': appel,
            'reviewAs': 'possible-wine' if review else None,
            'classificationMethod': 'heuristic',
            'reasons': reasons, 'altText': alt or None,
            'sourceName': source_name, 'sourcePage': page, 'directURL': url,
            'width': w, 'height': h, 'aspect': round(h / w, 2) if w else None,
            'hasAlpha': alpha, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'retrievedAt': RUN_DATE,
            'rights': rights, 'watermark': '未去水印；未放大；仅原尺寸保存',
        })
        return role

    DIR_RIGHTS = ('来源 vin-condrieu.fr 公开页面；未标注许可。按站点方 2026-09-13 决定：'
                  '官网图片可下载使用，站点内容将标注“均为合作上传，如侵权可联系删除”。')
    SITE_RIGHTS = ('来源酒庄官网公开图片；未标注许可。按站点方 2026-09-13 决定：'
                   '官网图片可下载使用，站点内容将标注“均为合作上传，如侵权可联系删除”。')

    # -- phase 0: the association directory page. Its banner and its lightbox
    #    gallery (URLs hidden in generated CSS) are this estate's own photos,
    #    and re-reading them from cache costs no extra request.
    have_dir = {g.get('directURL') for g in entry['images']}
    cands0 = []
    if item.get('bannerImageURL'):
        cands0.append((item['bannerImageURL'], item.get('name') or ''))
    for u in (item.get('galleryImageURLs') or []):
        cands0.append((u, item.get('name') or ''))
    for u, alt in cands0:
        if u in have_dir:
            continue
        try:
            raw = fetch_bytes(u)
        except Exception as err:  # noqa: BLE001
            entry['failures'].append({'url': u, 'error': str(err)})
            continue
        if len(raw) < 6000:
            continue
        try:
            w, h, alpha = dimensions_and_alpha(raw)
        except Exception:  # noqa: BLE001
            continue
        if not w or min(w, h) < MIN_SIDE:
            continue
        role = record(u, alt, item['directoryURL'], raw, w, h, alpha,
                      'Condrieu 产区协会名录', DIR_RIGHTS)
        if role in ('producer-site', 'producer-logo-or-product'):
            entry['images'][-1]['role'] = 'producer-people'
            entry['images'][-1]['confidence'] = 'medium'
            entry['images'][-1]['reasons'].append(
                '来自协会名录画廊，文件名未见风土/酒瓶线索，按酒庄人物照归档')

    if not entry['website']:
        entry['note'] = '协会名录未给出官网，仅采到名录页人物/庄园图'
        manifest[slug] = entry
        save()
        log('%3d/%d %-38s no site, directory images=%d'
            % (i, total, item['name'][:38], len(entry['images'])))
        return entry

    # -- robots.txt: obey it, and obey any crawl delay the estate asks for
    rp, stated = robots_for(entry['website'])
    delay = stated if stated else PER_DOMAIN_DELAY
    if rp is not None and not rp.can_fetch(HEADERS['User-Agent'], entry['website']):
        entry['note'] = 'robots.txt 不允许抓取首页'
        manifest[slug] = entry
        save()
        log('%3d/%d %-38s robots disallow' % (i, total, item['name'][:38]))
        return entry

    wine_tokens = set()
    pages = []
    try:
        (home, cached), live = open_site(entry['website'], 'wsite-' + slug, delay)
        entry['websiteLive'] = live
        entry['pagesVisited'].append(live)
        wine_tokens |= wine_name_tokens(home, brand)
        # Pages may now legitimately sit on a sibling host (estate migration),
        # so robots.txt is consulted for whichever host each page lives on.
        def allowed(u):
            pu = urlparse(u)
            if pu.netloc == urlparse(live).netloc:
                local = rp
            else:
                local, _ = robots_for('%s://%s' % (pu.scheme, pu.netloc))
            return local is None or local.can_fetch(HEADERS['User-Agent'], u)

        for link in wine_page_links(home, live):
            if allowed(link):
                pages.append(link)
        # a caller may name pages the generic link rules would miss (estate,
        # commitments, contact) - they carry the people and terroir pictures
        for extra in (item.get('extraPages') or []):
            u = extra if extra.startswith('http') else urljoin(live, extra)
            if u not in pages and allowed(u):
                pages.append(u)
    except Exception as err:  # noqa: BLE001
        entry['failures'].append({'url': entry['website'],
                                  'error': '%s: %s' % (type(err).__name__, err)})
        manifest[slug] = entry
        save()
        log('%3d/%d %-38s HOME FAIL %s' % (i, total, item['name'][:38], err))
        return entry

    # -- the estate's drinks pages: cuvée names and candidate images
    cands = []
    for url in pages:
        try:
            html, _ = fetch_html(
                url, 'wsite-%s-%s' % (slug,
                                      re.sub(r'\W+', '-', urlparse(url).path)[-40:] or 'x'),
                delay, referer=live)
            entry['pagesVisited'].append(url)
            wine_tokens |= wine_name_tokens(html, brand)
            for u, alt in page_images(html, url):
                cands.append((u, alt, url))
        except Exception as err:  # noqa: BLE001
            entry['failures'].append({'url': url, 'error': str(err)})
    for u, alt in page_images(home, live):
        cands.append((u, alt, live))
    wine_tokens |= cuvee_tokens_from_paths(pages + [live], brand)
    entry['wineNameTokens'] = sorted(wine_tokens)[:40]

    seen, ordered = set(), []
    for u, alt, page in cands:
        key = re.sub(r'-\d{2,4}x\d{2,4}(?=\.)', '', u.lower())
        if key in seen:
            continue
        seen.add(key)
        ordered.append((u, alt, page))

    got = 0
    for u, alt, page in ordered:
        if got >= MAX_PER_SITE:
            break
        full = derive_full_size(u) or u
        try:
            raw = fetch_bytes(full, referer=page)
        except Exception as err:  # noqa: BLE001
            try:
                raw, full = fetch_bytes(u, referer=page), u
            except Exception:  # noqa: BLE001
                entry['failures'].append({'url': full, 'error': str(err)})
                continue
        if len(raw) < 6000:
            continue
        try:
            w, h, alpha = dimensions_and_alpha(raw)
        except Exception:  # noqa: BLE001
            continue
        if not w or min(w, h) < MIN_SIDE:
            continue
        record(full, alt, page, raw, w, h, alpha,
               '酒庄官网 ' + (urlparse(page).netloc or ''), SITE_RIGHTS)
        got += 1
        time.sleep(0.3)

    manifest[slug] = entry
    save()
    wines = sum(1 for g in entry['images'] if g['role'].startswith('wine-'))
    own = sum(1 for g in entry['images'] if g.get('attribution') == 'own-wine')
    log('%3d/%d %-38s images=%-3d wines=%-3d own=%-3d pages=%d' % (
        i, total, item['name'][:38], len(entry['images']), wines, own,
        len(entry['pagesVisited'])))
    return entry


def main():
    global profiles, outdir, manifest, manifest_path, save
    profiles = json.loads(Path(sys.argv[1]).read_text())
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
        profiles = [p for p in profiles if p['slug'] in only]

    manifest_path = outdir / 'wine-image-manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest = {e['slug']: e for e in (manifest.get('producers') or [])}

    def _save():
        with _LOCK:
            _atomic_write(manifest_path, json.dumps(
                {'date': RUN_DATE, 'producers': list(manifest.values())},
                ensure_ascii=False, indent=1) + '\n')

    save = _save
    workers = 1
    if '--workers' in sys.argv:
        workers = max(1, int(sys.argv[sys.argv.index('--workers') + 1]))

    total = len(profiles)
    if workers == 1:
        for i, item in enumerate(profiles, 1):
            try:
                process(item, i, total)
            except Exception as err:  # noqa: BLE001
                log('%3d/%d %-38s UNCAUGHT %s' % (i, total, item['name'][:38], err))
    else:
        log('running %d workers over %d producers (per-domain politeness kept)'
            % (workers, total))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(process, item, i, total): item
                    for i, item in enumerate(profiles, 1)}
            for fut in as_completed(futs):
                item = futs[fut]
                try:
                    fut.result()
                except Exception as err:  # noqa: BLE001
                    log('  UNCAUGHT %s %s' % (item['name'][:38], err))

    allp = list(manifest.values())
    imgs = [g for e in allp for g in e['images']]
    from collections import Counter
    wines = [g for g in imgs if g['role'].startswith('wine-')]
    log('\nproducers=%d  images=%d  wine-related=%d  attributed own=%d'
        % (len(allp), len(imgs), len(wines),
           sum(1 for g in imgs if g.get('attribution') == 'own-wine')))
    log('appellations: %s' % dict(Counter((g['appellation'] or '未判定') for g in wines)))
    log('sites reachable: %d/%d' % (sum(1 for e in allp if e.get('websiteLive')), len(allp)))
    log('failures: %d' % sum(len(e.get('failures') or []) for e in allp))


if __name__ == '__main__':
    main()
