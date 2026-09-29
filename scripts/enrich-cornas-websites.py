# coding: utf-8
"""Enrich the 003期 Cornas bundle + data/catalog-seed.json with winery websites
confirmed in the 2026-09-18 search round.

Why a dedicated script: re-running build-cornas-bundle.py regenerates the whole
bundle and re-running merge-cornas-bundle.py needs a rollback first (see the
skill's idempotency trap). This script patches only the two records concerned,
is safe to re-run, and records every change in a report.

Rules honoured:
- never overwrite an existing *live* website without keeping the old value in
  notesHistory;
- a directory website that is dead may be corrected, but the original value is
  preserved and the reason is recorded;
- cross-region duplicate producers are reported, never renamed or moved.

Usage: python3 scripts/enrich-cornas-websites.py
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'cornas'
SEED = ROOT / 'data' / 'catalog-seed.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-cornas-website-2026-09-18.json'
TODAY = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')

# recordId -> (new website, evidence, kind)
#   'new'     : the directory gave no website; this fills an empty field
#   'correct' : the directory website is dead; this corrects it (old kept)
ENRICH = {
    'winery-cornas-kerschen-cecillon-sarl': {
        'website': 'https://www.juliencecillon.com',
        'kind': 'new',
        'aliases': ['Famille Cécillon', 'Cave Julien Cécillon', 'Domaine Julien Cécillon'],
        'evidence': 'saint-peray.net 协会名录页（/producer/famille-cecillon-2/）标注 www.juliencecillon.com；'
                    'worldyellowpages（Famille & Domaine Cécillon, Tournon sur Rhone）与 wine-world 酒庄页'
                    '（朱利安·塞西隆酒庄）均记录同一域名，域名可达 200。',
        'sourceURL': 'https://saint-peray.net/en/producer/famille-cecillon-2/',
        'staff': 'Julien Cécillon（庄主/酿酒师）· Nancy Kerschen（庄主/酿酒师，美国人）',
        'staffNote': '2011 年创立 Famille Cécillon；名录登记名为 KERSCHEN CECILLON (SARL)。'
                     '地址 42 Chemin des Prés, 07300 Saint-Jean-de-Muzols（部分来源写作 '
                     '152 Chemin du Cornilhac, 07300 Tournon-sur-Rhône）。',
    },
    'winery-cornas-domaine-paul-jaboulet-aine': {
        'website': 'https://jaboulet.com',
        'kind': 'correct',
        'aliases': ['Domaines Paul Jaboulet Aîné', 'Maison Paul Jaboulet Aîné'],
        'evidence': '名录给出 paul-jaboulet-aine.fr 已失效（curl 返回 000，DNS/连接失败）。'
                    'jaboulet.com 页面标题为 "Domaines Paul Jaboulet Aîné - Rhône Valley Fine Wines"，'
                    'Star Wine List 酒庄页亦记录 https://jaboulet.com，故认定为该庄现行官网。'
                    '注意 jaboulet.com 声明 robots.txt Crawl-delay: 10，采集已按 10 秒/请求限速。',
        'sourceURL': 'https://starwinelist.com/wine-place/domaines-paul-jaboulet-aine',
        'staff': 'Caroline Frey（庄主）· Nicolas Mielly（酿酒师）',
        'staffNote': '2006 年起归 Frey 家族；2026 年 5 月以 Global Partner 身份加入 Star Wine List。'
                     'HANDOFF 已划界：不把该庄 Hermitage / Crozes-Hermitage 的图当作 Cornas。',
    },
}

# Cross-region duplicates observed while searching (human decision, not touched).
CROSS_REGION_NOTE = [
    {
        'cornasRecordId': 'winery-cornas-kerschen-cecillon-sarl',
        'existingRecordIds': ['winery-saint-joseph-cave-julien-cecillon',
                              'winery-crozes-hermitage-cave-julien-cecillon'],
        'observation': '同一生产者在库内已有两条记录，分属 saint-joseph 与 crozes-hermitage 期，'
                       '官网均为 juliencecillon.com；Cornas 名录以 "KERSCHEN CECILLON (SARL)" 登记。'
                       '因为规范化名称不相等，按名去重不会命中，三条记录并存。',
        'action': '不合并、不改名、不搬 regionId（会破坏已发布数据的归属），'
                  '留给人决定是否合并为单一生产者记录。',
    },
]


def main():
    records = json.loads(SEED.read_text())
    by_id = {r['id']: r for r in records}
    if not BACKUP.exists():
        shutil.copy2(SEED, BACKUP)

    changes = []
    for rid, spec in ENRICH.items():
        rec = by_id.get(rid)
        if rec is None:
            changes.append({'recordId': rid, 'action': 'skipped',
                            'reason': 'record not found in catalog-seed'})
            continue
        data = rec.setdefault('data', {})
        old = data.get('website')
        if old == spec['website']:
            changes.append({'recordId': rid, 'action': 'already-current',
                            'website': spec['website']})
            continue
        if old and spec['kind'] == 'new':
            changes.append({'recordId': rid, 'action': 'skipped',
                            'reason': '已有官网 %s，本轮不覆盖' % old})
            continue
        if old and old != spec['website']:
            hist = rec.setdefault('notesHistory', [])
            hist.append({'at': TODAY, 'field': 'data.website', 'previous': old,
                         'reason': '名录给出的官网地址已失效，改指现行官网（证据见 additionalSources）'})
        data['website'] = spec['website']
        data['checkedDate'] = TODAY
        add_src = data.setdefault('additionalSources', [])
        add_src.append({
            'checkedDate': TODAY,
            'sourceURL': spec['sourceURL'],
            'sourceTitle': '官网核实（2026-09-18 搜索轮）',
            'note': spec['evidence'],
        })
        if spec.get('aliases'):
            al = data.setdefault('aliases', [])
            for a in spec['aliases']:
                if a not in al:
                    al.append(a)
        if spec.get('staff'):
            data['staff'] = spec['staff']
            data['staffNote'] = spec['staffNote']
        rec['version'] = int(rec.get('version') or 1) + 1
        rec['updated'] = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        changes.append({'recordId': rid, 'action': spec['kind'],
                        'name': rec.get('name'), 'website_old': old,
                        'website_new': spec['website'], 'evidence': spec['evidence']})
        print('%-52s %s  %s -> %s' % (rid, spec['kind'], old, spec['website']))

    SEED.write_text(json.dumps(records, ensure_ascii=False, indent=1) + '\n')

    # Mirror into the delivery bundle's catalog-additions so downstream sees it too.
    ca_path = OUT / 'catalog-additions.json'
    ca = json.loads(ca_path.read_text())
    patched = 0
    for r in ca.get('records', []):
        spec = ENRICH.get(r.get('id'))
        if not spec:
            continue
        d = r.setdefault('data', {})
        d['website'] = spec['website']
        d['checkedDate'] = TODAY
        if spec.get('aliases'):
            al = d.setdefault('aliases', [])
            for a in spec['aliases']:
                if a not in al:
                    al.append(a)
        if spec.get('staff'):
            d['staff'] = spec['staff']
            d['staffNote'] = spec['staffNote']
        patched += 1
    counts = ca.setdefault('counts', {})
    counts['withWebsite'] = sum(1 for r in ca.get('records', [])
                                if r.get('kind') == 'winery' and (r.get('data') or {}).get('website'))
    ca['websiteEnrichmentRound'] = {
        'date': TODAY,
        'goal': '对名录里没有官网的生产者逐家搜索官网；并复核名录给出的官网是否仍有效',
        'recordsPatched': patched,
        'changes': changes,
        'crossRegionProducers': CROSS_REGION_NOTE,
        'notFound': [
            {'directoryName': 'CAVE DUMAZET',
             'evidence': '多轮检索只找到第三方页（wineryway / bibendum-wine / grapex / 零售商），'
                         '未见自建官网；登记地址 136 Rue du 2 Septembre 1944, 07340 Limony（阿尔代什右岸，'
                         '非 Cornas 村内）。'},
            {'directoryName': 'CUCHET BELIANDO CATHERINE',
             'evidence': '只有英国/美国进口商页（cuchet.co.uk、veritaswine、vins-de-lieux），无自建官网；'
                         '酒窖地址 rue Pied la Vigne, Cornas（第三方访谈提及）。'},
            {'directoryName': 'DESPESSE JEROME',
             'evidence': '只有旅游局与零售商页（ardeche-guide、flightwineshop、wineandcheeseplace），无自建官网；'
                         '地址 10 basses rues, 07130 Cornas。'},
            {'directoryName': 'KERSCHEN CECILLON (SARL)',
             'note': '已找到官网 juliencecillon.com（见 changes），从"未找到"移出。'},
            {'directoryName': 'CAVE PINHEIRO',
             'evidence': '本轮检索未获得可核实的官网；下轮改用当地语言（法文页码/村镇名）继续搜索。'},
            {'directoryName': 'COTE MILLESIME',
             'evidence': '本轮检索未获得可核实的官网；该名与葡萄酒零售品牌重名，须谨慎区分同名词条。'},
            {'directoryName': 'EQUIS',
             'evidence': '本轮检索未获得可核实的官网。'},
            {'directoryName': 'JABOULET CLAUDIA ET LAURENT',
             'evidence': '检索被同名大酒商 Paul Jaboulet Aîné 稀释，本轮未能定位该小生产者的独立官网。'},
        ],
        'notSearchedThisPass': [],
    }
    ca_path.write_text(json.dumps(ca, ensure_ascii=False, indent=1) + '\n')

    report = {
        'date': TODAY,
        'region': 'cornas',
        'backup': str(BACKUP.relative_to(ROOT)),
        'recordsPatchedInSeed': sum(1 for c in changes if c.get('action') in ('new', 'correct')),
        'changes': changes,
        'crossRegionProducers': CROSS_REGION_NOTE,
    }
    (OUT / 'website-enrichment-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print('seed records:', len(records), '| bundle patched:', patched)


if __name__ == '__main__':
    main()
