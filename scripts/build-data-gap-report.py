# coding: utf-8
"""生成"酒庄缺数据清单"：给 Canz 拿着去批量向酒庄索要缺失资料。

分组逻辑（关键）：
- A 组「可直接联系」：有官网或邮箱 → 现在就能发信要数据
- B 组「需先找联系人」：连官网/邮箱都没有 → 要先从协会名录/电话/社媒找人
- C 组「仅缺少量」：只差 1–2 项 → 顺手补齐

产出：
  outputs/collect/_data-gaps-2026-09-21/酒庄缺数据清单.csv   （UTF-8 BOM，Excel 直接开）
  outputs/collect/_data-gaps-2026-09-21/酒庄缺数据清单.md    （可读版 + 索要话术模板）
  outputs/collect/_data-gaps-2026-09-21/缺口汇总.json        （机读）
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
OUT = ROOT / 'outputs' / 'collect' / '_data-gaps-2026-09-21'

# 索要优先级：先要"能联系上"，再要"地图能用"，最后要"内容更丰富"
ORDER = ['邮箱', '联系人', '电话', '坐标', '官网', '地址', '酒款', '图片', '本地语资料']
TEMPLATES = {
 '中文': '您好，我们在做葡萄酒风土地图与产区资料库（风土图鉴），贵庄已被收录（{region}）。'
         '目前还缺以下资料，方便的话请回复补充：{items}。'
         '如方便，也可提供 3–5 张庄园/酒款实拍图（我们会标注来源，侵权可随时联系删除）。',
 'English': 'Hello, we maintain a wine terroir atlas and regional database (TERROIR ATLAS) and your estate is listed under {region}. '
            'We are still missing: {items}. If convenient, please send them over; 3–5 real photos of the estate/wines are also welcome '
            '(we credit the source and will remove on request).',
 'Français': 'Bonjour, nous tenons un atlas des terroirs viticoles (TERROIR ATLAS) ; votre domaine y figure pour {region}. '
             'Il nous manque : {items}. Merci de nous les transmettre si possible, ainsi que 3–5 photos réelles du domaine/cuvées '
             '(source créditée, retrait sur demande).',
 'Español': 'Hola, mantenemos un atlas de terroirs y una base de datos de regiones vitivinícolas (TERROIR ATLAS); su bodega figura en {region}. '
            'Nos faltan: {items}. Si es posible, envíelos; también agradecemos 3–5 fotos reales de la bodega/vinos '
            '(acreditamos la fuente y retiramos a petición).',
 'Italiano': 'Buongiorno, gestiamo un atlante dei terroir viticoli (TERROIR ATLAS); la vostra azienda è inserita per {region}. '
             'Ci mancano: {items}. Se possibile inviateli; gradite anche 3–5 foto reali di cantina/vini '
             '(citiamo la fonte, rimozione su richiesta).',
 'Deutsch': 'Guten Tag, wir führen einen Weinbergs-/Terroir-Atlas (TERROIR ATLAS); Ihr Weingut ist für {region} gelistet. '
            'Uns fehlen noch: {items}. Bitte senden Sie sie uns wenn möglich; willkommen sind auch 3–5 echte Fotos von Weingut/Weinen '
            '(Quelle wird genannt, Löschung auf Anfrage).',
 'Português': 'Olá, mantemos um atlas de terroirs e base de dados regional (TERROIR ATLAS); a vossa quinta consta em {region}. '
              'Faltam-nos: {items}. Se possível envie; agradecemos também 3–5 fotos reais da quinta/vinhos '
              '(creditamos a fonte, remoção a pedido).',
}
LANG_BY_COUNTRY = {'法国': 'Français', '西班牙': 'Español', '意大利': 'Italiano', '德国': 'Deutsch',
                   '奥地利': 'Deutsch', '瑞士': 'Deutsch', '葡萄牙': 'Português', '巴西': 'Português',
                   '中国': '中文', '日本': 'English', '美国': 'English', '加拿大': 'English',
                   '澳大利亚': 'English', '新西兰': 'English', '南非': 'English', '英国': 'English',
                   '格鲁吉亚': 'English', '希腊': 'English', '匈牙利': 'English', '阿根廷': 'Español',
                   '智利': 'Español', '乌拉圭': 'Español', '墨西哥': 'Español', '黎巴嫩': 'English',
                   '克罗地亚': 'English', '斯洛文尼亚': 'English', '以色列': 'English'}


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    region_name = {r['id']: (r.get('data') or {}).get('name') or r.get('name')
                   for r in recs if r.get('kind') == 'region'}
    country_of = {r['id']: (r.get('data') or {}).get('country') for r in recs if r.get('kind') == 'region'}
    wines_by_winery = Counter()
    for r in recs:
        if r.get('kind') == 'wine':
            wid = (r.get('data') or {}).get('wineryId')
            if wid:
                wines_by_winery[wid] += 1

    rows = []
    for r in recs:
        if r.get('kind') != 'winery':
            continue
        d = r.get('data') or {}
        rid = d.get('regionId')
        items = []
        if not d.get('email'):
            items.append('邮箱')
        if not d.get('contactPerson'):
            items.append('联系人')
        if not d.get('phone'):
            items.append('电话')
        if d.get('lat') is None or d.get('lng') is None:
            items.append('坐标')
        if not d.get('website'):
            items.append('官网')
        if not d.get('address'):
            items.append('地址')
        if wines_by_winery.get(r['id'], 0) == 0:
            items.append('酒款')
        if not (d.get('images') or []):
            items.append('图片')
        if not (d.get('localizations') or {}):
            items.append('本地语资料')
        items.sort(key=lambda x: ORDER.index(x) if x in ORDER else 99)
        reachable = bool(d.get('website') or d.get('email'))
        group = ('C 仅缺少量' if 1 <= len(items) <= 2 else 'A 可直接联系') if reachable else 'B 需先找联系人'
        rows.append({
            'group': group,
            'country': d.get('country') or country_of.get(rid) or '',
            'region': region_name.get(rid, rid or ''),
            'regionId': rid,
            'name': r.get('name'),
            'id': r['id'],
            'website': d.get('website') or '',
            'email': d.get('email') or '',
            'phone': d.get('phone') or '',
            'address': d.get('address') or '',
            'lat': d.get('lat'), 'lng': d.get('lng'),
            'wines': wines_by_winery.get(r['id'], 0),
            'images': len(d.get('images') or []),
            'missing': items,
            'missingCount': len(items),
            'sourceURL': d.get('sourceURL') or '',
            'askFirst': '、'.join(items[:3]),
        })

    # ---------- CSV ----------
    csv_path = OUT / '酒庄缺数据清单.csv'
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['组', '国家', '产区', '酒庄（原语种名）', '官网', '邮箱', '电话', '地址',
                    '有坐标', '酒款数', '图片数', '缺失项', '缺几项', '最该先问的3件', '来源页', '记录ID'])
        for r in sorted(rows, key=lambda x: (x['group'], x['country'], -x['missingCount'], x['name'])):
            w.writerow([r['group'], r['country'], r['region'], r['name'], r['website'], r['email'],
                        r['phone'], r['address'], '有' if r['lat'] is not None else '无',
                        r['wines'], r['images'], '、'.join(r['missing']), r['missingCount'],
                        r['askFirst'], r['sourceURL'], r['id']])

    # ---------- 汇总 ----------
    by_country = defaultdict(lambda: {'total': 0, 'missing': Counter(), 'reachable': 0})
    for r in rows:
        b = by_country[r['country']]
        b['total'] += 1
        if r['website'] or r['email']:
            b['reachable'] += 1
        for m in r['missing']:
            b['missing'][m] += 1
    summary = {
        'date': '2026-09-21',
        'wineriesTotal': len(rows),
        'groups': dict(Counter(r['group'] for r in rows)),
        'missingTotals': dict(Counter(m for r in rows for m in r['missing'])),
        'byCountry': {k: {'total': v['total'], 'reachable': v['reachable'],
                          'missing': dict(v['missing'])} for k, v in
                      sorted(by_country.items(), key=lambda x: -x[1]['total'])},
    }
    (OUT / '缺口汇总.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))

    # ---------- Markdown ----------
    L = ['# 酒庄缺数据清单（可拿去批量索要）', '',
         '> 生成日期：%s ｜ 酒庄总数：**%d** ｜ 数据源：`data/catalog-seed.json`（%d 条记录 / %d 个产区）'
         % (datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M'), len(rows),
            len(recs), len(region_name)), '',
         '## 怎么用这份清单', '',
         '1. **A 组（可直接联系）**：有官网或邮箱 → 现在就能发信/发微信要数据，按国家用对应语言模板（见文末）。',
         '2. **B 组（需先找联系人）**：连官网/邮箱都没有 → 先从产区协会名录、酒庄电话或社媒把人找到，再要数据。',
         '3. **C 组（仅缺 1–2 项）**：顺手补齐，投入最小、收益最快。',
         '4. 表格文件 `酒庄缺数据清单.csv` 可用 Excel 直接打开（已带 UTF-8 BOM，中文不乱码），'
         '按「组」「国家」「缺几项」排序即可分批推进。', '',
         '## 总览', '',
         '| 分组 | 酒庄数 |', '| --- | --- |']
    for k, v in summary['groups'].items():
        L.append('| %s | %d |' % (k, v))
    L += ['', '| 缺失项 | 涉及酒庄数 |', '| --- | --- |']
    for k, v in sorted(summary['missingTotals'].items(), key=lambda x: -x[1]):
        L.append('| %s | %d |' % (k, v))
    L += ['', '## 按国家（前 25 国）', '',
          '| 国家 | 酒庄 | 可联系上 | 缺坐标 | 缺官网 | 缺邮箱 | 缺酒款 | 缺图片 | 缺本地语资料 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c, v in list(summary['byCountry'].items())[:25]:
        m = v['missing']
        L.append('| %s | %d | %d | %d | %d | %d | %d | %d | %d |' % (
            c, v['total'], v['reachable'], m.get('坐标', 0), m.get('官网', 0), m.get('邮箱', 0),
            m.get('酒款', 0), m.get('图片', 0), m.get('本地语资料', 0)))
    L += ['', '## 明细（按缺失项数量排序，前 120 家）', '']
    for g in ('A 可直接联系', 'B 需先找联系人', 'C 仅缺少量'):
        sel = [r for r in rows if r['group'] == g]
        sel.sort(key=lambda x: (-x['missingCount'], x['name']))
        L += ['### %s（%d 家）' % (g, len(sel)), '',
              '| 酒庄 | 国家 | 产区 | 缺几项 | 缺失项 | 官网 |', '| --- | --- | --- | --- | --- | --- |']
        for r in sel[:120]:
            L.append('| %s | %s | %s | %d | %s | %s |' % (
                r['name'], r['country'], r['region'], r['missingCount'],
                '、'.join(r['missing']), r['website'] or '—'))
        if len(sel) > 120:
            L.append('| … | 其余 %d 家见 CSV |  |  |  |  |' % (len(sel) - 120))
        L.append('')
    L += ['## 索要话术模板（按酒庄所在国语言选）', '']
    for lang, t in TEMPLATES.items():
        L += ['**%s**' % lang, '', '> ' + t, '']
    L += ['## 说明与边界', '',
          '- 缺失项判定口径：邮箱/联系人/电话/坐标/官网/地址 为空即算缺；「酒款」= 库里没有该庄的 wine 记录；'
          '「图片」= 没有采集到该庄图片（含因 robots/403 而未采的情况）；「本地语资料」= 没有 localizations。',
          '- 向酒庄索要数据时**不要**承诺任何商业回报或合作条件（本任务只做采集）；图片请说明"标注来源、侵权可联系删除"。',
          '- 收到回复后按 `采集规格-网站字段对照.md` 的字段要求录入，并记 `sourceURL` 与 `checkedDate`。']
    (OUT / '酒庄缺数据清单.md').write_text('\n'.join(L) + '\n')
    print('酒庄 %d 家；分组：%s' % (len(rows), summary['groups']))
    print('缺失项总计：', summary['missingTotals'])
    print('产出：%s' % OUT)


if __name__ == '__main__':
    main()
