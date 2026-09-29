# coding: utf-8
"""应用"酒款名称复核"结论：ok 确认 / corrected 改名（旧名进 notesHistory）/ notFound 标记留档。

用法：python3 scripts/apply-wine-name-recheck.py work/agents/wine-name-recheck-A-payload.json
可重复跑（幂等）：同一结论重复应用不会重复 +1 版本号。
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def main(path):
    payload = json.loads(Path(path).read_text())
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs}
    st = {'ok': 0, 'corrected': 0, 'notFound': 0, 'missing': 0}
    not_found = []
    for r in payload.get('results') or []:
        rec = by_id.get(r.get('wineId'))
        if not rec:
            st['missing'] += 1
            continue
        d = rec.setdefault('data', {})
        v = r.get('verdict')
        d['verification'] = {
            'method': 'independent-window:name-recheck', 'checkedDate': '2026-09-21',
            'verdict': v, 'productURL': r.get('productURL') or None,
            'evidence': (r.get('evidence') or '')[:200], 'note': (r.get('note') or '')[:200],
            'status': {'ok': 'name-confirmed', 'corrected': 'name-corrected',
                       'notFound': 'name-not-found-manual'}.get(v, 'unknown'),
        }
        if v == 'ok':
            if r.get('standardName') and r['standardName'] != rec.get('name'):
                d.setdefault('nameVariants', []).append(r['standardName'])
            if r.get('productURL') and r['productURL'] != d.get('sourceURL'):
                d['sourceURL'] = r['productURL']
                d['sourceNote'] = '2026-09-21 复核后指向具体产品页'
            st['ok'] += 1
        elif v == 'corrected':
            old = rec.get('name')
            new = r.get('correctedName')
            if new and new != old:
                d.setdefault('notesHistory', []).append({
                    'field': 'name', 'previousValue': old, 'replacedAt': NOW,
                    'reason': '酒款复核：库内名与产品页不符（含抓取残留/重复拼接）→ 改为页面真实名'})
                rec['name'] = new
                d['name'] = new
            if r.get('productURL'):
                d['sourceURL'] = r['productURL']
            st['corrected'] += 1
        elif v == 'notFound':
            not_found.append({'wineId': rec['id'], 'name': rec.get('name'),
                              'checkedURLs': r.get('checkedURLs') or [],
                              'note': r.get('note'), 'evidence': r.get('evidence')})
            st['notFound'] += 1
        rec['version'] = int(rec.get('version') or 1) + 1
        rec['updated'] = NOW
    SEED.write_text(json.dumps(seed if isinstance(seed, list) else seed, ensure_ascii=False, indent=1))
    Path('work/wine-name-recheck-report.json').write_text(json.dumps(
        {'date': '2026-09-21', 'source': path, 'stats': st, 'notFoundItems': not_found},
        ensure_ascii=False, indent=1))
    print('复核应用：ok %d / corrected %d / notFound %d（id 不存在 %d）'
          % (st['ok'], st['corrected'], st['notFound'], st['missing']))
    for x in not_found[:8]:
        print('  待人工:', x['name'], '|', (x.get('note') or '')[:60])


if __name__ == '__main__':
    main(sys.argv[1])
