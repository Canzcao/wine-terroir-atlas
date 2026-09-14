# coding: utf-8
"""Build contact sheets so a human/agent can actually look at the collected
images instead of trusting filename heuristics.

The classifier in collect-wine-images.py can only read words. A bottle photo
named `Vignobles-Levet1.png` carries no keyword at all, so anything the
heuristics flagged as wine, or queued as `reviewAs: possible-wine`, is laid out
on numbered sheets. Each cell is numbered so a verdict can be written back per
image without ambiguity.

Usage:
  python3 scripts/build-contact-sheets.py <manifest.json> <outdir> [--per-sheet 20]
"""
import io, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CELL = 320
PAD = 8
LABEL_H = 26
COLS = 5


def load_font(size=16):
    for p in ('/System/Library/Fonts/Supplemental/Arial.ttf',
              '/System/Library/Fonts/Helvetica.ttc',
              '/System/Library/Fonts/SFNSMono.ttf'):
        try:
            return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def select(manifest, mode='all'):
    """Images whose role is uncertain enough to need eyes on them.

    mode 'wine'   -> everything currently called a bottle or a label
    mode 'review' -> images the heuristics queued as possible wines
    mode 'every'  -> the whole set (for a single flagship estate)
    mode 'all'    -> wine plus queued
    """
    out = []
    for e in manifest.get('producers') or []:
        for g in e.get('images') or []:
            is_wine = g['role'] in ('wine-bottle', 'wine-label')
            is_review = bool(g.get('reviewAs'))
            if mode == 'wine' and not is_wine:
                continue
            if mode == 'review' and not is_review:
                continue
            if mode == 'all' and not (is_wine or is_review):
                continue
            out.append((e['slug'], e['name'], g))
    return out


def main():
    manifest_path = Path(sys.argv[1])
    manifest = json.loads(manifest_path.read_text())
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    base = manifest_path.parent          # images live next to the manifest
    per_sheet = 25
    mode = 'all'
    for flag in ('wine', 'review', 'every', 'all'):
        if '--mode' in sys.argv and sys.argv[sys.argv.index('--mode') + 1] == flag:
            mode = flag
    if '--per-sheet' in sys.argv:
        per_sheet = int(sys.argv[sys.argv.index('--per-sheet') + 1])
    rows = (per_sheet + COLS - 1) // COLS      # never clip the last row

    items = select(manifest, mode)
    index, sheets = {}, []
    font = load_font(15)

    for s in range((len(items) + per_sheet - 1) // per_sheet):
        chunk = items[s * per_sheet:(s + 1) * per_sheet]
        W = COLS * CELL + PAD * (COLS + 1)
        H = rows * (CELL + LABEL_H) + PAD * (rows + 1)
        sheet = Image.new('RGB', (W, H), (250, 250, 248))
        draw = ImageDraw.Draw(sheet)
        for i, (slug, name, g) in enumerate(chunk):
            r, c = divmod(i, COLS)
            x = PAD + c * (CELL + PAD)
            y = PAD + r * (CELL + LABEL_H + PAD)
            cell_no = s * per_sheet + i + 1
            path = base / g['relativePath']
            try:
                with Image.open(path) as im:
                    im = im.convert('RGB')
                    im.thumbnail((CELL, CELL), Image.LANCZOS)
                    if g.get('hasAlpha'):
                        draw.rectangle([x, y, x + CELL, y + CELL], fill=(225, 225, 232))
                    sheet.paste(im, (x + (CELL - im.width) // 2, y + (CELL - im.height) // 2))
            except Exception:  # noqa: BLE001
                draw.rectangle([x, y, x + CELL, y + CELL], fill=(240, 220, 220))
                draw.text((x + 8, y + 8), 'unreadable', font=font, fill=(120, 0, 0))
            draw.rectangle([x, y + CELL, x + CELL, y + CELL + LABEL_H], fill=(255, 255, 255))
            draw.text((x + 4, y + CELL + 5), '#%d %s' % (cell_no, g['file'][:34]),
                      font=font, fill=(20, 20, 20))
            index[str(cell_no)] = {
                'sheet': s + 1, 'slug': slug, 'name': name, 'file': g['file'],
                'role': g['role'], 'attribution': g.get('attribution'),
                'appellation': g.get('appellation'),
                'directURL': g['directURL'], 'width': g['width'], 'height': g['height'],
            }
        out = outdir / ('sheet-%02d.jpg' % (s + 1))
        sheet.save(out, quality=88)
        sheets.append(str(out))
        print('wrote %s (%d cells)' % (out, len(chunk)), flush=True)

    (outdir / 'sheet-index.json').write_text(json.dumps(
        {'total': len(items), 'sheets': sheets, 'cells': index},
        ensure_ascii=False, indent=1) + '\n')
    print('\n%d images across %d sheets' % (len(items), len(sheets)))


if __name__ == '__main__':
    main()
