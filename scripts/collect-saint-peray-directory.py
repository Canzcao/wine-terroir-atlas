# coding: utf-8
"""Collect the official AOC Saint-Péray producer directory (saint-peray.net).

Site shape (WordPress + Divi, one profile page per producer):
  listing  /nos-vignerons/                  -> N x <a href="/producer/<slug>/">
  profile  /producer/<slug>/                -> Divi modules with stable ids:
      #wng-logo      logo image
      #wng-name      <h1>NAME<br>CONTACT PERSON</h1>
      #wng-infos     <p>ADDRESS<br>POSTAL COMMUNE<br>PHONE<br>EMAIL<br>WEBSITE</p>
                     + optional opening-hours line + free-text description
      #wng-portrait  portrait/people photo   (lazy-loaded)
      #wng-packshot  wine bottle packshot    (lazy-loaded)

CRITICAL: every image is Divi-lazyloaded. The real URL lives in `data-src`
(the `src` attribute holds a base64 placeholder), with a <noscript> fallback.
A naive `<img>` + `src` scrape therefore yields zero usable images.

robots.txt is fully permissive (Yoast block, `Disallow:` empty, no Crawl-delay).

Outputs
  work/saint-peray/directory-raw.html          listing page cache
  work/saint-peray/producers/<slug>.html       profile page cache (resume-safe)
  work/saint-peray/profiles.json               parsed producers + image seeds
  work/saint-peray-geo-input.json              input for collect-producer-geo.py

Usage: python3 scripts/collect-saint-peray-directory.py [--refetch]
"""
import argparse
import json
import re
import ssl
import time
import unicodedata
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-17'
WORK = ROOT / 'work' / 'saint-peray'
RAW = WORK / 'producers'
BASE = 'https://saint-peray.net'
LISTING_URL = BASE + '/nos-vignerons/'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0 Safari/537.36')
DELAY = 1.2          # polite per-host delay
SITE_VERIFY = False  # saint-peray.net serves an incomplete TLS chain; curl needs -k too

# saint-peray.net's TLS chain is incomplete (curl exits 60 without -k). We do not
# downgrade silently: the flag is explicit and recorded in sources.json.
SSL_CTX = ssl.create_default_context()
if not SITE_VERIFY:
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE

# The two communes of the AOC (Ardèche). Used only for labelling, never for coords.
KNOWN_COMMUNES = {'saint-peray', 'toulaud', 'cornas', 'valence', 'guilherand-granges',
                  'bourg-les-valence', 'soyons', 'chateaubourg', 'la-roche-de-glun'}


def slugify(name: str) -> str:
    t = unicodedata.normalize('NFKD', name)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r'[^A-Za-z0-9]+', '-', t).strip('-').lower()
    return re.sub(r'-{2,}', '-', t)


def text_of(s: str) -> str:
    """Tags -> space, entities decoded, whitespace collapsed. Newlines from <br> survive."""
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
    s = re.sub(r'</(p|div|h1|h2|h3|li)>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    s = re.sub(r'[^\S\n]+', ' ', s)
    s = re.sub(r'\n{2,}', '\n', s)
    return s.strip()


def strip_tags(s: str) -> str:
    return re.sub(r'\s+', ' ', text_of(s)).strip()


def lines_of(s: str) -> list:
    return [ln.strip() for ln in text_of(s).split('\n') if ln.strip()]


def fetch(url: str, dest: Path, refetch: bool) -> str:
    if dest.exists() and not refetch and dest.stat().st_size > 1000:
        return dest.read_text(encoding='utf-8', errors='replace')
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={'User-Agent': UA, 'Accept-Language': 'fr,en;q=0.8'})
    try:
        with urlopen(req, timeout=45, context=SSL_CTX) as r:
            body = r.read()
        dest.write_bytes(body)
        time.sleep(DELAY)
        return body.decode('utf-8', errors='replace')
    except (HTTPError, URLError, OSError) as exc:
        print(f'  !! {url} -> {type(exc).__name__}: {exc}')
        return ''


