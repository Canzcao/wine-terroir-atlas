# coding: utf-8
"""为缺坐标的酒庄补全坐标（第三遍：登记地址解析通道）。

前两遍的局限（已实测）：
  · OSM 名称通道：小酒庄在 OSM 里根本没有记录 → 命中率 16%；
  · 官网地图嵌入通道：现代站点地图是 JS 动态渲染 → 命中率 0–20%。

但缺坐标的 757 条里有 **603 条带登记地址**。这些地址本来就是酒庄自己公布的
联系地址，把它解析成坐标是「弱一档但站得住」的证据。因此本脚本产出两个档位：

  档 A（precise，approximate 不设）：地址解析命中**门牌/建筑级**要素，
        即 Nominatim 从「含门牌号的完整地址」解析出 house/building。
        → 这就是该酒庄登记的门牌地址，与 Wines of Argentina 官方登记地址同级。
  档 B（approximate=true）：只解析到街道/城镇/行政区中心。
        → 位置是「对的城市、错的点」，必须显式标注，供前端与「只看已定位」筛选区分。

两条硬护栏（缺一不可）：
  1. **地名一致性**：解析结果的 display_name / address 里必须出现我们抽出的地名，
     否则丢弃（防止 "España 1094" 被匹配到另一个省的同名街道）。
  2. **地理合理性**（复用 fill-missing-winery-geo.py 的 geo_ok）：产区边界内 /
     产区聚类半径内 / 同国家已知坐标 300km 内，否则丢弃。

用法:
    python3 scripts/fill-missing-winery-geo-addr.py <missing.json> <out.json> [--limit N]
"""
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path
import importlib.util as ilu

ROOT = Path(__file__).resolve().parents[1]
_spec = ilu.spec_from_file_location('fmg', str(ROOT / 'scripts' / 'fill-missing-winery-geo.py'))
_fmg = ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fmg)

fetch = _fmg.fetch
clean_addr = _fmg.clean_addr
geo_ok = _fmg.geo_ok
haversine = _fmg.haversine
load_boundaries = _fmg.load_boundaries
load_anchors = _fmg.load_anchors
region_name = _fmg.region_name
COUNTRY_EN = _fmg.COUNTRY_EN
COUNTRY_ISO = _fmg.COUNTRY_ISO

# 门牌/建筑级：算「确切的登记地址」
HOUSE_TYPES = {'house', 'building', 'apartments', 'residential', 'detached', 'terrace',
               'yes', 'industrial', 'commercial', 'farm', 'warehouse', 'hut'}
# 软档（街道/城镇级）只接受这几类要素。
# ⚠️ 必须收窄，不能「任何类型都算软档」——实测踩过两个坑：
#   · 'Chavanay, France' 排第一的是 amenity/post_office（沙瓦内的邮局），
#     它是个点要素、看着很精确，其实和「酒庄在哪」毫无关系（这类混进来 15 条）；
#   · 'Saint-Péray' 会被解析到 highway/proposed（"Projet de déviation" 规划中的绕城路）
#     —— 一条不存在的路（3 条）。
# 所以只认 boundary/place/landuse，以及 highway 里的实际道路类型。
SOFT_OK_CLASSES = {'boundary', 'place', 'landuse', 'highway'}
SOFT_REJECT_TYPES = {
    'proposed', 'construction', 'planned', 'abandoned', 'disused', 'razed', 'demolished',
    'bus_stop', 'platform', 'tram_stop', 'stop_position', 'traffic_signals', 'crossing',
    'milestone', 'turning_circle', 'speed_camera', 'fire_hydrant', 'post_box',
}
# 无地名（纯街道地址）时额外要求要素是「路或房子」，不能是面状地物
NO_LOCALITY_CLASSES = {'highway', 'place', 'boundary', 'building', 'landuse'}
# 聚类半径上限（km）。不封顶会出现「门多萨 710km」这种形同虚设的护栏：
# 实测 'CALLE NUEVA S/N' 因此被放到 326km 外圣胡安省的 Jáchal。
# 封顶 250km 仍能保住正确命中（圣拉斐尔 181km、图努扬 68km）。
ANCHOR_RADIUS_CAP = 250.0


