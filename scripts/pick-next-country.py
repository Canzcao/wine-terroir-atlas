# coding: utf-8
"""决定本轮该采哪个国家的哪个产区，并打印双语言检索计划。

用法：
  python3 scripts/pick-next-country.py                 # 打印本轮计划（不写状态）
  python3 scripts/pick-next-country.py --json          # 机器可读
  python3 scripts/pick-next-country.py --country ES    # 强制指定国家
  python3 scripts/pick-next-country.py --commit ES --region rioja --summary "..." 
                                                       # 记录本轮已完成的国家并推进指针

规则（data/country-rotation.json）：
- 按 queue 顺序轮转，**跳过上一轮刚做过的国家**；
- 法国排在队列末位（已深耕），只在其他国家都做不动时插入；
- 每轮输出该国本地语言 + 英语的两套检索关键词。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ROT = ROOT / 'data' / 'country-rotation.json'


def load():
    return json.loads(ROT.read_text())


def pick(rot, force=None):
    q = rot['queue']
    last = rot['recentRuns'][-1]['country'] if rot.get('recentRuns') else None
    if force:
        for e in q:
            if e['code'].upper() == force.upper() or e['country'] == force:
                return e, last
        raise SystemExit('国家不在 queue 里：%s（可加进 candidateCountries 后使用）' % force)
    n = len(q)
    for step in range(n):
        e = q[(rot.get('pointer', 0) + step) % n]
        if e['country'] == last and n > 1:
            continue
        return e, last
    return q[0], last


def plan(entry, last):
    todo = [r for r in entry['regions'] if r.get('status') in ('todo', 'queued')]
    return {
        'date': datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'),
        'country': entry['country'],
        'countryCode': entry['code'],
        'lastCountry': last,
        'switched': entry['country'] != last,
        'languages': entry['languages'],
        'extraLocalLanguages': entry.get('extraLocalLanguages', []),
        'regions': todo or entry['regions'],
        'candidateRegions': entry.get('candidateRegions', []),
        'contentSearchTerms': entry['contentSearchTerms'],
        'imageSearchTerms': entry['imageSearchTerms'],
        'note': entry.get('note', ''),
        'checklist': [
            '① 官方名录/协会入口：用本地语言搜「<产区> bodega/Weingut/cantina/quinta/ワイナリー 生産者」'
            '找官方生产者名录，记录分母与来源页',
            '② region 记录富化：官方口径（面积/产量/法规/村镇）+ 地理土壤气候，口径冲突留 null 进 discrepancies',
            '③ 酒庄：逐家核对官网/地址/坐标（OSM 实体名 + POI 类型 + 产区地理窗三重判定）',
            '④ 酒款/年份：官网产品页逐款核对（本地语言关键词），只有瓶标可读的年份才建 vintage',
            '⑤ 图片：协会名录图库 + 官网（人物/庄园照 + 酒款瓶标图），文件名不作判据，必须开图看，逐张记溯源字段',
            '⑥ 事件：本地语言搜采收/天气/活动/新闻；无可核实发生日期就进 heldBack',
            '⑦ localizations：补 originalLanguage + localizations[本地语言]/[en]，只有可靠页面才标 verified',
            '⑧ 交付：outputs/collect/<region>/ 全套 + ZIP（同一天第二轮起加 -HHMM）+ 平铺到 wine-content-studio',
            '⑨ 校验：validate-data.mjs / validate-reports.mjs 通过后才算完成',
        ],
    }


def commit(rot, code, region, summary):
    q = rot['queue']
    idx = next((i for i, e in enumerate(q)
                if e['code'].upper() == code.upper() or e['country'] == code), None)
    if idx is None:
        raise SystemExit('国家不在 queue 里：%s' % code)
    rot['recentRuns'].append({
        'date': datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'),
        'country': q[idx]['country'], 'code': q[idx]['code'],
        'region': region, 'summary': summary,
    })
    rot['pointer'] = (idx + 1) % len(q)
    rot['updated'] = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    ROT.write_text(json.dumps(rot, ensure_ascii=False, indent=1))
    return rot['pointer'], q[rot['pointer']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--country')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--commit')
    ap.add_argument('--region', default='')
    ap.add_argument('--summary', default='')
    a = ap.parse_args()
    rot = load()

    if a.commit:
        ptr, nxt = commit(rot, a.commit, a.region, a.summary)
        print('已记录本轮：%s / %s → 指针 %d，下一轮建议：%s'
              % (a.commit, a.region or '(未写产区)', ptr, nxt['country']))
        return

    entry, last = pick(rot, a.country)
    p = plan(entry, last)
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return
    print('=== 本轮建议 ===')
    print('国家：%s（%s）%s' % (p['country'], p['countryCode'],
                            '← 换国家 ✓' if p['switched'] else '（同上一轮，队列异常请检查）'))
    print('上一轮国家：%s' % (p['lastCountry'] or '（无记录）'))
    print('检索语言：%s' % '、'.join(p['languages']))
    if p['extraLocalLanguages']:
        print('可补充本地语：%s' % '；'.join(p['extraLocalLanguages']))
    print('待做产区：')
    for r in p['regions']:
        print('  - %s（%s）%s' % (r.get('name'), r.get('status'), (' · ' + r.get('note','')) if r.get('note') else ''))
    print('同国候选产区：%s' % '、'.join(p['candidateRegions']))
    print('内容检索词（本地语）：%s' % ' / '.join(p['contentSearchTerms']))
    print('图片检索词（本地语）：%s' % ' / '.join(p['imageSearchTerms']))
    print('=== 清单 ===')
    for c in p['checklist']:
        print(c)


if __name__ == '__main__':
    sys.exit(main())
