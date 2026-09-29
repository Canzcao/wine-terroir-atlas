# coding: utf-8
"""把窗口交回的 wine / vintage 记录并库（带门禁校验）。

规则：
- wine 必须指向**已存在**的 wineryId（否则拒收）；regionId 缺省继承酒庄的 regionId；
- grapes 只允许引用库里已有 grape id；percent 没官方标注就留空；
- vintage 必须指向本轮或库里已有的 wineId，year 必须 4 位且在合理区间（1900—今年+3）；
- **不去重名**：同庄同名 cuvée 视为同一款（按 id 幂等），重跑不重复加；
- 逐条记录来源（sourceURL 必须 http）。

用法：python3 scripts/apply-wines-payload.py work/agents/wines-payload.json
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
CHECKED = '2026-09-21'
YEAR_MAX = 2029


def main(path):
    payload = json.loads(Path(path).read_text())
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs}
    grape_ids = {r['id'] for r in recs if r.get('kind') == 'grape'}
    winery_region = {r['id']: (r.get('data') or {}).get('regionId')
                     for r in recs if r.get('kind') == 'winery'}

    st = {'wines': 0, 'vintages': 0, 'grapes': 0, 'wineRejected': 0, 'vintageRejected': 0}
    rejected = []

    # ---- 品种（缺的补，走同义表）----
    try:
        AL = json.loads((ROOT / 'data' / 'grape-aliases.json').read_text())
    except Exception:
        AL = {'byId': {}, 'byEn': {}}
    alias_id = AL.get('byId') or {}
    alias_en = {k.lower(): v for k, v in (AL.get('byEn') or {}).items()}
    name2grape = {}
    for r in recs:
        if r.get('kind') == 'grape':
            name2grape[(r.get('name') or '').strip().lower()] = r['id']
            en = ((r.get('data') or {}).get('en') or '').split('/')[0].strip().lower()
            if en:
                name2grape[en] = r['id']
    for mg in payload.get('missingGrapes') or []:
        key = (mg.get('en') or '').strip().lower()
        if key in alias_en and alias_en[key] in grape_ids:
            continue
        if key in name2grape:
            continue
        if not (mg.get('en') or mg.get('name')):
            continue
        import re as _re
        slug = _re.sub(r'[^a-z0-9]', '', (mg.get('en') or mg.get('name')).lower())[:24]
        gid = alias_id.get('grape-' + slug, 'grape-' + slug)
        if gid in grape_ids or gid in by_id:
            continue
        rec = {'id': gid, 'kind': 'grape', 'name': mg.get('name') or mg.get('en'),
               'data': {'name': mg.get('name') or mg.get('en'), 'en': mg.get('en'),
                        'sourceTitle': mg.get('sourceTitle') or '酒款窗口采集依据页',
                        'sourceURL': mg.get('sourceURL'),
                        'checkedDate': CHECKED},
               'version': 1, 'updated': NOW, 'origin': '酒款窗口采集 · 2026-09-21'}
        if not str(rec['data']['sourceURL'] or '').startswith('http'):
            continue
        recs.append(rec); by_id[gid] = rec; grape_ids.add(gid); st['grapes'] += 1

    # ---- wines ----
    for w in payload.get('wines') or []:
        wid = w.get('id')
        why = []
        if not wid or wid in by_id:
            st['wineRejected'] += 1
            rejected.append({'kind': 'wine', 'id': wid, 'name': w.get('name'),
                             'reason': '缺 id 或已存在（幂等跳过）'})
            continue
        if not w.get('wineryId') or w['wineryId'] not in by_id:
            why.append('wineryId 不存在')
        if not w.get('name'):
            why.append('缺 name')
        if not str(w.get('sourceURL') or '').startswith('http'):
            why.append('sourceURL 不是 http')
        grapes = []
        for g in (w.get('grapes') or []):
            gid = g.get('id') if isinstance(g, dict) else g
            gid = alias_id.get(gid, gid)
            if gid in grape_ids:
                grapes.append({'id': gid, 'percent': (g.get('percent') if isinstance(g, dict) else None)})
            else:
                why.append('未知品种 %s' % gid)
        if why:
            st['wineRejected'] += 1
            rejected.append({'kind': 'wine', 'id': wid, 'name': w.get('name'), 'reason': '；'.join(why)})
            continue
        region = w.get('regionId') or winery_region.get(w['wineryId'])
        rec = {'id': wid, 'kind': 'wine', 'name': w['name'],
               'data': {'name': w['name'], 'country': w.get('country') or None,
                        'wineryId': w['wineryId'], 'regionId': region,
                        'grapes': grapes,
                        'sourceTitle': w.get('sourceTitle') or '酒庄官网产品页',
                        'sourceURL': w['sourceURL'],
                        'checkedDate': w.get('checkedDate') or CHECKED,
                        'notes': w.get('notes') or ''},
               'version': 1, 'updated': NOW, 'origin': '酒款窗口采集 · 官网产品页核对 2026-09-21'}
        if w.get('grapeNote'):
            rec['data']['grapeNote'] = w['grapeNote']
        recs.append(rec); by_id[wid] = rec; st['wines'] += 1

    # ---- vintages ----
    for v in payload.get('vintages') or []:
        vid = v.get('id')
        why = []
        if not vid or vid in by_id:
            st['vintageRejected'] += 1
            rejected.append({'kind': 'vintage', 'id': vid, 'reason': '缺 id 或已存在（幂等跳过）'})
            continue
        if not v.get('wineId') or v['wineId'] not in by_id:
            why.append('wineId 不存在')
        try:
            y = int(v.get('year'))
            if y < 1900 or y > YEAR_MAX:
                why.append('year 越界（%s）' % v.get('year'))
        except Exception:
            why.append('year 不是整数')
        if str(v.get('evidenceLevel') or '') not in ('label-readable', 'official-page'):
            why.append('缺 evidenceLevel（label-readable/official-page）')
        if why:
            st['vintageRejected'] += 1
            rejected.append({'kind': 'vintage', 'id': vid, 'reason': '；'.join(why)})
            continue
        wine = by_id[v['wineId']]
        wd = wine.get('data') or {}
        rec = {'id': vid, 'kind': 'vintage', 'name': '%s %d' % (wine.get('name'), y),
               'data': {'name': '%s %d' % (wine.get('name'), y),
                        'country': wd.get('country'), 'wineId': v['wineId'],
                        'yearType': 'vintage', 'year': y,
                        'sourceTitle': v.get('sourceTitle') or '酒庄官网产品页',
                        'sourceURL': v.get('sourceURL') or wd.get('sourceURL'),
                        'checkedDate': v.get('checkedDate') or CHECKED,
                        'notes': (v.get('notes') or '') +
                                 '（evidenceLevel=%s）' % v.get('evidenceLevel')},
               'version': 1, 'updated': NOW, 'origin': '酒款窗口采集 · 年份证据 2026-09-21'}
        if v.get('grapes'):
            gl = []
            for g in v['grapes']:
                gid = g.get('id') if isinstance(g, dict) else g
                gid = alias_id.get(gid, gid)
                if gid in grape_ids:
                    gl.append({'id': gid, 'percent': (g.get('percent') if isinstance(g, dict) else None)})
            if gl:
                rec['data']['grapes'] = gl
        recs.append(rec); by_id[vid] = rec; st['vintages'] += 1

    SEED.write_text(json.dumps(seed if isinstance(seed, list) else seed, ensure_ascii=False, indent=1))
    Path('work/wines-apply-report-2026-09-21.json').write_text(json.dumps(
        {'date': CHECKED, 'source': path, 'stats': st, 'rejected': rejected}, ensure_ascii=False, indent=1))
    print('酒款并库：wine +%d / vintage +%d / grape +%d；拒收 wine %d / vintage %d'
          % (st['wines'], st['vintages'], st['grapes'], st['wineRejected'], st['vintageRejected']))
    for x in rejected[:10]:
        print('  拒收:', x.get('name') or x.get('id'), '|', x['reason'])


if __name__ == '__main__':
    main(sys.argv[1])
