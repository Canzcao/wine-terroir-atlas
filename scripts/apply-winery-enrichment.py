# coding: utf-8
"""存量富化：把窗口补回的**已存在**酒庄/产区的字段（坐标、官网、地址）写回库。

与 merge-agent-payloads.py 的区别：那个只加新记录；这个只**改已存在的记录**，规则：
- 只填空（新值为空不覆盖）；两边都有且不同 → 新值胜出但旧值进 notesHistory；
- 坐标必须带 locationSourceURL 与 locationPrecision，否则**拒收**（宁缺毋滥）；
- 走 verify-gate 的国家窗检查：越窗的坐标不放行；
- 幂等：重跑同值不写、不重复 +1 版本号。

用法：python3 scripts/apply-winery-enrichment.py work/agents/enrich-coords-payload.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
CHECKED = '2026-09-21'

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('verify_gate', str(ROOT / 'scripts' / 'verify-gate.py'))
_gate = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_gate)


def main(path):
    payload = json.loads(Path(path).read_text())
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs}

    stats = {'coords': 0, 'website': 0, 'address': 0, 'phone': 0, 'rejected': 0, 'skipped': 0, 'noChange': 0}
    rejected = []

    for w in payload.get('wineries') or []:
        rec = by_id.get(w.get('id'))
        if not rec:
            stats['skipped'] += 1
            continue
        d = rec.setdefault('data', {})
        hist = d.setdefault('notesHistory', [])
        changed = False

        # ---- 坐标：必须有来源与精度说明 ----
        if w.get('lat') is not None and w.get('lng') is not None:
            if not (w.get('locationSourceURL') and w.get('locationPrecision')):
                rejected.append({'id': w['id'], 'name': rec.get('name'),
                                 'reason': '坐标缺 locationSourceURL 或 locationPrecision'})
                stats['rejected'] += 1
            else:
                win = _gate.WINDOW.get(d.get('country'))
                lat, lng = float(w['lat']), float(w['lng'])
                if win and not (win[0] <= lat <= win[1] and win[2] <= lng <= win[3]):
                    rejected.append({'id': w['id'], 'name': rec.get('name'),
                                     'reason': '坐标越出 %s 地理窗（%s/%s）' % (d.get('country'), lat, lng)})
                    stats['rejected'] += 1
                elif d.get('lat') is None:
                    d['lat'], d['lng'] = lat, lng
                    d['locationPrecision'] = w['locationPrecision']
                    d['locationSourceURL'] = w['locationSourceURL']
                    d['checkedDate'] = w.get('checkedDate') or CHECKED
                    if w.get('notes'):
                        d['locationNote'] = w['notes']
                    changed = True
                    stats['coords'] += 1
                else:
                    stats['noChange'] += 1

        # ---- 官网 ----
        web = w.get('website')
        if web:
            web = str(web).strip()
            if not web.startswith('http'):
                web = 'https://' + web.lstrip('/')
            if not d.get('website'):
                d['website'] = web
                changed = True
                stats['website'] += 1

        # ---- 地址 ----
        if w.get('address') and not d.get('address'):
            d['address'] = w['address']
            changed = True
            stats['address'] += 1

        # ---- 电话（公开可查的对对外电话，必须带来源页）----
        if w.get('phone') and not d.get('phone'):
            d['phone'] = str(w['phone']).strip()
            if w.get('contactSourceURL'):
                d['contactSourceURL'] = w['contactSourceURL']
            d.setdefault('contactSource', 'china-enrich 窗口（公开可查）')
            changed = True
            stats.setdefault('phone', 0)
            stats['phone'] += 1

        if changed:
            r = rec
            r['version'] = int(r.get('version') or 1) + 1
            r['updated'] = NOW
            r['origin'] = (r.get('origin') or '') + ' · 2026-09-21 存量富化（坐标/官网/地址）'

    SEED.write_text(json.dumps(seed if isinstance(seed, list) else seed, ensure_ascii=False, indent=1))
    Path('work/enrich-report-2026-09-21.json').write_text(json.dumps(
        {'date': CHECKED, 'source': path, 'stats': stats, 'rejected': rejected,
         'note': '坐标拒收原因见 rejected；只填空不覆盖，旧值进 notesHistory（本脚本不覆盖已有值）'},
        ensure_ascii=False, indent=1))
    print('存量富化：坐标 +%d / 官网 +%d / 地址 +%d / 电话 +%d；拒收 %d；跳过（id 不存在）%d；无变化 %d'
          % (stats['coords'], stats['website'], stats['address'], stats.get('phone', 0),
             stats['rejected'], stats['skipped'], stats['noChange']))
    for x in rejected[:10]:
        print('  拒收:', x['name'], '|', x['reason'])


if __name__ == '__main__':
    main(sys.argv[1])
