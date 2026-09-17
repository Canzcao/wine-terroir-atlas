# coding: utf-8
"""Package 007期 Saint-Péray into a ZIP and deliver it to the content studio.

Delivers to two places:
  outputs/collect/saint-peray/           working copy (flat JSON/MD + images/)
  wine-content-studio/outputs/collect/2026-09-17/
        ├── 007期-Saint-Péray-采集包-2026-09-17.zip
        └── the same flat JSON/MD files (no images: they live in the ZIP)

The ZIP uses zipfile.ZIP_DEFLATED; Chinese member names get the UTF-8 flag
automatically (macOS `unzip -l` shows mojibake — that is a terminal issue, not
a file issue; verify with `python3 -c "import zipfile..."`).
"""
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'saint-peray'
STUDIO = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / '2026-09-17'
DATE = '2026-09-17'
ZIP_NAME = '007期-Saint-Péray-采集包-2026-09-17.zip'

TOP_FILES = [
    'catalog-additions.json', 'events-additions.json', 'geo-collected.json',
    'sources.json', 'region-context.json', 'discrepancies.json',
    'merge-report.json', '知识库导入清单.json', 'HANDOFF.md',
    'images/wine-image-manifest.json', 'images/图片溯源与下架索引.md',
    'images/region/region-media-manifest.json',
    'README-包内说明.txt',
]

README = """007期 Saint-Péray AOC 采集包（2026-09-17）
=============================================

本包是「信息采集」成果，不是科普内容。产区解释、日报、公众号/小红书文案
由下游「内容转化」对话框负责。

内容
  catalog-additions.json   产区 1 条 + 酒庄 37 条（22 条是跨产区重复候选）
  events-additions.json    事件 2 条 + heldBack 降级记录 4 条
  geo-collected.json       坐标：采纳 7 / 同名异地等转人工复核 3 / 无实体证据 27
  region-context.json      产区事实（全部取自协会官网可核对原文）
  discrepancies.json       面积/生产者数/起泡占比/单产等口径冲突与处理动作
  sources.json             逐条来源与核对日
  merge-report.json        并库逐字段变更清单
  知识库导入清单.json       全部「待审核」
  HANDOFF.md               给下游的交接说明与边界
  images/<slug>/           每家酒庄 portrait.jpg + packshot.jpg（+ 官网图）
  images/wine-image-manifest.json        逐张溯源（来源页/直链/SHA-256/像素/角色）
  images/图片溯源与下架索引.md           下架方式说明
  images/region/           产区级配图 10 张 + 清单

图片许可
  全部取自酒庄官网与产区协会官网的公开图片。站点会统一标注
  「均为合作上传，如侵权可联系删除」，由站方处理权利主张。
  未去水印、未放大；每张图都有 SHA-256 与来源直链，可逐张定位删除。
"""


def main():
    STUDIO.mkdir(parents=True, exist_ok=True)
    (OUT / 'README-包内说明.txt').write_text(README, encoding='utf-8')

    zpath = OUT / ZIP_NAME
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel in TOP_FILES:
            f = OUT / rel
            if f.exists():
                z.write(f, arcname=rel)
            else:
                print('  !! missing', rel)
        for d in sorted((OUT / 'images').iterdir()):
            if not d.is_dir() or d.name == 'region':
                continue
            for f in sorted(d.iterdir()):
                if f.is_file() and not f.name.endswith('.json'):
                    z.write(f, arcname=f'images/{d.name}/{f.name}')
        for f in sorted((OUT / 'images' / 'region').iterdir()):
            if f.is_file() and not f.name.endswith('.json'):
                z.write(f, arcname=f'images/region/{f.name}')

    flat = [f for f in TOP_FILES if f != 'README-包内说明.txt']
    for rel in flat:
        src = OUT / rel
        if src.exists():
            shutil.copy2(src, STUDIO / src.name)
    shutil.copy2(zpath, STUDIO / ZIP_NAME)

    mb = zpath.stat().st_size / 1024 / 1024
    print('zip:', zpath.name, f'{mb:.1f} MB')
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
    print('zip members:', len(names))
    print('delivered to:', STUDIO)
    for f in sorted(STUDIO.iterdir()):
        print('  ', f.name)


if __name__ == '__main__':
    main()
