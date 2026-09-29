# coding: utf-8
"""把采集产出的「图片清单」合并回 catalog-seed.json，让图片真正上网页。

Why this exists
---------------
采集流水线每天会产出两类图片清单，但**从来没有一步把它们并回种子库**：

  1. `outputs/collect/<期>/images/wine-image-manifest.json`
     酒庄官网/名录抓到的图（瓶身、酒标、庄园、人物…），字段最丰富。
  2. `outputs/collect/<期>/images/region-media-manifest.json`
     产区协会/官方机构的图（风景、葡萄园、采收、酒窖…）。

而网页只认一条链路：

    catalog-seed.json 的 data.images[].relativePath
      → scripts/publish-entity-photos.py 生成缩略图 + entity-photos.json
      → public/region-wineries.js 从 /entity-photos.json 取图渲染

所以清单再全，只要没进 catalog，就一张都上不了站。实测滞留：
  · Condrieu 002 期 1,444 张（只登记了 77 张「目录头像」）
  · 产区图 3,057 条（109 个 region 里只有 cornas 有图）
  · 其余各期零散 500+ 张

它在链路里的位置
----------------
    采集脚本 → catalog-additions.json / 两类 image-manifest
                                        ↓  ← 本脚本（补齐这一环）
                              data/catalog-seed.json
                                        ↓
                              publish-entity-photos.py
                                        ↓
                                   网页可见

关键约束（踩过的坑）
--------------------
* `publish-entity-photos.py` 的 `build_source_index()` **只扫
  `outputs/collect/<collection>/images/<folder>/<file>` 这一层**（collection 必须是
  `outputs/collect` 的直接子目录），并用键 `<folder>/<file>` 建索引。所以本脚本
  只登记「能被那个索引命中」的文件——否则登记了也是死链接。嵌套目录（如
  `多国产区批量采集包-2026-09-21/<产区>/images/…`）天生不被索引扫描，跳过。
* `normalize_rel()` 会把 `images/` 前缀剥掉，所以 relativePath 写
  `images/<folder>/<file>`，归一后正好等于索引键 `<folder>/<file>`。
* 产区图统一写成 `images/region/<basename>`——采集清单里的 `file` 字段常是
  临时工作路径（`work/we-src/media/rueda/xxx.png`），照抄会全部失配。
* 同一实体同一路径只登记一次；已有记录不覆盖（保留人工复核过的数据）。
* 写盘前先备份到 `work/`。

Usage
-----
    python3 scripts/merge-collected-media.py --dry-run      # 只看计划
    python3 scripts/merge-collected-media.py                # 真写（先自动备份）
    python3 scripts/merge-collected-media.py --include-unreviewed-region
        # 额外并入 role 为空、reviewAs=region-media-unreviewed 的产区图（默认不并，
        # 这批多为协会官网头图/logo，未过目检）
"""

import argparse
import collections
import glob
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
COLLECT = ROOT / 'outputs' / 'collect'
BACKUP_DIR = ROOT / 'work'

IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.png', '.webp', '.avif', '.gif')
# PIL 认得的位图格式（用于「按内容而不是按后缀」判断）
RASTER_FORMATS = {'JPEG', 'PNG', 'WEBP', 'AVIF', 'GIF', 'BMP', 'TIFF', 'MPO'}


def is_image_file(path):
    """后缀认识就放行；后缀不认识或干脆没有，用 PIL 按内容嗅探。

    ⚠️ 2026-09-22 实测：rheingau 有 8 张 webp **落盘时丢了扩展名**，只按后缀判会
    让它们永远上不了站；`cornas/.../xxx.gif` 也因为后缀不在白名单里被挡。
    两者 PIL 都读得出来，所以按内容判才可靠。`Image.open` 只读文件头，开销很小。
    """
    if path.suffix.lower() in IMAGE_SUFFIXES:
        return True
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.format in RASTER_FORMATS
    except Exception:
        return False


