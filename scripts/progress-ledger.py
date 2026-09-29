# coding: utf-8
"""产区采集进度台账：谁都能读的"现在做到哪、接下来做哪"。

用法：
  python3 scripts/progress-ledger.py report            # 打印中文播报（给人看 / 给播报自动化用）
  python3 scripts/progress-ledger.py report --short     # 一句话版
  python3 scripts/progress-ledger.py update \
      --country ES --region rioja --phase "逐家核对" \
      --done "官方名录入口已确认" --next "拉官方口径写 region 记录" \
      --blocker "riojawine.com 名录 URL 待确认" --artefact "outputs/collect/rioja/"
  python3 scripts/progress-ledger.py sync              # 只按现有数据重算统计，不改轮次

产物：
  data/collection-progress.json   （机读台账：当前任务、轮次历史、各国统计）
  outputs/collection-progress.md  （人读播报，每次 report/sync 重写）
"""
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ROT = ROOT / 'data' / 'country-rotation.json'
PLAN = ROOT / 'data' / 'editorial-plan.json'
SEED = ROOT / 'data' / 'catalog-seed.json'
LEDGER = ROOT / 'data' / 'collection-progress.json'
MD = ROOT / 'outputs' / 'collection-progress.md'


def now_cn():
    return datetime.now(ZoneInfo('Asia/Shanghai'))


def stats_by_region():
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    wins, wines, vints, imgs = Counter(), Counter(), Counter(), Counter()
    for r in recs:
        d = r.get('data') or {}
        rid = d.get('regionId')
        if r.get('kind') == 'winery' and rid:
            wins[rid] += 1
            imgs[rid] += len(d.get('images') or [])
        elif r.get('kind') == 'wine' and rid:
            wines[rid] += 1
        elif r.get('kind') == 'vintage':
            wid = d.get('wineId')
            for r2 in recs:
                if r2['id'] == wid:
                    rid2 = (r2.get('data') or {}).get('regionId')
                    if rid2:
                        vints[rid2] += 1
                    break
    return wins, wines, vints, imgs, len(recs)


def load_or_init():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {
        'createdAt': now_cn().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        'howToRead': '这是"葡萄酒产区采集"任务的实时进度台账。任何对话/任何人想知道"现在做到哪个产区、下一个是哪个"，'
                     '读这个文件（或跑 python3 scripts/progress-ledger.py report）即可，不需要翻历史对话。',
        'cadence': '连续跑，无间隔（自动化每小时触发一轮，一轮做完立刻被下一轮接上）',
        'current': None,
        'rounds': [],
        'regionStats': {},
    }


def refresh_stats(led):
    wins, wines, vints, imgs, total = stats_by_region()
    led['regionStats'] = {rid: {'wineries': wins[rid], 'wines': wines[rid],
                                'vintages': vints[rid], 'images': imgs[rid]}
                          for rid in sorted(set(list(wins) + list(wines) + list(vints)))}
    led['catalogRecords'] = total
    rot = json.loads(ROT.read_text())
    plan = json.loads(PLAN.read_text())
    led['nextCountry'] = rot['queue'][rot['pointer']]['country'] if rot.get('queue') else None
    led['lastCountry'] = rot['recentRuns'][-1]['country'] if rot.get('recentRuns') else None
    led['editorialPlanStatus'] = [{'id': q['id'], 'name': q['name'], 'status': q['status']}
                                  for q in plan['queue']]
    led['updatedAt'] = now_cn().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    return led


