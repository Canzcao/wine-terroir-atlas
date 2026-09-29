# coding: utf-8
"""给产区记录设置"可浮现的参考点"：取本产区内已定位酒庄的实体点位。

用户要求（2026-09-22）：
  国外酒庄先争取每个产区至少有一个能给出位置的酒庄，
  产区边界不确定时，先用那个已定位酒庄的点代替产区的显示点。

规则：
- 只在该产区**已有带坐标酒庄**时执行；
- 选点优先级：locationPrecision 里含"建筑/来访/酒窖/POI/官网"字样 > 其余；同档按名称排序取第一个；
- 写 locationPrecision 明确"这是什么、不是什么"（不代表产区边界）；
- 旧值存 notesHistory；加 regionReferencePoint 记录来源酒庄，便于追溯与回滚；
- 幂等：同一点位重复跑不重复 +1 版本号。
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
GOOD_WORDS = ('建筑', '来访', '酒窖', 'POI', '官网', '联系页', '门口', '门牌', '展厅', 'cellar')


def main():
    seed = json.loads(SEED.read_text())
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    by_region = defaultdict(list)
    for r in recs:
        if r.get('kind') != 'winery':
            continue
        d = r.get('data') or {}
        rid = d.get('regionId')
        if rid and d.get('lat') is not None and d.get('lng') is not None:
            by_region[rid].append(r)

    changed, skipped, no_src = [], [], []
    for r in recs:
        if r.get('kind') != 'region':
            continue
        cands = by_region.get(r['id']) or []
        if not cands:
            continue
        cands.sort(key=lambda w: (0 if any(k in (( w.get('data') or {}).get('locationPrecision') or '')
                                             for k in GOOD_WORDS) else 1,
                                  (w.get('name') or '')))
        w = cands[0]
        wd = w['data']
        d = r.setdefault('data', {})
        same = (d.get('lat') == wd['lat'] and d.get('lng') == wd['lng'])
        if same and (d.get('regionReferencePoint') or {}).get('sourceWineryId') == w['id']:
            skipped.append(r['id'])
            continue
        if d.get('lat') is not None:
            d.setdefault('notesHistory', []).append({
                'field': 'lat/lng', 'previousValue': '%s/%s' % (d.get('lat'), d.get('lng')),
                'replacedAt': NOW,
                'reason': '改为"本产区已定位酒庄的点位"作为产区显示点（旧值为近似代表点/浏览中心）'})
        d['lat'], d['lng'] = wd['lat'], wd['lng']
        d['locationPrecision'] = ('参考点：取本产区内已定位酒庄「%s」的实体点位作为产区显示点。'
                                  '**这不是产区法定边界，也不代表产区范围**；法定边界文件未取得。'
                                  '酒庄点位精度与来源见该酒庄记录的 locationPrecision / locationSourceURL。'
                                  % (w.get('name') or w['id']))
        d['locationSourceURL'] = wd.get('locationSourceURL') or d.get('locationSourceURL')
        d['regionReferencePoint'] = {
            'method': 'located-winery-point',
            'sourceWineryId': w['id'],
            'sourceWineryName': w.get('name'),
            'locatedWineriesInRegion': len(cands),
            'setAt': NOW,
            'note': '产区边界不确定时的显示点方案（用户 2026-09-22 指示）；'
                    '若日后取得法定边界，应以边界几何覆盖此点。',
        }
        r['version'] = int(r.get('version') or 1) + 1
        r['updated'] = NOW
        changed.append((r['id'], w.get('name'), wd['lat'], wd['lng']))
        if not wd.get('locationSourceURL'):
            no_src.append(r['id'])

    SEED.write_text(json.dumps(seed if isinstance(seed, list) else seed, ensure_ascii=False, indent=1))
    print('设置产区参考点：更新 %d 个，跳过（已一致）%d 个' % (len(changed), len(skipped)))
    for c in changed[:10]:
        print('  %s ← %s（%.4f, %.4f）' % c)
    if no_src:
        print('注意：%d 个产区的来源酒庄缺 locationSourceURL：%s' % (len(no_src), '、'.join(no_src[:8])))
    # 仍无点位的产区
    still = [r['id'] for r in recs if r.get('kind') == 'region' and (r.get('data') or {}).get('lat') is None]
    print('仍无点位的产区 %d 个：%s' % (len(still), '、'.join(still)))


if __name__ == '__main__':
    main()
