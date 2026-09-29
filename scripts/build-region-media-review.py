#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「产区图片人工审查台」——一个单文件本地 HTML。

背景
----
`region-media-manifest.json` 里有约 1,900 条 `role` 为空、`reviewAs=region-media-unreviewed`
的产区图。管线自己标了「待开图复核」，所以默认不并进站点。

人不可能凭尺寸参数想象出一张图放进 1:1 方格好不好看。所以这个脚本做三件事：

1. **全局按 sha256 去重**：同一张图在顶层目录和「多国产区批量采集包」里各存一份，
   不先去重的话审查量直接翻倍。
2. **算一个可量化的「丑」指标 —— 方格填充度**。
   网页上每张缩略图都是 1:1 的方格、`object-fit: contain`（不裁酒标）。
   于是图放进方格后能占多满可以精确算出来：
       填充度 = min(宽比, 1/宽比)
   1600×400 的横幅 → 25%（四分之三都是白边）；1200×900 → 75%；1:1 → 100%。
   这样「好不好看」就不再是玄学，而是一个百分比。
3. **把审查台写成单文件 HTML**（双击即开、零依赖、localStorage 记进度），
   缩略图直接按相对路径读本地磁盘，所见即上线后的样子。

用法
----
    # 只生成审查台
    python3 scripts/build-region-media-review.py

    # 顺手看一眼自动建议的分布（不写盘）
    python3 scripts/build-region-media-review.py --dry-run

产物
----
    work/region-media-review.html              单文件审查台（双击打开）
    work/region-media-review.candidates.json   候选全量（含建议，供 merge 回灌核对）

审查完在网页里点「导出结果」，得到 `region-media-review.result.json`，交给：
    python3 scripts/merge-collected-media.py --region-review work/region-media-review.result.json
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BAN = Path(__file__).resolve().parent.parent
COLLECT = BAN / 'outputs' / 'collect'
SEED = BAN / 'data' / 'catalog-seed.json'
OUT_HTML = BAN / 'work' / 'region-media-review.html'
OUT_DATA = BAN / 'work' / 'region-media-review.candidates.json'
ASSETS = BAN / 'work' / 'region-media-review-assets'

# 审查台用的本地预览图规格。
#
# ⚠️ 为什么非要另存一份、而不是直接引用 `../outputs/collect/…`：
# 双击用 file:// 打开时相对路径没问题，但一旦页面被别的东西托管
# （预览面板 / 本地静态服务器 / 换台机器），`..` 会跑到服务根之外被挡掉，
# 表现就是「图全都不显示」。所以预览图必须和 HTML **同级、不带 `..`**。
#
# 卡片最大 276px、放大图层最大约 450px，640px 在视网膜屏上也够 2x，够判质量。
PREVIEW_EDGE = 640
PREVIEW_QUALITY = 78

# 原始文件名里出现这些词，基本可以直接判死：它们不是照片。
DROP_WORDS = {
    'logo', 'logos', 'marca', 'marcas', 'brand', 'brands', 'icon', 'favicon',
    'symbol', 'simbolo', 'símbolo', 'stemma', 'escudo', 'wappen', 'seal', 'badge',
    'banner', 'banners', 'slider', 'slideshow', 'carousel', 'hero', 'header',
    'footer', 'nav', 'navbar', 'menu', 'btn', 'button', 'arrow', 'chevron',
    'social', 'facebook', 'instagram', 'twitter', 'youtube', 'linkedin',
    'whatsapp', 'pinterest', 'tiktok', 'newsletter', 'cookie', 'cookiebot',
    'spinner', 'loading', 'placeholder', 'blank', 'sprite', 'pattern', 'texture',
    'wallpaper', 'bg', 'background', 'wave', 'divider', 'separator', 'pixel',
    'spacer', 'transparent', 'avatar', 'thumb-default', 'no-image',
}

# 方格填充度分档。16:9（56%）是常见的风光构图，得放行；2:1 是 50%，2.22:1 是 45%。
FILL_GOOD = 55      # ≥ 这个值：放进方格基本填满 → 建议留（16:9 = 56%，刚好过线）
FILL_DROP = 45      # < 这个值：白边面积过半 → 建议丢（2.22:1 以下是横幅）
MIN_SIDE_GOOD = 420  # 缩略图格只有 78px，420px 已够 2x 屏；低于这数才叫糊
MIN_SIDE_DROP = 300

# 「这是照片还是排版」的阈值。把图缩到 128px 后量化到 5bit/通道数唯一色：
# 真照片通常 600~2500 色；logo / 纯色块 / 透明底图形 常低于 45 色。
COLORS_GRAPHIC = 45
EDGE_FLAT = 6       # 边缘能量低 = 大块纯色 → 不是照片
EDGE_MONO = 9       # 低色数 + 高边缘 = 单色/黑白图（可能是真照片，交人判断）

# 文件名里出现这些片段（子串匹配，不切词）：百分百不是照片。
DROP_SUBSTRINGS = (
    'no-image', 'no_image', 'noimage', 'nophoto', 'sin-imagen', 'sinimagen',
    'placeholder', 'monowhite', 'white-logo', 'whitelogo', 'non-disponibile',
    'default-image', 'image-not-found', 'coming-soon',
)

METRICS_CACHE = BAN / 'work' / 'region-media-review.metrics.json'


