# coding: utf-8
"""中国酒庄缺数据清单（中文索要版）：CSV + MD。

判缺口与分组口径同 build-data-gap-report.py，但只取 country == 中国，
并把"微信/邮箱"提为第一位（中国酒庄的实际联系渠道）。
"""
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / '_data-gaps-2026-09-21'
ORDER = ['微信/邮箱', '联系人', '电话', '坐标', '官网', '地址', '酒款', '图片', '本地语资料']


def main():
    if not OUT.exists():
        OUT.mkdir(parents=True)
    seed = json.loads((ROOT / 'data' / 'catalog-seed.json').read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    rname = {r['id']: (r.get('data') or {}).get('name') or r.get('name')
             for r in recs if r.get('kind') == 'region'}
    wines = Counter()
    for r in recs:
        if r.get('kind') == 'wine':
            w = (r.get('data') or {}).get('wineryId')
            if w:
                wines[w] += 1
    rows = []
    for r in recs:
        if r.get('kind') != 'winery':
            continue
        d = r.get('data') or {}
        if (d.get('country') or '') != '中国':
            continue
        miss = []
        if not d.get('email'):
            miss.append('微信/邮箱')
        if not d.get('contactPerson'):
            miss.append('联系人')
        if not d.get('phone'):
            miss.append('电话')
        if d.get('lat') is None:
            miss.append('坐标')
        if not d.get('website'):
            miss.append('官网')
        if not d.get('address'):
            miss.append('地址')
        if wines.get(r['id'], 0) == 0:
            miss.append('酒款')
        if not (d.get('images') or []):
            miss.append('图片')
        if not (d.get('localizations') or {}):
            miss.append('本地语资料')
        reach = bool(d.get('website') or d.get('email') or d.get('phone'))
        grp = ('C 仅缺少量' if 1 <= len(miss) <= 2 else 'A 可直接联系') if reach else 'B 需先找联系人'
        rows.append({'grp': grp, 'region': rname.get(d.get('regionId'), d.get('regionId')),
                     'name': r.get('name'), 'en': d.get('en') or '', 'website': d.get('website') or '',
                     'phone': d.get('phone') or '', 'email': d.get('email') or '',
                     'addr': d.get('address') or '', 'coord': '有' if d.get('lat') is not None else '无',
                     'wines': wines.get(r['id'], 0), 'imgs': len(d.get('images') or []),
                     'miss': miss, 'n': len(miss), 'ask': '、'.join(miss[:3]),
                     'src': d.get('sourceURL') or '', 'id': r['id']})
    rows.sort(key=lambda x: (x['grp'], x['region'], -x['n']))

    with (OUT / '中国酒庄缺数据清单.csv').open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['组', '产区', '酒庄（中文名）', '英文名', '官网', '电话', '邮箱/微信', '地址',
                    '有坐标', '酒款数', '图片数', '缺失项', '缺几项', '最该先问的3件', '来源页', '记录ID'])
        for r in rows:
            w.writerow([r['grp'], r['region'], r['name'], r['en'], r['website'], r['phone'], r['email'],
                        r['addr'], r['coord'], r['wines'], r['imgs'], '、'.join(r['miss']), r['n'],
                        r['ask'], r['src'], r['id']])

    g = Counter(r['grp'] for r in rows)
    mt = Counter(m for r in rows for m in r['miss'])
    L = ['# 中国酒庄缺数据清单（优先处理）', '',
         '> 生成：%s ｜ 中国酒庄 **%d 家** ｜ 中国产区 **%d 个**' % (
             datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M'),
             len(rows), len({r['region'] for r in rows})), '',
         '> 中国酒庄的实际联系渠道是**电话/微信**，所以索要顺序是：'
         '先把联系方式拿到（电话/微信/联系人），再补坐标与酒款，最后才是图片与多语言资料。', '',
         '| 分组 | 家数 |', '| --- | --- |']
    for k, v in sorted(g.items()):
        L.append('| %s | %d |' % (k, v))
    L += ['', '| 缺失项 | 家数 |', '| --- | --- |']
    for k, v in mt.most_common():
        L.append('| %s | %d |' % (k, v))
    L += ['', '## 明细', '',
          '| 组 | 产区 | 酒庄 | 缺几项 | 缺失项 | 官网 | 电话 |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        L.append('| %s | %s | %s | %d | %s | %s | %s |' % (
            r['grp'], r['region'], r['name'], r['n'], '、'.join(r['miss']),
            r['website'] or '—', r['phone'] or '—'))
    L += ['', '## 索要话术（中文，可直接发微信/邮件）', '',
          '> 您好，我们在做葡萄酒风土地图与产区资料库（风土图鉴），贵庄已收录在【{产区}】。'
          '目前还缺以下资料，方便的话请回复补充：{缺失项}。'
          '如方便，也欢迎提供 3–5 张庄园/酒款实拍图（我们会标注来源，如涉侵权可随时联系删除）。谢谢！', '',
          '## 边界', '',
          '- 只索要资料，不承诺任何商业回报或合作条件。',
          '- 收到回复后按 `采集规格-网站字段对照.md` 录入，并记 `sourceURL` 与 `checkedDate`。']
    (OUT / '中国酒庄缺数据清单.md').write_text('\n'.join(L) + '\n')
    print('中国清单：%d 家 %s；缺项 %s' % (len(rows), dict(g), dict(mt.most_common(6))))


if __name__ == '__main__':
    main()
