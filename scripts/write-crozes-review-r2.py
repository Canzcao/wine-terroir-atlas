#!/usr/bin/env python3
# 一次性脚本：006期 Crozes-Hermitage 第二轮视觉复核结论（170 条）
# 规则：直接写规范值（role ∈ VALID_ROLES / attribution ∈ VALID_ATTR），
#       不跑 normalize-visual-review.py；自检键存在性 + 旧结论覆盖告警。
import json
from pathlib import Path

import os as _os
ROOT = Path(_os.environ.get('TERROIR_ROOT', Path(__file__).resolve().parent.parent))
MANIFEST = ROOT / 'outputs/collect/crozes-hermitage/images/wine-image-manifest.json'
REVIEW = ROOT / 'work/crozes-hermitage/visual-review.json'
IX = ROOT / 'work/crozes-hermitage/review-r2/sheet-index.json'

ix = json.loads(IX.read_text())
cells = {int(k): v for k, v in ix['cells'].items()}

def V(n, role, attr, app, conf, note):
    c = cells[n]
    return ('%s|%s' % (c['slug'], c['file']),
            {'role': role, 'attribution': attr, 'appellation': app,
             'confidence': conf, 'note': note})

# 证据说明：拼图定位 + 关键原图（review-r1/small 720px 副本）直读；
# 原图直读项：poinard 02/04/06/08、guigal 06/07/09/10、pilon 10、ogier 12、
# jaboulet 07/11、brotte 05、PJV 02、amira 05/06/07、jaume 03/04、st-clair 02；
# 其余按拼图可读性给置信度。
V2 = dict([
    # --- yann-chave（1-6）---
    V(1, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '标面 Yann Chave 系列，文件名与页面对应 Crozes-Hermitage Blanc，白瓶照。'),
    V(2, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'medium', '深色瓶照，同系列 Crozes-Hermitage Rouge 页面用图；标面小字在拼图中不可读。'),
    V(3, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '原图复核：标面 CROZES-HERMITAGE "Le Rouvre"；启发式误记 logo。'),
    V(4, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '同系列 Saint-Joseph Rouge 页面用图。'),
    V(5, 'wine-bottle', 'own-wine', 'Hermitage', 'high', '同系列 Hermitage Rouge 页面用图。'),
    V(6, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'medium', '01 号同图的 500px 缩放版（页面缩略变体）。'),
    # --- michel-poinard（7-16）---
    V(7, 'logo-or-graphic', 'not-a-wine', None, 'high', '黑底棕色卡通人物插画（厨师形象），非酒款图。'),
    V(8, 'wine-bottle', 'likely-own', 'Crozes-Hermitage', 'medium', '红白格纹标瓶，AOC 行部分可读（CROZES…，右侧被裁）；该站混排多家酒庄瓶图。'),
    V(9, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：瓶身浮雕与标面均为 GIGONDAS（Domaine des Roucas de St Pierre）——非本产区酒款，客串瓶图。'),
    V(10, 'producer-logo', 'not-a-wine', None, 'high', '"DOMAINE DU PRADAS" 手绘风徽标块。'),
    V(11, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：瓶身浮雕 GIGONDAS，标面 APPELLATION GIGONDAS CONTRÔLÉE（Domaine du Pradas）。'),
    V(12, 'producer-logo', 'not-a-wine', None, 'high', '棕底 "DOMAINE DE ST GENS" 徽标块。'),
    V(13, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：瓶身浮雕 GIGONDAS（Domaine de St Gens，L\'Oracle）；非本产区酒款。'),
    V(14, 'wine-photo', 'likely-own', None, 'low', '六瓶组合照（文件名提示 Grand Comtadine / Gigondas），各标小字不可读。'),
    V(15, 'wine-photo', 'likely-own', None, 'low', '多瓶组合照（Comtadine 系列），标面小字不可读。'),
    V(16, 'wine-bottle', 'likely-own', 'Crozes-Hermitage', 'medium', '与 02 号同款红白格纹标瓶（bloc 变体图），AOC 行不可完整判读。'),
    # --- domaine-saint-clair（17-25）---
    V(17, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '标面可读 Crozes Hermitage（"un matin…"），木桌深底瓶照。'),
    V(18, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '原图复核：标面 la fleur enchantée / Crozes-Hermitage，APPELLATION CROZES-HERMITAGE CONTRÔLÉE。'),
    V(19, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'medium', '同系列 "étincelle" 瓶照，AOC 行小字在拼图中不可读；同站标贴图可证。'),
    V(20, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'medium', '同系列 "la fleur d\'enfer" 瓶照，AOC 行小字在拼图中不可读。'),
    V(21, 'producer-logo', 'not-a-wine', None, 'high', 'Instagram 图标，社交平台占位图。'),
    V(22, 'wine-photo', 'likely-own', None, 'low', '首页四瓶组合照，标面小字不可读（同站标贴图显示均为 Crozes-Hermitage 系列）。'),
    V(23, 'wine-label', 'own-wine', 'Crozes-Hermitage', 'high', '标贴扫描件："un matin…" Crozes-Hermitage，Appellation Crozes-Hermitage Contrôlée。'),
    V(24, 'wine-label', 'own-wine', 'Crozes-Hermitage', 'high', '标贴扫描件："étincelle…" Crozes-Hermitage。'),
    V(25, 'wine-label', 'own-wine', 'Crozes-Hermitage', 'high', '标贴扫描件："la fleur enchantée" Crozes-Hermitage。'),
    # --- cave-julien-cecillon（26）---
    V(26, 'uncertain', 'not-a-wine', None, 'high', '空白占位图（sloppyframe），无有效内容。'),
    # --- famille-cheron（27-36，与 poinard 同源文件）---
    V(27, 'logo-or-graphic', 'not-a-wine', None, 'high', '黑底棕色卡通人物插画（与 poinard 站同文件），非酒款图。'),
    V(28, 'wine-bottle', 'likely-own', 'Crozes-Hermitage', 'medium', '红白格纹标瓶，AOC 行部分可读（CROZES…）；该站混排多家酒庄瓶图。'),
    V(29, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：GIGONDAS 瓶（Roucas de St Pierre），非本产区酒款。'),
    V(30, 'producer-logo', 'not-a-wine', None, 'high', '"DOMAINE DU PRADAS" 徽标块。'),
    V(31, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：GIGONDAS 瓶（Domaine du Pradas），APPELLATION GIGONDAS CONTRÔLÉE。'),
    V(32, 'producer-logo', 'not-a-wine', None, 'high', '"DOMAINE DE ST GENS" 徽标块。'),
    V(33, 'wine-bottle', 'unverified', 'Gigondas', 'high', '原图复核：GIGONDAS 瓶（St Gens L\'Oracle），非本产区酒款。'),
    V(34, 'wine-photo', 'likely-own', None, 'low', '六瓶组合照（Grand Comtadine/Gigondas），标面小字不可读。'),
    V(35, 'wine-photo', 'likely-own', None, 'low', '多瓶组合照（Comtadine 系列），标面小字不可读。'),
    V(36, 'wine-bottle', 'likely-own', 'Crozes-Hermitage', 'medium', '红白格纹标瓶 bloc 变体，AOC 行不可完整判读。'),
    # --- e-guigal（37-45）---
    V(37, 'wine-bottle', 'own-wine', 'Condrieu', 'high', '标面 La Doriane / CONDRIEU。'),
    V(38, 'wine-photo', 'own-wine', 'Côte-Rôtie', 'high', 'La Mouline 瓶景照，标面 CÔTE-RÔTIE 可辨。'),
    V(39, 'wine-bottle', 'own-wine', 'Hermitage', 'high', '原图复核：EX-VOTO ERMITAGE，APPELLATION ERMITAGE CONTRÔLÉE。'),
    V(40, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '原图复核：CHÂTEAUNEUF-DU-PAPE（白）。'),
    V(41, 'wine-bottle', 'own-wine', 'Côte-Rôtie', 'high', 'Brune et Blonde 瓶照，标面 CÔTE-RÔTIE 可辨。'),
    V(42, 'wine-bottle', 'own-wine', 'Tavel', 'high', '原图复核：TAVEL，APPELLATION TAVEL CONTRÔLÉE。'),
    V(43, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '原图复核：Saintes Pierres de Nalys，CHÂTEAUNEUF-DU-PAPE。'),
    V(44, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'medium', 'Château de Nalys 白版，同系列（43 号红版原图已证 CNDP），标面小字在拼图中不可读。'),
    V(45, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'medium', 'Château de Nalys 红版，同上。'),
    # --- julien-pilon（46-50）---
    V(46, 'region-landscape', 'producer-official', None, 'high', '葡萄园风貌照（terroir 页配图）。'),
    V(47, 'producer-estate', 'producer-official', None, 'medium', '白瓶照（文件名提示 dahu blanc），标面小字不可读。'),
    V(48, 'wine-bottle', 'own-wine', None, 'low', '原图复核：双瓶照 "le bruit des vagues — marsanne/roussanne"，标面无 AOC 行。'),
    V(49, 'wine-bottle', 'own-wine', None, 'low', '双白瓶照（文件名提示 viognier grandpère limonadier），标面小字不可读。'),
    V(50, 'producer-estate', 'producer-official', None, 'medium', '葡萄园行间绿篱照（横幅变体）。'),
    # --- grands-vins-selection（51-53）---
    V(51, 'logo-or-graphic', 'not-a-wine', None, 'high', '藏青/金双色块地图式插画。'),
    V(52, 'producer-logo', 'not-a-wine', None, 'high', '"engagements" 植物图标（承诺页图标），非酒款图。'),
    V(53, 'producer-logo', 'not-a-wine', None, 'high', '"engagements" 奖章图标，非酒款图。'),
    # --- lemenicier（54）---
    V(54, 'producer-site', 'producer-official', None, 'medium', '首页横幅裁切（葡萄园远景带果穗），非酒款图。'),
    # --- les-vignes-de-chatiou（55）---
    V(55, 'uncertain', 'not-a-wine', None, 'high', '空白占位图（sloppyframe），无有效内容。'),
    # --- lavau（56-67）---
    V(56, 'producer-logo', 'not-a-wine', None, 'high', '紫色圆形品牌纹样（SF02）。'),
    V(57, 'producer-logo', 'not-a-wine', None, 'high', '紫色圆形品牌纹样（SF01）。'),
    V(58, 'producer-logo', 'not-a-wine', None, 'high', 'LAVAU 紫底字标。'),
    V(59, 'wine-bottle', 'own-wine', 'Côtes du Rhône', 'high', '标面 LAVAU / CÔTES DU RHÔNE（白）。'),
    V(60, 'wine-bottle', 'own-wine', 'Côtes du Rhône', 'high', '标面 LAVAU / CÔTES DU RHÔNE（桃红）。'),
    V(61, 'wine-bottle', 'own-wine', 'Côtes du Rhône Villages', 'high', '标面 LAVAU / CÔTES DU RHÔNE VILLAGES。'),
    V(62, 'wine-bottle', 'own-wine', 'Tavel', 'high', '标面 LAVAU / TAVEL。'),
    V(63, 'wine-bottle', 'own-wine', 'Vacqueyras', 'high', '标面 LAVAU / VACQUEYRAS。'),
    V(64, 'wine-bottle', 'own-wine', 'Gigondas', 'high', '标面 LAVAU / GIGONDAS。'),
    V(65, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '标面 LAVAU / CHÂTEAUNEUF-DU-PAPE。'),
    V(66, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '标面 LAVAU / CROZES-HERMITAGE。'),
    V(67, 'wine-bottle', 'own-wine', 'Côtes du Rhône', 'high', '标面 LAVAU / CÔTES DU RHÔNE（红）。'),
    # --- albert-bichot（68-69）---
    V(68, 'wine-bottle', 'own-wine', None, 'low', '"Secret Ocean" Chardonnay 白标，标面无 AOC 行可读。'),
    V(69, 'wine-bottle', 'own-wine', None, 'low', '同图 1400px 变体（Secret Ocean Chardonnay）。'),
    # --- maison-delas-freres（70-77）---
    V(70, 'producer-logo', 'not-a-wine', None, 'high', '玻璃瓶身浮雕 Delas Frères 纹章特写，非完整酒标。'),
    V(71, 'producer-logo', 'not-a-wine', None, 'high', '同上（375px 变体）。'),
    V(72, 'producer-logo', 'not-a-wine', None, 'high', '同上（750px 变体）。'),
    V(73, 'producer-logo', 'not-a-wine', None, 'high', '同上（375px 变体）。'),
    V(74, 'producer-logo', 'not-a-wine', None, 'high', '同上（750px 变体）。'),
    V(75, 'producer-logo', 'not-a-wine', None, 'high', '同上（1440px 变体）。'),
    V(76, 'producer-logo', 'not-a-wine', None, 'high', '同上（1920px 变体）。'),
    V(77, 'producer-logo', 'not-a-wine', None, 'high', '同上（1920px 变体）。'),
    # --- les-vins-pierre-rougon（78-80）---
    V(78, 'producer-estate', 'producer-official', None, 'high', '老藤特写（酒庄官网 paysages 组图）。'),
    V(79, 'region-landscape', 'stock-or-generic', None, 'medium', '文件名提示 Inter Rhône 素材的梯田风貌照，非酒款图。'),
    V(80, 'region-landscape', 'stock-or-generic', None, 'medium', '文件名含 AdobeStock 编号的图库照片（谢纳坡风貌），非酒款图。'),
    # --- domaine-du-coulet（81-91，Cornas 酒庄）---
    V(81, 'wine-bottle', 'own-wine', 'Cornas', 'high', '原图复核：CORNAS "Billes Noires"。'),
    V(82, 'wine-bottle', 'own-wine', None, 'low', '创意手写标 "Brise Cailloux"，AOC 行不可读。'),
    V(83, 'wine-bottle', 'own-wine', None, 'low', 'Brise Cailloux 橙酒版，标面无 AOC 行可读。'),
    V(84, 'wine-bottle', 'own-wine', None, 'low', '黑底涂鸦标（文件名 5_SAOULS），AOC 行不可读。'),
    V(85, 'wine-bottle', 'own-wine', None, 'low', '黑标 "La Bannière"，AOC 行不可读。'),
    V(86, 'wine-bottle', 'own-wine', None, 'low', '手写标（文件名提示 géniale patronne），AOC 行不可读。'),
    V(87, 'wine-bottle', 'own-wine', None, 'low', '黑标 NOWINESLAND，AOC 行不可读。'),
    V(88, 'wine-bottle', 'own-wine', None, 'low', 'NOWINESLAND 白瓶版，AOC 行不可读。'),
    V(89, 'wine-bottle', 'own-wine', 'Cornas', 'high', '原图复核：CORNAS "Vivre Libre ou Mourir" 2023（泰迪熊持瓶摆拍）。'),
    V(90, 'wine-bottle', 'own-wine', None, 'low', '白瓶 "INGLOURIOUS BROCARD"，AOC 行不可读。'),
    V(91, 'wine-bottle', 'own-wine', None, 'low', '橙酒瓶手绘标（文件名提示 j\'aurais tapauter），AOC 行不可读。'),
    # --- famille-jaume-pascal-richard（92-103）---
    V(92, 'producer-logo', 'not-a-wine', None, 'high', '红色 J 字花体 monogram。'),
    V(93, 'wine-bottle', 'own-wine', 'Vinsobres', 'high', '标面 CLOS DES ÉCHALAS / VINSOBRES（Domaine Jaume）。'),
    V(94, 'wine-bottle', 'own-wine', 'Vinsobres', 'high', '原图复核：Référence / VINSOBRES，APPELLATION VINSOBRES PROTÉGÉE。'),
    V(95, 'wine-bottle', 'own-wine', 'Vinsobres', 'high', '原图复核：Altitude 420 / VINSOBRES，APPELLATION VINSOBRES PROTÉGÉE。'),
    V(96, 'wine-bottle', 'own-wine', 'Côtes du Rhône', 'medium', '白标红字 "Côtes du Rhône"（rouge），AOC 行在拼图中可辨但字形小。'),
    V(97, 'wine-bottle', 'own-wine', 'Côtes du Rhône', 'medium', '同系列桃红版（Côtes du Rhône）。'),
    V(98, 'producer-logo', 'not-a-wine', None, 'high', '红色 J 字花体 monogram（变体）。'),
    V(99, 'producer-logo', 'not-a-wine', None, 'high', '红色 J 字花体 monogram（变体）。'),
    V(100, 'producer-estate', 'producer-official', None, 'high', '薰衣草丛中 "CLOS DES ÉCHALAS" 石刻地块标牌。'),
    V(101, 'producer-estate', 'stock-or-generic', None, 'medium', '酒窖成摞瓶照（文件名提示 stock 图库照）。'),
    V(102, 'producer-people', 'producer-official', None, 'high', '黑白人物肖像（签名页配图）。'),
    V(103, 'wine-bottle', 'own-wine', 'Vinsobres', 'high', '标面 Domaine Jaume / VINSOBRES（Clos des Échalas 变体图）。'),
    # --- newrhone-millesimes（104-110，均为横幅裁切）---
    V(104, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（枝叶特写），非酒款图。'),
    V(105, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（葡萄园行），非酒款图。'),
    V(106, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（倒酒场景），非酒款图。'),
    V(107, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（酒窖瓶列），非酒款图。'),
    V(108, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（品鉴场景），非酒款图。'),
    V(109, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（枝叶），非酒款图。'),
    V(110, 'producer-site', 'producer-official', None, 'medium', '网页横幅裁切（田块风貌），非酒款图。'),
    # --- ogier（111-116）---
    V(111, 'region-harvest', 'producer-official', None, 'high', '采摘者劳作照（人物戴帽采果）。'),
    V(112, 'document-map', 'not-a-wine', None, 'high', '绿底罗讷产区分布图。'),
    V(113, 'producer-logo', 'not-a-wine', None, 'high', '黑底 OGIER 字标（红色色块装饰）。'),
    V(114, 'wine-bottle', 'own-wine', 'Condrieu', 'high', '标面 OGIER / CONDRIEU。'),
    V(115, 'wine-photo', 'likely-own', None, 'low', '木箱中多瓶白葡萄酒瓶景照，标面小字不可读。'),
    V(116, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '原图复核：OGIER L\'ÂNE / APPELLATION CHÂTEAUNEUF-DU-PAPE CONTRÔLÉE。'),
    # --- paul-jaboulet-aine（117-120）---
    V(117, 'wine-bottle', 'own-wine', None, 'low', '原图复核：Viognier Secret de Famille 2024，标面仅注 France，无 AOC 行。'),
    V(118, 'region-landscape', 'producer-official', None, 'medium', '山坡葡萄园风貌照；文件名提示 Cornas Reynard，图内未验证。'),
    V(119, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '原图复核：Saint-Joseph Le Grand Pompée 2024（白）。'),
    V(120, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '标面 CROZES-HERMITAGE Les Jalets（白）。'),
    # --- brotte（121-132）---
    V(121, 'wine-bottle', 'own-wine', None, 'low', '白标 "Domaine Grosset"，AOC 行不可读。'),
    V(122, 'wine-bottle', 'own-wine', None, 'low', '红字手写体 "Domaine Grosset"，AOC 行不可读。'),
    V(123, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '标面 Domaine Barville / Châteauneuf-du-Pape（红）。'),
    V(124, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'medium', '同系列白版（Barville），AOC 行小字在拼图中不可读。'),
    V(125, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'high', '原图复核：LES HAUTS DE BARVILLE / APPELLATION CHÂTEAUNEUF-DU-PAPE CONTRÔLÉE（白）。'),
    V(126, 'wine-bottle', 'own-wine', 'Châteauneuf-du-Pape', 'medium', '同系列红版（Hauts de Barville）；125 号原图已证 AOC，本图标面小字不可读。'),
    V(127, 'wine-bottle', 'own-wine', None, 'low', '白瓶钥匙孔图案 "Secret"，AOC 行不可读。'),
    V(128, 'wine-bottle', 'own-wine', 'Condrieu', 'high', '标面 CONDRIEU。'),
    V(129, 'wine-bottle', 'own-wine', 'Côte-Rôtie', 'high', '标面 CÔTE-RÔTIE。'),
    V(130, 'wine-bottle', 'own-wine', None, 'low', '"ESPRIT" 白版，AOC 行在拼图中不可读。'),
    V(131, 'wine-bottle', 'own-wine', None, 'low', '"ESPRIT" 桃红版，AOC 行在拼图中不可读。'),
    V(132, 'wine-bottle', 'own-wine', None, 'low', '"ESPRIT" 红版，AOC 行在拼图中不可读。'),
    # --- maison-gabriel-meffre（133-134）---
    V(133, 'uncertain', 'not-a-wine', None, 'high', '全黑矩形，内容不可判读（疑似深色 logo 图）。'),
    V(134, 'logo-or-graphic', 'not-a-wine', None, 'high', '绿底葡萄藤白描插画。'),
    # --- pierre-jean-villa（135-145）---
    V(135, 'wine-bottle', 'own-wine', 'Condrieu', 'high', '标面 CONDRIEU "Jardin Suspendu"。'),
    V(136, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '原图复核：SAINT-JOSEPH "Saut de l\'Ange"。'),
    V(137, 'wine-bottle', 'own-wine', None, 'high', '原图复核："PRIMAVERA VIOGNIER"，标面无 AOC 行。'),
    V(138, 'wine-bottle', 'own-wine', None, 'low', '"ESPRIT D\'ANTAN VIOGNIER"，未见 AOC 行。'),
    V(139, 'wine-bottle', 'own-wine', 'Côte-Rôtie', 'high', '标面 CÔTE-RÔTIE "Fongeant"。'),
    V(140, 'wine-bottle', 'own-wine', 'Côte-Rôtie', 'high', '标面 CÔTE-RÔTIE "Carmina"。'),
    V(141, 'wine-bottle', 'own-wine', None, 'low', '"ESPRIT D\'ANTAN SYRAH"，未见 AOC 行。'),
    V(142, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '标面 SAINT-JOSEPH "Préface"。'),
    V(143, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '标面 SAINT-JOSEPH "Tilde"。'),
    V(144, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '标面 CROZES-HERMITAGE "Accroche-Cœur"。'),
    V(145, 'wine-bottle', 'own-wine', None, 'low', '"Gamine" Syrah，AOC 行在拼图中不可读。'),
    # --- vignoble-amira（146-153）---
    V(146, 'producer-logo', 'not-a-wine', None, 'high', '黑底 VIGNOBLE AMIRA 字标横幅。'),
    V(147, 'wine-bottle', 'own-wine', 'Brézème', 'high', '原图复核：标面 BRÉZÈME 2023（无单独 AOC 行）。'),
    V(148, 'wine-bottle', 'own-wine', None, 'high', '原图复核："éClos" ROUSSANNE，标面无 AOC 行。'),
    V(149, 'wine-bottle', 'own-wine', None, 'low', '"éClos" 瓶照，AOC 行在拼图中不可读。'),
    V(150, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '原图复核：标面 Flower / CROZES-HERMITAGE；启发式误记 Saint-Péray。'),
    V(151, 'wine-bottle', 'own-wine', 'Crozes-Hermitage', 'high', '原图复核：标面 Genèse / CROZES-HERMITAGE。'),
    V(152, 'wine-bottle', 'own-wine', 'Saint-Joseph', 'high', '原图复核：标面 Ozons! / SAINT-JOSEPH。'),
    V(153, 'wine-bottle', 'own-wine', 'Brézème', 'high', '标面大字 BREZÈME（mag 版）。'),
    # --- vincent-paris-selection（154-158，博客文章配图）---
    V(154, 'producer-site', 'not-a-wine', None, 'high', '酒窖/门店人物照（文章配图），非酒款图。'),
    V(155, 'producer-site', 'not-a-wine', None, 'high', '白葡萄酒与酒杯摆拍（文章配图）。'),
    V(156, 'producer-site', 'not-a-wine', None, 'high', '葡萄园中手机拍瓶特写（文章配图）。'),
    V(157, 'producer-site', 'not-a-wine', None, 'high', '门店内人物合影（文章配图）。'),
    V(158, 'producer-site', 'not-a-wine', None, 'high', '红葡萄酒佐餐场景（文章配图）。'),
    # --- vins-jean-luc-colombo（159-170）---
    V(159, 'producer-logo', 'not-a-wine', None, 'high', '"Jean-Luc Colombo VINS CC" 签名字标。'),
    V(160, 'wine-bottle', 'own-wine', None, 'low', '白底品牌标瓶（"Design sans titre" 系列电商图），AOC 行不可读。'),
    V(161, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 3）。'),
    V(162, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 4）。'),
    V(163, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 5）。'),
    V(164, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 19，标面小字提示 Syrah 系）。'),
    V(165, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 20）。'),
    V(166, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 21）。'),
    V(167, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 13）。'),
    V(168, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 18）。'),
    V(169, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 12）。'),
    V(170, 'wine-bottle', 'own-wine', None, 'low', '同上（变体 7，桃红）。'),
])

# ---- 自检 ----
manifest = json.loads(MANIFEST.read_text())
have = {'%s|%s' % (e['slug'], g['file'])
        for e in manifest['producers'] for g in (e.get('images') or [])}
missing = sorted(set(V2) - have)
old = json.loads(REVIEW.read_text())
overlap = sorted(k for k in V2 if k in old and old[k].get('role') != V2[k]['role'])

print('verdicts: %d | keys not in manifest (%d): %s | role changed vs round-1 (%d): %s'
      % (len(V2), len(missing), missing, len(overlap), overlap))

extra = sorted(have & set(old) - set(V2))
if not missing:
    REVIEW.write_text(json.dumps({**old, **V2}, ensure_ascii=False, indent=1) + '\n')
    print('review total -> %d' % (len(old) + len(V2)))
else:
    print('ABORT: 未写入（有键不在 manifest）')
