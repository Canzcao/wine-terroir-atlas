# coding: utf-8
"""酒款/年份交叉验证（Tier1 机器层）：来源页可达性 + 酒款名是否出现在来源页。

带 HTTP 缓存（work/verify-cache/），可反复重跑；结果写回记录的 data.verification。
"""
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
OUT = ROOT / 'outputs' / 'collect' / '_verification-2026-09-21' / 'verification-wines.json'
UA = 'Mozilla/5.0 (compatible; TerroirAtlasVerify/1.0)'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch(url, timeout=20):
    cdir = ROOT / 'work' / 'verify-cache'
    if not cdir.exists():
        cdir.mkdir(parents=True)
    cp = cdir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.html')
    if cp.exists():
        raw = cp.read_bytes()
        return (0, '') if raw.startswith(b'STATUS:000') else (200, raw.decode('utf-8', 'ignore'))
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,fr,es,it,pt,de,zh,ja;q=0.7'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read(400000)
            cp.write_bytes(data)
            return r.status, data.decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        cp.write_bytes(b'STATUS:%03d' % e.code)
        return e.code, ''
    except Exception:
        cp.write_bytes(b'STATUS:000')
        return 0, ''


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def main():
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    wines = [r for r in recs if r.get('kind') == 'wine']
    st = {'checked': 0, 'nameOnPage': 0, 'nameNotOnPage': 0, 'unreachable': 0}
    items = []
    for w in wines:
        d = w.get('data') or {}
        url = d.get('sourceURL')
        code, html = fetch(url)
        name_ok = False
        if code == 200 and html:
            key = norm(w.get('name'))[-18:]
            plain = norm(html)
            name_ok = bool(key) and key in plain
        status = ('reliable' if name_ok else 'name-not-found-on-page' if code == 200 else 'source-unreachable')
        d['verification'] = {'method': 'auto:http+name-on-page', 'checkedDate': '2026-09-21',
                             'httpStatus': code, 'nameOnPage': name_ok, 'status': status}
        st['checked'] += 1
        st['nameOnPage' if name_ok else ('nameNotOnPage' if code == 200 else 'unreachable')] += 1
        items.append({'id': w['id'], 'name': w.get('name'), 'sourceURL': url,
                      'httpStatus': code, 'nameOnPage': name_ok, 'status': status})
    SEED.write_text(json.dumps(seed if isinstance(seed, list) else seed, ensure_ascii=False, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'date': '2026-09-21', 'stats': st, 'items': items},
                              ensure_ascii=False, indent=1))
    print('酒款验证：核对 %d 条 | 名字在页 %d | 页面可达但名字未出现 %d | 来源不可达 %d'
          % (st['checked'], st['nameOnPage'], st['nameNotOnPage'], st['unreachable']))


if __name__ == '__main__':
    main()
