/* 底图（basemap）配置 —— 2026-09-22 换掉 OpenTopoMap
 *
 * 为什么要换：原来这里直接引 `https://{s}.tile.opentopomap.org/...`（境外 OSM 系瓦片）。
 *   ① 合规：境内地图服务只能用 天地图 / 腾讯 / 高德 / 百度，境外瓦片属红线；
 *   ② 可用性：从境内访问经常整片加载不出来（表现为 tileerror 后提示「详细底图加载较慢」）。
 *
 * 默认走 `vector`：**不引入任何第三方瓦片**，底图直接用站点自带的 /assets/world.geojson 矢量地理
 *   （海 #e6ede8 / 陆 #f4f5ef 是 style.css 里 #map 的既有配色，本来就是这个观感）。
 *   好处：零 key、零境外请求、与站点数据同为 WGS-84 因此没有偏移。
 *
 * 想要真正的底图（路网 / 地形 / 地名注记，且边界为国标口径）就切 `tianditu`：
 *   ① 到 https://console.tianditu.gov.cn/api/key 免费申请一个 tk（个人开发者即可）；
 *   ② 申请时把 Referer 白名单填成站点域名（例如 your-domain.example.com）——前端明文 key 靠这个兜；
 *   ③ 把下面的 KIND 改成 'tianditu'、TIANDITU_KEY 填上 tk，重新部署即可。
 *   没填 tk 时会自动回落 vector，不会白屏。
 */
window.WineBasemap = (function () {
  'use strict';

  // ── 只改这两行就能切换底图 ────────────────────────────────────────────
  var KIND = 'vector'; // 'vector'（默认，零 key）| 'tianditu'（需填 tk）
  var TIANDITU_KEY = ''; // 申请到的天地图 tk
  // ────────────────────────────────────────────────────────────────────

  var TIANDITU_ATTRIBUTION =
    '&copy; <a href="https://www.tianditu.gov.cn/">天地图</a>';

  function tianditu(key) {
    // vec_w = 矢量底图，cva_w = 中文注记；两者都是 EPSG:3857，Leaflet 可直接用
    var opts = { subdomains: '01234567', maxZoom: 19, maxNativeZoom: 18 };
    return [
      L.tileLayer(
        'https://t{s}.tianditu.gov.cn/DataServer?T=vec_w&x={x}&y={y}&l={z}&tk=' + key,
        opts
      ),
      L.tileLayer(
        'https://t{s}.tianditu.gov.cn/DataServer?T=cva_w&x={x}&y={y}&l={z}&tk=' + key,
        opts
      ),
    ];
  }

  /** 返回 {layers: L.Layer[], attribution: string}。layers 为空 = 纯矢量底图。 */
  function create() {
    if (KIND === 'tianditu' && TIANDITU_KEY) {
      return {
        layers: tianditu(TIANDITU_KEY),
        attribution: TIANDITU_ATTRIBUTION,
        kind: 'tianditu',
      };
    }
    // 纯矢量模式不需要额外 attribution —— world.geojson 的 Natural Earth 归属
    // 由 app.js 自己 addAttribution，别在这里重复加。
    return { layers: [], attribution: '', kind: 'vector' };
  }

  return {
    create: create,
    get kind() {
      return KIND === 'tianditu' && TIANDITU_KEY ? 'tianditu' : 'vector';
    },
  };
})();
