# 数据许可 / Data License

代码部分适用 [`LICENSE`](LICENSE)（MIT）。**本文件只说明数据部分的许可。**

`data/` 下的结构化数据（`catalog-seed.json`、`events.json`、`entity-photos.json`、
`region-boundary-sources.json` 等）与 `public/*.geojson` 边界几何，
采用 **Creative Commons Attribution 4.0 International（CC BY 4.0）**：
<https://creativecommons.org/licenses/by/4.0/>

你可以出于任何目的共享与改编这些数据，**只需注明来源**。

---

## 上游来源各自的许可

本仓库的数据是**对官方开放数据的汇编**，各上游仍持有自己的许可。
再分发时需同时遵守：

| 上游 | 覆盖范围 | 许可 |
|---|---|---|
| [INAO](https://www.data.gouv.fr/fr/datasets/aires-geographiques-des-aoc-aop/) | 法国 AOC 法定范围（commune 级） | Licence Ouverte / Etalab |
| [geo.api.gouv.fr](https://geo.api.gouv.fr/) | 法国市镇边界几何 | Licence Ouverte / Etalab |
| [IGN Admin Express](https://github.com/gregoiredavid/france-geojson) | 法国省级行政界 | Licence Ouverte / Etalab |
| [EU eAmbrosia](https://ec.europa.eu/agriculture/eambrosia/) | 欧盟 PDO/PGI 地理标志 | EU 开放数据 |
| [OpenStreetMap](https://www.openstreetmap.org/) | 葡萄园分布 / 酒庄点位 | **ODbL 1.0**，© OpenStreetMap contributors |
| [Natural Earth](https://www.naturalearthdata.com/) | 底图 | 公有领域 |

> **ODbL 特别说明**：由 OpenStreetMap 派生的几何
> （即 `boundaryType` 为 `vineyard_distribution` 的边界，以及酒庄点位）
> 受 ODbL 1.0 约束，属**传染性**许可。如果你要把这部分数据与自己的数据混合后分发，
> 需按 ODbL 要求同样开放衍生数据。若只想宽松使用，**请排除这部分**。

---

## 图片

本仓库**不包含任何第三方图片素材**。`data/entity-photos.json` 只记录图片的
元信息（sha256、原页地址、拍摄者署名），用于溯源与按请求下架，
不含图片文件本身。原始项目中收集的图片版权归各酒庄 / 协会 / 摄影师所有。

---

## 免责

本项目是**数据汇编与可视化**，不构成法律、投资或商业建议。
边界几何可能存在简化（见各条 Feature 的 `precision` 与 `note` 字段），
**不应用于任何法律或产权判定**。法定范围的权威解释以各产区官方
*cahier des charges* 与主管机构公布为准。
