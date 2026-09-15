# coding: utf-8
"""Write the round-1 visual-review verdicts for 006期 Crozes-Hermitage.

One-off authoring script (per skill §2.4b: these are hand-written verdicts for a
fresh round; values are already canonical — do NOT run normalize-visual-review.py).

Self-checks before writing:
  1. every key must exist in the current manifest (apply would silently ignore it);
  2. flag keys whose old role differs from the new role (informational only).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'outputs' / 'collect' / 'crozes-hermitage' / 'images' / 'wine-image-manifest.json'
OUT = ROOT / 'work' / 'crozes-hermitage' / 'visual-review.json'

W = 'wine-bottle'; P = 'wine-photo'
V = {}


def v(slug, file, role, attr, appel, conf, note):
    V['%s|%s' % (slug, file)] = {
        'role': role, 'attribution': attr, 'appellation': appel,
        'confidence': conf, 'note': note}


# ---- castel-freres（第三方品牌标识） --------------------------------------
v('castel-freres', '07-MALARD-resized.png', 'document-label', 'not-a-wine', None, 'high',
  '第三方品牌标识：Champagne Malard（Castel 体系香槟品牌）。不是本产区酒款，也不是该条目自有标识。')
v('castel-freres', '10-maison-nicolas-ft.png', 'document-label', 'not-a-wine', None, 'high',
  '第三方品牌图形（Maison Nicolas 红色色块）。非酒款图。')

# ---- cave-jean-claude-marsanne-et-fils（Domaine Jean-Claude Marsanne, Mauves）----
sl = 'cave-jean-claude-marsanne-et-fils'
v(sl, '01-winery-41.png', 'logo-or-graphic', 'not-a-wine', None, 'high', '绿底酒瓶与酒杯线稿插画，非照片。')
v(sl, '02-ST-JO-R-2017-.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH / APPELLATION SAINT-JOSEPH CONTROLEE，2017 红。')
v(sl, '03-ST-JO-R-2018-.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH，2018 红。')
v(sl, '04-ST-JO-BLANC-2018-.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH，2018 白。')
v(sl, '05-CRZ-HERMITAGE-2017-.png', W, 'own-wine', 'Crozes-Hermitage', 'high',
  '标面读出 APPELLATION CROZES-HERMITAGE CONTROLEE（2017）。**纠正启发式：此前误记为 Hermitage。**')
v(sl, '06-CRZ-HERMITAGE-2018-.png', W, 'own-wine', 'Crozes-Hermitage', 'high',
  '标面读出 CROZES-HERMITAGE（2018）。**纠正启发式：此前误记为 Hermitage。**')
v(sl, '07-SYHRAH-MAUVES-2018-.png', W, 'own-wine', 'IGP Ardèche', 'high',
  '标面读出「"Syrah mauve" SYRAH — INDICATION GÉOGRAPHIQUE PROTÉGÉE ARDÈCHE」，非法定产区酒。')
v(sl, '08-VIOGNIER-2016-.png', W, 'own-wine', 'IGP Ardèche', 'high', '标面读出 VIOGNIER — IGP ARDÈCHE（2016）。')
v(sl, '09-VIOGNIER-LES-RUISSEAUX-2018-.png', W, 'own-wine', 'IGP Ardèche', 'high', '标面读出「LES RUISSEAUX」VIOGNIER — IGP ARDÈCHE（2018）。')
v(sl, '10-grappe-bouteille-ST-JO-2018-FINALE-2-.png', W, 'own-wine', 'Saint-Joseph', 'high',
  '瓶旁为手绘葡萄串插画；瓶标读出 SAINT-JOSEPH 2018。')
v(sl, '12-hve_coul.png', 'document-label', 'not-a-wine', None, 'high', 'HVE（Haute Valeur Environnementale）认证标识。')

# ---- bibovino（零售商产品图） --------------------------------------------
v('bibovino', '06-Bibovino_Packshot_BourgueilAudebert2022.png', W, 'stock-or-generic', 'Bourgueil', 'medium',
  '零售商 bibovino 的 Bag-in-Box 产品图（Bourgueil Audebert 2022）。不是本名录生产者的自有酒款，用图须注明第三方零售图。')
v('bibovino', '10-etiquettebergeracsecletapbio2023.png', 'document-label', 'not-a-wine', 'Bergerac', 'high',
  'Château Le Tap Bergerac Sec 2023 酒标扫描（有机）。非本产区酒款。')

v('cave-de-tain', '01-cave-de-tain.png', 'producer-logo', 'producer-official', None, 'high', 'Cave de Tain 合作社徽标（龙纹盾徽）。')

# ---- dauvergne-ranvier（跨产区酒商 D&R Sélection） -------------------------
sl = 'dauvergne-ranvier'
v(sl, '01-696911ce785016311b5c6fca_crozes-hermitage_20rge.avif', W, 'own-wine', 'Crozes-Hermitage', 'high',
  'D&R Sélection Crozes-Hermitage 2024，标面读出产区行。')
v(sl, '04-6969136a6547dcd3d24c2167_Voisin_20d_27en_20face_20-_20modifie_CC_81e_20a_CC_80_20valider_20par_20FD.avif',
  W, 'own-wine', 'Vin de France', 'medium',
  '「Le Voisin d\'en face」Syrah；标面底部疑为 VIN DE FRANCE，小字置信中等。')
v(sl, '05-6969122fb47af30b7b533bf2_VDF_20Levat.avif', W, 'own-wine', None, 'high',
  'LEVAT 2019「Vin affranchi」；标面无法定产区行，appellation 留空。')
v(sl, '06-6969118b8de84eab75c89770_St_20Estephe_20Slct_20RGE_20Face.avif', W, 'own-wine', 'Saint-Estèphe', 'high',
  'D&R Sélection Saint-Estèphe 2023，标面读出「Appellation Saint-Estèphe Contrôlée」。')
v(sl, '08-696910b9a68b4c764bc43b4c_co_CC_82te_20ro_CC_82tie_20slct_20rge2.avif', W, 'own-wine', 'Côte-Rôtie', 'high',
  'D&R Sélection Côte-Rôtie 2023，标面读出。')
v(sl, '09-69690fe735ae1b980abd6846_brdx_20vg_20rge_202.avif', W, 'own-wine', 'Bordeaux', 'high',
  'D&R「Vin Gourmand」Bordeaux 2024，标面读出。')
v(sl, '11-69690db3aab429327cf16c51_ch9_20sat.avif', W, 'own-wine', 'Châteauneuf-du-Pape', 'high',
  '「Du Soleil à la Terre」Châteauneuf-du-Pape 2023，标面读出。')

v('domaine-arnoux-vins', '02-brutal-character-mainbanner.webp', 'uncertain', 'not-a-wine', None, 'high',
  '网页横幅漫画插画，与酒款/庄园无关，不建议作配图。')

# ---- domaine-courbis -----------------------------------------------------
sl = 'domaine-courbis'
v(sl, '04-viognier-2016-blanc.png', W, 'own-wine', 'IGP Ardèche', 'high', '标面读出 Viognier — IGP ARDÈCHE（2016）。')
v(sl, '05-syrah.png', W, 'own-wine', 'IGP Ardèche', 'high', '标面读出 Syrah — IGP ARDÈCHE。')
v(sl, '07-st-peray-le-tram.png', W, 'own-wine', 'Saint-Péray', 'high', '标面读出 SAINT-PÉRAY（Le Tram），白。')
v(sl, '08-st-joseph-les-royes.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH（Les Royes），红。')
v(sl, '09-st-joseph-rouge.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH，红。')
v(sl, '10-LES-ROYES-st-joseph-blanc.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH（Les Royes），白。')
v(sl, '11-st-joseph-blanc.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH，白。')
v(sl, '12-st-joseph-cotte-sud.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH（La Cotte Sud），红。')

# ---- cave-de-clairmont ---------------------------------------------------
sl = 'cave-de-clairmont'
v(sl, '01-CapriceSyrah.png', W, 'own-wine', None, 'high',
  '实为 MARSANNE「#Juste un caprice.」彩字标（Clairmont & Domaines）；标面无法定产区行。**文件名写 Syrah 不可信。**')
v(sl, '02-FTCLAIRMONT_3.png', W, 'own-wine', None, 'high', '同 01：MARSANNE「#Juste un caprice.」版式，标面无产区行。')
v(sl, '03-CapriceViognier.png', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Caprice VIOGNIER — Collines Rhodaniennes。')
v(sl, '04-36097122-af75-48a8-b08e-e0016aa9bd55.png', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Caprice SAUVIGNON — Collines Rhodaniennes。')
v(sl, '05-Beige_Minimalist_Mood_Photo_Collage.png', W, 'own-wine', None, 'high', '「Bouquet de Syrah」桃红，标面无法定产区行，appellation 留空。')
v(sl, '09-ec6ae64c-549d-4600-b224-2c0a492eae69.png', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Confidence SYRAH VIOGNIER — Collines Rhodaniennes。')
v(sl, '10-ConfidencePinotNoir.png', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Confidence PINOT NOIR — Collines Rhodaniennes。')
v(sl, '11-PRO_6546-1png.png', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Confidence CHARDONNAY — Collines Rhodaniennes。')
v(sl, '12-CoeurRougenonmillesime.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '白标读出 CLAIRMONT — CROZES-HERMITAGE（无年份）。')

# ---- domaine-des-hauts-chassis --------------------------------------------
sl = 'domaine-des-hauts-chassis'
v(sl, '02-winery-18.png', 'logo-or-graphic', 'not-a-wine', None, 'high', '橡木桶素描插画。')
v(sl, '03-winery-40.png', 'logo-or-graphic', 'not-a-wine', None, 'high', '橡木桶插画（绿底）。')
v(sl, '05-Les-Chassis.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 DOMAINE DES HAUTS CHÂSSIS — CROZES-HERMITAGE「Les Châssis」红。')
v(sl, '06-Les-Calcaires.png', W, 'own-wine', 'Saint-Péray', 'high',
  '标面读出 SAINT-PÉRAY「Les Calcaires」白。**纠正启发式：这不是 Crozes。**')
v(sl, '07-LEssentiel.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CROZES-HERMITAGE「L\'Essentiel」白。')
v(sl, '08-Condrieu.png', W, 'likely-own', 'Condrieu', 'high',
  '标面读出 CONDRIEU 2018，但瓶签署名 **François Gonnnet**——图挂在 Hauts Châssis 官网而瓶署另一生产者名，用图与归属表述须谨慎。')
v(sl, '09-Hermitage-blanc.png', W, 'likely-own', 'Hermitage', 'high',
  '标面读出 HERMITAGE 2017（白），瓶署 François Gonnnet，同上条注意归属。')
v(sl, '10-Esquisse.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CROZES-HERMITAGE「Esquisse」红。')
v(sl, '11-Saint-Joseph.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH 红（cuvée 名手写体）。')
v(sl, '12-Les-Galets.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CROZES-HERMITAGE「Les Galets」红。')

# ---- domaine-breyton（官网绿色插画组） --------------------------------------
sl = 'domaine-breyton'
for f, note in [('03-grappe-raisin-1.png', '葡萄串线稿插画'),
                ('04-picto-culture.png', '葡萄藤/农事图标插画'),
                ('05-raisin-portfolio.png', '葡萄串插画（组合）'),
                ('06-fond-vin.png', '酒杯线稿插画（页面底图）')]:
    v(sl, f, 'logo-or-graphic', 'not-a-wine', None, 'high', note + '，非照片非酒款。')

v('domaine-du-murinais', '09-carto.png', 'document-map', 'not-a-wine', None, 'high', '村镇/产区关系地图插画。')

# ---- domaine-emmanuel-darnaud ---------------------------------------------
sl = 'domaine-emmanuel-darnaud'
v(sl, '01-0006_hermitage_darnaud-6_WEB-e1700728807132.jpg', 'producer-estate', 'producer-official', None, 'high',
  '葡萄园与山坡小礼拜堂实景（官网 Hermitage 栏目页），庄园/风土照，非酒瓶特写。')
v(sl, '02-0010_hermitage_darnaud-10_WEB-e1700729338905.jpg', 'producer-estate', 'producer-official', None, 'high',
  '手中葡萄串特写（官网页面），风土/农事照。')
v(sl, '03-cropped-Triangle.png', 'logo-or-graphic', 'not-a-wine', None, 'high', '品牌三角图形。')

# ---- cave-st-desirat -------------------------------------------------------
sl = 'cave-st-desirat'
v(sl, '02-vignette-aop-condrieu1.jpg', 'producer-site', 'producer-official', 'Condrieu', 'medium',
  '合作社门店的 Condrieu 品类缩略图（葡萄串照），说明门店经销多个 AOC，不代表自有酒款。')
v(sl, '04-374c10f23dde395ea18b0ddaa100e3ef.jpg', 'producer-logo', 'not-a-wine', None, 'high',
  '「RENDEZ-VOUS TERROIRS · Vignobles de la Rhône」组织标识（红菱形）。')
v(sl, '09-vignette-maison-des-vins-saint-desirat6.jpg', 'document-label', 'not-a-wine', None, 'high',
  'Maison des vins de Saint-Désirat 宣传拼贴小图。')

# ---- domaine-gilles-robin ---------------------------------------------------
sl = 'domaine-gilles-robin'
v(sl, '02-enmagnum-alberic2018-page-001.jpg', 'document-label', 'not-a-wine', None, 'high',
  'en Magnum 杂志页节选（Alberic 2018 文字介绍），非图片素材主体。')
v(sl, '06-MARSANNE-1-scaled-e1761292747753.jpg', W, 'own-wine', None, 'high',
  'MARSANNE 2024（Gilles Robin）；标面无产区行，appellation 留空。')
v(sl, '07-VIOGNIER-1-scaled-e1761292877180.jpg', W, 'own-wine', None, 'high',
  'VIOGNIER 2024；标面无产区行，appellation 留空。')
v(sl, '08-LES-CHATAIGNIERS-scaled-e1761292965415.jpg', W, 'own-wine', 'Saint-Péray', 'high',
  'LES CHÂTAIGNIERS 2024 — **SAINT-PÉRAY**。纠正：不是 Crozes-Hermitage。')
v(sl, '09-PAPILLON-B-scaled-e1761293039204.jpg', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Papillon — CROZES-HERMITAGE。')
v(sl, '10-Marelles-24-e1761293186322.jpg', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 LES MARELLES 2024 — CROZES-HERMITAGE。')
v(sl, '11-PETITE-PIERRE-1-scaled-e1761293247679.jpg', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 PETITE PIERRE 2024 — SAINT-JOSEPH。')
v(sl, '12-HERMITAGE-BLC-scaled-e1761293323555.jpg', W, 'own-wine', 'Hermitage', 'high', '标面读出 HERMITAGE 2023（白）。')

# ---- domaine-gaylord-machon -------------------------------------------------
sl = 'domaine-gaylord-machon'
for f, name in [('01-crozes-hermitage-ghany-machon_2.jpg', 'Ghany（粉标）'),
                ('02-Ghany_2.jpg', 'Ghany'),
                ('03-crozes-hermitage-lhony-gaylord-machon_2.jpg', 'Lhony（黑标）'),
                ('04-Lhony_2NOIR.jpg', 'Lhony'),
                ('05-crozes-hermitage-blanc-gaylord-machon_2.jpg', 'blanc（青标）'),
                ('06-La-fille_2.jpg', 'La Fille（蓝标）')]:
    v(sl, f, W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CROZES-HERMITAGE（%s）。' % name)

v('etienne-becheras', '01-1.jpg', 'producer-estate', 'producer-official', None, 'high',
  '葡萄园与坡顶小礼拜堂实景，庄园/风土照。')

# ---- domaine-esprit（Jean Esprit） -------------------------------------------
sl = 'domaine-esprit'
v(sl, '01-bouteille-Le-Zouave-2025.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Le Zouave — CROZES-HERMITAGE（Jean Esprit）。')
v(sl, '02-Bouteille-Perle-noire-2025.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 PERLES NOIRES — CROZES-HERMITAGE。')
v(sl, '03-Bouteille-perle-ivoire-2025.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 PERLES IVOIRE — CROZES-HERMITAGE（白）。')
v(sl, '04-Pont-de-la-Deesse-Blanc-2025.png', W, 'own-wine', 'Vin de France', 'high', '标面读出「Pont de la Déesse — VIN DE FRANCE」（白）。')
v(sl, '05-Pont-de-la-Deesse-Rose-2025.png', W, 'own-wine', 'Vin de France', 'high', '标面读出 VIN DE FRANCE（桃红）。')
v(sl, '06-bouteille-arlettes-2025.png', W, 'own-wine', 'Cornas', 'high', '标面读出 Les Arlettes — **CORNAS**。不是 Crozes。')
v(sl, '07-bouteille-esprit-2025.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Esprit — CROZES-HERMITAGE。')
v(sl, '08-coffret-decouverte-2025.png', P, 'own-wine', 'Crozes-Hermitage', 'high', '发现礼盒照（六瓶全家福，标面均为 CROZES-HERMITAGE）。')
v(sl, '09-coffret-perle-2025.png', P, 'own-wine', 'Crozes-Hermitage', 'high', 'Perles 系列礼盒照（标面 CROZES-HERMITAGE）。')
v(sl, '10-le-zouave.jpg', P, 'own-wine', 'Crozes-Hermitage', 'medium', 'Le Zouave 酒瓶实景照（桶边），与 01 同款。')
v(sl, '11-zouave-visuel.jpg', P, 'own-wine', 'Crozes-Hermitage', 'medium', 'Le Zouave 视觉图（品牌合成背景），同款。')

# ---- domaine-etienne-pochon --------------------------------------------------
sl = 'domaine-etienne-pochon'
v(sl, '01-chateau-curson-blanc.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CHÂTEAU CURSON — Crozes-Hermitage（白，Étienne Pochon）。')
v(sl, '02-chateau-curson-rouge.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '同系列红（标面同版式，产区行 Crozes-Hermitage）。')
v(sl, '03-etienne-pochon-blanc.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Étienne Pochon — Crozes-Hermitage（白，含有机标）。')
v(sl, '04-etienne-pochon-rouge.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Crozes-Hermitage（红，有机标）。')

v('domaine-michelas-saint-jemms', '03-Michelas_St_Jemms_800x_2x.png', 'producer-logo', 'producer-official', None, 'high',
  'Domaine Michelas St Jemms 手写体标识。')

# ---- domaine-laurent-veyrat ---------------------------------------------------
v('domaine-laurent-veyrat', '01-TONNEAUX.webp', 'producer-estate', 'producer-official', None, 'high',
  '酒窖橡木桶黑白照。**纠正启发式：不是酒瓶图（文件名 tonneaux=酒桶）。**')
v('domaine-laurent-veyrat', '02-LAURENT-EMILIE-CAVE.jpg', 'producer-people', 'producer-official', None, 'high',
  '酒窖中 Laurent 与 Émilie 两人工作照（黑白）。')

# ---- domaine-mucyn -------------------------------------------------------------
sl = 'domaine-mucyn'
v(sl, '01-IGP.jpg', W, 'own-wine', 'IGP Collines Rhodaniennes', 'high', '标面读出 Gam\'Sy — COLLINES RHODANIENNES。')
v(sl, '02-Crozes-hermitage-blanc-1.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Les Charmeuses — CROZES-HERMITAGE（白）。')
v(sl, '03-Crozes-Rouge.jpg', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 Les Entrecoeurs — CROZES-HERMITAGE（红）。')
v(sl, '04-Saint-joseph-blanc-1.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 Les Carats — SAINT-JOSEPH（白）。')
v(sl, '05-Saint-Joseph-Rouge.jpg', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 Les Salamandres — SAINT-JOSEPH（红）。')
v(sl, '06-cornas-hypsos.png', W, 'own-wine', 'Cornas', 'high', '标面读出 Hypsos — CORNAS。')

v('domaine-melody', '04-insta.png', 'uncertain', 'not-a-wine', None, 'high', 'Instagram 平台图标，装饰元素。')
v('domaine-melody', '05-fb.png', 'uncertain', 'not-a-wine', None, 'high', 'Facebook 平台图标，装饰元素。')
v('domaine-melody', '06-logo2.png', 'producer-logo', 'producer-official', None, 'high', 'DOMAINE MELODY 字标。')

# ---- domaine-pierre-gaillard -----------------------------------------------------
sl = 'domaine-pierre-gaillard'
v(sl, '02-Design-sans-titre-67.png', W, 'own-wine', 'Vin de France', 'high', '标面读出 AVANT L\'HEURE — VIN DE FRANCE（甜白型瓶）。')
v(sl, '03-Pierre-saint-peray-low.png', W, 'own-wine', 'Saint-Péray', 'high', '标面读出 SAINT-PÉRAY。')
v(sl, '04-Pierre-saint-joseph-blanc-low.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH（白）。')
v(sl, '05-Pierre-condrieu-low.png', W, 'own-wine', 'Condrieu', 'high', '标面读出 CONDRIEU。')
v(sl, '06-Gaillard-Crozes-Hermitage-HD.png', W, 'own-wine', 'Crozes-Hermitage', 'high', '标面读出 CROZES-HERMITAGE。')
v(sl, '07-Pierre-saint-joseph-low.png', W, 'own-wine', 'Saint-Joseph', 'high', '标面读出 SAINT-JOSEPH。')
v(sl, '08-Pierre-cornas-low-1.png', W, 'own-wine', 'Cornas', 'high', '标面读出 CORNAS。')
v(sl, '09-Pierre-co_te-ro_tie-low-1.png', W, 'own-wine', 'Côte-Rôtie', 'high', '标面读出 CÔTE-RÔTIE。')
v(sl, '10-Pierre-les-gendrines-low.png', W, 'own-wine', 'Côtes du Rhône', 'high',
  '标面读出 LES GENDRINES — **CÔTES DU RHÔNE**。纠正：不是 Saint-Joseph。')
v(sl, '11-Pierre-l_octroi-low.png', W, 'own-wine', 'Condrieu', 'high',
  '标面读出 L\'OCTROI — **CONDRIEU**。纠正：不是 Saint-Péray。')
v(sl, '12-Pierre-clos-de-cuminaille-low.png', W, 'own-wine', 'Saint-Joseph', 'high',
  '标面读出 CLOS DE CUMINAILLE — **SAINT-JOSEPH**。纠正：不是 Côte-Rôtie。')

# ---- domaine-pradelle --------------------------------------------------------------
sl = 'domaine-pradelle'
v(sl, '02-62913c765057-Vendangeur-d-un-jour-7-.webp.webp', 'document-label', 'not-a-wine', None, 'high',
  '「Vendangeur d\'un jour」体验活动宣传海报（粉底），非酒款图。')
v(sl, '12-62913c765057-Vendangeur-d-un-jour-7-.webp.webp', 'document-label', 'not-a-wine', None, 'high', '同上（同海报另一尺寸）。')

# ---- domaine-yves-cuilleron ----------------------------------------------------------
sl = 'domaine-yves-cuilleron'
v(sl, '03-1987.jpg', 'producer-people', 'producer-official', None, 'high', '酒窖人物黑白老照片（1987）。')
v(sl, '04-Premier_Mill_sime_dec88.png', P, 'own-wine', 'Condrieu', 'high',
  '双瓶历史照：左 CONDRIEU 1957、右 SAINT-JOSEPH 1986（首年份纪念页）。**纠正启发式：不是 Côte-Rôtie。**')

# ------------------------------------------------------------------ self-check
manifest = json.loads(MANIFEST.read_text())
have = {'%s|%s' % (e['slug'], g['file'])
        for e in manifest['producers'] for g in (e.get('images') or [])}
missing = sorted(set(V) - have)
old_role_diff = []
by_key = {'%s|%s' % (e['slug'], g['file']): g
          for e in manifest['producers'] for g in (e.get('images') or [])}
for k, verdict in V.items():
    g = by_key.get(k)
    if g and g.get('role') != verdict['role']:
        old_role_diff.append('%s: %s -> %s' % (k, g.get('role'), verdict['role']))

print('verdicts:', len(V))
print('keys not in manifest (%d):' % len(missing))
for k in missing[:10]:
    print('  ', k)
print('role changed vs heuristic (%d):' % len(old_role_diff))
for k in old_role_diff:
    print('  ', k)

if not missing:
    OUT.write_text(json.dumps(V, ensure_ascii=False, indent=1) + '\n')
    print('wrote', OUT)
