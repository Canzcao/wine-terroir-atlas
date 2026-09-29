# coding: utf-8
"""进库门禁：任何窗口交回的 payload，必须过这道闸才能进 data/catalog-seed.json。

两类判定：
- **BLOCK（硬拦）**：数据完整性问题，条目**不入库**，进 work/gate-held-<date>.json 待修。
- **FLAG（软标）**：数据可疑（如来源页不可达、单来源、面积无口径说明），入库但打标记。

设计原则：门禁只拦"数据自己的毛病"，不因网络抖动丢内容（不可达 → FLAG，不 BLOCK）。

用法：
  python3 scripts/verify-gate.py --check work/agents/*.json     # 只体检，不写库
  python3 scripts/verify-gate.py --gate  work/agents/xxx.json   # 输出过滤后的 payload 到 work/gate/xxx.gated.json
merge-agent-payloads.py 在并库前调用本模块（见 gate_payload）。
"""
import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 9, 21)
UA = 'Mozilla/5.0 (compatible; TerroirAtlasGate/1.0)'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 国家地理窗（含岛屿，见技能 2.14 的马德拉教训）
WINDOW = {
 '法国': (41.0, 51.5, -5.5, 9.8), '西班牙': (27.5, 43.9, -18.5, 4.4), '葡萄牙': (30.0, 42.2, -31.5, -6.1),
 '意大利': (35.0, 47.1, 6.6, 18.6), '德国': (47.2, 55.1, 5.8, 15.1), '奥地利': (46.3, 49.1, 9.5, 17.2),
 '匈牙利': (45.7, 48.6, 16.0, 22.9), '希腊': (34.8, 41.8, 19.3, 29.7), '格鲁吉亚': (41.0, 43.6, 40.0, 46.8),
 '美国': (18.9, 71.4, -179.2, -66.9), '加拿大': (41.6, 83.2, -141.1, -52.6),
 '澳大利亚': (-44.0, -9.0, 112.9, 154.0), '新西兰': (-47.5, -34.0, 166.0, 179.0),
 '阿根廷': (-55.1, -21.7, -73.6, -53.6), '智利': (-56.1, -17.4, -109.5, -66.3),
 '乌拉圭': (-35.1, -30.0, -58.5, -53.0), '南非': (-35.0, -22.0, 16.4, 33.0),
 '中国': (18.0, 53.6, 73.5, 135.1), '日本': (24.0, 45.6, 122.9, 146.0),
}
EVENT_TYPES = ('news', 'event', 'harvest', 'weather', 'disaster')
REQ_EVENT = ['id', 'title', 'summary', 'type', 'startDate', 'country', 'region',
             'precision', 'sourceName', 'sourceURL', 'verification', 'checkedDate']


def _fetch(url, timeout=15):
    import hashlib
    cdir = ROOT / 'work' / 'verify-cache'
    if not cdir.exists():
        cdir.mkdir(parents=True)
    cp = cdir / (hashlib.sha256(url.encode()).hexdigest()[:16] + '.html')
    if cp.exists():
        raw = cp.read_bytes()
        return (0, '') if raw.startswith(b'STATUS:000') else (200, raw.decode('utf-8', 'ignore'))
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            data = r.read(300000)
            cp.write_bytes(data)
            return r.status, data.decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        cp.write_bytes(b'STATUS:%03d' % e.code)
        return e.code, ''
    except Exception:
        cp.write_bytes(b'STATUS:000')
        return 0, ''


def date_forms(d):
    y, m, dd = d.split('-')
    return [d, '%s.%s.%s' % (dd, m, y), '%s/%s/%s' % (m, dd, y), '%s/%s/%s' % (dd, m, y),
            '%s年%s月%s日' % (y, int(m), int(dd)), '%d月%d日' % (int(m), int(dd))]


