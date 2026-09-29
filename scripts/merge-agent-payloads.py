# coding: utf-8
"""把各"国家窗口"交回的 payload 统一并入站点目录（单点写入，避免并发冲突）。

规则：
- region：库内已有 id → 就地富化（version+1；非空旧值被覆盖前存 notesHistory）；新 id → 新建记录。
- 品种：payload 的 missingGrapes → 新建 grape 记录（按英文名去重，已有则复用）。
- winery：新 id 建档；**按规范化名称查重**（防同名重复）；空键不参与名称匹配。
- events：按 id 追加；缺必填字段则补齐（validate 要求 12 个字段）。
- 幂等：已存在的 id 跳过；重跑不重复加。
"""
import json
import re
import shutil
import glob
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
EVENTS = ROOT / 'data' / 'events.json'
B_SEED = ROOT / 'work' / '_catalog-seed.before-agent-bulk-2026-09-21.json'
B_EV = ROOT / 'work' / '_events.before-agent-bulk-2026-09-21.json'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
CHECKED = '2026-09-21'
REQUIRED_EVENT = ['id', 'title', 'summary', 'type', 'startDate', 'country', 'region',
                  'precision', 'sourceName', 'sourceURL', 'verification', 'checkedDate']
REGION_FIELDS = ['appellationCreated', 'appellationCreatedNote', 'areaHectares', 'areaNote',
                 'productionNote', 'producersNote', 'growersNote', 'yieldNote', 'harvestNote',
                 'productionHl', 'bottlesNote', 'villagesNote', 'subzones', 'communes', 'provinces',
                 'grapeNote', 'agingNote', 'qualityTiers', 'doStructure', 'historyNote', 'soil',
                 'climate', 'geography', 'notes', 'totalAreaHectares', 'officialQuote']


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def main():
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs}
    winery_by_name = {}
    for r in recs:
        if r.get('kind') == 'winery':
            k = norm(r.get('name'))
            if k:
                winery_by_name.setdefault(k, r)
    ev_doc = json.loads(EVENTS.read_text())
    ev_list = ev_doc.get('events', [])
    ev_ids = {e['id'] for e in ev_list}

    # 抑制名单：已被判定降级/冲突的事件 id，重跑并库时**不得复活**
    SUPPRESS = set()
    for pat in ('events-date-conflicts-*.json', 'events-heldback-*.json'):
        for sf in (ROOT / 'work').glob(pat):
            try:
                for h in (json.loads(sf.read_text()).get('heldBack') or []):
                    if h.get('id'):
                        SUPPRESS.add(h['id'])
            except Exception:
                pass
    if SUPPRESS:
        print('抑制名单：%d 条降级事件不会被重新入库' % len(SUPPRESS))

    # 记录级抑制名单（酒庄/产区）：已判不合格被清出的实体，重跑不得复活
    SUPPRESS_REC = set()
    for sf in (ROOT / 'work').glob('quarantine-wineries-*.json'):
        try:
            for it in (json.loads(sf.read_text()).get('items') or []):
                if it.get('id'):
                    SUPPRESS_REC.add(it['id'])
        except Exception:
            pass
    if SUPPRESS_REC:
        print('抑制名单：%d 条已清出的酒庄/产区不会被重新入库' % len(SUPPRESS_REC))
    ev_ids_all = ev_ids | SUPPRESS

    if not B_SEED.exists():
        shutil.copy2(SEED, B_SEED)
    if not B_EV.exists():
        shutil.copy2(EVENTS, B_EV)

    new_region, new_winery, new_grape, new_event = [], [], [], []
    gate_log = {'date': '2026-09-21', 'blocked': [], 'flagged': [], 'skipped': []}
    report = {}

    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('verify_gate', str(ROOT / 'scripts' / 'verify-gate.py'))
    _gate_mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_gate_mod)

    for f in sorted(glob.glob(str(ROOT / 'work' / 'agents' / '*-payload.json'))):
        p = json.loads(Path(f).read_text())
        if not isinstance(p, dict) or not (p.get('regions') or p.get('wineries') or p.get('events')):
            continue
        # ---- 门禁：进库前先过闸（结构性问题硬拦，可疑项打标）----
        p, _blk, _flg = _gate_mod.gate_payload(p, http=False, known_event_ids=ev_ids_all)
        src = Path(f).name
        for x in _blk:
            x['payload'] = src; gate_log['blocked'].append(x)
        for x in _flg:
            x['payload'] = src; gate_log['flagged'].append(x)
        cc = p.get('countryCode', '?')
        stat = {'regions': 0, 'wineries': 0, 'events': 0, 'grapes': 0, 'skipped': 0}

        # ---- 品种 ----
        # 同义表：防止重跑把已归并的重复品种又建回来（data/grape-aliases.json）
        try:
            AL = json.loads((ROOT / 'data' / 'grape-aliases.json').read_text())
        except Exception:
            AL = {'byId': {}, 'byEn': {}}
        ALIAS_ID = AL.get('byId') or {}
        ALIAS_EN = {k.lower(): v for k, v in (AL.get('byEn') or {}).items()}
        grape_key = {}
        for r in recs:
            if r.get('kind') == 'grape':
                grape_key[norm(r.get('name'))] = r['id']
                grape_key[norm((r.get('data') or {}).get('en'))] = r['id']
        for k, canon in ALIAS_EN.items():
            if canon in by_id:
                grape_key[norm(k)] = canon

        for rg in p.get('regions') or []:
            rid = rg.get('id')
            if not rid:
                continue
            grapes = []
            for gid in rg.get('grapeIds') or []:
                if gid in by_id:
                    grapes.append({'id': gid, 'percent': None})
            for mg in rg.get('missingGrapes') or []:
                if isinstance(mg, str):          # 窗口有时只给品种名（字符串）
                    mg = {'name': mg, 'en': mg, 'sourceURL': rg.get('sourceURL')}
                key = norm(mg.get('en')) or norm(mg.get('name'))
                if key and key in grape_key:
                    grapes.append({'id': grape_key[key], 'percent': None})
                    continue
                gid = 'grape-%s' % (norm(mg.get('en')) or norm(mg.get('name')))[:24]
                gid = ALIAS_ID.get(gid, gid)          # 同义表优先
                if gid in by_id:
                    grapes.append({'id': gid, 'percent': None})
                    continue
                gr = {'id': gid, 'kind': 'grape', 'name': mg.get('name') or mg.get('en'),
                      'data': {'name': mg.get('name') or mg.get('en'), 'en': mg.get('en'),
                               'sourceTitle': '国家窗口采集依据页', 'sourceURL': mg.get('sourceURL') or rg.get('sourceURL'),
                               'checkedDate': CHECKED},
                      'version': 1, 'updated': NOW, 'origin': '国家窗口采集 · %s' % cc}
                recs.append(gr); by_id[gid] = gr; new_grape.append(gr)
                if key:
                    grape_key[key] = gid
                grapes.append({'id': gid, 'percent': None})
                stat['grapes'] += 1

            if rid in by_id:
                r = by_id[rid]
                d = r.setdefault('data', {})
                hist = d.setdefault('notesHistory', [])
                for k in ('sourceTitle', 'sourceURL', 'notes', 'en'):
                    if d.get(k) and d[k] != rg.get(k):
                        hist.append({'field': k, 'previousValue': d[k], 'replacedAt': NOW,
                                     'reason': '国家窗口官方口径富化（2026-09-21）'})
                for k in REGION_FIELDS:
                    if rg.get(k) not in (None, '', []):
                        d[k] = rg[k]
                d['sourceTitle'] = rg.get('sourceTitle') or d.get('sourceTitle')
                d['sourceURL'] = rg.get('sourceURL') or d.get('sourceURL')
                d['checkedDate'] = rg.get('checkedDate') or CHECKED
                if rg.get('producerDirectory'):
                    d['producerDirectory'] = rg['producerDirectory']
                if grapes:
                    d['grapes'] = grapes
                for lg, lv in (rg.get('localizations') or {}).items():
                    d.setdefault('localizations', {})[lg] = lv
                d.setdefault('originalLanguage', 'en')
                r['version'] = int(r.get('version') or 1) + 1
                r['updated'] = NOW
                r['origin'] = '国家窗口采集 · 官方协会/监管机构页（%s）' % cc
                stat['regions'] += 1
            else:
                data = {'name': rg.get('name'), 'en': rg.get('en'),
                        'country': rg.get('country') or p.get('country'),
                        'lat': rg.get('lat'), 'lng': rg.get('lng'),
                        'sourceTitle': rg.get('sourceTitle'), 'sourceURL': rg.get('sourceURL'),
                        'checkedDate': rg.get('checkedDate') or CHECKED,
                        'originalLanguage': 'en',
                        'localizations': rg.get('localizations') or {}}
                for k in REGION_FIELDS:
                    if rg.get(k) not in (None, '', []):
                        data[k] = rg[k]
                if rg.get('producerDirectory'):
                    data['producerDirectory'] = rg['producerDirectory']
                if grapes:
                    data['grapes'] = grapes
                rec = {'id': rid, 'kind': 'region', 'name': rg.get('name') or rg.get('en'),
                       'data': data, 'version': 1, 'updated': NOW,
                       'origin': '国家窗口采集 · 官方协会/监管机构页（%s）' % cc}
                recs.append(rec); by_id[rid] = rec; new_region.append(rec)
                stat['regions'] += 1

        # ---- 酒庄 ----
        for w in p.get('wineries') or []:
            wid = w.get('id')
            if not wid or wid in by_id or wid in SUPPRESS_REC:
                stat['skipped'] += 1
                continue
            key = norm(w.get('name'))
            if key and key in winery_by_name:
                stat['skipped'] += 1
                continue
            data = {k: w.get(k) for k in ('name', 'country', 'regionId', 'aliases', 'address',
                                          'website', 'lat', 'lng', 'locationPrecision',
                                          'locationSourceURL', 'sourceTitle', 'sourceURL',
                                          'checkedDate', 'notes') if w.get(k) is not None}
            data.setdefault('name', w.get('name'))
            data.setdefault('country', w.get('country') or p.get('country'))
            data.setdefault('checkedDate', CHECKED)
            rec = {'id': wid, 'kind': 'winery', 'name': w.get('name'), 'data': data,
                   'version': 1, 'updated': NOW, 'origin': '国家窗口采集 · 官方名录 × OSM/%s' % cc}
            recs.append(rec); by_id[wid] = rec
            if key:
                winery_by_name[key] = rec
            new_winery.append(rec)
            stat['wineries'] += 1

        # ---- 事件 ----
        for ev in p.get('events') or []:
            if not ev.get('id') or ev['id'] in ev_ids or ev['id'] in SUPPRESS:
                stat['skipped'] += 1
                continue
            for k in REQUIRED_EVENT:
                ev.setdefault(k, None)
            ev.setdefault('type', 'news')
            if ev['type'] not in ('news', 'event', 'harvest', 'weather', 'disaster'):
                ev['type'] = 'news'
            for k in ('lat', 'lng', 'endDate', 'publishedDate', 'dateNote', 'subtype'):
                ev.setdefault(k, None)
            ev['checkedDate'] = ev.get('checkedDate') or CHECKED
            ev_list.append(ev); ev_ids.add(ev['id']); new_event.append(ev)
            stat['events'] += 1

        report[cc] = stat

    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    ev_doc['events'] = ev_list
    EVENTS.write_text(json.dumps(ev_doc, ensure_ascii=False, indent=1))

    (ROOT / 'work' / 'gate-log-2026-09-21.json').write_text(
        json.dumps(gate_log, ensure_ascii=False, indent=1))
    print('门禁：拦 %d 条 / 标 %d 条 → work/gate-log-2026-09-21.json'
          % (len(gate_log['blocked']), len(gate_log['flagged'])))

    print('并库结果：新增 region %d / winery %d / grape %d / event %d'
          % (len(new_region), len(new_winery), len(new_grape), len(new_event)))
    print('目录总数 %d，事件总数 %d' % (len(recs), len(ev_list)))
    for cc, s in report.items():
        print('  %-8s regions+%d wineries+%d events+%d grapes+%d skipped=%d'
              % (cc, s['regions'], s['wineries'], s['events'], s['grapes'], s['skipped']))


if __name__ == '__main__':
    main()
