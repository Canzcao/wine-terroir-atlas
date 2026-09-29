# coding: utf-8
"""004期 Hermitage 首批采集（partial）。

做法（editorial-plan hermitage 条目的既定方案起步）：
- 官方口径：Inter Rhône Cru 页（2025 年数字）+ INAO cahier des charges 链接。
- 首批酒款：不扫名录，先录入 003 期 Cornas 图片复核中已读标确认 HERMITAGE 的
  6 张图（agent-visual-review，2026-09-19），归并为 6 条 wine + 1 条 vintage。
- 新增品种记录：Marsanne / Roussanne（白 Hermitage 与北罗讷后续期次都要用）。
- 新增 region 记录（id=hermitage）：坐标留 null，待 OSM 实体检索后再补。
- 面积口径冲突：Inter Rhône 137 ha（2025）为准，百度百科 140 ha、SommSelect
  ~135/122 ha 的差异全部进 discrepancies.json。

幂等：按 id 去重，重跑不重复加记录；每次运行前备份 catalog-seed。
"""
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-hermitage-firstbatch-2026-09-20.json'
OUT = ROOT / 'outputs' / 'collect' / 'hermitage'

SYRAH = 'grape-36404f2e5476'
INTER_RHONE = 'https://www.vins-rhone.com/en/cotes-du-rhone-cru-aoc-hermitage'
INAO_SPEC = ('https://info.agriculture.gouv.fr/boagri/'
             'document_administratif-44a11782-ba80-4c0e-85ef-6acd35675371/telechargement')
CHECKED = '2026-09-20'

# (wine_id, name, winery_id, 颜色或 None, cuvée 说明, 证据图, vintage 或 None)
WINES = [
    ('wine-hermitage-jaboulet-la-maison-bleue', 'Hermitage La Maison Bleue',
     'winery-cornas-domaine-paul-jaboulet-aine', None,
     '标面读作 HERMITAGE「La Maison Bleue」（石头墙上 lifestyle 瓶照）；'
     'Paul Jaboulet Aîné 该庄以 cornas 记录在库，酒挂同一酒庄点位；瓶身颜色未读出，品种不填',
     ('domaine-paul-jaboulet-aine', '08-IMG_4009_retouche-large-Modifier.jpg'), None),
    ('wine-hermitage-alexandrins-blanc', 'Hermitage Blanc',
     'winery-cornas-maison-et-domaines-les-alexandrins', 'white',
     '标面 HERMITAGE，白（Maison Les Alexandrins）',
     ('maison-et-domaines-les-alexandrins', '15-MLA_HERMITAGE_BLANC.jpg'), None),
    ('wine-hermitage-alexandrins', 'Hermitage',
     'winery-cornas-maison-et-domaines-les-alexandrins', None,
     '文件名写 CROZES-HERMITAGE，标面实为 HERMITAGE——文件名与标面不符，以标面为准；'
     '颜色未读出，品种不填',
     ('maison-et-domaines-les-alexandrins', '16-MLA_CROZES-HERMITAGE_RG.jpg'), None),
    ('wine-hermitage-robin-gilles-blanc', 'Hermitage Blanc',
     'winery-cornas-robin-gilles', 'white',
     '读标：HERMITAGE / GILLES ROBIN（白）',
     ('robin-gilles', '12-HERMITAGE-BLC-scaled-e1761293323555.jpg'), None),
    ('wine-hermitage-robin-gilles', 'Hermitage',
     'winery-cornas-robin-gilles', None,
     '放大读标：2023 / HERMITAGE / GILLES ROBIN；颜色未读出，品种不填',
     ('robin-gilles', '21-HERMITAGE-scaled-e1761300113405.jpg'), 2023),
    ('wine-hermitage-colombo-le-rouet', 'Hermitage Le Rouet',
     'winery-cornas-vins-jean-luc-colombo', 'red',
     '放大读标：LE ROUET ROUGE / HERMITAGE（Jean-Luc Colombo）',
     ('vins-jean-luc-colombo', '19-Design-sans-titre-22.jpg'), None),
]


