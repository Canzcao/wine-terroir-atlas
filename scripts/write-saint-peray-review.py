# coding: utf-8
"""Write the 2026-09-17 visual-review verdicts for the association-module images
and apply them to the manifest.

What was actually looked at (contact sheets + direct reads of originals):
  * 37 packshots  -> 36 read SAINT-PÉRAY off the label, 1 (Domaine du Coulet)
                     reads CORNAS ("Brise cailloux", Matthieu Barret).
  * 37 portraits  -> 31 are people/estate photos; 6 are byte-identical
                     duplicates of the same producer's packshot, so they are
                     dropped from the manifest instead of being reviewed twice.

Because the packshot verdicts came from reading the labels directly, this file
is written with canonical role/attribution values and is applied WITHOUT running
normalize-visual-review.py (which would rewrite historical roles and derive
attribution from role).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'outputs' / 'collect' / 'saint-peray' / 'images' / 'wine-image-manifest.json'
REVIEW = ROOT / 'work' / 'saint-peray' / 'visual-review.json'

# appellation read off the label, per producer slug (None = not readable)
LABEL_APPELLATION = {
    'cave-blanc-christophe': 'SAINT-PÉRAY',
    'cave-de-tain': 'SAINT-PÉRAY',
    'cave-yves-cuilleron': 'SAINT-PÉRAY',
    'colombo': 'SAINT-PÉRAY',
    'domaine-alain-voge': 'SAINT-PÉRAY',
    'domaine-bourg-mickael': 'SAINT-PÉRAY',
    'domaine-chaboud-cellier': 'SAINT-PÉRAY',
    'domaine-clape': 'SAINT-PÉRAY',
    'domaine-courbis': 'SAINT-PÉRAY',
    'domaine-cyril-courvoisier': 'SAINT-PÉRAY',
    'domaine-de-la-sarbeche': 'SAINT-PÉRAY',
    'domaine-de-lorient': 'SAINT-PÉRAY',
    'domaine-des-hauts-chassis': 'SAINT-PÉRAY',
    'domaine-du-coulet': 'CORNAS',          # 标面印 “Cornas / Brise cailloux / Matthieu BARRET”
    'domaine-du-tunnel': 'SAINT-PÉRAY',
    'domaine-durand': 'SAINT-PÉRAY',
    'domaine-guillaume-gilles': 'SAINT-PÉRAY',   # 原图直读：“Appellation Saint Peray Contrôlée / Millésime 2009”
    'domaine-johann-michel': 'SAINT-PÉRAY',
    'domaine-laurent-fayolle': 'SAINT-PÉRAY',
    'domaine-verset-a-et-e': 'SAINT-PÉRAY',
    'domaine-villard': 'SAINT-PÉRAY',
    'domaines-paul-jaboulet-aine': 'SAINT-PÉRAY',
    'dumien-serrette': 'SAINT-PÉRAY',
    'earl-catherine-et-pascal-jamet': 'SAINT-PÉRAY',
    'famille-cecillon': 'SAINT-PÉRAY',
    'famille-pierre-gaillard': 'SAINT-PÉRAY',
    'farge': 'SAINT-PÉRAY',
    'ferraton-pere-fils': 'SAINT-PÉRAY',
    'j-denuziere': 'SAINT-PÉRAY',
    'lemenicier': 'SAINT-PÉRAY',
    'les-vins-de-vienne': 'SAINT-PÉRAY',
    'luyton-fleury': 'SAINT-PÉRAY',
    'maison-m-chapoutier': 'SAINT-PÉRAY',
    'melody': 'SAINT-PÉRAY',
    'remy-nodin': 'SAINT-PÉRAY',
    'vignoble-de-boisseyt': 'SAINT-PÉRAY',
    # 'domaine-du-geant' packshot is an SVG vector file, not a photo -> verdict below
}

LABEL_CUVÉE = {
    'cave-yves-cuilleron': 'Les Potiers',
    'colombo': 'La Belle de Mai',
    'domaine-alain-voge': 'Fleur de Crussol',
    'domaine-des-hauts-chassis': 'Les Calcaires',
    'domaine-du-coulet': 'Brise cailloux (Cornas)',
    'domaine-du-tunnel': None,
    'domaine-laurent-fayolle': 'Montis',
    'domaines-paul-jaboulet-aine': 'Les Sauvagères',
    'dumien-serrette': 'Grand Classieu',
    'ferraton-pere-fils': 'La Mateus',
    'maison-m-chapoutier': 'Hongrie',
    'remy-nodin': 'Vieilles vignes du Suchet',
    'luyton-fleury': 'La Source',
    'domaine-villard': 'Version',
    'domaine-guillaume-gilles': 'Le Saint Pérey (2009)',
}


def main():
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    review = {}
    dropped = []

    for entry in man['producers']:
        slug = entry['slug']
        ims = entry.get('images') or []
        pk = [i for i in ims if i['file'].startswith('packshot')]
        pt = [i for i in ims if i['file'].startswith('portrait')]

        # drop portraits that are byte-identical to the packshot
        if pk and pt:
            pkh = {i['sha256'] for i in pk}
            keep = [i for i in ims if not (i['file'].startswith('portrait') and i['sha256'] in pkh)]
            removed = len(ims) - len(keep)
            if removed:
                dropped.append(slug)
                entry['images'] = keep
                ims = keep

        for im in ims:
            key = f"{slug}|{im['file']}"
            if im['file'].startswith('packshot'):
                if im['file'].endswith('.svg'):
                    review[key] = {
                        'role': 'uncertain', 'attribution': 'unverified', 'appellation': None,
                        'confidence': 'low',
                        'note': '协会 packshot 模块给出的是 SVG 矢量图（8 KB），不是照片，无法读标判读酒款；'
                                'appellation 留空，留待酒庄官网重采。',
                    }
                else:
                    ap = LABEL_APPELLATION.get(slug)
                    note = '协会 packshot 模块，拼图复核+原图直读标面'
                    if slug == 'domaine-du-coulet':
                        note += '：标面印 “Cornas / Brise cailloux / Matthieu BARRET”，是 Cornas 酒，不是 Saint-Péray——' \
                                '协会名录收录不代表页面上每瓶都是 Saint-Péray，下游不得当 Saint-Péray 配图。'
                    elif slug == 'domaine-guillaume-gilles':
                        note += '：原图直读 “Appellation Saint Peray Contrôlée / Millésime 2009 / Guillaume GILLES, Vigneron à Cornas”。'
                    elif ap:
                        note += f'：标面读得 {ap}' + (f'，cuvée {LABEL_CUVÉE[slug]}' if LABEL_CUVÉE.get(slug) else '')
                    review[key] = {
                        'role': 'wine-bottle', 'attribution': 'likely-own',
                        'appellation': ap, 'confidence': 'high', 'note': note,
                    }
            elif im['file'].startswith('portrait'):
                review[key] = {
                    'role': 'producer-people', 'attribution': 'producer-official',
                    'appellation': None, 'confidence': 'high',
                    'note': '协会 portrait 模块，拼图复核：庄主/团队/酒窖/葡萄园人物或场景照，非酒瓶。',
                }

    MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8')
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'review verdicts: {len(review)}')
    print(f'dropped duplicate portraits for {len(dropped)} producers: {dropped}')
    n_sp = sum(1 for v in review.values() if v.get('appellation') == 'SAINT-PÉRAY')
    print(f'packshots labelled SAINT-PÉRAY: {n_sp}')


if __name__ == '__main__':
    main()
