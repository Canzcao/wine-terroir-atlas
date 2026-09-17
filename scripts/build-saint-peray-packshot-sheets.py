# coding: utf-8
"""Lay out the association-module packshots so the labels can actually be read.

The association crops every bottle to the same 692x1508 template, so a single
tall cell per producer wastes space. Labels sit in the middle of the bottle:
each cell shows the full bottle (so the shape is visible) at a size big enough
that the appellation printed on the label is legible, with the producer slug
captioned underneath so a verdict maps back to `slug|packshot`.

Usage: python3 scripts/build-saint-peray-packshot-sheets.py [--per-sheet 10] [--outdir work/saint-peray/sheets]
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'outputs' / 'collect' / 'saint-peray' / 'images' / 'wine-image-manifest.json'
CELL_H = 620          # bottle height inside a cell
LABEL_H = 30
PAD = 10


def font(size):
    for p in ('/System/Library/Fonts/Supplemental/Arial.ttf',
              '/System/Library/Fonts/Helvetica.ttc'):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-sheet', type=int, default=10)
    ap.add_argument('--outdir', default=str(ROOT / 'work' / 'saint-peray' / 'sheets'))
    ap.add_argument('--kind', default='packshot')
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))

    items = []
    for p in sorted(man['producers'], key=lambda e: e['slug']):
        for im in p.get('images') or []:
            if im.get('classificationMethod') == 'official-module' and im['file'].startswith(args.kind):
                items.append((p['slug'], im, ROOT / 'outputs' / 'collect' / 'saint-peray' / 'images' / im['relativePath']))

    print(f'{args.kind}: {len(items)} images')
    f = font(LABEL_H - 8)
    for s in range(0, len(items), args.per_sheet):
        chunk = items[s:s + args.per_sheet]
        cols = min(5, len(chunk))
        rows = (len(chunk) + cols - 1) // cols
        # work out the widest cell after scaling to CELL_H
        cells = []
        for slug, im, path in chunk:
            try:
                imo = Image.open(path).convert('RGB')
            except Exception as exc:
                print(f'  !! {path} -> {exc}')
                continue
            w, h = imo.size
            nw = max(1, int(w * CELL_H / h))
            cells.append((slug, imo.resize((nw, CELL_H), Image.LANCZOS)))
        cw = max(c[1].width for c in cells) + PAD * 2
        sheet = Image.new('RGB', (cw * cols, (CELL_H + LABEL_H + PAD * 2) * rows), 'white')
        d = ImageDraw.Draw(sheet)
        for i, (slug, imo) in enumerate(cells):
            r, c = divmod(i, cols)
            x = c * cw + (cw - imo.width) // 2
            y = r * (CELL_H + LABEL_H + PAD * 2) + PAD
            sheet.paste(imo, (x, y))
            d.text((c * cw + PAD, y + CELL_H + 6), slug[:34], fill='black', font=f)
        name = f'{args.kind}-sheet-{s // args.per_sheet + 1:02d}.jpg'
        sheet.save(outdir / name, quality=88)
        print(f'  wrote {outdir / name}  ({sheet.width}x{sheet.height})')


if __name__ == '__main__':
    main()