# --------------------------------------------------------------------------
# 源文件索引：刻意复刻 publish-entity-photos.py 的 build_source_index()
# --------------------------------------------------------------------------
def build_source_keys():
    """返回 (key -> [collection, ...], collection -> {key, ...})。

    口径必须与 `publish-entity-photos.py` 的 `build_source_index()` 一致：
    扫 `outputs/collect/<collection>/` 下**任意深度**的图片，键取「父目录名 + 文件名」。

    ⚠️ 2026-09-22 修：原来只扫 `<collection>/images/<folder>/<file>` 这一层，
    于是 `cornas/images-retry/domaine-francois-villard/…` 这类「补采重跑」目录里的图
    两边都登记不上，静默丢掉 53 张酒庄图 + 一批产区图。改成 rglob 全深度。

    第二个返回值是「某采集期里到底有没有这个键」——产区图重名极多
    （`region/region-01.webp` 在 barossa / hawkes / marlborough 都存在，**内容不同**），
    必须按来源采集期精确取，否则 marlborough 会显示 barossa 的图。
    """
    index = collections.defaultdict(list)
    by_collection = collections.defaultdict(set)
    if not COLLECT.is_dir():
        return index, by_collection
    for collection in sorted(COLLECT.iterdir()):
        if not collection.is_dir():
            continue
        for f in sorted(collection.rglob('*')):
            if not f.is_file() or not is_image_file(f):
                continue
            key = f'{f.parent.name}/{f.name}'
            index[key].append(collection.name)
            by_collection[collection.name].add(key)
    return index, by_collection


def build_basename_index(source_keys):
    """文件名 → 候选键。

    有些产区的图放在 `images/region/<二级子目录>/<file>`（如 `region/region-event/…`），
    发布脚本按**一级目录**建键，所以清单里记的 `region/<file>` 对不上。按文件名回查
    可以把它修回真正会被索引命中的键，而不是白白丢掉。
    """
    index = collections.defaultdict(list)
    for key in source_keys:
        index[key.rsplit('/', 1)[-1]].append(key)
    return index


def strip_prefixes(rel):
    """把各种前缀剥干净（`publish-entity-photos.py` 只剥一层，这里剥干净以便比对）。"""
    rel = (rel or '').strip().lstrip('/')
    changed = True
    while changed:
        changed = False
        for prefix in ('images/', './', 'photos/'):
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                changed = True
    return rel


# --------------------------------------------------------------------------
# 实体解析
# --------------------------------------------------------------------------
def build_slug_index(winery_ids, region_ids):
    """winery id -> slug 别名。

    ⚠️ 别名只按**已知产区 id** 精确剥前缀生成，不做「多层尾巴」枚举。
    早先版本把每个 id 的所有后缀都塞进索引，`winery-saint-peray-maison-m-chapoutier`
    于是也贡献了别名 `m-chapoutier`，和 `winery-condrieu-m-chapoutier` 撞成假歧义，
    迫使下游用「猜最近」的启发式、把图片挂到隔壁产区。按真产区 id 剥前缀后
    每个别名只有确切的来源，歧义只会在**真的同名双注册**时出现。
    """
    index = collections.defaultdict(list)
    regions_by_len = sorted(region_ids, key=len, reverse=True)
    for wid in winery_ids:
        body = wid[7:] if wid.startswith('winery-') else wid
        index[body].append(wid)
        for r in regions_by_len:
            if body.startswith(r + '-'):
                index[body[len(r) + 1:]].append(wid)
                break
    return index


def make_winery_resolver(winery_ids, slug_index, fuzzy_log):
    """slug → winery id。

    采集清单里的 `wineryId` 并不总是对的（实测有悬空值，如
    `winery-saint-joseph-vidal-fleury` 在库里根本不存在），`slug` 也可能与
    catalog id 差一个产区前缀。分三级，越靠后越需要人工看一眼：
      1. 清单自报的 wineryId / `<region>-<slug>` 拼法 / 原 slug —— 精确命中；
      2. slug 索引里**带本产区**的唯一候选；
      3. slug 索引里的唯一候选；多个同名双注册且无本产区候选 → 放弃（不猜）。
    第 2、3 级记进 fuzzy_log，报告里逐条打印，不静默。
    """
    def resolve(slug, region='', winery_id=None):
        s = (slug or '').strip()
        r = (region or '').strip()
        base = s[7:] if s.startswith('winery-') else s
        ordered = ([winery_id] if winery_id else []) \
            + ([f'winery-{r}-{base}'] if r else []) \
            + [s, f'winery-{base}', base]
        for cand in ordered:
            if cand and cand in winery_ids:
                return cand
        for cand in (base, s):
            hits = [h for h in slug_index.get(cand, []) if (not r or f'-{r}-' in h)]
            if len(hits) == 1:
                fuzzy_log[f'{s} @ {r} → {hits[0]}（按本产区候选）'] += 1
                return hits[0]
        for cand in (base, s):
            hits = slug_index.get(cand, [])
            if len(hits) == 1:
                fuzzy_log[f'{s} @ {r} → {hits[0]}（全局唯一同名）'] += 1
                return hits[0]
        return None
    return resolve


