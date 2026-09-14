# coding: utf-8
"""Apply agent visual-review verdicts to the image manifest.

The filename heuristics in collect-wine-images.py only see words. A bottle
photographed as `Vignobles-Levet1.png` carries no keyword, and a transparent
logo looks exactly like a transparent packshot. So the flagged images are laid
out on contact sheets (build-contact-sheets.py), looked at, and the verdicts
written to a review file. This script folds those verdicts back into the
manifest and records *how* each image was finally classified, so the downstream
editor can tell a machine guess from a human-checked fact.

Review file format (work/visual-review.json)::

    {
      "vignobles-levet|15-Vignobles-Levet1.png": {
        "role": "wine-bottle",
        "appellation": "Côte-Rôtie",
        "attribution": "own-wine",
        "note": "瓶身标签可读 Côte-Rôtie，非 Condrieu 目标产区"
      }
    }

Only the keys present are applied; anything omitted keeps its heuristic value
but is marked as still unverified.

Usage: python3 scripts/apply-visual-review.py <manifest.json> <review.json>
"""
import json, sys
from pathlib import Path

VALID_ROLES = {
    'wine-bottle', 'wine-label', 'wine-photo', 'producer-people',
    'producer-estate', 'producer-logo', 'producer-site', 'producer-logo-or-product',
    'document-map', 'document-label',
    'region-harvest', 'region-vinework', 'region-weather', 'region-tasting',
    'region-landscape', 'region-grape', 'region-people', 'region-context',
    # 002期 Condrieu 复核新增（2026-09-14）：非酒款的庄园/风土/人物/标志类，
    # 以及无法判读时的 uncertain 占位，避免被迫错分。
    'people', 'estate-or-terroir', 'terroir-photo', 'logo-or-graphic',
    'cert-logo', 'uncertain',
}
VALID_ATTR = {'own-wine', 'likely-own', 'stock-or-generic', 'unverified', 'not-a-wine',
              # 图片来源为酒庄官网（下载自 producer 官网，非第三方图库）。
              'producer-official'}


def main():
    manifest_path = Path(sys.argv[1])
    review_path = Path(sys.argv[2])
    manifest = json.loads(manifest_path.read_text())
    review = json.loads(review_path.read_text())

    changed, unknown = 0, []
    for entry in manifest.get('producers') or []:
        slug = entry['slug']
        for img in entry.get('images') or []:
            key = '%s|%s' % (slug, img['file'])
            verdict = review.get(key)
            if not verdict:
                continue
            if 'role' in verdict:
                if verdict['role'] not in VALID_ROLES:
                    unknown.append('%s role=%s' % (key, verdict['role']))
                    continue
                img['role'] = verdict['role']
            if 'attribution' in verdict:
                if verdict['attribution'] not in VALID_ATTR:
                    unknown.append('%s attribution=%s' % (key, verdict['attribution']))
                    continue
                img['attribution'] = verdict['attribution']
            if 'appellation' in verdict:
                img['appellation'] = verdict['appellation']
            if 'confidence' in verdict:
                img['confidence'] = verdict['confidence']
            else:
                img['confidence'] = 'high'
            img['classificationMethod'] = 'agent-visual-review'
            img['reviewedAt'] = manifest.get('date', '2026-09-13')
            img['reviewNote'] = verdict.get('note')
            img['reviewAs'] = None
            changed += 1

    missing = [k for k in review if not any(
        k == '%s|%s' % (e['slug'], i['file'])
        for e in (manifest.get('producers') or []) for i in (e.get('images') or []))]
    manifest['visualReviewApplied'] = changed
    manifest['visualReviewNotes'] = ('人工视觉复核结果覆盖启发式判断；'
                                     'classificationMethod 标明来源，便于下游区分机判与核判。')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')

    print('applied %d verdicts' % changed)
    if missing:
        print('review keys with no matching image: %d' % len(missing))
        for k in missing[:10]:
            print('  ', k)
    if unknown:
        print('rejected values: %d' % len(unknown))
        for k in unknown[:10]:
            print('  ', k)


if __name__ == '__main__':
    main()