def manifest_index():
    m = json.loads((ROOT / 'outputs' / 'collect' / 'cornas' / 'images'
                    / 'wine-image-manifest.json').read_text())
    idx = {}
    for pr in m['producers']:
        for im in pr.get('images') or []:
            idx[(pr['slug'], im['file'])] = im
    return idx


def build_records():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    idx = manifest_index()
    recs = []

    # 品种记录
    recs.append({
        'id': 'grape-marsanne', 'kind': 'grape', 'name': '玛珊',
        'data': {'name': '玛珊', 'en': 'Marsanne',
                 'sourceTitle': 'Inter Rhône 官网品种页',
                 'sourceURL': 'https://www.vins-rhone.com/en/marsanne-grape-variety',
                 'checkedDate': CHECKED,
                 'notes': '北罗讷白葡萄品种；Hermitage / Crozes-Hermitage / Saint-Joseph '
                          '白葡萄酒的构成品种（Inter Rhône Cru 页）。'},
        'version': 1, 'updated': now, 'origin': 'Inter Rhône 官网品种页',
    })
    recs.append({
        'id': 'grape-roussanne', 'kind': 'grape', 'name': '胡珊',
        'data': {'name': '胡珊', 'en': 'Roussanne',
                 'sourceTitle': 'Inter Rhône 官网品种页',
                 'sourceURL': 'https://www.vins-rhone.com/en/roussanne-grape-variety',
                 'checkedDate': CHECKED,
                 'notes': '北罗讷白葡萄品种；Hermitage 白葡萄酒由 Marsanne 与 Roussanne 构成'
                          '（Inter Rhône Cru 页）。'},
        'version': 1, 'updated': now, 'origin': 'Inter Rhône 官网品种页',
    })

    # 产区记录（坐标留 null，待 OSM 实体检索）
    recs.append({
        'id': 'hermitage', 'kind': 'region', 'name': '埃米塔日产区',
        'data': {
            'name': '埃米塔日产区', 'en': 'Hermitage AOC', 'country': '法国',
            'regionId': 'rhone',
            'lat': None, 'lng': None,
            'locationPrecision': None,
            'locationSourceURL': None,
            'locationNote': "本期未做坐标检索（批次边界：先录官方口径与读标证据酒款）。"
                            "待用 OSM 实体匹配「Colline de l'Hermitage / Chapelle Saint-Christophe」"
                            "并做产区地理窗过滤后再补，不用村镇中心顶替。",
            'grapes': [{'id': SYRAH, 'percent': None},
                       {'id': 'grape-marsanne', 'percent': None},
                       {'id': 'grape-roussanne', 'percent': None}],
            'grapeNote': '红：以 Syrah 酿造，可含不超过 15% 的 Roussanne 和/或 Marsanne'
                         '（Inter Rhône Cru 页原文「Reds are made from Syrah, and may contain '
                         'up to 15% Roussanne and/or Marsanne」）；白：Marsanne 与 Roussanne。'
                         '比例为 AOC 规则，非逐瓶读标。',
            'appellationCreated': '1937',
            'areaHectares': 137,
            'areaNote': '137 ha 为 Inter Rhône 官网 2025 年口径（Production area in 2025）。'
                        '百度百科写 140 ha、SommSelect 写 ~135 ha（总）/~122 ha（投产），'
                        '口径差异见 discrepancies.json。',
            'productionHl': 3526,
            'productionNote': 'Inter Rhône 官网 2025 年总产量 3 526 hl，平均单产 26 hl/ha。',
            'communeCount': 3,
            'communeNote': "全部在德龙省（Drôme）罗讷河左岸：Tain-l'Hermitage、Crozes-Hermitage、"
                           "Larnage（Inter Rhône Cru 页）。",
            'geography': '单一山丘产区：南向陡坡俯瞰罗讷河。山丘可分三段——西侧 Les Bessards'
                         "（花岗岩，被称为产区“红”风土，含 L'Ermite 园）；中部上段 Le Méal"
                         '（石灰岩-燧石混圆砾石），下段 Les Greffieux（细沟侵蚀土壤）；'
                         '东侧 Murets / Dionnières（黏土缓坡，白葡萄酒风土）。'
                         '具名 lieu-dit 还包括 Rocoules、Beaumes 等（Inter Rhône Cru 页）。',
            'soil': '花岗质砂土为主，覆云母片岩与片麻岩，近河处有滚圆冲积砾石；'
                    '地质剖面图官方链接见 region-context.json（Inter Rhône coupe_Hermitage_GB.pdf）。',
            'climate': '半大陆性气候带地中海影响（Inter Rhône 页 Climate 栏）；'
                       '坡向朝南、避北风。',
            'sourceTitle': 'Inter Rhône 官网 Cru 介绍页（AOC Hermitage）',
            'sourceURL': INTER_RHONE,
            'cahierDesChargesURL': INAO_SPEC,
            'checkedDate': CHECKED,
        },
        'version': 1, 'updated': now, 'origin': '每日采集 · Inter Rhône 官方口径',
    })

    # 酒款与年份
    for wid, name, winery_id, color, cuvee_note, ev, year in WINES:
        im = idx.get(ev)
        if not im:
            raise SystemExit('证据图不在 manifest：%s|%s' % ev)
        ev_path = 'images/%s/%s' % ev
        if color == 'white':
            grapes = [{'id': 'grape-marsanne', 'percent': None},
                      {'id': 'grape-roussanne', 'percent': None}]
            grape_note = 'Hermitage 白由 Marsanne 与 Roussanne 构成（AOC 规则）；' \
                         '具体配比无标签标注，不填。'
        elif color == 'red':
            grapes = [{'id': SYRAH, 'percent': None}]
            grape_note = '红以 Syrah 酿造，AOC 允许含不超过 15% 的 Roussanne/Marsanne；' \
                         '具体配比无标签标注，percent 留空。'
        else:
            grapes = []
            grape_note = None
        data = {
            'name': name, 'country': '法国', 'wineryId': winery_id,
            'regionId': 'hermitage',
            'grapes': grapes,
            'sourceTitle': im.get('sourceName', '酒庄官网读标证据'),
            'sourceURL': im.get('sourcePage'),
            'checkedDate': CHECKED,
            'notes': ('读标证据（视觉复核 2026-09-19，classificationMethod=agent-visual-review）：'
                      '%s。证据图：images/cornas/%s（随 003 期采集包交付）。'
                      % (cuvee_note, ev_path)),
        }
        if grape_note:
            data['grapeNote'] = grape_note
        recs.append({'id': wid, 'kind': 'wine', 'name': name, 'data': data,
                     'version': 1, 'updated': now,
                     'origin': '官网图片读标视觉复核（agent-visual-review）'})
        if year:
            recs.append({
                'id': wid.replace('wine-hermitage-', 'vintage-hermitage-') + '-%d' % year,
                'kind': 'vintage', 'name': '%s %d' % (name, year),
                'data': {
                    'name': '%s %d' % (name, year), 'country': '法国',
                    'wineId': wid, 'yearType': 'vintage', 'year': year,
                    'sourceTitle': im.get('sourceName', '酒庄官网读标证据'),
                    'sourceURL': im.get('sourcePage'),
                    'checkedDate': CHECKED,
                    'notes': '年份为瓶标可读年份（evidenceLevel=label-readable，视觉复核 2026-09-19）。'
                             '该年份品种比例无标签/官方标注，不推导。证据图：images/cornas/%s。' % ev_path,
                },
                'version': 1, 'updated': now,
                'origin': '官网图片读标视觉复核（agent-visual-review）',
            })
    return recs


