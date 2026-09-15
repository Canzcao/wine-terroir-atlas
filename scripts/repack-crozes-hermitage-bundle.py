# coding: utf-8
"""Pack and hand off the 006期 Crozes-Hermitage bundle.

ZIP: outputs/collect/crozes-hermitage/006期-Crozes-Hermitage-采集包-2026-09-15.zip
Hand-off copy: ../wine-content-studio/outputs/collect/2026-09-15/

The README is generated from the actual bundle contents (record counts, image
counts, coordinate counts, event counts) instead of being hard-coded, so it can
never drift from what is really in the ZIP.

Usage: python3 scripts/repack-crozes-hermitage-bundle.py
"""
import hashlib
import json
import time
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'crozes-hermitage'
STUDIO = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / '2026-09-15'
ZIP_PATH = OUT / '006期-Crozes-Hermitage-采集包-2026-09-15.zip'

TOP_FILES = [
    'catalog-additions.json', 'geo-collected.json', 'sources.json',
    'region-context.json', 'events-additions.json', 'discrepancies.json',
    'merge-report.json', '知识库导入清单.json', 'HANDOFF.md',
]


def build_readme() -> str:
    add = json.loads((OUT / 'catalog-additions.json').read_text())
    c = add['counts']
    ev = json.loads((OUT / 'events-additions.json').read_text())
    geo = json.loads((OUT / 'geo-collected.json').read_text())
    wr = json.loads((OUT / 'merge-report.json').read_text()) \
        if (OUT / 'merge-report.json').exists() else None

    rman = OUT / 'images' / 'region' / 'region-media-manifest.json'
    role_counts, reviewed = {}, 0
    if rman.exists():
        imgs = json.loads(rman.read_text())['images']
        role_counts = dict(Counter(g['role'] for g in imgs))
        reviewed = sum(1 for g in imgs
                       if g.get('classificationMethod') == 'agent-visual-review')

    wman = OUT / 'images' / 'wine-image-manifest.json'
    prod_slugs, wine_role, prod_reviewed, queued = 0, 0, 0, 0
    unresolved = []
    if wman.exists():
        producers = json.loads(wman.read_text())['producers']
        prod_slugs = sum(1 for e in producers if e.get('images'))
        allw = [g for e in producers for g in e.get('images') or []]
        wine_role = sum(1 for g in allw if str(g.get('role', '')).startswith('wine-'))
        prod_reviewed = sum(1 for g in allw
                            if g.get('classificationMethod') == 'agent-visual-review')
        queued = sum(1 for g in allw if g.get('reviewAs') and g.get('classificationMethod') != 'agent-visual-review')
        unresolved = [('images/%s/%s' % (e['slug'], g['file']))
                      for e in producers for g in e.get('images') or []
                      if g.get('reviewAs') and g.get('classificationMethod') != 'agent-visual-review']

    lines = [
        '006期 Crozes-Hermitage（克罗兹-埃米塔日 AOC）采集包 — 2026-09-15',
        '',
        '内容',
        '- 顶层 JSON：catalog-additions（%d 家生产者 + %d 条产区记录）/ geo-collected /'
        % (c['wineryRecords'], c['regionRecords']),
        '  sources / region-context / events-additions（%d 条 + %d 条 heldBack）/'
        % (len(ev['events']), len(ev.get('heldBack') or [])),
        '  discrepancies / merge-report（并库结果）/ 知识库导入清单',
        '- HANDOFF.md：交付说明与写作边界（先读这个）',
        '- images/region/：%d 张产区级图（crozes-hermitage-vin.fr 协会官网）'
        % c.get('regionImages', 0),
        '  + region-media-manifest.json',
        '- images/<酒庄 slug>/：%d 家有官网图片，共 %d 张（庄园/人物照 + 酒款瓶标图），'
        % (prod_slugs, c.get('producerImages', 0)),
        '  清单见 images/wine-image-manifest.json（其中 %d 张被判为酒款相关）' % wine_role,
        '',
        '产区图分类',
        '- %s' % (role_counts or '（无）'),
        '- 其中 %d / %d 张已逐张目视复核（classificationMethod = agent-visual-review）。'
        % (reviewed, c.get('regionImages', 0)),
        '',
        '生产者图复核',
        '- %d 张已逐张目视复核（role / appellation / confidence / reviewNote 逐条写在'
        % prod_reviewed,
        '  catalog-additions.json 与 images/wine-image-manifest.json）。',
        '- 仍有 %d 张启发式判为「可能酒款」但未复核，文件路径见本包 HANDOFF.md 末节；' % queued,
        '  未复核的一律没有 classificationMethod=agent-visual-review，不得当成人工判读。',
        '',
        '坐标',
        '- 采纳 %d 家；转人工复核 %d 家（OSM 实体类型不符 / 越出北罗讷地理窗 / 落在'
        % (len(geo['acceptedForCoordinates']), len(geo['heldForReview'])),
        '  11 村镇范围外的他处场所）。',
        '- 名录里的通讯地址**不是**葡萄园所在地：本期名录接口自带的坐标是按登记通讯地址',
        '  地理编码所得（含巴黎、博讷、南罗讷等），一律不作为采纳依据。',
        '',
        '并库结果（merge-report.json）',
    ]
    if wr:
        lines += [
            '- 新增 %d 条；另有 %d 家因同时出现在既有产区名录中而**按名匹配、保留原稳定 ID'
            % (len(wr['newRecords']), len(wr['enrichedExistingRecords'])),
            '  就地补齐**，未新建重复记录；目录合计 %d 条。' % wr['catalogueTotal'],
            '- 跨产区生产者 %d 家：原 regionId / 来源 / notes 一律保留，新增产区记在'
            % len(wr['crossRegionProducers']),
            '  data.alsoListedIn，新增来源记在 data.additionalSources。',
            '- 事件新增 %d 条（事件总数 %d 条）。'
            % (len(wr['eventsAdded']), wr['eventsTotal']),
        ]
    else:
        lines.append('- 尚未并库（merge-report.json 缺失）。')

    lines += [
        '',
        '已知缺口',
        '- 名录 136 条里有官网的 %d 家；无官网的条目只到「名录字段」这一层。'
        % c.get('producersWithWebsite', 0),
        '- **本期仍无酒款（wine）/ 年份（vintage）级记录**：只到 winery 与 region 两层，'
        '与 003/005 期同一结构性缺口。',
        '- 面积与家数存在冲突口径（协会 1 964 ha vs 媒体 2 073 ha；名录 136 条 vs 媒体 170+），',
        '  未收敛，见 discrepancies.json。',
        '',
        '图片权限：官网公开图片，均为合作上传，如侵权可联系删除。未去水印、未放大。',
        '',
    ]
    if unresolved:
        lines.append('未复核清单（reviewAs 仍为 possible-wine）：')
        lines += ['  - ' + u for u in unresolved[:40]]
        if len(unresolved) > 40:
            lines.append('  - … 共 %d 张，完整清单见 images/wine-image-manifest.json'
                         % len(unresolved))
    return '\n'.join(lines)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    t0 = time.time()
    members = []
    for name in TOP_FILES:
        p = OUT / name
        if p.exists():
            members.append((name, p, not name.endswith('.json')))
    img_dir = OUT / 'images'
    n_img = 0
    for p in sorted(img_dir.rglob('*')):
        if p.is_file():
            rel = 'images/' + p.relative_to(img_dir).as_posix()
            stored = not p.name.lower().endswith(('.json', '.md'))
            members.append((rel, p, stored))
            n_img += 1

    readme = build_readme()
    with zipfile.ZipFile(ZIP_PATH, 'w', allowZip64=True) as z:
        z.writestr('README-包内说明.txt', readme)
        for arc, p, stored in members:
            z.write(p, arc, compress_type=zipfile.ZIP_STORED if stored
                    else zipfile.ZIP_DEFLATED)

    with zipfile.ZipFile(ZIP_PATH) as z:
        bad = z.testzip()
        names = z.namelist()
        mism = [a for a, p, _ in members
                if sha256(p) != hashlib.sha256(z.read(a)).hexdigest()]
    print('members(incl. README): %d (images %d)' % (len(names), n_img))
    print('zip: %.2f MB, testzip=%s, integrity mismatch=%d, %.1fs'
          % (ZIP_PATH.stat().st_size / 1e6, bad, len(mism), time.time() - t0))

    STUDIO.mkdir(parents=True, exist_ok=True)
    dest = STUDIO / ZIP_PATH.name
    dest.write_bytes(ZIP_PATH.read_bytes())
    for name in TOP_FILES:
        p = OUT / name
        if p.exists():
            (STUDIO / ('006期-crozes-hermitage-' + name)).write_text(p.read_text())
    print('hand-off:', dest, '(%.2f MB)' % (dest.stat().st_size / 1e6))
    print('README lines: %d' % len(readme.splitlines()))


if __name__ == '__main__':
    main()
