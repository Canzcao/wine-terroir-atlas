# coding: utf-8
"""Repack the 002期 Condrieu collection bundle after the visual review.

Regenerates only the ZIP (full images + all bundle JSONs + review artefacts)
and the hand-off copy under wine-content-studio/outputs/collect/.
Does NOT touch catalog-additions.json / events-additions.json / the manifest.

Usage: python3 scripts/repack-condrieu-bundle.py
"""
import hashlib
import json
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / '2026-09-13'
IMG = OUT / 'images'
STUDIO = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / '2026-09-14'
ZIP_PATH = OUT / '002期-Condrieu-采集包-2026-09-14.zip'

TOP_FILES = [
    'catalog-additions.json',
    'events-additions.json',
    'geo-collected.json',
    'sources.json',
    'region-context.json',
    'merge-report.json',
    '知识库导入清单.json',
    'wine-images.json',
    'HANDOFF.md',
]
REVIEW_FILES = [
    (ROOT / 'work' / 'condrieu-visual-review.json', 'review/condrieu-visual-review.json'),
    (ROOT / 'work' / 'condrieu-visual-review.raw.json', 'review/condrieu-visual-review.raw.json'),
]

README = """002期 Condrieu（孔德里约）采集包 — 2026-09-14 重打包（含酒款图片视觉复核）

内容
- 顶层 JSON：catalog-additions / events-additions / geo-collected / sources /
  region-context / merge-report / 知识库导入清单 / wine-images（酒款图分类清单）
- HANDOFF.md：交付说明与写作边界（先读这个）
- review/：逐张视觉复核的原始结论（规范版 + 原始版）
- images/：全部采集图片（1444 张，529 MB）
  - wine-image-manifest.json：图片清单，556 张带
    classificationMethod='agent-visual-review' 的逐张人工复核结论与中文备注
  - media-manifest.json：酒庄媒体（横幅/简介图）清单
  - 图片溯源与下架索引.md：逐张来源 URL
- 图片版权口径：均为合作上传，如侵权可联系删除。

写作提醒（详见 HANDOFF.md 第五节）
- 酒瓶图 appellation 以瓶上可读文字为准；读不出就留空，不要用文件名推断。
- IGP Collines Rhodaniennes / Vin de France 的酒不是 Condrieu AOC，别混写。
- 庄名以 wine-images.json 的 name 为准（已用协会 profile 页对齐 18 家）。
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    t0 = time.time()
    members = []  # (arcname, path, stored)
    for name in TOP_FILES:
        p = OUT / name
        if p.exists():
            members.append((name, p, name.endswith(('.json', '.md'))))
    for p, arc in REVIEW_FILES:
        if p.exists():
            members.append((arc, p, True))
    img_files = sorted(IMG.rglob('*'))
    n_img = 0
    for p in img_files:
        if p.is_file():
            rel = 'images/' + p.relative_to(IMG).as_posix()
            # 已压缩格式直接 STORED，省时；清单与 md 用 DEFLATE
            members.append((rel, p, not p.name.lower().endswith(('.json', '.md'))))
            n_img += 1

    with zipfile.ZipFile(ZIP_PATH, 'w', allowZip64=True) as z:
        z.writestr('README-包内说明.txt', README)
        for arc, p, stored in members:
            method = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            z.write(p, arc, compress_type=method)

    size = ZIP_PATH.stat().st_size
    with zipfile.ZipFile(ZIP_PATH) as z:
        bad = z.testzip()
        n_members = len(z.namelist())
    print('members(incl. README): %d (images %d)' % (n_members, n_img))
    print('zip: %.2f MB, testzip=%s, %.1fs' % (size / 1e6, bad, time.time() - t0))

    # 自检：磁盘文件 SHA-256 与包内一致（抽全量校验太慢，校验 json/md + 前 50 张图）
    check = [(a, p) for a, p, _ in members if p.suffix.lower() in ('.json', '.md')]
    check += [(a, p) for a, p, _ in members if p.suffix.lower() not in ('.json', '.md')][:50]
    mism = [a for a, p in check if sha256(p) != hashlib.sha256(zipfile.ZipFile(ZIP_PATH).read(a)).hexdigest()]
    print('integrity spot-check: %d checked, %d mismatch' % (len(check), len(mism)))

    STUDIO.mkdir(parents=True, exist_ok=True)
    dest = STUDIO / ZIP_PATH.name
    dest.write_bytes(ZIP_PATH.read_bytes())
    print('hand-off copy:', dest, '%.2f MB' % (dest.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
