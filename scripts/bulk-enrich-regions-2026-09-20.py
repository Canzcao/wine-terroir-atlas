# coding: utf-8
"""批量富化 region 记录（第一批 5 个空壳产区：Rioja / Ribera del Duero / Chianti Classico / Etna DOC / Douro）。

原则：
- 一律用**一手官方页**（各国协会 / 监管机构），页面上拿不到的数字留 null，不推断；
- 口径互相冲突的（面积/生产者数）不取单一值，写进 discrepancies 并保持 null 或**带年份标注**；
- 就地富化：同 ID、version +1，被覆盖的旧值进 notesHistory；
- 同时产出 outputs/collect/<region>/ 的首批采集件（catalog-additions / sources / discrepancies / 名录入口）。
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-region-bulk-2026-09-20.json'
CHECKED = '2026-09-20'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

L = {'zh': 'zh', 'es': 'es', 'it': 'it', 'pt': 'pt', 'en': 'en'}


def loc(lang, name, url, title, status='verified'):
    return {'name': name, 'description': '', 'sourceURL': url, 'sourceTitle': title,
            'checkedDate': CHECKED, 'status': status}


REGIONS = [
 {
  'id': 'rioja',
  'official': {
    'en': 'Rioja DOCa', 'localName': 'Rioja',
    'country': '西班牙', 'appellationCreated': None,
    'areaHectares': 66000, 'areaNote': '协会官网首页原文「Más de 66.000 hectáreas」（超过 66 000 公顷）——'
                                      '这是产区协会自述的种植面积，未给出统计年份；其他来源口径见 discrepancies。',
    'producersNote': '协会官网首页原文「Nearly 600 wineries with unique experiences in Rioja」'
                     '（近 600 家酒庄）。**这不是注册生产者数**，是官网对外宣传的规模描述，'
                     '且可能含酒商与酒庄旅游接待点；注册生产者分母需另向协会/监管机构核实。',
    'subzones': ['Rioja Alta', 'Rioja Alavesa', 'Rioja Oriental'],
    'grapeNote': '以丹魄（Tempranillo）为核心，另有 Garnacha、Graciano、Mazuelo、Viura 等；'
                 '具体法定比例以 DOCa 法规为准，本期未从官方页取得逐项比例。',
    'qualityTiers': ['Reserva', 'Gran Reserva'],
    'notes': '2025–2026 为 DOCa 百年纪念期（协会官网 Rioja news 栏目多处提及百年庆典活动）。',
  },
  'source': {'title': 'Consejo Regulador DOCa Rioja 官网（西班牙语/英语）',
             'url': 'https://www.riojawine.com/', 'quote':
             '「More than 66,000 hectares... Nearly 600 wineries... Three areas: Rioja Alta, '
             'Rioja Alavesa and Rioja Oriental」'},
  'directory': {'name': 'DOCa Rioja 官网酒庄名录 / Wine Locator',
                'url': 'https://www.riojawine.com/', 'note':
                '首页有「Discover the wineries」分类入口（Contemporary / Centenarian / Family / '
                'Among the vineyards / City / With historical prominence / Singular）与 Professionals 下的 '
                'Wine Locator；具体名录列表 URL 待逐页确认。'},
  'localizations': {'es': ('Rioja', 'https://www.riojawine.com/', 'Consejo Regulador DOCa Rioja'),
                    'en': ('Rioja DOCa', 'https://ca.riojawine.com/en/', 'DOCa Rioja — official site (EN)')},
 },
 {
  'id': 'ribera',
  'official': {
    'en': 'Ribera del Duero DO', 'localName': 'Ribera del Duero',
    'country': '西班牙', 'appellationCreated': '1982',
    'areaHectares': 26123,
    'areaNote': '协会官网 Viñedos 页原文「26.123 hectáreas de viñedo a lo largo de la Ribera del Duero, '
                'divididas en 63.630 parcelas」——26 123 公顷、63 630 个地块（官网当期口径，未标年份）。'
                '其他来源（2023 年 27 252 ha、2025 年 27 468 ha）见 discrepancies。',
    'growersNote': '协会官网原文「Cerca de 8.000 viticultores」——约 8 000 名种植者。',
    'yieldNote': '协会官网原文：近十年平均 4 320 kg/ha，远低于法规上限 7 000 kg/ha。',
    'harvestNote': '协会官网原文：72.2% 的采收仍为手工；超过 8.2% 的葡萄藤种植于 1940 年前（树龄 80 年以上）。',
    'producersNote': '协会官网酒庄检索页原文「más de 300 bodegas y 2.500 marcas」——'
                     '超过 300 家酒庄、2 500 个品牌。**这不是注册酒庄分母**（另有来源称 2024 年 1 月 212 家持证酒庄）。',
    'subzones': ['西部台地（Pesquera–Roa 一带）', '东部台地（Roa 以东）', 'Cima/Valle 等分区（本期未从官方页取得官方分区名）'],
    'grapeNote': '丹魄（当地称 Tinto Fino / Tinta del País）为绝对主力；法规允许搭配赤霞珠、梅洛、马尔贝克、'
                 '加尔纳恰（合计不超过 25%）；白葡萄为 Albillo Mayor。法定比例以 DO 法规（Pliego de Condiciones）为准。',
    'agingNote': '陈年分级 Crianza / Reserva / Gran Reserva 的法定橡木桶与瓶陈时长本期**未从协会官网页面取得**，'
                 '故不登记具体年限，避免引用二手数字。',
    'notes': '产区横跨 Burgos / Segovia / Soria / Valladolid 四省，官方酒庄检索库按酒庄逐个可查。',
  },
  'source': {'title': 'Consejo Regulador DO Ribera del Duero 官网（西班牙语）',
             'url': 'https://www.riberadelduero.es/la-do-ribera-del-duero/vinedos', 'quote':
             '「26.123 hectáreas de viñedo ... 63.630 parcelas ... Cerca de 8.000 viticultores ... '
             '4.320 kilos por hectárea ... el 72,2% de la vendimia es a mano」'},
  'directory': {'name': 'DO Ribera del Duero 官网酒庄检索（>300 家酒庄 / 2 500 品牌）',
                'url': 'https://www.riberadelduero.es/bodegas/resultados',
                'note': '官网自带酒庄搜索引擎，可按名称/村镇检索；逐家核对从下一批开始。'},
  'localizations': {'es': ('Ribera del Duero', 'https://www.riberadelduero.es/',
                           'Consejo Regulador de la D.O. Ribera del Duero')},
 },
 {
  'id': 'chianti',
  'official': {
    'en': 'Chianti Classico DOCG', 'localName': 'Chianti Classico',
    'country': '意大利', 'appellationCreated': None,
    'areaHectares': None,
    'areaNote': '协会官网「Zona di produzione」页给的是**产区总地域 70 000 公顷**（含非葡萄园），'
                '葡萄园面积未在该页给出 → areaHectares 留 null，不把 70 000 当葡萄园面积。',
    'producersNote': '协会官网 Consorzio 页原文「oggi rappresenta 480 produttori, di cui 342 escono '
                     'sul mercato con la propria etichetta」——代表 480 家生产者，其中 342 家以自有酒标上市。',
    'historyNote': '协会官网原文：1924 年在 Radda in Chianti 成立，是意大利第一个葡萄酒协会（「Nato per primo '
                   'in Italia, nel 1924」）；2024 年满 100 年。',
    'communes': ['Castellina in Chianti', 'Gaiole in Chianti', 'Greve in Chianti', 'Radda in Chianti',
                 'Barberino Tavarnelle（部分）', 'Castelnuovo Berardenga（部分）', 'Poggibonsi（部分）',
                 'San Casciano in Val di Pesa（部分）'],
    'provinces': ['Firenze', 'Siena'],
    'harvestNote': '协会官网原文：采收期可自 9 月上半月至 10 月下半月，因地理位置与海拔而异。',
    'grapeNote': '以桑娇维塞（Sangiovese）为主，可搭配本土及国际品种；逐项法定比例本期未从官方页取得，留空。',
    'notes': '协会官网首页显示 22 款 Chianti Classico 获 2026 年 Gambero Rosso 三杯奖（官网自述）。',
  },
  'source': {'title': 'Consorzio Vino Chianti Classico 官网（意大利语/英语）',
             'url': 'https://www.chianticlassico.com/consorzio/', 'quote':
             '「Nato per primo in Italia, nel 1924, oggi rappresenta 480 produttori, di cui 342 escono '
             'sul mercato con la propria etichetta」'},
  'directory': {'name': 'Chianti Classico 协会生产者名录（480 家，官网内部检索）',
                'url': 'https://www.chianticlassico.com/consorzio/',
                'note': '协会官网有成员/酒庄检索入口，具体列表 URL 待确认。'},
  'localizations': {'it': ('Chianti Classico', 'https://www.chianticlassico.com/consorzio/',
                           'Consorzio Vino Chianti Classico'),
                    'en': ('Chianti Classico', 'https://www.chianticlassico.com/en/',
                           'Chianti Classico Wine Consortium (EN)')},
 },
 {
  'id': 'etna',
  'official': {
    'en': 'Etna DOC', 'localName': 'Etna DOC',
    'country': '意大利', 'appellationCreated': '1968',
    'appellationCreatedNote': 'DOC 1968 年设立（西西里最早的 DOC）——出自行业媒体（Decanter / Gambero Rosso）'
                              '报道的协会口径，协会官网首页本身未标注年份。',
    'areaHectares': None,
    'areaNote': '面积各来源冲突：协会官网首页写 1 291 hectares，2024 年行业媒体引协会口径写 1 500 ha，'
                '2022 年报道写 1 184 ha → 按规矩 **留 null**，全部写入 discrepancies。',
    'producersNote': '协会官网首页写 441 producers；行业媒体引协会口径写 220 companies / 383 viticoltori（2022）'
                     '——口径不同（生产者 vs 协会会员 vs 种植者），生产者数按官网 441 记录并注明口径差异。',
    'productionHl': 43700, 'bottlesNote': '协会官网首页写 5,8 mil bottles（580 万瓶）。',
    'villagesNote': '协会官网首页写 20 villages；contrade（法定 UGA）官网首页写 133，'
                    '2026 年协会更新地图后媒体报 142（新增 9 个）→ 两个数都记，见 discrepancies。',
    'grapeNote': '红：Nerello Mascalese、Nerello Cappuccio（库内已有品种记录）；'
                 '白：Carricante、Catarratto 等。海拔带 250–1 100 m（行业媒体引协会口径，非官网页原文）。',
    'notes': '协会自述「3000 years of viticulture」（三千年葡萄栽培史）；被广泛称为「英雄式葡萄栽培」代表。',
  },
  'source': {'title': 'Consorzio Tutela Vini Etna DOC 官网（英语/意大利语）',
             'url': 'http://thewinesofetna.com/', 'quote':
             '「441 producers, 43.700 hectoliters of wine, 5,8 mil bottles, 1.291 hectares」'
             '「7 wines, 20 villages, 133 Contrade and 3000 years of viticulture」'},
  'directory': {'name': 'Etna DOC 协会生产者名录（441 家）',
                'url': 'https://thewinesofetna.com/consortium/',
                'note': '协会官网有 Consortium 页与 news/events 栏目；成员名录逐家 URL 待确认。'},
  'localizations': {'it': ('Etna DOC', 'https://thewinesofetna.com/', 'Consorzio Tutela Vini Etna DOC'),
                    'en': ('Etna DOC', 'https://thewinesofetna.com/', 'Consorzio Tutela Vini Etna DOC (EN)')},
 },
 {
  'id': 'douro',
  'official': {
    'en': 'Douro DOC', 'localName': 'Douro',
    'country': '葡萄牙', 'appellationCreated': '1756',
    'appellationCreatedNote': '1756 年庞巴尔侯爵划定，世界最早的法定划定葡萄酒产区——多来源一致（含 IVDP 体系叙述）。',
    'areaHectares': 43808,
    'areaNote': 'IVDP 官网分区分区表给出葡萄园面积合计 43 808 ha（占产区总面积 250 000 ha 的 18%）；'
                '另有来源写约 40 000 ha / 33 000 ha → 取 IVDP 官方表数并记冲突。',
    'totalAreaHectares': 250000,
    'growersNote': 'IVDP 官网原文「The land under vines is worked by approximately 20,000 farmers, each '
                   'owning an average of 2 ha under vines」——约 2 万农户，人均约 2 ha。'
                   '另有来源写 33 000 名种植者 → 见 discrepancies。',
    'subzones': [{'name': 'Baixo Corgo / Lower Corgo', 'totalHa': 45000, 'vinesHa': 13204, 'share': '29%'},
                 {'name': 'Cima Corgo / Upper Corgo', 'totalHa': 95000, 'vinesHa': 20427, 'share': '22%'},
                 {'name': 'Douro Superior / Upper Douro', 'totalHa': 110000, 'vinesHa': 10177, 'share': '9%'}],
    'doStructure': '两个法定产区并存：DO Douro（干型红/白/桃红、起泡、Moscatel do Douro）与 DO Porto（波特酒），'
                   '同由 IVDP 监管。',
    'grapeNote': '葡萄品种逾 80 个，分推荐/许可/容许三类（行业指南转述 IVDP 体系）；'
                 '波特酒最重要的红品种为 Touriga Nacional（库内已有记录）。逐项比例留空。',
    'notes': '产区以片岩梯田为标志，2001 年列入 UNESCO 世界遗产；IVDP 每年核定可用于波特酒的葡萄量（benefício 制度）。',
  },
  'source': {'title': 'IVDP（Instituto dos Vinhos do Douro e do Porto）官网 — 产区特征页',
             'url': 'https://www.ivdp.pt/en/viticulture/region/characteristics-of-the-region/',
             'quote': '「Total 250 000 ha / 43 808 ha under vines (18%)；Lower Corgo 45 000 / 13 204；'
                      'Upper Corgo 95 000 / 20 427；Upper Douro 110 000 / 10 177；'
                      'approximately 20,000 farmers, each owning an average of 2 ha」'},
  'directory': {'name': 'IVDP 官网（监管机构，非消费者名录）',
                'url': 'https://www.ivdp.pt/', 'note':
                'IVDP 是监管机构，官网提供法规/统计/教育栏目（另有 2026-09-09 通函、Port Wine Day 2026 等）；'
                '酒庄名录需用行业机构（如 ViniPortugal / Wines of Portugal）或产区协会来源，待下一批核对。'},
  'localizations': {'pt': ('Douro', 'https://www.ivdp.pt/pt/viticulture/region/characteristics-of-the-region/',
                           'IVDP — Características da Região'),
                    'en': ('Douro DOC', 'https://www.ivdp.pt/en/viticulture/region/characteristics-of-the-region/',
                           'IVDP — Characteristics of the Region (EN)')},
 },
]

DISCREPANCIES = {
 'rioja': [
   {'field': 'areaHectares',
    'values': [{'source': '协会官网首页自述', 'value': '>66 000 ha（未标年份）'}],
    'resolution': '取官网自述数并注明未标年份；若后续取得监管机构年度报表口径，以报表覆盖。',
    'action': 'areaHectares=66000 + areaNote 说明'},
   {'field': '生产者数',
    'values': [{'source': '协会官网首页', 'value': 'Nearly 600 wineries（宣传口径，含酒商/接待点可能）'}],
    'resolution': '**不登记为注册生产者分母**，只作规模描述；分母待向协会核实。',
    'action': 'producersNote 记录，未写 producers 字段'},
 ],
 'ribera': [
   {'field': 'areaHectares',
    'values': [{'source': '协会官网 Viñedos 页', 'value': 26123},
               {'source': '中文资料（2023 年末）', 'value': 27252},
               {'source': '行业媒体引 2025 数据', 'value': 27468}],
    'resolution': '取协会官网当期口径 26 123（并保留“未标年份”的说明）；其余进本清单。',
    'action': 'areaHectares=26123 + areaNote 列全部口径'},
   {'field': '注册酒庄数',
    'values': [{'source': '协会官网检索页', 'value': '>300 bodegas / 2 500 marcas'},
               {'source': '行业媒体引 2024-01', 'value': '212 家持 DO 认证'}],
    'resolution': '两者口径不同（酒庄+品牌 vs 持证酒庄），不合并；不写 producers 数字字段。',
    'action': 'producersNote 两个口径并列'},
   {'field': '陈年分级年限',
    'values': [{'source': '第三方汇总', 'value': 'Crianza 24 个月 / Reserva 36 个月 / Gran Reserva 60 个月'}],
    'resolution': '未从协会官网取得 → 本期不登记具体年限。',
    'action': 'agingNote 说明未取官方页'},
 ],
 'chianti': [
   {'field': 'areaHectares',
    'values': [{'source': '协会官网 Zona di produzione 页', 'value': '70 000 ha 为产区总地域（含非葡萄园）'}],
    'resolution': '**不把 70 000 ha 当葡萄园面积**，留 null。',
    'action': 'areaHectares=null + areaNote 说明 70 000 的含义'},
 ],
 'etna': [
   {'field': 'areaHectares',
    'values': [{'source': '协会官网首页', 'value': 1291},
               {'source': '行业媒体（2024，引协会）', 'value': 1500},
               {'source': '行业媒体（2022）', 'value': 1184}],
    'resolution': '三值冲突且无年份标注 → 保持 null。',
    'action': 'areaHectares=null + 全部口径进本清单'},
   {'field': 'contrade 数量',
    'values': [{'source': '协会官网首页', 'value': 133},
               {'source': 'Decanter（2026，协会新地图）', 'value': '142（新增 9）'}],
    'resolution': '两个数都保留并注明来源与时间；法定 UGA 以 disciplinare 最新版本为准，待核对。',
    'action': 'villagesNote 并列'},
   {'field': '生产者数',
    'values': [{'source': '协会官网首页', 'value': '441 producers'},
               {'source': '行业媒体（2024，引协会）', 'value': '220 companies'},
               {'source': '行业媒体（2022）', 'value': '383 viticoltori'}],
    'resolution': '口径不同（生产者/公司/种植者），按官网 441 记录并注明。',
    'action': 'producersNote 三值并列'},
 ],
 'douro': [
   {'field': '葡萄园面积',
    'values': [{'source': 'IVDP 官网分区表', 'value': 43808},
               {'source': '行业来源', 'value': '≈40 000 / 33 000'}],
    'resolution': '取 IVDP 官方表数 43 808 并保留冲突记录。',
    'action': 'areaHectares=43808 + areaNote'},
   {'field': '种植者数',
    'values': [{'source': 'IVDP 官网', 'value': '约 20 000 farmers（人均 2 ha）'},
               {'source': '行业来源', 'value': '33 000 名种植者'}],
    'resolution': '按官网记录约 2 万，并注明另有 3.3 万口径。',
    'action': 'growersNote 并列'},
 ],
}


def main():
    if not BACKUP.exists():
        shutil.copy2(SEED, BACKUP)
        print('backup ->', BACKUP)
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs}

    touched, bundles = [], []
    for rg in REGIONS:
        r = by_id[rg['id']]
        d = r.setdefault('data', {})
        hist = d.setdefault('notesHistory', [])
        o = rg['official']

        # 覆盖前留痕
        for k in ('sourceTitle', 'sourceURL', 'notes'):
            if d.get(k):
                hist.append({'field': k, 'previousValue': d[k],
                             'replacedAt': NOW, 'reason': '首批官方口径富化（2026-09-20）'})

        d['en'] = o['en']
        for k in ('country', 'appellationCreated', 'appellationCreatedNote', 'areaHectares', 'areaNote',
                  'totalAreaHectares', 'producersNote', 'growersNote', 'yieldNote', 'harvestNote',
                  'productionHl', 'bottlesNote', 'villagesNote', 'subzones', 'communes', 'provinces',
                  'grapeNote', 'agingNote', 'qualityTiers', 'doStructure', 'historyNote', 'notes'):
            if o.get(k) not in (None, '', []):
                d[k] = o[k]
        d['sourceTitle'] = rg['source']['title']
        d['sourceURL'] = rg['source']['url']
        d['checkedDate'] = CHECKED
        d['officialQuote'] = rg['source'].get('quote')
        d['producerDirectory'] = rg['directory']
        locs = d.setdefault('localizations', {})
        for lang, (nm, url, title) in rg['localizations'].items():
            locs[lang] = loc(lang, nm, url, title)
        d['originalLanguage'] = 'es' if o['country'] == '西班牙' else (
            'it' if o['country'] == '意大利' else 'pt')
        r['version'] = int(r.get('version') or 1) + 1
        r['updated'] = NOW
        r['origin'] = '每日采集 · 官方协会/监管机构页面（本地语言 + 英语双通道）'
        touched.append(r)

        # 采集包
        outdir = ROOT / 'outputs' / 'collect' / rg['id']
        if not outdir.exists():
            outdir.mkdir(parents=True)
        (outdir / 'catalog-additions.json').write_text(json.dumps({
            'date': CHECKED, 'regionId': rg['id'], 'batch': '第一批（多国空壳产区批量富化）',
            'schemaNote': 'region 记录就地富化（version +1），未新增或删除任何记录。',
            'counts': {'regionRecords': 1, 'records': 1},
            'records': [r],
            'producerDirectory': rg['directory'],
        }, ensure_ascii=False, indent=1))
        (outdir / 'sources.json').write_text(json.dumps({
            'date': CHECKED,
            'searchQueries': [{'language': d['originalLanguage'],
                               'query': rg['source']['title'], 'channel': '本地语言官方页直连'}],
            'sources': [{'id': rg['id'] + '-official', 'sourceName': rg['source']['title'],
                         'sourceURL': rg['source']['url'], 'checkedDate': CHECKED,
                         'method': '官网页面直取（本地语言版本）',
                         'quote': rg['source'].get('quote')}],
        }, ensure_ascii=False, indent=1))
        (outdir / 'discrepancies.json').write_text(json.dumps({
            'date': CHECKED, 'regionId': rg['id'], 'items': DISCREPANCIES.get(rg['id'], []),
        }, ensure_ascii=False, indent=1))
        bundles.append(rg['id'])
        print('富化:', rg['id'], '→', outdir)

    (ROOT / 'data' / 'catalog-seed.json').write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    print('合并完成：%d 条 region 记录已就地富化（catalog 共 %d 条）' % (len(touched), len(recs)))
    print('采集件目录：', ', '.join(bundles))


if __name__ == '__main__':
    main()