def write_md(led):
    cur = led.get('current') or {}
    L = []
    L.append('# 葡萄酒产区采集 · 实时进度台账')
    L.append('')
    L.append('> 更新时间：%s（北京时间）  ' % led.get('updatedAt', ''))
    L.append('> 节奏：%s  ' % led.get('cadence', ''))
    L.append('> 想知道"现在做到哪、下一个做哪"，看下面三行即可；详情在 `data/collection-progress.json`。')
    L.append('')
    L.append('## 现在做到哪')
    L.append('')
    if cur:
        L.append('- **当前国家/产区**：%s / %s' % (cur.get('country', '—'), cur.get('region', '—')))
        L.append('- **当前阶段**：%s' % cur.get('phase', '—'))
        L.append('- **开始时间**：%s' % cur.get('startedAt', '—'))
        for d in cur.get('done') or []:
            L.append('- 已完成：%s' % d)
        for n in cur.get('next') or []:
            L.append('- 接着做：%s' % n)
        for b in cur.get('blockers') or []:
            L.append('- **卡点**：%s' % b)
    else:
        L.append('- 暂无进行中的轮次（等下一轮触发）')
    L.append('')
    L.append('## 接下来做哪个')
    L.append('')
    L.append('- 下一轮国家：**%s**（上一轮：%s）' % (led.get('nextCountry') or '—',
                                                  led.get('lastCountry') or '—'))
    L.append('- 选取器：`python3 scripts/pick-next-country.py`')
    L.append('')
    L.append('## 各国产区内容深度（0 = 空壳，待补）')
    L.append('')
    L.append('| 产区 | 酒庄 | 酒款 | 年份 | 图片 |')
    L.append('| --- | --- | --- | --- | --- |')
    rot = json.loads(ROT.read_text())
    rot_ids = [r.get('id') for e in rot['queue'] for r in e['regions'] if r.get('id')]
    st = led.get('regionStats', {})
    other_ids = [k for k in st if k not in rot_ids]
    for rid in rot_ids + other_ids:
        s = st.get(rid, {})
        L.append('| %s | %d | %d | %d | %d |' % (rid, s.get('wineries', 0), s.get('wines', 0),
                                                 s.get('vintages', 0), s.get('images', 0)))
    L.append('')
    L.append('## 轮次历史（最近 20 条）')
    L.append('')
    for r in (led.get('rounds') or [])[-20:]:
        L.append('- %s %s / %s — %s' % (r.get('date', ''), r.get('country', ''),
                                        r.get('region', ''), r.get('summary', '')))
    L.append('')
    L.append('## 规则提醒')
    L.append('')
    L.append('- 只做采集：不发文、不发消息、不暴露凭据、不改站点成员与 OWNER_EMAIL。')
    L.append('- 每轮换一个国家（跳过上一轮国家），用该国本地语言 + 英语双通道检索内容与图片。')
    L.append('- 交付：`outputs/collect/<region>/` 全套 + ZIP → `wine-content-studio/outputs/collect/<日期>/`。')
    L.append('- 校验：`node scripts/validate-data.mjs` 与 `node scripts/validate-reports.mjs` 必须通过。')
    L.append('')
    if not MD.parent.exists():   # 沙箱里对已存在目录 mkdir 会报 EEXIST，先判断
        MD.parent.mkdir(parents=True)
    MD.write_text('\n'.join(L))
    return MD


def cmd_report(short=False):
    led = refresh_stats(load_or_init())
    write_md(led)
    cur = led.get('current') or {}
    if short:
        print('现在：%s / %s（%s）｜接下来：%s｜进度台账 %s'
              % (cur.get('country', '—'), cur.get('region', '—'), cur.get('phase', '等下一轮'),
                 led.get('nextCountry') or '—', str(MD)))
        return
    print(MD.read_text())


def cmd_update(a):
    led = load_or_init()
    t = now_cn()
    cur = led.get('current') or {}
    if not cur or cur.get('country') != a.country or cur.get('region') != a.region:
        led.setdefault('rounds', [])
    led['current'] = {
        'country': a.country, 'region': a.region, 'phase': a.phase,
        'startedAt': a.started or (cur.get('startedAt') if cur.get('country') == a.country
                                   and cur.get('region') == a.region else t.strftime('%Y-%m-%dT%H:%M:%S+08:00')),
        'updatedAt': t.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        'done': [x for x in (a.done or []) if x],
        'next': [x for x in (a.next or []) if x],
        'blockers': [x for x in (a.blocker or []) if x],
        'artefact': a.artefact or '',
    }
    if a.summary:
        led['rounds'].append({'date': t.strftime('%Y-%m-%d %H:%M'), 'country': a.country,
                              'region': a.region, 'phase': a.phase,
                              'summary': a.summary, 'artefact': a.artefact or ''})
    if a.finish:
        led['current'] = None
    refresh_stats(led)
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1))
    write_md(led)
    print('台账已更新 → %s' % MD)


def cmd_sync():
    led = refresh_stats(load_or_init())
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1))
    write_md(led)
    print('台账统计已重算 → %s' % MD)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    ap.add_argument('--short', action='store_true')
    r = sub.add_parser('report')
    u = sub.add_parser('update')
    for f in ('--country', '--region', '--phase', '--started', '--artefact', '--summary'):
        u.add_argument(f)
    for f in ('--done', '--next', '--blocker'):
        u.add_argument(f, action='append')
    u.add_argument('--finish', action='store_true')
    sub.add_parser('sync')

    # 支持 `progress-ledger.py report` 与 `progress-ledger.py --short` 两种写法
    argv = [a for a in __import__('sys').argv[1:]]
    a = ap.parse_args(argv)
    if a.cmd == 'update':
        cmd_update(a)
    elif a.cmd == 'sync':
        cmd_sync()
    else:
        cmd_report(short=a.short)


if __name__ == '__main__':
    main()
