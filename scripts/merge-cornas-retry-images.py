# coding: utf-8
"""Fold the Cornas retry crawl back into the live image manifest.

Why a dedicated script instead of re-running the collector into the same
folder: the live manifest already carries 255 hand-written review verdicts
(`classificationMethod = agent-visual-review` + 中文 reviewNote). Re-running
the collector would rebuild every producer entry from scratch and silently
throw those away. So the retry output goes to its own folder and only *new*
files are merged in.

Identity is content-based (sha256), not filename-based: the retry used the
repaired URL handling, so the same picture may now arrive under a different
name (`Tradition-278x540.png` vs `Tradition-370x720.png`, `%20` vs space).
Comparing names would duplicate the whole set.

New images keep `classificationMethod = heuristic` and their `reviewAs` flag,
i.e. they land in the review queue and are NOT presented as verified.

Usage: python3 scripts/merge-cornas-retry-images.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'outputs' / 'collect' / 'cornas' / 'images'
LIVE = IMAGES / 'wine-image-manifest.json'
NEW_ONLY = ROOT / 'work' / 'cornas-retry-new-images.json'
# Merge order matters only for the `addedBy` tag; identity is sha256-based.
DEFAULT_RETRIES = [
    ROOT / 'outputs' / 'collect' / 'cornas' / 'images-retry',
    ROOT / 'outputs' / 'collect' / 'cornas' / 'images-retry3',
]


def sha_of(path):
    import hashlib
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    retry_dirs = [Path(a) for a in sys.argv[1:]] or DEFAULT_RETRIES
    retry_dirs = [d for d in retry_dirs if (d / 'wine-image-manifest.json').exists()]
    if not retry_dirs:
        print('no retry manifest found in', DEFAULT_RETRIES)
        return 1
    print('merging:', ', '.join(str(d.name) for d in retry_dirs))

    live = json.loads(LIVE.read_text())
    live_by = {p['slug']: p for p in live['producers']}
    new_entries = {}
    added, untouched, copied = 0, 0, 0
    report = {}

    for retry_dir in retry_dirs:
        tag = 'retry-2026-09-14' if retry_dir.name == 'images-retry' else \
            'retry2-2026-09-14'
        retry = json.loads((retry_dir / 'wine-image-manifest.json').read_text())
        for pro in retry['producers']:
            slug = pro['slug']
            target = live_by.get(slug)
            if target is None:
                print('  !! retry producer not in live manifest:', slug)
                continue
            known = set()
            for g in (target.get('images') or []):
                digest = g.get('sha256')
                if not digest:
                    # older entries may lack the digest; hash the file on disk so
                    # the dedupe stays content-based rather than name-based.
                    p = IMAGES / (g.get('relativePath') or '')
                    if p.exists():
                        digest = sha_of(p)
                if digest:
                    known.add(digest)
            fresh = []
            for g in pro.get('images') or []:
                src = retry_dir / g['relativePath']
                if not src.exists():
                    continue
                digest = g.get('sha256') or sha_of(src)
                if digest in known:
                    untouched += 1
                    continue
                known.add(digest)
                dst = IMAGES / slug / Path(g['file']).name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists() or sha_of(dst) != digest:
                    shutil.copy2(src, dst)
                    copied += 1
                g = dict(g)
                g['sha256'] = digest
                g['relativePath'] = '%s/%s' % (slug, dst.name)
                g['addedBy'] = tag
                g['reviewNote'] = None
                g['classificationMethod'] = 'heuristic'
                fresh.append(g)

            if fresh:
                target.setdefault('images', []).extend(fresh)
                added += len(fresh)
                bucket = new_entries.setdefault(slug, {
                    'slug': slug, 'name': target.get('name'),
                    'website': pro.get('website'),
                    'websiteLive': pro.get('websiteLive'),
                    'images': [],
                })
                bucket['images'].extend(fresh)
            r = report.setdefault(slug, {'slug': slug, 'name': target.get('name'),
                                         'new': 0, 'failures': 0})
            r['new'] += len(fresh)
            # The retries run with repaired URL handling, so their failure list is
            # the accurate one; keep the previous count for comparison.
            target['failuresPreviousPass'] = len(target.get('failures') or [])
            target['failures'] = pro.get('failures') or []
            r['failures'] = len(target['failures'])
            if pro.get('websiteLive'):
                target['websiteLive'] = pro['websiteLive']
            for page in pro.get('pagesVisited') or []:
                if page not in (target.get('pagesVisited') or []):
                    target.setdefault('pagesVisited', []).append(page)

    live['retryNote'] = ('2026-09-14 两轮重抓：修正 URL 空格/重音未编码、HTML 实体未解码、'
                         'srcset 整串、Shopify 模板占位符，补 Referer 与 http→https 兜底，'
                         '并允许跟随"改过域名但品牌词相同"的站内链接；'
                         '只并入按 sha256 判断的新图，未触碰已有复核结论。')
    live['retryMergedImages'] = added
    LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=1) + '\n')

    NEW_ONLY.write_text(json.dumps({
        'date': live.get('date'), 'producers': list(new_entries.values()),
        'note': '两轮重抓新增的图（按 sha256 去重后），尚未复核。',
    }, ensure_ascii=False, indent=1) + '\n')

    print('new images merged: %d | already had (skipped): %d | files copied: %d'
          % (added, untouched, copied))
    print('producers gained images: %d' % len(new_entries))
    for r in sorted(report.values(), key=lambda x: -x['new']):
        print('  %-42s new %3d  failures %d' % (r['slug'][:42], r['new'], r['failures']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