REGION_SUFFIXES = (' aoc', ' aop', ' docg', ' doc', ' igt', ' vdp', ' 产区')

# 采集清单里的「产区自称」→ catalog 里的 region id。
# 采集脚本常按当地叫法写区域名（意语 Piemonte），而 catalog id 用英文通用名
# （piedmont）。不映射的话 `Piemonte（Barolo / Barbaresco DOCG）` 那 9 张图
# 会被判成「实体解析失败」直接丢掉。
REGION_ALIASES = {
    'piemonte': 'piedmont',
    'toscana': 'tuscany',
    'burgenland': 'burgenland',
}


def region_key(raw):
    s = (raw or '').strip()
    low = s.lower()
    for suf in REGION_SUFFIXES:
        if low.endswith(suf):
            s = s[: -len(suf)]
            low = s.lower()
    # 去掉括号补充说明：Piemonte（Barolo / Barbaresco DOCG）→ piemonte
    for ch in '（(':
        i = s.find(ch)
        if i > 0:
            s = s[:i]
    return s.strip().lower()


def make_region_resolver(region_ids):
    regions = sorted(region_ids)

    def resolve(raw, parent):
        s = (raw or '').strip()
        key = region_key(s)
        cands = [s, f'region-{s}', parent, key, REGION_ALIASES.get(key, ''), parent.lower()]
        for c in cands:
            if c and c in region_ids:
                return c
        for c in cands:
            if not c:
                continue
            hits = [r for r in regions if r == c or r.endswith('-' + c) or c.endswith('-' + r)]
            if len(hits) == 1:
                return hits[0]
        for c in (region_key(s), parent.lower()):
            if not c:
                continue
            hits = [r for r in regions if c in r or r in c]
            if len(hits) == 1:
                return hits[0]
        return None
    return resolve


# --------------------------------------------------------------------------
# 条目构造
# --------------------------------------------------------------------------
def build_entry(item, rel_path, key, collection=None):
    """把采集清单条目转成站点 schema 的 image 记录。"""
    entry = {
        'file': Path(key).name,
        'relativePath': rel_path,
        'role': item.get('role') or None,
        'attribution': item.get('attribution') or None,
        'confidence': item.get('confidence') or None,
        'classificationMethod': item.get('classificationMethod') or None,
    }
    if collection:
        # 来源采集期。发布脚本用它消除同名文件的歧义（region-01.webp 这种名字
        # 在多个采集期都存在且内容不同），不写的话会按字母序取错。
        entry['collection'] = collection
    optional = (
        ('appellation', 'appellation'),
        ('reviewNote', 'reviewNote'),
        ('note', 'reviewNote'),          # 产区清单把说明写在 note
        ('reviewAs', 'reviewAs'),
        ('reasons', 'reasons'),
        ('altText', 'altText'),
        ('alt', 'altText'),
        ('sourceName', 'sourceName'),
        ('sourcePage', 'sourcePage'),
        ('directURL', 'directURL'),
        ('width', 'width'),
        ('height', 'height'),
        ('sha256', 'sha256'),
        ('retrievedAt', 'retrievedAt'),
        ('rights', 'rights'),
    )
    for src, dst in optional:
        if entry.get(dst) is not None:
            continue
        value = item.get(src)
        if value not in (None, '', [], {}):
            entry[dst] = value
    return {k: v for k, v in entry.items() if v is not None}


def collection_dir(path):
    """取 `outputs/collect/<这一层>/…` 里的采集期名。

    ⚠️ 产区清单常放在 `<期>/images/region/region-media-manifest.json`，此时
    `path.parent.parent.name` 是字面量 `images`；酒庄清单在 `<期>/images/` 下，
    那里才是 `<期>`。统一走路径定位，避免把 `images` 当成产区名。
    """
    parts = path.parts
    try:
        i = parts.index('collect')
    except ValueError:
        return ''
    return parts[i + 1] if i + 1 < len(parts) else ''


