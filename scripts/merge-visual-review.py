# coding: utf-8
"""Merge a round of visual-review verdicts into an existing review file.

Each collection round produces its own verdict file (review-round2/verdicts.json,
review-round3/verdicts.json, ...). Folding them into one review file by hand is
how a later round silently clobbers an earlier verdict, so this script refuses to
overwrite: a key that already exists must carry an identical verdict, otherwise
the run stops and prints the conflict.

Usage:
  python3 scripts/merge-visual-review.py <base.json> <additions.json> [--dry-run]
                                        [--supersede key1,key2,...]

--supersede lists keys a later round legitimately re-decided (e.g. an earlier
round left the appellation blank because the label was unreadable at contact-sheet
size, and a later round zoomed into the original file and read it). Without it a
re-decision looks exactly like an accident, so it is refused by default.
"""
import json
import sys
from pathlib import Path

FIELDS = ('role', 'attribution', 'appellation', 'confidence', 'note')


def main():
    base_path, add_path = Path(sys.argv[1]), Path(sys.argv[2])
    dry = '--dry-run' in sys.argv

    supersede = set()
    if '--supersede' in sys.argv:
        supersede = {k for k in sys.argv[sys.argv.index('--supersede') + 1].split(',') if k}

    base_doc = json.loads(base_path.read_text())
    base = base_doc.get('reviews', base_doc)
    add_doc = json.loads(add_path.read_text())
    add = add_doc.get('reviews', add_doc)

    added, same, updated, conflicts = 0, 0, [], []
    for key, verdict in add.items():
        if key not in base:
            base[key] = verdict
            added += 1
        elif all(base[key].get(f) == verdict.get(f) for f in FIELDS):
            same += 1
        elif key in supersede:
            updated.append((key, base[key], verdict))
            base[key] = verdict
        else:
            conflicts.append((key, base[key], verdict))

    print('additions file: %d keys' % len(add))
    print('  newly merged : %d' % added)
    print('  identical    : %d' % same)
    print('  superseded   : %d' % len(updated))
    for key, old, new in updated:
        print('    %s' % key)
        print('      was: %s' % old.get('note'))
        print('      now: %s' % new.get('note'))
    print('  conflicts    : %d' % len(conflicts))
    for key, old, new in conflicts[:10]:
        print('    %s' % key)
        print('      base: %s' % json.dumps(old, ensure_ascii=False))
        print('      new : %s' % json.dumps(new, ensure_ascii=False))
    if conflicts:
        raise SystemExit('refusing to write: %d conflicting key(s) — resolve first'
                         % len(conflicts))
    if dry:
        print('dry run, nothing written (total would be %d)' % len(base))
        return

    if 'reviews' in base_doc:
        base_doc['reviews'] = base
    else:
        base_doc = base
    base_path.write_text(json.dumps(base_doc, ensure_ascii=False, indent=1) + '\n')
    print('review file now holds %d verdicts' % len(base))


if __name__ == '__main__':
    main()
