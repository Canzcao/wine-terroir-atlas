"""把「中国台湾」产区里几句已经过时的话改掉。

背景：Canz 2026-09-22 追加了 KAVALAN（威士忌蒸馏厂）之后，产区描述里
「本图鉴暂未收录该地区的酒庄与酒款」「0 家酒庄」这类表述就变成错的了。
产区本身是 0 葡萄酒庄，但面板计数已经会显示「1 家酒庄」，文字必须跟着说清楚
——否则访客会以为图鉴把一家蒸馏厂当成葡萄酒庄。

跑法：python3 scripts/refresh-taiwan-region-copy.py
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import os as _os
BASE = Path(_os.environ.get('TERROIR_ROOT', Path(__file__).resolve().parent.parent))
SEED = BASE / 'data/catalog-seed.json'
CHECKED = '2026-09-22'

DESC_ZH = (
    '中国台湾的酿酒葡萄产区，以彰化县二林镇为核心。二林镇地处浊水溪冲积扇，数十年以酿酒葡萄闻名，'
    '种植面积曾为全地区之冠（1990 年代峰值约 1,800 公顷）；1997 年公卖局终止收购契约后，农户转向自设酒庄，'
    '使二林成为全地区合法酒庄最密集的乡镇。本图鉴暂未收录该地区的葡萄酒庄与酒款；'
    '目前挂在本产区下的 1 家生产者为噶玛兰威士忌酒厂——那是威士忌蒸馏厂，不是葡萄酒庄。'
)

NOTES = (
    '本条目为地图占位产区：按 Canz 的要求只登记「中国台湾」这一层级，'
    '没有收录任何葡萄酒庄/酒款，故面板里的「1 家酒庄」指的是 2026-09-22 应要求挂上来的 '
    '「噶玛兰威士忌酒厂」——威士忌蒸馏厂，非葡萄酒庄，详见该条目自己的 notes。'
    '坐标用岛屿几何中心而非产地中心，仅为把标签落在台湾岛上。'
    'CN 现有产区（ningxia / penglai / shangri-la）的 originalLanguage 均写作 "en"，'
    '本条按实际来源语种写 "zh"。'
)

SUBNOTE = (
    '来源页原文「二林鎮位於彰化縣西南方……該鎮數十年來以釀酒葡萄產業聞名全台，種植面積為全台之冠」；'
    '早期公賣局契作区的核心，也是全地区合法酒庄最密集的乡镇。本图鉴暂未收录该地区酒庄。'
)

PRODUCERS = (
    '来源页对二林镇合法酒庄数给出多个互不一致的数字：农业知识入口网《2010年…產業概述》写'
    '「目前合格酒莊高達22家，是台灣地區成立合法酒莊最多之鄉鎮」；联合新闻网 2025 年稿写'
    '「二林鎮現有11家酒莊」、另一篇写「目前全台368鄉鎮市約有177家酒莊，二林鎮就有9家」。'
    '数字随年份递减；本图鉴暂未收录其中任何一家（产区下唯一的条目是威士忌蒸馏厂噶玛兰，非葡萄酒庄）。'
)

PATCH = {
    ('localizations', 'zh', 'description'): DESC_ZH,
    ('notes',): NOTES,
    ('producersNote',): PRODUCERS,
}


def main():
    seed = json.loads(SEED.read_text(encoding='utf-8'))
    tw = next(e for e in seed if e['id'] == 'taiwan')
    d = tw['data']

    for path, new in PATCH.items():
        cur = d
        for k in path[:-1]:
            cur = cur[k]
        old = cur[path[-1]]
        assert old != new, '内容没变，检查一下：%s' % (path,)
        cur[path[-1]] = new
        print('已改 %s：%d -> %d 字' % ('.'.join(path), len(old), len(new)))

    for sz in d.get('subzones', []):
        if sz.get('name') == '彰化县二林镇':
            print('已改 subzones[彰化县二林镇].note：%d -> %d 字' % (len(sz.get('note') or ''), len(SUBNOTE)))
            sz['note'] = SUBNOTE

    tw['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    backup = BASE / 'work' / ('_catalog-seed.before-tw-copy-%s.json'
                              % datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 落盘后自检 ----
    seed2 = json.loads(SEED.read_text(encoding='utf-8'))
    tw2 = next(e for e in seed2 if e['id'] == 'taiwan')
    for stale in ['暂未收录该地区的酒庄与酒款', '显示 0 家酒庄']:
        hit = stale in json.dumps(tw2, ensure_ascii=False)
        print('过时表述「%s」仍在: %s' % (stale, hit))
        assert not hit, '过时表述没清掉'
    print('产区 updated:', tw2['updated'])
    print('备份:', backup.name)


if __name__ == '__main__':
    main()
