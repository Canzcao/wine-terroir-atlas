# coding: utf-8
"""003期 Cornas 增补轮 5：从读标复核证据录入 wine / vintage 级结构化记录。

证据来源：outputs/collect/cornas/images/wine-image-manifest.json 中
classificationMethod == "agent-visual-review" 且 appellation == "Cornas" 的 34 张图
（读标复核完成于 2026-09-19）。本脚本：

1. 按下表把 34 张读标图归并成 wine 记录（同庄同名 cuvée 合并）；
   年份可读的 3 条另录 vintage 记录。
2. 每条 wine 从 manifest 反查证据图的 sourcePage / sourceName，写进来源字段。
3. 幂等并库进 data/catalog-seed.json（按 id 去重，重跑不重复加）。
4. 把新增记录写进 outputs/collect/cornas/catalog-additions.json 的
   wineVintageAdditions 段，并更新 counts。

 grapes 口径：Cornas AOC 红葡萄酒法定为单一西拉（INAO cahier des charges），
 percent 按产区法定口径标 100，不是逐瓶读标。年份（vintage）不做此推导，
 无标签/官方年份配方时登记 grapes 为空并在 note 说明。
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
MANIFEST = ROOT / 'outputs' / 'collect' / 'cornas' / 'images' / 'wine-image-manifest.json'
OUT_CA = ROOT / 'outputs' / 'collect' / 'cornas' / 'catalog-additions.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-cornas-wines-2026-09-20.json'

SYRAH = 'grape-36404f2e5476'
CHECKED = '2026-09-19'  # 读标视觉复核完成日

# (wine_id, name, winery_id, cuvée 中文说明, [证据图 (slug, file)], vintage 年份或 None)
WINES = [
    ('wine-cornas-dumien-serrette-cornas', 'Cornas',
     'winery-cornas-domaine-dumien-serrette', '标面仅 CORNAS，无 cuvée 名',
     [('domaine-dumien-serrette', '01-Domaine_Serrette_058.jpg'),
      ('domaine-dumien-serrette', '02-Domaine_Serrette_057.jpg'),
      ('domaine-dumien-serrette', '03-Domaine_Serrette_059.jpg')], None),
    ('wine-cornas-courbis-les-eygats', 'Cornas Les Eygats',
     'winery-cornas-domaine-courbis', '单一园 cuvée',
     [('domaine-courbis', '18-eygats.png')], None),
    ('wine-cornas-courbis-la-sabarotte', 'Cornas La Sabarotte',
     'winery-cornas-domaine-courbis', '单一园 cuvée',
     [('domaine-courbis', '19-sabarotte.png')], None),
    ('wine-cornas-courbis-champelrose', 'Cornas Champelrose',
     'winery-cornas-domaine-courbis', '单一园 cuvée',
     [('domaine-courbis', '20-champelrose.png')], None),
    ('wine-cornas-de-lorient-cornas', 'Cornas',
     'winery-cornas-domaine-de-lorient', '标面仅 CORNAS，无 cuvée 名',
     [('domaine-de-lorient', '02-bouteillevin-cornas-domaine-lorient.png')], None),
    ('wine-cornas-jean-esprit-les-arlettes', 'Cornas Les Arlettes',
     'winery-cornas-domaine-jean-esprit', 'cuvée；文件名含 2025 但标面年份未读出，不作为年份依据',
     [('domaine-jean-esprit', '06-bouteille-arlettes-2025.png')], None),
    ('wine-cornas-remy-nodin-les-eygas', 'Cornas Les Eygas',
     'winery-cornas-domaine-remy-nodin', '熟成酒款 cuvée',
     [('domaine-remy-nodin', '06-cornas-les-eygas-remy-nodin.jpg')], None),
    ('wine-cornas-tunnel-cornas', 'Cornas',
     'winery-condrieu-robert-stephane', 'Domaine du Tunnel（Stéphane Robert）；该庄以 condrieu 记录在库，酒挂同一酒庄点位',
     [('robert-stephane', '01-cornas-2016-domaine-du-tunnel.png')], None),
    ('wine-cornas-vendome-baryte', 'Cornas Baryte',
     'winery-cornas-domaine-vendome', 'cuvée',
     [('domaine-vendome', '18-design-sans-titre-1.png'),
      ('domaine-vendome', '21-baryte.png')], None),
    ('wine-cornas-coulet-billes-noires', 'Cornas Billes Noires',
     'winery-cornas-domaine-du-coulet', 'Matthieu Barret cuvée',
     [('domaine-du-coulet', '02-billesnoires_d12b9f7d-822b-491a-b669-5703f1b07803.jpg')], None),
    ('wine-cornas-coulet-brise-cailloux', 'Cornas Brise Cailloux',
     'winery-cornas-domaine-du-coulet', 'Matthieu Barret cuvée',
     [('domaine-du-coulet', '03-brisecailloux.jpg')], None),
    ('wine-cornas-coulet-geniale-patronne', 'Cornas Géniale Patronne',
     'winery-cornas-domaine-du-coulet', 'Matthieu Barret cuvée',
     [('domaine-du-coulet', '07-geniale_patronne_copie.jpg')], None),
    ('wine-cornas-voge-vieilles-fontaines', 'Cornas Les Vieilles Fontaines',
     'winery-cornas-domaine-alain-voge', 'cuvée；读标年份 2011',
     [('domaine-alain-voge', '06-vins-6-2.jpg.jpg'),
      ('domaine-alain-voge', '17-vins-6-1.jpg.jpg')], 2011),
    ('wine-cornas-voge-chapelle-saint-pierre', 'Cornas Chapelle Saint-Pierre',
     'winery-cornas-domaine-alain-voge', 'cuvée；读标年份 2018',
     [('domaine-alain-voge', '07-vins-7-2.jpg.jpg'),
      ('domaine-alain-voge', '18-vins-7-1.jpg.jpg')], 2018),
    ('wine-cornas-mucyn-hypsos', 'Cornas Hypsos',
     'winery-cornas-domaine-mucyn', 'cuvée',
     [('domaine-mucyn', '06-cornas-hypsos.png'),
      ('domaine-mucyn', '25-Hypsos_FB-1.png')], None),
    ('wine-cornas-mucyn-cornas', 'Cornas',
     'winery-cornas-domaine-mucyn', '标面仅 CORNAS，无 cuvée 名',
     [('domaine-mucyn', '26-Cornas.png')], None),
    ('wine-cornas-robin-gilles-cornas', 'Cornas',
     'winery-cornas-robin-gilles', 'Gilles Robin；读标年份 2023',
     [('robin-gilles', '20-CORNAS-1-scaled-e1761300030797.jpg')], 2023),
    ('wine-cornas-colombo-terres-brulees', 'Cornas Terres Brûlées',
     'winery-cornas-vins-jean-luc-colombo', 'cuvée',
     [('vins-jean-luc-colombo', '03-Design-sans-titre-3.jpg')], None),
    ('wine-cornas-colombo-les-ruchets', 'Cornas Les Ruchets',
     'winery-cornas-vins-jean-luc-colombo', 'cuvée',
     [('vins-jean-luc-colombo', '04-Design-sans-titre-4.jpg')], None),
    ('wine-cornas-colombo-la-louvee', 'Cornas La Louvée',
     'winery-cornas-vins-jean-luc-colombo', 'cuvée',
     [('vins-jean-luc-colombo', '05-Design-sans-titre-5.jpg')], None),
    ('wine-cornas-colombo-vallon-arde', 'Cornas Vallon de l’Ardé',
     'winery-cornas-vins-jean-luc-colombo',
     '标面读作 VALLON DE L’ARDE，完整拼写以酒庄官方为准（不猜译）',
     [('vins-jean-luc-colombo', '20-Design-sans-titre-25.jpg')], None),
    ('wine-cornas-colombo-bernardines', 'Cornas Les Bernardines',
     'winery-cornas-vins-jean-luc-colombo',
     '木盒六支装盒盖印 cuvée 名，属包装证据',
     [('vins-jean-luc-colombo', '24-verticale-ruchets.jpg')], None),
    ('wine-cornas-alexandrins-cornas', 'Cornas',
     'winery-cornas-maison-et-domaines-les-alexandrins', '标面仅 CORNAS，无 cuvée 名',
     [('maison-et-domaines-les-alexandrins', '13-MLA_CORNAS_RG_2561851c-6e9e-466f-b4e7-c63aced36ebe.jpg')], None),
    ('wine-cornas-gaillard-cornas', 'Cornas',
     'winery-condrieu-domaine-pierre-gaillard', '该庄以 condrieu 记录在库，酒挂同一酒庄点位',
     [('domaine-pierre-gaillard', '08-Pierre-cornas-low-1.png')], None),
    ('wine-cornas-cheze-cornas', 'Cornas',
     'winery-cornas-domaine-cheze', 'Louis Chèze；标面仅 CORNAS，无 cuvée 名',
     [('domaine-cheze', '15-cornas.png')], None),
    ('wine-cornas-villard-jouvet', 'Cornas Jouvet',
     'winery-condrieu-domaine-francois-villard', '酒标扫描件；该庄以 condrieu 记录在库',
     [('domaine-francois-villard', '23-Jouvet.jpg')], None),
]


def build():
    manifest = json.loads(MANIFEST.read_text())
    page_by_key = {}
    for pr in manifest['producers']:
        for im in pr.get('images') or []:
            page_by_key[(pr['slug'], im['file'])] = im

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    wines, vintages = [], []
    for wid, name, winery_id, cuvee_note, evidence, year in WINES:
        ev_info, pages = [], []
        for slug, f in evidence:
            im = page_by_key.get((slug, f))
            if not im:
                raise SystemExit('证据图不在 manifest：%s|%s' % (slug, f))
            ev_info.append('images/%s/%s' % (slug, f))
            sp = im.get('sourcePage')
            if sp and sp not in pages:
                pages.append(sp)
        notes = ('读标证据（视觉复核 %s，classificationMethod=agent-visual-review）：%s。'
                 '证据图：%s。%s' % (CHECKED, cuvee_note, '、'.join(ev_info),
                                    cuvee_note if '不猜译' in cuvee_note else ''))
        wines.append({
            'id': wid, 'kind': 'wine', 'name': name,
            'data': {
                'name': name, 'country': '法国', 'wineryId': winery_id,
                'regionId': 'cornas',
                'grapes': [{'id': SYRAH, 'percent': 100}],
                'grapeNote': 'Cornas AOC 红葡萄酒法定为单一西拉（INAO cahier des charges）；'
                             'percent 按产区法定口径标注 100，非逐瓶读标。',
                'sourceTitle': page_by_key[(evidence[0][0], evidence[0][1])].get(
                    'sourceName', '酒庄官网读标证据'),
                'sourceURL': pages[0],
                'checkedDate': CHECKED,
                'notes': notes.strip(),
                'evidenceImages': ev_info,
                'vintageEvidence': year or None,
            },
            'version': 1, 'updated': now,
            'origin': '官网图片读标视觉复核（agent-visual-review）',
        })
        if year:
            vintages.append({
                'id': wid.replace('wine-cornas-', 'vintage-cornas-') + '-%d' % year,
                'kind': 'vintage', 'name': '%s %d' % (name, year),
                'data': {
                    'name': '%s %d' % (name, year), 'country': '法国',
                    'wineId': wid, 'yearType': 'vintage', 'year': year,
                    'sourceTitle': page_by_key[(evidence[0][0], evidence[0][1])].get(
                        'sourceName', '酒庄官网读标证据'),
                    'sourceURL': pages[0],
                    'checkedDate': CHECKED,
                    'notes': '年份为瓶标可读年份（视觉复核 %s，evidenceLevel=label-readable）。'
                             '该年份品种比例无标签/官方标注，不推导，登记为空。证据图：%s。'
                             % (CHECKED, '、'.join(ev_info)),
                    'evidenceImages': ev_info,
                },
                'version': 1, 'updated': now,
                'origin': '官网图片读标视觉复核（agent-visual-review）',
            })
    return wines, vintages


def main():
    wines, vintages = build()
    print('wine records: %d, vintage records: %d' % (len(wines), len(vintages)))

    seed = json.loads(SEED.read_text())
    if not BACKUP.exists():
        shutil.copy2(SEED, BACKUP)
        print('backup ->', BACKUP)
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    ids = {r['id'] for r in recs}
    added_w = added_v = 0
    for r in wines + vintages:
        if r['id'] in ids:
            print('  已存在，跳过:', r['id'])
            continue
        recs.append(r)
        ids.add(r['id'])
        added_w += r['kind'] == 'wine'
        added_v += r['kind'] == 'vintage'
    if isinstance(seed, list):
        seed = recs
    else:
        seed['records'] = recs
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    print('merged: +%d wine, +%d vintage (catalog now %d)' % (added_w, added_v, len(recs)))

    # 更新采集包 catalog-additions
    ca = json.loads(OUT_CA.read_text())
    ca['wineVintageAdditions'] = {
        'date': '2026-09-20',
        'round': '增补轮 5',
        'method': '把 09-19 读标复核（agent-visual-review）确认的 Cornas 酒款图归并为 wine 记录；'
                  '年份可读的另录 vintage（evidenceLevel=label-readable）。',
        'grapesConvention': 'Cornas AOC 红 = 法定单一西拉（INAO cahier des charges），percent 标 100；'
                            'vintage 不做品种比例推导。',
        'wines': [r for r in wines if r['id'] in ids],
        'vintages': [r for r in vintages if r['id'] in ids],
        'evidenceBanked': [
            'Domaine du Tunnel Saint-Péray Marsanne 2007（读标可读年份）已攒证据，'
            '留给 Saint-Péray 增补轮录入，不混入本期 Cornas 统计。',
            'Cornas 风土剖面示意图（domaine-du-coulet|17-terreCornas.png，document-map）不转 wine 记录。',
            'Gilles Robin 2024 白（VIOGNIER/MARSANNE，标面无 AOC）等读不出产区的图不入库。',
        ],
    }
    c = ca.setdefault('counts', {})
    c['wineRecords'] = sum(1 for r in ca['wineVintageAdditions']['wines'])
    c['vintageRecords'] = sum(1 for r in ca['wineVintageAdditions']['vintages'])
    OUT_CA.write_text(json.dumps(ca, ensure_ascii=False, indent=1))
    print('catalog-additions updated:', OUT_CA)


if __name__ == '__main__':
    main()