def gate_payload(payload, http=True, known_event_ids=None, known_event_types=True):
    """返回 (clean_payload, blocked[], flagged[])；blocked 的条目不会进库。

    known_event_ids：库里已有的事件 id 集合 —— payload 里同 id 的占位/重复条目按"重复跳过"处理，
    不算 BLOCK（真实教训：窗口会在 events 里放只带 id 的交叉引用条目）。
    """
    blocked, flagged, skipped = [], [], []
    known_event_ids = set(known_event_ids or [])
    out = {k: v for k, v in payload.items()}

    # ---- 事件 ----
    ev_ok, seen_ev = [], set()
    for e in payload.get('events') or []:
        eid = e.get('id')
        if eid and (eid in known_event_ids or eid in seen_ev):
            skipped.append({'kind': 'event', 'id': eid,
                            'reason': 'id 已存在或 payload 内重复 → 跳过（不重复入库）'})
            continue
        why = []
        for k in REQ_EVENT:
            if not e.get(k):
                why.append('缺字段 %s' % k)
        sd = str(e.get('startDate') or '')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', sd):
            why.append('startDate 非 YYYY-MM-DD')
        else:
            try:
                d0 = date(*[int(x) for x in sd.split('-')])
                if d0.year < 1900 or (d0 - TODAY).days > 400:
                    why.append('startDate 超出合理范围（%s）' % sd)
            except Exception:
                why.append('startDate 不可解析')
        if e.get('type') not in EVENT_TYPES:
            why.append('type 不在闭集内（%s）' % e.get('type'))
        if not str(e.get('sourceURL') or '').startswith('http'):
            why.append('sourceURL 不是 http(s)')
        if why:
            blocked.append({'kind': 'event', 'id': eid, 'title': e.get('title'),
                            'reasons': why}); continue
        if eid:
            seen_ev.add(eid)
        if e.get('endDate') and str(e['endDate']) < sd:
            flagged.append({'kind': 'event', 'id': eid, 'reason': 'endDate 早于 startDate，已置空'})
            e['endDate'] = None
        if http:
            code, html = _fetch(e['sourceURL'])
            if code != 200:
                flagged.append({'kind': 'event', 'id': eid,
                                'reason': '来源页不可达（%s）——入库但需重试' % code})
                e['verification'] = '来源页当前不可达（%s），日期未能复核' % code
            elif not any(f in html for f in date_forms(sd)):
                flagged.append({'kind': 'event', 'id': eid,
                                'reason': '发生日期未在来源页出现（可能动态渲染），入库但需人工看'})
                e['verification'] = '来源页可达，但发生日期未在页面上直接出现，待人工确认'
            else:
                e['verification'] = '来源页可达且发生日期出现在页面上（自动核对）'
        ev_ok.append(e)
    out['events'] = ev_ok

    # ---- 酒庄 ----
    w_ok, seen = [], set()
    for w in payload.get('wineries') or []:
        wid, nm = w.get('id'), w.get('name')
        why = []
        if not wid or not nm:
            why.append('缺 id 或 name')
        elif wid in seen:
            why.append('payload 内 id 重复')
        if why:
            blocked.append({'kind': 'winery', 'id': wid, 'name': nm, 'reasons': why}); continue
        seen.add(wid)
        # 坐标证据的类型检查（2026-09-21 实测教训：4 家阿根廷酒庄的坐标来源是 OSM 道路要素）
        lsu = str(w.get('locationSourceURL') or '')
        if lsu and re.search(r'openstreetmap\.org/(way|relation)/', lsu):
            flagged.append({'kind': 'winery', 'id': wid,
                            'reason': '坐标来源是 OSM way/relation —— 需人工确认要素类型'
                                      '（道路 highway=*、行政区 boundary=* 不算酒庄点位）'})
            if 'highway' in lsu.lower() or 'road' in lsu.lower():
                flagged.append({'kind': 'winery', 'id': wid,
                                'reason': '坐标来源疑似道路要素，坐标已置空待重检索'})
                w['lat'], w['lng'] = None, None
                w['locationReview'] = {'status': 'invalid-poi',
                                       'reason': '门禁：坐标来源为道路类 OSM 要素', 'checkedDate': str(TODAY)}
        c, lat, lng = w.get('country'), w.get('lat'), w.get('lng')
        if lat is not None and lng is not None:
            win = WINDOW.get(c)
            if win and not (win[0] <= lat <= win[1] and win[2] <= lng <= win[3]):
                flagged.append({'kind': 'winery', 'id': wid,
                                'reason': '坐标越出 %s 地理窗（%s/%s）→ 置空待重检索' % (c, lat, lng)})
                w['lat'], w['lng'] = None, None
                w['locationReview'] = {'status': 'out-of-window',
                                       'reason': '门禁：坐标不在该国地理窗内', 'checkedDate': str(TODAY)}
        if w.get('website') and not str(w['website']).startswith('http'):
            v = str(w['website']).strip()
            # 真问题修法：`www.xxx.com` 这类缺 scheme 的**归一化**补 https://，不丢字段
            if re.match(r'^(www\.)?[a-z0-9][a-z0-9\-\.]+\.[a-z]{2,}(/|$)', v, re.I):
                w['website'] = 'https://' + v.lstrip('/')
                flagged.append({'kind': 'winery', 'id': wid,
                                'reason': 'website 缺 scheme，已归一化为 %s（未验证可达性）' % w['website']})
            else:
                flagged.append({'kind': 'winery', 'id': wid,
                                'reason': 'website 不是域名（%r），已丢弃该字段' % v[:40]})
                w['website'] = None
        # 缺来源字段 → FLAG（并库后需从产区官方页回填，实测一轮有 102 条缺来源）
        if not str(w.get('sourceURL') or '').startswith('http'):
            flagged.append({'kind': 'winery', 'id': wid,
                            'reason': '缺 sourceURL/sourceTitle —— 入库后需从产区官方页回填（否则 validate 会拦）'})
        w_ok.append(w)
    out['wineries'] = w_ok

    # ---- 产区 ----
    r_ok = []
    for rg in payload.get('regions') or []:
        why = []
        if not rg.get('id') or not (rg.get('name') or rg.get('en')):
            why.append('缺 id 或 name')
        if not str(rg.get('sourceURL') or '').startswith('http'):
            why.append('缺可复核的 sourceURL')
        if why:
            blocked.append({'kind': 'region', 'id': rg.get('id'), 'name': rg.get('name'),
                            'reasons': why}); continue
        if rg.get('areaHectares') is not None and not (rg.get('areaNote') or '').strip():
            flagged.append({'kind': 'region', 'id': rg['id'],
                            'reason': '写了面积但没写口径说明（areaNote 为空）'})
        r_ok.append(rg)
    out['regions'] = r_ok

    out['_gate'] = {'date': str(TODAY), 'blocked': len(blocked), 'flagged': len(flagged)}
    return out, blocked, flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--gate', action='store_true', help='输出过滤后的 payload 到 work/gate/')
    ap.add_argument('--no-http', action='store_true')
    a = ap.parse_args()
    all_b, all_f, lines = [], [], []
    for f in a.files:
        p = json.loads(Path(f).read_text())
        if not isinstance(p, dict) or 'regions' not in p and 'events' not in p and 'wineries' not in p:
            print('%s: 跳过（不是窗口 payload 结构）' % Path(f).name)
            continue
        clean, b, fl = gate_payload(p, http=not a.no_http)
        all_b += b; all_f += fl
        lines.append('%s: 拦 %d / 标 %d' % (Path(f).name, len(b), len(fl)))
        if a.gate:
            od = ROOT / 'work' / 'gate'
            if not od.exists():
                od.mkdir(parents=True)
            (od / (Path(f).stem + '.gated.json')).write_text(json.dumps(clean, ensure_ascii=False, indent=1))
    print('\n'.join(lines))
    print('合计：拦 %d 条，标记 %d 条' % (len(all_b), len(all_f)))
    for x in all_b[:20]:
        print('  BLOCK', x['kind'], x.get('id') or x.get('name'), '|', '；'.join(x['reasons']))
    for x in all_f[:20]:
        print('  FLAG ', x['kind'], x.get('id'), '|', x.get('reason'))


if __name__ == '__main__':
    sys.exit(main())
