# 风土图鉴 · Terroir Atlas

中文交互式葡萄酒地图。19 个国家、34 个精选产区、52 个品种及 35 家代表酒庄；支持查询全球视野内的 OpenStreetMap 葡萄园和酒庄。

## 使用

静态入口为 `dist/index.html`，需通过 HTTP 服务访问。选择产区查看主要品种和酒庄；放大后查询当前位置的公开地块。搜索框支持中文或英文；右侧箭头在 Nominatim 中查找地理位置。

## 数据口径

- 产区标记是浏览中心，不是法定边界；索引不构成完整的全球产区名录。
- 产区概况来自条目链接的协会、行业机构、酒庄及专业资料。整理日期 2026-09-12，不保证与当前种植情况同步。
- 地块几何与酒庄位置来自 OpenStreetMap，ODbL 1.0，© OpenStreetMap contributors。OSM 葡萄园记录可能指用地或命名葡萄园区域，不等同于地籍或产权边界；也不保证均为酿酒葡萄。
- 已收录的沃恩-罗曼尼周边 GeoJSON 包含 131 处葡萄园，来自 2026-09-12 的 OSM 数据。原始查询范围：南 47.15、西 4.93、北 47.17、东 4.97。
- 罗曼尼·康帝园和拉塔希园的品种、经营者信息据酒庄公开资料单独补充，并与 OSM 轮廓分别标注来源。其他记录没有品种标签时明确显示未提供，不用产区品种填充。
- 地图图形面积是球面近似计算，不是登记面积。
- 详细地图为 OpenTopoMap（CC-BY-SA 3.0）/ OSM / SRTM；基础地图为 Natural Earth 公有领域数据。原始数据：https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson
- 外部地块服务只在用户点击时请求小范围数据，有超时、备用端点和内存缓存。地点检索不进行自动补全。

## 第三方库

Leaflet 1.9.4（BSD-2-Clause）与 osmtogeojson 3.0.0-beta.5（MIT）；授权文本保留在 `dist/assets`。

## 部署

Sites 静态站点，发布目录见 `.openai/hosting.json`。无需应用数据库、登录表单或私密密钥。Sites 的访问控制独立于页面代码。
