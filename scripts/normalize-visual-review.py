# coding: utf-8
"""Normalize a visual-review file so apply-visual-review.py accepts it.

Two problems this fixes:

1. **Key mismatch** — the manifest's `file` values are sometimes truncated
   (`…-2021-6-7.jpg`) or differ by a letter from the file on disk
   (`…condrieux.png` vs `…condrieu.png`). Keys are realigned by
   slug + leading numeric prefix; anything still unmatched is printed, never
   silently dropped.
2. **Closed enums** — `apply-visual-review.py` rejects unknown `role` /
   `attribution` values (and skips the whole verdict). Loose words written
   while looking at pictures (`people-photo`, `terroir-photo`, `cert-logo`,
   `uncertain`) are mapped onto the site's role/attribution vocabulary.

Usage:
  python3 scripts/normalize-visual-review.py <manifest.json> <review.json> [out.json]

Without out.json the review file is rewritten in place, and the previous
version is kept next to it as `<name>.raw.json`.
"""
import collections
import json
import re
import shutil
import sys
from pathlib import Path

ROLE_MAP = {
    'people-photo': 'producer-people',
    'people': 'producer-people',
    'estate-photo': 'producer-estate',
    'estate-or-terroir': 'producer-estate',
    'cert-logo': 'document-label',
    'logo-or-graphic': 'producer-logo',
    'uncertain': 'producer-site',
    'stock-photo': 'producer-site',
    # 003期 Cornas 复核新增（2026-09-14）：官网里大量非酒款的图（包装、标识、
    # 海报、拼贴、生产/品鉴/活动照、地图与示意图、以及纯装饰底纹与占位图）
    # 必须各自落到站点既有词表，否则 apply 脚本会把整条结论当非法值丢弃。
    'product-packaging': 'producer-logo-or-product',
    'product-food': 'producer-logo-or-product',
    'graphic-illustration': 'logo-or-graphic',
    'brand-logo': 'producer-logo',
    'brand-graphic': 'producer-logo',
    'certification-logo': 'document-label',
    'press-clipping': 'document-label',
    'region-map': 'document-map',
    'region-diagram': 'document-map',
    'poster-artwork': 'producer-site',
    'history-collage': 'producer-site',
    'collage-montage': 'producer-site',
    'photo-lifestyle': 'producer-site',
    'production-photo': 'producer-site',
    'tasting-photo': 'region-tasting',
    'event-photo': 'region-people',
    'region-event': 'region-people',
    # 占位图与纯装饰底纹没有信息量，落到 uncertain 并靠 note 说明不可用。
    'placeholder': 'uncertain',
    'decorative-banner': 'uncertain',
    'decorative-pattern': 'uncertain',
}

TERROIR_KEYWORDS = [
    ('region-harvest', ('采收', '采摘', '拖拉机', '周转箱', 'vendange')),
    ('region-grape', ('葡萄串', '果穗', '成熟的金黄葡萄', 'grappe')),
    ('region-context', ('土壤', '地表', 'sol')),
]

APPELLATION_MAP = {
    'Cote-Rotie': 'Côte-Rôtie',
    'Ermitage': 'Hermitage',
    'Chateauneuf-du-Pape': 'Châteauneuf-du-Pape',
}


def map_role(role, note):
    if role == 'terroir-photo':
        hay = note or ''
        for target, kws in TERROIR_KEYWORDS:
            if any(k in hay for k in kws):
                return target
        return 'region-landscape'
    return ROLE_MAP.get(role, role)


def main():
    manifest_path = Path(sys.argv[1])
    review_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else review_path

    manifest = json.loads(manifest_path.read_text())
    review = json.loads(review_path.read_text())

    actual = [(e['slug'], i['file']) for e in (manifest.get('producers') or [])
              for i in (e.get('images') or [])]
    akeys = {'%s|%s' % (s, f) for s, f in actual}
    by_prefix = collections.defaultdict(dict)
    for s, f in actual:
        m = re.match(r'^(\d+)', f)
        if m:
            by_prefix[s][m.group(1)] = f

    if out_path == review_path:
        shutil.copy(review_path, review_path.with_suffix('.raw.json'))

    out, renamed, unmatched, remapped = {}, 0, [], collections.Counter()
    for key, verdict in review.items():
        slug, _, fname = key.partition('|')
        new_key = key
        if key not in akeys:
            m = re.match(r'^(\d+)', fname)
            if m and m.group(1) in by_prefix.get(slug, {}):
                new_key = '%s|%s' % (slug, by_prefix[slug][m.group(1)])
                renamed += 1
            else:
                unmatched.append(key)
                continue
        note = verdict.get('note') or ''
        role = map_role(verdict.get('role'), note)
        if role != verdict.get('role'):
            remapped[verdict.get('role')] += 1
        app = verdict.get('appellation')
        # 复核时"标面不可读/留空"的结论不是高置信判读：酒款图但产区留空的记 medium，
        # 明写不可读的记 low，其余 high。便于下游区分"看清了"与"看不出来"。
        if 'confidence' in verdict:
            conf = verdict['confidence']
        elif role.startswith('wine-') and app is None:
            conf = 'low' if ('不可读' in note or '留空' in note) else 'medium'
        else:
            conf = 'high'
        out[new_key] = {
            'role': role,
            'attribution': ('own-wine' if role in ('wine-photo', 'wine-bottle', 'wine-label')
                            else 'not-a-wine'),
            'appellation': APPELLATION_MAP.get(app, app),
            'confidence': conf,
            'note': note,
        }

    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print('in %d → out %d | renamed %d | unmatched %d | remapped %s'
          % (len(review), len(out), renamed, len(unmatched), dict(remapped)))
    for k in unmatched:
        print('  unmatched:', k)


if __name__ == '__main__':
    main()