def build_previews(rows: list[dict], force: bool = False) -> dict[str, str]:
    """给审查台生成同级预览图（`work/region-media-review-assets/<hash>.jpg`）。

    文件名用「源路径的 sha1 前 10 位」，**不能用行号**：重算阈值会改变排序，
    行号一变缓存就整体错位，会出现张冠李戴的预览图。

    Return: {rel: 'region-media-review-assets/xxxx.jpg'}
    """
    import hashlib

    from PIL import Image, ImageOps

    ASSETS.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    made = reused = failed = 0
    total_bytes = 0
    for r in rows:
        digest = hashlib.sha1(r['rel'].encode('utf-8')).hexdigest()[:10]
        name = f'{digest}.jpg'
        dst = ASSETS / name
        src = COLLECT / r['rel']
        mapping[r['rel']] = f'region-media-review-assets/{name}'
        if (not force and dst.exists() and dst.stat().st_size > 0
                and dst.stat().st_mtime >= src.stat().st_mtime):
            reused += 1
            total_bytes += dst.stat().st_size
            continue
        try:
            im = Image.open(src)
            im = ImageOps.exif_transpose(im)         # 按 EXIF 转正，否则手机上拍的是躺着的
            if im.mode in ('RGBA', 'LA', 'P'):
                # 带透明通道的要压到白底上。压黑底的话反白 logo 会变成一团黑，
                # 跟站点里的呈现也不一致。
                rgba = im.convert('RGBA')
                bg = Image.new('RGB', rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            else:
                im = im.convert('RGB')
            im.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.LANCZOS)
            im.save(dst, 'JPEG', quality=PREVIEW_QUALITY, optimize=True, progressive=True)
            made += 1
            total_bytes += dst.stat().st_size
        except Exception:
            failed += 1
            mapping[r['rel']] = r['rel']               # 缩不了就退回原图
    print(f'  预览图：生成 {made}、复用缓存 {reused}、失败 {failed}'
          f'（合计 {total_bytes / 1048576:.0f} MB → {ASSETS.relative_to(BAN)}）')
    return mapping


def load_metrics(rows: list[dict]) -> dict[str, dict]:
    """算「色彩复杂度 / 边缘能量」，带磁盘缓存（950 张约 40 秒，之后秒开）。

    Return: rel -> {'colors': int, 'gray': float, 'edge': float}；算不出的键不存在。
    """
    try:
        from PIL import Image            # noqa: N813
    except ImportError:                   # 没装 Pillow 就优雅降级
        return {}
    cache = {}
    if METRICS_CACHE.exists():
        try:
            cache = json.loads(METRICS_CACHE.read_text(encoding='utf-8'))
        except Exception:
            cache = {}

    todo = [r for r in rows if r['rel'] not in cache]
    if todo:
        print(f'  首次运行要读 {len(todo)} 张图算色彩指标（约 {len(todo) // 25} 秒，结果会缓存）…')
    for i, r in enumerate(todo, 1):
        try:
            im = Image.open(COLLECT / r['rel']).convert('RGB')
            im.thumbnail((128, 128))
            w, h = im.size
            px = list(im.getdata())
        except Exception as exc:                     # 坏图不该拖垮整批
            cache[r['rel']] = {'error': str(exc)[:60]}
            continue
        quant = {(a >> 3, b >> 3, c >> 3) for (a, b, c) in px}
        n = len(px) or 1
        gray = sum(1 for (a, b, c) in px if max(a, b, c) - min(a, b, c) < 12) / n
        diff = total = 0
        for y in range(0, h - 1, 2):
            base = y * w
            for x in range(0, w - 1, 2):
                p, q = px[base + x], px[base + x + 1]
                diff += abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2])
                total += 1
        cache[r['rel']] = {
            'colors': len(quant),
            'gray': round(gray, 3),
            'edge': round(diff / max(total, 1) / 3, 1),
        }
        if todo and i % 200 == 0:
            print(f'    … {i}/{len(todo)}')
    if todo:
        METRICS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    return cache


def collection_of(path: Path) -> str:
    """从 `…/outputs/collect/<这一层>/…` 取出这一层的名字（顶层产区目录）。"""
    parts = path.relative_to(COLLECT).parts
    return parts[0] if len(parts) > 1 else ''


def fill_ratio(w: int, h: int) -> int:
    """图片放进 1:1 方格、contain 缩放后，占方格面积的百分比（取整）。"""
    if not w or not h:
        return 0
    a = w / h
    return round(100 * min(a, 1 / a))


def classify(row: dict, taken: dict) -> tuple[str, str]:
    """返回 (建议, 中文理由)。建议 ∈ keep / drop / todo。"""
    sha = row['sha']
    if sha and taken.get(sha):
        return 'drop', f"与「{taken[sha]}」完全同一张图，留一份就够"
    if row['drop_sub']:
        return 'drop', f"原始文件名就是占位图 / 反白 logo（{row['orig']}）"
    if row['drop_name']:
        return 'drop', f"原始文件名像 logo / 横幅 / 按钮（{row['orig'] or '无文件名'}）"

    met = row.get('metrics') or {}
    colors, edge, gray = met.get('colors'), met.get('edge'), met.get('gray')
    if colors is not None and edge is not None:
        if colors <= COLORS_GRAPHIC and edge <= EDGE_FLAT:
            return 'drop', f"整张只有 {colors} 种颜色、没有画面细节 —— 是 logo / 纯色块，不是照片"
        if colors <= COLORS_GRAPHIC and gray is not None and gray >= 0.9 and edge > EDGE_MONO:
            return 'todo', f"单色 / 黑白图（{colors} 色），可能是老照片也可能是黑白排版，需开图看"
        if colors <= COLORS_GRAPHIC:
            return 'todo', f"只有 {colors} 种颜色，不像实拍照片，需开图看"

    f, w, h = row['fill'], row['w'], row['h']
    if not w or not h:
        return 'todo', '尺寸未知，需开图看'
    if f < FILL_DROP:
        return 'drop', f"太扁（{w}×{h}），放进方格 {100 - f}% 都是白边"
    if f < FILL_GOOD:
        return 'todo', f"比例一般（{w}×{h}），方格填充 {f}%，需开图看"
    if min(w, h) < MIN_SIDE_DROP:
        return 'drop', f"像素太小（{w}×{h}），放大到方格会糊"
    if min(w, h) < MIN_SIDE_GOOD:
        return 'todo', f"尺寸偏小（{w}×{h}），方格填充 {f}%"
    return 'keep', f"实拍照片（{w}×{h}），方格填充 {f}%，{colors} 种颜色"


