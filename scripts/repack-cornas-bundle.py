# coding: utf-8
"""Pack and hand off the 003期 Cornas bundle.

ZIP: outputs/collect/cornas/003期-Cornas-采集包-2026-09-14.zip
Hand-off copy: ../wine-content-studio/outputs/collect/2026-09-14/

Usage: python3 scripts/repack-cornas-bundle.py
"""
import hashlib
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'cornas'
STUDIO = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / '2026-09-14'
ZIP_PATH = OUT / '003期-Cornas-采集包-2026-09-14.zip'

TOP_FILES = [
    'catalog-additions.json', 'geo-collected.json', 'sources.json',
    'region-context.json', 'events-additions.json', 'discrepancies.json',
    '知识库导入清单.json', 'HANDOFF.md',
]

README = """003期 Cornas（科尔纳斯 AOC）采集包 — 2026-09-14

内容
- 顶层 JSON：catalog-additions（71 家生产者 + 1 条产区记录）/
  geo-collected / sources / region-context / events-additions（7 条 + 2 条 heldBack）/
  discrepancies / 知识库导入清单
- HANDOFF.md：交付说明与写作边界（先读这个）
- images/region/：24 张产区级图 + region-media-manifest.json + 图片溯源与下架索引.md

本期缺口（重要）
- 酒庄人物照与酒款瓶标图 0 张，尚未采集；不要配不存在的图。
- 71 家里只有 4 家有坐标（证据标准所致，不是产业规模）。
- 面积与土壤各方口径冲突，已留空并记入 discrepancies.json。

图片权限：官网公开图片，均为合作上传，如侵权可联系删除。未去水印、未放大。
"""


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
            members.append((name, p, name.endswith('.md')))
    img_dir = OUT / 'images'
    n_img = 0
    for p in sorted(img_dir.rglob('*')):
        if p.is_file():
            rel = 'images/' + p.relative_to(img_dir).as_posix()
            stored = not p.name.lower().endswith(('.json', '.md'))
            members.append((rel, p, stored))
            n_img += 1

    with zipfile.ZipFile(ZIP_PATH, 'w', allowZip64=True) as z:
        z.writestr('README-包内说明.txt', README)
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
    # 平铺交付：JSON/MD 便于直接阅读
    for name in TOP_FILES:
        p = OUT / name
        if p.exists():
            (STUDIO / ('003期-cornas-' + name)).write_text(p.read_text())
    print('hand-off:', dest, '(%.2f MB)' % (dest.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
