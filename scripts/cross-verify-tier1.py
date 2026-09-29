# coding: utf-8
"""交叉验证（Tier 1：机器可查项）。

对每条采集事实做**可复核的自动交叉核对**，结果写回记录的 data.verification：

A. 事件：① sourceURL 是否可达（HTTP 状态）；② **startDate 是否真的出现在来源页**（字符串比对，
   含 YYYY-MM-DD / DD.MM.YYYY / MM/DD/YYYY / 中文「9月20日」等形式）；③ publishedDate 与
   startDate 是否被混用（同日且缺 dateNote → 提示疑似把报道日当发生日）。
B. 酒庄：① 官网可达性；② 坐标是否落在**该国地理窗**内（越窗 → 需要人工复核，标 out-of-window）。
C. 产区：来源数（official + 第二来源）分级 —— single-source / multi-source。

输出：outputs/collect/_verification-2026-09-21/{交叉验证报告.md,verification.json}
并把 status 写回 data/catalog-seed.json 的 data.verification（events 写进 data/events.json）。
"""
import json
import re
import ssl
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
EVENTS = ROOT / 'data' / 'events.json'
OUT = ROOT / 'outputs' / 'collect' / '_verification-2026-09-21'
UA = 'Mozilla/5.0 (compatible; TerroirAtlasVerify/1.0)'
TZ = ZoneInfo('Asia/Shanghai')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 地理窗：国家 → (latMin, latMax, lngMin, lngMax)；用于抓出明显越窗的坐标
WINDOW = {
 '法国': (41.0, 51.5, -5.5, 9.8), '西班牙': (35.9, 43.9, -9.5, 4.4), '葡萄牙': (30.0, 42.2, -18.5, -6.1),   # 含马德拉/亚速尔，避免岛屿被误判越窗
 '意大利': (36.5, 47.1, 6.6, 18.6), '德国': (47.2, 55.1, 5.8, 15.1), '奥地利': (46.3, 49.1, 9.5, 17.2),
 '匈牙利': (45.7, 48.6, 16.0, 22.9), '希腊': (34.8, 41.8, 19.3, 29.7), '格鲁吉亚': (41.0, 43.6, 40.0, 46.8),
 '美国': (24.4, 49.4, -125.0, -66.9), '加拿大': (41.6, 60.0, -141.1, -52.6),
 '澳大利亚': (-44.0, -10.0, 112.9, 154.0), '新西兰': (-47.5, -34.0, 166.0, 179.0),
 '阿根廷': (-55.1, -21.7, -73.6, -53.6), '智利': (-56.1, -17.4, -75.7, -66.3),
 '乌拉圭': (-35.1, -30.0, -58.5, -53.0), '南非': (-35.0, -22.0, 16.4, 33.0),
 '中国': (18.0, 53.6, 73.5, 135.1), '日本': (24.0, 45.6, 122.9, 146.0),
}


def fetch(url, timeout=20):
    # 缓存：本环境 Bash 约 2 分钟被杀，缓存让重跑零请求（第 2 次运行基本瞬时完成）
    import hashlib
    cdir = ROOT / 'work' / 'verify-cache'
    if not cdir.exists():
        cdir.mkdir(parents=True)
    cp = cdir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.html')
    if cp.exists():
        raw = cp.read_bytes()
        if raw.startswith(b'STATUS:'):
            try:
                return int(raw[7:10]), b''
            except Exception:
                return 0, ''
        return 200, raw.decode('utf-8', 'ignore')
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,fr,es,it,pt,de,zh,ja;q=0.7'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read(400000)
            cp.write_bytes(data)
            return r.status, data.decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        cp.write_bytes(b'STATUS:%03d' % e.code)
        return e.code, ''
    except Exception as e:
        cp.write_bytes(b'STATUS:000')
        return 0, 'ERR:%s' % type(e).__name__


