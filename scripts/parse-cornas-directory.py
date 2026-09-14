# coding: utf-8
"""Parse the official AOC Cornas producer directory (aoc-cornas.fr) into JSON.

The listing is a single page (no per-producer profile pages, no images):
repeated <div class="row LigneProd"> blocks with h2 (name), h3 (contact person)
and a FicheProdCoord line holding address / phone / email / website.

Output: outputs/daily/2026-09-14/cornas-官方名录-2026-09-14.json
        work/cornas-geo-input.json  (for collect-producer-geo.py)

Usage: python3 scripts/parse-cornas-directory.py
"""
import json
import re
import unicodedata
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-09-14'
SRC = ROOT / 'work' / 'cornas' / 'directory.html'
OUT_DIR = ROOT / 'outputs' / 'daily' / DATE
OUT_DIR.mkdir(parents=True, exist_ok=True)
LISTING_URL = 'https://www.aoc-cornas.fr/cornas-producteurs.html'


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r'[^A-Za-z0-9]+', '-', text).strip('-').lower()
    return re.sub(r'-{2,}', '-', text)


def strip_tags(s: str) -> str:
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def main():
    html = SRC.read_text(encoding='utf-8')
    blocks = re.findall(
        r'<div class="row LigneProd">(.*?)<hr class="FicheProdHR">',
        html, flags=re.S)
    producers, seen = [], {}
    for b in blocks:
        name = strip_tags(re.search(r'<h2>(.*?)</h2>', b, re.S).group(1))
        h3 = re.search(r'<h3>(.*?)</h3>', b, re.S)
        contact = strip_tags(h3.group(1)) if h3 else ''
        coord = re.search(r'<div class="FicheProdCoord">(.*?)</div>', b, re.S)
        line = coord.group(1) if coord else ''
        # website: first <a> href with a real http(s) target
        link = re.search(r'<a href="(https?://[^"]+)"', line)
        website = link.group(1).rstrip('/') if link else None
        text = strip_tags(line)
        # email
        mail = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
        email = mail.group(0) if mail else None
        # phone: French patterns like 04 90 83 57 29
        phone = re.search(r'(?:\+33|0)\s?[1-9](?:[\s.-]?\d{2}){4}', text)
        phone = re.sub(r'\s+', ' ', phone.group(0)) if phone else None
        # address: text before the first phone/email
        addr = text
        for cutter in (phone or '␀', email or '␀'):
            if cutter in addr:
                addr = addr.split(cutter)[0]
        addr = addr.strip(' -–')
        # address starts after the producer's own name if repeated
        if addr.lower().startswith(name.lower()):
            addr = addr[len(name):].lstrip(' -–')
        if not name:
            continue
        entry = {
            'name': name,
            'contact': contact or None,
            'address': addr or None,
            'phone': phone,
            'email': email,
            'website': website,
            'directoryURL': LISTING_URL,
        }
        slug = slugify(name)
        if slug in seen:  # exact duplicate block (site repeats some entries)
            continue
        seen[slug] = True
        producers.append(entry)

    # 同名异写去重（如 "Julien Pilon" vs "PILON JULIEN"）记录在 note，不静默合并
    by_lower = {}
    for p in producers:
        key = re.sub(r'[^a-z]', '', p['name'].lower())
        by_lower.setdefault(key, []).append(p['name'])
    duplicates = {k: v for k, v in by_lower.items() if len(v) > 1}

    (OUT_DIR / 'cornas-官方名录-2026-09-14.json').write_text(json.dumps({
        'date': DATE,
        'source': 'Syndicat AOC Cornas · Domaines & Maisons 名录',
        'sourceURL': LISTING_URL,
        'checkedDate': DATE,
        'sourceLanguage': 'fr',
        'notes': '官方名录单页列表，无逐家详情页与图片；每家仅名称/联系人/地址/电话/邮箱/官网。'
                 '名录包含产区外的酒商（maisons/négociants），照录不删。',
        'producers': producers,
    }, ensure_ascii=False, indent=1) + '\n')

    geo_input = [{'id': 'cornas-' + slugify(p['name']), 'name': p['name'],
                  'country': 'France'} for p in producers]
    (ROOT / 'work' / 'cornas-geo-input.json').write_text(
        json.dumps(geo_input, ensure_ascii=False, indent=1) + '\n')

    print('producers:', len(producers))
    print('with website:', sum(1 for p in producers if p['website']))
    print('with email:', sum(1 for p in producers if p['email']))
    print('possible same-name variants:', duplicates)


if __name__ == '__main__':
    main()