def manifest_region_id(path):
    """推断 manifest 属于哪个产区：优先用文件里的 region 字段，否则用采集期目录名。"""
    collection = collection_dir(path)
    if collection.startswith('2026-'):
        return 'condrieu'       # 002 期（Condrieu）的目录名是日期
    return collection


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只报告，不写盘')
    ap.add_argument('--seed', default=str(SEED))
    ap.add_argument('--include-unreviewed-region', action='store_true',
                    help='连同 role 为空、reviewAs=region-media-unreviewed 的产区图一起并入')
    ap.add_argument('--region-only', action='store_true',
                    help='只并入产区图（region-media-manifest.json），跳过酒庄/酒款图。'
                         '用于「先补全所有产区的图片、酒庄酒款图暂缓」的分阶段策略（2026-09-26）')
    ap.add_argument('--region-review', metavar='JSON',
                    help='人工审查结果（work/region-media-review.html 导出）。传了它之后，'
                         'role 为空的产区图只并入名单里标了「留」的那些，role 统一记作 region-photo')
    args = ap.parse_args()

    review_keep = None
    if args.region_review:
        rp = Path(args.region_review)
        review = json.loads(rp.read_text(encoding='utf-8'))
        review_keep = set(review.get('keep') or [])
        print(f'人工审查名单：{rp.name} —— 通过 {len(review_keep)} 张'
              f'（丢弃 {len(review.get("drop") or [])}、未定 {len(review.get("undecided") or [])}）')

    seed_path = Path(args.seed)
    seed = json.loads(seed_path.read_text(encoding='utf-8'))
    # ⚠️ 必须在任何改动之前取基线：后面 add() 是就地 append 到 seed 对象上的，
    # 事后再统计 `before_images` 会拿到合并后的数字、断言永远「相等」。
    before_records = len(seed)
    before_images = sum(len((r.get('data') or {}).get('images') or []) for r in seed)
    by_id = {r['id']: r for r in seed}
    winery_ids = {r['id'] for r in seed if r.get('kind') == 'winery'}
    region_ids = {r['id'] for r in seed if r.get('kind') == 'region'}

    source_keys, keys_by_collection = build_source_keys()
    basename_index = build_basename_index(source_keys)
    fuzzy_log = collections.Counter()
    resolve_winery = make_winery_resolver(winery_ids, build_slug_index(winery_ids, region_ids), fuzzy_log)
    resolve_region = make_region_resolver(region_ids)

    # 已有记录：实体 -> 已登记路径集合（用剥离前缀后的形状比对）
    existing = collections.defaultdict(set)
    for r in seed:
        for img in ((r.get('data') or {}).get('images') or []):
            key = strip_prefixes(img.get('relativePath') or img.get('file'))
            if key:
                existing[r['id']].add(key)

    stats = collections.Counter()
    role_stats = collections.Counter()
    unresolved_wineries = collections.Counter()
    unresolved_regions = collections.Counter()
    no_source = collections.Counter()
    ambiguous_hits = collections.Counter()

    def add(entity_id, item, key, collection):
        """登记一条；返回 True 表示真的新增了。

        取文件优先级：
          1. 本采集期里有这个键 → 用它（`collection` 写进条目，发布时不再有歧义）；
          2. 本采集期没命中 → 按文件名回查全局索引（产区图常在 region/<二级>/ 下）；
          3. 都没有 → 不登记（登记了也是死链接）。
        """
        if not entity_id or not key:
            return False
        if key in existing[entity_id]:
            stats['duplicate'] += 1
            return False
        source = collection
        if not source or key not in keys_by_collection.get(source, ()):
            # 一级目录猜错，或文件不在本采集期 → 按文件名回查真键
            candidates = basename_index.get(key.rsplit('/', 1)[-1], [])
            if len(candidates) == 1:
                key = candidates[0]
                stats['key_repaired'] += 1
            if source and key in keys_by_collection.get(source, ()):
                pass
            else:
                in_this = [c for c in source_keys.get(key, []) if c == source]
                others = source_keys.get(key)
                if in_this:
                    pass
                elif others:
                    source = others[0]
                    stats['collection_fallback'] += 1
                else:
                    no_source[key] += 1
                    return False
        if key in existing[entity_id]:
            stats['duplicate'] += 1
            return False
        candidates = source_keys.get(key) or []
        if len(candidates) > 1:
            ambiguous_hits[key] += 1
        by_id[entity_id].setdefault('data', {})
        images = by_id[entity_id]['data'].setdefault('images', [])
        images.append(build_entry(item, 'images/' + key, key, source))
        existing[entity_id].add(key)
        stats['added'] += 1
        role_stats[item.get('role') or '(空)'] += 1
        return True

    # ---- 1) 酒庄 / 酒款图（wine-image-manifest.json）----
    # --region-only 时整段跳过：本轮策略是先补全产区图，酒庄/酒款图暂缓。
    for f in ([] if args.region_only else sorted(glob.glob(str(COLLECT / '**' / 'wine-image-manifest.json'), recursive=True))):
        path = Path(f)
        data = json.loads(path.read_text(encoding='utf-8'))
        region = data.get('region') or manifest_region_id(path)
        producers = data.get('producers') if isinstance(data, dict) else data
        for producer in (producers or []):
            wid = resolve_winery(producer.get('slug'), region, producer.get('wineryId'))
            if not wid:
                n = len(producer.get('images') or [])
                if n:
                    unresolved_wineries[f"{producer.get('slug')} ({n})"] += 1
                stats['winery_entity_miss'] += n
                continue
            for item in (producer.get('images') or []):
                rel = item.get('relativePath') or item.get('file') or ''
                key = strip_prefixes(rel)
                if not key:
                    continue
                # 归一后的键必须形如 <folder>/<file>；若只剩文件名，用采集期目录补 folder
                if '/' not in key:
                    slug = (producer.get('slug') or '').strip()
                    candidate = f'{slug}/{Path(key).name}'
                    if candidate in source_keys:
                        key = candidate
                stats['winery_seen'] += 1
                add(wid, item, key, collection_dir(path))

    # ---- 2) 产区图（region-media-manifest.json）----
    for f in sorted(glob.glob(str(COLLECT / '**' / 'region-media-manifest.json'), recursive=True)):
        path = Path(f)
        data = json.loads(path.read_text(encoding='utf-8'))
        # 2026-09-26：清单有三种 schema —— `items[]` / `images[]` / 早期采集 pass
        # 写的 `entries[]`（file 指向 work/world-src/media/<region>/…，发布副本已按
        # basename 存在于 outputs/collect/<region>/images/region/）。不认 entries
        # 会让 soave/bolgheri/dao/paso-robles/itata/martinborough 这些产区
        # 「盘上有 30 张图却一张都上不了站」。
        items = (data.get('items') or data.get('images') or data.get('entries') or []) if isinstance(data, dict) else data
        if not items:
            continue
        # 产区 id 的来源有三处，按可信度取：
        #   1) 清单顶层 regionId / region（主流写法）
        #   2) 首条元素自带的 regionId —— 早期 pass 写成「裸 list」，
        #      顶层没有 regionId，只有每条 entry 里有（codru 等产区就是这样，
        #      旧逻辑 raw='' 直接判为「实体解析失败」，124 条图白丢）
        #   3) 采集期目录名兜底
        raw = ''
        if isinstance(data, dict):
            raw = data.get('regionId') or data.get('region') or ''
        if not raw and items and isinstance(items[0], dict):
            raw = items[0].get('regionId') or items[0].get('region') or ''
        rid = resolve_region(raw, manifest_region_id(path))
        if not rid:
            stats['region_entity_miss'] += len(items)
            unresolved_regions[f'{raw} @ {collection_dir(path)}'] += len(items)
            continue
        # 采集包有两种摆法：`<产区>/images/region/…`（顶层）和
        # `多国产区批量采集包-<日期>/<产区>/images/region/…`（嵌套）。同一份清单会出现两次。
        # 发布脚本只认顶层那种，所以只信顶层副本；嵌套的只当重复登记忽略。
        rel_parts = path.relative_to(COLLECT).parts
        nested = len(rel_parts) > 1 and rel_parts[1] != 'images'
        top_collection = rel_parts[1] if nested else rel_parts[0]
        for item in items:
            role = (item.get('role') or '').strip()
            review_as = (item.get('reviewAs') or '').strip()
            rel = item.get('relativePath') or item.get('file') or ''
            key = f'region/{Path(rel).name}'

            # 人工审查通道：只并名单里标了「留」的
            if not role and review_keep is not None:
                name = Path(rel).name
                if f'{rid}/{name}' not in review_keep:
                    stats['region_review_skipped'] += 1
                    continue
                if not (COLLECT / top_collection / 'images' / 'region' / name).exists():
                    # 嵌套副本单独存在时发布脚本扫不到，登记了也是 404
                    stats['region_review_no_source'] += 1
                    continue
                if add(rid, dict(item, role='region-photo'), key, top_collection):
                    stats['region_review_added'] += 1
                continue

            if not role and not args.include_unreviewed_region:
                stats['region_unreviewed_skipped'] += 1
                continue
            stats['region_seen'] += 1
            add(rid, item, key, collection_dir(path))

    # ---- 3) 报告 ----
    print(f'源索引键 {len(source_keys)} 个（可被 publish-entity-photos.py 命中）')
    print(f'酒庄/酒款图：扫描 {stats["winery_seen"]} 条')
    print(f'产区图：扫描 {stats["region_seen"]} 条（跳过未过目检 {stats["region_unreviewed_skipped"]}）')
    if review_keep is not None:
        print(f'产区图（人工审查）：并入 {stats["region_review_added"]} 张、'
              f'名单外跳过 {stats["region_review_skipped"]} 条、无顶层副本 {stats["region_review_no_source"]} 张')
    print(f'→ 合计新增 {stats["added"]} 条；重复 {stats["duplicate"]} 条；源文件不可命中 {sum(no_source.values())} 条')
    print(f'实体解析失败：酒庄图 {stats["winery_entity_miss"]} 条、产区图 {stats["region_entity_miss"]} 条')
    print(f'\n新增条目 role 分布：{role_stats.most_common(20)}')

    if no_source:
        print(f'\n⚠️ 源文件不在发布脚本的索引里（未登记，{len(no_source)} 个键）：')
        for k in list(no_source)[:10]:
            print('   · ' + k)
    if ambiguous_hits:
        print(f'\n⚠️ {len(ambiguous_hits)} 个键在多个采集期都存在，发布时按字母序取第一个。')
    if unresolved_wineries:
        print(f'\n⚠️ 未解析酒庄 slug（前 10，括号内为失联图片数）：')
        for k in list(unresolved_wineries)[:10]:
            print('   · ' + k)
    if unresolved_regions:
        print(f'\n⚠️ 未解析产区（前 10）：')
        for k in list(unresolved_regions)[:10]:
            print('   · ' + k)
    if fuzzy_log:
        print(f'\nℹ️ 模糊匹配 {len(fuzzy_log)} 个 slug（清单自报 id 悬空或多候选，按最近匹配）：')
        for k, n in fuzzy_log.most_common(15):
            print(f'   · {k}  [{n} 张]')
        if len(fuzzy_log) > 15:
            print(f'   … 其余 {len(fuzzy_log) - 15} 个')

    audit = {
        'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'goal': '把采集图片清单合并回 catalog-seed.json，让图片经 publish-entity-photos.py 上站',
        'counts': dict(stats),
        'newRoles': dict(role_stats),
        'fuzzySlugMatches': dict(fuzzy_log),
        'unresolvedWinerySlugs': dict(unresolved_wineries),
        'unresolvedRegions': dict(unresolved_regions),
        'sourceNotIndexed': sorted(no_source),
        'keyInMultipleCollections': sorted(ambiguous_hits),
    }
    audit_dir = COLLECT / '_co-build'
    if audit_dir.is_dir():
        audit_path = audit_dir / 'media-merge-report.json'
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(f'\n审计报告 → {audit_path}')

    if not stats['added']:
        print('\n没有需要新增的条目。')
        return

    if args.dry_run:
        print('\n--dry-run：未写盘。')
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = BACKUP_DIR / f'catalog-seed.backup-{stamp}.json'
    shutil.copy2(seed_path, backup)
    print(f'\n备份 → {backup}')

    seed_path.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')

    after = json.loads(seed_path.read_text(encoding='utf-8'))
    after_images = sum(len((r.get('data') or {}).get('images') or []) for r in after)
    assert len(after) == before_records, '记录数不该变！'
    assert after_images == before_images + stats['added'], \
        f'图片数对不上：{before_images} + {stats["added"]} != {after_images}'

    withimg = collections.Counter()
    for r in after:
        if (r.get('data') or {}).get('images'):
            withimg[r['kind']] += 1
    print(f'落盘完成：记录 {before_records} 条不变，图片条目 {before_images} → {after_images}')
    print('有图实体：' + ' · '.join(f'{k} {v}' for k, v in sorted(withimg.items())))


if __name__ == '__main__':
    main()