def soft_ok(row):
    cls = (row.get('class') or '').lower()
    typ = (row.get('type') or '').lower()
    if typ in SOFT_REJECT_TYPES:
        return False
    return cls in SOFT_OK_CLASSES

POSTCODE_RE = re.compile(r'\b(\d{5})\b')
# AU/NZ 用 4 位邮编，但只在**段首是纯词、数字在段末**时才认（否则 FR 的 'RD 1086' 会被当成邮编）
POSTCODE4_RE = re.compile(r'^([^\d]{3,}?)\s+(\d{4})$')
FOUR_DIGIT_COUNTRIES = {'澳大利亚', '新西兰'}
# '0 7300' / '0 7340' —— 有些地址把邮编首位和后四位隔开了（实测北罗讷 3 条）
SPLIT_POSTCODE_RE = re.compile(r'\b(\d)\s+(\d{4})\b')
# 段内出现的邮箱/网址要摘掉，但保留同段的其余内容
NOISE_TOKEN_RE = re.compile(r'\S*@\S*|\bhttps?://\S+|\bwww\.\S+', re.I)
# 拆地址段：只按「逗号 / 斜杠 / 空格-连字符-空格」切，保住 Saint-Michel-sur-Rhône 这类含连字符地名
SPLIT_RE = re.compile(r'\s*[,/;]\s*|\s+[-\u2013\u2014]\s+|\s*\|\s*')
# 段首出现这些词即判定该段是「电话/传真/邮箱」而非地址
JUNK_LABEL_RE = re.compile(
    r'^(fax|t[ée]l(?:[ée]phone)?|tel|phone|mobile|portable|e-?mail|courriel|contact|web|site)\b',
    re.I)
PAREN_RE = re.compile(r'\s*\([^)]*\)\s*')
POSTAL_RE = re.compile(r'^\d{4,5}$')


def clean_addr2(addr):
    """按段清地址：丢掉传真/电话/邮箱段，其余用逗号拼接。

    ⚠️ 不要复用 collect-producer-geo.py 里的 clean_addr()：它用 `[/|].*?(fax...).*$`
    做删除，`.*?` 会从**第一个**斜杠一路吃到 Fax 处，把中间的街道和邮编整段吞掉
    （实测 '125, Rue du Piaton / 42410 Saint-Michel-sur-Rhône / Fax : ...' 只剩 '125, '）。
    那条路径只把地址当辅助查询词，损失有限；本脚本靠地址吃饭，必须逐段处理。
    """
    out = []
    for raw in re.split(r'[/|\n\r]+', addr or ''):
        seg = NOISE_TOKEN_RE.sub(' ', raw)
        seg = SPLIT_POSTCODE_RE.sub(r'\1\2', seg)
        seg = re.sub(r'\s{2,}', ' ', seg).strip(' ,;-\t')
        if not seg or JUNK_LABEL_RE.match(seg):
            continue
        # 段内还有 Fax 之类的中缀 → 截断到该中缀之前
        seg = re.sub(r'\s*\b(fax|t[ée]l(?:[ée]phone)?|tel|phone|mobile|e-?mail)\b\s*[:：].*$',
                     '', seg, flags=re.I).strip(' ,;-\t')
        if seg:
            out.append(seg)
    return ', '.join(out)