def merge(recs):
    if not BACKUP.exists():
        shutil.copy2(SEED, BACKUP)
        print('backup ->', BACKUP)
    seed = json.loads(SEED.read_text())
    recs_all = seed if isinstance(seed, list) else seed.get('records', [])
    ids = {r['id'] for r in recs_all}
    added = []
    for r in recs:
        if r['id'] in ids:
            print('  已存在，跳过:', r['id'])
            continue
        recs_all.append(r)
        ids.add(r['id'])
        added.append(r)
    if not isinstance(seed, list):
        seed['records'] = recs_all
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    print('merged +%d records (catalog now %d)' % (len(added), len(recs_all)))
    return added


def write_bundle(recs):
    now = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    OUT.mkdir(parents=True, exist_ok=True)
    wines = [r for r in recs if r['kind'] == 'wine']
    vintages = [r for r in recs if r['kind'] == 'vintage']
    grapes = [r for r in recs if r['kind'] == 'grape']
    region = [r for r in recs if r['kind'] == 'region']

    catalog = {
        'date': now,
        'regionId': 'hermitage',
        'period': '004期（首批，partial）',
        'schemaNote': '字段与网站 schema 一致；region 记录 lat/lng 留 null（本批未做坐标检索）。',
        'counts': {
            'regionRecords': len(region), 'grapeRecords': len(grapes),
            'wines': len(wines), 'vintages': len(vintages),
            'wineries': 0, 'producerBaseline': 0,
            'directoryStatus': 'partial — 名录核对未开始；首批只录入读标证据酒款',
        },
        'records': recs,
        'methodNote': '首批不扫名录：把 003 期 Cornas 图片复核中读标确认 HERMITAGE 的 6 张图'
                      '（agent-visual-review，2026-09-19）归并为 wine/vintage 记录。'
                      '136 家底册逐家核对（editorial-plan 既定方案）从下一轮开始。',
    }
    (OUT / 'catalog-additions.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=1))

    (OUT / 'events-additions.json').write_text(json.dumps({
        'date': now,
        'events': [],
        'note': 'WebSearch（2026-09-20）未发现可核实的 Hermitage 产区特定新事件；'
                '罗讷河谷 2026 极早采收（8/11 开榨）已于 2026-09-14 作为全河谷事件登记，'
                '不重复登记为 Hermitage 事件。',
        'heldBack': [{
            'title': 'Rhône Valley 2026 采收窗口（媒体通表：9/28–10/18）',
            'reason': 'winetravelguides.com 的欧洲采收日历是通用媒体推断，非 Hermitage 官方'
                      '发布的发生日期，无可核实单一起始日期 → 不登记为事件。',
            'sourceURL': 'https://winetravelguides.com/wine-harvest-season-2026',
            'factStoredWhere': '不存入任何记录字段；待协会/酒庄发布具体采收日期后再登记。',
        }],
    }, ensure_ascii=False, indent=1))

    (OUT / 'geo-collected.json').write_text(json.dumps({
        'date': now,
        'accepted': [],
        'heldForReview': [],
        'note': "本期未运行坐标采集。region 记录 lat/lng 留 null。下一轮按"
                "「OSM 实体名匹配 + POI 类型 + 产区地理窗」检索 Colline de l'Hermitage 一带"
                "实体后补产区参考点。",
    }, ensure_ascii=False, indent=1))

    (OUT / 'region-context.json').write_text(json.dumps({
        'date': now,
        'sourceURL': INTER_RHONE,
        'officialFigures2025': {'areaHa': 137, 'productionHl': 3526, 'yieldHlHa': 26,
                                'exportShare': '42%', 'aocSince': 1937},
        'communes': ["Tain-l'Hermitage", 'Crozes-Hermitage', 'Larnage'],
        'lieuDits': ['Les Bessards', "L'Ermite", 'Le Méal', 'Les Greffieux',
                     'Les Murets', 'Les Dionnières', 'Les Rocoules', 'Les Beaumes'],
        'geologicalSectionPDF': 'https://www.vins-rhone.com/sites/vignoble/files/'
                                'documentation/2025-04/coupe_Hermitage_GB.pdf',
        'varieties': {'red': 'Syrah（可含≤15% Roussanne 和/或 Marsanne）',
                      'white': 'Marsanne + Roussanne'},
        'historyNote': '传说：13 世纪骑士 Gaspard de Stérimberg（Blanche de Castille 封地）'
                       '隐居山丘得名；AOC 1937。以上为 Inter Rhône 官网页自述。',
    }, ensure_ascii=False, indent=1))

    (OUT / 'sources.json').write_text(json.dumps({
        'date': now,
        'sources': [
            {'id': 'inter-rhone-cru-hermitage', 'sourceName': 'Inter Rhône 官网 Cru 页',
             'sourceURL': INTER_RHONE, 'checkedDate': CHECKED,
             'method': '官网页面核对（WebFetch 全文提取）',
             'covers': '面积/产量/单产/出口占比/AOC 年份/村镇/品种规则/土壤与 lieu-dit'},
            {'id': 'inao-cahier-des-charges-hermitage', 'sourceName': 'INAO cahier des charges（官方下载入口）',
             'sourceURL': INAO_SPEC, 'checkedDate': CHECKED,
             'method': '入口链接登记（Inter Rhône 页引用），文件本体未下载核对',
             'covers': '法定生产条件（待后续轮次核对细节）'},
            {'id': 'cornas-bundle-label-review', 'sourceName': '003 期 Cornas 采集包官网图读标复核',
             'sourceURL': 'outputs/collect/cornas/images/wine-image-manifest.json',
             'checkedDate': '2026-09-19',
             'method': 'agent-visual-review（逐张读标）',
             'covers': '首批 6 条 wine / 1 条 vintage 的读标证据'},
        ],
    }, ensure_ascii=False, indent=1))

    (OUT / 'discrepancies.json').write_text(json.dumps({
        'date': now,
        'items': [
            {'field': 'areaHectares',
             'values': [{'source': 'Inter Rhône 官网（2025）', 'value': 137},
                        {'source': '百度百科「埃米塔日」', 'value': 140},
                        {'source': 'SommSelect（~acre 换算）', 'value': '≈135（总面积）/≈122（投产）'}],
             'resolution': '采纳 Inter Rhône 2025 官方口径 137 并写明年份；其余进本清单。',
             'action': 'areaHectares=137 + areaNote 声明冲突'},
            {'field': '产区参考点（lat/lng）',
             'values': [{'source': '本批', 'value': None}],
             'resolution': '宁缺毋滥：未做 OSM 实体检索前不填点位；不与 Crozes-Hermitage '
                           '产区记录共用 Tain 代表点（两点重叠会互相混淆）。',
             'action': '留 null，下轮 OSM 检索后补'},
            {'field': 'hermitage-vin.fr',
             'values': [{'source': 'editorial-plan 侦察（2026-09-19）', 'value': 'HTTP 000'}],
             'resolution': '确认 Hermitage 无自有 -vin.fr 名录站，底册改用 006 期 '
                           'Crozes-Hermitage 136 家名录逐家核对（不把 136 当 Hermitage 生产者数）。',
             'action': '方案写入 editorial-plan'},
        ],
    }, ensure_ascii=False, indent=1))

    (OUT / '知识库导入清单.json').write_text(json.dumps({
        'date': now,
        'status': '待审核',
        'entries': [
            {'type': 'region', 'id': 'hermitage', 'name': '埃米塔日产区', '审核状态': '待审核'},
            {'type': 'grape', 'id': 'grape-marsanne', 'name': '玛珊', '审核状态': '待审核'},
            {'type': 'grape', 'id': 'grape-roussanne', 'name': '胡珊', '审核状态': '待审核'},
        ] + [{'type': 'wine', 'id': r['id'], 'name': r['name'], '审核状态': '待审核'}
             for r in wines]
            + [{'type': 'vintage', 'id': r['id'], 'name': r['name'], '审核状态': '待审核'}
               for r in vintages],
    }, ensure_ascii=False, indent=1))

    handoff = """# 004期 Hermitage 首批交接（partial — 给内容工作室）

## 这批采到了什么

- **产区官方口径**（Inter Rhône Cru 页，2025 年）：137 ha / 3 526 hl / 26 hl/ha /
  出口 42% / AOC 1937 / 3 个德龙省村镇（Tain-l'Hermitage、Crozes-Hermitage、Larnage）。
  红葡萄：西拉，可含 ≤15% 胡珊和/或玛珊；白葡萄：玛珊 + 胡珊。
- **首批酒款 6 条 + 年份 1 条**：全部来自 003 期 Cornas 图片复核中**读标确认 HERMITAGE** 的
  6 张图（agent-visual-review，2026-09-19）。酒款挂在这些酒庄已存在的地图点位上：
  Paul Jaboulet Aîné（La Maison Bleue）、Maison Les Alexandrins（Hermitage / Hermitage Blanc）、
  Gilles Robin（Hermitage / Hermitage Blanc，红标年份 2023 可读 → 已录 vintage）、
  Jean-Luc Colombo（Le Rouet）。
- **新增品种记录**：玛珊（grape-marsanne）、胡珊（grape-roussanne）——后续北罗讷期次复用。
- 证据图片本体随 **003 期 Cornas 采集包**交付（路径见各 wine 记录 notes 的 evidenceImages），
  本包不含图片文件。

## 不可越界的话（写作红线）

- **没有产区参考点坐标**：region 记录 lat/lng 留 null（本批未做 OSM 检索），
  不要写"位于 Tain-l'Hermitage 村中心"之类点位表述。
- **面积 137 ha 是 2025 年官方口径**，百度百科 140 ha、SommSelect ~135/122 ha 与之冲突
  （见 discrepancies.json）；不要写" Hermitage 是最大/最小的 AOC"这类排序论断。
- **Jaboulet「La Maison Bleue」与 Alexandrins 的 Hermitage 未读出瓶身颜色**，
  品种字段留空——不要脑补成"当然是西拉"。
- **"La Maison Bleue" 只是标面读名**，它是 cuvée 名还是庄名别称未核实，图注措辞留余地。
- 136 家底册核对**尚未开始**：不要写"Hermitage 有 136 家生产者"——136 是 Crozes-Hermitage
  名录条数，只是下一轮核对用的底册。
- 白葡萄品种中文写法沿用库内约定：**玛珊（Marsanne）/ 胡珊（Roussanne）**。

## 明确没有的东西

- 0 条新事件（WebSearch 2026-09-20 无可核实的 Hermitage 特定新事件；heldBack 1 条见
  events-additions.json）。
- 0 张本产区级图片（无独立协会名录站；等逐家核对轮次再收）。
- 0 家酒庄记录（首批不新增酒庄，避免同名异地风险）。
- INAO cahier des charges 只登记了官方下载入口，**文件本体未核对**。

## 素材路径与图片权限

- 读标证据图：`outputs/collect/cornas/images/<酒庄slug>/`（溯源字段在 wine-image-manifest.json，
  图片权限说明见 003 期包 README）。
- 官方事实来源：Inter Rhône Cru 页 + INAO cahier des charges 下载入口（见 sources.json）。

## 下一步（下一轮优先）

1. 以 006 期 Crozes-Hermitage 136 家名录为底册逐家核对 Hermitage 出产证据。
2. OSM 实体检索补产区参考点（Colline de l'Hermitage / Chapelle Saint-Christophe，
   产区地理窗过滤）。
3. INAO cahier des charges 文件本体核对。
"""
    (OUT / 'HANDOFF.md').write_text(handoff)

    # 打包
    zpath = OUT / ('004期-Hermitage-采集包-%s.zip' % now)
    with zipfile.ZipFile(zpath, 'w') as z:
        z.writestr('README-包内说明.txt', (
            '004期 Hermitage（埃米塔日 AOC）采集包 — %s 首批（partial）\n\n'
            '- catalog-additions.json：1 产区 + 2 品种 + 6 酒款 + 1 年份（首批读标证据）\n'
            '- region-context / sources / geo-collected / events-additions（含 heldBack）/\n'
            '  discrepancies / 知识库导入清单（全部待审核）\n'
            '- HANDOFF.md：先读这个；写作红线与缺口都在里面\n'
            '- 本包不含图片；读标证据图随 003 期 Cornas 采集包交付\n' % now))
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p.suffix in ('.json', '.md') and p.name != zpath.name:
                z.write(p, p.name, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
    print('zip:', zpath, '%.2f MB' % (zpath.stat().st_size / 1e6))
    return zpath, now


def main():
    recs = build_records()
    print('records to add: %d' % len(recs))
    added = merge(recs)
    zpath, now = write_bundle(added)
    studio = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / now
    studio.mkdir(parents=True, exist_ok=True)
    dest = studio / zpath.name
    dest.write_bytes(zpath.read_bytes())
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.suffix in ('.json', '.md'):
            (studio / ('004期-hermitage-' + p.name)).write_text(p.read_text())
    print('hand-off:', dest)


if __name__ == '__main__':
    main()