def collect(args) -> tuple[list[dict], Counter]:
    known = {r['id'] for r in json.loads(SEED.read_text(encoding='utf-8')) if r.get('kind') == 'region'}
    files = sorted(glob.glob(str(COLLECT / '**' / 'region-media-manifest.json'), recursive=True))
    raw_rows: list[dict] = []
    stats = Counter()
    stats['manifests'] = len(files)

    for f in files:
        p = Path(f)
        man = p.parent
        data = json.loads(p.read_text(encoding='utf-8'))
        items = (data.get('items') or data.get('images') or []) if isinstance(data, dict) else data
        raw_rg = (data.get('regionId') or data.get('region') or '') if isinstance(data, dict) else ''
        top = collection_of(p)
        rid = raw_rg if raw_rg in known else top
        if rid.startswith('2026-'):
            rid = 'condrieu'          # 002 期的目录名是日期
        for it in items:
            if (it.get('role') or '').strip():
                continue              # 已过目检的不归这里管
            stats['raw_items'] += 1
            name = Path(it.get('relativePath') or it.get('file') or '').name
            if not name:
                continue
            top_copy = COLLECT / top / 'images' / 'region' / name
            u = urlparse(it.get('directURL') or '')
            orig = Path(u.path).name
            raw_rows.append({
                'rid': rid,
                'top': top,
                'sha': it.get('sha256') or '',
                'file': name,
                # 发布脚本只扫 `outputs/collect/<collection>/images/<folder>/<file>` 这一层，
                # 所以一律优先用顶层副本的路径；嵌套副本只是备胎。
                'rel': f'{top}/images/region/{name}' if top_copy.exists()
                       else (man / name).relative_to(COLLECT).as_posix(),
                'nested_only': not top_copy.exists(),
                'w': it.get('width') or 0,
                'h': it.get('height') or 0,
                'bytes': it.get('bytes') or 0,
                'orig': orig,
                'host': u.netloc or '',
                'page': it.get('sourcePage') or '',
                'attribution': it.get('attribution') or '',
            })

    # ---- 按 sha256 全局去重。同一张图在顶层与嵌套包里各存一份是常态。----
    best: dict[str, dict] = {}
    for r in raw_rows:
        key = r['sha'] or f"{r['rid']}#{r['file']}"
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        stats['dup_copies'] += 1
        # 留「非 nested-only」的那份
        if cur['nested_only'] and not r['nested_only']:
            best[key] = r

    rows = list(best.values())
    for r in rows:
        r['fill'] = fill_ratio(r['w'], r['h'])
        stem_tokens = {t for t in ''.join(
            c if (c.isalnum() or c in '_-') else ' '
            for c in Path(r['orig'] or '').stem.lower()
        ).replace('-', ' ').replace('_', ' ').split()}
        r['drop_name'] = bool(stem_tokens & DROP_WORDS)
        low = (r['orig'] or '').lower()
        r['drop_sub'] = any(s in low for s in DROP_SUBSTRINGS)

    print(f'  算色彩指标 …')
    metrics = load_metrics(rows)
    for r in rows:
        m = metrics.get(r['rel']) or {}
        r['metrics'] = None if 'colors' not in m else m

    # ---- 跨产区同一张图：给后面的那条标记出来，但不强制丢 ----
    by_sha_regions: dict[str, list[str]] = {}
    for r in rows:
        by_sha_regions.setdefault(r['sha'], []).append(r['rid'])

    taken: dict[str, str] = {}
    # 先按「更像照片」的顺序过一遍，保证留下的那条是质量好的那条
    ordered = sorted(rows, key=lambda r: (-r['fill'], -(min(r['w'], r['h']) or 0)))
    verdict: dict[int, tuple[str, str]] = {}
    for r in ordered:
        v, why = classify(r, taken)
        verdict[id(r)] = (v, why)
        if v != 'drop' and r['sha'] and r['sha'] not in taken:
            taken[r['sha']] = f"{r['rid']}/{r['file']}"
    for r in rows:
        v, why = verdict[id(r)]
        regs = by_sha_regions.get(r['sha'], [])
        if len(regs) > 1 and v == 'keep':
            why += f"；同一张图也被 {'、'.join(x for x in regs if x != r['rid'])} 采到了"
        r['verdict'], r['why'] = v, why
        stats[f'verdict_{v}'] += 1

    rows.sort(key=lambda r: (r['rid'], {'keep': 0, 'todo': 1, 'drop': 2}[r['verdict']],
                             -r['fill'], r['file']))
    stats['regions'] = len({r['rid'] for r in rows})
    stats['unique'] = len(rows)
    stats['nested_only'] = sum(1 for r in rows if r['nested_only'])
    return rows, stats


