# coding: utf-8
"""Sync the 2026-09-18 Cornas image round into data/catalog-seed.json and the
delivery bundle's catalog-additions.json.

Idempotent, follows the same rules as the 2026-09-17 round:
- target record = wineryId match first, else normalised-name match (cross-region
  producers keep their ORIGINAL stable ID — no record is created or moved);
- images attach by filename union, dedupe additionally by sha256;
- for images already attached, only the *classification* fields are refreshed
  (role / attribution / appellation / confidence / classificationMethod /
  reviewedAt / reviewNote) — name, source, regionId and version are untouched;
- a pre-merge snapshot is written once (idempotent backup).

Also records honest zero-image reasons for the two sites that cannot be crawled
by this toolchain (ferraton.fr, jean-baptiste-souillard.com).

Usage: python3 scripts/sync-cornas-images-2026-09-18.py
"""
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'outputs' / 'collect' / 'cornas' / 'images'
MANIFEST = IMAGES / 'wine-image-manifest.json'
SEED = ROOT / 'data' / 'catalog-seed.json'
BACKUP = ROOT / 'work' / '_catalog-seed.before-cornas-images-2026-09-18.json'
OUT = ROOT / 'outputs' / 'collect' / 'cornas'
TODAY = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')

CLASS_FIELDS = ('role', 'attribution', 'appellation', 'confidence',
                'classificationMethod', 'reviewedAt', 'reviewNote', 'reviewAs')

ZERO_IMAGE_NOTES = {
    'ferraton-pere-fils': 'ferraton.fr 已探活并按 robots 允许抓取 16 个页面，但站内只有 '
                          '990×199 装饰横条与 .gif 按钮，无 ≥250px 内容图——0 张是站内实情，'
                          '不是抓取失败；酒款信息为纯文字 ColdFusion 页。',
    'maison-jean-baptiste-souillard': 'jean-baptiste-souillard.com 为 JS 单页应用'
                                      '（建站商 aneox.com），HTML 内无图片节点，'
                                      '需浏览器渲染采集，本轮未采到图。',
    'decelle-villa': 'decelle-villa.com 域名不可达（DNS/连接失败，多后缀变体均 000）。',
    'm-chapoutier': 'chapoutier.com 对自动化请求返回 403（bot 防护），本轮无法采集。',
    'david-reynaud-domaine-les-bruyeres': 'domainelesbruyeres.fr 返回 cgi-sys 默认停放页'
                                          '（163 字节），无实际站点内容。',
}


