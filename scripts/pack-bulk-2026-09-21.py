# coding: utf-8
"""收束：把 2026-09-20/21 多国窗口的成果汇总成一份批量交付包。

产出：
  outputs/collect/_bulk-2026-09-21/
    00-总览.md                 各国/各产区数字总表 + 缺口
    region-summary.json        机读总表（产区/酒庄/酒款/年份/图片/来源数）
    events-additions.json      本轮新增事件（含无法补齐而降级的 heldBack）
    discrepancies-all.json     各产区口径冲突汇总
    sources-all.json           各产区来源汇总（含 language 字段）
    知识库导入清单.json         全部标"待审核"
    HANDOFF.md                 给内容工作室：采到什么、边界、缺什么、图片权限
    README-包内说明.txt
  多国产区批量采集包-2026-09-21.zip（含上述 + 各产区目录下的 JSON/MD 与 images/）
并交付到 wine-content-studio/outputs/collect/2026-09-21/
"""
import json
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
EVENTS = ROOT / 'data' / 'events.json'
OUT = ROOT / 'outputs' / 'collect' / '_bulk-2026-09-21'
DATE = '2026-09-21'


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    ev = json.loads(EVENTS.read_text())['events']

    payloads = []
    for f in sorted((ROOT / 'work' / 'agents').glob('*-payload.json')):
        if 'verification' in f.name:      # 验证类 payload 不是采集结果，不进总览
            continue
        payloads.append(json.loads(f.read_text()))

    region_ids, winery_ids, new_events = [], set(), []
    per_region_notes = {}
    for p in payloads:
        for rg in p.get('regions') or []:
            rid = rg.get('id')
            if rid:
                region_ids.append(rid)
                per_region_notes[rid] = (rg.get('notes') or '')[:300]
        for w in p.get('wineries') or []:
            if w.get('id'):
                winery_ids.add(w['id'])
        for e in p.get('events') or []:
            if e.get('id'):
                new_events.append(e['id'])

    by_region = defaultdict(lambda: {'wineries': 0, 'wines': 0, 'vintages': 0, 'images': 0})
    country_of = {}
    for r in recs:
        d = r.get('data') or {}
        rid = d.get('regionId')
        if r.get('kind') == 'winery' and rid:
            by_region[rid]['wineries'] += 1
            if d.get('country'):
                country_of[rid] = d['country']
        elif r.get('kind') == 'wine' and rid:
            by_region[rid]['wines'] += 1
    rid_of_wine = {r['id']: (r.get('data') or {}).get('regionId')
                   for r in recs if r.get('kind') == 'wine'}
    for r in recs:
        if r.get('kind') == 'vintage':
            rid = rid_of_wine.get((r.get('data') or {}).get('wineId'))
            if rid:
                by_region[rid]['vintages'] += 1
    for r in recs:
        if r.get('kind') == 'region':
            by_region[r['id']]

    img_count = {}
    for rid in set(region_ids):
        p = ROOT / 'outputs' / 'collect' / rid / 'images'
        n = 0
        if p.exists():
            n = sum(1 for f in p.rglob('*') if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.avif'))
        img_count[rid] = n
        by_region[rid]['images'] = n

    summary = []
    rid2country = {r['id']: (r.get('data') or {}).get('country')
                   for r in recs if r.get('kind') == 'region'}
    for p in payloads:
        for rg in p.get('regions') or []:
            rid = rg.get('id')
            s = dict(by_region.get(rid, {}))
            summary.append({
                'country': rid2country.get(rid) or p.get('country'),
                'countryCode': p.get('countryCode'),
                'regionId': rid, 'name': rg.get('name'), 'en': rg.get('en'),
                'existingRegionRecord': bool(rg.get('existing')),
                'sourceURL': rg.get('sourceURL'),
                'producerDirectory': (rg.get('producerDirectory') or {}).get('url'),
                **s,
                'notes': per_region_notes.get(rid, ''),
            })

    # 事件：只挑本轮的
    ev_by_id = {e['id']: e for e in ev}
    todays_events = [ev_by_id[i] for i in new_events if i in ev_by_id]
    held = []
    hp = ROOT / 'work' / 'events-heldback-2026-09-21.json'
    if hp.exists():
        held = json.loads(hp.read_text()).get('heldBack') or []
    # 各窗口自己的 heldBack
    for p in payloads:
        for h in p.get('heldBack') or []:
            held.append({'id': None, 'title': h.get('title'), 'reason': h.get('reason'),
                         'sourceURL': h.get('sourceURL'),
                         'factStoredWhere': h.get('factStoredWhere'),
                         'country': p.get('country')})

    (OUT / 'region-summary.json').write_text(json.dumps({
        'date': DATE, 'note': '本轮多国窗口采集总表（按国家→产区）',
        'catalogTotals': {'records': len(recs), 'events': len(ev),
                          'regionsTouched': len(set(region_ids)),
                          'wineriesAdded': len(winery_ids)},
        'regions': summary,
    }, ensure_ascii=False, indent=1))
    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': DATE, 'events': todays_events, 'heldBack': held,
        'note': '事件 startDate 均为可核实的发生日期；无法补齐必填字段的已降级进 heldBack，不是遗漏。',
    }, ensure_ascii=False, indent=1))

    disc, srcs = [], []
    for p in payloads:
        for d in p.get('discrepancies') or []:
            d = dict(d); d['country'] = p.get('country'); disc.append(d)
        for s in p.get('sources') or []:
            s = dict(s); s['country'] = p.get('country'); srcs.append(s)
    for rid in region_ids:
        dp = ROOT / 'outputs' / 'collect' / rid / 'discrepancies.json'
        if dp.exists():
            try:
                for d in (json.loads(dp.read_text()).get('items') or []):
                    d = dict(d); d['regionId'] = rid; disc.append(d)
            except Exception:
                pass
    (OUT / 'discrepancies-all.json').write_text(json.dumps(
        {'date': DATE, 'count': len(disc), 'items': disc}, ensure_ascii=False, indent=1))
    (OUT / 'sources-all.json').write_text(json.dumps(
        {'date': DATE, 'count': len(srcs), 'sources': srcs}, ensure_ascii=False, indent=1))

    kb = {'date': DATE, 'status': '待审核', 'rule': '一律先标"待审核"，经审核流程后才可标"已审核"',
          'entries': [{'type': 'region', 'id': s['regionId'], 'name': s['name'],
                       '审核状态': '待审核'} for s in summary]}
    (OUT / '知识库导入清单.json').write_text(json.dumps(kb, ensure_ascii=False, indent=1))

    # 总览 md
    byc = defaultdict(list)
    for s in summary:
        byc[s['country'] or '未标注'].append(s)
    L = ['# 多国产区批量采集 · 总览（%s）' % DATE, '',
         '目标：给风土图鉴网站补齐各国空壳产区的内容与图片。每个国家由独立"窗口"采集，'
         '统一并库（避免并发写冲突）。', '',
         '## 数字总表', '',
         '| 国家 | 产区 | 酒庄 | 酒款 | 年份 | 图片 | 官方名录入口 |',
         '| --- | --- | --- | --- | --- | --- | --- |']
    for c in sorted(byc):
        for s in sorted(byc[c], key=lambda x: -x['wineries']):
            L.append('| %s | %s（%s） | %d | %d | %d | %d | %s |' % (
                c, s['name'], s['regionId'], s['wineries'], s['wines'], s['vintages'],
                s['images'], s['producerDirectory'] or '—'))
    L += ['', '## 合计', '',
          '- 目录记录：%d 条（其中产区 %d、酒庄 %d+）' % (len(recs), len(set(region_ids)), len(winery_ids)),
          '- 本轮新增事件：%d 条；降级进 heldBack：%d 条' % (len(todays_events), len(held)),
          '- 口径冲突记录：%d 条；来源：%d 条' % (len(disc), len(srcs)),
          '- 本轮产区图片：%d 张（详见各产区 images/ 与其 manifest）' % sum(img_count.values()),
          '', '## 缺口（如实说明，不要当成"不存在"）', '']
    gaps = []
    for p in payloads:
        n = str(p.get('notes') or '').strip()
        if n:
            gaps.append('- **%s**：%s' % (p.get('country'), n[:400]))
    L += gaps or ['- 各窗口未报告额外缺口']
    (OUT / '00-总览.md').write_text('\n'.join(L) + '\n')

    handoff = """# 多国产区批量采集 · 交接说明（%s）

## 采到了什么
本轮由多个"国家窗口"并行采集，统一并库，覆盖 %d 个产区、新增/补齐 %d 家酒庄、
%d 条事件（另 %d 条按硬规矩降级进 heldBack）。
逐区数字与官方名录入口见 `00-总览.md` 与 `region-summary.json`。

## 写作红线（内容工作室必读）
1. **面积/产量口径冲突的一律留空**：哪些冲突见 `discrepancies-all.json`。
   不要写"最大/最小/最古老"这类没有来源支撑的排序论断。
2. **事件只有可核实发生日期的才登记**；`heldBack` 是主动降级，不是遗漏。
   不要拿报道日期当发生日期。
3. **酒款图必须按瓶标读出的产区归属**：文件名不作判据。
   产区级图（`images/region/`）里可能混有活动海报、logo、人物照等，配图前先看 manifest 的 role。
4. **localizations**：只有官方对应语种页面存在的才标 verified；其余为 draft 或留空。
   不要把界面语言切换当成译文证据。
5. 酒庄坐标来源与精度写在 `data.locationPrecision` / `locationSourceURL`，
   不要自造坐标或把行政村中心当酒庄位置。

## 图片权限与下架
- 全部来自产区协会/监管机构或酒庄官网的公开页面；站点统一标注「均为合作上传，如侵权可联系删除」。
- 未去水印、未放大、未声称版权。每张图带 来源页/直链/抓取日/字节数/SHA-256/真实像素，
  可按 `图片溯源与下架索引.md` 逐张定位并删除；按酒庄/按产区分目录，便于整家整区下架。

## 明确没有的东西
- 未做社媒发布；未动站点成员/OWNER_EMAIL/数据库。
- 部分产区官方不公布面积或生产者数 → 字段留空，见 discrepancies（不是没查，是官方没有）。
- 部分官网图库很小或全为 logo → 该产区图片数偏少，已在总览中标注。
"""
    (OUT / 'HANDOFF.md').write_text(handoff % (DATE, len(set(region_ids)), len(winery_ids),
                                              len(todays_events), len(held)))
    (OUT / 'README-包内说明.txt').write_text(
        '多国产区批量采集包 — %s\n\n'
        '- 00-总览.md：先读这个（各国/各产区数字）\n'
        '- region-summary.json / events-additions.json / discrepancies-all.json / sources-all.json\n'
        '- 知识库导入清单.json：全部待审核\n'
        '- HANDOFF.md：写作红线与图片权限\n'
        '- <region>/：各产区自己的 JSON/MD 与 images/（含 manifest 与下架索引）\n' % DATE)

    # 打包：汇总文件 + 各产区目录（含图片）
    zpath = ROOT / 'outputs' / 'collect' / ('多国产区批量采集包-%s.zip' % DATE)
    n_files = 0
    with zipfile.ZipFile(zpath, 'w', allowZip64=True) as z:
        for f in sorted(OUT.iterdir()):
            if f.is_file():
                z.write(f, f.name, compress_type=zipfile.ZIP_DEFLATED)
                n_files += 1
        for rid in sorted(set(region_ids)):
            base = ROOT / 'outputs' / 'collect' / rid
            if not base.exists():
                continue
            for f in sorted(base.rglob('*')):
                if f.is_file():
                    rel = '%s/%s' % (rid, f.relative_to(base).as_posix())
                    stored = f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.avif')
                    z.write(f, rel, compress_type=zipfile.ZIP_STORED if stored
                            else zipfile.ZIP_DEFLATED)
                    n_files += 1
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        print('zip: %s（%.1f MB，%d 个文件，testzip=%s）'
              % (zpath.name, zpath.stat().st_size / 1e6, n_files, bad))

    studio = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / DATE
    if not studio.exists():
        studio.mkdir(parents=True)
    (studio / zpath.name).write_bytes(zpath.read_bytes())
    for f in sorted(OUT.iterdir()):
        if f.is_file():
            (studio / ('批量采集-' + f.name)).write_text(f.read_text())
    print('交付:', studio)


if __name__ == '__main__':
    main()