def module_images(html: str) -> dict:
    """Pull the lazy-loaded uploads URL out of each Divi image module."""
    out = {}
    for mod in ('wng-logo', 'wng-portrait', 'wng-packshot'):
        # slice from the module id to the next module id marker
        i = html.find(f'id="{mod}"')
        if i < 0:
            continue
        seg = html[i:i + 6000]
        urls = re.findall(r'data-src="(https://saint-peray\.net/wp-content/uploads/[^"]+)"', seg)
        if not urls:
            urls = re.findall(r'<noscript><img[^>]+src="(https://saint-peray\.net/wp-content/uploads/[^"]+)"', seg)
        if urls:
            out[mod] = urls[0]
    return out


def parse_profile(slug: str, html: str) -> dict:
    rec = {'slug': slug, 'profileURL': f'{BASE}/producer/{slug}/'}

    # --- name + contact person -------------------------------------------------
    m = re.search(r'id="wng-name".*?<div class="et_pb_text_inner">(.*?)</div>', html, re.S)
    if m:
        parts = lines_of(m.group(1))
        if parts:
            rec['name'] = parts[0]
        if len(parts) > 1:
            rec['contactPerson'] = parts[1]
    if not rec.get('name'):
        m2 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        rec['name'] = strip_tags(m2.group(1)) if m2 else slug

    # --- infos block ----------------------------------------------------------
    # Divi emits the contact block as a run of <p> inside #wng-infos:
    #   <p>STREET<br>POSTCODE COMMUNE<br>PHONE<br>EMAIL<br>WEBSITE</p>
    #   <p>open-hours sentence + free-text pitch</p>          (optional)
    m = re.search(r'id="wng-infos".*?<div class="et_pb_text_inner">(.*?)(?:<div id="wng|</article>)', html, re.S)
    infos_html = m.group(1) if m else ''
    paras = re.findall(r'<p[^>]*>(.*?)</p>', infos_html, re.S)
    if not paras:
        paras = [infos_html]

    website = phone = email = None
    addr_lines = []
    for ln in lines_of(paras[0]):
        # the directory writes some sites without a scheme ("www.cavedetain.com")
        # and some on non-.fr/.com TLDs ("earl-...-a-e.business.site").
        # Require an alpha character so dotted phone numbers ("04.75.81.81.60") are not read as hosts.
        if re.fullmatch(r'(?:https?://)?[\w\-]+(?:\.[\w\-]+)+(?:/\S*)?', ln) \
                and re.search(r'[A-Za-z]', ln) and not re.search(r'[@\s]', ln) and not website:
            website = ln if ln.startswith('http') else 'https://' + ln
        elif re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', ln) and not email:
            email = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', ln).group(0)
        elif re.fullmatch(r'(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}', ln) and not phone:
            phone = ln
        else:
            addr_lines.append(ln)

    rest = strip_tags(' '.join(paras[1:])) if len(paras) > 1 else ''
    plain = strip_tags(infos_html)

    hours = None
    mh = re.search(r'([^.]*(?:caveau|Ouvert|ouvert|Accueil)[^.]*(?:h\s?-|h\d|samedi|dimanche)[^.]*)', plain)
    if mh:
        hours = mh.group(1).strip(' -')

    rec['website'] = website
    rec['email'] = email
    rec['phone'] = phone
    rec['addressLines'] = addr_lines[:4]

    # postcode + commune from the address block (comma after postcode is common:
    # "90 chemin du tram / 07130, Saint Péray")
    postcode = commune = None
    for ln in addr_lines:
        mc = re.search(r'\b(\d{5})\s*,?\s+([A-Za-zÀ-ÿ\'\- ]+)$', ln)
        if mc:
            postcode, commune = mc.group(1), mc.group(2).strip()
    if not postcode:
        mc = re.search(r'\b(\d{5})\s*,?\s+([A-Za-zÀ-ÿ\'\- ]+)', plain)
        if mc:
            postcode, commune = mc.group(1), mc.group(2).strip()
    rec['postcode'] = postcode
    rec['commune'] = commune
    rec['address'] = ' '.join(addr_lines) if addr_lines else None

    # --- description ----------------------------------------------------------
    # prose tail = everything in the infos module after the hours sentence
    desc = None
    cand = rest or plain
    if hours:
        cand = cand.replace(hours, ' ')
    cand = re.sub(r'\s+', ' ', cand)
    cand = re.sub(r'Voir tous les vignerons.*$', '', cand).strip()
    # drop any leftover address/phone/mail/web fragments
    for junk in [website, email, phone] + addr_lines:
        if junk:
            cand = cand.replace(junk, ' ')
    cand = re.sub(r'\s+', ' ', cand).strip(' .-')
    if len(cand) > 60:
        desc = cand
    rec['description'] = desc

    rec['openingHours'] = hours
    imgs = module_images(html)
    rec['imageSeeds'] = {
        'logo': imgs.get('wng-logo'),
        'portrait': imgs.get('wng-portrait'),
        'packshot': imgs.get('wng-packshot'),
    }
    rec['hasPortrait'] = bool(imgs.get('wng-portrait'))
    rec['hasPackshot'] = bool(imgs.get('wng-packshot'))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refetch', action='store_true')
    args = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    listing = fetch(LISTING_URL, WORK / 'directory-raw.html', args.refetch)
    slugs = []
    for u in re.findall(r'href="(https://saint-peray\.net/producer/[^"]+)"', listing):
        s = u.rstrip('/').rsplit('/', 1)[-1]
        if s not in slugs:
            slugs.append(s)
    # de-dup the double <a> wrapper (image link + title link) already handled above
    print(f'listing: {len(slugs)} producer slugs')

    # also pull the EN listing purely as an alias/name cross-check
    en_listing = fetch(BASE + '/en/our-winegrowers/', WORK / 'directory-raw-en.html', args.refetch)
    print(f'EN listing bytes: {len(en_listing)}')

    producers = []
    for n, slug in enumerate(slugs, 1):
        html = fetch(f'{BASE}/producer/{slug}/', RAW / f'{slug}.html', args.refetch)
        if not html:
            producers.append({'slug': slug, 'name': None, 'fetchFailed': True,
                              'profileURL': f'{BASE}/producer/{slug}/'})
            continue
        rec = parse_profile(slug, html)
        producers.append(rec)
        flag = ('P' if rec['hasPortrait'] else '-') + ('B' if rec['hasPackshot'] else '-')
        print(f"  [{n:2d}/{len(slugs)}] {flag} {rec['name']} | {(rec['commune'] or '?')} | {rec['website'] or '-'}")

    have_site = [p for p in producers if p.get('website')]
    have_portrait = [p for p in producers if p.get('hasPortrait')]
    have_packshot = [p for p in producers if p.get('hasPackshot')]
    print(f'\nwith website      : {len(have_site)}/{len(producers)}')
    print(f'with portrait img : {len(have_portrait)}/{len(producers)}')
    print(f'with packshot img : {len(have_packshot)}/{len(producers)}')

    (WORK / 'profiles.json').write_text(
        json.dumps({'sourceURL': LISTING_URL, 'checkedDate': DATE,
                    'producerBaseline': len(slugs), 'producers': producers},
                   ensure_ascii=False, indent=1), encoding='utf-8')

    geo_input = [{'slug': slugify(p.get('name') or p['slug']), 'name': p.get('name') or p['slug'],
                  'commune': p.get('commune'), 'website': p.get('website'),
                  'profileURL': p.get('profileURL')} for p in producers if p.get('name')]
    (ROOT / 'work' / 'saint-peray-geo-input.json').write_text(
        json.dumps(geo_input, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\nwrote work/saint-peray/profiles.json ({len(producers)} producers)')
    print('wrote work/saint-peray-geo-input.json')


if __name__ == '__main__':
    main()
