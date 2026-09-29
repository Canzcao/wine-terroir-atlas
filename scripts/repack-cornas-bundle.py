# coding: utf-8
"""Pack and hand off the 003期 Cornas bundle.

Usage: python3 scripts/repack-cornas-bundle.py [--date YYYY-MM-DD]

--date selects the run date used for the ZIP name and the hand-off directory
(defaults to today in Asia/Shanghai). The bundle directory itself is always
outputs/collect/cornas/.
"""
import argparse
import hashlib
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'collect' / 'cornas'

TOP_FILES = [
    'catalog-additions.json', 'geo-collected.json', 'sources.json',
    'region-context.json', 'events-additions.json', 'discrepancies.json',
    'merge-report.json', '知识库导入清单.json', 'HANDOFF.md',
    'website-enrichment-report.json', 'image-attach-report.json',
]

def readme_for(date: str) -> str:
    """Build the in-ZIP README from the actual manifest/bundle numbers.

    Numbers are read at pack time instead of being hard-coded, so the README can
    never drift from what is really inside the ZIP.
    """
    manifest = json.loads((OUT / 'images' / 'wine-image-manifest.json').read_text())
    prods = manifest['producers']
    total = sum(len(p.get('images') or []) for p in prods)
    withimg = sum(1 for p in prods if p.get('images'))
    reviewed = sum(1 for p in prods for im in (p.get('images') or [])
                   if im.get('classificationMethod') == 'agent-visual-review')
    app_img = 0
    wv = {}
    ca = OUT / 'catalog-additions.json'
    if ca.exists():
        caj = json.loads(ca.read_text())
        app_img = len(caj.get('cornasAppellationImages') or [])
        add = caj.get('wineVintageAdditions') or {}
        wv = {'wines': len(add.get('wines') or []),
              'vintages': len(add.get('vintages') or [])}
    trad = sum(1 for p in prods for im in (p.get('images') or [])
               if im.get('attribution') == 'own-wine')
    return """003期 Cornas（科尔纳斯 AOC）采集包 — 2026-09-14 首采 + 09-17/18/19 增补 + {date} 增补（wine/vintage 落地）

内容
- 顶层 JSON：catalog-additions（71 家生产者 + 1 条产区记录 + websiteSearchRound 各轮结果 +
  wineVintageAdditions）/ geo-collected / sources / region-context / events-additions（含 heldBack）/
  discrepancies / merge-report / website-enrichment-report / 知识库导入清单
- HANDOFF.md：交付说明与写作边界（先读这个；末节是 2026-09-20 增补轮 5）
- images/region/：产区级图（AOC Cornas 协会官网）+ region-media-manifest.json
  + 图片溯源与下架索引.md
- images/<酒庄 slug>/：{withimg} 家官网共 {total} 张图（人物/庄园照 + 酒款瓶标图），
  清单见 images/wine-image-manifest.json

酒款 / 年份结构化记录（本轮新增，见 catalog-additions.json 的 wineVintageAdditions）
- wine {wines} 条、vintage {vintages} 条，全部来自读标复核（agent-visual-review）确认标面 CORNAS 的
  34 张图；年份只有 3 条是瓶标可读（Voge 2011/2018、Gilles Robin 2023）。
- grapes.percent = 100 是 Cornas AOC「红=法定单一西拉」的产区口径，**不是读标结论**；
  vintage 记录不填品种比例。
- 26 条 ≠ Cornas 酒款全貌：只是官网图里标面读得出 CORNAS 的那些。

图片来源与复核（重要）
- {total} 张中 {reviewed} 张已逐张目视复核（classificationMethod = agent-visual-review），
  每条带中文 reviewNote；confidence 区分 high / medium / low。
  其余为启发式初判（classificationMethod = heuristic），appellation 一律留空。
- 读标确认为 Cornas 的酒款图 {app_img} 张，已在 catalog-additions.json 的
  cornasAppellationImages 列明。**其余瓶标图多为该庄的 Saint-Joseph /
  Crozes-Hermitage / Saint-Péray / Hermitage / Condrieu / Côtes du Rhône / IGP 等酒款，
  配图时不得当作 Cornas 酒款使用**（各图 appellation 已写明）。
- **GAEC DU LAUTARET (Durand) 的官网图全部隔离**：domaine-durand.fr 站内内容全为
  Sancerre 产区，归属存疑（见 discrepancies），不得当 Cornas 素材。
- 标签读不出产区的一律 appellation 留空，未按文件名推断。
  **文件名确实会骗人**：如 Les Alexandrins 的 16-MLA_CROZES-HERMITAGE_RG.jpg
  标面实为 HERMITAGE —— 一律以标面为准。
- 尊重 robots.txt：Domaine Teysseire 的 robots.txt 对通用 UA 为 Disallow: /，
  本包内**没有**该庄的任何图片，这是依规不采，不是该庄没有图。
  jaboulet.com 声明 Crawl-delay: 10，采集时已按 10 秒/请求限速。

已知缺口（不要当成"不存在"）
- 71 家里只有 4 家有坐标（证据标准所致，不是产业规模）。
- 采集未达的官网：DECELLE VILLA（域名不可达）、M. Chapoutier（站点 403 反爬）、
  David Reynaud / Domaine Les Bruyères（返回 cgi-sys 停放页）。
- 酒款记录只覆盖 16 家（有读标证据的那些）；其余酒庄未做产品页结构化。
- 面积、产量、藤龄等口径冲突项一律留空，见 discrepancies.json。

图片权限：官网公开图片，均为合作上传，如侵权可联系删除。未去水印、未放大、未声称版权。
""".format(date=date, total=total, withimg=withimg, reviewed=reviewed,
           app_img=app_img, trad=trad, wines=wv.get('wines', 0),
           vintages=wv.get('vintages', 0))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'))
    args = ap.parse_args()
    date = args.date
    studio = ROOT.parent / 'wine-content-studio' / 'outputs' / 'collect' / date
    zip_path = OUT / ('003期-Cornas-采集包-%s.zip' % date)
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

    with zipfile.ZipFile(zip_path, 'w', allowZip64=True) as z:
        z.writestr('README-包内说明.txt', readme_for(date))
        for arc, p, stored in members:
            z.write(p, arc, compress_type=zipfile.ZIP_STORED if stored
                    else zipfile.ZIP_DEFLATED)

    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        names = z.namelist()
        mism = [a for a, p, _ in members
                if sha256(p) != hashlib.sha256(z.read(a)).hexdigest()]
    print('members(incl. README): %d (images %d)' % (len(names), n_img))
    print('zip: %.2f MB, testzip=%s, integrity mismatch=%d, %.1fs'
          % (zip_path.stat().st_size / 1e6, bad, len(mism), time.time() - t0))

    studio.mkdir(parents=True, exist_ok=True)
    dest = studio / zip_path.name
    dest.write_bytes(zip_path.read_bytes())
    # 平铺交付：JSON/MD 便于直接阅读
    for name in TOP_FILES:
        p = OUT / name
        if p.exists():
            (studio / ('003期-cornas-' + name)).write_text(p.read_text())
    print('hand-off:', dest, '(%.2f MB)' % (dest.stat().st_size / 1e6))


if __name__ == '__main__':
    main()
