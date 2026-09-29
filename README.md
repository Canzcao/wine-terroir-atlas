# 风土图鉴 · Terroir Atlas

一个**中文交互式葡萄酒产区地图**，也是一份**结构化的世界葡萄酒产区数据资产**。

![产区](https://img.shields.io/badge/产区-196-informational) ![国家](https://img.shields.io/badge/国家-29-informational) ![酒庄](https://img.shields.io/badge/酒庄-2794-informational) ![酒款](https://img.shields.io/badge/酒款-1352-informational) ![边界](https://img.shields.io/badge/法定边界-183-success) ![许可](https://img.shields.io/badge/license-MIT-blue)

[![CI](https://github.com/Canzcao/wine-terroir-atlas/actions/workflows/ci.yml/badge.svg)](https://github.com/Canzcao/wine-terroir-atlas/actions/workflows/ci.yml)

> 在线预览：<https://terroir.vincode.chat>

## 这是什么

一张地图 + 一套数据。**重点在数据口径**：

- **产区分级严格对齐权威标准**。法国产区按 **WSET Level 3 官方考纲**（2024 Issue 2）的 98 条列名产区逐条核对，覆盖率 100%；层级按 WSET 四阶梯（大区 → 次区 → 村庄 → 地块）挂载。
- **边界是官方法定范围，不是近似**。法国 AOC 的法定范围由 `cahier des charges` 以 commune 清单定义，直接取 **INAO**（法国农业部下属国家原产地与质量研究所）的开放数据；意大利/西班牙等取 EU eAmbrosia PDO；美国取 AVA。每一次导入都记录来源、许可、检索时间与几何指纹。
- **每个字段都能追到源头**。实体带 `sourceTitle` / `sourceURL` / `checkedDate`；边界带 `sourceName` / `sourceURL` / `license`；图片带 `sha256` 与原页地址（便于按请求下架）。
- **不猜、不补、不推断**。未知的坐标、品种、产权、产量一律留 `null` 并显式标注，不用相邻产区的数据填充。

## 数据规模

| 类型 | 数量 | 说明 |
|---|---|---|
| 产区 region | **196** | 覆盖 29 个国家 |
| 酒庄 winery | **2794** | 带坐标的才上图 |
| 酒款 wine | **1352** | |
| 年份 vintage | **469** | |
| 品种 grape | **299** | |
| 法定边界 | **183** | 含 AOC / PDO / AVA / 行政区兜底 |
| 世界动态 event | **149** | 新闻 / 事件 / 采收 / 天气 / 灾害 |

### 法国产区（WSET L3 对齐成果）

按 WSET L3 考纲的 8 大区重组，覆盖率 **100%（98/98 条列名）**：

```
波尔多 bordeaux ── 左岸 / 右岸 / 两海之间 ── 各 AOC（Pauillac / Margaux / Pomerol …）
勃艮第 burgundy ── Côte de Beaune / Côte Chalonnaise / Chablis / Mâconnais ── 村庄 AOC
罗讷河谷 rhone ── 北罗讷 8 个 Crus（Côte-Rôtie / Condrieu / Hermitage …）+ 南罗讷 Crus
卢瓦尔河谷 loire ── Anjou / Saumur / Touraine …
阿尔萨斯 alsace ── Alsace Grand Cru（51 个单一园并集）
博若莱 beaujolais ── Beaujolais / Brouilly / Fleurie / Morgon …
法国西南 south-west ── Bergerac / Cahors / Madiran / Jurançon …
法国南部 southern-france ── Languedoc / Roussillon / Provence / IGP Pays d'Oc
```

> **大区本身不画边界**。波尔多、罗讷河谷、勃艮第这些是**聚合层级**，不是法定产区 ——
> 拿其中某一支 AOC 的范围冒充整个大区，会让人误以为「罗讷河谷只有这么一小块」。
> 所以只给各个 AOC 的法定范围，大区留给使用者点开子项查看。（唯一例外是 `bordeaux`
> 下的三个岸分区，它们本身有明确的官方地理定义。）

## 数据格式

`data/catalog-seed.json` 是**顶层数组**，每条形如：

```json
{
  "id": "pauillac",
  "kind": "region",
  "name": "波亚克",
  "data": {
    "name": "波亚克",
    "en": "Pauillac",
    "country": "法国",
    "regionId": "haut-medoc",
    "geoZone": "Haut-Médoc（左岸，Médoc 南部）",
    "sourceTitle": "Conseil Interprofessionnel du Vin de Bordeaux (CIVB)",
    "sourceURL": "https://www.bordeaux.com/",
    "checkedDate": "2026-09-29"
  },
  "version": 1,
  "updated": "2026-09-29T10:00:00.000Z"
}
```

关键字段：

- `kind` — `region` / `winery` / `wine` / `vintage` / `grape` / `parcel`
- `data.regionId` — **父级指针**。产区树靠它表达层级（村 `pauillac` → 次区 `haut-medoc` → 岸 `bordeaux-left-bank` → 大区 `bordeaux`）
- `data.geoZone` — 人类可读的地理分区标签
- `data.sourceURL` — **每个实体必有**，校验器会强制

`public/region-boundaries.geojson` 是标准 GeoJSON FeatureCollection。

**每个 Feature 都有的字段**（183/183）：

| 字段 | 说明 |
|---|---|
| `regionId` | 指向 catalog 里的产区实体，**全表唯一**（一个产区最多一条边界） |
| `label` | 地图上显示的名称 |
| `boundaryType` | 取值范围见下表 |
| `sourceName` / `sourceURL` | 边界数据出处（校验器强制） |
| `license` / `licenseURL` | 数据许可（校验器强制） |
| `checkedDate` | 该条最后一次人工核对日期 |
| `note` | 口径说明。**把「这不是法定界线」这类限定写在这里**，而不是靠使用者猜 |

**类型专属字段**（只在对应 `boundaryType` 上出现）——命名即含义：

| 字段 | 出现于 | 说明 |
|---|---|---|
| `precision` | 77 条 | `parcellaire`（地块级，最高）> `commune`（市镇级）> `province` / `county`。**只在法国式「按 commune 清单定义」的 AOC 上有意义**，其他类型不填 |
| `areaKm2` | 88 条 | 边界面积（km²） |
| `appellationNames` / `communeCount` / `communeMissing` | 77 条 | 该 AOC 覆盖的法定产区名与市镇数、未取到几何的市镇数 |
| `mappedVineyardKm2` / `envelopeKm2` / `blockCount` / `officialVineyardKm2` / `coverageRatio` / `coverageVerdict` | 15 条 | `vineyard_distribution` 专用：实测葡萄园面积、外接范围、地块数、官方公布面积与覆盖率判定 |
| `countyCount` / `countyNames` / `countyMissing` / `officialGI` | 10 条 | `administrative_fallback` 专用 |
| `giSystem` / `giDesignated` | 3 条 | AVA 专用（登记体系与生效日期） |
| `parcelFeatureCount` / `previousAreaKm2` / `previousBoundaryType` | 2 条 | 地块级专用；`previous*` 记录口径变更前的值，**便于审计** |

> 字段不全的情况是**有意的**：`precision` 对 IGP/AVA 没有意义，硬填反而会误导。校验器只强制上表「每个 Feature 都有」的那几项。

`boundaryType` 的取值与含义：

| 值 | 数量 | 含义 |
|---|---|---|
| `geographical_indication` | 131 | 地理标志范围（IGP / GI / AOC 法定 aire），**权威** |
| `appellation_geographical_area` | 21 | 法定产区（AOC/AOP）官方地理范围 |
| `vineyard_distribution` | 15 | **非边界**：无官方边界时用 OSM 实测葡萄园地块的分布范围，`note` 明确声明「不是法定产区界线」 |
| `administrative_fallback` | 10 | **行政兜底**，不是法定产区范围（明确标注） |
| `american_viticultural_area` | 3 | 美国 TTB 登记的 AVA |
| `administrative_county` | 3 | 官方县界兜底（美国 Sonoma / 英国 Sussex / 中国台湾地区） |

> 为什么分这么细？因为**「这块地是什么」会改变用户对它的信任程度**。法定范围可以拿来判断酒庄归属，葡萄园分布只能说明「这一带种葡萄」，行政兜底只是「大致在这一片」。混在一起会让人把示意当成法条。

## 使用

环境要求：**Node.js 22+**（无其他系统依赖；GIS 相关的导入脚本另需 Python 3 + `pyshp`/`pyproj`/`shapely`）。

```bash
npm install

npm run build          # 构建（把 public/ 静态资源嵌入 dist/server/index.js）
npm run dev            # 本地预览 http://localhost:4173
npm test               # 测试（授权 / 并发 / 审核 / 文件访问 / 边界口径）
npm run validate       # 校验数据关联与来源字段
node scripts/validate-reports.mjs # 校验简报
```

> `npm test` 会**先自动构建**（`pretest`），因为 `tests/workflows.test.mjs` 用 miniflare
> 加载 `dist/server/index.js`。若直接跑 `node --test tests/*.test.mjs`，务必先构建，
> 否则该用例会以 `ENOENT: dist/server/index.js` 失败。

推送与 PR 都会触发 CI（`.github/workflows/ci.yml`）：校验数据 → 构建 → 跑测试。

### 部署

部署目标通过环境变量提供，仓库里**不含任何具体服务器地址**：

```bash
SERVER=root@your.server.ip REMOTE_DIR=/opt/terroir-atlas \
  npm run build && bash deploy/deploy.sh
```

`deploy/` 下：

- `deploy.sh` — macOS/Linux 版（rsync）
- `deploy.local.sh` — Windows / Git Bash 版（无 rsync，用 `tar | ssh`，photos 走增量）
- `server-setup.sh` — 服务器初始化（nginx + pm2 + 证书）
- `nginx.conf.example` — nginx 站点配置模板

## 数据来源与许可

本项目的数据来自**官方机构与开放数据**，逐条记录来源与许可：

| 来源 | 用途 | 许可 |
|---|---|---|
| [INAO](https://www.data.gouv.fr/fr/datasets/aires-geographiques-des-aoc-aop/) — Aires géographiques des AOC/AOP | 法国 AOC 法定范围（commune 级） | Licence Ouverte / Etalab |
| [geo.api.gouv.fr](https://geo.api.gouv.fr/) | 法国市镇边界几何 | Licence Ouverte / Etalab |
| [IGN Admin Express](https://github.com/gregoiredavid/france-geojson) | 法国省级行政界 | Licence Ouverte / Etalab |
| [EU eAmbrosia](https://ec.europa.eu/agriculture/eambrosia/) | 欧盟 PDO/PGI 地理标志 | EU 开放数据 |
| [OpenStreetMap](https://www.openstreetmap.org/) | 葡萄园 / 酒庄点位 | ODbL 1.0，© OpenStreetMap contributors |
| [Natural Earth](https://www.naturalearthdata.com/) | 底图 | 公有领域 |
| [WSET](https://www.wsetglobal.cn/) Level 3 考纲 | 产区分级结构依据 | 结构参照，非内容转载 |

> **图片**：本仓库不包含第三方图片素材。原始项目中收集的图片版权归各酒庄/协会/摄影师所有，仅供本地研究，未随本仓库分发。

## 设计原则

1. **官方图形，绝不反推**。不接受「把几个酒庄点位连起来」「用行政区拼出产区」这类做法；官方只给行政界时，`boundaryType` 必须标 `administrative_fallback` 并在 `note` 里说明它不是法定范围。
2. **大区不能悄悄缩成更小的产区**。宁可不给边界，也不给一个误导的——因为地图上点开会让人误以为「这块地就是这个大区」。
3. **来源可追、修订留痕**。每个实体带版本号、来源、校验日期；编辑需带预期版本号；审核者不能批准自己的提交。
4. **数据校验是硬门槛**。`validate-data.mjs` 会拦下缺来源、断链引用、重复 ID 的数据。

## 参与贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

- **代码**：[MIT](LICENSE)
- **数据**（`data/`、`public/*.geojson`）：[CC BY 4.0](LICENSE-DATA.md) —— 可自由使用，请注明来源。
  注意上游 OpenStreetMap 派生的部分（葡萄园分布、酒庄点位）是 **ODbL 1.0** 传染性许可，
  混合分发时需同样开放 —— 细节见 [`LICENSE-DATA.md`](LICENSE-DATA.md)。