def norm(text):
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def main():
    manifest = json.loads(MANIFEST.read_text())
    seed = json.loads(SEED.read_text())
    if not BACKUP.exists():
        shutil.copy2(SEED, BACKUP)

    by_id = {r['id']: r for r in seed}
    by_name = {}
    for r in seed:
        if r.get('kind') == 'winery' and norm(r.get('name')):
            by_name.setdefault(norm(r['name']), r)

    report = {'date': TODAY, 'attached': 0, 'refreshed': 0, 'unmapped': [],
              'perProducer': []}
    for p in manifest['producers']:
        imgs = p.get('images') or []
        slug = p['slug']
        target = by_id.get(p.get('wineryId')) or by_name.get(norm(p.get('name')))
        if not target and not imgs and slug in ZERO_IMAGE_NOTES:
            report['perProducer'].append({'slug': slug, 'zeroImageNote': ZERO_IMAGE_NOTES[slug]})
            continue
        if not target:
            report['unmapped'].append({'slug': slug, 'wineryId': p.get('wineryId'),
                                       'images': len(imgs)})
            continue
        data = target.setdefault('data', {})
        data['images'] = data.get('images') or []
        existing = {im.get('file'): im for im in data['images']}
        existing_sha = {im.get('sha256'): im for im in data['images']}
        a, r = 0, 0
        for im in imgs:
            hit = existing.get(im['file']) or existing_sha.get(im.get('sha256'))
            if hit is None:
                data['images'].append(dict(im))
                existing[im['file']] = data['images'][-1]
                if im.get('sha256'):
                    existing_sha[im['sha256']] = data['images'][-1]
                a += 1
            else:
                for f in CLASS_FIELDS:
                    if f in im:
                        hit[f] = im[f]
                r += 1
        if slug in ZERO_IMAGE_NOTES:
            data['imagesNote'] = ZERO_IMAGE_NOTES[slug]
        if a or r:
            report['perProducer'].append({'slug': slug, 'targetId': target['id'],
                                          'attached': a, 'refreshed': r})
        report['attached'] += a
        report['refreshed'] += r
        print('%-34s -> %-52s attach=%-3d refresh=%d'
              % (slug, target['id'], a, r))

    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1) + '\n')

    # Mirror the same into the bundle's catalog-additions records + counts.
    ca_path = OUT / 'catalog-additions.json'
    ca = json.loads(ca_path.read_text())
    recs = {r['id']: r for r in ca.get('records', [])}
    for p in manifest['producers']:
        imgs = p.get('images') or []
        target = recs.get(p.get('wineryId'))
        if target is None:
            key = norm(p.get('name'))
            target = next((r for rid, r in recs.items()
                           if rid.startswith('winery-') and norm(r.get('name')) == key), None)
        if target is None or not imgs:
            continue
        d = target.setdefault('data', {})
        d['images'] = d.get('images') or []
        ex = {im.get('file'): im for im in d['images']}
        ex_sha = {im.get('sha256'): im for im in d['images']}
        for im in imgs:
            hit = ex.get(im['file']) or ex_sha.get(im.get('sha256'))
            if hit is None:
                d['images'].append(dict(im))
                ex[im['file']] = d['images'][-1]
                if im.get('sha256'):
                    ex_sha[im['sha256']] = d['images'][-1]
            else:
                for f in CLASS_FIELDS:
                    if f in im:
                        hit[f] = im[f]

    wineries = [r for r in ca.get('records', []) if r.get('kind') == 'winery']
    counts = ca.setdefault('counts', {})
    counts['producerImages'] = sum(len((r.get('data') or {}).get('images') or []) for r in wineries)
    counts['producersWithImages'] = sum(1 for r in wineries
                                        if (r.get('data') or {}).get('images'))
    counts['withImages'] = counts['producersWithImages']
    counts['reviewedImages'] = sum(
        1 for r in wineries for im in (r.get('data') or {}).get('images') or []
        if im.get('classificationMethod') == 'agent-visual-review')

    tally = {}
    appellation_images = []
    for r in wineries:
        for im in (r.get('data') or {}).get('images') or []:
            if im.get('classificationMethod') != 'agent-visual-review':
                continue
            app = im.get('appellation')
            if app:
                tally[app] = tally.get(app, 0) + 1
                if app == 'Cornas':
                    appellation_images.append({
                        'producer': r.get('name'), 'slug': (r.get('data') or {}).get('manifestSlug') or '',
                        'file': im.get('file'),
                        'relativePath': 'images/' + (im.get('relativePath') or ''),
                    })
    ca['appellationTallyFromReview'] = tally
    ca['cornasAppellationImages'] = appellation_images

    # failures summary (truncated, per skill 2.6)
    unreached, partial = [], []
    for p in manifest['producers']:
        fails = p.get('failures') or []
        imgs = p.get('images') or []
        if fails and not imgs and not p.get('robotsDisallowed'):
            unreached.append({'producer': p.get('name'), 'slug': p['slug'],
                              'website': p.get('website'), 'kind': 'site-unreached',
                              'failureCount': len(fails),
                              'note': ZERO_IMAGE_NOTES.get(p['slug'])})
        elif fails:
            partial.append({'producer': p.get('name'), 'slug': p['slug'],
                            'failureCount': len(fails),
                            'sampleFailures': [
                                {'url': f.get('url', '')[:160], 'error': str(f.get('error', ''))[:160]}
                                for f in fails[:3]]})
    ca['producerImagesUnreached'] = unreached
    ca['producerImagePartialFailures'] = partial
    ca_path.write_text(json.dumps(ca, ensure_ascii=False, indent=1) + '\n')

    report['counts'] = counts
    report['appellationTallyFromReview'] = tally
    (OUT / 'image-attach-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print('\nseed images attached=%d refreshed=%d unmapped=%d'
          % (report['attached'], report['refreshed'], len(report['unmapped'])))
    print('cornas-labelled wine images:', len(appellation_images))
    print('appellation tally:', json.dumps(tally, ensure_ascii=False))


if __name__ == '__main__':
    main()
