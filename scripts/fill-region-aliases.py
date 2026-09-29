# coding: utf-8
"""给产区补齐 `data.aliases`（搜索别名）—— 共建看板「别名」列 109 个产区里只有 1 个有值。

Why
---
别名**不是新事实**，而是同一产区的其他已知称呼。站点 `public/language-core.js` 的
`searchText()` 会把 `d.aliases` 拼进检索文本，所以它的作用是**让人用自己习惯的名字
也能搜到这个产区**。既然库里已经有该产区的官方名/本地语名，别名就可以从这些
**已核实字段**派生出来，不需要新采集、也不需要凭记忆写译名。

派生规则（只用记录内已核实字段，绝不猜译）
------------------------------------------
别名 = **除主名以外的其他已知称呼**（`data.name` 本身就是主名、`searchText()` 已经收录，
塞进 aliases 只是重复），来源只有三处：

1. `data.en`（官方/英文名）—— 按 ` / ` 切分得到并列官方名
   （`Alto Adige / Südtirol`、`Valais / Wallis`、`Istra / Istria`、`Trakya / Thrace`、
   `Galilee / Galil`、`Médoc / Haut-Médoc`、`Valpolicella / Valpolicella Ripasso`…）
2. `data.en` 括号里的短名字（`Huailai (Shacheng)` → `Shacheng`）
3. `data.localizations[*].name`，但**只取站点认定为 confirmed 的条目**
   （`status==='verified'` 且 sourceURL / sourceTitle / checkedDate 齐全 —— 与
   `public/language-core.js` 的 `confirmed()` 完全同口径）。没核实过的名字不进别名。

每条候选都会被剥掉题注缩写：DOC / DOCG / DO / DOP / AOC / AOP / PDO / PGI / AVA /
VQA / IGT / IGP / GI / DAC / Anbaugebiet / Weinbaugebiet。
含题注的整串长名（`Bolgheri DOC / Bolgheri Sassicaia DOC`）**不作为别名**，
只留剥干净的原子名（`Bolgheri`、`Bolgheri Sassicaia`）—— 别名是给人搜索用的，
塞一长串反而在页面上难看。

不写的东西（这三条是刻意的，不要"优化"掉）
------------------------------------------
* **不造音译变体**：`勃艮第` 的常见变体 `布根地/勃根地` 库里没有依据，写了就是编。
* **不用 id slug**：`margaret` 是被截断的 slug（真名是 Margaret River），不是名字。
* **不把国家名当别名**：`Bekaa Valley (Lebanon)` 的括号里是国家，不是产区别称。

用法
----
    python3 scripts/fill-region-aliases.py --dry-run     # 只打印，不写盘
    python3 scripts/fill-region-aliases.py               # 落盘（先自动备份）
    python3 scripts/fill-region-aliases.py --force       # 连已有 aliases 也重算（默认跳过）
"""

import argparse
import json
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'data' / 'catalog-seed.json'
WORK = ROOT / 'work'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

# 法定/体系题注缩写：出现在名称末尾时剥掉（`Bierzo (DO)` → `Bierzo`、`Paso Robles AVA` → `Paso Robles`）
DENOM = ('DOCG', 'DOCa', 'DOC', 'DOP', 'DO', 'AOC', 'AOP', 'PDO', 'PGI', 'AVA', 'VQA',
         'IGT', 'IGP', 'DAC', 'GI')
DENOM_WORDS = ('Anbaugebiet', 'Weinbaugebiet', 'Weinbaugebiete')

# 括号里若是国家名就不是产区别称（`Bekaa Valley (Lebanon)`）
COUNTRY_WORDS = {
    'lebanon', 'moldova', 'china', 'france', 'italy', 'spain', 'portugal', 'germany',
    'austria', 'united states', 'usa', 'australia', 'new zealand', 'south africa',
    'chile', 'argentina', 'brazil', 'uruguay', 'romania', 'hungary', 'greece',
    'georgia', 'russia', 'japan', 'canada', 'switzerland', 'united kingdom',
    'turkey', 'croatia', 'slovenia', 'israel', 'mexico',
}

MAX_ALIASES = 30   # worker/model.js 的 aliases 上限就是 30


def confirmed(entry):
    """与 public/language-core.js 的 confirmed() 同口径，一处都不能松。"""
    return bool(entry and entry.get('status') == 'verified'
                and entry.get('sourceURL') and entry.get('sourceTitle')
                and entry.get('checkedDate'))


def strip_denom(text):
    s = ' '.join(str(text or '').split()).strip(' .,;·-/')
    moved = True
    while moved:
        moved = False
        for w in DENOM_WORDS:
            if s.endswith(' ' + w):
                s = s[:-(len(w) + 1)].strip(' .,;·-/')
                moved = True
        for w in DENOM:
            if s.endswith(' ' + w):
                s = s[:-(len(w) + 1)].strip(' .,;·-/')
                moved = True
    return s


