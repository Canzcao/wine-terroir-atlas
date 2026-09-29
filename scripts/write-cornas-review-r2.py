# coding: utf-8
"""Append 2026-09-18 round visual-review verdicts to work/cornas/visual-review.json.

Rules (see skill 2.4b — this is an increment round on an already-normalized
review file):
- write canonical values only (role ∈ apply-visual-review.VALID_ROLES,
  attribution ∈ VALID_ATTR), skip normalize-visual-review.py entirely;
- self-check 1: every key must exist in the manifest (slug|file exact match);
- self-check 2: never overwrite an existing verdict (this round only ADDS keys;
  any collision is reported and left untouched).

Also removes one useless image (a fully black lazy-load placeholder) from the
manifest and disk, as the 007期 precedent does for unusable files.

Usage: python3 scripts/write-cornas-review-r2.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'outputs' / 'collect' / 'cornas' / 'images' / 'wine-image-manifest.json'
REVIEW = ROOT / 'work' / 'cornas' / 'visual-review.json'

J = 'domaine-paul-jaboulet-aine'
R = 'les-remizieres'
T = 'tardieu-laurent'
C = 'kerschen-cecillon-sarl'

PO = 'producer-official'
VERDICTS = {
    # ---- Paul Jaboulet Aîné (jaboulet.com，Crawl-delay 10 已遵守) ----
    f'{J}|01-Our-history.jpg': ('producer-estate', PO, None, 'high',
        '黑白历史照片：采收者背负背篓走过 Jaboulet 葡萄园（官网 Our history 栏目图），历史资料照。'),
    f'{J}|02-Terroirs.jpg': ('producer-estate', PO, None, 'high',
        '石墙梯田葡萄园山坡，官网 Terroirs 栏目图。'),
    f'{J}|03-Sustainable-viticulture.jpg': ('producer-people', PO, None, 'high',
        '马耕犁地与牵引工人在葡萄园行间作业（可持续耕作主题）。'),
    f'{J}|04-Biodiversity.jpg': ('producer-people', PO, None, 'high',
        '女士与爱犬查看葡萄植株（生物多样性主题）；人物未标身份，不写姓名。'),
    f'{J}|05-Eco-responsability.jpg': ('uncertain', PO, None, 'medium',
        '软木栎树皮特写（生态责任主题装饰图），不宜当酒款图或产区实景图。'),
    f'{J}|06-PJA-2410-x-1600-V3-copie-2.jpg': ('producer-people', PO, None, 'high',
        '采收者肩扛红色采收筐走在葡萄园石砌田埂上。'),
    f'{J}|07-IMG_8217-Modifier.jpg': ('producer-estate', PO, None, 'high',
        '酒窖内蛋形混凝土发酵罐与橡木桶阵列。'),
    f'{J}|08-IMG_4009_retouche-large-Modifier.jpg': ('wine-photo', 'own-wine',
        'Hermitage', 'high',
        '标面 HERMITAGE「La Maison Bleue」；石头墙上 lifestyle 瓶照。'
        '注意：这是该庄的 Hermitage 酒，不是 Cornas。'),
    f'{J}|09-IMG_1366_retouche-copie.jpg': ('producer-estate', PO, None, 'high',
        '日落下的葡萄园与小石屋。'),
    f'{J}|10-Crozes-Hermitage_Les-Jalets_2023-BIO_L1600px-1-scaled.png': (
        'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high',
        '标面 CROZES-HERMITAGE LES JALETS 2023（欧盟有机标）。'),
    f'{J}|11-Crozes-Hermitage-Les-Jalets-rouge.jpg': ('producer-estate', PO, None, 'high',
        '文件名写 rouge，实为葡萄园采收场景（人手在行间作业）——文件名不可信的又一例。'),
    f'{J}|12-P45_red03-1.jpg': ('wine-photo', 'own-wine', 'Côtes du Rhône', 'high',
        '标面 PARALLÈLE 45 CÔTES-DU-RHÔNE；酒杯+酒瓶 lifestyle 照。'),
    f'{J}|13-p45_white_01-1.jpg': ('wine-photo', 'own-wine', 'Côtes du Rhône', 'high',
        'PARALLÈLE 45 BLANC 2022，背标可读品种比例（Viognier 22%、Grenache blanc 21%、'
        'Roussanne 18%、Clairette 9%、Marsanne 5%）——有据的年份配方，如做 wine/vintage 记录可用。'),
    f'{J}|14-Viognier_Secret-de-Famille_BLANC-2024-BIO_L1600px-scaled.png': (
        'wine-bottle', 'own-wine', None, 'high',
        '标面 VIOGNIER SECRET DE FAMILLE 2024；仅品种名无法定 AOC，appellation 留空。'),
    f'{J}|15-Crozes-Hermitage_Les-Jalets_BLANC-2024-BIO_L1600px-scaled.png': (
        'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high',
        '标面 CROZES-HERMITAGE LES JALETS（白）2024。'),
    f'{J}|16-Saint-Joseph_Le-Grand-Pompee_BLANC-2024_L1600px-scaled.png': (
        'wine-bottle', 'own-wine', 'Saint-Joseph', 'high',
        '标面 SAINT-JOSEPH LE GRAND POMPÉE（白）2024。'),
    f'{J}|17-Viognier_Secret-de-Famille_BLANC-2024-BIO_L1600px-1024x3008.png': (
        'wine-bottle', 'own-wine', None, 'high',
        '同 14 号图的大尺寸版本：VIOGNIER SECRET DE FAMILLE 2024，标面无 AOC，留空。'),
    f'{J}|18-Crozes-Hermitage_Les-Jalets_BLANC-2024-BIO_L1600px-1024x3008.png': (
        'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high',
        'CROZES-HERMITAGE LES JALETS（白）2024，15 号图大尺寸版本。'),
    f'{J}|19-Saint-Joseph_Le-Grand-Pompee_BLANC-2024_L1600px-1024x3008.png': (
        'wine-bottle', 'own-wine', 'Saint-Joseph', 'high',
        'SAINT-JOSEPH LE GRAND POMPÉE（白）2024，16 号图大尺寸版本。'),
    f'{J}|20-Saint-Jo_Grand-Pompee_2023_L1600px-scaled.png': (
        'wine-bottle', 'own-wine', 'Saint-Joseph', 'high',
        '标面 SAINT-JOSEPH LE GRAND POMPÉE 2023（红）。'),
    f'{J}|21-Saint-Joseph-Le-Grand-Pompee-rouge.jpg': ('producer-estate', PO, None, 'high',
        '文件名写 rouge，实为虞美人草甸葡萄园全景——再次证明不能按文件名分类。'),
    f'{J}|22-P45_BLANC_2023.png': ('wine-bottle', 'own-wine', 'Côtes du Rhône', 'high',
        'PARALLÈLE 45 BLANC 2023 正标，标面印品种比例（Viognier 38% 等），AOC CÔTES-DU-RHÔNE。'),
    f'{J}|23-EUR_2022_P45_ROUGE-1.png': ('wine-bottle', 'own-wine', 'Côtes du Rhône', 'high',
        'PARALLÈLE 45 ROUGE 2022 正标（Grenache 52%、Syrah 37%、Mourvèdre 3%、'
        'Marsanne 1%、Carignan 2%），AOC CÔTES-DU-RHÔNE。'),
    f'{J}|24-Viognier-Secret-de-Famille-2023.png': ('wine-bottle', 'own-wine', None, 'high',
        'VIOGNIER SECRET DE FAMILLE 2023（新版标），标面无 AOC 字样，留空。'),
    f'{J}|25-Saint-Jo_Grand-Pompee_2023_L1600px-1024x3008.png': (
        'wine-bottle', 'own-wine', 'Saint-Joseph', 'high',
        'SAINT-JOSEPH LE GRAND POMPÉE 2023（红），20 号图大尺寸版本。'),
    f'{J}|26-Syrah_2024_L1600px-scaled.png': ('wine-bottle', 'own-wine', None, 'high',
        '标面仅 SYRAH 2024（品种名，无 AOC），appellation 留空。'),
    # ---- Les Remizières ----
    f'{R}|01-Vinalies2025.png': ('document-label', PO, None, 'high',
        '2025 年 Vinalies 全国竞赛银奖徽章（Œnologues de France）。'),
    f'{R}|02-OR-2025.jpg': ('document-label', PO, None, 'high',
        '2025 年独立酒农竞赛金奖（Vignerons Indépendants OR）徽章。'),
    f'{R}|03-Hachette2017-15euros.jpg': ('document-label', PO, None, 'high',
        '《Hachette 葡萄酒指南 2017》"15 欧元以下好计划" 推荐标。'),
    f'{R}|04-caveau.jpg': ('producer-estate', PO, None, 'high',
        '品酒窖（caveau）：拱门后大橡木桶与桶阵。'),
    f'{R}|05-caveau2.jpg': ('producer-estate', PO, None, 'high',
        '酒窖内单只橡木桶（桶板印酒庄 R 字标）。'),
    f'{R}|06-LOGO_REGION_RVB-BLEU-GRIS.png': ('logo-or-graphic', PO, None, 'high',
        'Auvergne-Rhône-Alpes 大区标识（资助/合作署名用），非产区实景图。'),
    f'{R}|07-travail-1.jpg': ('producer-estate', PO, None, 'high',
        '成行葡萄园全景（网站 travail 栏目图）。'),
    f'{R}|08-travail-2.jpg': ('producer-estate', PO, None, 'high',
        '老藤新芽逆光特写。'),
    f'{R}|09-travail-3.jpg': ('producer-people', PO, None, 'high',
        '人工采收：采 Grape 入桶的手部与藤串（人未露脸，不写身份）。'),
    f'{R}|10-travail-4.jpg': ('producer-estate', PO, None, 'high',
        '新橡木桶（桶板印 DAMY 桶厂标）陈酿库。'),
    f'{R}|11-travail-5.jpg': ('wine-label', 'own-wine', None, 'medium',
        '瓶帽/酒标 R 字标微距；产区读不出，appellation 留空。'),
    # ---- Tardieu Laurent ----
    f'{T}|01-040_cmoirencbd.jpg': ('producer-estate', PO, None, 'high',
        '发酵车间大橡木桶列（酒窖）。'),
    f'{T}|02-009_cmoirencbd.jpg': ('producer-estate', PO, None, 'high',
        '庄园建筑外观（橄榄树前景）。'),
    f'{T}|03-034_cmoirencbd.jpg': ('producer-estate', PO, None, 'high',
        '老桶堆叠（酒窖细节）。'),
    f'{T}|04-tardieulaurent_cmoirenc_051846_16469_retina.jpg': (
        'producer-estate', PO, None, 'high',
        '石墙梯台葡萄园俯瞰（风土表达）。'),
    f'{T}|05-tardieulaurent_cmoirenc_042402_16470_retina.jpg': (
        'producer-estate', PO, None, 'high',
        '行列式葡萄园坡地（秋色）。'),
    f'{T}|06-027_cmoirencbd.jpg': ('producer-estate', PO, None, 'high',
        '陶罐（amphore）发酵与酒液取样；小黑板隐约「JM05/HE…」，字不全不作产区依据，留空。'),
    f'{T}|07-cmoirenc_135563.jpg': ('producer-estate', PO, None, 'high',
        '地下酒窖橡木桶列与地面导轨。'),
    f'{T}|08-cmoirenc_135549.jpg': ('wine-photo', 'own-wine', None, 'medium',
        '两瓶酒与品酒杯：一瓶标面 CHÂTEAUNEUF-DU-PAPE、一瓶 SAINT-JOSEPH。'
        '两瓶两产区，单值 appellation 字段无法表达，故留空；下游不得只按单一产区使用。'),
    f'{T}|09-cmoirenc_135497.jpg': ('producer-people', PO, None, 'high',
        '酿酒师在酒窖闻杯中酒（人物未标身份）。'),
    f'{T}|10-phototheque.jpg': ('producer-people', PO, None, 'high',
        '工作人员倚桶留影（官网 photothèque 图库页）。'),
    f'{T}|11-phototheque2.jpg': ('producer-estate', PO, None, 'high',
        '深色土壤葡萄园行植（图库页）。'),
    # ---- Kerschen Cécillon (juliencecillon.com，官网为本轮新确认) ----
    f'{C}|01-SAINT-JOSEPH_2C_20BABYLONE.png': ('wine-bottle', 'own-wine',
        'Saint-Joseph', 'medium',
        '标面 Julien Cécillon SAINT-JOSEPH「Babylone」；图幅较小但产区可读。'
        '该庄是跨产区生产者，不得当 Cornas 素材。'),
}

DROP = [f'{C}|02-sloppyframe.3214ce8e.png']


def main():
    manifest = json.loads(MANIFEST.read_text())
    review = json.loads(REVIEW.read_text())

    existing_keys = {'%s|%s' % (e['slug'], i['file'])
                     for e in manifest['producers'] for i in (e.get('images') or [])}
    # self-check 1: keys must exist
    missing = [k for k in VERDICTS if k not in existing_keys]
    # self-check 2: no overwrite of an already-delivered verdict
    collisions = [k for k in VERDICTS if k in review]

    added = 0
    for k, (role, attr, app, conf, note) in VERDICTS.items():
        if k in missing or k in collisions:
            continue
        review[k] = {'role': role, 'attribution': attr, 'appellation': app,
                     'confidence': conf, 'note': note}
        added += 1

    # drop unusable placeholder files
    dropped = []
    for key in DROP:
        slug, fname = key.split('|', 1)
        for e in manifest['producers']:
            if e['slug'] != slug:
                continue
            keep = []
            for im in e.get('images') or []:
                if im['file'] == fname:
                    p = MANIFEST.parent / im['relativePath']
                    if p.exists():
                        p.unlink()
                    dropped.append(key)
                    continue
                keep.append(im)
            e['images'] = keep
            if dropped:
                e.setdefault('failures', []).append({
                    'url': (e.get('images') or [{}])[0].get('sourcePage', slug),
                    'error': '剔除 1 张全黑懒加载占位图（%s），非真实内容图' % fname})
    manifest['date'] = manifest.get('date')
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1) + '\n')

    print('added %d verdicts (review now %d)' % (added, len(review)))
    print('dropped placeholders: %d' % len(dropped))
    if missing:
        print('MISSING KEYS (not written): %d' % len(missing))
        for k in missing:
            print('  ', k)
    if collisions:
        print('COLLISIONS with existing verdicts (left untouched): %d' % len(collisions))
        for k in collisions:
            print('  ', k)


if __name__ == '__main__':
    main()