def build_html(rows: list[dict], stats: Counter, stamp: str) -> str:
    slim = [{
        'i': i,
        'k': f"{r['rid']}/{r['file']}",     # 稳定键：产区 + 文件名（顶层/嵌套包两种摆法都能对上）
        'r': r['rid'],
        'a': r['asset'],                    # 同级预览图，`src` 直接用这个（不带 `..`）
        's': r['rel'],                      # 真实磁盘路径，只在导出结果里留档
        'w': r['w'], 'h': r['h'],
        'b': r['bytes'],
        'c': (r['metrics'] or {}).get('colors'),
        'o': r['orig'],
        'p': r['page'],
        'f': r['fill'],
        'v': {'keep': 'k', 'todo': 't', 'drop': 'd'}[r['verdict']],
        'y': r['why'],
    } for i, r in enumerate(rows)]
    payload = json.dumps(slim, ensure_ascii=False, separators=(',', ':'))
    counts = {k: stats.get(f'verdict_{k}', 0) for k in ('keep', 'todo', 'drop')}
    meta = json.dumps({
        'stamp': stamp,
        'unique': stats['unique'],
        'raw': stats['raw_items'],
        'dupCopies': stats['dup_copies'],
        'regions': stats['regions'],
        'keep': counts['keep'], 'todo': counts['todo'], 'drop': counts['drop'],
        'nestedOnly': stats['nested_only'],
    }, ensure_ascii=False)

    return HTML_TEMPLATE.replace('__DATA__', payload).replace('__META__', meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只打印统计，不写产物')
    ap.add_argument('--force-previews', action='store_true', help='强制重做全部预览图')
    ap.add_argument('--no-assets', action='store_true',
                    help='不生成同级预览图，图片直接引用 ../outputs/collect/…（'
                         '只在直接双击 HTML 时有效；被任何静态服务器托管都会 404）')
    args = ap.parse_args()

    rows, stats = collect(args)
    stamp = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')

    print(f"扫描清单文件 {stats['manifests']} 个")
    print(f"未过目检条目 {stats['raw_items']} 条 → 去掉重复登记 {stats['dup_copies']} 条 "
          f"→ **唯一图片 {stats['unique']} 张**（覆盖 {stats['regions']} 个产区）")
    if stats['nested_only']:
        print(f"  ⚠️ 其中 {stats['nested_only']} 张只在嵌套包里、没有顶层副本")
    print(f"自动建议：留 {stats['verdict_keep']} · 需你定 {stats['verdict_todo']} · 丢 {stats['verdict_drop']}")

    if args.dry_run:
        print('\n（--dry-run，未写产物）')
        return

    if args.no_assets:
        for r in rows:
            r['asset'] = f"../outputs/collect/{r['rel']}"
        print('  预览图：已跳过（--no-assets），图片按 ../outputs/collect/ 引用')
    else:
        mapping = build_previews(rows, force=args.force_previews)
        for r in rows:
            r['asset'] = mapping[r['rel']]

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(json.dumps({
        'generatedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'stats': dict(stats),
        'candidates': rows,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    OUT_HTML.write_text(build_html(rows, stats, stamp), encoding='utf-8')
    print(f'\n审查台 → {OUT_HTML.relative_to(BAN)}  ({OUT_HTML.stat().st_size / 1024:.0f} KB)')
    print(f'候选表 → {OUT_DATA.relative_to(BAN)}')
    if not args.no_assets:
        print(f'预览图 → {ASSETS.relative_to(BAN)}/  '
              f'（⚠️ 会和 HTML 一起被引用，别单独删这个目录）')
    print('\n打开方式（任选一）：')
    print('  A) 双击 work/region-media-review.html')
    print('  B) 在 work/ 下起本地服务：'
          'python3 -m http.server 8791 --directory work')
    print('     → http://127.0.0.1:8791/region-media-review.html')
    print('\n导出结果后跑：')
    print('  python3 scripts/merge-collected-media.py --region-review work/region-media-review.result.json')


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>产区图片审查台 · 风土图鉴</title>
<style>
:root{
  --bg:#f5f5f7; --panel:#fff; --line:#e3e3e6; --line2:#f0f0f2;
  --ink:#1d1d1f; --ink2:#6e6e73; --ink3:#a1a1a6;
  --keep:#1d7a4f; --keepbg:#e8f5ee;
  --todo:#9a6400; --todobg:#fdf3e0;
  --drop:#9b2c2c; --dropbg:#fbeceb;
  --accent:#751f3d;
  --r:12px;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:var(--bg); color:var(--ink);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
  padding-bottom:96px;
}
h1{font-size:19px;font-weight:600;margin:0}
h2{font-size:14px;font-weight:600;margin:0 0 8px}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}
header.top{background:rgba(255,255,255,.86);backdrop-filter:saturate(180%) blur(18px);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30}
.top-in{padding:14px 16px 12px;max-width:1180px;margin:0 auto}
.top-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.sub{color:var(--ink2);font-size:12.5px}
.sub b{color:var(--ink);font-weight:600}
.bar{height:6px;border-radius:3px;background:var(--line2);overflow:hidden;margin-top:11px;display:flex}
.bar i{display:block;height:100%}
.bar .b-keep{background:var(--keep)}
.bar .b-todo{background:#e0a83a}
.bar .b-drop{background:#c96a66}

.tools{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center}
button{font:inherit;cursor:pointer;border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink);padding:6px 12px;transition:.12s}
button:hover{border-color:#c9c9cf;background:#fafafb}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.primary:hover{background:#5e1831;border-color:#5e1831}
button.sm{padding:4px 9px;font-size:12.5px;border-radius:8px}
select{font:inherit;padding:6px 10px;border-radius:9px;border:1px solid var(--line);background:#fff;color:var(--ink);max-width:230px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;font-size:12.5px;color:var(--ink2)}
.chip.on{background:var(--ink);border-color:var(--ink);color:#fff}

.legend{margin:18px 0 4px;background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.legend ul{margin:0;padding-left:18px;color:var(--ink2);font-size:13px}
.legend li{margin:3px 0}
.legend li b{color:var(--ink);font-weight:600}
.legend .n{display:inline-block;min-width:2.4em;color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}

.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:18px 0 0}
@media(max-width:1000px){.grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:720px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}}
@media(max-width:400px){.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}

.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;display:flex;flex-direction:column}
.card.k{border-color:#b6ddc9}
.card.d{border-color:#e8c3c0}
.card.t{border-color:#eed9ac}
.shot{position:relative;aspect-ratio:1/1;background:
  linear-gradient(45deg,#f4f4f6 25%,transparent 25%,transparent 75%,#f4f4f6 75%),
  linear-gradient(45deg,#f4f4f6 25%,#fbfbfc 25%,#fbfbfc 75%,#f4f4f6 75%);
  background-size:14px 14px;background-position:0 0,7px 7px;
  display:flex;align-items:center;justify-content:center;cursor:zoom-in;overflow:hidden}
.shot img{display:block;max-width:100%;max-height:100%;object-fit:contain}
.tags{position:absolute;top:6px;left:6px;display:flex;flex-wrap:wrap;gap:4px;max-width:calc(100% - 62px)}.tags em,.tag.v{font-style:normal;font-size:11px;padding:2px 7px;border-radius:999px;background:rgba(255,255,255,.92);border:1px solid var(--line);color:var(--ink2);font-variant-numeric:tabular-nums}
.tags em.warn{color:var(--drop);border-color:#e8c3c0;background:var(--dropbg)}
.tag.v{position:absolute;top:6px;right:6px;font-weight:600}
.card.k .tag.v{color:var(--keep);border-color:#b6ddc9;background:var(--keepbg)}
.card.t .tag.v{color:var(--todo);border-color:#eed9ac;background:var(--todobg)}
.card.d .tag.v{color:var(--drop);border-color:#e8c3c0;background:var(--dropbg)}
.body{padding:9px 10px 10px;display:flex;flex-direction:column;gap:7px;flex:1}
.rid{font-size:12px;color:var(--ink2);display:flex;justify-content:space-between;gap:8px}
.rid b{color:var(--ink);font-weight:600;font-size:12.5px}
.why{font-size:11.5px;line-height:1.5;color:var(--ink2)}
.acts{display:flex;gap:6px;margin-top:auto}
.acts button{flex:1;padding:5px 0;font-size:12.5px}
.acts button.on.k{background:var(--keepbg);border-color:#8ec9ab;color:var(--keep);font-weight:600}
.acts button.on.t{background:var(--todobg);border-color:#e5c383;color:var(--todo);font-weight:600}
.acts button.on.d{background:var(--dropbg);border-color:#dfa9a4;color:var(--drop);font-weight:600}

footer.bot{position:fixed;bottom:0;left:0;right:0;background:rgba(255,255,255,.93);backdrop-filter:saturate(180%) blur(18px);border-top:1px solid var(--line);z-index:40}
.bot-in{max-width:1180px;margin:0 auto;padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.tally{font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums}
.tally b{font-weight:600}
.tally .kk{color:var(--keep)}.tally .tt{color:var(--todo)}.tally .dd{color:var(--drop)}
.spacer{flex:1}

.lightbox{position:fixed;inset:0;background:rgba(20,20,22,.72);backdrop-filter:blur(6px);z-index:80;display:none;align-items:center;justify-content:center;padding:22px}
.lightbox.open{display:flex}
.lb-in{background:#fff;border-radius:16px;max-width:min(920px,100%);max-height:100%;overflow:auto;width:100%}
.lb-head{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:12px}
.lb-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 18px 6px}
@media(max-width:640px){.lb-grid{grid-template-columns:1fr}}
.lb-cell{text-align:center}
.lb-cell .cap{font-size:12px;color:var(--ink2);margin-bottom:7px}
.lb-box{aspect-ratio:1/1;background:#fafafb;border:1px solid var(--line);border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;margin:0 auto;max-width:100%}
.lb-box img{max-width:100%;max-height:100%;display:block}
.lb-raw{background:#fafafb;border:1px solid var(--line);border-radius:10px;padding:8px;display:flex;align-items:center;justify-content:center;min-height:120px}
.lb-raw img{max-width:100%;max-height:46vh;display:block}
.lb-meta{padding:12px 18px 18px;font-size:12.5px;color:var(--ink2);line-height:1.7}
.lb-meta code{background:#f4f4f6;padding:1px 5px;border-radius:5px;font-size:11.5px;word-break:break-all}
.lb-meta a{color:var(--accent)}
.empty{padding:44px 0;text-align:center;color:var(--ink3)}
.shot.noimg img{display:none}
.shot.noimg::after{content:"图片读不出来";font-size:11px;color:var(--drop)}
#more{display:block;margin:20px auto 8px;padding:9px 24px;border-radius:999px;color:var(--ink2)}
.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:104px;background:var(--ink);color:#fff;padding:9px 16px;border-radius:999px;font-size:12.5px;z-index:90;opacity:0;transition:.2s;pointer-events:none}
.toast.on{opacity:1}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
</style>
</head>
<body>
<h2 class="sr">产区图片人工审查台：把采集到的产区图逐张过一遍，决定哪些放进风土图鉴</h2>

<header class="top">
  <div class="top-in">
    <div class="top-row">
      <h1>产区图片审查台</h1>
      <span class="sub" id="subline"></span>
    </div>
    <div class="bar" id="bar"><i class="b-keep" style="width:0"></i><i class="b-todo" style="width:0"></i><i class="b-drop" style="width:0"></i></div>
    <div class="tools">
      <div class="chips" id="verdictChips"></div>
      <select id="regionSel"></select>
      <button class="sm" id="onlyUndecided">只看还没定的</button>
      <button class="sm" id="acceptAll">全部按建议定稿</button>
      <span class="spacer"></span>
      <button class="sm" id="reset">清空重来</button>
    </div>
  </div>
</header>

<div class="wrap">
  <div class="legend" id="legend"></div>
  <div class="grid" id="grid"></div>
  <button id="more" style="display:none"></button>
  <div class="empty" id="empty" style="display:none">这个筛选下没有图。</div>
</div>

<footer class="bot">
  <div class="bot-in">
    <span class="tally" id="tally"></span>
    <span class="spacer"></span>
    <button class="sm" id="nextTodo">跳到下一张待定 <kbd>Enter</kbd></button>
    <button class="primary" id="export">导出结果 JSON</button>
  </div>
</footer>

<div class="lightbox" id="lb"><div class="lb-in">
  <div class="lb-head"><b id="lbTitle"></b><button class="sm" id="lbClose">关闭</button></div>
  <div class="lb-grid">
    <div class="lb-cell"><div class="cap">放进网页方格（1:1 —— 这就是它上线后的样子）</div><div class="lb-box"><img id="lbBox" alt=""></div></div>
    <div class="lb-cell"><div class="cap">完整画面（原比例，不裁切）</div><div class="lb-raw"><img id="lbRaw" alt=""></div></div>
  </div>
  <div class="lb-meta" id="lbMeta"></div>
</div></div>

<div class="toast" id="toast"></div>

<script>
const META = __META__;
const DATA = __DATA__;
const STORE = 'terroir.regionReview.v2';

const V = {k:{label:'留',cls:'k'}, t:{label:'待定',cls:'t'}, d:{label:'丢',cls:'d'}};
const RANK = {k:0, t:1, d:2};
const PAGE = 240;              // 一次最多画这么多张，剩下的往下滚再补

function suggest(item){ return item.v === 't' ? null : (item.v === 'k' ? 'keep' : 'drop'); }

let state = load();
let filter = 'all';
let regionFilter = '';
let onlyUndecided = false;
let drawn = 0;

function load(){
  try{
    const raw = localStorage.getItem(STORE);
    if(raw){
      const s = JSON.parse(raw);
      if(s && s.d && s.d.length === DATA.length) return s;
    }
  }catch(e){}
  // 首次打开：建议直接预填，只把「待定」留成待办
  const d = DATA.map(item => suggest(item));
  return {d};
}
function save(){ try{ localStorage.setItem(STORE, JSON.stringify(state)); }catch(e){} }

function fmtSize(b){
  if(!b) return '';
  if(b > 1048576) return (b/1048576).toFixed(1)+' MB';
  return Math.round(b/1024)+' KB';
}
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function visible(){
  const out = [];
  for(let i=0;i<DATA.length;i++){
    const it = DATA[i], d = state.d[i];
    if(regionFilter && it.r !== regionFilter) continue;
    if(filter !== 'all' && it.v !== (filter==='keep'?'k':filter==='drop'?'d':'t')) continue;
    if(onlyUndecided && d) continue;
    out.push(i);
  }
  out.sort((a,b)=> {
    const A=DATA[a], B=DATA[b];
    if(A.r!==B.r) return A.r<B.r?-1:1;
    const da=state.d[a]?1:0, db=state.d[b]?1:0;
    if(da!==db) return da-db;                       // 还没定的排前面
    if(RANK[A.v]!==RANK[B.v]) return RANK[A.v]-RANK[B.v];
    // 「待定」里先看色数最少的 —— 那些最可能是 logo/排版，一眼就能清掉
    if(A.v==='t' && B.v==='t') return (A.c==null?99999:A.c) - (B.c==null?99999:B.c);
    return B.f-A.f;
  });
  return out;
}

function renderLegend(){
  document.getElementById('legend').innerHTML =
   '<h2>怎么一眼分出好看和丑</h2><ul>'+
   '<li><b>唯一真正要紧的指标：方格填充度。</b>网页上每个缩略图都是 1:1 方格、'+
   '按最长边缩放不裁切（酒标不能被切）。所以一张图放进方格后占多满，可以直接算：'+
   '填充度 = 较短边 ÷ 较长边。</li>'+
   '<li><span class="n">100%</span>正方形（1200×1200）——方格填满，最好看。</li>'+
   '<li><span class="n">75%</span>4:3 横构图（1200×900）——四边留白一点，标准照片。</li>'+
   '<li><span class="n">56%</span>16:9 宽屏（1920×1080）——上下各留一条白，还能看。</li>'+
   '<li><span class="n">28%</span>3.5:1 网页横幅（1366×390）——<b>格子里七成是白底，直接扔。</b></li>'+
   '<li><b>第二件事：色数 —— 它到底是不是一张照片。</b>把图缩到 128px 再数量一数有多少种颜色（每张卡片左上角都标着）。'+
   '实拍照片一般 <b>600～2500 种</b>；logo、纯色块、文字排版通常<b>不到 45 种</b>。'+
   '左边第二枚标签变红，就是机器闻到「不像照片」的味道了。</li>'+
   '<li><b>第三件事：它到底是不是照片。</b>文件名里出现 logo / banner / slider / icon / button / 社交图标 / '+
   'no-image 占位图 的，基本是网页装饰件，不是风土照片。</li>'+
   '<li><b>第四件事：像素够不够。</b>缩略图格只有 78px，所以 ≥420px 就已经很清楚了；'+
   '低于 300px 的才会糊。</li>'+
   '<li>黄色（待定）是自动判断拿不准的 —— <b>那 ' + META.todo + ' 张才真正需要你的眼睛</b>，'+
   '剩下的建议已按量算好、预填好了。</li>'+
   '<li>页面里的图是 <b>640px 缩略预览</b>（原图尺寸写在每张卡片右侧）；'+
   '点图放大，可以同时看「放进方格的样子」和「完整画面」。</li></ul>';
}

function renderChips(){
  const c = document.getElementById('verdictChips');
  const opts = [['all','全部 '+DATA.length],['keep','建议留 '+META.keep],['todo','待定 '+META.todo],['drop','建议丢 '+META.drop]];
  c.innerHTML = opts.map(([k,label])=>'<button class="chip'+(filter===k?' on':'')+'" data-f="'+k+'">'+label+'</button>').join('');
  c.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{ filter=b.dataset.f; renderChips(); render(); });
}

function renderRegionSel(){
  const regs = [...new Set(DATA.map(d=>d.r))].sort();
  const sel = document.getElementById('regionSel');
  sel.innerHTML = '<option value="">全部产区（'+regs.length+'）</option>'+
    regs.map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');
  sel.value = regionFilter;
  sel.onchange = ()=>{ regionFilter = sel.value; render(); };
}

function counts(){
  let k=0,t=0,d=0,und=0;
  for(let i=0;i<DATA.length;i++){
    const v = state.d[i];
    if(!v){ und++; continue; }
    if(v==='keep')k++; else if(v==='drop')d++;
  }
  return {k,t:und,d};
}

let IDX = [];

function renderStats(){
  const c = counts();
  const total = DATA.length;
  const done = total - c.t;
  document.getElementById('bar').innerHTML =
    '<i class="b-keep" style="width:'+(c.k/total*100)+'%"></i>'+
    '<i class="b-todo" style="width:'+(c.t/total*100)+'%"></i>'+
    '<i class="b-drop" style="width:'+(c.d/total*100)+'%"></i>';
  document.getElementById('subline').innerHTML =
    '原始 '+META.raw+' 条 → 去重后 <b>'+META.unique+'</b> 张唯一图，覆盖 <b>'+META.regions+'</b> 个产区'+
    (META.dupCopies?'（舍掉 '+META.dupCopies+' 条重复登记）':'');
  document.getElementById('tally').innerHTML =
    '已定稿 <b>'+done+'/'+total+'</b> ｜ 留 <b class="kk">'+c.k+'</b> ｜ 待你定 <b class="tt">'+c.t+'</b> ｜ 丢 <b class="dd">'+c.d+'</b>';
  document.getElementById('onlyUndecided').classList.toggle('primary', onlyUndecided);
}

function bindGrid(grid){
  grid.querySelectorAll('[data-act]').forEach(b=>{
    b.onclick = (e)=>{ e.stopPropagation(); setDecision(+b.dataset.i, b.dataset.act); };
  });
  grid.querySelectorAll('.shot').forEach(s=>{
    s.onclick = ()=> openLb(+s.dataset.i);
  });
}

function renderGrid(){
  IDX = visible();
  drawn = Math.min(IDX.length, PAGE);
  const grid = document.getElementById('grid');
  grid.innerHTML = IDX.slice(0, drawn).map(cardHTML).join('');
  bindGrid(grid);
  document.getElementById('empty').style.display = IDX.length ? 'none' : 'block';
  const more = document.getElementById('more');
  more.style.display = drawn < IDX.length ? 'block' : 'none';
  more.textContent = '再显示 ' + (IDX.length - drawn) + ' 张（共 ' + IDX.length + '）';
}

function render(){ renderStats(); renderGrid(); }

function loadMore(){
  const grid = document.getElementById('grid');
  const next = IDX.slice(drawn, drawn + PAGE);
  drawn += next.length;
  grid.insertAdjacentHTML('beforeend', next.map(cardHTML).join(''));
  bindGrid(grid);
  document.getElementById('more').style.display = drawn < IDX.length ? 'block' : 'none';
  document.getElementById('more').textContent = '再显示 ' + (IDX.length - drawn) + ' 张（共 ' + IDX.length + '）';
}

function cardHTML(i){
  const it = DATA[i], d = state.d[i];
  const cls = d ? (d==='keep'?'k':'d') : it.v;
  const fill = it.f ? it.f+'%' : '—';
  return '<div class="card '+cls+'" id="c'+i+'">'+
    '<div class="shot" data-i="'+i+'">'+
      (it.w&&it.h?'<img src="'+encodeURI(it.a)+'" alt="" loading="lazy" decoding="async" onerror="this.closest(\'.shot\').classList.add(\'noimg\')">':'<span class="empty">无图</span>')+
      '<span class="tags"><em>填充 '+fill+'</em>'+(it.c!=null?'<em class="'+(it.c<=45?'warn':'')+'">色数 '+it.c+'</em>':'')+'</span>'+
      '<span class="tag v">'+V[it.v].label+'</span>'+
    '</div>'+
    '<div class="body">'+
      '<div class="rid"><b>'+esc(it.r)+'</b><span>'+(it.w?it.w+'×'+it.h:'—')+'</span></div>'+
      '<div class="why">'+esc(it.y)+(it.b?'　'+fmtSize(it.b):'')+'</div>'+
      '<div class="acts">'+
        '<button data-i="'+i+'" data-act="keep" class="'+(d==='keep'?'on k':'')+'">留</button>'+
        '<button data-i="'+i+'" data-act="drop" class="'+(d==='drop'?'on d':'')+'">丢</button>'+
        '<button data-i="'+i+'" data-act="clear" class="'+(d?'':'on t')+'">待定</button>'+
      '</div>'+
    '</div></div>';
}

function paintCard(i){
  const card = document.getElementById('c'+i);
  if(!card) return;
  const d = state.d[i], item = DATA[i];
  card.className = 'card ' + (d ? (d==='keep'?'k':'d') : item.v);
  card.querySelectorAll('.acts button').forEach(b=>{
    const a = b.dataset.act;
    b.className = ((a==='keep'&&d==='keep')||(a==='drop'&&d==='drop')||(a==='clear'&&!d))
      ? 'on ' + (a==='keep'?'k':a==='drop'?'d':'t') : '';
  });
}

function setDecision(i, act){
  const cur = state.d[i];
  // 再点一次同一个按钮 = 取消，回到「待定」
  const next = (act === 'clear') ? null : (cur === act ? null : act);
  if(next === cur) return;
  state.d[i] = next;
  save();
  if(onlyUndecided && next !== null){
    const card = document.getElementById('c'+i);
    if(card) card.remove();
    IDX = IDX.filter(x => x !== i);
    document.getElementById('empty').style.display = IDX.length ? 'none' : 'block';
  }else{
    paintCard(i);
  }
  renderStats();
}

function scrollTo(i){
  const el = document.getElementById('c'+i);
  if(el) el.scrollIntoView({block:'center', behavior:'smooth'});
}

/* ---------- 放大对比 ---------- */
let lbIndex = -1;
function openLb(i){
  lbIndex = i;
  const it = DATA[i], src = encodeURI(it.a);
  document.getElementById('lbTitle').textContent = it.r + ' · ' + it.w + '×' + it.h;
  document.getElementById('lbBox').src = src;
  document.getElementById('lbRaw').src = src;
  document.getElementById('lbMeta').innerHTML =
    '方格填充 <b>'+it.f+'%</b>（白边 '+(100-it.f)+'%）　·　'+fmtSize(it.b)+
    (it.c!=null?'　·　色彩 <b>'+it.c+'</b> 种':'')+
    (it.o?'　·　原始文件名 <code>'+esc(it.o)+'</code>':'')+
    (it.p?'<br>来源页 <a href="'+esc(it.p)+'" target="_blank" rel="noopener">'+esc(it.p)+'</a>':'')+
    '<br>自动建议：'+V[it.v].label+' —— '+esc(it.y)+
    '<br>（页面里是 640px 缩略预览；原图 '+it.w+'×'+it.h+'，'+(it.c!=null?it.c+' 种颜色':'色彩未知')+'）';
  document.getElementById('lb').classList.add('open');
}
document.getElementById('lbClose').onclick = ()=>{ document.getElementById('lb').classList.remove('open'); };
document.getElementById('lb').onclick = (e)=>{ if(e.target.id==='lb') document.getElementById('lb').classList.remove('open'); };

/* ---------- 工具条 ---------- */
document.getElementById('onlyUndecided').onclick = ()=>{ onlyUndecided = !onlyUndecided; render(); };
document.getElementById('acceptAll').onclick = ()=>{
  let filled = 0, soft = 0;
  for(let i=0;i<DATA.length;i++){
    if(state.d[i] !== null) continue;
    filled++;
    if(DATA[i].v === 't'){ state.d[i] = 'keep'; soft++; }   // 自动拿不准的：宁可先留
    else state.d[i] = suggest(DATA[i]);
  }
  save(); render();
  toast(soft ? ('已定稿 '+filled+' 张；其中 '+soft+' 张自动拿不准、先按「留」算，建议用黄色筛一遍')
             : ('已定稿 '+filled+' 张'));
};
document.getElementById('more').onclick = loadMore;
document.getElementById('reset').onclick = ()=>{
  if(!confirm('清空所有决定，回到「建议预填 + 待定留空」的初始状态？')) return;
  state = {d: DATA.map(suggest)};
  save(); filter='all'; regionFilter=''; onlyUndecided=false;
  renderChips(); renderRegionSel(); render(); toast('已回到初始状态');
};
document.getElementById('nextTodo').onclick = ()=>{
  const idx = visible();
  const target = idx.find(i=>state.d[i]===null);
  if(target===undefined){ toast('当前筛选下没有待定项了'); return; }
  scrollTo(target);
};
document.getElementById('export').onclick = ()=>{
  const keep=[], drop=[], undecided=[], keepPaths=[], dropPaths=[], undecidedPaths=[];
  for(let i=0;i<DATA.length;i++){
    const d = state.d[i], it = DATA[i];
    if(d==='keep'){ keep.push(it.k); keepPaths.push(it.s); }
    else if(d==='drop'){ drop.push(it.k); dropPaths.push(it.s); }
    else { undecided.push(it.k); undecidedPaths.push(it.s); }
  }
  const out = {
    version: 1,
    generatedAt: new Date().toISOString(),
    source: 'work/region-media-review.html',
    keyFormat: '<regionId>/<fileName>',
    counts: {total: DATA.length, keep: keep.length, drop: drop.length, undecided: undecided.length},
    keep, drop, undecided,
    keepPaths, dropPaths, undecidedPaths,
  };
  const blob = new Blob([JSON.stringify(out, null, 1)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'region-media-review.result.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
  toast('已导出 ' + keep.length + ' 张「留」、' + drop.length + ' 张「丢」');
};

/* ---------- 键盘 ---------- */
let cursor = -1;
document.addEventListener('keydown', (e)=>{
  if(e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
  const idx = IDX;
  if(e.key==='ArrowRight'||e.key==='j'){ cursor = Math.min(cursor+1, idx.length-1); if(idx[cursor]!=null) scrollTo(idx[cursor]); }
  else if(e.key==='ArrowLeft'||e.key==='k'){ cursor = Math.max(cursor-1, 0); if(idx[cursor]!=null) scrollTo(idx[cursor]); }
  else if(e.key==='Enter'){ e.preventDefault(); const t = idx.find(i=>state.d[i]===null); if(t!=null) scrollTo(t); }
  else if(['1','2','3'].includes(e.key)){
    const cur = (cursor>=0 && idx[cursor]!=null && document.getElementById('c'+idx[cursor]))
      ? idx[cursor] : idx.find(i=>state.d[i]===null && document.getElementById('c'+i));
    if(cur==null) return;
    setDecision(cur, e.key==='1'?'keep':e.key==='2'?'drop':'clear');
    cursor = idx.indexOf(cur);
  }
});

// 快滚到底自动续上，不用点按钮
window.addEventListener('scroll', ()=>{
  if(drawn >= IDX.length) return;
  if(window.innerHeight + window.scrollY > document.body.offsetHeight - 900) loadMore();
}, {passive:true});

let toastTimer = null;
function toast(msg){
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(()=>t.classList.remove('on'), 2000);
}

renderLegend(); renderChips(); renderRegionSel(); render();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    main()
