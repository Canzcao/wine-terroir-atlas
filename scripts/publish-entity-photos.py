# coding: utf-8
"""Publish collected entity photos as web-servable thumbnails.

Why this exists
---------------
The daily collection pipeline downloads images into
`outputs/collect/<collection>/images/<producer-folder>/<file>` and records each
one on the entity as `data.images[]` (with `relativePath`, `role`, `reviewNote`,
`sourcePage`, ...). **Nothing ever published them**: `public/` contained zero
image files, and `scripts/build.mjs` base64-embeds every file under `public/`
into the worker bundle, so putting photos there would bloat the 7 MB bundle.

This script is the missing publish step:
  source disk  ->  resized JPEG thumbnails  ->  <deploy>/photos/...  (rsynced)
                                            ->  data/entity-photos.json (+ public/)

`server.mjs` serves `<deploy>/photos/*` straight from disk, so thumbnails are
cached by Cloudflare and never enter the worker bundle.

Usage
-----
    python3 scripts/publish-entity-photos.py                        # 全量
    python3 scripts/publish-entity-photos.py --entities winery-chateau-grillet,wine-chateau-grillet
    python3 scripts/publish-entity-photos.py --dry-run              # 只报告不写盘

Notes
-----
* `relativePath` is relative to `<collection>/images/`, and the leading segment
  is the *producer folder* (usually the winery id) — wine entities reuse their
  winery's folder. Different collections can therefore contain the same
  relativePath with different files, so the published path keeps the collection
  segment and ambiguity is reported loudly instead of silently picked.
* Thumbnails are regenerated only when the source is newer (mtime), so repeat
  runs are cheap.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
COLLECT = ROOT / 'outputs' / 'collect'


def resolve_deploy_dir():
    """找到真正会被 deploy.sh rsync 上去的 terroir-deploy 目录。

    ⚠️ 不能用 `ROOT.parent / 'terroir-deploy'`：ROOT 的父级是源码目录旁边，
    不是部署目录，会静默建出一个游离目录、缩略图永远上不了线。
    这里按 环境变量 → WorkBuddy 工作区 glob → 报错 的顺序解析，找不到就停下来，
    绝不猜。
    """
    env = os.environ.get('TERROIR_DEPLOY_DIR')
    if env:
        p = Path(env).expanduser()
        if (p / 'deploy' / 'deploy.sh').is_file():
            return p
        raise SystemExit(f'TERROIR_DEPLOY_DIR={p} 下没有 deploy/deploy.sh，请检查。')
    found = [Path(p) for p in glob.glob(str(Path.home() / 'WorkBuddy' / '*' / 'terroir-deploy'))
             if (Path(p) / 'deploy' / 'deploy.sh').is_file()]
    if not found:
        raise SystemExit(
            '找不到 terroir-deploy 部署目录。请用 --out 指定，或设置环境变量\n'
            '  TERROIR_DEPLOY_DIR=/absolute/path/to/terroir-deploy')
    return max(found, key=lambda p: p.stat().st_mtime)


ROLE_GROUPS = {
    'estate': ['producer-estate', 'producer-site', 'terroir-photo', 'region-landscape', 'region-context',
               'winery', 'region-winery'],
    'wine': ['wine-bottle', 'wine-photo', 'wine-label'],
    'people': ['producer-people', 'region-people'],
    'document': ['document-map', 'document-label', 'producer-photo-directory',
                 'producer-logo', 'producer-logo-or-product', 'logo-or-graphic', 'cert-logo', 'map'],
    'region': ['region-grape', 'region-harvest', 'region-tasting',
               'region', 'region-other', 'region-vineyard', 'region-vinework', 'region-weather',
               # merge-collected-media.py --region-review 人工审查通过后统一给的角色
               'region-photo'],
    'uncertain': ['uncertain'],
}
ROLE_TO_GROUP = {r: g for g, rs in ROLE_GROUPS.items() for r in rs}


def build_source_index():
    """`<父目录名>/<文件名>` -> [(collection, Path), ...]

    ⚠️ **必须扫采集期目录下的任意深度，不能只扫 `<collection>/images/` 这一层。**

    2026-09-22 实测：`cornas/images-retry/domaine-francois-villard/13-….jpg` 这类
    「补采重跑」目录（`images-retry` / `images-r2` / 嵌套采集包 …）里的图，
    老逻辑完全看不见 —— 结果 53 张酒庄图 + 一批产区图**从未上线过**，
    而且 merge 那边也照同一口径登记失败，静默丢掉、只在报告里留一行数字。
    键仍然取「父目录名 + 文件名」，所以 `images/region/x.jpg` 与
    `images-retry/region/x.jpg` 的键都是 `region/x.jpg`，语义不变。
    """
    index = {}
    if not COLLECT.is_dir():
        return index
    for collection in sorted(COLLECT.iterdir()):
        if not collection.is_dir():
            continue
        for f in sorted(collection.rglob('*')):
            if not f.is_file() or not is_image_file(f):
                continue
            index.setdefault(f'{f.parent.name}/{f.name}', []).append((collection.name, f))
    return index


# 按后缀认得就放行；后缀不认识或干脆没有，用 PIL 按内容嗅探。
# ⚠️ 实测：rheingau 有 8 张 webp 落盘时丢了扩展名、cornas 有 1 张 .gif，
# 只按后缀判会让它们永远上不了站，而两者 PIL 都读得出来。
RASTER_FORMATS = {'JPEG', 'PNG', 'WEBP', 'AVIF', 'GIF', 'BMP', 'TIFF', 'MPO'}
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif')


def is_image_file(path):
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return True
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.format in RASTER_FORMATS
    except Exception:
        return False


def pick_source(candidates, preferred):
    """同名文件在多个采集期都存在时，用条目上的 `collection` 定夺。

    ⚠️ 产区图大量使用 `region/region-01.webp` 这种通用名，barossa / hawkes /
    marlborough 下**内容各不相同**（实测 md5 与字节数都不同）。旧逻辑一律按字母序
    取第一个，会让 marlborough 的产区图变成 barossa 的照片。新采集由
    `scripts/merge-collected-media.py` 把来源采集期写进 image 条目的 `collection`
    字段，这里优先按它取；没有该字段的老条目仍旧按字母序（行为不变）。
    """
    if preferred:
        for collection, path in candidates:
            if collection == preferred:
                return collection, path
    return candidates[0]


def build_basename_index():
    """文件名 -> [(collection, Path), ...]，用于修「首段目录名写错」的登记。

    历史登记的 `relativePath` 首段未必等于磁盘目录名：`winery-cornas-michel-johann`
    登记的是 `images/michel-johann/…`，磁盘上却是 `domaine-johann-michel/`
    （采集脚本换过命名）。这类错误按整键查表永远查不到。

    注意这**不是**猜测式别名表：只有在**全盘同名文件恰好一个**时才采用，
    多个候选一律放弃并打进 misses，不猜。
    """
    index = {}
    for key, candidates in build_source_index().items():
        index.setdefault(key.rsplit('/', 1)[-1], []).extend(candidates)
    return index


def normalize_rel(rel):
    """把 relativePath 归一成「<生产商目录>/<文件名>」——磁盘索引就是按这个键建的。

    ⚠️ 必须做这一步，否则会静默丢掉大半图片（2026-09-21 修）。
    种子库里的 relativePath 有两套写法，是两代采集脚本留下的：
      · 老（Château Grillet 那批，823 条）：`winery-chateau-grillet/18-xxx.jpg`
      · 新（condrieu / cornas / saint-joseph / crozes-hermitage / saint-péray，1973 条）：
        `images/vignobles-chirat/01-xxx.jpg`  ← 多了一层 `images/`
    而 `build_source_index()` 的键一直是 `vignobles-chirat/01-xxx.jpg`。
    于是新格式的每一条都被判成「源文件不存在」——旧版脚本一声不响地把
    1,973 条里的大部分丢进了 misses 列表，站上只活了 Château Grillet 的 26 张。
    实测：直接匹配命中 742 条，归一后 2,689 条。
    """
    rel = (rel or '').strip().lstrip('/')
    for prefix in ('images/', './', 'photos/'):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    return rel


def published_name(relative_path):
    """Same folder + stem as the source, always .jpg so the URL is predictable."""
    folder, _, name = relative_path.rpartition('/')
    stem = Path(name).stem
    return f'{folder}/{stem}.jpg'


def thumb_url(collection, relative_path):
    return '/photos/' + quote(f'{collection}/{published_name(relative_path)}', safe='/')


def make_thumb(src, dst, max_edge, quality):
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        with Image.open(dst) as im:
            return im.width, im.height, 'cached'
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        w, h = im.size
        scale = max_edge / max(w, h)
        if scale < 1:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        im.save(dst, 'JPEG', quality=quality, optimize=True, progressive=True)
        return im.width, im.height, 'written'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--entities', help='逗号分隔的实体 id；省略=全量')
    ap.add_argument('--out', help='缩略图输出目录；默认 <terroir-deploy>/photos')
    ap.add_argument('--manifest', default=str(ROOT / 'data' / 'entity-photos.json'))
    ap.add_argument('--public-manifest', default=str(ROOT / 'public' / 'entity-photos.json'))
    ap.add_argument('--max-edge', type=int, default=1200)
    ap.add_argument('--quality', type=int, default=80)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    out_root = Path(args.out) if args.out else resolve_deploy_dir() / 'photos'
    print(f'缩略图输出目录: {out_root}')

    entities = json.loads(SEED.read_text())
    if args.entities:
        wanted = {s.strip() for s in args.entities.split(',') if s.strip()}
        entities = [e for e in entities if e['id'] in wanted]
        missing = wanted - {e['id'] for e in entities}
        if missing:
            print(f'⚠️ 找不到实体: {", ".join(sorted(missing))}', file=sys.stderr)

    index = build_source_index()
    basename_index = build_basename_index()

    manifest, ambiguous, misses, repaired, stats = {}, [], [], [], {'entities': 0, 'images': 0, 'written': 0,
                                                                    'cached': 0, 'bytes': 0}

    for entity in entities:
        images = (entity.get('data') or {}).get('images') or []
        if not images:
            continue
        rows = []
        for img in images:
            rel = normalize_rel(img.get('relativePath'))
            if not rel:
                continue
            candidates = index.get(rel, [])
            if not candidates:
                # 首段目录名写错 → 按文件名回查；只有全盘唯一时才敢用
                by_name = basename_index.get(rel.rsplit('/', 1)[-1], [])
                if len(by_name) == 1:
                    repaired.append(f'{entity["id"]} :: {rel} → {by_name[0][0]}/{by_name[0][1].parent.name}/'
                                    f'{by_name[0][1].name}')
                    candidates = by_name
                else:
                    misses.append(f'{entity["id"]} :: {rel}' + (f'（同名候选 {len(by_name)} 个，不猜）' if by_name else ''))
                    continue
            if len(candidates) > 1:
                chosen = pick_source(candidates, img.get('collection'))
                if chosen != candidates[0]:
                    ambiguous.append(f'{entity["id"]} :: {rel} → ' +
                                     ', '.join(c for c, _ in candidates) +
                                     f'（按 collection={img.get("collection")} 取 {chosen[0]}）')
                else:
                    ambiguous.append(f'{entity["id"]} :: {rel} → ' +
                                     ', '.join(c for c, _ in candidates) +
                                     f'（取 {candidates[0][0]}）')
                collection, src = chosen
            else:
                collection, src = candidates[0]
            dst = out_root / collection / published_name(rel)
            if args.dry_run:
                w, h, state = img.get('width'), img.get('height'), 'dry-run'
            else:
                try:
                    w, h, state = make_thumb(src, dst, args.max_edge, args.quality)
                except Exception as exc:                      # noqa: BLE001
                    misses.append(f'{entity["id"]} :: {rel} 处理失败 {exc}')
                    continue
                if state == 'written':
                    stats['written'] += 1
                    stats['bytes'] += dst.stat().st_size
                else:
                    stats['cached'] += 1
            rows.append({
                'src': thumb_url(collection, rel),
                'w': w,
                'h': h,
                'role': img.get('role'),
                'group': ROLE_TO_GROUP.get(img.get('role'), 'uncertain'),
                'note': img.get('reviewNote'),
                'sourceURL': img.get('sourcePage'),
            })
        if rows:
            manifest[entity['id']] = rows
            stats['entities'] += 1
            stats['images'] += len(rows)

    payload = {
        'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'note': ('采集图片的网页缩略图清单。src 由 server.mjs 的 /photos/* 从磁盘直接提供，'
                 '不进入 worker 产物。group 用于界面上的本地化标签，note 为采集复核原文（中文）。'),
        'entities': manifest,
    }

    print(f'实体 {stats["entities"]} 个 · 图片 {stats["images"]} 张 '
          f'（新生成 {stats["written"]}，命中缓存 {stats["cached"]}，'
          f'新增 {stats["bytes"] / 1048576:.1f} MB）')
    if ambiguous:
        by_collection = sum(1 for row in ambiguous if 'collection=' in row)
        print(f'\n⚠️ relativePath 在多处出现（{len(ambiguous)} 条）：'
              f'其中 {by_collection} 条按条目的 collection 字段精确取，'
              f'其余 {len(ambiguous) - by_collection} 条按字母序取第一个：')
        for row in ambiguous[:15]:
            print('   · ' + row)
        if len(ambiguous) > 15:
            print(f'   … 其余 {len(ambiguous) - 15} 条')
    if repaired:
        print(f'\nℹ️ 按文件名回查修好的登记（首段目录名写错，全盘同名唯一，{len(repaired)} 条）：')
        for row in repaired[:10]:
            print('   · ' + row)
        if len(repaired) > 10:
            print(f'   … 其余 {len(repaired) - 10} 条')
    if misses:
        print(f'\n⚠️ 未找到源文件或处理失败（{len(misses)} 条）：')
        for row in misses[:15]:
            print('   · ' + row)
        if len(misses) > 15:
            print(f'   … 其余 {len(misses) - 15} 条')

    if args.dry_run:
        print('\n--dry-run：未写盘。')
        return

    Path(args.manifest).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    Path(args.public_manifest).write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))
    mf = Path(args.manifest)
    pm = Path(args.public_manifest)
    print(f'清单 → {mf} ({mf.stat().st_size / 1024:.1f} KB)')
    print(f'清单 → {pm} ({pm.stat().st_size / 1024:.1f} KB，供前端 fetch)')
    print(f'缩略图 → {out_root}（随 deploy.sh rsync 上服务器）')


if __name__ == '__main__':
    main()