def strip_accents(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def tokens(s):
    return set(re.findall(r'[a-z0-9]{2,}', strip_accents(s)))


# 地址里的「非辨识性」词：出现它们不能算「街道名对上了」
ADDR_STOP = {
    'calle', 'ruta', 'ruta', 'avenida', 'avda', 'av', 'carril', 'pasaje', 'esquina', 'esq',
    'nacional', 'provincial', 'prov', 'km', 'kilometro', 's/n', 'sn', 's', 'n', 'y', 'e',
    'rue', 'chemin', 'route', 'impasse', 'lieu', 'dit', 'quartier', 'zone', 'hameau',
    'via', 'viale', 'strada', 'piazza', 'corso', 'street', 'road', 'avenue', 'drive',
    'francia', 'france', 'italia', 'italy', 'argentina', 'chile', 'espana', 'spain',
}
# 公路编号：'Ruta Nacional 144 Km 674' / 'RP 96' / 'RD 1086' / 'RN 86'
ROUTE_RE = re.compile(
    r'\b(?:ruta|rn|rp|rd|nacional|provincial|route)\b[\s.]*(?:nacional|provincial)?[\s.]*'
    r'(?:n[°º]?)?[\s.]*(\d{1,4})\b', re.I)


def addr_keywords(addr):
    """从地址里抽「应该出现在解析结果里」的辨识性词（街道名 + 公路编号）。"""
    toks = {t for t in tokens(addr) if len(t) >= 4 and t not in ADDR_STOP}
    routes = {m.group(1) for m in ROUTE_RE.finditer(addr)}
    return toks, routes


def locality_consistent(row, locality):
    """解析结果必须落在我们抽出的地名上，否则判定为误匹配。"""
    if not locality:
        return True
    want = tokens(locality)
    if not want:
        return True
    addr = row.get('address') or {}
    blob = ' '.join(str(row.get(k) or '') for k in ('display_name', 'name'))
    for key in ('city', 'town', 'village', 'hamlet', 'municipality', 'suburb',
                'neighbourhood', 'county', 'state', 'road', 'postcode'):
        blob += ' ' + str(addr.get(key) or '')
    return bool(want & tokens(blob))


def address_consistent(row, full_addr):
    """没有邮编地名时（全是阿根廷那种纯街道地址）的唯一护栏。

    实测反例：'CALLE NUEVA S/N' 查出来命中 'Calle 34, La Favorita' —— 街名根本不同。
    规则：地址里的街道辨识词或公路编号，至少有一样出现在解析结果里。
    """
    toks, routes = addr_keywords(full_addr)
    if not toks and not routes:
        return False
    addr = row.get('address') or {}
    blob = ' '.join(str(row.get(k) or '') for k in ('display_name', 'name'))
    blob += ' ' + ' '.join(str(addr.get(k) or '') for k in
                           ('road', 'pedestrian', 'footway', 'path', 'residential', 'highway'))
    got = tokens(blob)
    if toks & got:
        return True
    if routes:
        for r in routes:
            if re.search(r'(?<!\d)%s(?!\d)' % re.escape(r), blob):
                return True
    return False


def is_commune_feature(row, locality):
    """解析结果是不是「该公社本身」——放宽产区边界时只认这一种。"""
    if not locality:
        return False
    typ = (row.get('type') or '').lower()
    if typ not in ('administrative', 'city', 'town', 'village', 'hamlet', 'municipality'):
        return False
    a = row.get('address') or {}
    for key in ('municipality', 'city', 'town', 'village', 'hamlet', 'county'):
        if tokens(str(a.get(key) or '')) & tokens(locality):
            return True
    return tokens(str(row.get('name') or '')) == tokens(locality)


def load_bboxes(boundaries):
    """每个 region 边界的外接框，用于「点离产区多远」的粗判（不逐顶点算，够用且快）。"""
    out = {}
    for rid, rings in boundaries.items():
        pts = [p for ring in rings for p in ring]
        if not pts:
            continue
        out[rid] = (min(p[1] for p in pts), min(p[0] for p in pts),
                    max(p[1] for p in pts), max(p[0] for p in pts))
    return out


def dist_to_bbox_km(bbox, lat, lng):
    """点到外接框的最近距离（框内为 0）。经度按该纬度收缩。"""
    s, w, n, e = bbox
    dlat = max(s - lat, 0.0, lat - n)
    k = math.cos(math.radians(lat))
    dlng = max(w - lng, 0.0, lng - e) * k
    return 111.0 * math.hypot(dlat, dlng)


def far_from_region_km(rid, lat, lng, boundaries, anchors, bboxes):
    if rid in bboxes:
        return dist_to_bbox_km(bboxes[rid], lat, lng)
    if rid in anchors:
        a = anchors[rid]
        return max(0.0, haversine(a['center'], (lat, lng)) - a['radius'])
    return None


def region_admin_consistent(row, rid):
    """纯街道地址的兜底护栏：解析结果的行政区里必须出现目录所记的地区名。

    为什么必须要有这一条：阿根廷地址基本没有城市（'Calle Nueva S/N'），而没有城市时
    街道名在省内根本不唯一 —— 实测 'Calle Nueva' 在 185km 外的圣胡安省 Jáchal 也有同名街，
    Nominatim 照样返回，距离护栏（250km）拦不住。
    加上「结果必须落在 Mendoza」之后：圣拉斐尔(181km)、图努扬(68km)、路冉德库约(6km)
    这些正确命中全部保留，跨省的整类误配被清掉。
    """
    a = row.get('address') or {}
    blob = ' '.join(str(a.get(k) or '') for k in
                    ('state', 'province', 'region', 'county', 'state_district',
                     'municipality', 'display_name'))
    blob += ' ' + str(row.get('display_name') or '')
    return bool(tokens(region_name(rid)) & tokens(blob))


def pick(rows, locality, full_addr, rid, country, boundaries, anchors, country_pts, bboxes):
    """在候选里挑第一个「地名/街道一致 + 地理合理」的。优先门牌级，其次软级。"""
    soft, soft_why, notes = None, None, []
    for r in rows:
        if not isinstance(r, dict) or r.get('lat') is None:
            continue
        if not locality_consistent(r, locality):
            notes.append('locality_mismatch')
            continue
        if not locality:
            if not address_consistent(r, full_addr):
                notes.append('street_mismatch')
                continue
            if not region_admin_consistent(r, rid):
                notes.append('outside_region_admin')
                continue
        try:
            lat, lng = float(r['lat']), float(r['lon'])
        except (TypeError, ValueError):
            continue
        why = None
        ok, reason = geo_ok(rid, country, lat, lng, boundaries, anchors, country_pts)
        if ok:
            why = reason
        else:
            # 有界放宽：公社级、地名已核实、且离产区边界 <60km —— 产区内的酒庄把公司
            # 注册在隔壁公社是常态（实测 Ampuis 的 Gerin 被标成 Condrieu 产区）。
            # 这比把它丢回产区质心更接近事实，但离得远的照旧拒绝。
            d = far_from_region_km(rid, lat, lng, boundaries, anchors, bboxes)
            if locality and d is not None and d <= 60 and is_commune_feature(r, locality):
                why = 'outside_region_but_%.0fkm_from_it（登记地址在该公社：%s）' % (d, locality)
            else:
                notes.append('geo_reject(%s)' % reason)
                continue
        typ = (r.get('type') or '').lower()
        cls = (r.get('class') or '').lower()
        if not locality and cls not in NO_LOCALITY_CLASSES:
            notes.append('no_locality_weak_feature(%s/%s)' % (cls, typ))
            continue
        if not soft_ok(r):
            notes.append('soft_type_rejected(%s/%s)' % (cls, typ))
            continue
        a = r.get('address') or {}
        has_num = bool(str(a.get('house_number') or '').strip())
        if has_num and typ in HOUSE_TYPES:
            return r, why, 'precise', notes
        if soft is None:
            soft, soft_why = r, why
    if soft is not None:
        return soft, soft_why, 'approx', notes
    return None, None, None, notes


def extract_locality(addr, country=''):
    """从登记地址里抽地名，**只认邮编锚定的地名**。返回 (locality, postcode)。

    为什么必须邮编锚定：不带邮编时「最后一段」在阿根廷地址里几乎都是街道名
    （'Clodomiro Silva S/N'、'La Gloria S/N'），会把街道当城市去查，全盘误定位。
    宁可返 None 走「整条地址」变体，也不要造一个假城市。

    覆盖的格式（都是实测样例）：
      FR  '125, Rue du Piaton / 42410 Saint-Michel-sur-Rhône'  → Saint-Michel-sur-Rhône / 42410
      FR  '18, chemin de la Roue - 07300 ST JEAN DE MUZOLS'    → ST JEAN DE MUZOLS / 07300
      FR  '8 rue Cuvillière / 42410 / Condrieu'                → Condrieu / 42410   （邮编独立成段）
      FR  '103 RD 1086 - Luzin / 42410 / Chavanay'             → Chavanay / 42410
      FR  '802 CHEMIN DES PEYROUSES 07130 Saint-Péray'         → Saint-Péray / 07130（同段内）
      AU  '78 Penfold Road, Magill, South Australia 5072'      → South Australia / 5072（4 位邮编）
      IT  'Via XX Settembre 52, 12052 Neive (CN), Italia'      → Neive / 12052      （剥掉括号）
      AR  'Roque Saenz Peña Vistalba 3531'                     → None（无 5 位邮编，放弃）
    """
    text = clean_addr2(addr)
    if not text:
        return None, None
    parts = [PAREN_RE.sub(' ', p).strip(' ,-.') for p in SPLIT_RE.split(text)]
    parts = [p for p in parts if p]
    for i, part in enumerate(parts):
        m = POSTCODE_RE.search(part)
        if not m and country in FOUR_DIGIT_COUNTRIES:
            m4 = POSTCODE4_RE.match(part)
            if m4:
                return m4.group(1).strip(' ,-.'), m4.group(2)
        if not m:
            continue
        tail = part[m.end():].strip(' ,-.')
        if len(tail) >= 3 and not tail.isdigit():
            return tail, m.group(1)
        # 邮编独立成段或落在段末（'... / 42410 / Chavanay'、AU '... South Australia 5072'）
        # 顺序：先看下一段（法语区惯例是「邮编 → 市镇」），再看上一段（AU 惯例是「郊区 → 州+邮编」）
        nxt = parts[i + 1] if i + 1 < len(parts) else ''
        if len(nxt) >= 3 and not POSTAL_RE.match(nxt):
            return nxt, m.group(1)
        prev = parts[i - 1] if i > 0 else ''
        if len(prev) >= 3 and not re.search(r'\d', prev):
            return ' '.join(prev.split()[-4:]), m.group(1)
        head = part[:m.start()].strip(' ,-.')
        if len(head) >= 3 and not head.isdigit():
            return ' '.join(head.split()[-4:]), m.group(1)
    return None, None


def city_variant(q, iso):
    # limit 给到 8：收紧软档类型之后，公社边界常被邮局／商铺挤到 2–3 位，
    # 只要它在前 8 条里就能被挑到。多要几条不额外收费，也不影响限速。
    params = {'q': q, 'format': 'json', 'limit': 8, 'addressdetails': 1, 'extratags': 1}
    if iso:
        params['countrycodes'] = iso
    return fetch(params)


def main():
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    # 三条通道并发时 Nominatim 会限流，被限流的那条只会记 ERR 不会重试。
    # 用这个开关只重跑「因为 ERR 而失败」的条目，跑完再合一次。
    redo_errors = '--redo-errors' in sys.argv
    # 判定规则收紧过之后用这个：剔掉旧规则放进来的脏命中（邮局、规划中的路之类），
    # 让它们回到待办重算。跑完仍要按正常流程再跑一遍收集新结果。
    recheck = '--recheck' in sys.argv
    items = json.loads(src.read_text())
    if limit:
        items = items[:limit]
    boundaries = load_boundaries()
    bboxes = load_bboxes(boundaries)
    anchors, _region_pts, country_pts = load_anchors()
    anchors = {k: {**v, 'radius': min(ANCHOR_RADIUS_CAP, v['radius'])} for k, v in anchors.items()}
    print('边界覆盖 %d 个 region；聚类参照 %d 个 region（半径封顶 %.0fkm）、%d 个国家' % (
        len(boundaries), len(anchors), ANCHOR_RADIUS_CAP, len(country_pts)), flush=True)

    results, done = [], set()
    if dst.exists():
        try:
            prev = json.loads(dst.read_text())
            ids = {i['id'] for i in items}
            results = [r for r in prev if r.get('id') in ids]
            if recheck:
                # 收紧过判定规则之后，把「旧规则放进来的脏命中」剔掉，
                # 让它们回到待办里重算（Nominatim 结果有磁盘缓存，重算很快）。
                keep, dropped = [], 0
                for r in results:
                    if r.get('status') != 'matched':
                        keep.append(r)
                        continue
                    row = {'class': r.get('osmClass'), 'type': r.get('osmTypeDetail')}
                    valid = soft_ok(row) if r.get('tier') == 'approx' else bool(r.get('houseNumber'))
                    if valid:
                        keep.append(r)
                    else:
                        dropped += 1
                results = keep
                print('重核：剔除 %d 条按新规则不成立的命中，重新解析' % dropped, flush=True)
            if redo_errors:
                keep = [r for r in results if not any('ERR' in str(n) for n in (r.get('notes') or []))]
                done = {r['id'] for r in keep}
                results = keep
                print('续跑（仅重跑 ERR）：保留 %d 条，重跑 %d 条' % (
                    len(keep), len(prev) - len(keep)), flush=True)
            else:
                done = {r['id'] for r in results}
                print('续跑：已完成 %d 条' % len(done), flush=True)
        except Exception:
            results, done = [], set()

    precise = approx = 0
    for idx, it in enumerate(items, 1):
        if it['id'] in done:
            continue
        raw_addr = it.get('address') or ''
        hit = {'id': it['id'], 'name': it['name'], 'status': 'not_found',
               'lat': None, 'lng': None, 'notes': []}
        if len(clean_addr2(raw_addr)) >= 6:
            full = clean_addr2(raw_addr)
            locality, postcode = extract_locality(raw_addr, it.get('country') or '')
            country = it.get('country') or ''
            rid = it.get('regionId') or ''
            ccn = COUNTRY_EN.get(country, '')
            iso = COUNTRY_ISO.get(country, '')
            rn = region_name(rid)
            variants = []
            if locality:
                variants.append(('locality+region+country',
                                 ', '.join(x for x in [locality, rn, ccn] if x)))
                variants.append(('locality+country', ', '.join(x for x in [locality, ccn] if x)))
            variants.append(('addr+region+country', ', '.join(x for x in [full, rn, ccn] if x)))
            variants.append(('addr+country', ', '.join(x for x in [full, ccn] if x)))
            # 地名优先（便宜且命中率高，且有磁盘缓存），最后才用整条地址
            variants = ([v for v in variants if v[0].startswith('locality')] +
                        [v for v in variants if not v[0].startswith('locality')])

            for tag, q in variants:
                rows = city_variant(q, iso)
                if isinstance(rows, dict) and rows.get('error'):
                    hit['notes'].append('%s:ERR' % tag)
                    continue
                if not isinstance(rows, list) or not rows:
                    continue
                row, why, tier, why_notes = pick(rows, locality, full, rid, country,
                                                 boundaries, anchors, country_pts, bboxes)
                if not row:
                    hit['notes'] += ['%s:%s' % (tag, n) for n in why_notes[:3]]
                    continue
                addr = row.get('address') or {}
                shown = row.get('display_name') or ''
                hit.update({
                    'status': 'matched', 'tier': tier, 'matchedBy': tag, 'query': q,
                    'lat': float(row['lat']), 'lng': float(row['lon']),
                    'geoCheck': why,
                    'osmClass': row.get('class'), 'osmTypeDetail': row.get('type'),
                    'displayName': shown,
                    'locality': locality, 'postcode': postcode,
                    'houseNumber': addr.get('house_number') or '',
                    'locationSourceURL': 'https://www.openstreetmap.org/%s/%s' % (
                        row.get('osm_type'), row.get('osm_id')),
                })
                if tier == 'precise':
                    hit['locationPrecision'] = (
                        '按登记地址「%s」解析定位（Nominatim/OSM %s/%s%s），'
                        '命中「%s」；该地址为酒庄公开联系地址，非地块边界'
                        % (full, row.get('class'), row.get('type'),
                           ' ' + str(row.get('osm_id')), shown))
                else:
                    hit['locationApproximate'] = True
                    hit['locationPrecision'] = (
                        '登记地址「%s」仅解析到街道／城镇级（Nominatim/OSM %s/%s），'
                        '显示「%s」的近似位置，非酒庄门址'
                        % (full, row.get('class'), row.get('type'), shown))
                if tier == 'precise':
                    precise += 1
                else:
                    approx += 1
                break
        else:
            hit['notes'].append('no_address')

        results.append(hit)
        mark = ''
        if hit['status'] == 'matched':
            mark = '  %-7s %s' % (hit['tier'], (round(hit['lat'], 5), round(hit['lng'], 5)))
        print('%3d/%d  %-38s %s%s' % (idx, len(items), (it.get('name') or '')[:38],
                                      hit['status'], mark), flush=True)
        if len(results) % 5 == 0:
            dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        time.sleep(1.1)

    dst.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    m = sum(1 for r in results if r.get('status') == 'matched')
    print('\n完成：%d 条，命中 %d（%.0f%%）＝ 门牌级 %d + 近似级 %d -> %s' % (
        len(results), m, 100.0 * m / max(1, len(results)), precise, approx, dst))


if __name__ == '__main__':
    main()