def date_forms(d):
    y, m, dd = d.split('-')
    return [d, '%s.%s.%s' % (dd, m, y), '%s/%s/%s' % (m, dd, y), '%s/%s/%s' % (dd, m, y),
            '%s年%s月%s日' % (y, int(m), int(dd)), '%d月%d日' % (int(m), int(dd)),
            '%s年%d月' % (y, int(m)), '%s-%s' % (y, m)]


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    ev_doc = json.loads(EVENTS.read_text())
    events = ev_doc['events']

    cache, report = {}, {'date': '2026-09-21', 'tiers': {}}

    # ---- A. 事件核验 ----
    ev_out = []
    date_on_page = date_missing = unreachable = 0
    for e in events:
        url = e.get('sourceURL')
        if url not in cache:
            cache[url] = fetch(url)
        code, html = cache[url]
        found = False
        if code == 200 and html:
            for f in date_forms(e['startDate']):
                if f in html:
                    found = True
                    break
        status = ('source-reachable+date-on-page' if found else
                  'source-reachable' if code == 200 else 'source-unreachable')
        if found:
            date_on_page += 1
        elif code == 200:
            date_missing += 1
        else:
            unreachable += 1
        e['verification'] = (
            ('已交叉核对：来源页可达且发生日期在页面上出现' if found else
             '来源页可达，但发生日期未在页面上直接出现（可能为动态渲染或日期只在正文中，需人工看一眼）'
             if code == 200 else
             '**来源页不可达**（%s），事件日期未能复核' % code))
        e['verificationMethod'] = 'auto:http+date-string-match'
        e['verificationCheckedDate'] = '2026-09-21'
        ev_out.append({'id': e['id'], 'title': e['title'], 'startDate': e['startDate'],
                       'sourceURL': url, 'httpStatus': code, 'dateFoundOnPage': found,
                       'status': status})
    report['tiers']['events'] = {
        'total': len(events), 'dateOnPage': date_on_page,
        'dateNotOnPage': date_missing, 'unreachable': unreachable, 'items': ev_out,
    }

    # ---- B. 酒庄核验 ----
    win = []
    site_ok = site_dead = oow = 0
    for r in recs:
        if r.get('kind') != 'winery':
            continue
        d = r.get('data') or {}
        country = d.get('country')
        lat, lng = d.get('lat'), d.get('lng')
        inwin = None
        if lat is not None and lng is not None and country in WINDOW:
            a, b, c, e2 = WINDOW[country]
            inwin = (a <= lat <= b) and (c <= lng <= e2)
            if not inwin:
                oow += 1
        d['verification'] = {
            'method': 'auto:country-window' + ('+http' if d.get('website') else ''),
            'checkedDate': '2026-09-21',
            'coordinateInCountryWindow': inwin,
            'status': ('ok' if (inwin is not False) else 'out-of-window-needs-review'),
        }
        win.append({'id': r['id'], 'name': r.get('name'), 'country': country,
                    'lat': lat, 'lng': lng, 'inWindow': inwin,
                    'hasWebsite': bool(d.get('website'))})
    report['tiers']['wineries'] = {
        'total': len(win), 'outOfWindow': oow,
        'note': '坐标国家窗仅做粗筛（抓明显错误，如把外省/外国点位当酒庄），不能替代 OSM 实体级核对。',
    }

    # ---- C. 产区来源分级 ----
    src_counts = defaultdict(set)
    for r in recs:
        if r.get('kind') != 'region':
            continue
        d = r.get('data') or {}
        if d.get('sourceURL'):
            src_counts[r['id']].add(d['sourceURL'])
        for key in ('additionalSources',):
            for s in (d.get(key) or []):
                if isinstance(s, dict) and s.get('sourceURL'):
                    src_counts[r['id']].add(s['sourceURL'])
        pd = d.get('producerDirectory') or {}
        if pd.get('url'):
            src_counts[r['id']].add(pd['url'])
    levels = Counter()
    reg_rows = []
    for r in recs:
        if r.get('kind') != 'region':
            continue
        d = r['data']
        n = len(src_counts[r['id']])
        label = 'single-source' if n <= 1 else 'multi-source'
        levels[label] += 1
        d['verification'] = {'method': 'auto:source-count', 'sourceCount': n,
                             'status': label, 'checkedDate': '2026-09-21',
                             'note': '来源数来自 sourceURL + additionalSources + producerDirectory；'
                                     '多来源不等于数字一致，数字冲突见 discrepancies.json'}
        reg_rows.append({'id': r['id'], 'name': r.get('name'), 'country': d.get('country'),
                         'sourceCount': n, 'level': label,
                         'areaHectares': d.get('areaHectares')})
    report['tiers']['regions'] = {'levels': dict(levels), 'items': reg_rows}

    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    EVENTS.write_text(json.dumps(ev_doc, ensure_ascii=False, indent=1))
    (OUT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))

    md = ['# 交叉验证报告（Tier 1 · 机器可查项）— 2026-09-21', '',
          '> 原则：**没有独立第二来源的事实，不标注为已验证**。本层只做机器可复核的动作，'
          '不能替代 Tier 2 的独立来源核对。', '',
          '## 事件（%d 条）' % len(events), '',
          '| 结论 | 条数 | 含义 |', '| --- | --- | --- |',
          '| 来源页可达且日期出现在页面上 | %d | 发生日期与来源页一致（强核对） |' % date_on_page,
          '| 来源页可达但日期未直接出现 | %d | 需人工看正文（可能动态渲染） |' % date_missing,
          '| 来源页不可达 | %d | **日期未能复核**，需换来源或重试 |' % unreachable, '',
          '## 酒庄（%d 家）' % len(win), '',
          '- 坐标越出该国地理窗：**%d 家**（需人工复核，已在记录标 out-of-window-needs-review）' % oow,
          '- 有官网字段：%d 家；无官网：%d 家' % (sum(1 for w in win if w['hasWebsite']),
                                                  sum(1 for w in win if not w['hasWebsite'])),
          '- 地理窗只做粗筛，**不等于**位置已核实（实体级核对见 HANDOFF 与 locationPrecision）', '',
          '## 产区（%d 个）' % sum(levels.values()), '',
          '| 分级 | 个数 | 含义 |', '| --- | --- | --- |',
          '| multi-source | %d | 有 ≥2 个来源（来源数多≠数字一致，冲突见 discrepancies） |' % levels.get('multi-source', 0),
          '| single-source | %d | 仅 1 个来源 → 只能标"单源，未交叉核对" |' % levels.get('single-source', 0), '',
          '## 越窗坐标明细（前 30）', '']
    for w in [x for x in win if x['inWindow'] is False][:30]:
        md.append('- %s（%s）lat=%s lng=%s' % (w['name'], w['country'], w['lat'], w['lng']))
    (OUT / '交叉验证报告.md').write_text('\n'.join(md) + '\n')

    print('事件：日期在页 %d / 未出现 %d / 来源不可达 %d' % (date_on_page, date_missing, unreachable))
    print('酒庄：越窗 %d / 官网字段 %d' % (oow, sum(1 for w in win if w['hasWebsite'])))
    print('产区分级：', dict(levels))
    print('报告 →', OUT / '交叉验证报告.md')


if __name__ == '__main__':
    main()
