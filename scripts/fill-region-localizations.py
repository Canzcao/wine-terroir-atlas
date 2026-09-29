# coding: utf-8
"""给 10 个缺「本地语资料」的法国产区补 `data.localizations.fr`。

背景
----
共建看板「本地语资料」一列的判定是 `if not (data.localizations or {})`：只要 localizations
是空对象就记一笔缺口。现有 109 个产区里 99 个有，**缺的 10 个全是法国产区**
（burgundy / bordeaux / champagne / loire / rhone / alsace / condrieu /
saint-joseph / crozes-hermitage / hermitage），都是最早那批入库的，
`originalLanguage` 还是 None、localizations 为空。

口径（为什么不能靠翻译凑）
--------------------------
`public/language-core.js` 的 `confirmed()` 要求
`status==='verified'` **且** sourceURL / sourceTitle / checkedDate 齐全，
齐了才会把这条本地语名拿去做显示与检索。所以本地语名必须是**官方页面印出来的名字**，
不能自己把英文名翻成法文填进去（那就成了编数据）。

下面的 `FR_NAMES` 每一条的 sourceURL 都是 **2026-09-23 当天实际抓过、返回 200 的页面**，
sourceTitle 就是那一页真实的 `<title>`（不是照抄记录里原有的泛称「产区协会 / 行业机构」）。
`note` 里记着核对的实际情况，特别是 loire 那条 —— 官网通篇没有出现 `Val de Loire`，
只有 InterLoire 自用的 `Vins de Loire`，所以**只收录有据的那一个**。

顺带修的
--------
这 10 个产区的 `originalLanguage` 都是 None。它们是法国产区，原语种就是法文，
补成 `'fr'`（与 `country='法国'` → `countryRules` 推出来的优先级一致，不改变任何渲染结果，
但 `field()` 回报的 `language` 字段就准了）。

用法
----
    python3 scripts/fill-region-localizations.py --dry-run
    python3 scripts/fill-region-localizations.py
"""

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
WORK = ROOT / 'work'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
CHECKED = '2026-09-23'

# region_id -> {name, sourceURL, sourceTitle, note?}
# ⚠️ sourceTitle 必须是该页真实的 <title>；sourceURL 必须是当天可访问的页面。
FR_NAMES = {
    'burgundy': {
        'name': 'Bourgogne',
        'sourceURL': 'https://www.bourgogne-wines.com/',
        'sourceTitle': 'Bourgogne wines, crafted in an exceptional winegrowing region - Bourgogne wines',
    },
    'bordeaux': {
        'name': 'Bordeaux',
        'sourceURL': 'https://www.bordeaux.com/fr/',
        'sourceTitle': 'Vins de Bordeaux - Site Officiel | Bordeaux.com',
    },
    'champagne': {
        'name': 'Champagne',
        'sourceURL': 'https://www.champagne.fr/',
        'sourceTitle': 'Champagne.fr I Le site officiel du Champagne',
    },
    'loire': {
        'name': 'Vins de Loire',
        'sourceURL': 'https://www.vinsdeloire.fr/',
        'sourceTitle': 'Les Vins de Loire',
        'note': ('官方机构 InterLoire 站点自用名称（页面标题「Les Vins de Loire」，'
                 '正文「Vins de Loire」出现 12 次）。地理／行政上的「Val de Loire」'
                 '在这批来源里一次都没出现，未收录。'),
    },
    'rhone': {
        'name': 'Vallée du Rhône',
        'sourceURL': 'https://www.vins-rhone.com/',
        'sourceTitle': 'Accueil | Vins Rhône',
        'note': 'Inter Rhône 官网列出的大区名称（页面正文「Vallée du Rhône」出现 6 次）。',
    },
    'alsace': {
        'name': 'Alsace',
        'sourceURL': 'https://www.vinsalsace.com/',
        'sourceTitle': "Vins d'Alsace : Site officiel du vignoble d'Alsace",
        'note': ('改用 CIVA（Conseil Interprofessionnel des Vins d\'Alsace）官网。'
                 '记录原有的 sourceURL（laroutedesvins-alsace.com）深层页仍可访问，'
                 '但该域名首页已被一家租车公司占用，来源站点待复核。'),
    },
    'condrieu': {
        'name': 'Condrieu',
        'sourceURL': 'https://www.inao.gouv.fr/produit/condrieu-20101',
        'sourceTitle': 'Condrieu | INAO',
    },
    'saint-joseph': {
        'name': 'Saint-Joseph',
        'sourceURL': 'https://www.aoc-saint-joseph.fr/',
        'sourceTitle': 'AOC Saint-Joseph',
    },
    'crozes-hermitage': {
        'name': 'Crozes-Hermitage',
        'sourceURL': 'https://www.crozes-hermitage-vin.fr/',
        'sourceTitle': 'AOC CROZES-HERMITAGE',
    },
    'hermitage': {
        'name': 'Hermitage',
        'sourceURL': 'https://www.vins-rhone.com/en/cotes-du-rhone-cru-aoc-hermitage',
        'sourceTitle': 'Côtes du Rhône Cru AOC Hermitage | Vins Rhône',
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='已有 fr 条目的产区也覆盖')
    args = ap.parse_args()

    seed = json.loads(SEED.read_text(encoding='utf-8'))
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_id = {r['id']: r for r in recs if r.get('kind') == 'region'}

    filled, skipped, missing_id = 0, 0, []
    for rid, spec in FR_NAMES.items():
        r = by_id.get(rid)
        if not r:
            missing_id.append(rid)
            continue
        d = r.setdefault('data', {})
        loc = d.setdefault('localizations', {})
        if loc.get('fr') and not args.force:
            skipped += 1
            continue
        entry = {
            'name': spec['name'],
            'description': '',
            'sourceURL': spec['sourceURL'],
            'sourceTitle': spec['sourceTitle'],
            'checkedDate': CHECKED,
            'status': 'verified',
        }
        if spec.get('note'):
            entry['note'] = spec['note']
        loc['fr'] = entry
        if not d.get('originalLanguage'):
            d['originalLanguage'] = 'fr'
        r['version'] = int(r.get('version') or 1) + 1
        r['updated'] = NOW
        filled += 1
        print(f"+ {rid:18s} fr={spec['name']:20s} ← {spec['sourceTitle'][:56]}")

    if missing_id:
        print('⚠️ 库里找不到这些产区 id：', missing_id)
    print(f'\n写入 {filled} 条，跳过 {skipped} 条（已有 fr 条目）')

    report = {'generatedAt': NOW, 'checkedDate': CHECKED, 'filled': filled,
              'skipped': skipped, 'missingIds': missing_id, 'payload': FR_NAMES}
    if not WORK.is_dir():
        WORK.mkdir(parents=True)
    (WORK / 'region-localizations-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    if args.dry_run:
        print('\n--dry-run：未写盘。报告 → work/region-localizations-report.json')
        return

    backup = WORK / f'catalog-seed.before-region-localizations-{datetime.now().strftime("%Y%m%d%H%M%S")}.json'
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'备份 → {backup}')
    print('落盘完成。')


if __name__ == '__main__':
    main()