def split_name(text):
    """`Bierzo (DO)` → ['Bierzo']；`Bekaa Valley (Lebanon)` → ['Bekaa Valley']。

    括号内容只有**看起来仍然是个名字**时才留（`Huailai (Shacheng)` → 多出 `Shacheng`）：
    不超过两个词、含小写字母、不含 `&`、不是国家名、不是题注缩写。

    ⚠️ 两个实测踩过的坑，条件都是必需的：
    * `Burgenland (Weinbaugebiet)` —— `Weinbaugebiet` 全是小写字母，
      只查「有没有小写」会漏，必须显式比对 DENOM_WORDS。
    * `Νεμέα (ΠΟΠ)` —— `ΠΟΠ`（希腊语 PDO 缩写）全大写、无小写字母，
      「必须含小写字母」这一条正好把它挡掉。
    """
    text = ' '.join(str(text or '').split())
    if '(' not in text:
        return [text]
    head, _, tail = text.partition('(')
    tail = tail.rstrip(')').strip()
    out = [head.strip()]
    words = tail.split()
    denom = set(DENOM) | {w.upper() for w in DENOM_WORDS}
    looks_like_name = (
        bool(tail)
        and '&' not in tail
        and len(tail) <= 18
        and 0 < len(words) <= 2
        and any(ch.islower() for ch in tail)              # 挡掉 ΠΟΠ / DOC 这类纯缩写
        and not any(w.upper() in denom for w in words)    # 挡掉 Weinbaugebiet
        and tail.lower() not in COUNTRY_WORDS
    )
    if looks_like_name:
        out.append(tail)
    return out


def derive(data):
    """返回该产区的**其他已知称呼**（不含 `data.name` 本身）。"""
    raw = []

    def add(v):
        v = ' '.join(str(v or '').split()).strip(' .,;·-/')
        if len(v) >= 2:
            raw.append(v)

    for variant in split_name(data.get('en')):
        for part in variant.split('/'):
            add(strip_denom(part))

    for _lang, entry in (data.get('localizations') or {}).items():
        if not confirmed(entry):
            continue
        for variant in split_name(entry.get('name')):
            for part in variant.split('/'):
                add(strip_denom(part))

    primary = unicodedata.normalize('NFKC', str(data.get('name') or '')).casefold()
    seen, out = set(), []
    for v in raw:
        key = unicodedata.normalize('NFKC', v).casefold().replace('·', '').replace(' ', '')
        if not key or key in seen or key == primary.replace(' ', ''):
            continue
        seen.add(key)
        out.append(v)
    return out[:MAX_ALIASES]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='已有 aliases 的产区也重算')
    args = ap.parse_args()

    seed = json.loads(SEED.read_text(encoding='utf-8'))
    recs = seed if isinstance(seed, list) else seed.get('records', [])
    regions = [r for r in recs if r.get('kind') == 'region']

    filled, skipped, singles, preview = 0, 0, 0, []
    for r in regions:
        d = r.setdefault('data', {})
        if d.get('aliases') and not args.force:
            skipped += 1
            continue
        aliases = derive(d)
        if not aliases:
            # 主名之外查不到任何已核实称呼 —— 不硬凑，留着让看板继续提示
            skipped += 1
            continue
        if len(aliases) == 1:
            singles += 1
        preview.append((r['id'], d.get('name'), d.get('country'), aliases))
        d['aliases'] = aliases
        r['version'] = int(r.get('version') or 1) + 1
        r['updated'] = NOW
        filled += 1

    print('== 派生别名：%d 个产区（其中 %d 个只派生出 1 条；跳过 %d） =='
          % (filled, singles, skipped))
    print()
    width = max((len(p[0]) for p in preview), default=10)
    for rid, name, country, aliases in sorted(preview, key=lambda x: (x[2] or '', x[0])):
        print(f"{rid:<{width}}  {str(name):<20} | {' | '.join(aliases)}")

    report = {
        'generatedAt': NOW, 'mode': 'force' if args.force else 'fill-empty',
        'filled': filled, 'skipped': skipped, 'singles': singles,
        'regions': [{'id': i, 'name': n, 'country': c, 'aliases': a} for i, n, c, a in preview],
    }
    if not WORK.is_dir():
        WORK.mkdir(parents=True)
    (WORK / 'region-aliases-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    if args.dry_run:
        print('\n--dry-run：未写盘。报告 → work/region-aliases-report.json')
        return

    backup = WORK / f'catalog-seed.before-region-aliases-{datetime.now().strftime("%Y%m%d%H%M%S")}.json'
    shutil.copy2(SEED, backup)
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n备份 → {backup}')
    print('落盘完成：%d 个产区写入 aliases' % filled)


if __name__ == '__main__':
    main()
